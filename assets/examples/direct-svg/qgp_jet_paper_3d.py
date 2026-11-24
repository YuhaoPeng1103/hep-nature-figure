"""Direct 3D QGP-jet storyboard assembled from article-derived vector assets."""
from __future__ import annotations

import json
import math
import sys
import argparse
from html import escape
from pathlib import Path
from random import Random

import cairosvg

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from element_library import load_index  # noqa: E402
from spec_compile import load_asset_svg, evaluate_layout, evaluate_physics  # noqa: E402
from spec_confirm import canonical_hash, load_spec  # noqa: E402

W, H = 840, 459
OUTPUT = (4323, 2362)
OUT = Path(__file__).resolve().parent


def tag(name, inside=None, **kw):
    attrs = "".join(
        f' {key.replace("_", "-")}="{escape(str(value), quote=True)}"'
        for key, value in kw.items()
        if value is not None
    )
    return f"<{name}{attrs}/>" if inside is None else f"<{name}{attrs}>{inside}</{name}>"


def url(name):
    return f"url(#{name})"


def path(d, fill="none", **kw):
    if "stroke_width" in kw:
        kw.setdefault(
            "data_stroke_pt",
            f"{float(kw['stroke_width']) * 183.0 / W * 72.0 / 25.4:.2f}",
        )
    return tag("path", d=d, fill=fill, **kw)


def line(a, b, stroke, width, **kw):
    return path(f"M {a[0]:.3f} {a[1]:.3f} L {b[0]:.3f} {b[1]:.3f}",
                stroke=stroke, stroke_width=width, stroke_linecap="round", **kw)


def polygon(points, fill, **kw):
    return tag("polygon", points=" ".join(f"{x:.3f},{y:.3f}" for x, y in points),
               fill=fill, **kw)


def ellipse(x, y, rx, ry, fill, **kw):
    return tag("ellipse", cx=x, cy=y, rx=rx, ry=ry, fill=fill, **kw)


def text(x, y, value, size=12, **kw):
    kw.setdefault("fill", "#20242a")
    kw.setdefault(
        "data_font_size_pt",
        f"{size * 183.0 / W * 72.0 / 25.4:.2f}",
    )
    return tag("text", value, x=x, y=y, font_family="DejaVu Sans",
               font_size=size, **kw)


def gradient(kind, ident, stops, **kw):
    body = "".join(
        tag("stop", offset=offset, stop_color=color, stop_opacity=opacity)
        for offset, color, opacity in stops
    )
    return tag(kind + "Gradient", body, id=ident, **kw)


def marker(ident, color):
    return tag(
        "marker",
        tag("path", "M0 0 L10 5 L0 10 Z", fill=color),
        id=ident, viewBox="0 0 10 10", refX="9", refY="5",
        markerWidth="5", markerHeight="5", orient="auto-start-reverse",
    )


def asset_render(asset_id, x, y, width, height, rotation=0, prefix="asset",
                 use_texture=True):
    assets = {a["id"]: a for a in load_index()["assets"]}
    asset = assets[asset_id]
    generation = asset["generation"]
    relative = (
        generation.get("texture_file") or asset["file"]
        if use_texture else asset["file"]
    )
    source = ROOT / "assets" / "element-library" / relative
    vb, definitions, body = load_asset_svg(source, prefix + "_")
    scale = min(width / (vb[2] - vb[0]), height / (vb[3] - vb[1]))
    offset_x = (width - (vb[2] - vb[0]) * scale) / 2
    offset_y = (height - (vb[3] - vb[1]) * scale) / 2
    transform = (
        f"translate({x:.3f} {y:.3f}) rotate({rotation:.3f}) "
        f"translate({-width/2:.3f} {-height/2:.3f}) "
        f"translate({offset_x:.3f} {offset_y:.3f}) "
        f"scale({scale:.6f}) translate({-vb[0]:.3f} {-vb[1]:.3f})"
    )
    return definitions, (
        f'<g data-element="{asset_id}" '
        f'data-origin="article_vector_native" transform="{transform}">{body}</g>'
    )


def build() -> str:
    definitions = [
        gradient("linear", "board-fill", [
            (0, "#d9dfe6", 1), (.58, "#eef1f4", 1), (1, "#d4dbe3", 1),
        ], x1="0%", y1="0%", x2="0%", y2="100%"),
        gradient("linear", "jet-escape", [
            (0, "#0751a2", .92), (.35, "#1389db", .93),
            (.72, "#63d6f5", .68), (1, "#d8fbf2", 0),
        ], x1="0%", y1="0%", x2="100%", y2="0%"),
        gradient("linear", "jet-quench", [
            (0, "#dce3e8", .23), (.35, "#aeb9c4", .63),
            (.76, "#788894", .84), (1, "#465664", .92),
        ], x1="0%", y1="0%", x2="100%", y2="0%"),
        gradient("radial", "medium-glow", [
            (0, "#ffd15a", .46), (.46, "#ef7332", .23), (1, "#d24d26", 0),
        ], cx=".5", cy=".5", r=".62"),
        marker("axis-arrow", "#28333e"),
    ]

    board = [(72, 253), (510, 152), (806, 255), (354, 424)]
    board_d = "M " + " L ".join(f"{x} {y}" for x, y in board) + " Z"
    layers = []
    layers.append(tag("rect", x=0, y=0, width=W, height=H, fill="#ffffff"))
    layers.append(
        '<g id="reaction-plane" data-element="reaction-plane">'
        + path(board_d, url("board-fill"), stroke="#b4bfca", stroke_width=.8)
        + path("M72 253 L510 152 L806 255 M72 253 L354 424 "
               "M510 152 L806 255 M354 424 L806 255",
               stroke="#b9c4ce", stroke_width=.55, opacity=.7)
        + "</g>"
    )

    # Shifted diamond grid inside the plane.
    def project(u, v):
        a, b, c, d = board
        return (
            a[0] * (1-u) * (1-v) + b[0] * u * (1-v)
            + c[0] * u * v + d[0] * (1-u) * v,
            a[1] * (1-u) * (1-v) + b[1] * u * (1-v)
            + c[1] * u * v + d[1] * (1-u) * v,
        )

    grid = []
    for i in range(1, 8):
        grid.append(line(project(i/8, 0), project(i/8, 1), "#aab7c4", .45, opacity=.6))
    for j in range(1, 6):
        grid.append(line(project(0, j/6), project(1, j/6), "#aab7c4", .45, opacity=.6))
    layers.append('<g id="plane-grid" data-element="plane-grid">' + "".join(grid) + "</g>")

    for name, x, y in (
        ("incoming_left", 160, 240),
        ("incoming_right", 686, 240),
    ):
        d, body = asset_render(
            "article_t302_shape_06", x, y, 155, 132,
            rotation=-8 if name == "incoming_left" else 8,
            prefix=name,
        )
        definitions.append(d)
        layers.append(f'<g id="{name}" data-element="{name}">{body}</g>')

    # The QGP uses the article-derived T3-30 reconstruction.
    qgp_defs, qgp_body = asset_render(
        "article_t330_qgp_fireball", 423, 240, 292, 239,
        prefix="qgp", use_texture=False,
    )
    definitions.append(qgp_defs)
    layers.append(
        '<g id="qgp-medium" data-element="qgp-medium">'
        + ellipse(423, 240, 151, 125, url("medium-glow"))
        + qgp_body + "</g>"
    )

    vertex = (435, 279)
    # Back-to-back jets share one origin. The escaping jet remains blue and compact.
    escaping = [
        (vertex[0] + 8, vertex[1] - 5),
        (714, 88),
        (731, 116),
        (451, 289),
    ]
    quenched = [
        (vertex[0] - 7, vertex[1] + 6),
        (227, 404),
        (244, 421),
        (452, 291),
    ]
    layers.append(
        '<g id="escaping-jet" data-element="escaping-jet">'
        + polygon(escaping, url("jet-escape"))
        + path("M441 267 C525 214 610 153 714 99",
               stroke="#d5ffff", stroke_width=1.2, opacity=.76)
        + "</g>"
    )
    layers.append(
        '<g id="quenched-jet" data-element="quenched-jet">'
        + polygon(quenched, url("jet-quench"))
        + path("M430 286 C369 319 305 356 235 407",
               stroke="#f2f6f8", stroke_width=.9, opacity=.57)
        + "</g>"
    )

    rng = Random(63)
    fragments = []
    for i in range(34):
        t = rng.random()
        x = vertex[0] + (238 - vertex[0]) * t + rng.gauss(0, 4 + 10*t)
        y = vertex[1] + (414 - vertex[1]) * t + rng.gauss(0, 5 + 12*t)
        r = rng.uniform(.65, 2.8)
        fragments.append(ellipse(x, y, r, r, "#d2dde5", opacity=.72))
    layers.append(
        '<g id="quenched-fragments" data-element="quenched-fragments">'
        + "".join(fragments) + "</g>"
    )

    radiation = []
    for offset, width in ((0, 1.1), (11, .85), (23, .65)):
        radiation.append(
            path(
                f"M {vertex[0]-4} {vertex[1]+12} "
                f"C {367} {306+offset} 320 {337+offset} {276} {361+offset} "
                f"S 246 {386+offset} {231} {401+offset}",
                stroke="#f7b34f", stroke_width=width, opacity=.72,
                stroke_dasharray="2 1",
            )
        )
    layers.append(
        '<g id="medium-induced-radiation" data-element="medium-induced-radiation">'
        + "".join(radiation) + "</g>"
    )

    # One explicit coordinate triad.
    ox, oy = 84, 423
    layers.append(
        '<g id="coordinate-axes" data-element="coordinate-axes">'
        + line((ox, oy), (ox, oy-58), "#294c73", 2.1, marker_end=url("axis-arrow"))
        + line((ox, oy), (ox+54, oy+28), "#2d6da6", 2.1, marker_end=url("axis-arrow"))
        + line((ox, oy), (ox+58, oy-8), "#318c71", 2.1, marker_end=url("axis-arrow"))
        + text(78, 359, "y", 13, font_weight="bold", fill="#294c73")
        + text(142, 451, "x", 12, font_weight="bold", fill="#2d6da6")
        + text(148, 415, "z", 13, font_weight="bold", fill="#318c71")
        + "</g>"
    )

    def label(ident, value, x, y, anchor="middle", color="#222830", box=True):
        width = len(value) * 6.7 + 8
        background = (
            tag("rect", x=x - width / 2, y=y - 11.5, width=width, height=16,
                rx=3.5, fill="#ffffff", opacity=.82)
            if box else ""
        )
        return (
            background
            + text(x, y, value, 12.5, id=ident, text_anchor=anchor, fill=color)
        )

    layers.append(
        '<g id="labels" data-element="labels">'
        + label("label-title", "Jet quenching in the quark–gluon plasma", 420, 32, box=False)
        + label("label-left-pb", "Pb", 160, 344)
        + label("label-right-pb", "Pb", 686, 344)
        + label("label-qgp", "QGP medium", 618, 356, color="#c7431d")
        + label("label-escape", "Escaping jet", 669, 78, color="#155b93")
        + label("label-quench", "Quenched jet", 280, 429, color="#52606e")
        + label("label-hard", "hard scattering", 606, 294, color="#3c4650")
        + path("M650 100 L603 171", stroke="#6f7982", stroke_width=.7)
        + path("M326 402 L389 327", stroke="#6f7982", stroke_width=.7)
        + path("M570 340 L520 292", stroke="#6f7982", stroke_width=.7)
        + path("M552 301 L453 276", stroke="#6f7982", stroke_width=.7)
        + "</g>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="183mm" height="100mm" viewBox="0 0 {W} {H}" '
        'data-spec="qgp-jet-paper-3d">\n'
        + "<defs>" + "".join(definitions) + "</defs>\n"
        + "\n".join(layers) + "\n</svg>\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=OUT)
    parser.add_argument("--stem", default="qgp_jet_paper_3d")
    parser.add_argument(
        "--spec",
        type=Path,
        default=ROOT / "assets" / "spec-examples" / "qgp-jet-paper-3d.spec.yaml",
    )
    args = parser.parse_args()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    svg = build()
    # Keep XML namespace declarations valid after extracting child definitions.
    svg = svg.replace(
        '<defs><',
        '<defs xmlns="http://www.w3.org/2000/svg"><',
        1,
    )
    (outdir / f"{args.stem}.svg").write_text(svg, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=str(outdir / f"{args.stem}.png"),
        output_width=OUTPUT[0], output_height=OUTPUT[1], background_color="#fff",
    )
    cairosvg.svg2pdf(
        bytestring=svg.encode("utf-8"),
        write_to=str(outdir / f"{args.stem}.pdf"),
    )
    report = {
        "schema": "hep-nature-figure/direct-svg-v1",
        "spec": str(args.spec.resolve()),
        "spec_sha256": canonical_hash(load_spec(args.spec)),
        "confirmation": "experimental",
        "safe_mode": True,
        "source_derived_only": True,
        "renderer": "direct-svg",
        "physics_checks": evaluate_physics(load_spec(args.spec))[1],
        "layout_checks": evaluate_layout(load_spec(args.spec))[1],
        "sources": {
            "nucleus": "article_t302_shape_06",
            "medium": "article_t330_qgp_fireball",
            "photon_jet_motif": "PRL125.122301-fig01",
        },
        "outputs": {
            name: str((outdir / f"{args.stem}.{name}").resolve())
            for name in ("svg", "png", "pdf")
        },
    }
    (outdir / f"{args.stem}_manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
