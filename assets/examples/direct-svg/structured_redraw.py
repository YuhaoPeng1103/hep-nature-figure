"""Procedural demonstration of a structured redraw. No reference assets are bundled."""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import sys

import cairosvg
import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from svg_glazes import Glaze, Scale, fit_glazes


WIDTH, HEIGHT = 420, 260
CENTER = (214, 123)
RADII = (154, 104)
MEDIUM = '<ellipse cx="214" cy="123" rx="154" ry="104" fill="url(#thermal)"/>'
ARROW = '<path d="M17 193 C117 128 231 96 369 69 L366 61 L405 66 L378 89 L375 80 C218 103 113 151 22 211Z" fill="url(#jet-fill)"/>'
PARTONS = (
    ("rear-parton", 192, 156, 22, "amber"),
    ("front-parton", 210, 146, 23, "purple"),
    ("cyan-parton", 250, 75, 15, "teal"),
)
DEFS = """
<radialGradient id="thermal" cx=".53" cy=".44" r=".59">
  <stop stop-color="#ffeb99"/><stop offset=".53" stop-color="#ff9d58"/><stop offset="1" stop-color="#e95e47"/>
</radialGradient>
<radialGradient id="amber" cx=".37" cy=".32" r=".65">
  <stop stop-color="#fffad5"/><stop offset=".30" stop-color="#e9b145"/><stop offset="1" stop-color="#875523"/>
</radialGradient>
<radialGradient id="purple" cx=".35" cy=".31" r=".66">
  <stop stop-color="#f7c7ff"/><stop offset=".32" stop-color="#ae56be"/><stop offset="1" stop-color="#59246d"/>
</radialGradient>
<radialGradient id="teal" cx=".37" cy=".33" r=".66">
  <stop stop-color="#d7ffff"/><stop offset=".32" stop-color="#52bacb"/><stop offset="1" stop-color="#186379"/>
</radialGradient>
<linearGradient id="jet-fill">
  <stop stop-color="#65809c"/><stop offset=".55" stop-color="#334d65"/><stop offset="1" stop-color="#2583c3"/>
</linearGradient>
"""


def group(key, content, attributes=""):
    return f'<g id="{key}" data-element="{key}" {attributes}>{content}</g>'


def svg(content, definitions=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}"><defs>{DEFS}{definitions}</defs>{content}</svg>'
    )


def raster(content, definitions=""):
    raw = cairosvg.svg2png(bytestring=svg(content, definitions).encode())
    with Image.open(BytesIO(raw)) as image:
        return image.convert("RGBA")


def scene(medium, shapes, *, texture=False, move=False):
    role = 'data-role="intrinsic-RGBA-vector-texture"' if texture else ""
    spheres = []
    for name, x, y, r, color in PARTONS:
        at = 'transform="translate(42 29)"' if move and name == "front-parton" else ""
        spheres.append(group(name, f'<circle cx="{x}" cy="{y}" r="{r}" fill="url(#{color})"/>', at))
    return "".join((
        group("medium", medium + f'<g {role}>{shapes}</g>'),
        group("jet", ARROW),
        group("particles", "".join(spheres)),
        group("label", '<text x="199" y="41" font-family="sans-serif" font-size="14" fill="#604331">QGP</text>'),
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    phase = np.linspace(0, np.pi * 2, 360, endpoint=False)
    outline = np.column_stack((CENTER[0] + RADII[0] * np.cos(phase), CENTER[1] + RADII[1] * np.sin(phase)))

    def markup(glazes):
        records = [g.svg(f"medium-glaze-{i:03d}", convex_outline=outline) for i, g in enumerate(glazes)]
        return "".join(r[0] for r in records), "".join(r[1] for r in records)

    # Seed an inspectable reference from authored geometry, separate material
    # and foreground so fit samples cannot include the overlying objects.
    target_defs, target_glazes = markup([
        Glaze(141, 104, 105, (255, 189, 88)),
        Glaze(252, 164, 95, (240, 117, 61)),
        Glaze(280, 116, 72, (255, 190, 91)),
        Glaze(108, 176, 74, (235, 103, 66)),
    ])
    reference = raster(scene(MEDIUM, target_glazes), target_defs)
    reference.save(args.outdir / "reference.png")
    target = np.asarray(raster(MEDIUM + target_glazes, target_defs))
    base = np.asarray(raster(MEDIUM))
    foreground = np.asarray(raster(scene("", "")))[..., 3]
    guarded = cv2.dilate((foreground > 12).astype(np.uint8), np.ones((9, 9), np.uint8))
    confidence = (base[..., 3] > 250) & (guarded == 0)
    scales = [Scale(24, 34, 2, .9), Scale(12, 19, 2, .9), Scale(6, 11, 1, 1.3)]
    for kind in ("edit", "texture"):
        fine = kind == "texture"
        schedule = scales + [Scale(3.7, 7, 1, .8)] if fine else scales
        definitions, shapes = markup(fit_glazes(target[..., :3], base[..., :3], confidence, schedule))
        document = svg(scene(MEDIUM, shapes, texture=fine), definitions)
        (args.outdir / f"qgp_{kind}.svg").write_text(document, encoding="utf-8")
        if fine:
            moved = svg(scene(MEDIUM, shapes, texture=True, move=True), definitions)
            (args.outdir / "qgp_moved.svg").write_text(moved, encoding="utf-8")


if __name__ == "__main__":
    main()
