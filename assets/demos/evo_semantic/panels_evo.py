# -*- coding: utf-8 -*-
"""panels_evo.py -- 「形变核 -> 量子涨落 -> 碰撞 -> QGP 火球」四阶段演化链
（gen/render_s31_clean.png，1662x925）的版式/元素表。

每条 ELEMENTS 项 = 一个**物理元素**：人能在 Illustrator 图层面板里按名字点选、
单独改它。框全部是**量出来的**（连通域 + 颜色掩膜），不是估的：

  四个阶段的框  = 亮度<240 的连通域里 >12000px 的那四个
                  （measure_stages.py 同一套判据，与三个箭头一起一次量出）
  三个箭头      = 同一次连通域分析里 1200..12000px 的那三个（全部指向右）
  核子圆 / 交叠透镜 / 火球内核子 = 颜色掩膜，见下面 SPLIT 的注释

另外这个版式表声明了 `GRADIENTS`（球面明暗 / 火球辉光合并成真 <gradient>）——
理由与实测数字见那一段的注释。

坐标系 = 工作分辨率坐标（--W 1662，与源图 1:1）。

为什么 stage1-nucleons / stage3-overlap / stage4-nucleons **只**出现在 SPLIT 里、
不写进 ELEMENTS：
  它们的框整个嵌在同一个"兄弟"元素的框内部（核子圆在核里、透镜在两核之间、
  火球内核子在火球里）。element_of 是**按整个连通域的 bbox 算 IoU** 命名的，
  把它们也列进 ELEMENTS，穿过那块小框的**本体网格细线**（bbox 又长又扁，
  与小框的 IoU 反而高于与本体大框的 IoU）就会被它们抢走 —— 实测面板里
  这样的细线有 3~4 条。改成只用 SPLIT 按**像素判据**切，网格线就留在本体里。
"""
CELLS = [
    ("p", "p", "schematic", (0, 0, 1662, 925),
     "Deformed nucleus -> quantum fluctuations -> collision -> QGP fireball: "
     "four-stage evolution chain of a heavy-ion collision, left to right"),
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


# ── 颜色判据（只给 IoU 加一个 0.22 的加成，不是硬门限）──
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


PALE = lambda c: 0.22 if _lum(c) >= 246 else 0.0                       # noqa: E731
GREY = lambda c: 0.22 if (_sat(c) < 0.12 and 40 < _lum(c) < 246) else 0.0   # noqa: E731
ORANGE = lambda c: 0.22 if (_sat(c) > 0.55 and 5 < _hue(c) < 32) else 0.0   # noqa: E731
DARK = lambda c: 0.22 if _lum(c) < 115 else 0.0                        # noqa: E731
ANY = lambda c: 0.0                                                    # noqa: E731

# 顺序 = 图层输出顺序；前三阶段是**同一个核**的三种形态，所以共用 GREY 判据
# （灰白低饱和 —— 不给任何颜色加分也一样靠 IoU 决胜；写死别的判据只会假警报）。
ELEMENTS = {
    "p": [
        ("background", "Panel background (white)", [(0, 0, 1662, 925)], PALE),
        ("stage1-nucleus",
         "Stage 1: one deformed nucleus (tilted ellipsoid with surface mesh)",
         [(55, 223, 273, 515)], GREY),
        ("stage2-fluctuations",
         "Stage 2: quantum fluctuations -- the same nucleus in three "
         "orientations (three overlapping ellipses)",
         [(471, 237, 723, 509)], GREY),
        ("stage3-nucleus-A",
         "Stage 3: projectile nucleus A, left lobe of the colliding pair",
         [(858, 285, 1061, 466)], GREY),
        ("stage3-nucleus-B",
         "Stage 3: target nucleus B, right lobe of the colliding pair",
         [(1004, 314, 1212, 476)], GREY),
        ("stage4-fireball",
         "Stage 4: QGP fireball (orange radial-gradient disc)",
         [(1343, 221, 1642, 543)], ORANGE),
        ("arrow-1", "Evolution arrow 1 (stage 1 -> 2, thick, pointing right)",
         [(311, 358, 409, 410)], DARK),
        ("arrow-2", "Evolution arrow 2 (stage 2 -> 3, thick, pointing right)",
         [(738, 359, 832, 411)], DARK),
        ("arrow-3", "Evolution arrow 3 (stage 3 -> 4, thick, pointing right)",
         [(1233, 361, 1324, 412)], DARK),
    ],
}

# ★ 从 ("p","*")（整面板）按【像素判据】捞出三个子结构。
#   每个判据都是**实测**出来的，量测脚本见 fig_evo/README.md：
#     stage1-nucleons  中位背景-亮度 > 35，落在核子圆那 100x91 的框里
#                      实测 3 个圆 = (105,324,143,362)/(167,319,204,358)/(136,370,174,409)，
#                      半径 ~19px，合计 3658px
#     stage3-overlap   饱和度 > 0.25 且落在透镜框里 —— 实测 4263px，
#                      透镜框 (1004,332,1061,445) = 58x114（竖直透镜 ✓）
#     stage4-nucleons  蓝通道 > 60（火球本体的 B 通道实测 = 0，球面填充 = 85，
#                      交叠灰 = 141）+ 落在内核子那 153x154 的框里 —— 实测 18273px
SPLIT = {
    ("p", "*"): [
        ("stage1-nucleons",
         "Stage 1: nucleons inside the deformed nucleus (three grey discs)",
         ("localdark", [(105, 319, 205, 410)], 35)),
        ("stage3-overlap",
         "Stage 3: overlapping (participating) matter -- vertical lens",
         ("satbox", [(1004, 332, 1062, 446)], 0.25)),
        ("stage4-nucleons",
         "Stage 4: nucleons inside the fireball (four overlapping discs)",
         ("innercluster", [(1420, 323, 1585, 489)])),
    ],
}

# ★ 真渐变合并：这些元素的大片**平滑渐变**（球面明暗 / 火球径向辉光）不再让四叉树
#   压成色阶台阶 —— 先按 gradfit.py 的三种模型拟合，残差过关就把台阶色块丢掉、
#   换一条真 <radialGradient>/<linearGradient> 的形状。实测（--q 16）：
#     不合并时形变核本体里有 25793px 的 b-r>=6 偏蓝像素被量化成互不连通的"蓝斑"，
#     火球则是一圈圈同心色阶环；合并后这两个都消失。
#   残差不过关（<tol 视为平坦，>tol 视为"不是干净渐变"）就自动放弃、保留台阶 ——
#   所以这里宁可多列几个元素，让实测说话。
# ★ 真渐变合并（可选能力，本图实测**不用**）：
#   gradfit.py 能把大片平滑渐变拟合成真 <radialGradient>/<linearGradient>
#   （算法与用法见 scripts/raster_vector/gradfit.py）。但本图实测：一旦调色板够细，
#   真渐变反而**更差** —— 原因很实在：渐变形状画的是“模型色”（残差 5.9~8.6 级），
#   而保留下来的台阶块画的是“原图色”，两者交界处又多出硬边；
#   模型误差本身又是低频的，于是整个球面出现成片的“斑块”
#   （人眼对平色区里的低频偏差比细碎噪声敏感得多）。
#   同一张源图、同一套参数（R=5, --q 32）实测：
#     真渐变全开：MAE 1.213 |>8 2.00%| 平滑体贴边比 1.39（stage1 2.12）
#     真渐变全关：MAE 1.048 |>8 0.75%| 平滑体贴边比 1.02（stage1 1.40）
#   → 所以 GRADIENTS 置空。仅在**粗调色板**（--q <= 16）需要救地板色阶时才按元素打开，
#     写 dict(nstops=, tol=, minpx=, drop_tol=) 即可（键 = 下面 ELEMENTS 里的元素名）。
GRADIENTS = {}

# ★ 必须显式置空：groupvec 的 `getattr(P, "MANUAL", LB.MANUAL)` 在 --panels 没定义时
#   会退回 labels.py 里 **T3-01 那张图** 的手工标签表，换图后会凭空多出鬼影标签。
MANUAL = []
FIX = {}
DROP = set()
ROTATED = []
EXTRA_ERASE = []


def pixel_pred(a, spec):
    """SPLIT 用的像素判据（**每一张图各不相同**）。

    支持：
      ("darkbox",     [框...], thr)  亮度 < thr
      ("satbox",      [框...], thr)  饱和度 > thr
      ("localdark",   [框...], thr)  61x61 中值背景 - 亮度 > thr（抓"局部更暗的圆盘"，
                                     核子圆与本体明暗的**亮度区间重叠**，纯阈值切不开）
      ("innercluster",[框...])       B>60 & R>90（球面填充/交叠灰）或 饱和度<0.35
                                     （球面描边），且亮度<235（排除白底）
      ("dark"|"pale", thr)           全画布亮度阈值

    框是 (x0,y0,x1,y1)，半开区间。"""
    import numpy as np
    kind = spec[0]
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]

    def _inbox(boxes):
        m = np.zeros(lum.shape, bool)
        for (x0, y0, x1, y1) in boxes:
            m[y0:y1, x0:x1] = True
        return m

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
    if kind == "innercluster":
        _, boxes = spec
        r, b = a[..., 0], a[..., 2]
        mx, mn = a.max(2), a.min(2)
        sat = (mx - mn) / np.maximum(mx, 1e-6)
        return _inbox(boxes) & (((b > 60) & (r > 90)) | (sat < 0.35)) & (lum < 235)
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
        s += float(cond(rgb))
        if s > bs:
            bs, best = s, (eid, label)
    if best is None or bs < 0.10:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        # ★ 兜底按 (距离, 框面积) 取最小：只看距离时整面板的 background 框
        #   会把所有落不进框的散块（描边抗锯齿碎片）全吞掉。
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


# ---------------------------------------------------------------- 明度重写（可选）
# 为什么：逐像素临摹的产物**结构上必然是「一种颜色一条 <path>」**（实测本图
# stage1-nucleus 5162 条 path = 5162 种 fill，stage4-fireball 6696 = 6696）。
# 图层虽然按物理元素分了，但元素内部还是"色素集合"—— 改色只能一条一条改，
# 改不了"整个火球"。开了下面这张表，元素会被重写成
#     1 条基色块 / 1 条真渐变 body（整体改色的把手）+ 少量黑/白 fill-opacity 明暗层
# 实测（--q 0 --R 5，见 README 的「可编辑版」表）：
#     31005 条 path -> 1411 条，全图 MAE 0.626 -> 0.898
# 关掉（删掉这张表）就回到逐色临摹的原样输出。
# 每条 = {"k": 基色个数(None=自适应) | "levels": 明度档数 | "gradient": 要不要试真渐变}
SHADING = {
    "*": {"k": None, "levels": 16, "gradient": True,
          "grad_tol": 26, "grad_minpx": 800, "rem_err": 60.0},
}
