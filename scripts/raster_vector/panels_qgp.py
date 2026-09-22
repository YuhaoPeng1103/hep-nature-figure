# -*- coding: utf-8 -*-
"""my_panels.py -- semantic layout table for: QGP orientation-fluctuation figure

!! This is an INSTANCE table (one figure). For another figure rewrite
   CELLS / ELEMENTS / SPLIT.

Canvas is the working resolution: 1200 x 865 (source 2218 x 1599).

1) CELLS   : tile the canvas into panels (must cover every pixel exactly once)
2) ELEMENTS: per-panel physical elements = (id, human label, [hit boxes], colour test)
3) SPLIT   : inside a named element, cut sub-elements by colour
"""

CELLS = [
 ("a",  "a", "nucleus",  (  0,   0,  320, 380),
  "a | Prolate-deformed nucleus + Low-energy method arrow"),
 ("b",  "b", "quantum",  (320,   0, 1200, 195),
  "b | Quantum fluctuations in orientations + time scale"),
 ("hi", "",  "method",   (  0, 380,  320, 620),
  "High-energy method arrow (>=100 GeV per nucleon)"),
 ("bl", "",  "note",     (  0, 620,  320, 865),
  "Bottom-left: fm/c = 3e-24 seconds + arrow tails"),
 ("d",  "d", "config",   (320, 195,  585, 865),
  "d | Body-body and tip-tip configurations; Boosted to relativistic speed"),
 ("e",  "e", "qgp",      (585, 195,  950, 865),
  "e | Pressure-driven hydrodynamic expansion (QGP fireball)"),
 ("f",  "f", "qgp",      (950, 195, 1200, 865),
  "f | QGP with large nu2 / small nu2 and flow arrows"),
]

def order():
    """组出现顺序（保持版式阅读顺序，e 只出现一次）"""
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
    """每个像素属于哪个 cell（返回 int 索引图）"""
    import numpy as np
    idx = np.full((H, W), -1, np.int32)
    for i, (cid, pan, role, (x0, y0, x1, y1), d) in enumerate(CELLS):
        idx[y0:y1, x0:x1] = i
    return idx


# =====================================================================
#  元素（人可直接编辑的「物理内容」分组）
#    - ELEMENTS[cid] = [(元素id, 人读说明, [命中框...], 颜色条件), ...]
#      自动切分出的每块，按「与上述框的 IoU + 颜色是否吻合」取名；
#      条件里 ALL 表示不限颜色。每个面板最后一项是兜底背景。
#    - SPLIT = 在某个已命名元素内部，再按像素颜色切出自元素
#      （用于「曲面上的坐标轴/引线」这类细线，自动切分切不开的情况）

def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _sat(c):
    mx = max(c)
    return 0.0 if mx == 0 else (mx - min(c)) / float(mx)


def _hue(c):
    r, g, b = [v / 255.0 for v in c]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d < 1e-6:
        return 0.0
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0


ALL = lambda c: True
def DARK(t=150):
    return lambda c: _lum(c) < t
GRAYISH = lambda c: _sat(c) < 0.14 and _lum(c) < 246
PALE = lambda c: _lum(c) >= 246
BLUE = lambda c: _sat(c) > 0.18 and 190 <= _hue(c) <= 275
RED = lambda c: _sat(c) > 0.35 and (_hue(c) <= 20 or _hue(c) >= 335)
WARM = lambda c: _sat(c) > 0.14 and 15 < _hue(c) < 60
REDBLUE = lambda c: BLUE(c) or RED(c)
# 喷流/共振锥：饱和且偏暗的细线（红或蓝）
JETCOL = lambda c: _sat(c) > 0.25 and _lum(c) < 215

ELEMENTS = {
 "a": [
   ("nucleus",     "Prolate-deformed nucleus (3D shaded ellipsoid)", [(  0, 175, 155, 360)], GRAYISH),
   ("method-arrow","Low-energy method arrow + label leader line",    [(155,  80, 320, 230)], DARK(215)),
   ("background",  "Panel background",                               [(  0,   0, 320, 380)], PALE),
 ],
 "b": [
   ("nucleus-row", "Six deformed nuclei: quantum fluctuations in orientation",
                                                                     [(465,  15, 1150, 165)], GRAYISH),
   ("dotted",      "Dotted orientation-connector lines",             [(355,  70, 1180, 105)], DARK(205)),
   ("background",  "Panel background",                               [(320,   0, 1200, 195)], PALE),
 ],
 "hi": [
   ("method-arrow","High-energy method arrow + label leader line",   [( 45, 380, 320, 555)], DARK(215)),
   ("background",  "Panel background",                               [(  0, 380, 320, 620)], PALE),
 ],
 "bl": [
   ("arrow-tail",  "Arrow tails running to the tip-tip panel",       [(230, 620, 330, 810)], DARK(215)),
   ("background",  "Panel background",                               [(  0, 620, 320, 865)], PALE),
 ],
 "d": [
   ("nucleus-bb",  "Body-body configuration: two deformed nuclei",   [(330, 345, 510, 485)], GRAYISH),
   ("nucleus-tt",  "Tip-tip configuration: two deformed nuclei",     [(320, 685, 500, 820)], GRAYISH),
   ("connector",   "Connector arrows d -> e (both rows)",
                    [(510, 420, 585, 470), (505, 740, 580, 790)], DARK(205)),
   ("background",  "Panel background",                               [(320, 195, 585, 865)], PALE),
 ],
 "e": [
   # 灰色等离子体板（两行各一块平行四边形）
   ("plasma-plane","Grey plasma slab (light grey parallelogram)",
                    [(596, 300, 840, 540), (596, 610, 840, 850)], GRAYISH),
   # 旁观核：穿过等离子体板的两个变形核（每行两个）
   ("spectator-nuclei","Spectator nuclei passing through the plasma slab",
                    [(610, 372, 678, 492), (766, 392, 838, 494),
                     (603, 692, 678, 784), (762, 717, 838, 802)], GRAYISH),
   # 火球（橙黄渐变团块）。★ 框必须贴住团块本体：框太松会被 flow-arrow 的大框
   #   以 IoU 抢走（实测火球曾被命名为 flow-arrow）
   ("fireball",    "QGP fireball (orange gradient blob)",
                    [(688, 388, 762, 498), (675, 704, 763, 790)], WARM),
   # 集体流箭头（每行 4 个：上 / 下 / 左 / 右）
   ("flow-arrow",  "Collective-flow arrows (warm, 4 per row)",
                    [(706, 361, 750, 399), (709, 490, 749, 520),
                     (645, 435, 703, 486), (744, 390, 805, 428),
                     (694, 664, 734, 713), (701, 784, 746, 833),
                     (644, 750, 691, 791), (744, 714, 798, 754)], WARM),
   ("axes",        "x-y coordinate frame",
                    [(620, 490, 690, 545), (620, 800, 690, 855)], DARK(190)),
   ("connector",   "Connector arrows e -> f (both rows)",
                    [(885, 425, 950, 470), (880, 740, 945, 790)], DARK(205)),
   ("background",  "Panel background",                               [(585, 195, 950, 865)], PALE),
 ],
 "f": [
   ("plasma-plane","Grey plasma slab",
                    [(972, 300, 1192, 512), (972, 610, 1192, 832)], GRAYISH),
   ("qgp-blob",    "QGP region (orange gradient) + radial flow lines",
                    [(985, 371, 1183, 493), (1002, 692, 1161, 826)], WARM),
   ("axes",        "x-y coordinate frame",
                    [(995, 485, 1050, 530), (995, 795, 1050, 840)], DARK(190)),
   ("background",  "Panel background",                               [(950, 195, 1200, 865)], PALE),
 ],
}

SPLIT = {
 # e 的火球是纯渐变、没有暗线（实测框内最低亮度 ~126），所以不切 flow-lines；
 # f 的团块里才有真正的深色径向流线 —— 阈值必须压到 120，
 # 用 170 会把橙色本体（lum~150）整片吞进 flow-lines（实测吞了 24725px）。
 ("f", "qgp-blob"): [("flow-lines", "Radial flow lines inside the QGP region",
                      ("dark", 120))],
}

# =====================================================================
#  每图各不相同的三张文字表（groupvec 会优先用 panels 里的这几张）
#    FIX     OCR 错字修正      DROP  丢弃的 OCR 碎片
#    MANUAL  OCR 漏掉的粗体面板标号 (text, x0, y0, x1, y1, bold)  ← 工作分辨率坐标
# =====================================================================
FIX = {}
DROP = set()
MANUAL = [
    ("b",  435,  11,  453,  32, True),
    ("d",  328, 303,  341, 322, True),
    ("e",  592, 303,  605, 322, True),
    ("f", 1000, 305, 1013, 324, True),
]

# 旋转标签（斜排的箭头说明）。labels.align 的墨迹模型只认水平文字，
# 所以这几条手量「框 + 角度 + 字号」。坐标 = 工作分辨率。
ROTATED = [
    ("Low-energy method",        183,  95, 349, 200, -24.0, 17),
    ("<100 MeV per nucleon",     150, 145, 398, 235, -24.0, 17),
    ("≥100 GeV per nucleon",    112, 375, 300, 460,  43.0, 17),
    ("High-energy method",        88, 410, 285, 545,  43.0, 17),
    # 斜排的物理标签：沿等离子体板顶边 / 火球切向。角度是最小二乘实测，
    # 框是紧墨迹框；这些不能走 labels.align（它的墨迹模型只认水平文字）。
    ("Quark-gluon plasma",       660, 330, 792, 374, -13.6, 16),
    ("Quark-gluon plasma",       660, 640, 792, 683, -13.6, 16),
    ("Quark-gluon plasma",      1014, 337, 1167, 390, -11.6, 16),
    ("Quark-gluon plasma",      1018, 641, 1167, 694, -14.4, 16),
    ("Large ε_{2} small d_{⊥}",  662, 508, 828, 560, -11.3, 16),
    ("Large ν_{2} small p_{⊥}", 1022, 504, 1200, 558,  -9.2, 16),
    ("Small ε_{2} large d_{⊥}",  671, 821, 803, 868, -13.8, 16),
    ("Small ν_{2} large p_{⊥}", 1046, 821, 1200, 869, -13.1, 16),
]


def pixel_pred(a, spec):
    import numpy as np
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a.max(2); mn = a.min(2)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    k = spec[0]
    if k == "box":
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        return (xx >= spec[1]) & (xx < spec[3]) & (yy >= spec[2]) & (yy < spec[4])
    if k == "and":
        return pixel_pred(a, spec[1]) & pixel_pred(a, spec[2])
    if k == "or":
        return pixel_pred(a, spec[1]) | pixel_pred(a, spec[2])
    if k == "red":
        return (r > 120) & (r > g + 45) & (r > b + 45)
    if k == "blue":
        return (b > 100) & (b > r + 30)
    if k == "dark":
        return lum < spec[1]
    if k == "pale":
        return lum >= spec[1]
    if k == "gray":
        return (sat < spec[1]) & (lum < spec[2])
    if k == "warm":
        rn = r / 255.0; gn = g / 255.0; bn = b / 255.0
        mxr = np.maximum(np.maximum(rn, gn), bn); mnr = np.minimum(np.minimum(rn, gn), bn)
        d = np.maximum(mxr - mnr, 1e-6)
        h = np.where(mxr == rn, ((gn - bn) / d) % 6, np.where(mxr == gn, (bn - rn) / d + 2, (rn - gn) / d + 4)) * 60
        return (sat > spec[1]) & (h > spec[2]) & (h < spec[3])
    raise ValueError(spec)


def _iou(A, B):
    x0 = max(A[0], B[0]); y0 = max(A[1], B[1])
    x1 = min(A[2], B[2]); y1 = min(A[3], B[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = float((x1 - x0) * (y1 - y0))
    ua = (A[2] - A[0]) * (A[3] - A[1]) + (B[2] - B[0]) * (B[3] - B[1]) - inter
    return inter / ua if ua > 0 else 0.0


def element_of(cid, bbox, rgb):
    """给自动切分出的一个色块命名：与 ELEMENTS 里的框比 IoU，颜色吻合加成；
    全都对不上就退化成「离哪个框最近」。返回 (元素id, 人读说明)"""
    els = ELEMENTS.get(cid)
    if not els:
        return None, None
    best, bs = None, 0.0
    for eid, label, boxes, cond in els:
        s = max(_iou(bbox, b) for b in boxes)
        if cond(rgb):
            s += 0.22
        if s > bs:
            bs, best = s, (eid, label)
    if best is None or bs < 0.10:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        bb, bd = els[-1][:2], 1e18
        for eid, label, boxes, cond in els:
            for (x0, y0, x1, y1) in boxes:
                dx = max(x0 - cx, 0.0, cx - x1); dy = max(y0 - cy, 0.0, cy - y1)
                d = (dx * dx + dy * dy) ** 0.5
                if d < bd:
                    bd, bb = d, (eid, label)
        return bb
    return best


if __name__ == "__main__":
    import numpy as np
    m = meta()
    for cid in order():
        print(f"  {cid:16s} panel={m[cid]['panel'] or '-':4s} role={m[cid]['role']:14s} "
              f"cells={len(m[cid]['rects'])} 元素={len(ELEMENTS.get(cid, []))}")
    W = max(r[2] for _, _, _, r, _ in CELLS)
    H = max(r[3] for _, _, _, r, _ in CELLS)
    cnt = np.zeros((H, W), np.int32)
    for cid, pan, role, (x0, y0, x1, y1), d in CELLS:
        cnt[y0:y1, x0:x1] += 1
    print("\n版面检查: 画布 %dx%d, 未覆盖像素 = %d, 重叠像素 = %d (都应为 0)"
          % (W, H, int((cnt == 0).sum()), int((cnt > 1).sum())))
