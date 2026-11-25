#!/usr/bin/env python3
"""Block release of a bitmap-to-SVG redraw that exceeds its pixel-error budget."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageOps

from _console import init_console
from check_direct_svg import check
from svg_repro_check import _flatten_rgba


PROFILES = {
    "edit": {"canvas": (12, 12), "region": (20, 24), "tile": (30, 40)},
    "texture": {"canvas": (8, 8), "region": (14, 16), "tile": (22, 32)},
}
TILE_COUNT = 8
EDGE_MATCH_MIN = 0.75
EDGE_MIN_REFERENCE_PIXELS = 8


def regions_at_size(raw_regions, width, height):
    regions = {}
    for name, *coordinates in raw_regions:
        if not re.fullmatch(r"[\w.-]+", name) or name in regions:
            raise ValueError(f"invalid or duplicate region name: {name!r}")
        box = tuple(map(int, coordinates))
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError(f"region {name!r} is empty or outside {width}x{height}: {box}")
        regions[name] = box
    return regions


def measurement(delta, mae_limit, gt32_limit):
    mae = float(delta.mean(dtype=np.float64))
    gt32 = 100 * float((delta > 32).mean())
    return {"mae": mae, "gt32_pct": gt32, "pixels": int(delta.size),
            "mae_limit": mae_limit, "gt32_pct_limit": gt32_limit,
            "pass": mae <= mae_limit and gt32 <= gt32_limit}


def compare(source, rendered, profile, regions):
    if source.shape != rendered.shape:
        raise ValueError("reference and render require identical native pixel dimensions")
    height, width = source.shape[:2]
    delta = np.abs(source - rendered).mean(axis=2)
    canvas = measurement(delta, *profile["canvas"])
    mse = float(np.square(source - rendered).mean(dtype=np.float64))
    canvas["psnr_db"] = 10 * math.log10(255**2 / mse) if mse else None

    def local_metrics(box, limits):
        x0, y0, x1, y1 = box
        return {"box": box, **measurement(delta[y0:y1, x0:x1], *limits)}

    per_region = {name: local_metrics(box, profile["region"]) for name, box in regions.items()}
    xs = np.linspace(0, width, min(TILE_COUNT, width) + 1, dtype=int).tolist()
    ys = np.linspace(0, height, min(TILE_COUNT, height) + 1, dtype=int).tolist()
    tiles = [local_metrics((x0, y0, x1, y1), profile["tile"])
             for y0, y1 in zip(ys, ys[1:]) for x0, x1 in zip(xs, xs[1:])]
    tiles.sort(key=lambda row: (row["pass"], -max(row["mae"] / row["mae_limit"],
                                                  row["gt32_pct"] / row["gt32_pct_limit"])))
    passed = canvas["pass"] and all(row["pass"] for row in per_region.values()) and tiles[0]["pass"]
    return {"status": "pass" if passed else "fail", "canvas": canvas,
            "regions": per_region, "tiles": tiles}, delta


def compare_structure(source, rendered, regions):
    """Measure missing and spurious structural edges in named source-pixel crops."""
    import cv2

    if source.shape != rendered.shape:
        raise ValueError("edge comparison requires identical native pixel dimensions")
    scale = max(source.shape[:2]) / 1024
    tolerance = max(1, round(3 * scale))
    sigma = max(0.75, 0.9 * scale)

    def detect(rgb):
        smooth = cv2.GaussianBlur(rgb.astype(np.uint8), (0, 0), sigma)
        return np.logical_or.reduce([
            cv2.Canny(channel, 32, 75, L2gradient=True) != 0
            for channel in cv2.split(smooth)
        ])

    reference = detect(source)
    candidate = detect(rendered)
    to_reference = cv2.distanceTransform((~reference).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    to_candidate = cv2.distanceTransform((~candidate).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    missing = reference & (to_candidate > tolerance)
    extra = candidate & (to_reference > tolerance)

    def score(box):
        x0, y0, x1, y1 = box
        crop = np.s_[y0:y1, x0:x1]
        n_ref = int(reference[crop].sum())
        n_svg = int(candidate[crop].sum())
        recall = 1 - int(missing[crop].sum()) / n_ref if n_ref else None
        precision = 1 - int(extra[crop].sum()) / n_svg if n_svg else None
        enough = n_ref >= EDGE_MIN_REFERENCE_PIXELS
        passed = enough and precision is not None and min(recall, precision) >= EDGE_MATCH_MIN
        return {"box": box, "reference_edges": n_ref, "svg_edges": n_svg,
                "recall": recall, "precision": precision, "pass": passed,
                "reason": None if enough else "reference crop has too few detectable edges"}

    height, width = source.shape[:2]
    selected = {name: score(box) for name, box in regions.items()}
    canvas = score((0, 0, width, height))
    canvas.pop("pass")
    report = {"tolerance_px": tolerance, "minimum_each": EDGE_MATCH_MIN,
              "canvas_diagnostic": canvas, "regions": selected,
              "status": "pass" if all(row["pass"] for row in selected.values()) else "fail"}
    overlay = (0.72 * source + 0.28 * 255).astype(np.uint8)
    overlay[missing] = (214, 25, 71)
    overlay[extra] = (0, 140, 210)
    overlay[missing & extra] = (108, 55, 181)
    return report, overlay


def render(contents, width, height):
    import cairosvg

    root, _, _ = check(contents.decode("utf-8-sig"), (), (), 0)
    x, y, vw, vh = map(float, root.get("viewBox").replace(",", " ").split())
    if not all(map(math.isfinite, (x, y, vw, vh))) or min(vw, vh) <= 0:
        raise ValueError("invalid SVG viewBox")
    if abs(vw * height / vh - width) > 1 and abs(vh * width / vw - height) > 1:
        raise ValueError("SVG viewBox aspect ratio differs from the reference by more than one pixel")
    raw = cairosvg.svg2png(bytestring=contents, output_width=width, output_height=height)
    with Image.open(io.BytesIO(raw)) as image:
        return _flatten_rgba(image), f"CairoSVG {cairosvg.__version__}"


def save_images(outdir, name, source, rendered, delta):
    width = source.shape[1]
    before = Image.fromarray(source.astype(np.uint8))
    after = Image.fromarray(rendered.astype(np.uint8))
    after.save(outdir / f"{name}.render.png")
    side = Image.new("RGB", (2 * width + 8, source.shape[0]), "white")
    side.paste(before, (0, 0))
    side.paste(after, (width + 8, 0))
    side.save(outdir / f"{name}.compare.png")
    heat = Image.fromarray(np.clip(delta * 4, 0, 255).astype(np.uint8))
    ImageOps.colorize(heat, black="#080712", mid="#df2515", white="#fff3a2").save(
        outdir / f"{name}.diff.png")


def show(name, report):
    print(f"{name}: {report['status'].upper()}")
    if "error" in report:
        print(f"  {report['error']}")
        return
    failed_tiles = [tile for tile in report["tiles"] if not tile["pass"]]
    rows = [("canvas", report["canvas"]), *report["regions"].items(),
            *((f"tile {tuple(tile['box'])}", tile) for tile in failed_tiles[:3])]
    for key, row in rows:
        status = "PASS" if row["pass"] else "FAIL"
        print(f"  {status} {key}: MAE {row['mae']:.2f}/{row['mae_limit']}, "
              f">32 {row['gt32_pct']:.2f}%/{row['gt32_pct_limit']}%")
    if failed_tiles:
        print(f"  {len(failed_tiles)} of {len(report['tiles'])} tiles over budget")
    if "structure" in report:
        shape = report["structure"]
        for key, row in shape["regions"].items():
            recall = "--" if row["recall"] is None else f"{row['recall']:.1%}"
            precision = "--" if row["precision"] is None else f"{row['precision']:.1%}"
            status = "PASS" if row["pass"] else "FAIL"
            reason = f" ({row['reason']})" if row["reason"] else ""
            print(f"  {status} structure {key}: recall {recall}, precision {precision}{reason}")


def main():
    init_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="original or author-approved bitmap")
    parser.add_argument("--edit", type=Path, help="final native geometry SVG")
    parser.add_argument("--texture", type=Path, help="final editable transparent-texture SVG")
    parser.add_argument("--region", action="append", nargs=5, required=True,
                        metavar=("ID", "X0", "Y0", "X1", "Y1"), help="repeat for each key object or panel")
    parser.add_argument("--structure", action="append", default=[], metavar="ID",
                        help="also check edge recall/precision in this --region (repeatable)")
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    variants = {name: path for name, path in (("edit", args.edit), ("texture", args.texture)) if path}
    if not variants:
        parser.error("provide --edit and/or --texture")
    if len(variants) == 2 and args.edit.resolve() == args.texture.resolve():
        parser.error("edit and texture must be distinct SVG files")
    products = {"fidelity.json"} | {f"{name}.{kind}.png" for name in variants
                                   for kind in ("render", "compare", "diff")}
    if args.structure:
        products.update(f"{name}.edges.png" for name in variants)
        region_ids = {name for name, *_ in args.region}
        if not set(args.structure) <= region_ids:
            parser.error("--structure must name a declared --region")
    inputs = {path.resolve() for path in [args.reference, *variants.values()]}
    if inputs & {(args.outdir / product).resolve() for product in products}:
        parser.error("an output path overlaps an input file")

    report = {"schema": "hepnf-svg-fidelity-v1", "status": "error",
              "reference": {"path": str(args.reference.resolve())}, "variants": {}}
    try:
        args.outdir.mkdir(parents=True, exist_ok=True)
        ref_bytes = args.reference.read_bytes()
        report["reference"]["sha256"] = hashlib.sha256(ref_bytes).hexdigest()
        with Image.open(io.BytesIO(ref_bytes)) as image:
            source = _flatten_rgba(image)
        height, width = source.shape[:2]
        report["size"] = [width, height]
        regions = regions_at_size(args.region, width, height)
    except (OSError, ValueError) as exc:
        report["error"] = str(exc)
    else:
        for name, path in variants.items():
            detail = {"status": "error", "path": str(path.resolve())}
            try:
                contents = path.read_bytes()
                detail["sha256"] = hashlib.sha256(contents).hexdigest()
                rendered, detail["renderer"] = render(contents, width, height)
                result, delta = compare(source, rendered, PROFILES[name], regions)
                save_images(args.outdir, name, source, rendered, delta)
                if args.structure:
                    structure_regions = {name: regions[name] for name in args.structure}
                    structure, overlay = compare_structure(source, rendered, structure_regions)
                    Image.fromarray(overlay).save(args.outdir / f"{name}.edges.png")
                    result["structure"] = structure
                    if structure["status"] == "fail":
                        result["status"] = "fail"
                detail.update(result)
            except (OSError, ValueError, TypeError, ImportError, ET.ParseError) as exc:
                detail["error"] = str(exc)
            report["variants"][name] = detail
            show(name, detail)
        states = {detail["status"] for detail in report["variants"].values()}
        report["status"] = "error" if "error" in states else "fail" if "fail" in states else "pass"

    try:
        (args.outdir / "fidelity.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot write the fidelity report: {exc}")
        return 2
    if "error" in report:
        print(f"ERROR: {report['error']}")
    print(f"{report['status'].upper()}: {args.outdir / 'fidelity.json'}")
    return {"pass": 0, "fail": 1, "error": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
