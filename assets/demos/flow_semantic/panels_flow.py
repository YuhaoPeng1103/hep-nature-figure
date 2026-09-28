# -*- coding: utf-8 -*-
"""flow_panels.py —— 集体流示意图（IR: COLLECTIVE-FLOW-1）的语义版式表

基准坐标 = 源图 gen/chosen.png 的 1x 像素（1664 x 928）。
表里统一用 R(x0,y0,x1,y1) 把 1x 坐标换算到工作分辨率 W（默认 1200，
可用环境变量 FLOW_W 覆盖），所以换 --W 不用改这张表。

1) CELLS   : 左（初态）/ 中（连接箭头）/ 右（末态）三栏，铺满画布
2) ELEMENTS: 每个 cell 内的「物理元素」= (元素id, 人读说明, [命中框...], 颜色条件)
   - 归属规则：取色块的 bbox 与颜色，按顺序找第一个「框命中且颜色成立」的元素
   - 每个 cell 最后一项必须是兜底背景（框 = 整个 cell, 颜色 = ALL）
"""
import os

W = float(os.environ.get("FLOW_W", "1200"))
SRC_W = 1664.0
K = W / SRC_W


def R(x0, y0, x1, y1):
    """1x 源图坐标 -> 工作分辨率坐标"""
    return (int(round(x0 * K)), int(round(y0 * K)),
            int(round(x1 * K)), int(round(y1 * K)))


CELLS = [
    ("left",  "", "initial-state", R(0, 0, 790, 928),
     "初态：两核以冲击参数 b 错开、横向平面薄板、竖直拉长的初态火球、压强梯度箭头、b 尺寸线"),
    ("conn",  "", "connector", R(790, 0, 1010, 928),
     "中栏：初态 -> 末态的大箭头（anisotropic expansion）"),
    ("right", "", "final-state", R(1010, 0, 1664, 928),
     "末态：水平拉长的火球、径向流箭头、v2 = <cos 2phi> > 0 与面内/面外方向"),
]


def order():
    seen, o = set(), []
    for cid, *_ in CELLS:
        if cid not in seen:
            seen.add(cid)
            o.append(cid)
    return o


def meta():
    m = {}
    for cid, pan, role, rect, desc in CELLS:
        if cid not in m:
            m[cid] = dict(panel=pan, role=role, desc=desc, rects=[rect])
        else:
            m[cid]["rects"].append(rect)
    return m


def cell_index(H, Wd):
    import numpy as np
    idx = np.full((H, Wd), -1, np.int32)
    for i, (cid, pan, role, (x0, y0, x1, y1), d) in enumerate(CELLS):
        idx[y0:y1, x0:x1] = i
    return idx


# ===================== 颜色条件 =====================
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
GRAYISH = lambda c: _sat(c) < 0.14 and _lum(c) < 246      # 浅灰薄板 / 灰色虚线 / 尺寸线
BLUE = lambda c: _sat(c) > 0.18 and 190 <= _hue(c) <= 275  # 半透明灰蓝核
WARM = lambda c: _sat(c) > 0.14 and 15 < _hue(c) < 60      # 橙黄火球 / 橙色立体箭头


def DARK(t=150):
    return lambda c: _lum(c) < t                          # 黑色径向箭头 / 深灰大箭头


ELEMENTS = {
    "left": [
        ("nucleus-A", "入射核 A（半透明灰蓝球，左，网格经纬线）",
         [R(215, 285, 505, 615)], BLUE),
        ("nucleus-B", "入射核 B（半透明灰蓝球，右，与 A 的轮廓重叠）",
         [R(470, 285, 700, 620)], BLUE),
        ("fireball-initial", "初态火球：竖直拉长的杏仁形（ε₂ > 0）",
         [R(405, 285, 550, 590)], WARM),
        ("gradient-up", "面外向上（out-of-plane）的压强梯度 3D 箭头：短",
         [R(455, 245, 545, 350)], WARM),
        ("gradient-down", "面外向下的压强梯度 3D 箭头：短",
         [R(450, 550, 545, 665)], WARM),
        ("gradient-left", "面内向左（in-plane）的压强梯度 3D 箭头：长",
         [R(285, 420, 425, 485)], WARM),
        ("gradient-right", "面内向右的压强梯度 3D 箭头：长",
         [R(540, 420, 740, 485)], WARM),
        ("impact-param-b", "冲击参数 b 的尺寸线（两端箭头 + 竖直引出线）",
         [R(285, 660, 500, 710)], GRAYISH),
        ("reaction-plane-line", "反应平面：过两核圆心的水平虚线",
         [R(0, 436, 300, 466)], GRAYISH),
        ("axes-triad", "x / y / z 坐标三轴（z = beam）",
         [R(5, 595, 185, 800)], DARK(180)),
        ("plate-A", "横向平面薄板 A（有厚度的浅灰 3D 平板）",
         [R(180, 85, 780, 820)], GRAYISH),
        ("background", "白色背景（左栏兜底）", [R(0, 0, 790, 928)], ALL),
    ],
    "conn": [
        ("expansion-arrow", "初态 -> 末态的大箭头（各向异性膨胀）",
         [R(792, 405, 1000, 485)], DARK(180)),
        ("label-expansion", "「anisotropic expansion」文字块",
         [R(805, 475, 935, 545)], DARK(180)),
        ("background", "白色背景（中栏兜底）", [R(790, 0, 1010, 928)], ALL),
    ],
    "right": [
        ("fireball-final", "末态火球：水平拉长的椭圆（长轴相对初态转 90°）",
         [R(1070, 325, 1460, 585)], WARM),
        ("radial-arrows", "径向流箭头：面内明显长于面外（v₂ > 0）",
         [R(1075, 330, 1455, 580)], DARK(120)),
        ("phi-arrow", "方位角 φ 的参考箭头（从火球中心指向上-右）",
         [R(1215, 345, 1560, 500)], DARK(160)),
        ("out-of-plane-line", "面外（out-of-plane）方向竖直虚线",
         [R(1233, 262, 1260, 618)], GRAYISH),
        ("in-plane-line", "面内（in-plane）方向水平虚线",
         [R(1040, 438, 1615, 474)], GRAYISH),
        ("plate-B", "横向平面薄板 B（同一张平面、更晚时刻）",
         [R(1035, 20, 1545, 810)], GRAYISH),
        ("background", "白色背景（右栏兜底）", [R(1010, 0, 1664, 928)], ALL),
    ],
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
    全都对不上就退化成「包含它的最紧的框」。返回 (元素id, 人读说明)。"""
    els = ELEMENTS.get(cid)
    if not els:
        return None, None
    best, bs = None, 0.0
    for eid, label, boxes, cond in els:
        s = max(_iou(bbox, b) for b in boxes)
        v = cond(rgb)
        if v is True or v is False or type(v).__name__ == "bool_":
            s += 0.22 if v else 0.0
        else:
            s += float(v)
        if s > bs:
            bs, best = s, (eid, label)
    if best is None or bs < 0.10:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        bb, bk = els[-1][:2], (1e18, 1e18)
        for eid, label, boxes, cond in els:
            for (x0, y0, x1, y1) in boxes:
                dx = max(x0 - cx, 0.0, cx - x1); dy = max(y0 - cy, 0.0, cy - y1)
                k = ((dx * dx + dy * dy) ** 0.5, (x1 - x0) * (y1 - y0))
                if k < bk:
                    bk, bb = k, (eid, label)
        return bb
    return best


if __name__ == "__main__":
    import numpy as np
    m = meta()
    for cid in order():
        print(f"  {cid:8s} role={m[cid]['role']:14s} cells={len(m[cid]['rects'])} "
              f"元素={len(ELEMENTS.get(cid, []))}")
    H = int(round(928 * W / SRC_W)); Wd = int(round(W))
    cnt = np.zeros((H, Wd), np.int32)
    for cid, pan, role, (x0, y0, x1, y1), d in CELLS:
        cnt[y0:y1, x0:x1] += 1
    print("\n版面检查 @ %dx%d: 未覆盖 = %d, 重叠 = %d (都应为 0)"
          % (Wd, H, int((cnt == 0).sum()), int((cnt > 1).sum())))

# ===================== 可选表（本图都不需要） =====================
SPLIT = {}      # 元素内部再按像素切子元素：本图色块已按颜色分得开，不需要
FIX = {}        # OCR 错字修正：flow_words.txt 里已直接写对
DROP = set()    # 要丢弃的元素 id：无
MANUAL = {}     # 手工指定的元素：无

# EXTRA_ERASE：拟合用「紧框」时，紧框外沿剩下的原字墨迹要补擦一块。
# v_{2} = <cos 2phi> > 0 的拟合框只取到 2x y=616（收紧才能通过 dh 验收），
# 原图下标「2」与 <phi> 的顶部在 y 604~616，不补擦会在成品里留下残迹。
EXTRA_ERASE = [R(1424, 298, 1618, 336)]
