#!/usr/bin/env python3
"""
svg_lib —— 科研示意图 SVG 图元库
=========================================================================
纯 Python 标准库，零第三方依赖。用于生成期刊级 3D 示意图（含光影）。

设计原则：
  1. 零依赖 —— 保证在任何沙箱（含 ChatGPT Code Interpreter）里都能跑
  2. 图元化 —— 每个函数对应一个物理元素，而不是一个绘图操作
  3. 渐变优先 —— 立体感来自明暗过渡，不是靠描边
  4. 踩坑固化 —— 字体/tspan/锚点的坑全部在内部处理掉，调用方不用管

渲染（必须用 cairosvg，PyMuPDF 不支持 SVG 渐变，见 SVG技术验证报告.md）：
    import cairosvg
    cairosvg.svg2png(url="x.svg", write_to="x.png", output_width=2000)
    cairosvg.svg2pdf(url="x.svg", write_to="x.pdf")     # 矢量交付

用法见文件末尾 __main__ 里的示例。
"""
from __future__ import annotations

import math
from pathlib import Path

# ---------------------------------------------------------------- 字体规则
# ⚠️ cairosvg 不做字体回退，font-family 只认第一个。
#    DejaVu Sans：含希腊字母 ε η φ 和 Unicode 下标 ₁₂₃ —— 纯英文期刊图用它。
#    SimHei：含中文字形 —— 需要中文标注时换它（但它没有 Unicode 下标）。
FONT_LATIN = "DejaVu Sans"
FONT_CJK = "SimHei"


def sub(s: str, rest: str = "", base: float = 13.0) -> str:
    """
    下标 tspan 组。⚠️ 仅在 text-anchor='start' 时可靠 ——
    cairosvg 在居中文本里遇到 tspan 会算错锚点，导致后续文字串位。
    居中标签请直接用 Unicode 下标字符（DejaVu Sans 有 ₁₂₃）。
    另外：不能用 baseline-shift（被忽略），不能用百分比 font-size（解析错误）。
    """
    dy = base * 0.28
    return (f'<tspan dy="{dy:.2f}" font-size="{base * 0.7:.2f}">{s}</tspan>'
            f'<tspan dy="{-dy:.2f}">{rest}</tspan>')


def esc(s: str) -> str:
    """XML 转义。"""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------- 主类
class SVG:
    """一张 SVG 画布。所有图元方法返回 self，支持链式调用。"""

    def __init__(self, width: float, height: float, bg: str = "#ffffff"):
        self.w, self.h = float(width), float(height)
        self.bg = bg
        self._defs: list[str] = []
        self._body: list[str] = []
        self._n = 0

    # ---- 内部：注册一个 def，返回它的 id
    def _reg(self, markup: str, prefix: str) -> str:
        self._n += 1
        gid = f"{prefix}{self._n}"
        self._defs.append(markup.replace("__ID__", gid))
        return gid

    # ================================================================ 渐变
    def linear(self, stops: list[tuple[float, str, float]],
               x1=0, y1=0, x2=1, y2=0) -> str:
        """线性渐变。stops = [(offset, color, opacity), ...]"""
        s = "".join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
            for o, c, a in stops)
        return self._reg(
            f'<linearGradient id="__ID__" x1="{x1}" y1="{y1}" '
            f'x2="{x2}" y2="{y2}">{s}</linearGradient>', "lg")

    def radial(self, stops: list[tuple[float, str, float]],
               cx=0.5, cy=0.5, r=0.5) -> str:
        """径向渐变。用于球体受光、发光体。"""
        s = "".join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
            for o, c, a in stops)
        return self._reg(
            f'<radialGradient id="__ID__" cx="{cx}" cy="{cy}" r="{r}">'
            f'{s}</radialGradient>', "rg")

    # ================================================================ 滤镜
    def blur(self, std: float) -> str:
        """高斯模糊。柔光晕、边缘软化、高光条的扩散。"""
        return self._reg(
            f'<filter id="__ID__" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{std}"/></filter>', "bl")

    def shadow(self, dx=2, dy=3, std=2.5, opacity=0.30) -> str:
        """投影。让图元"浮"在纸面上。"""
        return self._reg(
            f'<filter id="__ID__" x="-40%" y="-40%" width="180%" height="180%">'
            f'<feDropShadow dx="{dx}" dy="{dy}" stdDeviation="{std}" '
            f'flood-color="#000000" flood-opacity="{opacity}"/></filter>', "sh")

    # ================================================================ 预设材质
    def mat_cylinder(self, base="#d8d8d8") -> str:
        """圆柱侧面材质：横向明暗，左中偏亮、右缘暗 —— 模拟柱面受光。"""
        return self.linear([
            (0.00, "#8a8a8a", 1), (0.10, "#c0c0c0", 1), (0.28, "#f0f0f0", 1),
            (0.40, "#ffffff", 1), (0.55, base,    1), (0.80, "#9a9a9a", 1),
            (1.00, "#6e6e6e", 1)])

    def mat_sphere(self, base="#e07b39") -> str:
        """球体材质：光源在左上，高光点偏左上。"""
        return self.radial([
            (0.00, "#ffffff", 1), (0.18, "#ffe0c0", 1), (0.45, base, 1),
            (1.00, "#000000", 0.55)], cx=0.35, cy=0.32, r=0.78)

    def mat_fireball(self) -> str:
        """火球材质：中心白热 → 橙 → 红，边缘透明。"""
        return self.radial([
            (0.00, "#fffdf0", 1.00), (0.20, "#ffe08a", 0.98),
            (0.50, "#ff9f3c", 0.92), (0.80, "#e8551f", 0.70),
            (1.00, "#c03010", 0.10)])

    def mat_glow(self, color="#ffcf5c") -> str:
        """外辉光：向外衰减到全透明。"""
        return self.radial([(0.0, color, 0.55), (1.0, color, 0.0)])

    def mat_medium(self, color="#ffcc66", a=0.45) -> str:
        """半透明介质（QGP 流体）。"""
        return self.linear([(0.0, color, a), (1.0, color, a * 0.5)], y1=0, y2=1)

    # ================================================================ 图元
    def add(self, markup: str) -> "SVG":
        self._body.append(markup)
        return self

    def cylinder(self, cx, cy, w, h, squash=0.18, base="#d8d8d8",
                 amp=0.0, waves=3, phase=0.0, highlight=True,
                 edge="#5a5a5a", label=None, label_size=12) -> "SVG":
        """
        3D 圆柱。squash 是端面椭圆的扁平度 —— 这是 3D 感的关键，
        纯正椭圆端面让平面图形立刻有透视。
        amp/waves/phase 控制侧边的正弦起伏（对应 mode-by-mode 分解）。
        """
        shade = self.mat_cylinder(base)
        cap = self.mat_sphere("#e8e8e8")
        ry = w * squash
        top, bot = cy - h / 2, cy + h / 2

        def side(sign):
            pts, N = [], 48
            for i in range(N + 1):
                t = i / N
                y = top + (bot - top) * t
                env = math.sin(math.pi * t) if amp else 0.0
                x = cx + sign * (w / 2 + amp * env *
                                 math.sin(2 * math.pi * waves * t + phase))
                pts.append((x, y))
            return pts

        # 左边必须反向遍历（底→顶），否则与右边同向会连成蝴蝶结
        rp, lp = side(+1), list(reversed(side(-1)))
        d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in rp + lp) + " Z"
        self.add(f'<path d="{d}" fill="url(#{shade})" stroke="{edge}" '
                 f'stroke-width="0.8" stroke-linejoin="round"/>')
        self.add(f'<ellipse cx="{cx}" cy="{top}" rx="{w/2}" ry="{ry}" '
                 f'fill="url(#{cap})" stroke="{edge}" stroke-width="0.8"/>')
        if highlight:
            bl = self.blur(w * 0.03)
            self.add(f'<path d="M {cx - w*0.15:.1f} {top + ry*0.6:.1f} '
                     f'L {cx - w*0.15:.1f} {bot - ry*0.5:.1f}" stroke="#ffffff" '
                     f'stroke-width="{w*0.07:.1f}" stroke-opacity="0.55" '
                     f'stroke-linecap="round" filter="url(#{bl})"/>')
        if label:
            self.text(cx, bot + ry + label_size * 1.8, label, label_size,
                      anchor="middle")
        return self

    def sphere(self, cx, cy, r, base="#e07b39", edge=None) -> "SVG":
        """受光球体。光源固定在左上，与 cylinder 一致。"""
        m = self.mat_sphere(base)
        stroke = f' stroke="{edge}" stroke-width="0.5"' if edge else ""
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" '
                 f'fill="url(#{m})"{stroke}/>')
        return self

    def ellipsoid(self, cx, cy, rx, ry, base="#ffcc66", a=0.45,
                  stroke=None, dash=None) -> "SVG":
        """半透明椭球（QGP 介质、火球外壳）。"""
        m = self.mat_medium(base, a)
        s = f' stroke="{stroke}" stroke-width="1.2"' if stroke else ""
        if dash:
            s += f' stroke-dasharray="{dash}"'
        self.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
                 f'fill="url(#{m})"{s}/>')
        return self

    def fireball(self, cx, cy, r, glow=2.0) -> "SVG":
        """发光火球：外晕 / 本体 / 内核高光 三层叠加。"""
        gm, bm = self.mat_glow(), self.mat_fireball()
        bl = self.blur(r * 0.16)
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r*glow}" '
                 f'fill="url(#{gm})" filter="url(#{bl})"/>')
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{bm})"/>')
        self.add(f'<ellipse cx="{cx - r*0.20}" cy="{cy - r*0.24}" '
                 f'rx="{r*0.32}" ry="{r*0.24}" fill="#fffdf0" '
                 f'opacity="0.78" filter="url(#{bl})"/>')
        return self

    def nucleus(self, cx, cy, r, n=14, seed=7, colors=None) -> "SVG":
        """原子核 / 核碎片：一堆小球聚成团。固定 seed 保证可复现。"""
        import random
        rng = random.Random(seed)
        colors = colors or ["#e07b39", "#c85f2a", "#f0944f", "#b34e1f"]
        hm = self.mat_glow("#ffe9c9")
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r*1.05}" '
                 f'fill="url(#{hm})" opacity="0.5"/>')
        for _ in range(n):
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(0, r * 0.70)
            px, py = cx + d * math.cos(ang), cy + d * math.sin(ang)
            rr = r * rng.uniform(0.20, 0.32)
            self.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{rr:.1f}" '
                     f'fill="{rng.choice(colors)}" stroke="#8f3d14" '
                     f'stroke-width="0.5"/>')
        return self

    def arrow(self, x1, y1, x2, y2, color="#c0392b", w=2.2,
              curve=0.16, head=True, dash=None) -> "SVG":
        """
        箭头。curve>0 向上弯、<0 向下弯、=0 直线。

        ⚠️ 箭头头部尺寸用 userSpaceOnUse 显式算，不依赖 markerUnits="strokeWidth"。
        后者会让箭头随描边宽度线性放大 —— w=16 的粗箭头会长出 16 倍的三角头
        （复现 T3-05 时踩到）。这里改成按 w 温和增长并封顶。
        """
        d = (f"M {x1} {y1} L {x2} {y2}" if curve == 0 else
             f"M {x1} {y1} Q {(x1+x2)/2} {(y1+y2)/2 - abs(x2-x1)*curve} {x2} {y2}")
        marker = ""
        if head:
            hs = max(6.0, min(w * 2.4, 20.0))     # 头部尺寸（user unit），封顶 20
            mk = self._reg(
                f'<marker id="__ID__" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerUnits="userSpaceOnUse" markerWidth="{hs:.1f}" '
                f'markerHeight="{hs:.1f}" orient="auto-start-reverse">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>', "mk")
            marker = f' marker-end="url(#{mk})"'
        ds = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" fill="none" stroke="{color}" '
                 f'stroke-width="{w}"{ds}{marker}/>')
        return self

    def axes3d(self, ox, oy, sx=70, sy=30, sz=90,
               labels=("x", "y", "z"), color="#222") -> "SVG":
        """
        3D 斜投影坐标轴：x 向右、y 向后上、z 向上。
        与 project() 的投影一致，二者配合使用。
        """
        self.arrow(ox, oy, ox + sx, oy, color=color, w=1.4, curve=0)
        self.arrow(ox, oy, ox + sy * 0.7, oy - sy, color=color, w=1.4, curve=0)
        self.arrow(ox, oy, ox, oy - sz, color=color, w=1.4, curve=0)
        for (dx, dy), lb in zip([(sx + 10, 4), (sy * 0.7 + 4, -sy - 4),
                                 (4, -sz - 8)], labels):
            self.text(ox + dx, oy + dy, lb, 13, anchor="start", color=color)
        return self

    def perspective_grid(self, cx, cy, rx, ry, rows=9, cols=9,
                         color="#888", opacity=0.45, sw=0.5) -> "SVG":
        """
        透视网格平面（反应平面、探测面）。
        用椭圆坐标做等距压缩：横线是扁椭圆弧，竖线从中心向外辐射。
        """
        for i in range(1, rows):
            t = i / rows
            rrx, rry = rx * math.sin(math.pi * t) , ry * math.sin(math.pi * t)
            yy = cy - ry * math.cos(math.pi * t)
            self.add(f'<ellipse cx="{cx}" cy="{yy}" rx="{rrx:.1f}" '
                     f'ry="{rry*0.35:.1f}" fill="none" stroke="{color}" '
                     f'stroke-width="{sw}" opacity="{opacity}"/>')
        for j in range(cols):
            a = math.pi * j / (cols - 1)
            x2, y2 = cx + rx * math.cos(a), cy + ry * 0.35 * math.sin(a)
            x1, y1 = cx - rx * math.cos(a), cy - ry * 0.35 * math.sin(a)
            self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                     f'y2="{y2:.1f}" stroke="{color}" stroke-width="{sw}" '
                     f'opacity="{opacity}"/>')
        return self

    def ring3d(self, cx, cy, R, r, tilt=0.35, n=48,
               base="#6b7fd7", opacity=0.55) -> "SVG":
        """3D 环面（探测器）。用两个同心椭圆之间的带状填充表示。"""
        outer, inner = [], []
        for i in range(n + 1):
            a = 2 * math.pi * i / n
            outer.append((cx + R * math.cos(a), cy + R * tilt * math.sin(a)))
            inner.append((cx + (R - r) * math.cos(a),
                          cy + (R - r) * tilt * math.sin(a)))
        d = ("M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in outer) +
             " L " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in reversed(inner)) +
             " Z")
        self.add(f'<path d="{d}" fill="{base}" opacity="{opacity}" '
                 f'stroke="{base}" stroke-width="1"/>')
        return self

    def track(self, x1, y1, x2, y2, bend=0.3, color="#444", w=0.9,
              opacity=0.7) -> "SVG":
        """粒子径迹：带弯曲的细线。"""
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - abs(x2 - x1) * bend
        self.add(f'<path d="M {x1} {y1} Q {mx} {my} {x2} {y2}" fill="none" '
                 f'stroke="{color}" stroke-width="{w}" opacity="{opacity}"/>')
        return self

    # ================================================================ 通用几何
    # 以下图元由复现 T3-05（CME 火球+B场）时补入：
    # 原库只覆盖了 T3-01/T3-03 用到的形状，泛化不足。
    def polygon(self, pts, fill="#eef2f6", fill_opacity=1.0,
                stroke="#b9c2cc", sw=1.0) -> "SVG":
        """任意多边形 / 透视平面。pts = [(x,y), ...]"""
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
        s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<path d="{d}" fill="{fill}" fill-opacity="{fill_opacity}"{s}/>')
        return self

    def dashed(self, pts, color="#1a1a1a", w=1.1, dash="5 4") -> "SVG":
        """折线虚线（场线、辅助线）。svg_lib.arrow 只支持单段，故单列。"""
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        self.add(f'<path d="{d}" fill="none" stroke="{color}" '
                 f'stroke-width="{w}" stroke-dasharray="{dash}" '
                 f'stroke-linecap="round"/>')
        return self

    def badge(self, cx, cy, r, label="+", bg="#d81f2a",
              fg="#ffffff") -> "SVG":
        """带符号的圆徽章（电荷 +/−、序号 ①②③）。"""
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{bg}"/>')
        lw = r * 0.30
        if label == "+":
            self.add(f'<path d="M {cx-r*0.5} {cy} L {cx+r*0.5} {cy} '
                     f'M {cx} {cy-r*0.5} L {cx} {cy+r*0.5}" stroke="{fg}" '
                     f'stroke-width="{lw:.2f}" stroke-linecap="round"/>')
        elif label == "-":
            self.add(f'<path d="M {cx-r*0.5} {cy} L {cx+r*0.5} {cy}" '
                     f'stroke="{fg}" stroke-width="{lw:.2f}" '
                     f'stroke-linecap="round"/>')
        else:
            self.text(cx, cy + r * 0.42, label, r * 1.25, anchor="middle",
                      color=fg)
        return self

    def shell(self, cx, cy, rx, ry, angle=0.0, hue="#c9a8e0",
              rim="#a884c9", opacity=0.60) -> "SVG":
        """
        半透明碗 / 壳形（带虚线开口）。用于反应平面区域、介壳、畴结构。
        不是纯椭圆：一侧饱满一侧收窄，像侧面看的碗。
        """
        a = math.radians(angle)

        def P(u, v):
            return (cx + u * math.cos(a) - v * math.sin(a),
                    cy + u * math.sin(a) + v * math.cos(a))

        pt, pb = P(0, -ry), P(0, ry)
        c1, c2 = P(rx * 1.16, -ry * 0.86), P(rx * 1.12, ry * 0.92)
        c3, c4 = P(-rx * 0.86, ry * 0.78), P(-rx * 0.92, -ry * 0.72)
        d = (f'M {pt[0]:.1f} {pt[1]:.1f} C {c1[0]:.1f} {c1[1]:.1f} '
             f'{c2[0]:.1f} {c2[1]:.1f} {pb[0]:.1f} {pb[1]:.1f} '
             f'C {c3[0]:.1f} {c3[1]:.1f} {c4[0]:.1f} {c4[1]:.1f} '
             f'{pt[0]:.1f} {pt[1]:.1f} Z')
        m = self.linear([(0.0, hue, opacity * 1.35), (0.45, hue, opacity),
                         (1.0, hue, opacity * 0.55)], x1=0, y1=0, x2=0.25, y2=1)
        self.add(f'<path d="{d}" fill="url(#{m})" stroke="{rim}" '
                 f'stroke-width="1.1"/>')
        x0, y0 = P(-rx * 0.10, 0)
        self.add(f'<ellipse cx="{x0:.1f}" cy="{y0:.1f}" rx="{rx*0.90:.1f}" '
                 f'ry="{ry*0.52:.1f}" transform="rotate({angle:.1f} '
                 f'{x0:.1f} {y0:.1f})" fill="none" stroke="{rim}" '
                 f'stroke-width="1.0" stroke-dasharray="3.5 2.5"/>')
        hi = P(-rx * 0.30, -ry * 0.42)
        hm = self.radial([(0.0, "#ffffff", 0.50), (1.0, "#ffffff", 0.0)])
        self.add(f'<ellipse cx="{hi[0]:.1f}" cy="{hi[1]:.1f}" '
                 f'rx="{rx*0.42:.1f}" ry="{ry*0.34:.1f}" '
                 f'transform="rotate({angle:.1f} {hi[0]:.1f} {hi[1]:.1f})" '
                 f'fill="url(#{hm})"/>')
        return self

    def blob(self, cx, cy, w, h, base="#e0a86a", edge="#b9813f") -> "SVG":
        """有机形状的拉长团块（火球、熔融区）。比正椭球更接近手绘观感。"""
        m = self.radial([(0.0, "#f7d9ae", 1), (0.45, base, 1),
                         (0.85, "#c98e4e", 0.95), (1.0, edge, 0.5)],
                        cx=0.46, cy=0.42, r=0.66)
        d = (f'M {cx} {cy-h/2:.1f} '
             f'C {cx+w*0.62:.1f} {cy-h*0.44:.1f} {cx+w*0.56:.1f} {cy+h*0.30:.1f} '
             f'{cx+w*0.10:.1f} {cy+h/2:.1f} '
             f'C {cx-w*0.40:.1f} {cy+h*0.58:.1f} {cx-w*0.60:.1f} {cy-h*0.20:.1f} '
             f'{cx-w*0.34:.1f} {cy-h*0.44:.1f} '
             f'C {cx-w*0.20:.1f} {cy-h*0.56:.1f} {cx-w*0.12:.1f} {cy-h/2:.1f} '
             f'{cx} {cy-h/2:.1f} Z')
        self.add(f'<path d="{d}" fill="url(#{m})" stroke="{edge}" '
                 f'stroke-width="0.9"/>')
        return self

    def axes_alternate(self, ox, oy, L=58, color="#222",
                       dirs=None) -> "SVG":
        """
        另一种 3D 坐标约定：y↑ / x→ / z↙（不少 HEP 示意图用这个）。
        svg_lib.axes3d 是 y↗ / x→ / z↑，两套别混用。
        """
        dirs = dirs or {"y": (0, -1), "x": (1, 0), "z": (-0.62, 0.78)}
        for name, (dx, dy) in dirs.items():
            x2, y2 = ox + dx * L, oy + dy * L
            self.arrow(ox, oy, x2, y2, color=color, w=1.5, curve=0)
            self.text(x2 + dx * 8 - 3, y2 + dy * 8 + 5, name, 15, color=color)
        return self

    # ================================================================ 文字
    def text(self, x, y, s, size=12, anchor="start", color="#1a1a1a",
             weight="normal", font=None) -> "SVG":
        f = font or FONT_LATIN
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" '
                 f'font-family="{f}" fill="{color}" font-weight="{weight}" '
                 f'text-anchor="{anchor}">{esc(s)}</text>')
        return self

    def title(self, x, y, s, size=17, cjk=False) -> "SVG":
        """标题。含中文时必须 cjk=True（cairosvg 不会自动回退到中文字体）。"""
        return self.text(x, y, s, size, anchor="start",
                         font=FONT_CJK if cjk else FONT_LATIN)

    # ================================================================ 分层
    # ★ 为什么需要：Nature 硬性要求可编辑矢量，且美术团队要能重排版。
    #   分层 + 命名分组 = Illustrator/Inkscape 打开后每个部件可单独选中。
    #   这是"能直接被接管"的前提，比画面好看更基础。
    def begin_layer(self, lid, label=None) -> "SVG":
        """开一个命名图层。label 会写进 inkscape:label，Inkscape 里显示为图层名。"""
        lab = label or lid
        self._body.append(
            f'<g id="{lid}" inkscape:label="{lab}" '
            f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">')
        return self

    def end_layer(self) -> "SVG":
        self._body.append("</g>")
        return self

    # ================================================================ 输出
    def tostring(self) -> str:
        defs = f"<defs>{''.join(self._defs)}</defs>" if self._defs else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {self.w:g} {self.h:g}" '
                f'width="{self.w:g}" height="{self.h:g}">\n{defs}\n'
                f'<rect width="{self.w:g}" height="{self.h:g}" '
                f'fill="{self.bg}"/>\n' + "\n".join(self._body) + "\n</svg>\n")

    def save(self, path) -> Path:
        p = Path(path)
        p.write_text(self.tostring(), encoding="utf-8")
        return p

    def render(self, path, width=None) -> Path:
        """渲染成 PNG/PDF。必须用 cairosvg —— PyMuPDF 不支持 SVG 渐变。"""
        import cairosvg
        p = Path(path)
        kw = {"bytestring": self.tostring().encode(), "write_to": str(p)}
        if p.suffix.lower() == ".pdf":
            cairosvg.svg2pdf(**kw)
        else:
            if width:
                kw["output_width"] = width
            cairosvg.svg2png(**kw)
        return p


# ================================================================ 示例
if __name__ == "__main__":
    out = Path(__file__).parent / "svg_demo"
    out.mkdir(exist_ok=True)

    # ---- 复现 T3-03 的结构：ϕ 角示意（同心环 + 火球剖面）
    s = SVG(560, 400)
    for i, R in enumerate([120, 88, 56]):
        s.ring3d(280, 200, R, 9, tilt=1.0, base="#9aa4b8",
                 opacity=0.30 + i * 0.12)
    s.fireball(280, 200, 42, glow=1.7)
    s.arrow(280, 200, 280 + 150, 200 - 60, color="#c0392b", w=1.6, curve=0)
    s.text(280 + 118, 200 - 74, "ϕ", 15)
    s.title(24, 34, "Reaction-plane geometry (T3-03 structure)")
    s.save(out / "lib_demo_phi.svg")
    s.render(out / "lib_demo_phi.png", width=1120)

    # ---- 复现 T3-01 的结构：3D 圆柱 + 火球 + 核子
    s = SVG(760, 420)
    s.title(24, 34, "QGP initial geometry (T3-01 structure)")
    s.ellipsoid(300, 240, 175, 92, stroke="#e08a2e", dash="5 4")
    s.fireball(300, 240, 48)
    for x, w_, amp, wv in [(590, 88, 7, 2), (690, 88, 5, 3)]:
        s.cylinder(x, 215, w_, 190, amp=amp, waves=wv)
    s.nucleus(105, 165, 26); s.nucleus(125, 300, 22)
    s.nucleus(470, 300, 24)
    s.arrow(360, 210, 445, 150); s.arrow(365, 258, 452, 322)
    s.save(out / "lib_demo_qgp.svg")
    s.render(out / "lib_demo_qgp.png", width=1520)

    # ---- 3D 坐标轴 + 透视网格（T3-07 结构）
    s = SVG(560, 420)
    s.title(24, 34, "Fireball with reaction plane (T3-07 structure)")
    s.perspective_grid(300, 290, 190, 95, rows=8, cols=9)
    s.fireball(300, 215, 55, glow=2.2)
    s.axes3d(150, 330, sx=90, sy=34, sz=105)
    s.nucleus(455, 150, 22)
    s.save(out / "lib_demo_axes.svg")
    s.render(out / "lib_demo_axes.png", width=1120)

    print(f"示例已输出到 {out}：")
    for f in sorted(out.glob("lib_demo_*")):
        print("  ", f.name)
