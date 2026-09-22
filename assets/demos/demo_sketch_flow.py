# -*- coding: utf-8 -*-
"""草图 -> Nature 级配图（矢量直出）。
物理 = 用户草图上的内容：形变核 -> 量子涨落 -> 碰撞 -> QGP 火球。
图元全部来自 skill 的 cartoon_lib / svg_lib（统一光源 + 命名图层）。"""
import pathlib
import sys

# 仓库布局：assets/demos/  ->  scripts/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
import math
import cartoon_lib as C
from cartoon_lib import Cartoon, PALETTE, INK_SOFT

# 统一光源：掠一些（抬得低）-> 细网格线有明暗、球有明确亮暗，避免"平贴纸感"
C.LIGHT_AZIMUTH = 128.0
C.LIGHT_ELEVATION = 26.0
HX, HY = C.shade_center()

W, H = 1080, 340
c = Cartoon(W, H)
Y = 118.0
BODY = PALETTE["nucleus"]
EDGE = PALETTE["nucleus_edge"]


def _fill(cx, cy, rx, ry, ang, op=1.0):
    m = c.radial([(0.00, "#ffffff", 0.98),
                  (0.22, "#eef3ff", 1.0),
                  (0.58, BODY[0], 1.0),
                  (0.86, BODY[1], 1.0),
                  (1.00, BODY[2], 1.0)],
                 cx=HX, cy=HY, r=0.92)
    return (f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})" fill="url(#{m})" '
            f'stroke="{EDGE}" stroke-width="2.2" stroke-opacity="{op:.2f}"/>')


def _grid(cx, cy, rx, ry, ang, op=0.42):
    """长椭球的经纬网格：经线 = rx 固定 / ry 变化；纬线 = 沿长轴等分的小椭圆。"""
    out = []
    for k in (0.34, 0.62, 0.86):
        out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
                   f'ry="{ry*k:.1f}" fill="none" stroke="{PALETTE["nucleus_stripe"]}" '
                   f'stroke-width="0.9" opacity="{op:.2f}"/>')
    for f in (-0.66, -0.33, 0.33, 0.66):
        r2 = ry * math.sqrt(max(0.02, 1 - f * f))
        out.append(f'<ellipse cx="{cx + rx*f:.1f}" cy="{cy:.1f}" rx="{r2*0.34:.1f}" '
                   f'ry="{r2:.1f}" fill="none" stroke="{PALETTE["nucleus_stripe"]}" '
                   f'stroke-width="0.9" opacity="{op:.2f}"/>')
    return f'<g transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})">' + "".join(out) + '</g>'


def _outline(cx, cy, rx, ry, ang, op=0.55, col=None):
    """涨落的"幽灵轮廓"：只描边、虚线，表达取向不确定。"""
    return (f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})" fill="none" '
            f'stroke="{col or EDGE}" stroke-width="1.5" '
            f'stroke-dasharray="9 6" opacity="{op:.2f}"/>')


def _nucleons(cx, cy, rx, ang, r=9.0):
    """形变核里的核子：沿长轴排，受光小球（直接画到画布上）。"""
    th = math.radians(ang)
    for f in (-0.50, 0.0, 0.50):
        lx = f * rx
        c.shaded_sphere(cx + lx * math.cos(th), cy + lx * math.sin(th),
                        r, base="#dfe7ff", edge_w=1.0)


# ══════════════════════════ A：形变核
c.begin_layer("panel-A-deformed-nucleus", "A · prolate deformed nucleus")
c.cast_shadow(112, Y + 30, 46, 11, height=0.5, opacity=0.18)
c.add(_fill(112, Y, 44, 25, -20))
c.add(_grid(112, Y, 44, 25, -20))
_nucleons(112, Y, 44, -20)
c.end_layer()

# ══════════════════════════ B：量子涨落（取向叠加）
c.begin_layer("panel-B-quantum-fluctuations", "B · quantum fluctuations")
c.cast_shadow(330, Y + 30, 50, 11, height=0.5, opacity=0.16)
for a in (-40.0, -2.0):
    c.add(_outline(330, Y, 44, 25, a, op=0.5))
c.add(_fill(330, Y, 44, 25, -20))
c.add(_grid(330, Y, 44, 25, -20))
_nucleons(330, Y, 44, -20)
c.end_layer()

# ══════════════════════════ C：碰撞（重叠区 = 参与者区）
c.begin_layer("panel-C-collision", "C · collision")
c.cast_shadow(600, Y + 30, 54, 11, height=0.5, opacity=0.16)
c.add(_fill(574, Y, 44, 25, 24))
c.add(_grid(574, Y, 44, 25, 24))
c.add(_fill(626, Y, 44, 25, -24))
c.add(_grid(626, Y, 44, 25, -24))
lens = c.radial([(0.0, "#ffe6a8", 0.92), (0.5, "#ffb85c", 0.80),
                 (1.0, "#e05018", 0.28)])
c.add(f'<ellipse cx="600" cy="{Y:.0f}" rx="15" ry="25" fill="url(#{lens})"/>')
c.add(f'<ellipse cx="600" cy="{Y:.0f}" rx="15" ry="25" fill="none" '
      f'stroke="#c8501a" stroke-width="1.3" opacity="0.7"/>')
c.end_layer()

# ══════════════════════════ D：QGP 火球
c.begin_layer("panel-D-qgp-fireball", "D · QGP fireball")
c.cast_shadow(900, Y + 33, 58, 12, height=0.5, opacity=0.16)
glow = c.mat_glow("#ff8c42")
c.add(f'<circle cx="900" cy="{Y:.0f}" r="88" fill="url(#{glow})" opacity="0.36" '
      f'filter="url(#{c.blur(28)})"/>')
hot = c.radial([(0.00, "#fffaf0", 1.0), (0.28, "#ffd9a0", 0.96),
                (0.58, "#fca25c", 0.90), (0.82, "#f06a28", 0.78),
                (1.00, "#d84010", 0.0)])
c.add(f'<circle cx="900" cy="{Y:.0f}" r="54" fill="url(#{hot})"/>')
for a, op in ((28.0, 0.55), (-28.0, 0.55)):
    c.add(_outline(900, Y, 40, 26, a, op=op, col="#a83410"))
c.add(f'<circle cx="900" cy="{Y:.0f}" r="54" fill="none" stroke="#c8501a" '
      f'stroke-width="2.2" stroke-opacity="0.65"/>')
c.radial_arrows(900, Y, 54, n=6, r_in=0.80, r_out=1.28)
c.end_layer()

# ══════════════════════════ 阶段箭头
c.begin_layer("stage-arrows", "stage arrows")
for x1, x2 in ((174, 264), (400, 508), (690, 826)):
    c.tapered_arrow(x1, Y, x2, Y, w=3.6, color=INK_SOFT, head_frac=0.34)
c.end_layer()

# ══════════════════════════ 文字（真 <text>，可编辑）
c.begin_layer("labels", "labels")
for x, lines in ((112, ("Deformed", "nucleus")),
                 (330, ("Quantum", "fluctuations")),
                 (600, ("Collision",)),
                 (900, ("QGP fireball",))):
    if len(lines) == 1:
        c.label(x, 238, lines[0], size=17, weight="bold")
    else:
        c.label(x, 222, lines[0], size=17, weight="bold")
        c.label(x, 244, lines[1], size=17, weight="bold")
c.end_layer()

c.begin_layer("caption", "caption")
c.label(34, 302, "Rough sketch of the SAME physics as the STAR reference "
                 "(deformed nucleus \u2192 fluctuations \u2192 collision \u2192 fireball)",
        size=12.5, anchor="start", color="#3a3a3a")
c.end_layer()

c.save("sketch_nature.svg")
c.render("sketch_nature.png", width=W)
print("ok")


