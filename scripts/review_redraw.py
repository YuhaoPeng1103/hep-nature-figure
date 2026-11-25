#!/usr/bin/env python3
"""Build verification evidence for both editions of a reference-to-SVG redraw."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

from _console import init_console
from check_svg_pair import named_objects, validate_edit, validate_pair
from fidelity_gate import regions_at_size, render
from svg_zoom_review import comparison


SCRIPTS = Path(__file__).resolve().parent
KINDS = ("edit", "texture")


def run(script, arguments):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, arguments)]).returncode


def identify(path):
    payload = path.read_bytes()
    if not payload:
        raise ValueError(f"empty input: {path}")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(payload).hexdigest()}


def probe(root, object_id, dx, dy, size, original):
    nodes = named_objects(root)
    if object_id not in nodes or nodes[object_id].tag.rsplit("}", 1)[-1] != "g":
        raise ValueError(f"{object_id}: choose an editable named object group")
    frames = [("Original", original)]
    for label, attrib in (("Moved", "transform"), ("Hidden", "display")):
        changed = deepcopy(root)
        obj = named_objects(changed)[object_id]
        if attrib == "transform":
            previous = obj.get(attrib, "")
            obj.set(attrib, f"translate({dx:g} {dy:g}) {previous}".rstrip())
        else:
            obj.set(attrib, "none")
        validate_edit(root, changed, [object_id], attrib)
        pixels, _ = render(ET.tostring(changed, encoding="utf-8"), *size)
        frame = Image.fromarray(pixels.astype(np.uint8))
        if np.array_equal(np.asarray(original), np.asarray(frame)):
            raise ValueError(f"{object_id}: {label.lower()} object made no visible change")
        frames.append((f"{label}: {object_id}", frame))
    return comparison(frames)


def main(argv=None):
    init_console()
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "edit", "texture", "outdir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", required=True,
                        help="drawing source file; repeat to include separate geometry/material sources")
    parser.add_argument("--region", nargs=5, action="append", required=True,
                        metavar=("ID", "X0", "Y0", "X1", "Y1"))
    parser.add_argument("--structure", action="append", required=True, metavar="ID",
                        help="declared region focused on a visible contour or thin structure")
    parser.add_argument("--zoom", action="append", metavar="ID",
                        help="declared region to render at 4x; defaults to the structure regions")
    parser.add_argument("--move", nargs=3, required=True, metavar=("OBJECT_ID", "DX", "DY"),
                        help="translate a key occluding group in SVG user units, then test its visibility")
    args = parser.parse_args(argv)
    object_id, x, y = args.move

    try:
        dx, dy = float(x), float(y)
        if not all(map(math.isfinite, (dx, dy))) or (dx, dy) == (0, 0):
            raise ValueError("choose a finite, nonzero object displacement")
        if args.edit.resolve() == args.texture.resolve():
            raise ValueError("edit and texture must be distinct SVG files")
        with Image.open(args.reference) as image:
            size = image.size
        regions = regions_at_size(args.region, *size)
        structure = list(dict.fromkeys(args.structure))
        zoom = list(dict.fromkeys(args.zoom or structure))
        if not (set(structure) | set(zoom)) <= regions.keys():
            raise ValueError("--zoom and --structure must name declared regions")
        input_paths = [args.reference, args.edit, args.texture, *args.source]
        destinations = {"review.json", "fidelity/fidelity.json", "zoom/zoom.json"}
        destinations.update(f"fidelity/{kind}.{report}.png" for kind in KINDS
                            for report in ("render", "compare", "diff", "edges"))
        destinations.update(f"zoom/{name}.zoom.png" for name in zoom)
        destinations.update(f"{kind}.probe.png" for kind in KINDS)
        if {path.resolve() for path in input_paths} & {(args.outdir / name).resolve() for name in destinations}:
            raise ValueError("an output path overlaps an input file")
        report = {
            "schema": "hepnf-redraw-review-v1",
            "inputs": {name: identify(path) for name, path in
                       (("reference", args.reference), ("edit", args.edit), ("texture", args.texture))},
            "source": [identify(path) for path in args.source],
            "move": {"object": object_id, "delta": [dx, dy]},
            "checks": {},
            "visual_observations": ["compare native-size canvases", "inspect the 4x crops",
                                    "inspect newly revealed geometry and original-position ghosts"],
        }
        args.outdir.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as error:
        parser.exit(2, f"ERROR: {error}\n")

    checks = report["checks"]
    common = ["--reference", args.reference, "--edit", args.edit, "--texture", args.texture]
    fidelity_args = common + ["--outdir", args.outdir / "fidelity"]
    for region in args.region:
        fidelity_args.extend(["--region", *region])
    for name in structure:
        fidelity_args.extend(["--structure", name])
    result = run("fidelity_gate.py", fidelity_args)
    checks["fidelity"] = {"status": "pass" if result == 0 else "fail", "exit_code": result,
                          "report": "fidelity/fidelity.json"}

    zoom_args = common + ["--outdir", args.outdir / "zoom"]
    for name in zoom:
        zoom_args.extend(["--region", name, *regions[name]])
    result = run("svg_zoom_review.py", zoom_args)
    checks["zoom"] = {"status": "pass" if result == 0 else "fail", "exit_code": result,
                      "report": "zoom/zoom.json"}

    try:
        edit_root, texture_root, _, _ = validate_pair(args.edit, args.texture)
        checks["pair"] = {"status": "pass"}
    except (OSError, ValueError, ET.ParseError) as error:
        checks["pair"] = {"status": "fail", "reason": str(error)}
    else:
        for kind, root in zip(KINDS, (edit_root, texture_root)):
            try:
                with Image.open(args.outdir / "fidelity" / f"{kind}.render.png") as image:
                    original = image.convert("RGB")
                # If a rerun failed to render, do not treat a prior result as current evidence.
                original_pixels, _ = render(ET.tostring(root, encoding="utf-8"), *size)
                if not np.array_equal(np.asarray(original), original_pixels.astype(np.uint8)):
                    raise ValueError("fidelity render does not match the current SVG")
                evidence = probe(root, object_id, dx, dy, size, original)
                filename = f"{kind}.probe.png"
                evidence.save(args.outdir / filename)
                checks[f"{kind}_probe"] = {"status": "pass", "image": filename}
            except (OSError, ValueError, ImportError, ET.ParseError) as error:
                checks[f"{kind}_probe"] = {"status": "fail", "reason": str(error)}

    passed = all(check["status"] == "pass" for check in checks.values())
    report["status"] = "pass" if passed else "fail"
    destination = args.outdir / "review.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, check in checks.items():
        print(f"{name}: {check['status'].upper()}", check.get("reason", ""))
    print(f"{report['status'].upper()} machine verification: {destination}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
