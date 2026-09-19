#!/usr/bin/env python3
"""
草图 3 → 期刊级配图：喷注淬火
================================
严格按 ir/sketch3_jet.ir.yaml 实现。

物理核对（IR 末尾列的四条，实现时必须守住）：
  1. 介质必须【包裹】碰撞区，不能只在一侧
  2. 两个喷注必须【背对背】源自同一顶点
  3. 顶点必须【偏离】介质中心 → 表面偏置
  4. 能量损失用【胶子辐射】表达，不只是箭头变细
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEMO_OUT = HERE / "_demo_out"; DEMO_OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE))
from svg_lib import SVG
import geom

OUT = DEMO_OUT
OUT.mkdir(exist_ok=True)
FONT = "DejaVu Sans"


# ---------------------------------------------------------------- 介质
def qgp_medium(s, cx, cy, R, ry=0.72):
    """
    有机团块 + 暖色渐变 + 弥散边缘 + **内部密度结构**。
    ★ 质量修正：原来只有一层径向渐变 → 平坦、没有"介质"的体积感。
      参考库的 T3 图里，介质内部是有起伏的（热区/冷区）。
      做法：叠 8-10 个软斑（不同温度、不同大小），形成密度不均的观感。
    """
    import random
    rng = random.Random(21)
    b = geom.blob(cx, cy, R, R * ry, wobble=0.11, n=72, seed=5)
    d = geom.poly_to_path(b)

    # ① 外层弥散
    g0 = s.radial([(0.0, "#ff8c28", 0.42), (0.6, "#dc3808", 0.24),
                   (1.0, "#b82000", 0.0)])
    s.add(f'<path d="{d}" fill="url(#{g0})" filter="url(#{s.blur(R*0.20)})"/>')

    # ② 主体（略降不透明度，给内部结构留空间）
    g1 = s.radial([(0.0, "#ffb850", 0.80), (0.40, "#f86818", 0.72),
                   (0.74, "#dc3808", 0.54), (1.0, "#b82000", 0.0)])
    s.add(f'<path d="{d}" fill="url(#{g1})" filter="url(#{s.blur(R*0.10)})"/>')

    # ③ ★ 内部密度斑（热区偏亮黄、冷区偏暗红）
    clip = s._reg(f'<clipPath id="__ID__"><path d="{d}"/></clipPath>', "cp")
    for i in range(11):
        a = rng.uniform(0, 2*math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * R * 0.82
        px, py = cx + rr*math.cos(a), cy + rr*math.sin(a)*ry
        sz = R * rng.uniform(0.20, 0.44)
        hot = rng.random() < 0.55
        col = "#ffd070" if hot else "#a82800"
        op = rng.uniform(0.22, 0.40)
        m = s.radial([(0.0, col, op), (0.55, col, op*0.45), (1.0, col, 0.0)])
        bl = s.blur(sz*0.42)
        s.add(f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{sz:.1f}" '
              f'ry="{sz*0.72:.1f}" fill="url(#{m})" filter="url(#{bl})" '
              f'clip-path="url(#{clip})"/>')

    # ④ 边界（可辨的深色线，实验室已证：基准要求）
    s.add(f'<path d="{d}" fill="none" stroke="#8a3010" '
          f'stroke-width="2.0" stroke-opacity="0.72"/>')
    return b


# ---------------------------------------------------------------- 入射核
def lorentz_nucleus(s, cx, cy, rx, ry):
    """Lorentz 收缩的核：竖直扁椭圆 + 描边 + 内部核子暗示。"""
    m = s.radial([(0.0, "#c8d4f8", 0.92), (0.45, "#7a8ee0", 0.88),
                  (1.0, "#4a5cb8", 0.72)], cx=0.42, cy=0.35, r=0.78)
    s.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#{m})" '
          f'stroke="#1a2560" stroke-width="1.9" stroke-opacity="0.95"/>')
    # 内部横向条纹，暗示压扁的核物质
    for i in range(-3, 4):
        yy = cy + i * ry * 0.22
        hw = rx * math.sqrt(max(0.02, 1 - (i * 0.22 / 1.0) ** 2)) * 0.72
        s.add(f'<line x1="{cx-hw:.1f}" y1="{yy:.1f}" x2="{cx+hw:.1f}" '
              f'y2="{yy:.1f}" stroke="#5a6fd0" stroke-width="0.9" '
              f'opacity="0.45"/>')


# ---------------------------------------------------------------- 顶点
def hard_vertex(s, x, y, r=22, n=11):
    """硬散射顶点：星芒。"""
    glow = s.mat_glow("#fff0b0")
    s.add(f'<circle cx="{x}" cy="{y}" r="{r*2.1}" fill="url(#{glow})" '
          f'opacity="0.75"/>')
    for i in range(n):
        a = 2 * math.pi * i / n + 0.14
        L = r * (1.0 if i % 2 == 0 else 0.68)
        s.add(f'<line x1="{x}" y1="{y}" x2="{x+L*math.cos(a):.1f}" '
              f'y2="{y+L*math.sin(a):.1f}" stroke="#5a3608" '
              f'stroke-width="2.6" stroke-linecap="round" opacity="0.95"/>')
    s.add(f'<circle cx="{x}" cy="{y}" r="{r*0.30:.1f}" fill="#fff8dc" '
          f'stroke="#8a5a10" stroke-width="1.2"/>')


# ---------------------------------------------------------------- 喷注
def jet(s, x0, y0, x1, y1, w0, w1, c0, c1, cone=True):
    """
    渐细喷注。**三层结构**：
      ① 外围发散晕（宽、淡）——喷注不是一条线，是一束
      ② 主体（渐细、渐暗）——能量损失的视觉语言
      ③ 准直核心（细、亮）——硬核心
    ★ 质量修正：原来只有单层线 → 看着像"一根绳"，不像喷注。
    """
    def mix(a, b, t):
        a, b = a.lstrip("#"), b.lstrip("#")
        return "#" + "".join(
            f"{int(int(a[i:i+2],16)*(1-t) + int(b[i:i+2],16)*t):02x}"
            for i in (0, 2, 4))
    K = 30
    # ① 外围晕
    bl = s.blur(w0 * 0.95)
    s.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
          f'stroke="{c0}" stroke-width="{w0*3.1:.1f}" stroke-opacity="0.22" '
          f'stroke-linecap="round" filter="url(#{bl})"/>')
    # ② 主体
    for i in range(K):
        t0, t1 = i / K, (i + 1) / K
        ax, ay = x0 + (x1-x0)*t0, y0 + (y1-y0)*t0
        bx, by = x0 + (x1-x0)*t1, y0 + (y1-y0)*t1
        s.add(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
              f'stroke="{mix(c0,c1,t0)}" stroke-width="{w0+(w1-w0)*t0:.2f}" '
              f'stroke-linecap="round"/>')
    # ③ 准直核心（更细更亮，只到 70% 处就衰减——能量损失）
    for i in range(K):
        t0, t1 = i / K, (i + 1) / K
        if t0 > 0.72:
            break
        k = 1 - t0 / 0.72
        ax, ay = x0 + (x1-x0)*t0, y0 + (y1-y0)*t0
        bx, by = x0 + (x1-x0)*t1, y0 + (y1-y0)*t1
        s.add(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
              f'stroke="#fffbe8" stroke-width="{w0*0.30*(0.4+0.6*k):.2f}" '
              f'stroke-opacity="{0.85*k:.2f}" stroke-linecap="round"/>')
    if cone:
        ang = math.atan2(y1-y0, x1-x0)
        px, py = -math.sin(ang), math.cos(ang)
        L, sp = 52, w1 * 5.8
        s.add(f'<path d="M {x1:.1f} {y1:.1f} '
              f'L {x1-L*math.cos(ang)+px*sp:.1f} {y1-L*math.sin(ang)+py*sp:.1f} '
              f'L {x1-L*math.cos(ang)-px*sp:.1f} {y1-L*math.sin(ang)-py*sp:.1f} Z" '
              f'fill="{c1}" opacity="0.26"/>')


def gluon_radiation(s, x0, y0, x1, y1, n=5, seed=3):
    """胶子辐射：沿喷注路径向外发出的小螺旋线。"""
    import random
    rng = random.Random(seed)
    ang = math.atan2(y1-y0, x1-x0)
    for i in range(n):
        t = 0.18 + 0.72 * (i / max(1, n - 1))
        bx, by = x0 + (x1-x0)*t, y0 + (y1-y0)*t
        for sgn in (-1, 1):
            if rng.random() < 0.32:
                continue
            spread = math.radians(rng.uniform(38, 72)) * sgn
            aa = ang + spread
            L = rng.uniform(30, 52)
            ex, ey = bx + L*math.cos(aa), by + L*math.sin(aa)
            # 螺旋（弹簧线）
            pts = []
            K = 34
            for k in range(K + 1):
                u = k / K
                mx = bx + (ex-bx)*u
                my = by + (ey-by)*u
                off = math.sin(u * 3.2 * 2*math.pi) * 4.6 * (1 - u*0.4)
                pts.append((mx - math.sin(aa)*off, my + math.cos(aa)*off))
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            s.add(f'<path d="{d}" fill="none" stroke="#8a4a18" '
                  f'stroke-width="1.8" opacity="{0.92 - 0.08*i:.2f}"/>')


def medium_wake(s, x0, y0, x1, y1, n=4):
    """介质尾迹：喷注路径旁的弧形波纹（激波/马赫锥）。"""
    ang = math.atan2(y1-y0, x1-x0)
    for i in range(n):
        t = 0.30 + 0.16 * i
        bx, by = x0 + (x1-x0)*t, y0 + (y1-y0)*t
        rr = 26 + 20 * i
        for sgn in (-1, 1):
            a0 = ang + sgn * math.radians(52)
            a1 = ang + sgn * math.radians(108)
            xa, ya = bx + rr*math.cos(a0), by + rr*math.sin(a0)
            xb, yb = bx + rr*math.cos(a1), by + rr*math.sin(a1)
            s.add(f'<path d="M {xa:.1f} {ya:.1f} A {rr} {rr} 0 0 {1 if sgn>0 else 0} '
                  f'{xb:.1f} {yb:.1f}" fill="none" stroke="#ffffff" '
                  f'stroke-width="2.6" opacity="{0.34 - 0.05*i:.2f}" '
                  f'stroke-linecap="round"/>')


def label(s, x, y, t, sz=18, anchor="middle", bold=False):
    w = ' font-weight="bold"' if bold else ""
    s.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" '
          f'font-family="{FONT}" fill="#0d0d0d" text-anchor="{anchor}"{w}>{t}</text>')


# ================================================================ 组装
def main():
    W, H = 1020, 640
    s = SVG(W, H)
    CX, CY = 0.44 * W, 0.50 * H          # 介质中心
    R = 0.185 * W
    # ★ 几何修正：顶点必须在【介质边缘附近】（r = 0.72 R），
    #   否则两个喷注的介质内路径长度差不多，"表面偏置"就没了物理意义。
    #   参考 ir/sketch3_jet.ir.yaml 的 geometry_constraints。
    A = math.radians(-52)                # 顶点方位角（右上）
    VR = 0.72 * R
    VX, VY = CX + VR*math.cos(A), CY + VR*math.sin(A)*0.72
    # 逃逸喷注：朝【外】（远离中心）；淬火喷注：朝【内】（穿过介质）
    D_OUT = math.radians(-52)
    D_IN  = D_OUT + math.pi

    # ── 背景大气（极淡，给画面"呼吸感"）──
    s.begin_layer("layer-bg", "0 背景")
    bgm = s.radial([(0.0, "#fff8f0", 1.0), (0.55, "#fdfbf8", 1.0),
                    (1.0, "#f6f4f0", 1.0)], cx=0.45, cy=0.45, r=0.78)
    s.add(f'<rect x="0" y="0" width="{W}" height="{H}" fill="url(#{bgm})"/>')
    s.end_layer()

    # ── E1 介质 ──
    s.begin_layer("layer-medium", "1 QGP 介质")
    qgp_medium(s, CX, CY, R)
    s.end_layer()

    # ── E2 入射核 ──
    s.begin_layer("layer-nuclei", "2 入射核")
    lorentz_nucleus(s, CX - 0.045*W, CY, 0.020*W, 0.13*H)
    lorentz_nucleus(s, CX + 0.045*W, CY, 0.020*W, 0.13*H)
    s.end_layer()

    # 两个喷注的端点
    # 喷注长度：收缩到画布内（上一版端点跑出画布了）
    L_out = 0.255 * W
    L_in  = 0.50 * W
    OX, OY = VX + L_out*math.cos(D_OUT), VY + L_out*math.sin(D_OUT)*0.85
    IX, IY = VX + L_in*math.cos(D_IN),  VY + L_in*math.sin(D_IN)*0.72

    # ── E6 介质尾迹（在喷注之下，只沿淬火路径）──
    s.begin_layer("layer-wake", "3 介质尾迹")
    medium_wake(s, VX, VY, IX, IY, n=4)
    s.end_layer()

    # ── E4/E5 两个喷注 ──
    s.begin_layer("layer-jets", "4 双喷注")
    # 逃逸：朝外，短路径，亮，几乎不变细
    jet(s, VX, VY, OX, OY, 7.0, 5.6, "#ffe066", "#ffb020")
    # 淬火：朝内穿过介质，长路径，明显变细 + 由亮转暗
    jet(s, VX, VY, IX, IY, 7.0, 1.8, "#ffd060", "#a04010")
    gluon_radiation(s, VX, VY, IX, IY, n=5)
    s.end_layer()

    # ── E3 顶点（最亮，压在最上）──
    s.begin_layer("layer-vertex", "5 硬散射顶点")
    hard_vertex(s, VX, VY, 20)
    s.end_layer()

    # ── E7 标注 ──
    s.begin_layer("layer-labels", "6 标注")
    label(s, CX - 0.045*W, CY - 0.175*H, "nucleus A", 17)
    label(s, CX + 0.045*W, CY - 0.175*H, "nucleus B", 17)
    label(s, CX, CY + 0.215*H, "QGP medium", 19)
    label(s, VX + 0.048*W, VY - 0.115*H, "hard scattering", 16, anchor="start")
    label(s, OX + 0.012*W, OY - 0.012*H, "escaping jet", 17, anchor="start")
    label(s, IX - 0.012*W, IY + 0.062*H, "quenched jet", 17, anchor="end")
    label(s, W/2, 0.955*H,
          "Surface bias: the hard vertex sits near the medium edge, so the two "
          "jets traverse different path lengths", 13)
    s.end_layer()

    s.save(OUT / "jet_quenching.svg")
    s.render(OUT / "jet_quenching.png", width=1900)
    s.render(OUT / "jet_quenching.pdf")

    # 交付格式：EPS（Nature 首选之一）
    import subprocess
    subprocess.run(["pdftops", "-eps", str(OUT / "jet_quenching.pdf"),
                    str(OUT / "jet_quenching.eps")], capture_output=True)
    print("已输出:")
    for f in ["jet_quenching.svg", "jet_quenching.png",
              "jet_quenching.pdf", "jet_quenching.eps"]:
        p = OUT / f
        if p.exists():
            print(f"  {f:<26} {p.stat().st_size//1024} KB")


if __name__ == "__main__":
    main()
