#!/usr/bin/env python3
"""Render selected SVG regions at native vector scale for visual review."""

from __future__ import annotations

import argparse
from copy import copy
import hashlib
import io
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import cairosvg
from PIL import Image, ImageDraw

from _console import init_console
from check_direct_svg import SVG, check
from fidelity_gate import regions_at_size


def review_viewport(root, size, box):
    """Keep the original viewBox and crop it through a separate viewport."""
    width, height = size
    svg_x, svg_y, svg_width, svg_height = map(float, root.attrib["viewBox"].replace(",", " ").split())
    if not all(map(math.isfinite, (svg_x, svg_y, svg_width, svg_height))) or min(svg_width, svg_height) <= 0:
        raise ValueError("invalid SVG viewBox")
    if abs(svg_width * height / svg_height - width) > 1 and abs(svg_height * width / svg_width - height) > 1:
        raise ValueError("SVG viewBox aspect ratio differs from the reference by more than one pixel")

    x0, y0, x1, y1 = box
    crop_width, crop_height = x1 - x0, y1 - y0
    cropped = ET.Element(f"{{{SVG}}}svg", {
        "width": str(crop_width), "height": str(crop_height),
        "viewBox": f"{x0} {y0} {crop_width} {crop_height}",
    })
    # Using an outer crop leaves percentages and user-space paints inside the
    # original SVG viewport. Only the root viewport dimensions are resolved
    # to the same reference-pixel size used by the full-size fidelity render.
    scene = copy(root)
    scene.attrib = {**root.attrib, "x": "0", "y": "0", "width": str(width), "height": str(height)}
    cropped.append(scene)
    return ET.tostring(cropped, encoding="utf-8")


def render_crop(root, size, box, scale):
    width, height = box[2] - box[0], box[3] - box[1]
    data = cairosvg.svg2png(
        bytestring=review_viewport(root, size, box),
        output_width=width * scale,
        output_height=height * scale,
        background_color="white",
    )
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGB")


def comparison(panels):
    width, height = panels[0][1].size
    gutter, heading = 8, 24
    result = Image.new("RGB", (len(panels) * width + (len(panels) - 1) * gutter, height + heading), "white")
    painter = ImageDraw.Draw(result)
    for index, (title, panel) in enumerate(panels):
        x = index * (width + gutter)
        result.paste(panel, (x, heading))
        painter.text((x + 6, 6), title, fill="#394556")
    return result


def main():
    init_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--edit", type=Path)
    parser.add_argument("--texture", type=Path)
    parser.add_argument("--region", action="append", nargs=5, required=True,
                        metavar=("ID", "X0", "Y0", "X1", "Y1"))
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    variants = {name: path for name, path in (("edit", args.edit), ("texture", args.texture)) if path}
    if not variants or args.scale < 1:
        parser.error("provide --edit and/or --texture and a positive --scale")

    try:
        reference = args.reference.read_bytes()
        with Image.open(io.BytesIO(reference)) as raw:
            source = Image.new("RGBA", raw.size, "white")
            source.alpha_composite(raw.convert("RGBA"))
            source = source.convert("RGB")
        regions = regions_at_size(args.region, *source.size)
        report = {
            "schema": "hepnf-svg-zoom-review-v1", "reference_sha256": hashlib.sha256(reference).hexdigest(),
            "size": list(source.size), "scale": args.scale, "renderer": f"CairoSVG {cairosvg.__version__}",
            "svg_sha256": {}, "regions": {},
        }
        documents = {}
        for name, svg in variants.items():
            content = svg.read_bytes()
            root, _, _ = check(content.decode("utf-8-sig"), (), (), 0)
            documents[name] = root
            report["svg_sha256"][name] = hashlib.sha256(content).hexdigest()

        products = {f"{name}.zoom.png" for name in regions} | {"zoom.json"}
        inputs = {path.resolve() for path in (args.reference, *variants.values())}
        if inputs & {(args.outdir / filename).resolve() for filename in products}:
            raise ValueError("output path overlaps an input")
        args.outdir.mkdir(parents=True, exist_ok=True)
        for name, box in regions.items():
            width, height = (box[2] - box[0]) * args.scale, (box[3] - box[1]) * args.scale
            before = source.crop(box).resize((width, height), Image.Resampling.LANCZOS)
            panels = [(f"Reference enlarged {args.scale}x", before)]
            for kind, root in documents.items():
                pixels = render_crop(root, source.size, box, args.scale)
                panels.append((f"{kind} SVG rendered {args.scale}x", pixels))
            filename = f"{name}.zoom.png"
            comparison(panels).save(args.outdir / filename)
            report["regions"][name] = {"box": box, "panel_size": [width, height], "file": filename}
        (args.outdir / "zoom.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(2, f"ERROR: {error}\n")
    print(f"Rendered {len(regions)} region(s) at {args.scale}x for visual review: {args.outdir}")


if __name__ == "__main__":
    main()
