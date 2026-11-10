#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild visual and pick artifacts from an edited semantic SVG."""
from __future__ import annotations

import argparse
import copy
import io
import json
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
                       height: int | None = None) -> tuple[Path, Path, list[str]]:
    root = ET.parse(edit_svg).getroot()
    if root.attrib.get("data-contract") != "semantic-edit":
        raise ValueError("edit master must use data-contract=\"semantic-edit\"")
    groups = _direct_groups(root)
    ids = [g.attrib["data-element"] for g in groups]
    if not groups:
        raise ValueError("edit master contains no data-element groups")
    W, H, vx, vy = _root_size(root, width, height)
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


def main() -> int:
    ap = argparse.ArgumentParser(description="rebuild visual/pick from an edit master")
    ap.add_argument("--edit", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--stem", required=True)
    ap.add_argument("--size", default="", help="optional WxH")
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
    render, trace, ids = render_edit_master(
        Path(a.edit).resolve(), Path(a.outdir).resolve(), a.stem, width, height)
    print("edit render=%s trace=%s ids=%d" % (render, trace, len(ids)))
    if a.trace_only:
        return 0
    raise SystemExit("visual rebuild not implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
