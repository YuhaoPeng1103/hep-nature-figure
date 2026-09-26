# -*- coding: utf-8 -*-
"""panels_upc.py -- UPC 示意图（qwen-image-3.0 生成的位图，1664x928）的版式/元素表。

每条 ELEMENTS 项 = 一个**物理元素**：人能在 Illustrator 图层面板里按名字点选、
单独改它。框是从位图上实测的（连通域 + 颜色掩膜），不是估的。

坐标系 = 工作分辨率坐标（--W 1664，和源图 1:1）。
"""
CELLS = [
    ("p", "p", "schematic", (0, 0, 1664, 928),
     "UPC side view: two Lorentz-contracted nuclei, impact parameter b, gamma-gamma vertex"),
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


# ── 颜色判据（只用来给 IoU 加一个 0.22 的加成，不是硬门限）──
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


BLUE = lambda c: 195 < _hue(c) < 250 and _sat(c) > 0.35 and _lum(c) < 190   # noqa: E731
ORANGE = lambda c: 5 < _hue(c) < 32 and _sat(c) > 0.55 and _lum(c) < 205    # noqa: E731
AMBER = lambda c: 25 < _hue(c) < 52 and _sat(c) > 0.12 and _lum(c) > 150    # noqa: E731
MAGENTA = lambda c: 285 < _hue(c) < 335 and _sat(c) > 0.40                   # noqa: E731
GREEN = lambda c: 120 < _hue(c) < 175 and _sat(c) > 0.25                     # noqa: E731
DARK = lambda c: _lum(c) < 115                                              # noqa: E731
PALE = lambda c: _lum(c) >= 246                                             # noqa: E731

# 顺序 = 图层输出顺序（从下到上）
ELEMENTS = {
    "p": [
        ("background",   "Panel background (white)", [(0, 0, 1664, 928)], PALE),
        ("axis-A",       "Beam axis of nucleus A (upper dashed line)",
                         [(30, 240, 1640, 262)], DARK),
        ("axis-B",       "Beam axis of nucleus B (lower dashed line)",
                         [(30, 634, 1640, 656)], DARK),
        ("field-A",      "Lorentz-contracted Coulomb field of A (amber rings)",
                         [(339, 100, 481, 380)], AMBER),
        ("field-B",      "Lorentz-contracted Coulomb field of B (amber rings)",
                         [(1207, 510, 1354, 787)], AMBER),
        ("photon-A",     "Quasi-real photon emitted by A (wavy line, gamma)",
                         [(455, 288, 860, 470)], AMBER),
        ("photon-B",     "Quasi-real photon emitted by B (wavy line, gamma)",
                         [(818, 440, 1245, 718)], AMBER),
        ("nucleus-A",    "Nucleus A, Lorentz-contracted (blue)",
                         [(365, 130, 455, 350)], BLUE),
        ("nucleus-B",    "Nucleus B, Lorentz-contracted (orange)",
                         [(1234, 537, 1325, 754)], ORANGE),
        ("arrow-v-A",    "Velocity of A (thick arrow pointing right)",
                         [(525, 203, 680, 238)], DARK),
        ("arrow-v-B",    "Velocity of B (thick arrow pointing left)",
                         [(1005, 675, 1168, 708)], DARK),
        ("arrow-b",      "Impact parameter b (vertical double-headed arrow)",
                         [(98, 250, 133, 645)], DARK),
        ("vertex",       "gamma-gamma interaction vertex (starburst)",
                         [(805, 425, 862, 480)], DARK),
        ("arrow-e-plus", "Outgoing e+ (magenta arrow, back to back)",
                         [(855, 350, 958, 440)], MAGENTA),
        ("arrow-e-minus", "Outgoing e- (green arrow, back to back)",
                         [(715, 464, 818, 562)], GREEN),
    ],
}

# ★ 虚线束流轴在自动切分里是「几百段 <150px 的小连通域」，全部落进 background。
#   用 SPLIT 按【框 + 亮度】把它们捞回成独立图层。坐标是量出来的：
#   实测 y=250..251 有 780/831 个暗像素、y=644..645 有 778/876 个（阈值 150）。
#   单侧避让核 A/B 的 x 区段，免得把核的描边光晕算进来。
_AX_A = [(30, 240, 356, 262), (462, 240, 1640, 262)]
_AX_B = [(30, 634, 1230, 656), (1332, 634, 1640, 656)]

SPLIT = {
    ("p", "background"): [
        ("axis-A", "Beam axis of nucleus A (upper dashed line)",
         ("darkbox", _AX_A, 150)),
        ("axis-B", "Beam axis of nucleus B (lower dashed line)",
         ("darkbox", _AX_B, 150)),
    ],
}

# ★ 必须显式置空：groupvec 的 `getattr(P, "MANUAL", LB.MANUAL)` 在 --panels 没定义时
#   会退回 labels.py 里 **T3-01 那张图** 的手工标签表（a/b/c1/d1… 的写死坐标），
#   换图后会凭空多出 7 个鬼影标签。
MANUAL = []
# OCR 错字修正 / 丢弃表也一并接管（labels.FIX 是 T3-01 的词）
FIX = {"gamma": "\u03b3"}
DROP = set()


def pixel_pred(a, spec):
    """SPLIT 用的像素判据。支持 ("dark"|"pale", thr) 和
    ("darkbox", [框...], thr)：暗像素且落在给定框内（框是 (x0,y0,x1,y1)）。"""
    import numpy as np
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    if spec[0] == "darkbox":
        _, boxes, thr = spec
        m = np.zeros(lum.shape, bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] = True
        return m & (lum < thr)
    kind, thr = spec
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
                dx = max(x0 - cx, 0.0, cx - x1)
                dy = max(y0 - cy, 0.0, cy - y1)
                d = (dx * dx + dy * dy) ** 0.5
                if d < bd:
                    bd, bb = d, (eid, label)
        return bb
    return best
