#!/usr/bin/env python3
"""
T3-03 复现（参数化版）—— 供 auto_converge.py 驱动

与 repro_T3-03.py 的区别：所有可调量从 params.json 读，便于自动搜索。
渲染产物固定写到 repro/auto/ 下，文件名由 --tag 决定。
"""
import argparse
import colorsys
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_lib import SVG

OUT = Path(__file__).parent / "repro" / "auto"
OUT.mkdir(parents=True, exist_ok=True)

DEFAULTS = {
    # 几何
    "canvas_w": 345, "canvas_h": 737,
    "panel_r": 158, "panel_dy": 390,
    "spoke_n": 40, "spoke_w0": 0.95, "spoke_w1": 1.80,
    "spoke_r_in": 0.155, "spoke_r_out": 0.925,
    "glow_scale": 0.78, "halo_r": 1.12, "glow_opacity": 0.34,
    "shell_depth": 19.0, "shell_scale": 1.072,
    # 颜色
    "sat_mul": 1.00,        # 饱和度乘子（<1 降饱和）
    "dark_mul": 1.00,       # 描边加深乘子（<1 更深）
    "grad_span": 1.00,      # 渐变跨度（>1 渐变区间更长）
    # ★ 扩参数空间：针对卡住的 whitespace 和 gradient_ratio
    "face_tone": 1.00,      # 前表面亮度（<1 更灰 = 留白更少）
    "face_grad_r": 0.60,    # 前表面径向渐变半径（>1 渐变区更大）
    "halo_r": 1.12,         # 外晕半径倍数（>1 渐变区更大）
}


def load_params(path):
    p = dict(DEFAULTS)
    if path and Path(path).exists():
        p.update(json.loads(Path(path).read_text()))
    return p


def desat(hexstr, k):
    """按乘子 k 调饱和度。k<1 降饱和。"""
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    ss = max(0.0, min(1.0, ss * k))
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def darken(hexstr, k):
    """按乘子 k 调明度。k<1 更深。"""
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"#{int(r*255*k):02x}{int(g*255*k):02x}{int(b*255*k):02x}"


def convex_hull(pts):
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lo = []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def ngon(cx, cy, R, n=12, rot=15.0):
    return [(cx + R*math.cos(math.radians(rot + 360*k/n)),
             cy + R*math.sin(math.radians(rot + 360*k/n))) for k in range(n)]


def build(P):
    W, H = P["canvas_w"], P["canvas_h"]
    R = P["panel_r"]
    s = SVG(W, H)

    def panel(cx, cy, annot):
        d = P["shell_depth"]
        front = ngon(cx, cy, R)
        back = [(x - d, y - d * 1.05)
                for x, y in ngon(cx, cy, R * P["shell_scale"])]
        side = s.linear([(0.00, "#fbfcfd", 1), (0.30, "#e4e8ed", 1),
                         (0.60, "#c4cad3", 1), (0.85, "#a2a9b4", 1),
                         (1.00, "#868d99", 1)], x1=0, y1=0, x2=1, y2=1)
        ft = P["face_tone"]
        fg = lambda c: darken(c, ft) if ft < 1.0 else c
        face = s.radial([(0.00, fg("#ffffff"), 1), (0.62, fg("#fbfbfc"), 1),
                         (0.88, fg("#eef0f3"), 1), (1.00, fg("#e2e5ea"), 1)],
                        cx=0.5, cy=0.5, r=P["face_grad_r"])
        hull = convex_hull(front + back)
        s.add('<path d="M ' + " L ".join(f"{x:.2f} {y:.2f}" for x, y in hull)
              + f' Z" fill="url(#{side})" stroke="{darken("#8b9099", P["dark_mul"])}" stroke-width="0.9"/>')
        s.add('<path d="M ' + " L ".join(f"{x:.2f} {y:.2f}" for x, y in front)
              + f' Z" fill="url(#{face})" stroke="{darken("#8b9099", P["dark_mul"])}" stroke-width="1"/>')
        for rr, sw, op, col in [(0.985, 1.0, 0.9, "#8a919c"),
                                (0.955, 0.9, 0.75, "#98a0ab"),
                                (0.928, 0.8, 0.60, "#a8b0ba")]:
            pts = ngon(cx, cy, R * rr)
            s.add('<path d="M ' + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
                  + f' Z" fill="none" stroke="{col}" stroke-width="{sw}" opacity="{op}"/>')

        # 辐条：实测色渐变
        r_in, r_out = R * P["spoke_r_in"], R * P["spoke_r_out"]
        stops = [(0.00, 0xf5a070), (0.20, 0xfb833c), (0.45, 0xa15e69),
                 (0.69, 0x2f3491), (1.00, 0x2a2f96)]

        def col_at(u):
            span = P["grad_span"]
            u = min(1.0, u * span)
            for i in range(len(stops) - 1):
                u0, c0 = stops[i]
                u1, c1 = stops[i + 1]
                if u0 <= u <= u1:
                    k = (u - u0) / (u1 - u0)
                    rgb = tuple(int(((c0 >> sh) & 255)*(1-k) + ((c1 >> sh) & 255)*k)
                                for sh in (16, 8, 0))
                    hx = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                    return desat(hx, P["sat_mul"])
            return desat("#2a2f96", P["sat_mul"])

        seg = 18
        for k in range(int(P["spoke_n"])):
            a = math.radians(15 + 360*k/P["spoke_n"])
            ca, sa = math.cos(a), math.sin(a)
            for j in range(seg):
                u0, u1 = j/seg, (j+1)/seg
                rr0 = r_in + (r_out - r_in)*u0
                rr1 = r_in + (r_out - r_in)*u1
                w = P["spoke_w0"] + P["spoke_w1"]*u0
                s.add(f'<line x1="{cx+ca*rr0:.2f}" y1="{cy+sa*rr0:.2f}" '
                      f'x2="{cx+ca*rr1:.2f}" y2="{cy+sa*rr1:.2f}" '
                      f'stroke="{col_at(u0)}" stroke-width="{w:.2f}"/>')

        # 中心发光
        r = R * 0.205
        core = s.radial([(0.00, "#fff6e8", 0.90), (0.16, "#ffd7a8", 0.86),
                         (0.38, "#fcaa70", 0.74), (0.64, "#f47e46", 0.46),
                         (1.00, "#e0501e", 0.0)])
        bl = s.blur(r * 0.26)
        halo = s.mat_glow("#ff8c42")
        s.add(f'<circle cx="{cx}" cy="{cy}" r="{r*P["halo_r"]:.1f}" '
              f'fill="url(#{halo})" opacity="{P["glow_opacity"]}" filter="url(#{bl})"/>')
        s.add(f'<circle cx="{cx}" cy="{cy}" r="{r*P["glow_scale"]:.1f}" '
              f'fill="url(#{core})" filter="url(#{bl})"/>')
        s.add(f'<circle cx="{cx}" cy="{cy}" r="{r*1.02:.1f}" fill="none" '
              f'stroke="#1a1a1a" stroke-width="1.2"/>')

        if annot:
            # ϕ 弧箭头
            ar = R * 1.06
            a0, a1 = math.radians(-152), math.radians(-28)
            mk = s._reg('<marker id="__ID__" viewBox="0 0 10 10" refX="8" refY="5" '
                        'markerWidth="6.5" markerHeight="6.5" '
                        'orient="auto-start-reverse">'
                        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#333"/></marker>', "mk")
            s.add(f'<path d="M {cx+ar*math.cos(a0):.1f} {cy+ar*math.sin(a0):.1f} '
                  f'A {ar:.1f} {ar:.1f} 0 0 1 {cx+ar*math.cos(a1):.1f} '
                  f'{cy+ar*math.sin(a1):.1f}" fill="none" stroke="#333" '
                  f'stroke-width="1.0" marker-end="url(#{mk})"/>')
            s.text(cx + 8, cy - ar + 8, "ϕ", 21)
            # x-y 指示
            ax, ay = cx - R*0.95, cy + R*0.72
            s.add(f'<path d="M {ax} {ay} L {ax+26} {ay} M {ax+21} {ay-3.5} '
                  f'L {ax+26} {ay} L {ax+21} {ay+3.5}" fill="none" stroke="#333" stroke-width="1.1"/>')
            s.add(f'<path d="M {ax} {ay} L {ax} {ay-26} M {ax-3.5} {ay-21} '
                  f'L {ax} {ay-26} L {ax+3.5} {ay-21}" fill="none" stroke="#333" stroke-width="1.1"/>')
            s.text(ax+29, ay+4, "x", 12)
            s.text(ax-3, ay-30, "y", 12)

    s.text(6, 24, "g", 22, weight="bold")
    panel(W/2, int(173), True)
    panel(W/2, int(173 + P["panel_dy"]), False)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=None)
    ap.add_argument("--tag", default="p")
    a = ap.parse_args()
    P = load_params(a.params)
    s = build(P)
    s.save(OUT / f"{a.tag}.svg")
    s.render(OUT / f"{a.tag}.png", width=920)
    print(f"OK {a.tag}")


if __name__ == "__main__":
    main()
