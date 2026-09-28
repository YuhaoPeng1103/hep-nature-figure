# -*- coding: utf-8 -*-
"""redraw_demo.py —— 「重画」示例：手写末态火球（v2 > 0）那一格

这是 skill 里「位图→矢量」两个终点中的**首选：重画**。和临摹的根本区别：
  · 形体是**算出来的**：火球 = 椭圆，径向箭头**尖端落在椭圆表面**，所以
    面内/面外箭头长度比自动 = 椭圆长宽比 —— 这就是 v2 的几何来源
  · 颜色是**真渐变对象**：<radialGradient> 填椭圆（objectBoundingBox 单位，
    自动被拉成椭圆），不是几万条纯色小格
  · 物理量是**参数**：V2 一行就同时决定了火球多扁、箭头多各向异性
    —— 这在临摹版里做不到（改形状要删掉一堆小格）

跑：python gen/redraw_demo.py
出：out/redraw_fireball.svg / .png
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(Path(r"C:\Users\HUAWEI\.codex\skills\hep-nature-figure\scripts")))
from svg_lib import SVG   # noqa: E402

W, H = 624, 350
CX, CY = 300, 180
R0 = 150.0               # 平均半径
V2 = 0.216               # ★ v2 就写在这里：椭率 = RX/RY = (1+V2)/(1-V2) = 1.55
RX, RY = R0 * (1 + V2), R0 * (1 - V2)
NCORE = 0.23
NARR = 24
INK = "#3a3f4a"

s = SVG(W, H, bg="#ffffff")

# ---------- 图层 1：横向平面薄板（有厚度、带透视）----------
s.begin_layer("plate-B", "横向平面薄板 B")
face = s.linear([(0.0, "#f4f6f8", 1.0), (0.55, "#eef1f4", 1.0), (1.0, "#e2e7ec", 1.0)],
                x1=0, y1=0, x2=1, y2=0.35)
s.add('<polygon points="30,30 590,8 590,300 30,322" fill="url(#%s)"/>' % face)
s.add('<polygon points="590,8 604,14 604,306 590,300" fill="#d8dde3"/>')
s.add('<polygon points="30,30 30,24 604,8 604,14" fill="#fbfcfd"/>')
s.end_layer()

# ---------- 图层 2：火球（真 radialGradient + 椭圆）----------
s.begin_layer("fireball-final", "末态火球（真 radialGradient）")
g = s.radial([(0.00, "#fffbe8", 1.0), (0.22, "#ffe08a", 1.0),
              (0.48, "#ffab3c", 1.0), (0.74, "#ea5c22", 1.0),
              (0.93, "#cc3a12", 1.0), (1.00, "#b93310", 1.0)])
s.add('<ellipse cx="%d" cy="%d" rx="%.1f" ry="%.1f" fill="url(#%s)"/>' % (CX, CY, RX, RY, g))
gc = s.radial([(0.0, "#ffffff", 0.95), (0.45, "#ffeaa0", 0.55), (1.0, "#ffd257", 0.0)])
s.add('<ellipse cx="%d" cy="%d" rx="%.0f" ry="%.0f" fill="url(#%s)"/>'
      % (CX, CY, RX * NCORE * 2.2, RY * NCORE * 2.2, gc))
s.end_layer()

# ---------- 图层 3：方向参考虚线（面内 / 面外）----------
s.begin_layer("lines", "面内/面外方向虚线")
s.add('<line x1="150" y1="%d" x2="600" y2="%d" stroke="#8d949e" stroke-width="1.4"'
      ' stroke-dasharray="7 6"/>' % (CY, CY))
s.add('<line x1="%d" y1="42" x2="%d" y2="318" stroke="#8d949e" stroke-width="1.4"'
      ' stroke-dasharray="7 6"/>' % (CX, CX))
s.end_layer()

# ---------- 图层 4：径向流箭头（尖端落在火球表面 ⇒ 长宽比 = RX/RY = v2 的几何）----------
s.begin_layer("radial-arrows", "径向流箭头（尖端落在火球表面）")
L_in = L_out = 0.0
for i in range(NARR):
    t = 2 * math.pi * i / NARR
    ux, uy = math.cos(t), math.sin(t)
    f0, f1 = 0.30, 0.93
    x0, y0 = CX + RX * f0 * ux, CY + RY * f0 * uy
    x1, y1 = CX + RX * f1 * ux, CY + RY * f1 * uy
    ln = math.hypot(x1 - x0, y1 - y0)
    if abs(uy) < 1e-9:
        L_in = ln
    if abs(ux) < 1e-9:
        L_out = ln
    s.arrow(x0, y0, x1, y1, color=INK, w=1.5, curve=0.0)
s.end_layer()

# ---------- 图层 5：phi 参考箭头 + 角弧 ----------
s.begin_layer("phi-arrow", "方位角 phi 的参考箭头")
ang = math.radians(25)
s.arrow(CX + RX * 0.66, CY + RY * 0.30,
        CX + RX * 1.12 * math.cos(ang), CY - RY * 1.30 * math.sin(ang),
        color="#4b5563", w=2.6, curve=0.0)
s.add('<path d="M %.0f %d A 92 92 0 0 0 %.1f %.1f" fill="none" stroke="#4b5563"'
      ' stroke-width="1.2"/>' % (CX + 92, CY, CX + 92 * math.cos(ang), CY - 92 * math.sin(ang)))
s.end_layer()

# ---------- 图层 6：文字 ----------
s.begin_layer("text", "文字")
s.text(380, 62, "v", size=17)
s.add('<text x="389" y="69" font-size="11" font-family="DejaVu Sans">2</text>')
s.text(397, 62, "= \u27e8cos 2\u03c6\u27e9 > 0", size=17)
s.text(508, 212, "in-plane", size=15)
s.text(206, 44, "out-of-plane", size=15)
s.text(447, 150, "\u03c6", size=17)
s.end_layer()

s.save(HERE.parent / "out" / "redraw_fireball.svg")
s.render(HERE.parent / "out" / "redraw_fireball.png", width=1248)
print("V2 = %.3f -> RX/RY = %.2f" % (V2, RX / RY))
print("面内箭头 %.1f px | 面外箭头 %.1f px | 比 = %.2f（= 椭圆长宽比，由 V2 算出）"
      % (L_in, L_out, L_in / L_out))
print("写出 out/redraw_fireball.svg / .png")
