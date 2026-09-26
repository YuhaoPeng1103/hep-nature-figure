# -*- coding: utf-8 -*-
"""panels_spin.py -- 自旋关联示意图（render_s22_clean.png, 1664x926）的版式/元素表。

坐标系 = 工作分辨率坐标（--W 1664，与源图 1:1）。所有框都是**量出来的**
（见工作区 _grid22_spin.png 网格标尺 + 连通域实测），不是估的。

物理：
  (a) 非中心重离子碰撞：两条平行束流虚线(z) + 两个 Lorentz 收缩核（蓝 A / 红 B）
      各自对齐一条束流线相向运动 + b 竖直双箭头跨两线 + QGP 火球
      + L 竖直粗箭头（轨道角动量，垂直反应平面）+ 涡旋 omega
      + 两个超子自旋箭头（都与 L 同向）
  (b) 对静止系里 Lambda-Lambdabar 对的自旋关联：背对背动量箭头 + 自旋粗箭头
      + 衰变细箭头(p/pi- , pbar/pi+) + theta* 圆弧

细线（虚线束流轴、b 的竖直双箭头、panel b 的细衰变箭头）对**任何**框的
bbox IoU 都接近 0（被切成一堆小连通域），光靠 ELEMENTS 的框分不出来 --
用 SPLIT 按【框 + 颜色/亮度】把它们**捞回**成独立图层。顺序要紧：先窄带、
后宽带，最后那条是兜底。
"""
CELLS = [
    ("a", "a", "schematic", (0, 0, 900, 926),
     "Non-central HIC: two Lorentz-contracted nuclei, impact parameter b, "
     "orbital angular momentum L, QGP fireball with vorticity omega, "
     "Lambda/Lambda-bar spin arrows along L"),
    ("b", "b", "schematic", (900, 0, 1664, 926),
     "Lambda-Lambda-bar pair in the pair rest frame: back-to-back momenta, "
     "spin arrows, weak-decay daughters (p, pi-, pbar, pi+), angle theta*"),
]


def order():
    seen, o = set(), []
    for cid, *_ in CELLS:
        if cid not in seen:
            seen.add(cid); o.append(cid)
    return o


def meta():
    m = {}
    for cid, pan, role, rect, desc in CELLS:
        if cid not in m:
            m[cid] = dict(panel=pan, role=role, desc=desc, rects=[rect])
        else:
            m[cid]["rects"].append(rect)
    return m


def cell_index(H, W):
    import numpy as np
    idx = np.full((H, W), -1, np.int32)
    for i, (cid, pan, role, (x0, y0, x1, y1), d) in enumerate(CELLS):
        idx[y0:y1, x0:x1] = i
    return idx


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# 颜色条件返回的是**加分**（float），不是 bool。
# ★ 为什么 ANY 不能给加分：实测灰色抗锯齿碎片（自旋箭头外晕 / 束流虚线 /
#   b 的竖虚线，颜色 ~(150,150,150)）对任何框的 IoU 都≈0，那个 +0.22 就成了
#   唯一判据 —— 于是它们全被表里靠前的 L-angular-momentum 抢走（实测 L 的
#   包围盒被撑到 229,74,518,654，含 x=229..240 的 b 竖虚线）。
#   改成：只有「确实是黑」的元素才有 +0.22，其余靠 IoU / 最近邻兜底。
DARK = lambda c: 0.22 if _lum(c) < 140 else 0.0   # noqa: E731
# ★ COLOR：按**饱和度**加分。实测：只给「黑」加分时，beam-axis-A 的框又长又宽
#   （20,244,892,266），核的浅色渐变块（如 (87,124,249) 的蓝）跟它 IoU 更小却被
#   它 +0.22 反超 —— 实测 5 个核的色块被判成 beam-axis-A。彩色元素按饱和度拿
#   同样的 0.22，才是同类比同类。
COLOR = lambda c: 0.22 if (max(c) - min(c)) > 40 else 0.0   # noqa: E731
PALE = lambda c: 0.0                              # noqa: E731
ANY = lambda c: 0.0                               # noqa: E731

# 顺序 = 图层输出顺序（也是 element_of 平手时的优先顺序，靠前者先赢）
ELEMENTS = {
    "a": [
        ("background", "Panel a background (white)", [(0, 0, 900, 926)], PALE),
        ("beam-axis-A", "Beam axis of nucleus A: upper dashed line (+z)",
                        [(20, 244, 892, 266)], DARK),
        ("beam-axis-B", "Beam axis of nucleus B: lower dashed line (-z)",
                        [(16, 677, 892, 699)], DARK),
        ("velocity-A", "Velocity of nucleus A (thick arrow, pointing right)",
                        [(181, 453, 344, 508)], DARK),
        ("velocity-B", "Velocity of nucleus B (thick arrow, pointing left)",
                        [(470, 610, 660, 684)], DARK),
        ("impact-parameter-b", "Impact parameter b (vertical dashed double arrow)",
                        [(216, 456, 268, 702)], DARK),
        ("hyperon-spin-A", "Lambda spin arrow of panel a, left",
                        [(212, 172, 276, 356)], DARK),
        ("hyperon-spin-B", "Lambda-bar spin arrow of panel a, right",
                        [(586, 172, 644, 358)], DARK),
        ("vorticity-omega", "Global vorticity omega (curved arrows round the fireball)",
                        [(318, 362, 532, 562)], DARK),
        ("L-angular-momentum", "Orbital angular momentum L (vertical arrow, "
                        "perpendicular to the reaction plane)",
                        [(386, 64, 456, 462)], COLOR),
        ("nucleus-A", "Nucleus A: Lorentz-contracted nucleus (blue)",
                        [(46, 210, 198, 720)], COLOR),
        ("nucleus-B", "Nucleus B: Lorentz-contracted nucleus (red)",
                        [(624, 226, 760, 825)], COLOR),
        ("fireball-QGP", "QGP fireball (orange)",
                        [(348, 396, 500, 540)], COLOR),
    ],
    "b": [
        ("background", "Panel b background (white)", [(900, 0, 1664, 926)], PALE),
        # 两团黑色箭头在顶点处**连成一体**（实测：左 group 是一个 220x186 的连通域），
        # 没法用框直接分开 -> 先整团命名，再用 SPLIT 逐条切出物理元素。
        ("pair-A-arrows", "Lambda decay kinematics: all black strokes "
                        "(momentum + spin + decay arrows)",
                        [(968, 318, 1258, 522)], DARK),
        ("pair-B-arrows", "Lambda-bar decay kinematics: all black strokes "
                        "(momentum + spin + decay arrows)",
                        [(1380, 315, 1645, 520)], DARK),
        ("pair-A-vertex", "Lambda (pair rest frame, green disc)",
                        [(1138, 447, 1207, 517)], COLOR),
        ("pair-B-vertex", "Lambda-bar (pair rest frame, green disc)",
                        [(1387, 447, 1457, 516)], COLOR),
    ],
}

# 细线/粘连体靠 SPLIT 捞回。每个面板的 SPLIT 顺序 = 优先级：
# 先窄带（只可能属于某一个元素的区域），后宽带，最后一个用 thr=250 兜底，
# 保证父元素不会剩下一堆散像素。
SPLIT = {
    # ★ 细线从 **background** 元素里捞，不是从整个面板（"*"）。
    #   实测坑：从 "*" 捞时 darkbox 是无差别取「该带里所有暗像素」—— 束流线
    #   在 y244..266 / y677..699 正好横穿两个核，于是把两个核的**暗色底尖**
    #   整段挖走（nucleus-A 被切掉 y687..708、nucleus-B 被切掉 y694..700 的
    #   整块 7400px），核图层出现缺口。细虚线是 discover 判小（<150px）丢进
    #   background 的散块，只从 background 里捞就够，且碰不到核。
    ("a", "background"): [
        # b 的双箭头也是细的（竖虚线 + 三角头）：实测不写这条时整条消失。
        # 顺序要紧：先 b（下半段箭头尖压在束流线上），再两条横带。
        ("impact-parameter-b", "Impact parameter b (vertical dashed double arrow)",
         ("darkbox", [(239, 483, 249, 705), (226, 483, 262, 522),
                      (226, 650, 262, 705)], 150)),
        ("beam-axis-A", "Beam axis of nucleus A: upper dashed line (+z)",
         ("darkbox", [(20, 244, 892, 266)], 150)),
        ("beam-axis-B", "Beam axis of nucleus B: lower dashed line (-z)",
         ("darkbox", [(16, 677, 892, 699)], 150)),
    ],
    ("a", "nucleus-A"): [
        # 实测：蓝色核的外轮廓与 velocity-A 箭头**相连**（同一连通域
        # 62,221,333,708），整团会被判成 nucleus-A -> 箭头必须从核里捞回来。
        ("velocity-A", "Velocity of nucleus A (thick arrow, pointing right)",
         ("darkbox", [(183, 455, 342, 506)], 150)),
    ],
    ("a", "velocity-A"): [
        # 实测：b 的**上箭头尖**与 velocity-A 的杆是同一个连通域（尖点在
        # y466..480 与杆重叠），先把 b 从 velocity-A 里切出来，否则 velocity-A
        # 的杆中间会被掏出一个 36x12 的缺口（实测缺口 957px）。
        ("impact-parameter-b", "Impact parameter b (vertical dashed double arrow)",
         ("darkbox", [(239, 483, 249, 705), (226, 483, 262, 522),
                      (226, 650, 262, 705)], 150)),
    ],
    ("a", "nucleus-B"): [
        ("velocity-B", "Velocity of nucleus B (thick arrow, pointing left)",
         ("darkbox", [(472, 612, 658, 682)], 150)),
    ],
    # 实测：两支细衰变箭头的**箭头尖**是独立连通域（pbar 尖 1506,267,1533,284，
    # 灰 lum≈152），落不进任何小框 -> 兜底成 background。这里从 background 里
    # 把它们捞回来。阈值 190（不是 150）：灰箭头尖 lum≈152。
    # ★ 这里**不能**用 thr=250 兜底 —— background 的框里全是白底，250 会把
    #   整块白底判给这几个元素。
    ("b", "background"): [
        ("pair-A-decay-proton", "Weak decay p (thin arrow)",
         ("darkbox", [(1082, 323, 1190, 470)], 190)),
        ("pair-B-decay-antiproton", "Weak decay pbar (thin arrow)",
         ("darkbox", [(1428, 256, 1545, 470)], 190)),
        ("pair-A-decay-pion", "Weak decay pi- (thin arrow)",
         ("darkbox", [(998, 383, 1200, 508)], 190)),
        ("pair-B-decay-pion", "Weak decay pi+ (thin arrow)",
         ("darkbox", [(1440, 380, 1640, 508)], 190)),
    ],
    ("b", "pair-A-arrows"): [
        ("pair-A-vertex", "Lambda (pair rest frame, green disc)",
         ("greenbox", [(1138, 447, 1207, 517)], 0)),
        ("pair-A-momentum", "Lambda momentum (thick arrow, pointing left)",
         ("darkbox", [(972, 463, 1150, 506)], 150)),
        ("pair-A-theta", "theta* angle between the proton and the spin direction",
         ("darkbox", [(1116, 384, 1254, 444), (1136, 444, 1182, 474)], 150)),
        ("pair-A-spin", "Lambda spin (thick arrow)",
         ("darkbox", [(1068, 378, 1182, 490)], 150)),
        ("pair-A-decay-proton", "Weak decay p (thin arrow)",
         ("darkbox", [(1082, 323, 1190, 470)], 150)),
        ("pair-A-decay-pion", "Weak decay pi- (thin arrow)",
         ("darkbox", [(998, 383, 1200, 508)], 250)),
    ],
    ("b", "pair-B-arrows"): [
        ("pair-B-vertex", "Lambda-bar (pair rest frame, green disc)",
         ("greenbox", [(1387, 447, 1457, 516)], 0)),
        ("pair-B-momentum", "Lambda-bar momentum (thick arrow, pointing right)",
         ("darkbox", [(1444, 463, 1626, 506)], 150)),
        ("pair-B-theta", "theta* angle between the antiproton and the spin direction",
         ("darkbox", [(1346, 386, 1448, 444), (1368, 444, 1414, 474)], 150)),
        ("pair-B-spin", "Lambda-bar spin (thick arrow)",
         ("darkbox", [(1406, 375, 1530, 490)], 150)),
        # 实测：pbar 的箭头尖是独立连通域（1506,267,1533,284），框要包到它
        ("pair-B-decay-antiproton", "Weak decay pbar (thin arrow)",
         ("darkbox", [(1428, 256, 1545, 470)], 150)),
        ("pair-B-decay-pion", "Weak decay pi+ (thin arrow)",
         ("darkbox", [(1440, 380, 1640, 508)], 250)),
    ],
}

MANUAL = []
# OCR 框漏掉的多部件字形，补一块「只擦不改字」的框（groupvec 的 erase 会 OR 上它）。
# 实测：Λ̄ 的上划线是独立的一横 (1405,522,1436,526)，OCR 框从 y=530 起 -> 擦不到，
# 成品里重写的 <text> 再画一根横杠就成了双划线。
EXTRA_ERASE = [(1403, 518, 1438, 529)]
FIX = {}
DROP = set()
ROTATED = []


def pixel_pred(a, spec):
    import numpy as np
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    kind = spec[0]
    if kind == "darkbox":
        _, boxes, thr = spec
        m = np.zeros(lum.shape, bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] = True
        return m & (lum < thr)
    if kind == "greenbox":
        # 绿色圆盘（含**深绿描边**）：G 明显高于 R/B 才算绿
        _, boxes, _t = spec
        m = np.zeros(lum.shape, bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] = True
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        return m & (g - r > 25) & (g - b > 25) & (g > 50)
    _, thr = spec
    return lum < thr if kind == "dark" else lum >= thr


def _iou(A, B):
    x0, y0 = max(A[0], B[0]), max(A[1], B[1])
    x1, y1 = min(A[2], B[2]), min(A[3], B[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = float((x1 - x0) * (y1 - y0))
    ua = (A[2] - A[0]) * (A[3] - A[1]) + (B[2] - B[0]) * (B[3] - B[1]) - inter
    return inter / ua if ua > 0 else 0.0


def element_of(cid, bbox, rgb):
    els = ELEMENTS.get(cid)
    if not els:
        return None, None
    best, bs = None, 0.0
    for eid, label, boxes, cond in els:
        s = max(_iou(bbox, b) for b in boxes)
        s += float(cond(rgb))
        if s > bs:
            bs, best = s, (eid, label)
    if best is None or bs < 0.10:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        # ★ 兜底要按 (距离, 框面积) 取最小，不能只看距离：
        #   background 的框是**整面板**，任何点对它 d=0，只看距离的话所有
        #   落不到框里的散块（灰色抗锯齿碎片、束流虚线的散段）全被判成
        #   background（实测 5 个散块、8000+px 被吞）。面积做第二关键字 =
        #   「包含它的最紧的框」，符合「点选物理元素」的直觉。
        bb, bk = els[-1][:2], (1e18, 1e18)
        for eid, label, boxes, cond in els:
            for (x0, y0, x1, y1) in boxes:
                dx = max(x0 - cx, 0.0, cx - x1)
                dy = max(y0 - cy, 0.0, cy - y1)
                k = ((dx * dx + dy * dy) ** 0.5, (x1 - x0) * (y1 - y0))
                if k < bk:
                    bk, bb = k, (eid, label)
        return bb
    return best