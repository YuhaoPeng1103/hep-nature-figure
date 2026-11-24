"""Journal-quality vector reconstruction of the supplied jet-quenching sketch."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from html import escape
from pathlib import Path

import cairosvg

OUT = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from element_library import load_index  # noqa: E402
from spec_compile import evaluate_layout, evaluate_physics, load_asset_svg  # noqa: E402
from spec_confirm import canonical_hash, load_spec  # noqa: E402
W, H = 840, 459
OUTPUT = (4323, 2362)
SOURCE_SKETCH = ROOT / "assets" / "examples" / "direct-svg" / "references" / "jet-quenching-sketch.png"


def tag(name, inside=None, **kw):
    attrs = "".join(
        f' {key.replace("_", "-")}="{escape(str(value), quote=True)}"'
        for key, value in kw.items()
        if value is not None
    )
    return f"<{name}{attrs}/>" if inside is None else f"<{name}{attrs}>{inside}</{name}>"


def path(d, fill="none", **kw):
    if "stroke_width" in kw:
        kw.setdefault(
            "data_stroke_pt",
            f"{float(kw['stroke_width']) * 183.0 / W * 72.0 / 25.4:.2f}",
        )
    return tag("path", d=d, fill=fill, **kw)


def ellipse(x, y, rx, ry, fill, **kw):
    return tag("ellipse", cx=x, cy=y, rx=rx, ry=ry, fill=fill, **kw)


def text(x, y, value, size=12, **kw):
    kw.setdefault("fill", "#222830")
    kw.setdefault(
        "data_font_size_pt",
        f"{size * 183.0 / W * 72.0 / 25.4:.2f}",
    )
    return tag("text", value, x=x, y=y, font_family="DejaVu Sans",
               font_size=size, **kw)


def gradient(kind, ident, stops, **kw):
    return tag(
        kind + "Gradient",
        "".join(
            tag("stop", offset=offset, stop_color=color, stop_opacity=alpha)
            for offset, color, alpha in stops
        ),
        id=ident,
        **kw,
    )


def marker(ident, color):
    return tag(
        "marker",
        tag("path", "M0 0 L10 5 L0 10 Z", fill=color),
        id=ident, viewBox="0 0 10 10", refX="9", refY="5",
        markerWidth="5", markerHeight="5", orient="auto-start-reverse",
    )


def asset_render(asset_id, x, y, width, height, rotation=0, prefix="asset"):
    asset = next(
        item for item in load_index()["assets"] if item["id"] == asset_id
    )
    source = ROOT / "assets" / "element-library" / asset["file"]
    vb, definitions, body = load_asset_svg(source, prefix + "_")
    scale = min(width / (vb[2] - vb[0]), height / (vb[3] - vb[1]))
    ox = (width - (vb[2] - vb[0]) * scale) / 2
    oy = (height - (vb[3] - vb[1]) * scale) / 2
    transform = (
        f"translate({x:.3f} {y:.3f}) rotate({rotation:.3f}) "
        f"translate({-width/2:.3f} {-height/2:.3f}) "
        f"translate({ox:.3f} {oy:.3f}) scale({scale:.6f}) "
        f"translate({-vb[0]:.3f} {-vb[1]:.3f})"
    )
    return definitions, (
        f'<g data-element="{asset_id}" transform="{transform}">{body}</g>'
    )


def label(ident, value, x, y, color="#252a31", size=12.5,
          anchor="middle", sub=None):
    width = max(len(value), len(sub or "")) * size * 0.57 + 12
    pieces = [
        tag("rect", x=x-width/2, y=y-13, width=width, height=21 if sub else 17,
            rx=4, fill="#ffffff", opacity=.88),
        text(x, y, value, size, id=ident, text_anchor=anchor, fill=color,
             font_weight="bold"),
    ]
    if sub:
        pieces.append(text(x, y+13, sub, 9, id=ident+"-sub",
                           text_anchor=anchor, fill="#66717b"))
    return "".join(pieces)


def wave(cx, cy, height=42, width=12, tilt=-8, color="#d8a13f", opacity=.75):
    # Three smooth, finite wave packets as in the supplied sketch.
    result = []
    for index, xoff in enumerate((-width, 0, width)):
        d = (
            f"M {cx+xoff} {cy-height/2} "
            f"C {cx+xoff+8} {cy-height/3} {cx+xoff-8} {cy-height/6} {cx+xoff} {cy} "
            f"C {cx+xoff+8} {cy+height/6} {cx+xoff-8} {cy+height/3} "
            f"{cx+xoff} {cy+height/2}"
        )
        result.append(
            path(d, stroke=color, stroke_width=1.2,
                 opacity=opacity * (1 - index * .17), transform=f"rotate({tilt} {cx} {cy})")
        )
    return "".join(result)


def build() -> str:
    definitions = [
        gradient("radial", "qgp-body", [
            (0, "#fffaf0", 1), (.20, "#fff1d9", 1), (.48, "#fbe0c0", .98),
            (.72, "#f5bd87", .95), (.88, "#ed9a62", .86), (1, "#de7446", 0),
        ], cx=".50", cy=".47", r=".64", fx=".53", fy=".40"),
        gradient("radial", "qgp-core", [
            (0, "#fffef0", .92), (.35, "#ffeeb7", .55),
            (.72, "#ffbc68", .18), (1, "#ee8c49", 0),
        ], cx=".50", cy=".54", r=".58"),
        gradient("linear", "escape-jet", [
            (0, "#0d4f95", .94), (.28, "#217fca", .92),
            (.65, "#65d5ee", .72), (1, "#e6fbf4", 0),
        ], x1="0%", y1="0%", x2="100%" , y2="0%"),
        gradient("linear", "quench-jet", [
            (0, "#38526a", .95), (.33, "#667f96", .88),
            (.70, "#9bb3c2", .60), (1, "#dce8ec", .18),
        ], x1="100%", y1="0%", x2="0%", y2="0%"),
        gradient("radial", "hard-core", [
            (0, "#ffffff", 1), (.18, "#fff7be", 1),
            (.50, "#ffd45e", .75), (1, "#ffb536", 0),
        ], cx=".5", cy=".5", r=".5"),
        marker("axis-arrow", "#28333e"),
    ]
    layers = [tag("rect", x=0, y=0, width=W, height=H, fill="#ffffff")]

    # Perspective reaction-plane support, deliberately without a grid.
    layers.append(
        '<g id="reaction-plane" data-element="reaction-plane">'
        + tag("ellipse", cx=421, cy=257, rx=310, ry=185,
              fill="#f7e7d5", opacity=.2, transform="rotate(-4 421 257)")
        + tag("ellipse", cx=431, cy=276, rx=280, ry=162,
              fill="#90785f", opacity=.045, transform="rotate(-4 431 276)")
        + "</g>"
    )

    # QGP volume with a warm coloured edge, as in the source sketch.
    qgp_defs, qgp_body = asset_render(
        "article_t330_qgp_fireball", 421, 235, 476, 390,
        rotation=-4, prefix="qgp",
    )
    definitions.append(qgp_defs)
    layers.append(
        '<g id="qgp-medium" data-element="qgp-medium">'
        + ellipse(421, 242, 311, 185, "url(#qgp-body)",
                  opacity=.30, transform="rotate(-4 421 242)")
        + qgp_body + "</g>"
    )

    vertex = (607, 176)
    # The common parton track and its two opposite branches.
    layers.append(
        '<g id="parton-track" data-element="parton-track">'
        + path(f"M78 366 L{vertex[0]} {vertex[1]} L789 112",
               stroke="#456b86", stroke_width=1.1, opacity=.68)
        + "</g>"
    )

    # Article-derived jet notation: a strong central parton trajectory plus a
    # small set of unresolved secondary tracks, following PRL 125, 122301.
    escape_lines = []
    for index, t in enumerate((0, 1, 2, 3, 4, 5, 6)):
        dy = (t - 3) * 3.6
        end = (782 + (t % 3) * 5, 106 + dy)
        escape_lines.append(
            path(
                f"M {vertex[0]+4} {vertex[1]-3} Q "
                f"{(vertex[0]+end[0])/2:.1f} {vertex[1]-42+(t-3)*3.2:.1f} "
                f"{end[0]} {end[1]}",
                stroke="#176db2" if t == 3 else "#52b6df",
                stroke_width=7.2 if t == 3 else .70,
                opacity=.94 if t == 3 else .45,
            )
        )
    escape_lines.append(
        tag(
            "polygon",
            points="774,84 809,101 772,124",
            fill="#2f87ca",
        )
    )
    escape_lines.append(
        path("M611 173 C673 151 735 127 781 108",
             stroke="#dffbff", stroke_width=1.05, opacity=.78)
    )
    quench_lines = []
    for index, t in enumerate(range(10)):
        dy = (t - 4.5) * 3.2
        end = (91 + (t % 4) * 7, 374 + dy)
        quench_lines.append(
            path(
                f"M {vertex[0]-3} {vertex[1]+3} Q "
                f"{(vertex[0]+end[0])/2:.1f} {vertex[1]+38+(t-4.5)*2.8:.1f} "
                f"{end[0]} {end[1]}",
                stroke="#38586f" if t in (4, 5) else "#8da1af",
                stroke_width=6.2 if t in (4, 5) else .58,
                opacity=.86 if t in (4, 5) else .35,
            )
        )
    quench_lines.append(
        tag(
            "polygon",
            points="86,354 66,381 111,383",
            fill="#8aa0ae",
            opacity=.78,
        )
    )
    layers.append(
        '<g id="quenched_jet" data-element="quenched_jet" '
        'data-source="PRL125.122301-fig01 + PRC86.064904-fig01">'
        + "".join(quench_lines)
        + "</g>"
    )
    layers.append(
        '<g id="escaped_jet" data-element="escaped_jet" '
        'data-source="PRL125.122301-fig01">'
        + "".join(escape_lines)
        + "</g>"
    )

    fragments = []
    for index in range(44):
        t = index / 43
        x = vertex[0] + (105 - vertex[0]) * t
        y = vertex[1] + (374 - vertex[1]) * t + 7 * math.sin(9 * t)
        fragments.append(ellipse(x, y, 1.1 + 1.6*(1-t), .85 + .8*(1-t),
                                "#b8cbd5", opacity=.45 + .35*(1-t)))
    layers.append(
        '<g id="quenched-fragments" data-element="quenched-fragments">'
        + "".join(fragments) + "</g>"
    )

    # Six radiation packets along the long in-medium path.
    radiation = []
    for cx, cy, height, tilt in (
        (180, 326, 38, -14), (235, 290, 38, -13),
        (292, 252, 35, -11), (350, 218, 34, -10),
        (470, 198, 31, -8), (524, 171, 29, -7),
    ):
        radiation.append(wave(cx, cy, height=height, tilt=tilt))
    layers.append(
        '<g id="medium-induced-radiation" data-element="medium-induced-radiation">'
        + "".join(radiation) + "</g>"
    )

    layers.append(
        '<g id="hard-scattering" data-element="hard-scattering">'
        + ellipse(vertex[0], vertex[1], 13, 13, "url(#hard-core)")
        + ellipse(vertex[0], vertex[1], 3.7, 3.7, "#ffffff")
        + "</g>"
    )

    ox, oy = 63, 415
    layers.append(
        '<g id="coordinate-axes" data-element="coordinate-axes">'
        + path(f"M{ox} {oy} L{ox} {oy-56}", stroke="#2e526f",
               stroke_width=2.0, marker_end="url(#axis-arrow)")
        + path(f"M{ox} {oy} L{ox+55} {oy+28}", stroke="#2c6ca8",
               stroke_width=2.0, marker_end="url(#axis-arrow)")
        + path(f"M{ox} {oy} L{ox+58} {oy-8}", stroke="#2a866c",
               stroke_width=2.0, marker_end="url(#axis-arrow)")
        + text(ox-11, oy-66, "y", 11, font_weight="bold", fill="#2e526f")
        + text(ox+62, oy+35, "x", 11, font_weight="bold", fill="#2c6ca8")
        + text(ox+65, oy-13, "z", 11, font_weight="bold", fill="#2a866c")
        + "</g>"
    )

    layers.append(
        '<g id="labels" data-element="labels">'
        + label("label-qgp", "QGP", 420, 105, color="#5d4e41")
        + label("label-hard", "Hard scattering", 664, 104, color="#36424b")
        + path("M651 116 L607 169", stroke="#66717b", stroke_width=.75)
        + label("label-escape", "Escaping jet", 735, 83, color="#246b91",
                sub="short path")
        + path("M734 99 L662 147", stroke="#66717b", stroke_width=.75)
        + label("label-quench", "Quenched jet", 165, 360, color="#38536a",
                sub="long path")
        + path("M205 349 L266 285", stroke="#66717b", stroke_width=.75)
        + label("label-radiation", "Medium-induced radiation", 398, 427,
                color="#6e4c2e")
        + "</g>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'width="183mm" height="100mm" viewBox="0 0 840 459" '
        'data-spec="qgp-jet-sketch">\n'
        + "<defs>" + "".join(definitions) + "</defs>\n"
        + "\n".join(layers) + "\n</svg>\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=OUT)
    parser.add_argument("--stem", default="qgp_jet_sketch")
    parser.add_argument(
        "--spec",
        type=Path,
        default=ROOT / "assets" / "spec-examples" / "qgp-jet-sketch.spec.yaml",
    )
    args = parser.parse_args()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    svg = build()
    svg_path = outdir / f"{args.stem}.svg"
    png_path = outdir / f"{args.stem}.png"
    pdf_path = outdir / f"{args.stem}.pdf"
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(png_path),
        output_width=OUTPUT[0],
        output_height=OUTPUT[1],
        background_color="#fff",
    )
    cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(pdf_path))
    manifest = {
        "schema": "hep-nature-figure/direct-svg-v1",
        "spec": str(args.spec.resolve()),
        "spec_sha256": canonical_hash(load_spec(args.spec)),
        "confirmation": "experimental",
        "source_sketch": str(SOURCE_SKETCH),
        "source_sketch_sha256": hashlib.sha256(SOURCE_SKETCH.read_bytes()).hexdigest(),
        "safe_mode": True,
        "source_derived_only": True,
        "renderer": "direct-svg",
        "physics_checks": evaluate_physics(load_spec(args.spec))[1],
        "layout_checks": evaluate_layout(load_spec(args.spec))[1],
        "sources": {
            "qgp_colour_and_edge": "article_t330_qgp_fireball",
            "jet_motif": "PRL125.122301-fig01",
        },
        "outputs": {
            "svg": str(svg_path),
            "png": str(png_path),
            "pdf": str(pdf_path),
        },
    }
    (outdir / f"{args.stem}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
