# -*- coding: utf-8 -*-
"""panels.py —— 图的语义版式定义（★ 每张图都要自己写的一张表）

!! 这个文件是 **T3-01 那张图的实例**，换图必须重写 CELLS / ELEMENTS / SPLIT。
   用 --panels my_panels.py 指定你自己的表，不用改这里。


1) CELLS   : 把画布精确划分成面板单元格
2) ELEMENTS: 每个面板内的「物理元素」= (元素id, 人读说明, [命中框...], 颜色条件)
   - rect 归属规则：取矩形的颜色与中心点，按顺序找第一个「框命中且颜色条件成立」的元素
   - 每个面板最后一个元素必须是兜底的背景（框=整个面板, 颜色=ALL）
   - 想改某个物理内容（火球 / 核子 / 流箭头 / 曲面 / 坐标轴…）就改这里的框或颜色条件
"""

CELLS = [
 ("title",            "",   "title",         (   0,    0, 1200,   82),
  "Figure title (editable text)"),
 ("initial-nuclei",   "",   "initial-state", (   0,   82,  207,  386),
  "Three colliding nuclei + impact-parameter arrows (initial state)"),
 ("a",                "a",  "transverse",    ( 207,   82,  456,  386),
  "a | Transverse profile of the fireball: nucleons, participant zone, flow arrows"),
 ("b",                "b",  "decomposition", ( 456,   82, 1200,  386),
  "b | Longitudinal profile: mode-by-mode decomposition into Area / Ellipticity / Triangularity"),
 ("h2",               "",   "heading",       (   0,  386,  456,  430),
  "Section heading: Head-on collisions of spherical nuclei"),
 ("c1",               "c1", "schematic",     (   0,  430,  456,  770),
  "c1 | Longitudinal structure of ellipticity and hydrodynamic expansion (spherical nuclei)"),
 ("d1",               "d1", "surface",       ( 456,  386,  800,  770),
  "d1 | Observed two-particle flow correlation (spherical nuclei)"),
 ("conn-1",           "",   "connector",     ( 800,  386,  848,  770),
  "Connector arrow d1 -> e"),
 ("e",                "e",  "surface",       ( 848,  386, 1200,  770),
  "e | Extracted deformation-driven flow (upper part)"),
 ("h3",               "",   "heading",       (   0,  770,  456,  816),
  "Section heading: Head-on collisions of deformed nuclei"),
 ("c2",               "c2", "schematic",     (   0,  816,  456, 1133),
  "c2 | Longitudinal structure of ellipticity and hydrodynamic expansion (deformed nuclei)"),
 ("d2",               "d2", "surface",       ( 456,  770,  820, 1133),
  "d2 | Observed two-particle flow correlation (deformed nuclei)"),
 ("e",                "e",  "surface",       ( 820,  770, 1200, 1133),
  "e | Extracted deformation-driven flow (lower part) + connector arrow from d2"),
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
# =====================================================================
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
 "initial-nuclei": [
   ("arrow",          "Beam-direction arrow (gray)",                    [(106, 178, 207, 224)], DARK(215)),
   ("nuclei-incoming","Two incoming deformed nuclei (top / bottom)",    [( 30,  90, 140, 306)], ALL),
   ("fireball",       "Produced QGP fireball (central)",                [( 44, 150, 120, 250)], ALL),
   ("background",     "Panel background",                               [(  0,  82, 207, 386)], PALE),
],
 "a": [
   ("axes",           "Coordinate axes eta'-x (bottom left)",           [(210, 228, 296, 296)], DARK(190)),
   ("flow-arrows",    "Flow arrows (blue / red) in the participant zone", [(268, 136, 396, 268)], REDBLUE),
   ("fireball",       "Participant zone (orange fireball)",             [(266, 136, 396, 268)], WARM),
   ("nucleons",       "Nucleon spheres (gray ring)",                    [(212, 108, 452, 286)], GRAYISH),
   ("background",     "Panel background",                               [(207,  82, 456, 386)], PALE),
 ],
 "b": [
   ("axis-eta-x",     "eta-x axis of the longitudinal profile",         [(586,  88, 640, 142)], DARK(225)),
   ("symbols",        "= / + / ... operator symbols",                   [(630, 180, 662, 212), (808, 180, 840, 212),
                                                                         (960, 180, 990, 212), (1104, 185, 1160, 218)], DARK(225)),
   ("cyl-total",      "Longitudinal profile of the initial state",      [(474, 104, 620, 292)], ALL),
   ("cyl-area",       "Mode 1 - Area: S(eta)",                          [(682, 108, 824, 292)], ALL),
   ("cyl-ellipticity","Mode 2 - Ellipticity: eps2(eta)",                [(826, 104, 968, 292)], ALL),
   ("cyl-triangularity","Mode 3 - Triangularity: eps3(eta)",            [(968, 112, 1118, 296)], ALL),
   ("background",     "Panel background",                               [(456,  82, 1200, 386)], PALE),
 ],
 "c1": [
   ("momentum-arrow","Nuclear deformation / recoil arrow (red)",        [(350, 428, 380, 448), (112, 712, 142, 742)], RED),
   ("nucleus-deformed","Deformed nucleus (top right, spectator)",       [(308, 434, 382, 502)], ALL),
   ("nucleus-spectator","Nucleon spectator (bottom left)",              [(122, 652, 194, 720)], ALL),
   ("jets",           "Non-flow jets / resonance cones (red-blue)",     [(288, 600, 380, 706)], JETCOL),
   ("slice-ellipse",  "Cut face of the medium (gray ellipse)",          [(110, 446, 222, 558)], ALL),
   ("core-sphere",    "Participant core (gray sphere in the medium)",   [(170, 566, 254, 660)], ALL),
   ("medium-tube",    "Hydrodynamic expansion (medium tube)",           [(128, 462, 380, 700)], ALL),
   ("connector-arrow","Arrow towards panel d1",                         [(378, 534, 456, 574)], ALL),
   ("background",     "Panel background",                               [(  0, 430, 456, 770)], PALE),
 ],
 "d1": [
   ("surface",        "Two-particle correlation surface",               [(500, 408, 778, 656)], PALE),
   ("background",     "Panel background",                               [(456, 386, 800, 770)], PALE),
 ],
 "conn-1": [
   ("arrow",          "Connector arrow d1 -> e",                        [(796, 562, 878, 678)], ALL),
   ("background",     "Panel background",                               [(800, 386, 848, 770)], PALE),
 ],
 "e": [
   ("arrow",          "Connector arrow d2 -> e",                        [(814, 918, 888, 984)], ALL),
   ("arrow-d1",       "Connector arrow d1 -> e (arrow head)",           [(842, 622, 884, 664)], ALL),
   ("surface",        "Extracted deformation-driven flow surface",      [(908, 660, 1188, 908)], PALE),
   ("background",     "Panel background",                               [(820, 386, 1200, 1133)], PALE),
 ],
 "c2": [
   ("momentum-arrow","Nuclear deformation / recoil arrow (red)",        [(350, 816, 380, 838), (116, 1098, 146, 1130)], RED),
   ("nucleus-deformed","Deformed nucleus (top right, spectator)",       [(308, 820, 382, 892)], ALL),
   ("nucleus-spectator","Nucleon spectator (bottom left)",              [(124, 1040, 200, 1112)], ALL),
   ("jets",           "Non-flow jets / resonance cones (red-blue)",     [(286, 982, 380, 1076)], JETCOL),
   ("slice-ellipse",  "Cut face of the medium (gray ellipse)",          [(128, 902, 224, 1028)], ALL),
   ("core-sphere",    "Participant core (gray sphere in the medium)",   [(170, 958, 256, 1046)], ALL),
   ("medium-tube",    "Hydrodynamic expansion (medium tube)",           [(130, 854, 380, 1082)], ALL),
   ("connector-arrow","Arrow towards panel d2",                         [(376, 964, 456, 996)], ALL),
   ("background",     "Panel background",                               [(  0, 816, 456, 1133)], PALE),
 ],
 "d2": [
   ("surface",        "Two-particle correlation surface",               [(502, 854, 784, 1098)], PALE),
   ("background",     "Panel background",                               [(456, 770, 820, 1133)], PALE),
 ],
}

# 在已命名元素内部再按颜色切细（细线切不开时用）
SPLIT = {
 ("initial-nuclei", "nuclei-incoming"): [
     ("fireball",       "Produced QGP fireball (central)",
      ("and", ("box", 38, 148, 126, 252), ("warm", 0.14, 15, 70))),
     ("nucleus-top",    "Incoming deformed nucleus (top)",    ("box", 0, 82, 207, 200)),
     ("nucleus-bottom", "Incoming deformed nucleus (bottom)", ("box", 0, 200, 207, 330))],
 ("c1", "*"): [("momentum-arrow", "Nuclear deformation / recoil arrow (red)",
                ("and", ("or", ("box", 330, 414, 396, 450), ("box", 100, 702, 158, 752)),
                 ("red",)))],
 ("c2", "*"): [("momentum-arrow", "Nuclear deformation / recoil arrow (red)",
                ("and", ("or", ("box", 330, 810, 396, 846), ("box", 104, 1088, 162, 1133)),
                 ("red",)))],
 ("d1", "surface"): [("axes", "Coordinate frame, ticks and leader arrows", ("dark", 130))],
 ("d2", "surface"): [("axes", "Coordinate frame, ticks and leader arrows", ("dark", 130))],
 ("e",  "surface"): [("axes", "Coordinate frame, ticks and leader arrows", ("dark", 130))],
 ("c1", "medium-tube"): [("jets", "Non-flow jets / resonance cones (red-blue)",
                          ("and", ("box", 286, 596, 378, 708), ("dark", 215)))],
 ("c2", "medium-tube"): [("jets", "Non-flow jets / resonance cones (red-blue)",
                          ("and", ("box", 284, 978, 378, 1078), ("dark", 215)))],
}


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
    cnt = np.zeros((1133, 1200), np.int32)
    for cid, pan, role, (x0, y0, x1, y1), d in CELLS:
        cnt[y0:y1, x0:x1] += 1
    print("\n版面检查: 未覆盖像素 = %d, 重叠像素 = %d (都应为 0)"
          % (int((cnt == 0).sum()), int((cnt > 1).sum())))
