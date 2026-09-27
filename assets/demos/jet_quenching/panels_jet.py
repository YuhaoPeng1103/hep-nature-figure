# -*- coding: utf-8 -*-
"""panels_jet.py -- 喷注淬火（jet quenching）示意图的版式/元素表。

源图：gen3a/render_s33_clean.png（1662x926，路径三：IR -> 简报 -> 草图 -> 成品位图 -> 临摹）。
坐标系 = 工作分辨率坐标（--W 1662，与源图 1:1）。文字不在这里 —— 走 --words。

★ 图层按【物理对象】分组，不按颜色分组：人能在 Illustrator 图层面板里
  按名字点选、单独改它对应的物理内容（"要把被淬火那条喷注画深一点" →
  直接找 jet-quenched-cone 这一层）。

框全部是**量出来的**（颜色掩膜 + 连通域，见 fig_jet/README.md 的量测记录），
不是估的：

  介质          橙色高饱和块，凸包拟合椭圆 c=(838.6,427.9) 半轴 374x207 -> bbox (634,56,1045,802)
  顶点星芒      亮黄白(R>228,G>185)在 (920,360)-(1010,445) 那一小团
  蓝喷注锥      深藏青 (B-R>40,B>90,G<115) 最大连通域 25035px -> bbox (963,83,1297,383)
  蓝强子簇      浅蓝球 (B-R>18,B>140,lum>150) 在锥尖，5+ 个 25px 球 -> (1252,100,1325,212)
  灰喷注锥      低饱和灰 (sat<0.15) 最大连通域 31706px -> bbox (289,533,614,764)
  灰强子簇      暗蓝灰球 (sat<0.35, 90<lum<175) 在锥口 -> (300,645,372,716)
  胶子辐射      黄绿小点 (G-B>80,G>150,R>120)，都在介质内、沿灰喷注
  束流箭头      暗色细竖线 (1065,563)-(1079,681)
"""
CELLS = [
    ("p", "p", "schematic", (0, 0, 1662, 926),
     "Jet quenching: a back-to-back dijet produced inside a vertically elongated "
     "QGP medium. The right-going jet exits almost immediately (short path, "
     "unquenched); the left-going jet traverses nearly the whole medium, losing "
     "energy by gluon bremsstrahlung (quenched, fewer/softer hadrons)"),
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


# 颜色判据只给 IoU 加 0.22 的**加成**，不是硬门限（判归属还是 IoU 说了算）
PALE = lambda c: 0.22 if _lum(c) >= 246 else 0.0                                    # noqa: E731
ORANGE = lambda c: 0.22 if (_sat(c) > 0.45 and 5 < _hue(c) < 58) else 0.0           # noqa: E731
BLUE = lambda c: 0.22 if (_sat(c) > 0.30 and 200 < _hue(c) < 265) else 0.0          # noqa: E731
PALEBLUE = lambda c: 0.22 if (_sat(c) > 0.10 and 195 < _hue(c) < 265
                              and _lum(c) > 150) else 0.0                           # noqa: E731
GREY = lambda c: 0.22 if (_sat(c) < 0.15 and 40 < _lum(c) < 246) else 0.0           # noqa: E731
DARKGREY = lambda c: 0.22 if (_sat(c) < 0.35 and 90 < _lum(c) < 175) else 0.0       # noqa: E731
LIME = lambda c: 0.22 if (_sat(c) > 0.45 and 45 < _hue(c) < 105
                          and _lum(c) > 90) else 0.0                                # noqa: E731
BRIGHT = lambda c: 0.22 if _lum(c) >= 225 else 0.0                                  # noqa: E731
DARK = lambda c: 0.22 if _lum(c) < 95 else 0.0                                      # noqa: E731
ANY = lambda c: 0.0                                                                 # noqa: E731

# 顺序 = 图层输出顺序（从后往前 = 从背景到前景，与画序一致）
ELEMENTS = {
    "p": [
        ("background", "Panel background (white)", [(0, 0, 1662, 926)], PALE),
        ("medium",
         "QGP medium: vertically elongated semi-transparent ellipsoid "
         "(long axis = beam direction, vertical)",
         [(634, 56, 1045, 802)], ORANGE),
        ("vertex",
         "Hard-scattering vertex: small bright starburst where the back-to-back "
         "dijet is produced; sits inside the medium, clearly right of its centre",
         [(915, 355, 1015, 450)], BRIGHT),
        ("jet-unquenched-cone",
         "Unquenched jet: collimated cone going up-right. Short path -- it leaves "
         "the medium almost immediately, so it stays bright and saturated",
         [(940, 78, 1310, 400)], BLUE),
        ("jet-unquenched-hadrons",
         "Hadron cluster at the tip of the unquenched jet (many, bright, light blue)",
         [(1252, 100, 1325, 212)], PALEBLUE),
        ("jet-quenched-cone",
         "Quenched jet: cone going down-left. Long path -- it traverses nearly the "
         "whole medium, so it is desaturated, grey-blue and fades out",
         [(285, 395, 985, 772)], GREY),
        ("jet-quenched-hadrons",
         "Hadron cluster at the tip of the quenched jet (only 2-3, darker, grey)",
         [(300, 645, 372, 716)], DARKGREY),
        ("gluon-radiation",
         "Gluon bremsstrahlung: small yellow-green dots and swirls along the "
         "quenched jet, only inside the medium (this is the energy-loss mechanism)",
         [(688, 386, 968, 528)], LIME),
        ("beam-arrow",
         "Beam direction: short vertical double-headed arrow in the gap right of "
         "the medium",
         [(1058, 556, 1086, 688)], DARK),
    ],
}

# ★ 从 ("p","*") 按【像素判据】再切出嵌在兄弟元素里的小结构。
#   这里两个都是"嵌在介质大框里"的：胶子光点（介质内）与顶点星芒（介质内）。
#   不放进 SPLIT 也能靠 IoU 分对（它们的框小、色相与介质完全不同），
#   但介质里还有一圈**细网格线**（长而扁的连通域）会去抢小框 ——
#   所以按 evo3 的老经验，凡是"嵌在兄弟框里"的一律走 SPLIT 的像素判据。
SPLIT = {
    ("p", "*"): [
        ("gluon-radiation",
         "Gluon bremsstrahlung dots (yellow-green) along the quenched jet",
         ("huebox", [(688, 386, 968, 528)], (45, 105), 0.45)),
        ("vertex",
         "Hard-scattering starburst (bright yellow-white) at the dijet origin",
         ("brightbox", [(915, 355, 1015, 450)], 225)),
    ],
}

# 真渐变合并：本图实测**不用**（同 evo3：调色板够细时，真渐变反而更差 ——
# 渐变形状画的是"模型色"，与保留下来的台阶块（原图色）交界处又多出硬边）。
GRADIENTS = {}

# ★ 必须显式置空：groupvec 的 `getattr(P, "MANUAL", LB.MANUAL)` 在 --panels 没定义时
#   会退回 labels.py 里 T3-01 那张图的手工标签表，换图后会凭空多出鬼影标签。
MANUAL = []
FIX = {}
DROP = set()
ROTATED = []
EXTRA_ERASE = []

# ★ v2.7.1 的 PDF「纱窗」修正：不透明实色 path 加同色描边（1.0px），
#   否则四叉树切出的上万条紧贴矩形在 PDF 里各自抗锯齿，整片渐变浮起 1px 亮网格。
SEAM = {"*": 1.0}


def pixel_pred(a, spec):
    """SPLIT 用的像素判据（每一张图各不相同）。

    支持：
      ("huebox",   [框...], (hlo,hhi), satmin)  色相在区间内且饱和度 >= satmin
      ("brightbox",[框...], lummin)             亮度 >= lummin
      ("darkbox",  [框...], thr)                亮度 < thr
      ("satbox",   [框...], thr)                饱和度 > thr
      ("localdark",[框...], thr)                61x61 中值背景 - 亮度 > thr
    """
    import numpy as np
    kind = spec[0]
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]

    def _inbox(boxes):
        m = np.zeros(lum.shape, bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] = True
        return m

    if kind == "huebox":
        _, boxes, (hlo, hhi), smin = spec
        r, g, b = a[..., 0] / 255.0, a[..., 1] / 255.0, a[..., 2] / 255.0
        mx = np.max(a / 255.0, 2)
        mn = np.min(a / 255.0, 2)
        d = mx - mn
        h = np.zeros_like(mx)
        with np.errstate(divide="ignore", invalid="ignore"):
            h = np.where((d > 1e-6) & (mx == r), ((g - b) / np.maximum(d, 1e-9)) % 6, h)
            h = np.where((d > 1e-6) & (mx == g), (b - r) / np.maximum(d, 1e-9) + 2, h)
            h = np.where((d > 1e-6) & (mx == b), (r - g) / np.maximum(d, 1e-9) + 4, h)
        h *= 60.0
        sat = d / np.maximum(mx, 1e-9)
        return _inbox(boxes) & (h > hlo) & (h < hhi) & (sat > smin)
    if kind == "brightbox":
        _, boxes, thr = spec
        return _inbox(boxes) & (lum >= thr)
    if kind == "darkbox":
        _, boxes, thr = spec
        return _inbox(boxes) & (lum < thr)
    if kind == "satbox":
        _, boxes, thr = spec
        mx, mn = a.max(2), a.min(2)
        return _inbox(boxes) & ((mx - mn) / np.maximum(mx, 1e-6) > thr)
    if kind == "localdark":
        _, boxes, thr = spec
        from scipy import ndimage
        med = ndimage.median_filter(lum, size=61)
        return _inbox(boxes) & ((med - lum) > thr)
    raise ValueError("未知判据 %r" % (kind,))


# ---------------------------------------------------------------- 明度重写（整体改色）
# 为什么：逐像素临摹的产物**结构上必然是「一种颜色一条 <path>」**——图层虽然按物理
# 元素分了，元素内部还是"色素集合"，改色只能一条一条改，改不了"整个介质"/
# "整条被淬火喷注"。
# 开了下面这张表，元素被重写成
#     1 条基色块（或 1 条真渐变 body）+ 少量黑/白 fill-opacity 明暗层
# 于是「改基色块的 fill」= 整体改这个物理色块，而明暗层次（球面明暗、羽化）保留。
# 每条 = {"k": 基色个数(None=自适应) | "levels": 明度档数 | "gradient": 要不要试真渐变}
# 用法：raster_to_vector_semantic.py ... --shade auto:32
# ★ 这里定义了就**默认生效**（CLI 的 --shade 只是再加一个 "*" 默认档）。
#   要出「逐色临摹、最高保真」的那一版：置环境变量 NO_SHADE=1 再跑（见 README 对比表）。
import os as _os
SHADING = {} if _os.environ.get("NO_SHADE") else {
    # ★ 介质是**最大的一块**、也是人最可能想整体改色的（"把 QGP 介质换个色"）。
    #   默认 kmax=3 的"平涂基色 + 黑白明度层"拟合不过关（介质的色相跨度大：
    #   下缘暗红 -> 中部橙 -> 左上高光偏黄），实测被跳过、退回逐色。
    #   放宽到 kmax=6 / resid_cap=16 后能压成少数几个基色块 + 32 档明度层。
    # ★ 介质走**真渐变 body**（flat=False = 只算渐变模型，不算平涂模型）：
    #   平涂"基色 + 黑白明度层"在介质上会出斑块（实测 k=4x32 时介质内部
    #   出现成片"大陆"状色斑，肉眼可见）；真渐变 body 把那条平滑 ramp 交给
    #   <radialGradient>，明度层只补残差 —— 既能整体改色（改 gradient stops），
    #   又保住光滑。
    # ★ 真渐变 body 走不通：喷注横穿介质，介质掩膜被切成不连通（最大块只占 52.5%），
    #   gradfit 直接放弃（实测打印"掩膜不是单连通"）。所以介质只能用平涂模型 ——
    #   那就把明度档拉细（32 -> 64）压掉斑块。
    "medium": {"k": None, "kmax": 6, "levels": 64, "gradient": True,
               "resid_cap": 16.0, "grad_tol": 44, "nstops": 24, "rem_err": 60.0},
    "jet-unquenched-cone": {"k": None, "levels": 32, "gradient": True, "rem_err": 60.0},
    "jet-quenched-cone": {"k": None, "levels": 32, "gradient": True, "rem_err": 60.0},
    "jet-unquenched-hadrons": {"k": None, "levels": 24, "gradient": True, "rem_err": 60.0},
    "jet-quenched-hadrons": {"k": None, "levels": 24, "gradient": True, "rem_err": 60.0},
    "vertex": {"k": None, "levels": 16, "gradient": False, "rem_err": 60.0},
    "gluon-radiation": {"k": None, "kmax": 5, "levels": 16, "gradient": False,
                        "resid_cap": 14.0, "rem_err": 60.0},
    "beam-arrow": {"k": None, "levels": 8, "gradient": False, "rem_err": 60.0},
}


def _iou(A, B):
    x0, y0 = max(A[0], B[0]), max(A[1], B[1])
    x1, y1 = min(A[2], B[2]), min(A[3], B[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = float((x1 - x0) * (y1 - y0))
    ua = (A[2] - A[0]) * (A[3] - A[1]) + (B[2] - B[0]) * (B[3] - B[1]) - inter
    return inter / ua if ua > 0 else 0.0


def element_of(cid, bbox, rgb):
    """连通域 -> 物理元素：bbox 的 IoU 说话，颜色判据只加 0.22 的加成。"""
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
        # 兜底按 (距离, 框面积) 取最小：只看距离时整面板的 background 框
        # 会把所有落不进框的散块（描边抗锯齿碎片）全吞掉。
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
