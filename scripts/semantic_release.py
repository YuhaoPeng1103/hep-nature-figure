#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the three semantic vector artifacts from one raster trace.

The artifacts intentionally have different contracts:

  *_edit.svg        few semantic primitives; shape/colour edits are practical
  *_visual_mesh.svg gradient bands; optimised for visual fidelity
  *_visual_pick.svg invisible one-path-per-object hit targets

IR + bitmap + trace are the truth source.  SVG files are derived artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ELEMENT_RE = re.compile(r'\bdata-element="([^"]+)"')
AUX_ELEMENT_IDS = {"detail-layer"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def element_ids(svg_text: str) -> list[str]:
    seen = set()
    out = []
    for name in ELEMENT_RE.findall(svg_text):
        if name in AUX_ELEMENT_IDS:
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def artifact_record(path: Path, role: str, contract: str, **extra) -> dict[str, object]:
    """Describe one derived artifact by path, size, hash, and contract."""
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha256(path),
                role=role, contract=contract, **extra)


def tag_root(svg_text: str, role: str, contract: str) -> str:
    """Add stable artifact metadata without touching geometry."""
    start = svg_text.find("<svg")
    if start < 0:
        raise ValueError("missing <svg>")
    end = svg_text.find(">", start)
    if end < 0:
        raise ValueError("unterminated <svg>")
    tag = svg_text[start:end + 1]
    attrs = {
        "data-artifact": role,
        "data-contract": contract,
    }
    for key, value in attrs.items():
        pat = re.compile(r'\s%s="[^"]*"' % re.escape(key))
        tag = pat.sub("", tag)
        tag = tag[:-1] + ' %s="%s">' % (key, value)
    return svg_text[:start] + tag + svg_text[end + 1:]


def validate_element_sets(edit_svg: Path, visual_svg: Path) -> list[str]:
    edit = element_ids(edit_svg.read_text(encoding="utf-8", errors="replace"))
    visual = element_ids(visual_svg.read_text(encoding="utf-8", errors="replace"))
    if set(edit) != set(visual):
        raise ValueError(
            "semantic element IDs differ:\n"
            "  edit only: %s\n  visual only: %s"
            % (sorted(set(edit) - set(visual)), sorted(set(visual) - set(edit)))
        )
    return edit


def validate_manifest(path: Path) -> list[str]:
    """Validate release-v1 hashes and semantic element alignment."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "hep-nature-figure/release-v1":
        raise ValueError("unsupported manifest schema: %r" % data.get("schema"))
    sources = data.get("truth_source") or {}
    for key in ("bitmap", "trace", "ir"):
        item = sources.get(key)
        if not item:
            continue
        ref = Path(item["path"])
        if not ref.exists():
            raise ValueError("missing truth source %s: %s" % (key, ref))
        if sha256(ref) != item["sha256"]:
            raise ValueError("stale truth source hash: %s" % key)
    artifacts = data.get("artifacts") or {}
    paths = {}
    for key, item in artifacts.items():
        if not item:
            continue
        ref = Path(item["path"])
        if not ref.exists():
            raise ValueError("missing artifact %s: %s" % (key, ref))
        if sha256(ref) != item["sha256"]:
            raise ValueError("stale artifact hash: %s" % key)
        paths[key] = ref
    if "edit_master" in paths and "visual_master" in paths:
        return validate_element_sets(paths["edit_master"], paths["visual_master"])
    for ref in paths.values():
        return element_ids(ref.read_text(encoding="utf-8", errors="replace"))
    raise ValueError("manifest contains no artifacts")


def visible_sil(trace: Path, out_json: Path) -> dict[str, str]:
    """Create visible-only pick paths when no amodal completion JSON exists."""
    try:
        import shade_smooth as SS
    except Exception as exc:
        raise RuntimeError("cannot import shade_smooth: %s" % exc)
    text = trace.read_text(encoding="utf-8", errors="replace")
    width, height, elements, head = SS.parse_trace(text)
    sil = {}
    for elem in elements:
        mask = SS.rasterize(head, elem["body"], width, height)
        d = SS.smoothed_clip_svg(mask, iters=1, eps=0.8, dilate=0)
        if d:
            sil[elem["element"]] = d
    out_json.write_text(json.dumps(sil, ensure_ascii=False, indent=1), encoding="utf-8")
    return sil


def run(cmd: list[str], dry_run: bool) -> None:
    print("+", subprocess.list2cmdline(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="build semantic edit/visual/pick vector masters")
    ap.add_argument("--src", help="chosen raster")
    ap.add_argument("--trace", help="semantic trace SVG")
    ap.add_argument("--stem")
    ap.add_argument("--outdir")
    ap.add_argument("--validate-manifest", default="",
                    help="validate release-v1 hashes and semantic IDs, then exit")
    ap.add_argument("--ir", default="", help="IR file for provenance")
    ap.add_argument("--size", default="", help="WxH; default follows the trace")
    ap.add_argument("--elements", default="", help="volume IDs rebuilt in the edit master")
    ap.add_argument("--preset", choices=["draft", "balanced", "fidelity"], default="balanced")
    ap.add_argument("--pick-sil", default="",
                    help="optional amodal completion JSON; default uses visible-only pick paths")
    ap.add_argument("--pick-sub", default="", help="optional sub-object pick JSON")
    ap.add_argument("--edit-only", action="store_true")
    ap.add_argument("--visual-only", action="store_true")
    ap.add_argument("--no-pick", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.validate_manifest:
        ids = validate_manifest(Path(a.validate_manifest).resolve())
        print("manifest valid: %d semantic elements" % len(ids))
        return 0
    missing = [k for k in ("src", "trace", "stem", "outdir") if not getattr(a, k)]
    if missing:
        ap.error("missing required arguments: " + ", ".join("--" + k for k in missing))

    src = Path(a.src).resolve()
    trace = Path(a.trace).resolve()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    edit = outdir / (a.stem + "_edit.svg")
    visual = outdir / (a.stem + "_visual_mesh.svg")
    pick = outdir / (a.stem + "_visual_pick.svg")
    manifest = outdir / (a.stem + "_release.json")

    presets = {
        "draft": ("12", "8", "18", "8,plate=6,default=4"),
        "balanced": ("6", "16", "12", "background=8,plate=6,default=4"),
        "fidelity": ("3", "24", "10", "background=6,plate=4,default=2"),
    }
    band, nstop, dev_keep, cell = presets[a.preset]

    if not a.visual_only:
        cmd = [
            sys.executable, str(HERE / "trace_rebuild.py"),
            "--trace", str(trace), "--src", str(src),
            "--stem", a.stem + "_edit", "--outdir", str(outdir),
            "--band", band, "--nstop", nstop, "--dev-keep", dev_keep,
        ]
        if a.size:
            cmd += ["--size", a.size]
        if a.elements:
            cmd += ["--elements", a.elements]
        run(cmd, a.dry_run)

    if not a.edit_only:
        cmd = [
            sys.executable, str(HERE / "shade_smooth.py"),
            "--src", str(src), "--trace", str(trace),
            "--stem", a.stem + "_visual", "--outdir", str(outdir),
            "--cell", cell,
        ]
        if a.size:
            cmd += ["--size", a.size]
        run(cmd, a.dry_run)

    if a.dry_run:
        return 0
    for path, role, contract in (
        (edit, "edit-master", "semantic-edit"),
        (visual, "visual-master", "pixel-fidelity"),
    ):
        if path.exists():
            path.write_text(tag_root(path.read_text(encoding="utf-8"), role, contract),
                            encoding="utf-8")

    if not edit.exists() and not visual.exists():
        raise SystemExit("no artifact was built")
    ids = []
    if edit.exists() and visual.exists():
        ids = validate_element_sets(edit, visual)
    elif edit.exists():
        ids = element_ids(edit.read_text(encoding="utf-8"))
    elif visual.exists():
        ids = element_ids(visual.read_text(encoding="utf-8"))

    pick_source = "none"
    if not a.no_pick and visual.exists():
        if a.pick_sil:
            sil = Path(a.pick_sil).resolve()
            pick_source = "declared_amodal"
        else:
            sil = outdir / (a.stem + "_visible_sil.json")
            visible_sil(trace, sil)
            pick_source = "visible_only"
        cmd = [
            sys.executable, str(HERE / "pick_layer.py"), str(visual),
            "--sil", str(sil), "-o", str(pick),
            "--artifact-role", "visual-pick", "--contract", "object-pick",
        ]
        if a.pick_sub:
            cmd += ["--sub", str(Path(a.pick_sub).resolve())]
        run(cmd, False)

    data = {
        "schema": "hep-nature-figure/release-v1",
        "stem": a.stem,
        "preset": a.preset,
        "truth_source": {
            "bitmap": {"path": str(src), "sha256": sha256(src)},
            "trace": {"path": str(trace), "sha256": sha256(trace)},
            "ir": ({"path": str(Path(a.ir).resolve()),
                    "sha256": sha256(Path(a.ir).resolve())} if a.ir else None),
        },
        "element_ids": ids,
        "artifacts": {
            "edit_master": (artifact_record(edit, "edit-master", "semantic-edit")
                            if edit.exists() and not a.visual_only else None),
            "visual_master": (artifact_record(visual, "visual-master", "pixel-fidelity")
                              if visual.exists() and not a.edit_only else None),
            "visual_pick": (artifact_record(pick, "visual-pick", "object-pick",
                                            completion=pick_source)
                            if pick.exists() and not a.edit_only else None),
        },
        "rules": [
            "IR, bitmap, and semantic trace are the source of truth.",
            "Edit shape/colour in the edit master, then rebuild the visual master.",
            "Amodal completion may enter pick paths, never visible trace geometry.",
            "Use the visual master for submission PDFs; use the edit master for revisions.",
        ],
        "technical_limits": [
            "Single-view hidden geometry is not uniquely recoverable.",
            "Same-colour objects still require IR priors or human confirmation.",
            "Text/formula reconstruction remains dependent on OCR plus human review.",
        ],
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote %s" % manifest)
    print("contracts: semantic-edit | pixel-fidelity | object-pick")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
