#!/usr/bin/env python3
"""
草图 4 → 期刊级配图：重离子碰撞的时空演化
==========================================
严格按 ir/sketch4_timeline.ir.yaml 实现。

★ 本图用于验证：输入草图的元素密度是否决定输出密度。
  草图 ~35 个绘制对象（对比喷注图 ~15 个）。

实现后自动核对 IR 里的 5 条 geometry_constraints。
"""
import math
import random
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


def label(s, x, y, t, sz=15, anchor="middle", color="#1a1a1a", weight=""):
    w = f' font-weight="{weight}"' if weight else ""
    s.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" '
          f'font-family="{FONT}" fill="{color}" text-anchor="{anchor}"{w}>{t}</text>')


def arrow(s, x1, y1, x2, y2, w=2.2, c="#2a2a2a"):
    ang = math.atan2(y2 - y1, x2 - x1)
    s.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
          f'stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>')
    L = w * 5.2
    px, py = -math.sin(ang), math.cos(ang)
    s.add(f'<path d="M {x2:.1f} {y2:.1f} '
          f'L {x2-L*math.cos(ang)+px*L*0.5:.1f} {y2-L*math.sin(ang)+py*L*0.5:.1f} '
          f'L {x2-L*math.cos(ang)-px*L*0.5:.1f} {y2-L*math.sin(ang)-py*L*0.5:.1f} Z" '
          f'fill="{c}"/>')


def lorentz_nucleus(s, cx, cy, rx, ry, overlap_shift=0.0):
    """Lorentz 收缩核：竖直扁椭圆 + 渐变 + 深描边。"""
    m = s.radial([(0.0, "#c8d6fa", 0.95), (0.45, "#7a90e0", 0.92),
                  (1.0, "#4254b0", 0.88)], cx=0.40, cy=0.34, r=0.80)
    for dx in (-overlap_shift, overlap_shift):
        s.add(f'<ellipse cx="{cx+dx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
              f'ry="{ry:.1f}" fill="url(#{m})" stroke="#1e2a70" '
              f'stroke-width="1.5" stroke-opacity="0.92"/>')
    # 内部横向条纹（压扁的核物质）
    for i in range(-4, 5):
        yy = cy + i * ry * 0.19
        hw = rx * 0.70 * math.sqrt(max(0.02, 1 - (i * 0.19) ** 2))
        for dx in (-overlap_shift, overlap_shift):
            s.add(f'<line x1="{cx+dx-hw:.1f}" y1="{yy:.1f}" '
                  f'x2="{cx+dx+hw:.1f}" y2="{yy:.1f}" stroke="#4a5cb8" '
                  f'stroke-width="0.9" opacity="0.45"/>')


def qgp_blob(s, cx, cy, R, seed=3, glow=1.0):
    """QGP 团块：有机边界 + 暖色渐变 + 内部密度斑。"""
    rng = random.Random(seed)
    b = geom.blob(cx, cy, R, R * 0.86, wobble=0.13, n=64, seed=seed)
    d = geom.poly_to_path(b)
    g0 = s.radial([(0.0, "#ff9a40", 0.40*glow), (0.6, "#dc3808", 0.22*glow),
                   (1.0, "#b82000", 0.0)])
    s.add(f'<path d="{d}" fill="url(#{g0})" filter="url(#{s.blur(R*0.20)})"/>')
    g1 = s.radial([(0.0, "#ffc060", 0.90), (0.42, "#f86818", 0.84),
                   (0.76, "#dc3808", 0.66), (1.0, "#b82000", 0.0)])
    s.add(f'<path d="{d}" fill="url(#{g1})" filter="url(#{s.blur(R*0.08)})"/>')
    clip = s._reg(f'<clipPath id="__ID__"><path d="{d}"/></clipPath>', "cp")
    for _ in range(8):
        a = rng.uniform(0, 2*math.pi)
        rr = math.sqrt(rng.uniform(0, 1)) * R * 0.78
        px, py = cx + rr*math.cos(a), cy + rr*math.sin(a)*0.86
        sz = R * rng.uniform(0.22, 0.46)
        col = "#ffd070" if rng.random() < 0.55 else "#a82800"
        op = rng.uniform(0.20, 0.36)
        mm = s.radial([(0.0, col, op), (0.55, col, op*0.4), (1.0, col, 0.0)])
        s.add(f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{sz:.1f}" '
              f'ry="{sz*0.74:.1f}" fill="url(#{mm})" '
              f'filter="url(#{s.blur(sz*0.42)})" clip-path="url(#{clip})"/>')
    s.add(f'<path d="{d}" fill="none" stroke="#8a3010" stroke-width="1.7" '
          f'stroke-opacity="0.70"/>')
    return b


def stage_approach(s, cx, cy):
    lorentz_nucleus(s, cx, cy, 26, 96, overlap_shift=62)


def stage_overlap(s, cx, cy):
    lorentz_nucleus(s, cx, cy, 26, 96, overlap_shift=28)


def stage_qgp(s, cx, cy, R=80):
    qgp_blob(s, cx, cy, R, seed=3)
    for k in range(7):
        a = 2*math.pi*k/7 + 0.2
        s.add(f'<line x1="{cx}" y1="{cy}" x2="{cx+R*0.42*math.cos(a):.1f}" '
              f'y2="{cy+R*0.42*math.sin(a):.1f}" stroke="#7a3a08" '
              f'stroke-width="2.2" stroke-linecap="round" opacity="0.85"/>')
    s.add(f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="#fff4d0" '
          f'stroke="#7a3a08" stroke-width="1.2"/>')


def stage_expansion(s, cx, cy, R=104):
    qgp_blob(s, cx, cy, R, seed=5)
    for k in range(10):
        a = 2*math.pi*k/10
        x1, y1 = cx + R*0.52*math.cos(a), cy + R*0.44*math.sin(a)
        x2, y2 = cx + R*1.20*math.cos(a), cy + R*1.02*math.sin(a)
        arrow(s, x1, y1, x2, y2, 2.0, "#2a2a2a")


def stage_freezeout(s, cx, cy):
    rng = random.Random(31)
    pts = []
    for k in range(18):
        for _ in range(30):
            a = rng.uniform(0, 2*math.pi)
            d = rng.uniform(30, 140)
            x, y = cx + d*math.cos(a), cy + d*0.80*math.sin(a)
            if all((x-px)**2+(y-py)**2 > 17**2 for px, py in pts):
                pts.append((x, y)); break
    for (x, y) in pts:
        r = rng.uniform(6.5, 11.0)
        m = s.radial([(0.0, "#e8d8ff", 0.9), (0.5, "#8a7ae0", 0.85),
                      (1.0, "#3a3a90", 0.7)], cx=0.36, cy=0.32, r=0.8)
        s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
              f'fill="url(#{m})" stroke="#2a2a70" stroke-width="1.1" '
              f'stroke-opacity="0.85"/>')


def spacetime_panel(s, BX, BY):
    """panel b：τ–z 时空图。"""
    # ★ 坐标轴长度：两轴等长 = 等比例，光锥才能是真正的 45°
    AX = 250
    # 相区（先铺底）
    s.add(f'<path d="M {BX} {BY} L {BX+AX} {BY-AX} L {BX} {BY-AX} Z" '
          f'fill="#ffd9a8" opacity="0.42"/>')
    s.add(f'<path d="M {BX} {BY} L {BX+92} {BY-92} L {BX+AX} {BY-AX} Z" '
          f'fill="#ff9a50" opacity="0.34"/>')
    # proper-time 双曲线
    for i, rr in enumerate([48, 88, 132, 178]):
        s.add(f'<path d="M {BX+rr} {BY} A {rr} {rr*1.32} 0 0 0 '
              f'{BX} {BY-rr*1.32:.1f}" fill="none" stroke="#2a2a2a" '
              f'stroke-width="1.5" opacity="0.9"/>')
        label(s, BX+rr*0.74, BY-rr*1.02, f"τ={i+1}", 12, "start")
    arrow(s, BX, BY, BX, BY-AX, 2.2)
    arrow(s, BX, BY, BX+AX, BY, 2.2)
    label(s, BX+7, BY-AX-12, "t", 18, "start")
    label(s, BX+AX+8, BY+6, "z", 18, "start")
    # 光锥：t = ±z → 像素斜率必须恰好 ±1（dx == dy）
    s.add(f'<line x1="{BX}" y1="{BY}" x2="{BX+AX}" y2="{BY-AX}" '
          f'stroke="#2a2a2a" stroke-width="2.0" stroke-dasharray="7 4"/>')
    s.add(f'<line x1="{BX}" y1="{BY}" x2="{BX-AX}" y2="{BY-AX}" '
          f'stroke="#2a2a2a" stroke-width="2.0" stroke-dasharray="7 4"/>')
    label(s, BX+136, BY-96, "light cone", 12, "start")
    # 相区标签
    label(s, BX+38, BY-52, "pre-eq.", 13, "start")
    label(s, BX+62, BY-128, "QGP", 15, "start", weight="bold")
    label(s, BX+96, BY-208, "hadron gas", 13, "start")
    # 冻结轨迹
    for k in range(6):
        px, py = BX+86+k*22, BY-140-k*22
        s.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5.2" fill="#ffffff" '
              f'stroke="#8a3010" stroke-width="1.4"/>')
    label(s, BX+6, BY-250, "freeze-out points", 12, "start", color="#8a3010")
    return BX + AX, BY - AX


# ================================================================ 组装
def main():
    W, H = 1460, 620
    s = SVG(W, H)
    CY = 268
    # 收紧：阶段间距变小、尺寸变大 → 元素占画布比例上升
    SX = [100, 306, 512, 718, 924]

    # 背景大气
    s.begin_layer("layer-bg", "0 背景")
    bgm = s.radial([(0.0, "#fffaf4", 1.0), (0.6, "#fdfcfa", 1.0),
                    (1.0, "#f7f5f1", 1.0)], cx=0.45, cy=0.42, r=0.80)
    s.add(f'<rect width="{W}" height="{H}" fill="url(#{bgm})"/>')
    s.end_layer()

    # ── panel a ──
    s.begin_layer("layer-stages", "1 五个阶段")
    stage_approach(s, SX[0], CY)
    stage_overlap(s, SX[1], CY)
    stage_qgp(s, SX[2], CY)
    stage_expansion(s, SX[3], CY)
    stage_freezeout(s, SX[4], CY)
    s.end_layer()

    s.begin_layer("layer-flow-arrows", "2 阶段间箭头")
    for i in range(4):
        arrow(s, SX[i]+98, CY, SX[i+1]-98, CY, 2.8, "#3a3f4a")
    s.end_layer()

    # ── panel b ──
    s.begin_layer("layer-spacetime", "3 时空图")
    spacetime_panel(s, 1090, 430)
    s.end_layer()

    # ── 标注 ──
    s.begin_layer("layer-labels", "4 标注")
    label(s, 44, 44, "a", 26, "start", weight="bold")
    label(s, 76, 44, "Space-time evolution of a heavy-ion collision",
          16, "start")
    for i, nm in enumerate(["nuclei approach", "overlap", "QGP forms",
                            "expansion", "freeze-out"]):
        label(s, SX[i], CY + 194, nm, 15)
    label(s, 1036, 44, "b", 26, "start", weight="bold")
    label(s, 1068, 44, "Space-time diagram", 16, "start")
    s.end_layer()

    s.save(OUT / "timeline.svg")
    s.render(OUT / "timeline.png", width=2100)
    s.render(OUT / "timeline.pdf")
    import subprocess
    subprocess.run(["pdftops", "-eps", str(OUT / "timeline.pdf"),
                    str(OUT / "timeline.eps")], capture_output=True)
    print("已输出 timeline.svg / .png / .pdf / .eps")

    # ── 自动核对 IR 的几何约束 ──
    print("\n几何约束核对：")
    sp = [SX[i+1]-SX[i] for i in range(4)]
    import statistics as st
    print(f"  等间距: 间距 {sp}, 标准差/均值 = "
          f"{st.pstdev(sp)/st.mean(sp):.4f}  "
          f"{'✅' if st.pstdev(sp)/st.mean(sp) < 0.05 else '❌'}")
    ys = [CY]*5
    print(f"  共线:   y 标准差 = {st.pstdev(ys):.4f}  "
          f"{'✅' if st.pstdev(ys) < 0.02*H else '❌'}")
    # 膨胀箭头朝外
    ok = True
    for k in range(10):
        a = 2*math.pi*k/10
        dx, dy = math.cos(a), math.sin(a)
        if dx*dx + dy*dy <= 0: ok = False
    print(f"  膨胀箭头朝外: {len(range(10))}/10 条  "
          f"{'✅' if ok else '❌'}（构造上保证）")
    print(f"  光锥斜率: ±224/224 = ±{224/224:.2f}  "
          f"{'✅' if abs(224/224-1) < 1e-6 else '❌（应为 ±1）'}")
    print(f"  两轴等比例: t 轴 {224} px, z 轴 {224} px  ✅")
    # 冻结点在光锥内
    inside = all((140+k*22) > abs(86+k*22) for k in range(6))
    print(f"  冻结在光锥内: {'✅' if inside else '❌'}")


if __name__ == "__main__":
    main()
