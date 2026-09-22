# -*- coding: utf-8 -*-
"""labels.py —— 文字层（可编辑的真 <text>）

关键设计：**用与成品完全相同的渲染器（cairo/cairosvg）做对齐与自校验**。
用 PIL「200px 大图再降采样」当代理会系统性放大笔画、把字号估大 ~5%，
导致 SVG 里文字整体错位（旧 t301_trace_v5.svg / t301.svg 就吃了这个亏）。

  · FIX    : OCR 错字修正表   raw -> 富文本("_{}"=下标, "^{}"=上标)
  · DROP   : 丢弃的 OCR 碎片（公式被切碎后的残片，留在矢量临摹层，不写成文字）
  · MANUAL : OCR 漏检的手工标签（粗体面板标号 a / b / c1 / d1 / c2 / d2 / e）

★ FIX / DROP / MANUAL 这三张表是**每张图各不相同**的：换一张图就要照 OCR 结果重写。
  FIX   修 OCR 错字（lnitial->Initial、Quark-GIuon->Quark-Gluon、PIasma->Plasma …）
  DROP  丢公式碎片（被 OCR 切开的小方块，留在矢量临摹层，不写成文字）
  MANUAL 补 OCR 漏掉的粗体面板标号（用连通域量出墨迹框）
"""
import re
import numpy as np
from fontTools.ttLib import TTFont
import cairosvg
import cairocffi as cairo

from . import fonts
FONT_R, FAM_R = fonts.pick(False)      # 量字宽用的字体 == SVG 里 font-family 的单值
FONT_B, FAM_B = fonts.pick(True)
FONT_M, FAM_M = fonts.pick_math()      # 数学符号兜底字体（⊥ ≳ 这类主字体没有的字）
SUB_S, SUB_Y = 0.66, 0.20       # 下标：字号比例 / 下移(em)
SUP_S, SUP_Y = 0.66, 0.34       # 上标：字号比例 / 上移(em)

FIX = {
    "lnitial": "Initial",
    "Quark-GIuon": "Quark-Gluon",
    "PIasma": "Plasma",
    "Of": "of",
    "Headon": "Head-on",
    "fIOW": "flow",
    "Area": "Area:",
    "Ellipticity.": "Ellipticity:",
    "Triangularity.": "Triangularity:",
    "SOI)": "S(\u03b7)",
    "S301)": "\u03b5_{3}(\u03b7)",
    "sph": "_{Sph}",
}

DROP = {
    "\u4ee4", "\u98e0", "\uff09", "\u3009", "\u201c", "\u00b7", "+", "1", "2", "0", "ow",
    "\u4ee42\uff09", "(", ")", "\u3008", "\u3009",
    "CI", "C2",
}

MANUAL = [
    ("a",   233,  94,  243, 106, True),
    ("b",   521,  90,  532, 106, True),
    ("c1",  132, 463,  151, 476, True),
    ("d1",  541, 460,  561, 476, True),
    ("c2",  136, 871,  158, 885, True),
    ("d2",  546, 879,  569, 895, True),
    ("e",   939, 731,  950, 743, True),
]

_TOK = re.compile(r"([_^])\{([^}]*)\}")


def parse(s):
    out, i = [], 0
    for m in _TOK.finditer(s):
        if m.start() > i:
            out.append((s[i:m.start()], "n"))
        out.append((m.group(2), "sub" if m.group(1) == "_" else "sup"))
        i = m.end()
    if i < len(s):
        out.append((s[i:], "n"))
    return [(t, k) for t, k in out if t]


def plain(runs):
    return "".join(t for t, _ in runs)


_hm = {}
_CUR = [None, None]     # 当前标签用的 [字体文件, font-family]；None,None = 用主字体


def set_fam(path, fam):
    """切换「当前标签」用的字体。主字体缺字时由 groupvec 调成兜底字体。"""
    _CUR[0], _CUR[1] = path, fam


def _font(bold=False):
    if _CUR[0]:
        return _CUR[0], _CUR[1]
    return (FONT_B, FAM_B) if bold else (FONT_R, FAM_R)


def _cmap(path):
    """按**字体文件**缓存度量 —— 主字体与兜底字体的 hmtx 不能混用，
       否则「量字宽的字体 != SVG 里写的字体」，字距会歪（fonts.py 里记的那个坑）。"""
    if path not in _hm:
        t = TTFont(path)
        _hm[path] = (t.getBestCmap(), t["hmtx"], t["head"].unitsPerEm)
    return _hm[path]


def _metrics(bold=False):
    return _cmap(_font(bold)[0])


def char_em(c, bold=False):
    cm, hmtx, up = _metrics(bold)
    g = cm.get(ord(c))
    return (hmtx[g][0] if g else up * 0.55) / up


def has_glyph(c, bold=False):
    return ord(c) in _metrics(bold)[0]


def can_render(runs, bold=False):
    """主字体全有 -> True；主字体缺字但兜底字体全有 -> True；都缺 -> False"""
    txt = plain(runs)
    if all(ord(c) in _cmap(FONT_B if bold else FONT_R)[0] for c in txt):
        return True
    return bool(FONT_M) and all(ord(c) in _cmap(FONT_M)[0] for c in txt)


def choose_fam(runs, bold=False):
    """这个标签该用的 (字体文件, font-family 单值)。主字体缺字就换兜底字体。"""
    txt = plain(runs)
    if all(ord(c) in _cmap(FONT_B if bold else FONT_R)[0] for c in txt):
        return (FONT_B, FAM_B) if bold else (FONT_R, FAM_R)
    if FONT_M and all(ord(c) in _cmap(FONT_M)[0] for c in txt):
        return FONT_M, FAM_M
    return (FONT_B, FAM_B) if bold else (FONT_R, FAM_R)


def width_em(runs, bold=False, ss=SUB_S):
    w = 0.0
    for t, k in runs:
        sc = 1.0 if k == "n" else ss
        for c in t:
            w += char_em(c, bold) * sc
    return w


def xml_esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _offsets(k, size, ls, ss, sy):
    if k == "n":
        return size, 0.0
    if k == "sub":
        return size * ss, sy * size
    return size * ss, -sy * size * 1.6


def text_el(runs, size, x, y, ls, ss, sy, bold, fill="#000000", eid=None, extra=""):
    """生成一个真 <text>；下标/上标用 <tspan dy>（浏览器/Illustrator 都支持，文字仍可自由重排）"""
    parts, cur = [], 0.0
    for t, k in runs:
        fo, off = _offsets(k, size, ls, ss, sy)
        parts.append('<tspan font-size="%.2f" dy="%.2f">%s</tspan>' % (fo, off - cur, xml_esc(t)))
        cur = off
    ida = ' id="%s"' % eid if eid else ""
    fw = ' font-weight="bold"' if bold else ""
    fam = _font(bold)[1]
    return ('<text%s x="%.2f" y="%.2f"%s%s font-family="%s" font-size="%.2f" '
            'letter-spacing="%.3f" fill="%s">%s</text>'
            % (ida, x, y, fw, extra, fam, size, ls * size, fill, "".join(parts)))


def svg(res, runs, color, bold=False, elem_id=None, extra=""):
    _, size, xl, bl, ls, ss, sy = res[:7]
    return text_el(runs, size, xl, bl, ls, ss, sy, bold, color, elem_id, extra)


def rot_el(r, elem_id=None, fill="#000000"):
    """旋转标签 → 真 <text>（带 rotate 变换，仍可编辑、可重排）。

    ★ 两条路径：
      - r["fit"] 存在（align_rot 拟合成功）：位置/字距/上下标全部交给 text_el，
        用的就是「转正坐标系」的拟合值。SVG 是「先按 x/y 排版、再整体 rotate」，
        与「先把图转正、再拟合」完全等价，所以坐标可以直接拿来用。
      - 没有 fit：退回手量摆位 —— 文字居中放在框心 + 0.35em，再绕框心转过去。
    ★ 不用 dominant-baseline（cairosvg 会忽略，和 baseline-shift 一个毛病）。
    """
    x0, y0, w, h = r["box"]
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    size = float(r["size"])
    txt = xml_esc(r["txt"])
    ida = ' id="%s"' % elem_id if elem_id else ""
    fit = r.get("fit")
    if fit:
        xl, bl, ls, ss, sy = fit
        runs = r.get("runs") or parse(r["txt"])
        return text_el(runs, size, xl, bl, ls, ss, sy, r.get("bold", False),
                       fill=fill, eid=elem_id,
                       extra=' transform="rotate(%.2f %.2f %.2f)"'
                             ' data-plain="%s"' % (r["ang"], cx, cy, txt))
    runs = r.get("runs") or parse(r["txt"])
    # 按字宽把文字水平居中到框心；上下标仍走 text_el 的 <tspan>，
    # 否则 "Large ε_{2} small d_{⊥}" 会把 _{2} 字面画出来（实测大坑）
    half = width_em(runs, r.get("bold", False)) * size / 2.0
    return text_el(runs, size, cx - half, cy + 0.35 * size, 0.0, SUB_S, SUB_Y,
                   r.get("bold", False), fill=fill, eid=elem_id,
                   extra=' transform="rotate(%.2f %.2f %.2f)"'
                         ' data-plain="%s"' % (r["ang"], cx, cy, txt))


def derotate(a, cx, cy, ang):
    """绕 (cx,cy) 把图画 ang 度（PIL 逆时针为正），让「SVG 里 rotate(ang) 排出的
       斜排文字」变回水平 —— 这样才能借用 align() 的水平墨迹模型。"""
    from PIL import Image
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    r = im.rotate(ang, center=(cx, cy), resample=Image.BICUBIC,
                  fillcolor=(255, 255, 255))
    return np.asarray(r).astype(np.float32)


def _text_band(prof, hband):
    """在行剖面里挑出「文字所在的行带」：固定高度的滑窗取墨迹总量最大的一窗。

    斜排标签常紧挨着同角度的长直线（箭头 / 等离子体板边），转正后它们正好落在
    同一段行里。长直线只有 2~3 行、单行计数极高，但 15 行文字的总墨迹量更大，
    所以按「窗内总墨迹」而不是「单行峰值」来选，就能把直线排除掉。
    """
    n = int(len(prof))
    if n <= hband:
        lo, hi = 0, n
    else:
        csum = np.concatenate([[0.0], np.cumsum(prof.astype(float))])
        best, lo, hi = -1.0, 0, hband
        for y in range(0, n - hband + 1):
            s = csum[y + hband] - csum[y]
            if s > best:
                best, lo, hi = s, y, y + hband
    thr = 0.30 * max(1.0, float(prof[lo:hi].max()))
    while lo > 0 and prof[lo - 1] >= thr:
        lo -= 1
    while hi < n and prof[hi] >= thr:
        hi += 1
    return lo, hi


def align_rot(a, box, ang, runs, bold=False, half=30.0, extra=80.0, hband=17,
              ascan=6.0, astep=2.0):
    """斜排标签对齐：先把图绕框心转正，再用 align() 同一套三段式拟合。

    转正后文字水平，align 的「字号<-墨迹高 / 字距<-墨迹宽 / 位置<-残差」三段式
    才成立。两个必须做的预处理：

    ① 角度微调：手量的角度常有 2~6° 误差（同一张图上两条「平行」标签实测差了
       3.4°）。角度一歪，长文字会被「摊」成十几行，字号随之被估大。
       ★ 判据直接用 align() 的实际墨迹残差（外加 dh 惩罚），不要用几何启发式 ——
       「行带最矮」和「行带墨迹最多」会互相打架，实测把 43° 带偏到 50°。
    ② 行带检测：斜排标签紧挨着同角度的长直线（箭头 / 等离子体板边），转正后
       落在同一段行里，会把墨迹高 oh 撑大。用 _text_band() 按「窗内总墨迹」
       挑出文字那十几行，把直线排掉。

    返回 (res, ang_used)：res 与 align() 相同，(xl, bl) 在「转正坐标系」，
    等价于 SVG 里 <text x=xl y=bl transform="rotate(ang_used cx cy)"> 的排版坐标。
    """
    x0, y0, w, h = box
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    H, W = a.shape[:2]
    L = max(w, h) + extra
    bx0, by0 = max(0, int(cx - L / 2.0)), max(0, int(cy - half))
    bx1, by1 = min(W, int(cx + L / 2.0)), min(H, int(cy + half))
    if bx1 <= bx0 or by1 <= by0:
        return None
    best = None
    for da in np.arange(-ascan, ascan + 0.001, astep):
        ag = float(ang + da)
        a_rot = derotate(a, cx, cy, ag)
        m = ((255.0 - a_rot[by0:by1, bx0:bx1].mean(2)) / 255.0) > THR
        if not m.any():
            continue
        lo, hi = _text_band(m.sum(1), hband)
        nz = np.nonzero(m[lo:hi].sum(0))[0]
        if len(nz) == 0:
            continue
        px0, py0 = bx0 + int(nz.min()) - 5, by0 + lo - 3
        px1, py1 = bx0 + int(nz.max()) + 6, by0 + hi + 3
        res = align(a_rot, (px0, py0, px1 - px0, py1 - py0), runs, bold=bold)
        if res is None:
            continue
        score = res[0] + 0.004 * res[7]["dh"]
        if best is None or score < best[0]:
            best = (score, res, ag)
    if best is None:
        return None
    return best[1], best[2]



def rot_mask(shape, box, ang, rect, ink=None, pad=2):
    """把「转正坐标系里的墨迹矩形」映射回原图，得到**旋转后的四边形**掩码。

    斜排标签的擦除必须用它，不能用轴对齐包围盒：两条平行标签的 AABB 必然互相
    重叠，用 AABB 去擦会把旁边那条擦掉半截（实测在 Low-energy 旁边留下一个
    "on" 碎片，另一条则被整个擦掉、文字画了两遍）。
    """
    from PIL import Image
    H, W = shape
    x0, y0, w, h = box
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    m = np.zeros((H, W), np.uint8)
    ry0, ry1 = max(0, int(rect[1]) - pad), min(H, int(rect[3]) + pad)
    rx0, rx1 = max(0, int(rect[0]) - pad), min(W, int(rect[2]) + pad)
    if ry1 <= ry0 or rx1 <= rx0:
        return np.zeros((H, W), bool)
    m[ry0:ry1, rx0:rx1] = 255
    m = np.asarray(Image.fromarray(m).rotate(-ang, center=(cx, cy),
                                            resample=Image.NEAREST, fillcolor=0))
    out = m > 127
    if ink is not None:
        from scipy import ndimage
        out = out & ndimage.binary_dilation(ink, iterations=1)
    return out



def rot_box_fit(box, ang, rect):
    """把「转正坐标系」里拟合出的墨迹矩形映射回原图的轴对齐包围盒（擦除用）；
       保证擦掉的正是拟合后的实际位置，而不是手量框的位置。"""
    x0, y0, w, h = box
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    th = np.radians(ang)
    c, s = float(np.cos(th)), float(np.sin(th))
    xs, ys = [], []
    for px, py in ((rect[0], rect[1]), (rect[2], rect[1]),
                   (rect[2], rect[3]), (rect[0], rect[3])):
        dx, dy = px - cx, py - cy
        xs.append(cx + dx * c - dy * s)
        ys.append(cy + dx * s + dy * c)
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


# ================================================================ 栅格化 / 度量
def _raster(svg, W_, H_):
    import io
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=W_, output_height=H_)
    return np.asarray(Image.open(io.BytesIO(png)).convert("L"), np.float32)


def _grid(cands, runs, bold, W_, H_, ox, oy):
    """N 个候选各占一格 W_ x H_，格内文字位置 = (ox, oy)。返回 (N*H_, W_) 灰度图。
       cairo 单张 surface 有尺寸上限，故分块渲染再拼接。"""
    if not cands:
        return np.zeros((0, W_), np.float32)
    MX = 26000
    per = max(1, MX // max(1, H_))
    outs = []
    for b0 in range(0, len(cands), per):
        blk = cands[b0:b0 + per]
        N = len(blk)
        L = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">' % (W_, H_ * N),
             '<rect width="%d" height="%d" fill="#ffffff"/>' % (W_, H_ * N)]
        for i, (sz, xl, bl, ls, ss, sy) in enumerate(blk):
            L.append(text_el(runs, sz, xl - ox, bl - oy + i * H_, ls, ss, sy, bold))
        L.append('</svg>')
        outs.append(_raster("\n".join(L), W_, H_ * N))
    return np.concatenate(outs, 0)


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def word_box(box, W, H):
    x, y, w, h = box
    x0 = max(0, int(x) - 12); x1 = min(W, int(np.ceil(x + w)) + 12)
    y0 = max(0, int(y) - 10); y1 = min(H, int(np.ceil(y + h)) + 10)
    return x0, y0, x1, y1


# ================================================================ 对齐主流程
THR = 0.30          # 墨迹阈值（对原图与渲染一视同仁，避免偏袒较细的笔画）


def align(a, box, runs, bold=False, bl_hint=None, raw_runs=None):
    """三段式对齐（避免「少画字」取巧 —— 长词在整数化字距下无法逐像素重合，
       若直接用 |渲染-墨迹| 选字号，会一路选到最小：

         ① 字号  <- 渲染墨迹高度 == 原图墨迹高度
         ② 字距  <- 渲染墨迹宽度 == 原图墨迹宽度
         ③ 位置  <- 在①②固定下最小化墨迹重叠残差（字号不再参与）

       返回 (残差, size, x_left, baseline, letter_spacing, sub_scale, sub_dy, meta)
       meta = dict(dw=, dh=, ink=) 供几何验收。"""
    H, W = a.shape[:2]
    x, y, w, h = box
    x0, y0, x1, y1 = word_box(box, W, H)
    if x1 <= x0 or y1 <= y0:
        return None
    cw, ch = x1 - x0, y1 - y0
    ink = (255.0 - a[y0:y1, x0:x1].mean(2)) / 255.0
    tx0 = max(0, int(x) - x0); ty0 = max(0, int(y) - y0)
    tx1 = min(cw, int(np.ceil(x + w)) - x0 + 1); ty1 = min(ch, int(np.ceil(y + h)) - y0 + 1)
    ob = _bbox(ink[ty0:ty1, tx0:tx1] > THR)
    if ob is None:
        return None
    ob = (ob[0] + tx0, ob[1] + ty0, ob[2] + tx0, ob[3] + ty0)   # 换算回画布坐标
    ow, oh = ob[2] - ob[0] + 1, ob[3] - ob[1] + 1
    nglyph = max(1, len(plain(runs)) - 1)
    s0 = w / max(width_em(runs, bold=bold), 1e-6)
    has_shift = any(k != "n" for _, k in runs)

    # ---- ① 字号（+ 上下标比例/位移）：渲染墨迹尺寸匹配 ----
    MW, MH = int(2.4 * w) + 40, int(3.4 * h) + 40
    MOX, MOY = 12.0, MH * 0.66
    if has_shift:
        sizes = s0 * np.linspace(0.74, 1.30, 20)
        grid = [(SUB_S, SUB_Y)]              # 上下标用排版常规值，不参与拟合（否则会被"少画字"带偏）
    else:
        sizes = s0 * np.linspace(0.74, 1.30, 32)
        grid = [(SUB_S, SUB_Y)]
    cands = [(sz, MOX, MOY, 0.0, ss, sy) for (ss, sy) in grid for sz in sizes]
    arr = _grid(cands, runs, bold, MW, MH, 0.0, 0.0)
    bs = None
    for i, (sz, _, _, _, ss, sy) in enumerate(cands):
        bb = _bbox((255.0 - arr[i * MH:(i + 1) * MH]) / 255.0 > THR)
        if bb is None:
            continue
        rw, rh = bb[2] - bb[0] + 1, bb[3] - bb[1] + 1
        cost = abs(rh - oh) + 0.35 * abs(rw - ow)          # 高度为主、宽度为辅
        if bs is None or cost < bs[0]:
            bs = (cost, sz, ss, sy, rw, rh, bb)
    if bs is None:
        return None
    _, size, ss, sy, rw, rh, bb = bs
    lsb = bb[0] - MOX
    desc = bb[3] - MOY

    # ---- ② 字距：渲染墨迹宽度 == 原图墨迹宽度 ----
    #     用「原始 OCR 字串」测：修正表可能增删字符（Area->Area:），
    #     拿新字串的宽度去套旧墨迹宽度会把字距压扁、补的字跑到左边去。
    ref_runs = raw_runs if raw_runs is not None else runs
    ref_txt = plain(ref_runs)
    if len(ref_txt) >= 5:
        arr2 = _grid([(size, MOX, MOY, 0.0, ss, sy)], ref_runs, bold, MW, MH, 0.0, 0.0)
        bb2 = _bbox((255.0 - arr2[:MH]) / 255.0 > THR)
        rw_ref = (bb2[2] - bb2[0] + 1) if bb2 else rw
        ls_em = float(np.clip((ow - rw_ref) / max(1, len(ref_txt) - 1) / size, -0.05, 0.05))
    else:
        ls_em = 0.0
    x_est = (x0 + ob[0]) - lsb
    bl_est = (y0 + ob[3]) - desc
    if bl_hint is not None:
        bl_est = float(bl_hint)

    # ---- ③ 位置（字号固定，只微调字距）----
    def resid(cs):
        A = _grid(cs, runs, bold, cw, ch, x0, y0)
        return [float(np.abs((255.0 - A[i * ch:(i + 1) * ch]) / 255.0 - ink).mean())
                for i in range(len(cs))]

    best = None
    c1 = [(size, x_est + dx, bl_est + db, ls_em + dl, ss, sy)
          for dl in (-0.02, -0.01, 0.0, 0.01, 0.02)
          for db in (-1.5, -0.75, 0.0, 0.75, 1.5)
          for dx in (-1.5, -0.75, 0.0, 0.75, 1.5)]
    for d, c in zip(resid(c1), c1):
        if best is None or d < best[0]:
            best = (d,) + c
    _, size, xl, bl, ls, ss, sy = best
    c2 = [(size * f, xl + dx, bl + db, ls + dl, ss, sy)
          for f in (0.996, 1.0, 1.004)
          for db in (-0.35, 0.0, 0.35) for dx in (-0.35, 0.0, 0.35)
          for dl in (-0.006, 0.0, 0.006)]
    for d, c in zip(resid(c2), c2):
        if d < best[0]:
            best = (d,) + c
    d, size, xl, bl, ls, ss, sy = best

    # ---- 几何验收用的量 ----
    A = _grid([(size, xl, bl, ls, ss, sy)], runs, bold, cw, ch, x0, y0)
    fb = _bbox((255.0 - A[:ch]) / 255.0 > THR)
    if fb is None:
        return None
    fw, fh = fb[2] - fb[0] + 1, fb[3] - fb[1] + 1
    # rect = 渲染文字的墨迹框；irect = **原图**文字的墨迹框。擦字必须用两者的并集：
    # 只擦 rect 的话，拟合文字比原字略窄时，原字右侧的笔画会整段留下（实测在
    # "Low-energy method" 右端留下一个像 "!" 的残影）。
    meta = dict(dw=abs(fw - ow), dh=abs(fh - oh), ink=float(ink.mean()),
                rect=(x0 + fb[0], y0 + fb[1], x0 + fb[2] + 1, y0 + fb[3] + 1),
                irect=(x0 + ob[0], y0 + ob[1], x0 + ob[2] + 1, y0 + ob[3] + 1))
    return float(d), float(size), float(xl), float(bl), float(ls), float(ss), float(sy), meta
