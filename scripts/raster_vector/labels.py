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


def _metrics(bold):
    if bold not in _hm:
        t = TTFont(FONT_B if bold else FONT_R)
        _hm[bold] = (t.getBestCmap(), t["hmtx"], t["head"].unitsPerEm)
    return _hm[bold]


def char_em(c, bold=False):
    cm, hmtx, up = _metrics(bold)
    g = cm.get(ord(c))
    return (hmtx[g][0] if g else up * 0.55) / up


def has_glyph(c, bold=False):
    return ord(c) in _metrics(bold)[0]


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
    fam = FAM_B if bold else FAM_R
    return ('<text%s x="%.2f" y="%.2f"%s%s font-family="%s" font-size="%.2f" '
            'letter-spacing="%.3f" fill="%s">%s</text>'
            % (ida, x, y, fw, extra, fam, size, ls * size, fill, "".join(parts)))


def svg(res, runs, color, bold=False, elem_id=None, extra=""):
    _, size, xl, bl, ls, ss, sy = res[:7]
    return text_el(runs, size, xl, bl, ls, ss, sy, bold, color, elem_id, extra)


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
    meta = dict(dw=abs(fw - ow), dh=abs(fh - oh), ink=float(ink.mean()),
                rect=(x0 + fb[0], y0 + fb[1], x0 + fb[2] + 1, y0 + fb[3] + 1))
    return float(d), float(size), float(xl), float(bl), float(ls), float(ss), float(sy), meta
