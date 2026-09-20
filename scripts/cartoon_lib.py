#!/usr/bin/env python3
"""
cartoon_lib —— 卡通示意图图元库（「草图 → 卡通图」这条线的图元层）
=========================================================================
和 svg_lib 的分工：

  svg_lib     —— 通用 SVG 能力 + 复现期刊图用的图元（圆柱/环/透视网格…）
  cartoon_lib —— **物理语义图元**：喷注、胶子辐射、介质尾迹、Lorentz 核、
                  硬散射顶点、火球、粒子云……每个对应一个物理对象，
                  默认值按期刊插画校准。

## 为什么要有这个库

原来「草图 → 卡通图」不是一条流程，是三次一次性劳动：
三个脚本各写 250–300 行，`label` 写了 3 遍、`lorentz_nucleus` 2 遍、
QGP 团块 2 遍（约 85% 逐行相同）。同一个物理概念（冷色核）在两份脚本里
用了**两套不同的蓝**——这正是单一图元库本该消灭的漂移。

## 默认值从哪来

**从真实期刊图，不是拍脑袋。** 看了库里 T3 精选的 8 张（STAR Nature 2024、
Kharzeev Nat Rev Phys 等）：

  · 核是**带网格线的 3D 球**，不是平涂色块 → 线框产生大量边
  · 火球内部有**放射状/斑块纹理**，不是均匀渐变
  · **灰色衬板 + 投影**提供中间调
  · **粗黑箭头**连接各阶段，标签是粗体黑字

这解释了为什么原来的产出被门禁判「太淡太空」
（dark_ratio 低 69–91%、edge_density 低 53–57%）：
它们没有线框、没有内部纹理、没有衬板、描边太浅。

⚠️ 纪律 3 提醒：这些默认值是**诊断出来的修正**，不是"调指标"。
   改完必须看图确认，不许"指标匹配就收工"。

## 用法

    from cartoon_lib import Cartoon
    c = Cartoon(1020, 640)
    c.qgp_blob(450, 320, 160)
    c.lorentz_nucleus(260, 320, 26, 96, shift=62)
    c.jet(470, 300, 780, 180, w0=7, w1=5.6)
    c.save("fig.svg")

    # 或按注册名调用（IR 的 primitive 字段用这些 key）
    from cartoon_lib import PRIMITIVES
    PRIMITIVES["qgp_blob"](c, 450, 320, 160)
"""
from __future__ import annotations

import math
import random

import geom
import svg_lib
from svg_lib import SVG

# ══════════════════════════════════════════════════════════════
#  调色板 —— 每个物理概念只有一套色，消灭"两套蓝"
# ══════════════════════════════════════════════════════════════
INK = "#0d0d0d"           # 文字与主要描边
INK_SOFT = "#2a2a2a"      # 次级线与箭头
OUTLINE = "#0a0f3a"       # 深色描边（实测：通过门禁的那张图用的就是这个量级）

PALETTE = {
    # 冷色核（入射核 / 靶核）—— 统一成一套蓝
    "nucleus":   ["#c8d6fa", "#7a90e0", "#4254b0"],
    "nucleus_edge": "#1e2a70",
    "nucleus_stripe": "#4a5cb8",
    # QGP 火球 / 介质 —— 热色
    "qgp":       ["#ffc060", "#f86818", "#dc3808", "#b82000"],
    "qgp_edge":  "#8a3010",
    "qgp_hot":   "#ffd070",
    "qgp_cold":  "#a82800",
    # 强子 / 冻结散点
    "hadron":    ["#e8d8ff", "#8a7ae0", "#3a3a90"],
    "hadron_edge": "#2a2a70",
    # 硬散射顶点
    "vertex":    "#5a3608",
    "vertex_core": "#fff8dc",
}

# 默认描边宽度。实测：原来 1.5–1.9 太浅，参考图在 2–2.6
LW = 2.2
LW_THIN = 1.1

# ══════════════════════════════════════════════════════════════
#  ★★ 全局光照模型 —— 所有高光/投影/明暗都从这一个光源推导
#
#  为什么需要（实测，这是"平面感"的真正根源）：
#    改之前每个材质各自写死一个高光中心：
#      svg_lib:173      (0.35, 0.32)
#      svg_lib:448      (0.46, 0.42)
#      cartoon_lib:156  (0.34, 0.30)
#      cartoon_lib:230  (0.40, 0.34)
#      cartoon_lib:641  (0.36, 0.32)
#    **五个数字五个方向** —— 同一张图里的元素根本不在同一个光照环境里。
#    所以看着"平"、看着"贴纸感"，不是画得不够细，是**没有统一的光**。
#
#  老师要的"三维中的阴影感"，缺的正是这一层：不是没有渐变，
#  是渐变之间没有共同的光源逻辑。
#
#  ⚠️ 纪律 3：这是**诊断出来的结构性修正**（五个不一致的数 → 一个光源），
#     不是"调指标"。改完必须看图确认。
# ══════════════════════════════════════════════════════════════

# 光从哪个方位来（度）。0 = 正右方，逆时针；90 = 正上方。128 ≈ 左上偏上。
LIGHT_AZIMUTH = 128.0
# 光从纸面抬起多高（度）。0 = 贴着纸面（投影无限长），90 = 正上方（无投影）。
LIGHT_ELEVATION = 38.0

# 高光偏离球心的幅度（objectBoundingBox 单位）。全库统一，不许各自改。
SPECULAR_OFFSET = 0.35


def light_vec():
    """
    → 单位光向量 (lx, ly, lz)。
    屏幕坐标 y 向下，所以 ly < 0 表示光从**上方**来。
    lz 是"从纸面抬起的程度"，决定投影长度和高光锐度。
    """
    a = math.radians(LIGHT_AZIMUTH)
    e = math.radians(LIGHT_ELEVATION)
    lx = math.cos(a) * math.cos(e)
    ly = -math.sin(a) * math.cos(e)
    lz = math.sin(e)
    n = math.sqrt(lx * lx + ly * ly + lz * lz) or 1.0
    return lx / n, ly / n, lz / n


def shade_center(k=SPECULAR_OFFSET):
    """
    → radialGradient 的高光中心 (cx, cy) ∈ [0,1]（objectBoundingBox）。
    所有球体/椭球的材质都用它，保证同一张图里高光方向一致。
    """
    lx, ly, _ = light_vec()
    return 0.5 + lx * k, 0.5 + ly * k


def shadow_dir():
    """
    → 影子的**单位方向**（屏幕上从物体指向影子落点）。

    ★ 符号：`light_vec()` 给的是光**从**哪个方向来（左上 → lx,ly 都为负）。
      影子要投在光**去的**那一侧，也就是**反方向**（右下）→ 取负号。
      实测抓到的错：第一版没取负，影子投到了光源那一侧 ——
      看着像"光从右下打过来"，和所有高光方向自相矛盾。
    """
    lx, ly, _ = light_vec()
    n = math.hypot(lx, ly) or 1.0
    return -lx / n, -ly / n


def shadow_dir_px(height=1.0, size=100.0):
    """
    → 影子的**像素偏移** (dx, dy)。
    `height` 是物体离衬板的高度（相对自身尺寸），`size` 是物体半径（像素）。
    光越低（LIGHT_ELEVATION 小）影子拉得越长。

    ★ 为什么拆成 dir + len：原来 `shadow_vec` 返回无量纲比值，
      却被当成像素用（translate(0.195, 0.25)）—— 影子小到看不见。
      影子长度必须**跟着物体尺寸走**。
    """
    lx, ly, lz = light_vec()
    ux, uy = shadow_dir()
    # ★ 因子实测标定：第一版 0.55 让半径 87px 的火球影子偏了 70px
    #   （自身半径的 80%），看着像一块独立的脏印子而不是影子。
    #   贴地感约在自身半径的 12–20%。
    L = height * size * (1.0 / max(lz, 0.12)) * 0.16
    return ux * L, uy * L


def _hex_mix(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    return "#" + "".join(
        f"{int(int(a[i:i+2], 16) * (1 - t) + int(b[i:i+2], 16) * t):02x}"
        for i in (0, 2, 4))


def _shade(hexcol, k):
    """按比例提亮/压暗一个颜色（k>1 提亮，k<1 压暗）。"""
    h = hexcol.lstrip("#")
    return "#" + "".join(
        f"{max(0, min(255, int(int(h[i:i+2], 16) * k))):02x}" for i in (0, 2, 4))


class Cartoon(SVG):
    """
    带卡通图元的画布。继承 SVG，所以 svg_lib 的全部方法都能直接用。

    ★ 所有图元都接受**画布归一化坐标**的可选写法：传 fx/fy ∈ [0,1] 时
      按画布尺寸换算。IR 里的坐标应当用归一化值（见 ir-spec.md）。
    """

    # ---------------------------------------------------------- 坐标换算
    def px(self, fx, fy):
        """归一化坐标 → 像素坐标。"""
        return fx * self.w, fy * self.h

    @property
    def unit(self):
        """一个"图元尺度"单位 = 画布短边的 1/100。用于让尺寸随手画布缩放。"""
        return min(self.w, self.h) / 100.0

    # ---------------------------------------------------------- 文字
    def label(self, x, y, t, size=15, anchor="middle",
              color=INK, weight="", cjk=None) -> "Cartoon":
        """
        统一标注。**转调 svg_lib.text**，顺带拿到两件原来三份 label 都没有的东西：
          ① XML 转义（原来的 label 不转义，标签里有 & 或 < 会产出非法 SVG）
          ② 中文字体支持（原来三份都写死 DejaVu Sans → 中文静默变豆腐块，
             而"防中文豆腐块"恰好是 svg_lib 存在的理由之一）
        cjk=None 时自动判断：含中日韩字符就走中文字体。
        """
        if cjk is None:
            cjk = any("　" <= ch <= "鿿" or "＀" <= ch <= "￯"
                      for ch in t)
        self.text(x, y, t, size=size, anchor=anchor, color=color,
                  weight=weight or "normal",
                  font=svg_lib.FONT_CJK if cjk else svg_lib.FONT_LATIN)
        return self

    # ---------------------------------------------------------- 球
    def shaded_sphere(self, cx, cy, r, base=None, wire=False, edge_w=None,
                      n_lon=5, n_lat=4) -> "Cartoon":
        """
        受光球（按 base 色算明暗，不混黑 → 比 mat_sphere 干净）。

        wire=True 时叠加**线框**（经线 + 纬线）——这是从期刊图学到的：
        STAR 那张的核是带网格的球，线框是 edge_density 的主要来源之一。

        `base` 省略时用调色板的核色（与 nucleus_cluster 一致）。
        ★ 原来 base 是必填，而兄弟图元都有默认值 —— 生成骨架时漏传就崩，
          与"图元应该能独立调用"的用法不符。
        """
        base = base or PALETTE["nucleus"][1]
        hx, hy = shade_center()          # ★ 从全局光推导，不再写死
        m = self.radial([(0.00, "#ffffff", 0.95),
                         (0.22, _shade(base, 1.35), 1.0),
                         (0.60, base, 1.0),
                         (1.00, _shade(base, 0.55), 1.0)],
                        cx=hx, cy=hy, r=0.80)
        ew = edge_w if edge_w is not None else max(0.6, r * 0.085)
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                 f'fill="url(#{m})" stroke="{OUTLINE}" '
                 f'stroke-width="{ew:.2f}" stroke-opacity="0.85"/>')
        if wire and r > 4:
            pts_lat = [(cx, cy, r, 1.0)]
            # 纬线（横椭圆）
            for i in range(1, n_lat + 1):
                f = i / (n_lat + 1)
                yy = cy - r + 2 * r * f
                rr = r * math.sqrt(max(0.0, 1 - (2 * f - 1) ** 2))
                if rr < 0.6:
                    continue
                self.add(f'<ellipse cx="{cx:.1f}" cy="{yy:.1f}" rx="{rr:.1f}" '
                         f'ry="{rr * 0.26:.1f}" fill="none" '
                         f'stroke="{_shade(base, 0.55)}" '
                         f'stroke-width="{max(0.4, r * 0.03):.2f}" '
                         f'opacity="0.55"/>')
            # 经线（竖椭圆）
            for i in range(n_lon):
                a = math.pi * i / n_lon
                rx = abs(r * math.cos(a))
                if rx < 0.6:
                    continue
                self.add(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
                         f'ry="{r:.1f}" fill="none" '
                         f'stroke="{_shade(base, 0.55)}" '
                         f'stroke-width="{max(0.4, r * 0.03):.2f}" '
                         f'opacity="0.45"/>')
        return self

    def nucleus_cluster(self, cx, cy, R, base=None, seed=1, n=20,
                        wire=False) -> "Cartoon":
        """
        核子聚团：小球按**黄金角螺旋**堆在核体积内（比纯随机少空洞），
        外圈一圈弥散壳。

        和 lorentz_nucleus 的区别（**唯一不能合并的一对**）：
        这个是"有体积的球簇"，对应静止/靶核；
        那个是"压扁带条纹的椭圆"，对应束流方向上的 Lorentz 收缩核。
        """
        base = base or PALETTE["nucleus"][1]
        rng = random.Random(seed)
        shell = self.radial([(0.0, base, 0.30), (1.0, base, 0.0)])
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R*1.18:.1f}" '
                 f'fill="url(#{shell})"/>')
        pts = []
        for i in range(n):
            a = i * 2.399963                       # 黄金角
            rr = R * 0.80 * math.sqrt((i + 0.5) / n)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a),
                        R * rng.uniform(0.16, 0.22)))
        for (x, y, r) in pts:                      # 画序 = z 序：后画的在上
            self.shaded_sphere(x, y, r, base, wire=wire)
        return self

    # ---------------------------------------------------------- 核
    def lorentz_nucleus(self, cx, cy, rx, ry, shift=0.0, sep=0.22,
                        n_stripes=4, wire=False, angle=0.0) -> "Cartoon":
        """
        Lorentz 收缩核：竖直扁椭圆 + 渐变 + 深描边 + 内部横向条纹
        （条纹暗示被压扁的核物质）。

        ★ 合并自两份实现（s3 的 7 条纹/0.22 间距 + s4 的 9 条纹/0.19 间距），
          `sep` 与 `n_stripes` 参数化。

        ★ 修了一个真 bug：原 s4 版 `for dx in (-shift, shift)` 在 shift=0 时
          两个 dx 都是 0.0，**同一个椭圆被画两遍**（互为叠影）。
          这里改成 shift=0 时只画一次。
        """
        hx, hy = shade_center()          # ★ 全局光
        m = self.radial([(0.0, PALETTE["nucleus"][0], 0.95),
                         (0.45, PALETTE["nucleus"][1], 0.92),
                         (1.0, PALETTE["nucleus"][2], 0.88)],
                        cx=hx, cy=hy, r=0.80)
        # shift=0 时只画一个，不要画两遍
        dxs = [0.0] if abs(shift) < 1e-9 else [-shift, shift]
        # ★ 整体旋转：形变核的**长轴取向**是物理量（决定碰撞重叠区），
        #   不能只会画轴对齐的椭圆。实测由一张新草图暴露：
        #   要表达"量子涨落 → 取向不定"，必须能画不同倾角的椭球。
        #   用 <g transform> 包住全部图元，而不是给每个坐标手算旋转。
        if abs(angle) > 1e-9:
            self.add(f'<g transform="rotate({angle:.2f} {cx:.1f} {cy:.1f})">')
        for dx in dxs:
            self.add(f'<ellipse cx="{cx+dx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
                     f'ry="{ry:.1f}" fill="url(#{m})" '
                     f'stroke="{PALETTE["nucleus_edge"]}" '
                     f'stroke-width="{LW*0.85:.2f}" stroke-opacity="0.95"/>')
            for i in range(-n_stripes, n_stripes + 1):
                yy = cy + i * ry * sep
                hw = rx * 0.70 * math.sqrt(max(0.02, 1 - (i * sep) ** 2))
                self.add(f'<line x1="{cx+dx-hw:.1f}" y1="{yy:.1f}" '
                         f'x2="{cx+dx+hw:.1f}" y2="{yy:.1f}" '
                         f'stroke="{PALETTE["nucleus_stripe"]}" '
                         f'stroke-width="1.0" opacity="0.5"/>')
        if wire:
            for dx in dxs:
                for i in range(-2, 3):
                    if i == 0:
                        continue
                    rx2 = rx * abs(math.cos(i * 0.32))
                    self.add(f'<ellipse cx="{cx+dx:.1f}" cy="{cy:.1f}" '
                             f'rx="{rx2:.1f}" ry="{ry:.1f}" fill="none" '
                             f'stroke="{PALETTE["nucleus_edge"]}" '
                             f'stroke-width="0.5" opacity="0.3"/>')
        if abs(angle) > 1e-9:
            self.add('</g>')
        return self

    # ---------------------------------------------------------- QGP
    def qgp_blob(self, cx, cy, R, ry=0.78, seed=3, glow=1.0, n_spots=11,
                 wobble=0.12, edge_w=None, spots=True) -> "Cartoon":
        """
        QGP 介质团块：有机边界 + 暖色渐变 + **内部密度斑** + 深色边界。

        ★ 合并自 qgp_medium（s3）与 qgp_blob（s4）——两份约 85% 逐行相同，
          只差 6 个数字。这里全部参数化：ry / n_spots / glow / wobble / edge_w。

        ★ 内部密度斑是**从期刊图学的**：参考图里介质内部有热区冷区的起伏，
          不是均匀渐变。这一层直接贡献 edge_density，也是"有体积感"的来源。
        """
        rng = random.Random(seed)
        b = geom.blob(cx, cy, R, R * ry, wobble=wobble, n=72, seed=seed)
        d = geom.poly_to_path(b)
        P = PALETTE["qgp"]

        # ① 外层弥散
        g0 = self.radial([(0.0, "#ff9a40", 0.40 * glow),
                          (0.6, P[2], 0.22 * glow), (1.0, P[3], 0.0)])
        self.add(f'<path d="{d}" fill="url(#{g0})" '
                 f'filter="url(#{self.blur(R*0.20)})"/>')
        # ② 主体
        g1 = self.radial([(0.0, P[0], 0.90), (0.42, P[1], 0.84),
                          (0.76, P[2], 0.66), (1.0, P[3], 0.0)])
        self.add(f'<path d="{d}" fill="url(#{g1})" '
                 f'filter="url(#{self.blur(R*0.09)})"/>')
        # ③ 内部密度斑（热区偏亮黄、冷区偏暗红）
        if spots:
            clip = self._reg(f'<clipPath id="__ID__"><path d="{d}"/></clipPath>',
                             "cp")
            for _ in range(n_spots):
                a = rng.uniform(0, 2 * math.pi)
                rr = math.sqrt(rng.uniform(0, 1)) * R * 0.80
                px_, py_ = cx + rr * math.cos(a), cy + rr * math.sin(a) * ry
                sz = R * rng.uniform(0.22, 0.46)
                col = PALETTE["qgp_hot"] if rng.random() < 0.55 \
                    else PALETTE["qgp_cold"]
                op = rng.uniform(0.20, 0.40)
                mm = self.radial([(0.0, col, op), (0.55, col, op * 0.42),
                                  (1.0, col, 0.0)])
                self.add(f'<ellipse cx="{px_:.1f}" cy="{py_:.1f}" rx="{sz:.1f}" '
                         f'ry="{sz*0.74:.1f}" fill="url(#{mm})" '
                         f'filter="url(#{self.blur(sz*0.42)})" '
                         f'clip-path="url(#{clip})"/>')
        # ④ 边界（可辨的深色线 —— 实测基准要求）
        ew = edge_w if edge_w is not None else LW * 0.9
        self.add(f'<path d="{d}" fill="none" stroke="{PALETTE["qgp_edge"]}" '
                 f'stroke-width="{ew:.2f}" stroke-opacity="0.78"/>')
        return b

    def qgp_fireball(self, cx, cy, r, vortices=5, ring=True,
                     glow=True) -> "Cartoon":
        """
        QGP 火球（发光体）：弥散外晕 + 亮核 + 边缘环 + 内部涡旋。

        和 qgp_blob 的区别：这是**发光体**（正圆、有辉光），
        那个是**介质块**（不规则边界、有密度斑）。两者视觉语言不同，不合并。

        内部涡旋统一用**等角度分布**——原来用随机角度+随机大小，
        看着像渲染故障；改成规整图案才读得出是"集体运动"。
        """
        if glow:
            gl = self.mat_glow("#ff8c42")
            self.add(f'<circle cx="{cx}" cy="{cy}" r="{r*2.05:.1f}" '
                     f'fill="url(#{gl})" opacity="0.45" '
                     f'filter="url(#{self.blur(r*0.42)})"/>')
        core = self.radial([(0.00, "#fffaf0", 1.0), (0.20, "#ffd9a0", 0.98),
                            (0.48, "#fca25c", 0.92), (0.76, "#f06a28", 0.72),
                            (1.00, "#d84010", 0.0)])
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="url(#{core})" '
                 f'filter="url(#{self.blur(r*0.42)})"/>')
        if ring:      # 明确的边缘环：发光体要有可辨边界
            self.add(f'<circle cx="{cx}" cy="{cy}" r="{r*0.70:.1f}" fill="none" '
                     f'stroke="#c8501a" stroke-width="{r*0.055:.2f}" '
                     f'stroke-opacity="0.60"/>')
        for i in range(vortices):
            a = 180.0 * i / vortices          # 等角分布
            off = r * 0.24
            ox = off * math.cos(math.radians(a + 90))
            oy = off * math.sin(math.radians(a + 90))
            self.add(f'<ellipse cx="{cx+ox:.1f}" cy="{cy+oy:.1f}" '
                     f'rx="{r*0.50:.1f}" ry="{r*0.42:.1f}" '
                     f'transform="rotate({a:.0f} {cx+ox:.1f} {cy+oy:.1f})" '
                     f'fill="none" stroke="#fff4e0" '
                     f'stroke-width="{r*0.052:.2f}" opacity="0.62"/>')
        return self

    # ---------------------------------------------------------- 喷注
    def hard_vertex(self, x, y, r=22, n=11) -> "Cartoon":
        """硬散射顶点：星芒（长短交替的放射线 + 核心亮点）。"""
        gl = self.mat_glow("#fff0b0")
        self.add(f'<circle cx="{x}" cy="{y}" r="{r*2.1}" fill="url(#{gl})" '
                 f'opacity="0.75"/>')
        for i in range(n):
            a = 2 * math.pi * i / n + 0.14
            L = r * (1.0 if i % 2 == 0 else 0.68)
            self.add(f'<line x1="{x}" y1="{y}" x2="{x+L*math.cos(a):.1f}" '
                     f'y2="{y+L*math.sin(a):.1f}" stroke="{PALETTE["vertex"]}" '
                     f'stroke-width="2.6" stroke-linecap="round" '
                     f'opacity="0.95"/>')
        self.add(f'<circle cx="{x}" cy="{y}" r="{r*0.30:.1f}" '
                 f'fill="{PALETTE["vertex_core"]}" '
                 f'stroke="{PALETTE["vertex"]}" stroke-width="1.2"/>')
        return self

    def jet(self, x0, y0, x1, y1, w0=7.0, w1=5.6, c0="#ffd24a",
            c1="#c96a10", cone=True, cone_len=None) -> "Cartoon":
        """
        渐细喷注。**三层结构**：
          ① 外围发散晕（宽、淡）——喷注是一束，不是一根线
          ② 主体（渐细、渐暗）——能量损失靠"越走越暗"表达
          ③ 准直核心（细、亮，只到 70% 处衰减）——硬核心

        ★ 修正了一个画布魔数：原来锥形长度写死 52px，换画布就不成比例。
          现在默认按 `unit`（画布短边 1/100）缩放。
        """
        K = 30
        bl = self.blur(w0 * 0.95)
        self.add(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" '
                 f'y2="{y1:.1f}" stroke="{c0}" '
                 f'stroke-width="{w0*3.1:.1f}" stroke-opacity="0.22" '
                 f'stroke-linecap="round" filter="url(#{bl})"/>')
        for i in range(K):
            t = i / K
            ax, ay = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            bx, by = x0 + (x1-x0)*(t+1/K), y0 + (y1-y0)*(t+1/K)
            self.add(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" '
                     f'y2="{by:.1f}" stroke="{_hex_mix(c0, c1, t)}" '
                     f'stroke-width="{w0+(w1-w0)*t:.2f}" '
                     f'stroke-linecap="round"/>')
        for i in range(K):
            t = i / K
            if t > 0.72:
                break
            k = 1 - t / 0.72
            ax, ay = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            bx, by = x0 + (x1-x0)*(t+1/K), y0 + (y1-y0)*(t+1/K)
            self.add(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" '
                     f'y2="{by:.1f}" stroke="#fffbe8" '
                     f'stroke-width="{w0*0.30*(0.4+0.6*k):.2f}" '
                     f'stroke-opacity="{0.85*k:.2f}" stroke-linecap="round"/>')
        if cone:
            ang = math.atan2(y1-y0, x1-x0)
            px_, py_ = -math.sin(ang), math.cos(ang)
            L = cone_len if cone_len is not None else self.unit * 5.2
            sp = w1 * 5.8
            self.add(f'<path d="M {x1:.1f} {y1:.1f} '
                     f'L {x1-L*math.cos(ang)+px_*sp:.1f} '
                     f'{y1-L*math.sin(ang)+py_*sp:.1f} '
                     f'L {x1-L*math.cos(ang)-px_*sp:.1f} '
                     f'{y1-L*math.sin(ang)-py_*sp:.1f} Z" '
                     f'fill="{c1}" opacity="0.26"/>')
        return self

    def gluon_radiation(self, x0, y0, x1, y1, n=5, seed=3,
                        spread=(38, 72), amp=4.6) -> "Cartoon":
        """胶子辐射：沿喷注路径向外发出的螺旋（弹簧线）。"""
        rng = random.Random(seed)
        ang = math.atan2(y1-y0, x1-x0)
        for i in range(n):
            t = 0.18 + 0.72 * (i / max(1, n - 1))
            bx, by = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            for sgn in (-1, 1):
                if rng.random() < 0.32:
                    continue
                aa = ang + math.radians(rng.uniform(*spread)) * sgn
                L = self.unit * rng.uniform(3.0, 5.2)
                ex, ey = bx + L*math.cos(aa), by + L*math.sin(aa)
                K = 34
                pts = []
                for k in range(K + 1):
                    u = k / K
                    mx, my = bx + (ex-bx)*u, by + (ey-by)*u
                    off = math.sin(u * 3.2 * 2*math.pi) * amp * (1 - u*0.4)
                    pts.append((mx - math.sin(aa)*off, my + math.cos(aa)*off))
                d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
                self.add(f'<path d="{d}" fill="none" stroke="#8a4a18" '
                         f'stroke-width="1.8" opacity="{0.92 - 0.08*i:.2f}"/>')
        return self

    def medium_wake(self, x0, y0, x1, y1, n=4, r0=26, dr=20) -> "Cartoon":
        """
        介质尾迹：路径旁的弧形波纹（激波 / 马赫锥）。
        ★ 原实现把半径写死成 `26 + 20*i`，换画布就和介质脱钩；
          现在按 `unit` 缩放。
        """
        ang = math.atan2(y1-y0, x1-x0)
        u = self.unit
        for i in range(n):
            t = 0.30 + 0.16 * i
            bx, by = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            rr = (r0 + dr * i) * u / 5.0
            for sgn in (-1, 1):
                a0 = ang + sgn * math.radians(52)
                a1 = ang + sgn * math.radians(108)
                xa, ya = bx + rr*math.cos(a0), by + rr*math.sin(a0)
                xb, yb = bx + rr*math.cos(a1), by + rr*math.sin(a1)
                self.add(f'<path d="M {xa:.1f} {ya:.1f} '
                         f'A {rr:.1f} {rr:.1f} 0 0 {1 if sgn>0 else 0} '
                         f'{xb:.1f} {yb:.1f}" fill="none" stroke="#ffffff" '
                         f'stroke-width="2.6" opacity="{0.40 - 0.05*i:.2f}" '
                         f'stroke-linecap="round"/>')
        return self

    # ---------------------------------------------------------- 箭头
    def arrow(self, x1, y1, x2, y2, w=LW, c=INK_SOFT,
              head=None) -> "Cartoon":
        """直线箭头。`head` 是箭头三角的边长，默认随线宽。"""
        ang = math.atan2(y2 - y1, x2 - x1)
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                 f'y2="{y2:.1f}" stroke="{c}" stroke-width="{w:.2f}" '
                 f'stroke-linecap="round"/>')
        L = head if head is not None else w * 5.2
        px_, py_ = -math.sin(ang), math.cos(ang)
        self.add(f'<path d="M {x2:.1f} {y2:.1f} '
                 f'L {x2-L*math.cos(ang)+px_*L*0.5:.1f} '
                 f'{y2-L*math.sin(ang)+py_*L*0.5:.1f} '
                 f'L {x2-L*math.cos(ang)-px_*L*0.5:.1f} '
                 f'{y2-L*math.sin(ang)-py_*L*0.5:.1f} Z" fill="{c}"/>')
        return self

    def tapered_arrow(self, x1, y1, x2, y2, w=3.0, color=INK_SOFT,
                      curve=0.0, head_frac=0.30) -> "Cartoon":
        """
        渐细箭头（插画感，比直线箭头更适合"阶段演化"）。

        ⚠️ 不能用 linearGradient 描边：水平线的包围盒高度为 0，
           渐变退化 → 箭杆完全不渲染（只剩箭头）。实测踩过。
        ★ 原实现的箭头长 = 箭杆长的 30%，导致短线小头、长线巨头。
          现在由 `head_frac` 控制并默认限制在一个下限以上。
        """
        ang = math.atan2(y2 - y1, x2 - x1)
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if curve:
            nx, ny = -math.sin(ang) * curve, math.cos(ang) * curve
            mx, my = mx + nx, my + ny
        shaft = math.hypot(x2 - x1, y2 - y1)
        hf = max(head_frac, self.unit * 1.2 / max(shaft, 1e-6))
        hx = x2 - hf * (x2 - x1)
        hy = y2 - hf * (y2 - y1)
        self.add(f'<path d="M {x1:.1f} {y1:.1f} Q {mx:.1f} {my:.1f} '
                 f'{hx:.1f} {hy:.1f}" fill="none" stroke="{color}" '
                 f'stroke-width="{w:.2f}" stroke-linecap="round"/>')
        bx, by = x2 - (x2 - x1) * hf, y2 - (y2 - y1) * hf
        px_, py_ = -math.sin(ang), math.cos(ang)
        hw = max(w * 1.05, self.unit * 0.6)
        self.add(f'<path d="M {x2:.1f} {y2:.1f} '
                 f'L {bx + px_*hw:.1f} {by + py_*hw:.1f} '
                 f'L {bx - px_*hw:.1f} {by - py_*hw:.1f} Z" fill="{color}"/>')
        return self

    # ---------------------------------------------------------- 算法母题
    def radial_rays(self, cx, cy, R, n=7, inner=0.0, width=2.2,
                    color=None, phase=0.2, glow_core=5.5) -> "Cartoon":
        """点源径向射线（热化放射 / 点源发射 / 探测器 hit 丛发）。"""
        color = color or "#7a3a08"
        for k in range(n):
            a = 2 * math.pi * k / n + phase
            x1, y1 = cx + R*inner*math.cos(a), cy + R*inner*math.sin(a)
            x2, y2 = cx + R*math.cos(a), cy + R*math.sin(a)
            self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                     f'y2="{y2:.1f}" stroke="{color}" stroke-width="{width}" '
                     f'stroke-linecap="round" opacity="0.85"/>')
        if glow_core:
            self.add(f'<circle cx="{cx}" cy="{cy}" r="{glow_core}" '
                     f'fill="#fff4d0" stroke="{color}" stroke-width="1.2"/>')
        return self

    def radial_arrows(self, cx, cy, R, n=10, r_in=0.52, r_out=1.20,
                      ry=0.86, w=2.0, color=INK_SOFT) -> "Cartoon":
        """
        径向外流箭头（膨胀 / 集体流 / blast wave）。
        ★ 最通用的一个母题：中心源 + 径向外流，HEP 里到处出现。
        """
        for k in range(n):
            a = 2 * math.pi * k / n
            x1, y1 = cx + R*r_in*math.cos(a), cy + R*r_in*ry*math.sin(a)
            x2, y2 = cx + R*r_out*math.cos(a), cy + R*r_out*ry*math.sin(a)
            self.arrow(x1, y1, x2, y2, w=w, c=color)
        return self

    def spin_marker(self, x, y, r=11, direction="out", color=None) -> "Cartoon":
        """
        自旋/矢量方向的"垂直纸面"记号：
          direction="out"  → ⊙  指向读者
          direction="into" → ⊗  指离读者

        ★ 这是自旋极化类图必需的标准记号，原来库里没有。
          **不能把 L 画成面内箭头**——L = r × p 垂直于反应平面，
          在侧视图里它必须用 ⊙/⊗ 表达，否则物理是错的。
          （实测：第一版草图把 L 画成面内竖直箭头，等于说 L 在反应平面内。）
        """
        col = color or PALETTE["nucleus_edge"]
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#ffffff" '
                 f'stroke="{col}" stroke-width="{LW_THIN:.2f}"/>')
        if direction == "out":
            self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*0.34:.1f}" '
                     f'fill="{col}"/>')
        else:
            d = r * 0.66
            self.add(f'<line x1="{x-d:.1f}" y1="{y-d:.1f}" '
                     f'x2="{x+d:.1f}" y2="{y+d:.1f}" stroke="{col}" '
                     f'stroke-width="{LW_THIN:.2f}"/>')
            self.add(f'<line x1="{x-d:.1f}" y1="{y+d:.1f}" '
                     f'x2="{x+d:.1f}" y2="{y-d:.1f}" stroke="{col}" '
                     f'stroke-width="{LW_THIN:.2f}"/>')
        return self

    def vortex_arrows(self, cx, cy, R, n=3, arc=105.0, r_frac=0.62,
                      ccw=True, color=None, width=None) -> "Cartoon":
        """
        涡旋：沿圆周**切向**的弧形箭头（集体转动 / 涡度 ω）。

        和 `radial_arrows` 的区别：那个是**径向**外流（膨胀），
        这个是**切向**环流（转动）。自旋极化/涡旋主题必须用后者 ——
        画成径向就把"转动"画成了"膨胀"。

        ccw=True 逆时针（从指向读者看）。
        """
        col = color or "#7a3a08"
        w = width if width is not None else LW
        rr = R * r_frac
        for k in range(n):
            a0 = 360.0 * k / n + (0 if ccw else 0)
            span = arc * (1 if ccw else -1)
            self._tangential_arc_arrow(cx, cy, rr, a0, a0 + span, col, w)
        return self

    def _tangential_arc_arrow(self, cx, cy, r, a0, a1, color, w):
        """沿圆弧从 a0 画到 a1，末端加切向箭头。"""
        pts = []
        N = 20
        for i in range(N + 1):
            a = math.radians(a0 + (a1 - a0) * i / N)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        self.add(f'<path d="{d}" fill="none" stroke="{color}" '
                 f'stroke-width="{w:.2f}" stroke-linecap="round"/>')
        # 末端切向箭头
        ex, ey = pts[-1]
        tx, ty = pts[-1][0] - pts[-3][0], pts[-1][1] - pts[-3][1]
        L = math.hypot(tx, ty) or 1.0
        tx, ty = tx / L, ty / L
        h = max(11.0, w * 5.0)
        px, py = -ty, tx
        self.add(f'<path d="M {ex:.1f} {ey:.1f} '
                 f'L {ex-h*tx+px*h*0.45:.1f} {ey-h*ty+py*h*0.45:.1f} '
                 f'L {ex-h*tx-px*h*0.45:.1f} {ey-h*ty-py*h*0.45:.1f} Z" '
                 f'fill="{color}"/>')
        return self

    def poisson_discs(self, cx, cy, n=18, d_min=30, d_max=140, ry=0.80,
                      r_range=(6.5, 11.0), seed=31, palette="hadron",
                      r_scale=1.0) -> "Cartoon":
        """
        互不重叠的粒子云（拒绝采样）。用于冻结散点 / 探测器 hit / 事例显示。

        ★ 原实现签名里**没有 R**，散布范围写死 30–140，和相邻面板的
          blob 尺寸没有任何约束关系。现在 `d_min/d_max` 可由调用方按 R 传。
        """
        rng = random.Random(seed)
        cols = PALETTE.get(palette, PALETTE["hadron"])
        pts = []
        for _ in range(n):
            for _try in range(30):
                a = rng.uniform(0, 2 * math.pi)
                d = rng.uniform(d_min, d_max)
                x, y = cx + d*math.cos(a), cy + d*ry*math.sin(a)
                if all((x-qx)**2 + (y-qy)**2 > (d_min*0.57)**2
                       for qx, qy in pts):
                    pts.append((x, y))
                    break
        for (x, y) in pts:
            r = rng.uniform(*r_range) * r_scale
            hx, hy = shade_center()      # ★ 全局光
            m = self.radial([(0.0, cols[0], 0.9), (0.5, cols[1], 0.85),
                             (1.0, cols[2], 0.7)], cx=hx, cy=hy, r=0.8)
            self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                     f'fill="url(#{m})" stroke="{PALETTE["hadron_edge"]}" '
                     f'stroke-width="{LW_THIN:.2f}" stroke-opacity="0.85"/>')
        return self

    def light_cone(self, ox, oy, L, slope=1.0, color=INK_SOFT,
                   width=2.0, dash=None) -> "Cartoon":
        """
        光锥：从原点出发的两条对称线，**两支都在 t>0 侧**（向上的 V）。

        ★ 修了一个真 bug：原实现写的是 `y2 = oy - sgn*L*slope`，
          `sgn` 把负号吃掉了 → 两支分别落在 t>0 和 t<0 两侧，
          连起来是**过原点的一条直线**，不是 V 形光锥。
          实测：light_cone(300,300,120) 给出端点 (180,420) 与 (420,180)，
          与原点共线。改成两支都 `oy - L*slope`。
          （对靠画布底部的图，原写法的那一支会直接出界。）

        ★ 斜率默认 1.0（c=1 自然单位）。实测踩过画成 1.60 的坑
          （几何约束层抓出来的），所以它是显式参数。
        """
        d = f' stroke-dasharray="{dash}"' if dash else ""
        for sgn in (-1, 1):
            self.add(f'<line x1="{ox:.1f}" y1="{oy:.1f}" '
                     f'x2="{ox+sgn*L:.1f}" y2="{oy-L*slope:.1f}" '
                     f'stroke="{color}" stroke-width="{width}"{d}/>')
        return self

    def proper_time_family(self, ox, oy, taus, color=INK_SOFT,
                           width=1.2, dash="5 4", z_span=None,
                           half=False) -> "Cartoon":
        """
        proper-time 双曲线族 τ² = t² − z²：图中是各条 τ 等值线。

        ★ 原实现把 z 采样范围**写死成 ±2.2τ**，没有参数。
          后果：全支的左分支会长长地伸出去，紧邻面板时横穿隔壁内容。
          现在 `z_span` 可指定（绝对值，默认 2.2τ 保持兼容），
          `half=True` 只画 z≥0 半支。

        ★ 顺带更正一处物理：原来是 `rx=τ, ry=1.32τ` 的**四分之一椭圆**，
          不是 τ=const 曲线。真正的 τ=const 在 t–z 平面上是**双曲线**
          t = √(τ²+z²)，这里画的是后者。
        """
        for tau in taus:
            span = z_span if z_span is not None else tau * 2.2
            k0 = 0 if half else -span
            pts = []
            for k in range(41):
                z = k0 + (span - k0) * k / 40
                t = math.sqrt(tau * tau + z * z)
                pts.append((ox + z, oy - t))
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            self.add(f'<path d="{d}" fill="none" stroke="{color}" '
                     f'stroke-width="{width}" stroke-dasharray="{dash}"/>')
        return self

    # ---------------------------------------------------------- 衬板
    def cast_shadow(self, cx, cy, rx, ry=None, height=0.9, opacity=0.22,
                    blur=None) -> "Cartoon":
        """
        投射阴影：物体投在衬板上的软影。
        **方向和长度由全局光决定** —— 光低则影长，光换向则影跟着换。

        ★ 这是"三维阴影感"最直接的来源。原来只有 backplate 自带一个
          写死偏移的假影，且与光源无关；各元素之间根本没有互相投影。
        """
        ry = rx * 0.52 if ry is None else ry      # 地面影子默认压扁
        dx, dy = shadow_dir_px(height, max(rx, ry))
        b = blur if blur is not None else max(rx, ry) * 0.38
        self.add(f'<ellipse cx="{cx+dx:.1f}" cy="{cy+dy:.1f}" '
                 f'rx="{rx:.1f}" ry="{ry:.1f}" fill="#23232e" '
                 f'opacity="{opacity}" filter="url(#{self.blur(b)})"/>')
        return self

    def contact_shadow(self, cx, cy, rx, ry=None, opacity=0.26,
                       blur=None) -> "Cartoon":
        """
        接触阴影（AO 的简化）：物体与衬板接触处那一圈压暗。
        没有它，物体看着"浮"在板子上。
        """
        ry = rx if ry is None else ry
        b = blur if blur is not None else max(rx, ry) * 0.22
        self.add(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" '
                 f'ry="{ry:.1f}" fill="none" stroke="#23232e" '
                 f'stroke-width="{max(2.0, max(rx,ry)*0.30):.1f}" '
                 f'opacity="{opacity}" filter="url(#{self.blur(b)})"/>')
        return self

    def backplate(self, cx, cy, w, h, tilt=0.30, fill="#e8e8ea",
                  opacity=0.75, shadow=True) -> "Cartoon":
        """
        灰色透视衬板（期刊图里常见的"面板底面"，给 3D 物体一个立足处，
        同时提供中间调 → 直接贡献 dark_ratio）。
        """
        hw, hh = w / 2, h / 2
        dy = hh * tilt
        pts = [(cx-hw, cy-dy), (cx+hw, cy-dy), (cx+hw, cy+dy), (cx-hw, cy+dy)]
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if shadow:
            # ★ 投影方向从**全局光**推导（原来写死 translate(3,5)，
            #   和光源没关系——光换了方向影子还朝原来那边跑）。
            sx, sy = shadow_dir_px(0.55, min(w, h) * 0.5)
            self.add(f'<polygon points="{p}" fill="#000000" opacity="0.09" '
                     f'transform="translate({sx:.1f},{sy:.1f})" '
                     f'filter="url(#{self.blur(3.5)})"/>')
        self.add(f'<polygon points="{p}" fill="{fill}" opacity="{opacity}" '
                 f'stroke="#b8b8bc" stroke-width="1.0"/>')
        return self


# ══════════════════════════════════════════════════════════════
#  注册表 —— IR 的 `primitive` 字段用这些 key
# ══════════════════════════════════════════════════════════════
PRIMITIVES = {
    "label":            "Cartoon.label",
    "shaded_sphere":    "Cartoon.shaded_sphere",
    "nucleus_cluster":  "Cartoon.nucleus_cluster",
    "lorentz_nucleus":  "Cartoon.lorentz_nucleus",
    "qgp_blob":         "Cartoon.qgp_blob",
    "qgp_fireball":     "Cartoon.qgp_fireball",
    "hard_vertex":      "Cartoon.hard_vertex",
    "jet":              "Cartoon.jet",
    "gluon_radiation":  "Cartoon.gluon_radiation",
    "medium_wake":      "Cartoon.medium_wake",
    "arrow":            "Cartoon.arrow",
    "tapered_arrow":    "Cartoon.tapered_arrow",
    "radial_rays":      "Cartoon.radial_rays",
    "radial_arrows":    "Cartoon.radial_arrows",
    "poisson_discs":    "Cartoon.poisson_discs",
    "light_cone":       "Cartoon.light_cone",
    "proper_time_family": "Cartoon.proper_time_family",
    "backplate":        "Cartoon.backplate",
    "spin_marker":      "Cartoon.spin_marker",
    "vortex_arrows":    "Cartoon.vortex_arrows",
    "cast_shadow":      "Cartoon.cast_shadow",
    "contact_shadow":   "Cartoon.contact_shadow",
}


def check():
    """自检：每个图元都能画出来，且不抛异常。"""
    # 每个图元一组能跑通的调用参数（lambda 收 Cartoon）
    CALLS = {
        "label":              lambda c: c.label(300, 40, "ε₂(η) 中文 test"),
        "jet":                lambda c: c.jet(100, 100, 300, 200),
        "gluon_radiation":    lambda c: c.gluon_radiation(100, 100, 300, 200),
        "medium_wake":        lambda c: c.medium_wake(100, 100, 300, 200),
        "arrow":              lambda c: c.arrow(100, 100, 300, 200),
        "tapered_arrow":      lambda c: c.tapered_arrow(100, 100, 300, 200),
        "light_cone":         lambda c: c.light_cone(300, 300, 120),
        "proper_time_family": lambda c: c.proper_time_family(300, 300, [30, 60, 90]),
        "hard_vertex":        lambda c: c.hard_vertex(300, 200),
        "radial_rays":        lambda c: c.radial_rays(300, 200, 80),
        "radial_arrows":      lambda c: c.radial_arrows(300, 200, 80),
        "backplate":          lambda c: c.backplate(300, 200, 200, 120),
        "poisson_discs":      lambda c: c.poisson_discs(300, 200, n=10,
                                                        d_min=20, d_max=70),
        "nucleus_cluster":    lambda c: c.nucleus_cluster(300, 200, 50, n=12),
        "shaded_sphere":      lambda c: c.shaded_sphere(300, 200, 40,
                                                        PALETTE["nucleus"][1],
                                                        wire=True),
        "lorentz_nucleus":    lambda c: c.lorentz_nucleus(300, 200, 26, 96, shift=62),
        "qgp_blob":           lambda c: c.qgp_blob(300, 200, 90),
        "qgp_fireball":       lambda c: c.qgp_fireball(300, 200, 60),
        "spin_marker":        lambda c: c.spin_marker(300, 200, 12, "out"),
        "vortex_arrows":      lambda c: c.vortex_arrows(300, 200, 80),
        "cast_shadow":        lambda c: c.cast_shadow(300, 200, 40),
        "contact_shadow":     lambda c: c.contact_shadow(300, 200, 40),
    }
    missing = [n for n in PRIMITIVES if n not in CALLS]
    if missing:
        print(f"  ⚠️ 自检未覆盖：{missing}")

    c = Cartoon(600, 400)
    ok = 0
    for name in PRIMITIVES:
        try:
            CALLS[name](c)
            ok += 1
        except Exception as e:
            print(f"  ❌ {name}: {type(e).__name__}: {e}")
    print(f"cartoon_lib: {ok}/{len(PRIMITIVES)} 个图元可用")
    print(f"  中文字体 = {svg_lib.FONT_CJK}   （豆腐块检测见 selfcheck）")
    return ok == len(PRIMITIVES)


if __name__ == "__main__":
    check()
