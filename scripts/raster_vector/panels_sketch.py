# -*- coding: utf-8 -*-
"""panels_sketch.py -- semantic layout table for the 4-stage sketch figure.

!! INSTANCE table (one figure). Canvas = working resolution 1080 x 340.

1) CELLS   : tile the canvas into panels (cover every pixel exactly once)
2) ELEMENTS: per-panel physical elements = (id, human label, [hit boxes], colour test)
3) SPLIT   : inside a named element, cut sub-elements by colour
4) MANUAL  : text the OCR cannot be trusted on (bold labels), (txt,x0,y0,x1,y1,bold)
"""

CELLS = [
 ("a", "a", "nucleus",   (   0,   0,  222, 340),
  "a | Deformed nucleus (prolate 3D ellipsoid + three nucleons)"),
 ("b", "b", "fluct",     ( 222,   0,  465, 340),
  "b | Quantum fluctuations: same nucleus + rotated ghost outlines"),
 ("c", "c", "collision", ( 465,   0,  750, 340),
  "c | Collision: two overlapping nuclei + warm participant zone"),
 ("d", "d", "fireball",  ( 750,   0, 1080, 340),
  "d | QGP fireball: hot core, halo, radial expansion arrows"),
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

def LIGHT(t):
    """亮度 >= t（PALE 是写死阈值的 lambda，不能传参）"""
    return lambda c: _lum(c) >= t


ELEMENTS = {
 "a": [
   ("nucleus",    "Prolate deformed nucleus (blue shaded ellipsoid)", [( 56,  76, 168, 160)], BLUE),
   ("nucleons",   "Three nucleons inside the deformed nucleus",      [( 76,  98, 150, 138)], LIGHT(232)),
   ("background", "Panel background",                                [(  0,   0, 222, 340)], LIGHT(248)),
 ],
 "b": [
   ("nucleus",    "Deformed nucleus (solid body)",                   [(278,  76, 382, 160)], BLUE),
   ("ghost",      "Dashed ghost outlines = orientation uncertainty", [(262,  58, 398, 178)], DARK(225)),
   ("background", "Panel background",                                [(222,   0, 465, 340)], LIGHT(248)),
 ],
 "c": [
   ("nucleus-in",  "Left incoming nucleus",                          [(512,  76, 636, 160)], BLUE),
   ("nucleus-out", "Right outgoing nucleus",                         [(568,  76, 690, 160)], BLUE),
   ("participant", "Warm participant overlap lens",                  [(584,  86, 616, 150)], WARM),
   ("background",  "Panel background",                               [(465,   0, 750, 340)], LIGHT(248)),
 ],
 "d": [
   ("fireball-core", "QGP fireball hot core",                        [(846,  62, 954, 174)], WARM),
   ("fireball-halo", "Fireball halo / glow",                         [(808,  26, 992, 210)], LIGHT(250)),
   ("exp-arrows",    "Radial expansion arrows",                      [(796,  14, 1004, 222)], DARK(150)),
   ("init-geometry", "Dashed initial collision geometry",            [(858,  86, 942, 150)], WARM),
   ("background",    "Panel background",                             [(750,   0, 1080, 340)], LIGHT(248)),
 ],
}

# 细线子元素（自动切分切不开时按颜色再捞）
SPLIT = {
 ("c", "participant"): [("participant-edge", "Participant-zone outline",
                         ("and", ("box", 580, 82, 620, 154), ("dark", 150)))],
 ("d", "exp-arrows"):  [("arrows-dark", "Expansion arrow shafts",
                         ("and", ("box", 790, 10, 1010, 226), ("dark", 120)))],
}

# OCR 不可信的粗体标签：直接写死正确文字（含粗体位）
MANUAL = [
 # (文字, x0, y0, x1, y1=**基线**, bold)  <- 第 5 项是基线提示，不是墨迹下沿！
 ("Deformed",      62, 206, 165, 222, True),
 ("nucleus",       72, 228, 155, 244, True),
 ("Quantum",      282, 206, 379, 222, True),
 ("fluctuations", 267, 228, 393, 244, True),
 ("Collision",    555, 222, 646, 238, True),
 ("QGP fireball", 838, 222, 963, 238, True),
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
