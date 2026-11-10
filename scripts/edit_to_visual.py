#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild visual and pick artifacts from an edited semantic SVG."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import cairosvg
import numpy as np
from PIL import Image


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)


def _root_size(root: ET.Element, width: int | None, height: int | None) -> tuple[int, int, float, float]:
    viewbox = (root.attrib.get("viewBox") or "").replace(",", " ").split()
    if len(viewbox) != 4:
        raise ValueError("edit master needs a four-value viewBox")
    vx, vy, vw, vh = (float(v) for v in viewbox)
    return (width or int(round(vw)), height or int(round(vh)), vx, vy)


def _svg_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _render(root: ET.Element, width: int, height: int,
            background: str | None = None) -> np.ndarray:
    png = cairosvg.svg2png(bytestring=_svg_bytes(root), output_width=width,
                           output_height=height, background_color=background)
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def _direct_groups(root: ET.Element) -> list[ET.Element]:
    return [child for child in list(root)
            if child.attrib.get("data-element")]


def _single_group(root: ET.Element, target: ET.Element) -> ET.Element:
    target_index = list(root).index(target)
    clone = copy.deepcopy(root)
    for index, child in enumerate(list(clone)):
        if index == target_index or child.tag.rsplit("}", 1)[-1] == "defs":
            continue
        clone.remove(child)
    return clone


def _hex(rgb: np.ndarray) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def _derived_trace(edit_root: ET.Element, groups: list[ET.Element],
                   masks: dict[str, np.ndarray], render: np.ndarray,
                   width: int, height: int, vx: float, vy: float) -> ET.Element:
    from shade_smooth import smoothed_clip_svg

    out = ET.Element("{%s}svg" % SVG_NS, {
        "width": str(width), "height": str(height),
        "viewBox": "%g %g %d %d" % (vx, vy, width, height),
    })
    for group in groups:
        eid = group.attrib["data-element"]
        mask = masks[eid]
        d = smoothed_clip_svg(mask, iters=1, eps=0.8, dilate=0)
        if not d:
            raise ValueError("empty semantic mask: %s" % eid)
        pixels = render[:, :, :3][mask]
        fill = _hex(np.median(pixels, axis=0)) if len(pixels) else "#ffffff"
        g = ET.SubElement(out, "{%s}g" % SVG_NS, {
            "id": group.attrib.get("id", eid),
            "data-element": eid,
            "data-label": group.attrib.get("data-label", ""),
        })
        ET.SubElement(g, "{%s}path" % SVG_NS, {"d": d, "fill": fill})
    for child in edit_root:
        if child.attrib.get("data-role") == "text":
            out.append(copy.deepcopy(child))
    return out


def render_edit_master(edit_svg: Path, outdir: Path, stem: str,
                       width: int | None = None,
                       height: int | None = None,
                       expected_ids: list[str] | None = None) -> tuple[Path, Path, list[str]]:
    root = ET.parse(edit_svg).getroot()
    if root.attrib.get("data-contract") != "semantic-edit":
        raise ValueError("edit master must use data-contract=\"semantic-edit\"")
    for child in root:
        if (child.tag.rsplit("}", 1)[-1] == "g"
                and child.attrib.get("data-role") != "text"
                and not child.attrib.get("data-element")):
            raise ValueError("semantic group is missing data-element")
    groups = _direct_groups(root)
    ids = [g.attrib["data-element"] for g in groups]
    if not groups:
        raise ValueError("edit master contains no data-element groups")
    if len(ids) != len(set(ids)):
        seen = set()
        dupes = set()
        for eid in ids:
            if eid in seen:
                dupes.add(eid)
            else:
                seen.add(eid)
        dupes = sorted(dupes)
        raise ValueError("duplicate semantic IDs: %s" % dupes)
    if expected_ids is not None and set(ids) != set(expected_ids):
        raise ValueError("edit master IDs differ from release: missing=%s extra=%s"
                         % (sorted(set(expected_ids) - set(ids)),
                            sorted(set(ids) - set(expected_ids))))
    W, H, vx, vy = _root_size(root, width, height)
    if W <= 0 or H <= 0:
        raise ValueError("edit master dimensions must be positive")
    outdir.mkdir(parents=True, exist_ok=True)
    render_path = outdir / (stem + "_edit_render.png")
    trace_path = outdir / (stem + "_derived_trace.svg")

    render = _render(root, W, H, "white")
    Image.fromarray(render[:, :, :3]).save(render_path)
    masks = {}
    for group in groups:
        one = _single_group(root, group)
        alpha = _render(one, W, H, None)[:, :, 3]
        masks[group.attrib["data-element"]] = alpha > 8
    trace = _derived_trace(root, groups, masks, render, W, H, vx, vy)
    trace_path.write_bytes(_svg_bytes(trace))
    return render_path, trace_path, ids


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha(path)}


def build_visual(edit_svg: Path, manifest_path: Path, outdir: Path, stem: str,
                 preset: str = "balanced", size: str = "") -> dict:
    from pick_layer import tag_root
    from semantic_release import element_ids, visible_sil

    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    width = height = None
    if size:
        width, height = (int(v) for v in size.lower().replace("*", "x").split("x"))
    else:
        bitmap = source_manifest.get("truth_source", {}).get("bitmap", {}).get("path")
        if bitmap:
            width, height = Image.open(bitmap).size
    expected_ids = source_manifest.get("element_ids") or None
    render, trace, ids = render_edit_master(
        edit_svg, outdir, stem, width, height, expected_ids)
    cells = {
        "draft": "8,plate=6,default=4",
        "balanced": "background=8,plate=6,default=4",
        "fidelity": "background=6,plate=4,default=2",
    }
    visual = outdir / (stem + "_visual_mesh.svg")
    cmd = [
        sys.executable, str(Path(__file__).with_name("shade_smooth.py")),
        "--src", str(render), "--trace", str(trace),
        "--stem", stem + "_visual", "--outdir", str(outdir),
        "--cell", cells[preset],
    ]
    subprocess.run(cmd, check=True)
    visual_ids = element_ids(visual.read_text(encoding="utf-8"))
    if set(visual_ids) != set(ids):
        raise ValueError("visual semantic IDs differ from edit master")

    sil = outdir / (stem + "_visible_sil.json")
    visible_sil(trace, sil)
    pick = outdir / (stem + "_visual_pick.svg")
    subprocess.run([
        sys.executable, str(Path(__file__).with_name("pick_layer.py")),
        str(visual), "--sil", str(sil), "-o", str(pick),
        "--artifact-role", "visual-pick", "--contract", "object-pick",
    ], check=True)
    pick.write_text(tag_root(pick.read_text(encoding="utf-8"),
                             "visual-pick", "object-pick"), encoding="utf-8")
    manifest = outdir / (stem + "_edit_release.json")
    data = {
        "schema": "hep-nature-figure/edit-to-visual-v1",
        "stem": stem,
        "preset": preset,
        "source_release": str(manifest_path),
        "source_release_sha256": _sha(manifest_path),
        "edit_master": _record(edit_svg),
        "element_ids": ids,
        "derivatives": {
            "edit_render": _record(render),
            "derived_trace": _record(trace),
            "visual_master": _record(visual),
            "visual_pick": _record(pick),
        },
        "rules": [
            "edit-master is the semantic editing source",
            "visual-master and visual-pick are derived artifacts",
            "unsupported topology changes fail rather than synthesize texture",
        ],
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="rebuild visual/pick from an edit master")
    ap.add_argument("--edit", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--stem", required=True)
    ap.add_argument("--size", default="", help="optional WxH")
    ap.add_argument("--preset", choices=["draft", "balanced", "fidelity"],
                    default="balanced")
    ap.add_argument("--trace-only", action="store_true")
    a = ap.parse_args()
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    # Resolve source size from the manifest's original bitmap unless overridden.
    width = height = None
    if a.size:
        width, height = (int(v) for v in a.size.lower().replace("*", "x").split("x"))
    else:
        bitmap = manifest.get("truth_source", {}).get("bitmap", {}).get("path")
        if bitmap:
            width, height = Image.open(bitmap).size
    if a.trace_only:
        render, trace, ids = render_edit_master(
            Path(a.edit).resolve(), Path(a.outdir).resolve(), a.stem, width, height,
            manifest.get("element_ids") or None)
        print("edit render=%s trace=%s ids=%d" % (render, trace, len(ids)))
        return 0
    data = build_visual(Path(a.edit).resolve(), Path(a.manifest).resolve(),
                        Path(a.outdir).resolve(), a.stem, a.preset, a.size)
    print("wrote %s (%d semantic IDs)"
          % (Path(a.outdir) / (a.stem + "_edit_release.json"), len(data["element_ids"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
