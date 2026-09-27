# -*- coding: utf-8 -*-
"""groupvec.py —— 位图 -> 「按物理语义分组」的全矢量 SVG

产物结构（Illustrator 图层面板可直接按名字点选/改色/改字）:

  <g id="figure">
    <rect id="canvas-background"/>
    <g id="title"> ... </g>
    <g id="panel-a" data-panel="a" data-role="transverse" data-label="...">
      <g id="panel-a-gray"   data-family="gray">   <path id="panel-a-gray1" data-color="#c1c2c4"/> </g>
      <g id="panel-a-orange" data-family="orange"> <path id="panel-a-orange1"/> </g>
      <g id="panel-a-text"   data-role="text">     <text id="panel-a-t1">...</text> </g>
    </g>

用法:
  python groupvec.py src.png out.svg _words.txt [--W 1200] [--R 16] [--K 7]
                      [--erase] [--manifest out.json] [--stats]
"""

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8（否则打印 ✅ 会崩）

import sys, os, json, colorsys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from . import gradfit as GFT
from . import shade as SHD

# 颜色量化前的原图。渐变合并按它拟合 —— 量化误差（±255/(2(Q-1))）不该被算进
# 渐变模型里，否则「台阶」反而比「真渐变」更贴量化图，MAE 会假性地变好。
RAW = [None]
from . import quadtree as Q
from . import raster_ops as V
from . import labels as LB
from . import panels as P

_FAM = [(0, 16, "red"), (16, 45, "orange"), (45, 70, "yellow"), (70, 165, "green"),
        (165, 200, "cyan"), (200, 262, "blue"), (262, 300, "purple"),
        (300, 345, "magenta"), (345, 361, "red")]


def cname(r, g, b):
    """RGB -> 人读颜色族名（用于图层命名）"""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if v >= 0.99 and s < 0.02:
        return "white"
    if v <= 0.10:
        return "black"
    if s < 0.10:
        return "gray"
    deg = h * 360.0
    base = "misc"
    for lo, hi, nm in _FAM:
        if lo <= deg < hi:
            base = nm
            break
    if v < 0.38:
        base = "dk" + base
    elif v > 0.92 and s < 0.30:
        base = "lt" + base
    return base


def _dbg_font(sz):
    """自检图上写标签用的字体（找不到就退回 PIL 默认）"""
    try:
        from . import fonts
        return ImageFont.truetype(fonts.pick(True)[0], sz)
    except Exception:
        return ImageFont.load_default()


def hexs(c):
    return "#%02x%02x%02x" % tuple(c)


def runs_cells(a, R, K, cells):
    """四叉树叶块 -> 同色水平合并的矩形条 -> 按 (cell 索引, 颜色) 归并"""
    from itertools import groupby
    me, leaves = Q.build(a, R, K)
    H, W = a.shape[:2]
    out, nleaf = {}, 0
    rects_cells = [(c[3][0], c[3][1], c[3][2], c[3][3]) for c in cells]
    for k in range(K + 1):
        if not leaves[k]:
            continue
        s = 1 << k
        m = me[k]
        nleaf += len(leaves[k])
        for r, grp in groupby(sorted(leaves[k]), key=lambda t: t[0]):
            row = [j for _, j in grp]
            start = 0
            for t in range(1, len(row) + 1):
                # 必须「列相邻 + 同色」才合并：保证矩形严格不相交 => 渲染与出图顺序无关
                if (t == len(row) or row[t] != row[t - 1] + 1
                        or not np.array_equal(m[r, row[t]], m[r, row[t - 1]])):
                    j0, j1 = row[start], row[t - 1] + 1
                    x0, x1 = min(j0 * s, W), min(j1 * s, W)
                    y0, y1 = min(r * s, H), min((r + 1) * s, H)
                    if x1 > x0 and y1 > y0:
                        c = m[r, row[start]]
                        key = (int(round(c[0])), int(round(c[1])), int(round(c[2])))
                        # 粗块可能跨出所属面板：按面板边界切开，避免后画的组盖住别组的文字
                        for ci, (cx0, cy0, cx1, cy1) in enumerate(rects_cells):
                            ax0, ay0 = max(x0, cx0), max(y0, cy0)
                            ax1, ay1 = min(x1, cx1), min(y1, cy1)
                            if ax1 > ax0 and ay1 > ay0:
                                out.setdefault((ci, key), []).append(
                                    (ax0, ay0, ax1 - ax0, ay1 - ay0))
                    start = t
    return out, nleaf


def cell_of(box, idx):
    x, y, w, h = box
    H, W = idx.shape
    return int(idx[min(H - 1, int(y + h / 2)), min(W - 1, int(x + w / 2))])


def cid_of(box, idx):
    """框心所在的面板 id；框心不落在任何面板里 → None。

    ★ 实测坑：原来直接写 `P.CELLS[cell_of(...)][0]`。cell_of 在未被面板覆盖的
      位置返回 -1，而 Python 的负索引会**绕到最后一个面板** —— 文字被静默塞进
      错误的图层，而且 id 是合法的（`d-t1`），从产物上根本看不出错。
      实测暴露：把工作分辨率从 1080 提到 2160、但 layers 表仍是 1080 版时，
      6 条标签全部被塞进最后一个面板 d。
    """
    ci = cell_of(box, idx)
    return P.CELLS[ci][0] if 0 <= ci < len(P.CELLS) else None


def main():
    av = sys.argv[1:]
    src, out, wf = av[0], av[1], av[2]

    def opt(name, dflt):
        return type(dflt)(av[av.index(name) + 1]) if name in av else dflt

    W = opt("--W", 1200); R = opt("--R", 16.0); K = opt("--K", 7)
    Q = opt("--q", 0)
    erase = "--erase" in av
    # 图层清单默认跟输出 SVG 同名（不要硬编码某张图的文件名）
    man = opt("--manifest", "")
    if not man:
        man = os.path.splitext(out)[0] + "_layers.json"
    stats = "--stats" in av

    # 版式表可以外挂：--panels my_panels.py（不传就用包里的 T3-01 示例）
    pmod = opt("--panels", "")
    if pmod:
        import importlib.util
        spec = importlib.util.spec_from_file_location("user_panels", pmod)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        globals()["P"] = mod
        print("  版式表: %s" % pmod)

    im = Image.open(src).convert("RGB"); OW, OH = im.size
    im = im.resize((W, int(round(im.height * W / im.width))), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32); H, Wd = a.shape[:2]
    sc = Wd / OW

    # ★ 颜色量化（--q L）：AI 出的图边缘全是抗锯齿过渡带，
    #   四叉树会沿着它切出数万条碎路径。把每通道量化成 L 级，
    #   过渡带塔缩成 1~2 个硬边，叶子数大幅下降。
    #   Q 越小越粗；平涂草图建议 6~10，渲染稿建议 12~20。
    if Q and Q >= 2:
        RAW[0] = a.copy()          # 真渐变按**未量化**的颜色拟合（见 emit 里的注释）
        a = np.round(a / 255.0 * (Q - 1)) / (Q - 1) * 255.0
        print("  颜色量化到 %d 级/通道" % Q)
    print("图像 %dx%d | 四叉树 R=%s 最粗 %dpx | 源 %dx%d" % (Wd, H, R, 1 << K, OW, OH))

    # ---------- 1. 文字：OCR + 修正表 + 手工标签 -> 对齐 + 自校验 ----------
    if "--no-text" in av or wf == "-" or not os.path.exists(wf):
        sw = []
        print("  跳过文字层（%s）—— 原字笔画会留在色块矢量里"
              % ("--no-text" if "--no-text" in av else "没有词表"))
    else:
        sw = V.read_words(wf, sc * 0.5, Wd)
    # ★ FIX / DROP / MANUAL 是「每张图各不相同」的表：--panels 里定义了就用那张，
    #   没定义才退回 labels.py 的 T3-01 默认表（否则换图必须去改包里的文件）
    FIX = getattr(P, "FIX", LB.FIX)
    DROP = getattr(P, "DROP", LB.DROP)
    MANUAL = getattr(P, "MANUAL", LB.MANUAL)
    cand = []
    for x, y, w, h, t in sw:
        if t in DROP:
            continue
        cand.append((x, y, w, h, FIX.get(t, t), False, None, t))
    for txt, x0, y0, x1, y1, bold in MANUAL:
        cand.append((x0, y0, x1 - x0, y1 - y0, txt, True, y1, txt))

    # ★ 去重：同一条标签同时出现在词表和 MANUAL 里时（人工修 OCR 错字的常见做法），
    #   两个候选都会通过逐词自校验 → **同一句话画两遍**，肉眼就是 "Eollision" 这种
    #   重影（实测由「直出矢量 vs 位图临摹」那张草图对照暴露）。
    #   MANUAL 是人手写的、更权威，保留它，丢掉与它显著重叠的词表候选。
    #   阈值 0.35 很宽：两条**不同**的标签不会重叠 35%。
    def _iou_box(A, B):
        ax1, ay1 = A[0] + A[2], A[1] + A[3]
        bx1, by1 = B[0] + B[2], B[1] + B[3]
        ix = max(0.0, min(ax1, bx1) - max(A[0], B[0]))
        iy = max(0.0, min(ay1, by1) - max(A[1], B[1]))
        inter = ix * iy
        un = A[2] * A[3] + B[2] * B[3] - inter
        return 0.0 if un <= 0 else inter / un

    mboxes = [(x0, y0, x1 - x0, y1 - y0) for _, x0, y0, x1, y1, _ in MANUAL]
    if mboxes:
        n0 = len(cand)
        cand = [c for c in cand if c[5] or not any(
            _iou_box((c[0], c[1], c[2], c[3]), mb) > 0.35 for mb in mboxes)]
        if len(cand) < n0:
            print("  词表里 %d 条与 MANUAL 重叠，已丢弃（同一句只画一遍）" % (n0 - len(cand)))

    kept, fam_swapped = [], 0
    for x, y, w, h, txt, bold, blh, raw in cand:
        runs = LB.parse(txt)
        if not LB.can_render(runs, bold):
            continue
        raw_runs = None if bold else LB.parse(raw)

        def _accept(r):
            # 验收：重叠残差要明显优于「不画字」，且渲染墨迹高度与原图一致。
            # dh 门限按字号缩放 —— 写死 2px 会在高工作分辨率下误杀好拟合
            # （见 labels.dh_lim）。
            return (r is not None
                    and r[0] <= max(0.14, 0.70 * r[7]["ink"])
                    and r[7]["dh"] <= LB.dh_lim(r[7]))

        # ★ 2026-09-27：**逐标签选字体**。位图里的标签是生图模型画的，
        #   字体每张图都可能不同；以前只拿主字体（Arial）硬套，字面比例
        #   一变（实测 Tahoma 那类窄高体）就过不了 dh 验收 → 标签
        #   退回成色块轮廓，「文字必须可编辑」直接失守。
        #   默认字体先试（不改老行为），不过关再依次试候选字体。
        #   字体**必须在 align() 之前 set**：align 靠字体度量 + cairo 栅格化
        #   选字号/字距，换字体会改这两样。
        res, fam = None, None
        for fi, tf in enumerate(LB.fam_candidates(runs, bold)):
            LB.set_fam(*tf)
            r = LB.align(a, (x, y, w, h), runs, bold=bold, bl_hint=blh,
                         raw_runs=raw_runs)
            if _accept(r):
                res, fam = r, tf
                if fi:
                    fam_swapped += 1
                    print("    · 标签 %r 主字体不过验收 → 换 %s" % (txt, tf[1]))
                break
        if fam is None:
            continue
        x0, y0, x1, y1 = LB.word_box((x, y, w, h), Wd, H)
        sub = a[y0:y1, x0:x1].reshape(-1, 3)
        col = sub[sub.mean(1).argmin()]
        kept.append(dict(box=(x, y, w, h), runs=runs, bold=bold, res=res, fam=fam,
                         color="#%02x%02x%02x" % tuple(int(v) for v in col), raw=raw))
    print("  文字对象 %d 个（OCR+手工候选 %d，逐词自校验通过%s）"
          % (len(kept), len(cand),
             ("；其中 %d 条换了字体" % fam_swapped) if fam_swapped else ""))

    # ---------- 1b. 旋转标签 ----------
    #   labels.align() 的墨迹模型只认水平文字，旋转标签（斜排的箭头说明）
    #   不能走那条路；改为在 panels.ROTATED 里手量「框 + 角度 + 字号」直接摆。
    #   格式：[(text, x0, y0, x1, y1, angle_deg, size_px), ...]
    LB.set_fam(None, None)
    rot = []
    for (t, x0, y0, x1, y1, ang, sz) in getattr(P, "ROTATED", []):
        runs = LB.parse(t)
        fam = LB.choose_fam(runs, False)
        LB.set_fam(*fam)
        box = (x0, y0, x1 - x0, y1 - y0)
        r = dict(txt=t, box=box, ang=ang, size=sz, fam=fam[1],
                 fampath=fam[0], runs=runs)
        got = LB.align_rot(a, box, ang, runs)
        if got is not None:
            res, ang_fit = got
                    # 斜排标签的验收比水平文字更严：拟合是「转正后再拟合」，
                    # 万一被平行的长直线带偏，字号会整条放大（实测 19->27），
                    # 这种必须退回原图色块，宁可不改成 <text>。
            if res is not None and res[0] <= max(0.14, 0.55 * res[7]["ink"]) \
                    and res[7]["dh"] <= 5:
                r["ang"] = ang_fit
                r["size"] = res[1]
                r["fit"] = (res[2], res[3], res[4], res[5], res[6])
                r["box"] = LB.rot_box_fit(box, ang_fit, res[7]["rect"])
                rr = res[7]["rect"]; oi = res[7].get("irect") or rr
                r["mrect"] = (min(rr[0], oi[0]), min(rr[1], oi[1]),
                              max(rr[2], oi[2]), max(rr[3], oi[3]))
                r["ok"] = True
        rot.append(r)
    nbad = [r["txt"] for r in rot if not r.get("ok")]
    if nbad:
        print("  ⚠ %d 条斜排标签拟合不过关，保留原图色块不改成 <text>：%s"
              % (len(nbad), " / ".join(nbad)))
    if rot:
        print("  旋转标签 %d 个（%d 个自动拟合通过，其余退手量摆位）"
              % (len(rot), sum(1 for r in rot if r.get("fit"))))

    # ---------- 2. 擦掉被替换成真文字的原字笔画 ----------
    if erase:
        # 水平文字用轴对齐框；斜排标签必须用「旋转后的四边形」掩码 —— 两条平行
        # 标签的 AABB 必然互相重叠，用 AABB 擦会把旁边那条擦掉半截（实测留下
        # "on" 碎片、另一条被擦穿导致文字画了两遍）。拟合不过关的标签整条不擦，
        # 原样保留成色块（宁可不改成 <text>，也不能把原来对的东西擦掉）。
        boxes = [k["box"] for k in kept]
        mm = V.text_mask((H, Wd), [(x, y, w, h, ".") for x, y, w, h in boxes], 1.0,
                         pad=2, ink=V.ink_map(a))
        inkm = V.ink_map(a)
        for r in rot:
            if r.get("ok"):
                mm |= LB.rot_mask((H, Wd), r["box"], r["ang"], r["mrect"],
                                  ink=inkm, pad=2)
        # ★ EXTRA_ERASE：版式表点名要擦的框（OCR 框漏掉的多部件字形）。
        #   实测（自旋图）：Λ̄ 的上划线在原图里是独立的一横（1405,522,1436,526），
        #   OCR 给的框从 y=530 起 —— 横杠没被擦掉，成品里「重写的 <text>」再画一根
        #   横杠，就成了双划线。这个框**不能**并进词表：把 Λ̄ 的框撑到 55px 高时
        #   逐词自校验反而不过（res0 0.168 > 0.140，字体的横杠位置比原图近），
        #   于是只能「拟合用紧框 + 擦除补一块」。
        for (ex0, ey0, ex1, ey1) in getattr(P, "EXTRA_ERASE", []):
            mm |= V.text_mask((H, Wd), [(ex0, ey0, ex1 - ex0, ey1 - ey0, ".")], 1.0,
                              pad=2, ink=inkm)
        # 还要擦掉"重写文字实际占用的范围"：如 'Area'->'Area:' 补的冒号会压在原图冒号上
        rb = [k["res"][7]["rect"] for k in kept if k["res"][7].get("rect")]
        if rb:
            rb = [(x0 - 2, y0 - 2, x1 + 2, y1 + 2) for x0, y0, x1, y1 in rb]
            mm |= V.text_mask((H, Wd), [(x0, y0, x1 - x0, y1 - y0, ".") for x0, y0, x1, y1 in rb],
                              1.0, pad=1, ink=V.ink_map(a))
        a = V.inpaint(a, mm, sig=3.0)
        print("  已擦除原字笔画 %.2f%%（补背景后重建色块）" % (100 * mm.mean()))
    if "--elmap" in av:
        dump_elements(a, R, K, opt("--elmap", "_elem_overlay.png"))
        return
    if "--npz" in av:
        p = opt("--npz", "_prep.npz")
        np.savez_compressed(p, a=np.clip(a, 0, 255).astype(np.uint8))
        print("  已缓存预处理结果(擦字后) -> %s" % p)
        return
    if "--segs" in av:
        from . import segsem
        segsem.dump(a, P.CELLS, gap=int(opt("--gap", 6)), tol=float(opt("--tol", 52)),
                    out_png=opt("--el_png", "_el_overlay.png"),
                    out_txt=opt("--el_txt", "_el_table.txt"))
        return
    return emit(src, out, man, stats, a, H, Wd, kept, R, K, opt("--legend", ""), rot=rot,
                shade=opt("--shade", ""))


# ------------------------------------------------------------------ 元素归组
def _name_pass(a, R, K):
    """第一段：自动切分 + panels.ELEMENTS 定名字（按 bbox 的 IoU 匹配）+ SPLIT 按像素细化。

    返回 (eid_full, flat)：eid_full[y,x] = flat 的下标；flat[i] = (cid, eid, label)。
    单独抽出来，是为了让 emit() 能在**画之前**按元素拿到像素掩膜（真渐变合并要用）。
    """
    from . import elements as ELC
    ELC.P = P  # elements.py 自己 import 的是包内默认表；--panels 换表后必须同步，否则元素划分用错表 KeyError
    H, W = a.shape[:2]
    res = ELC.discover(a)
    eid_full = np.full((H, W), -1, np.int32)
    flat = []
    for cid in P.order():
        el, elems = res[cid]
        for k, e in enumerate(elems):
            eid, label = P.element_of(cid, e["bbox"], e["color"])
            if eid is None:
                eid, label = "graphics", "Panel graphics"
            flat.append((cid, eid, label))
            eid_full[el == k] = len(flat) - 1
    # 已命名元素内部再按颜色切细（曲面上的坐标轴 / 引线这类细线）
    for (cid, eid), subs in P.SPLIT.items():
        if eid == "*":          # 整个面板范围（可从未被正确命名的元素里捞出红箭头等）
            cidx = P.cell_index(H, W)
            gi = [i for i, c in enumerate(P.CELLS) if c[0] == cid]
            mask = np.isin(cidx, gi)
        else:
            ids = [v for v, (c, e, l) in enumerate(flat) if c == cid and e == eid]
            if not ids:
                continue
            mask = np.isin(eid_full, ids)
        for (eid2, label2, spec) in subs:
            m2 = mask & P.pixel_pred(a, spec)
            if not m2.any():
                continue
            flat.append((cid, eid2, label2))
            eid_full[m2] = len(flat) - 1
            mask = mask & ~m2
    return eid_full, flat


def assign_elements(a, R, K, named=None):
    """第二段：把四叉树叶块按「叶心像素属于哪个元素」归组。
    named = _name_pass 的结果，可复用（emit 里已经算过一次，别算两遍）。"""
    eid_full, flat = named if named is not None else _name_pass(a, R, K)
    H, W = a.shape[:2]
    bg = {}
    for v, (cid, eid, label) in enumerate(flat):
        if eid == "background" or eid == "graphics":
            bg[cid] = v
    groups, nleaf = runs_cells(a, R, K, P.CELLS)
    per, labels = {}, {}
    for (ci, col), rects in groups.items():
        cid = P.CELLS[ci][0]
        for r in rects:
            cx = min(W - 1, int(r[0] + r[2] / 2.0))
            cy = min(H - 1, int(r[1] + r[3] / 2.0))
            v = int(eid_full[cy, cx])
            if v < 0:
                v = bg.get(cid, -1)
            if v < 0:
                continue
            _, eid, label = flat[v]
            per.setdefault(cid, {}).setdefault(eid, {}).setdefault(col, []).append(r)
            labels[(cid, eid)] = label
    return per, labels, nleaf


def elem_order(cid, per):
    """元素输出顺序 = panels.ELEMENTS 的语义顺序；表外元素按像素量降序排最后"""
    tbl = [e[0] for e in P.ELEMENTS.get(cid, [])]
    have = list(per.get(cid, {}).keys())
    out = [e for e in tbl if e in have]
    extra = sorted([e for e in have if e not in out],
                   key=lambda e: -sum(len(v) for v in per[cid][e].values()))
    return out + extra


def elem_bbox(per_cid_e):
    x0 = y0 = 10 ** 9; x1 = y1 = -1
    for col, rects in per_cid_e.items():
        for (x, y, w, h) in rects:
            x0 = min(x0, x); y0 = min(y0, y)
            x1 = max(x1, x + w); y1 = max(y1, y + h)
    return (x0, y0, x1, y1)


def dump_elements(a, R, K, out_png="_elem_overlay.png"):
    """元素归组自检图：每个物理元素一种颜色 + 名字（画的是最终 SVG 的元素划分）"""
    per, labels, nleaf = assign_elements(a, R, K)
    H, W = a.shape[:2]
    vis = np.full((H, W, 3), 255, np.uint8)
    rng = np.random.RandomState(17)
    rows = []
    for cid in P.order():
        for eid in elem_order(cid, per):
            col = rng.randint(60, 256, 3)
            for c, rects in per[cid][eid].items():
                for (x, y, w, h) in rects:
                    vis[y:y + h, x:x + w] = col
            npx = sum(w * h for rs in per[cid][eid].values() for (_, _, w, h) in rs)
            nrect = sum(len(rs) for rs in per[cid][eid].values())
            rows.append("%-14s %-20s px=%-8d rects=%-6d %s"
                        % (cid, eid, npx, nrect, labels.get((cid, eid), "")))
    im = Image.fromarray(vis)
    d = ImageDraw.Draw(im)
    f = _dbg_font(15)
    for cid in P.order():
        for eid in elem_order(cid, per):
            x0, y0, x1, y1 = elem_bbox(per[cid][eid])
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            d.text((cx + 1, cy + 1), eid, fill=(0, 0, 0), font=f)
            d.text((cx, cy), eid, fill=(255, 255, 0), font=f)
    im.save(out_png)
    # ★ 表跟着 out_png 走，不要写到 cwd：--elmap 是诊断子命令，
    #   实测（2026-09-27）把 _elem_table.txt 落在 cwd 会把别的图的同名文件覆掉。
    txt = os.path.join(os.path.dirname(out_png) or ".", "_elem_table.txt")
    open(txt, "w", encoding="utf-8").write("\n".join(rows))
    print("写出 %s / %s" % (out_png, txt))
    return rows


# ------------------------------------------------------------------ 输出
def _seam_attr(col, sw):
    """同色描边 —— 专治 PDF/SVG 的「纱窗」接缝。

    为什么需要：四叉树把平滑渐变切成成千上万条**彼此紧贴**的同色矩形，每个矩形在
    PDF 里是独立填充、各做各的抗锯齿 → 相邻边界处混进背景色，形成一层 1px 的**亮网格**。
    实测（形变核→火球，1664×926）：PDF 里整个火球都是纱窗，火球区 MAE 13.4；加同色
    描边后 2.8，肉眼网纹消失（HTML 屏幕渲染看不出来，只有导出 PDF 才暴露）。
    宽度单位 = 工作分辨率像素（≈1 源像素），半宽 0.5px 正好盖住接缝；再宽会把形状
    撑大（实测 2.5px 反而更差：火球区 3.4）。

    ★ 只给**不透明**实色块加：明暗层是 `fill-opacity`，描边会按全不透明度画上去，
      整个元素直接变黑（实测 stage1 的 MAE 3.5 → 56.8）。所以调用点只覆盖
      base / 逐色 / remnant 三处，**不要**加到 shade 层上。
    panels 里可用 `SEAM = {"*": 1.0, "stage4-fireball": 1.4}` 覆盖，`{"*": 0}` 关掉。
    """
    if not sw:
        return ""
    return ' stroke="%s" stroke-width="%.2f" stroke-linejoin="round"' % (col, sw)


def emit(src, out, man, stats, a, H, Wd, kept, R, K, legend=None, rot=None, shade=""):
    rot = rot or []
    shade = shade or ""
    idx = P.cell_index(H, Wd)
    # 接缝描边宽度（见 _seam_attr）；panels 没写就是全局 1.0
    _SEAM = getattr(P, "SEAM", None)
    if _SEAM is None:
        _SEAM = {"*": 1.0}

    def seam_of(eid):
        v = _SEAM.get(eid)
        if v is None:
            v = _SEAM.get("*", 0.0)
        return float(v or 0.0)

    meta, order = P.meta(), P.order()
    named = _name_pass(a, R, K)
    per, labels, nleaf = assign_elements(a, R, K, named)
    for cid in order:
        per.setdefault(cid, {})

    # ---------- 真渐变合并（可选）：panels 里写 GRADIENTS = {eid: {...}} 才生效 ----------
    # 不写 = 一行行为都不变（向后兼容）。算法与实测见 raster_vector/gradfit.py。
    grads, gdefs = {}, []
    for eid, spec in (getattr(P, "GRADIENTS", None) or {}).items():
        eid_full, flat = named
        ids = [v for v, (c, e, l) in enumerate(flat) if e == eid and c in order]
        if not ids:
            print("  · 渐变 %s: 该元素不存在，跳过" % eid)
            continue
        spec = dict(spec or {})
        M = np.isin(eid_full, ids)
        g = GFT.fit(a, M, src=RAW[0], **spec)
        if g is None:
            print("  · 渐变 %s: 残差过大，放弃（保留原色阶台阶）" % eid)
            continue
        cid = flat[ids[0]][0]
        gid = "%s-grad-%s" % (cid, eid)
        g["eid"], g["cid"], g["gid"] = eid, cid, gid
        g["tol"] = float(spec.get("tol", 26))
        grads[(cid, eid)] = g
        gdefs.append(GFT.svg_defs(gid, g))
        print("  · 渐变 %s: %s 残差 %.2f | 渐变内 %dpx | %d 档"
              % (eid, g["kind"], g["resid"], g["px"], len(g["stops"])))
    def _shnp(sh):
        """一个元素重写后的 <path> 条数：k 个基色块（或 1 条真渐变 body）+ 用到的明暗层数"""
        if sh["mode"] == "grad":
            nb = len({(t, l) for _, _, t, l in sh["assign"] if t in (0, 1) and l > 0.0})
            return 1 + nb + sh.get("nleft", 0) + sh.get("nrem", 0)
        nb = len({(t, l) for _, t, l in sh["assign"].values() if t in (0, 1) and l > 0.0})
        nrem = len({tuple(sh["bases"][sh["assign"][c][0]]) for c in sh["assign"]
                    if sh["assign"][c][1] == 2})
        return sh["k"] + nb + nrem

    def _npath(cid, eid, e):
        sh = SH.get((cid, eid))
        return _shnp(sh) if sh else len(e)

    # ---------- 元素级「基色 + 明度层」重写（可选）----------
    # 交付版逐像素临摹的产物是「一种颜色一条 <path>」（实测 stage4-fireball
    # 6696 条 path = 6696 种颜色），改色只能一条一条改。这里把一个元素重写成
    #   k 个基色块（每块一个 fill）+ 若干条 fill-opacity 明暗层（黑/白，颜色无关）
    # 于是「改基色块的 fill」= 整体改这个物理色块。算法与实测见 raster_vector/shade.py。
    SH = {}
    shcfg = dict(getattr(P, "SHADING", None) or {})
    if shade:
        parts = shade.split(":")
        kk = parts[0] if parts[0] else "auto"
        lv = int(parts[1]) if len(parts) > 1 and parts[1] else 16
        shcfg["*"] = {"k": (None if kk == "auto" else int(kk)), "levels": lv}
        if len(parts) > 2 and parts[2] != "":      # 第三段：1/0 = 要不要真渐变 body
            shcfg["*"]["gradient"] = bool(int(parts[2]))
    if shcfg:
        dflt = shcfg.get("*")
        for cid in order:
            for eid in elem_order(cid, per):
                spec = shcfg.get(eid, dflt)
                if not spec or eid == "background" or (cid, eid) in grads:
                    continue
                items = sorted(per[cid][eid].items(),
                               key=lambda t: -sum(w * h for _, _, w, h in t[1]))
                lv = int(spec.get("levels", 16))
                # flat=False = 这个元素只走真渐变 body（不算平涂模型）——
                # 平涂模型在 levels 很小时残差指标不可比，会误胜。
                got = None
                if spec.get("flat", True):
                    got = SHD.fit(items, levels=max(1, lv), kmax=int(spec.get("kmax", 3)),
                                  tol=float(spec.get("tol", 1.35)),
                                  resid_cap=float(spec.get("resid_cap", 8.0)),
                                  kforce=spec.get("k"),
                                  rem_err=float(spec.get("rem_err", 60.0)))
                # ★ 径向渐变（火球）用「平涂基色 + N 档明度层」近似时，每一档会沿
                #   等半径连成一个**环**（实测 N=24 球面上肉眼可见同心色环）。真渐变
                #   body 把那条平滑 ramp 交给 <radialGradient>，明度层只补残差。
                #   两条路都算一遍，取残差低的那个（都记进图层清单，能对照）。
                gr = None
                if spec.get("gradient", True):
                    m = np.zeros((H, Wd), bool)
                    for rs in per[cid][eid].values():
                        for (x, y, w, h) in rs:
                            m[y:y + h, x:x + w] = True
                    gr = SHD.fit_grad(a, m, items, levels=lv,
                                      nstops=int(spec.get("nstops", 16)),
                                      tol=float(spec.get("grad_tol", 26)),
                                      minpx=int(spec.get("grad_minpx", 800)),
                                      rem_err=float(spec.get("rem_err", 60.0)),
                                      dbg=eid,
                                      drop_tol=spec.get("drop_tol"))
                if gr is not None and (got is None or gr["resid"] < got["resid"]):
                    SH[(cid, eid)] = gr
                    print("    · 明度重写 %-22s 真%7s 渐变 x %d 档 | 残差 %.2f | %d 色块 -> %d path"
                          % (eid, gr["g"]["kind"], lv, gr["resid"], len(items),
                             _shnp(gr)))
                elif got is not None:
                    SH[(cid, eid)] = got
                    print("    · 明度重写 %-22s k=%d x %d 档 | 残差 %.2f | %d 色块 -> %d path"
                          % (eid, got["k"], lv, got["resid"], len(items), _shnp(got)))
                else:
                    print("    · 明度重写 %-22s 跳过（残差过大，保留原色阶）" % eid)
    nrun = sum(len(rs) for cid in order for e in per[cid].values() for rs in e.values())
    npath = sum(_npath(cid, eid, e) for cid in order for eid, e in per[cid].items())
    nelem = sum(len(per[cid]) for cid in order)
    print("  叶块 %d -> 色块 %d 条 -> <path> %d 条 | 面板 %d | 物理元素 %d"
          % (nleaf, nrun, npath, len(order), nelem))

    # 图可以不设总标题：panels 里没有 title 单元时用输出文件名兜底（否则 KeyError）
    title = (meta.get("title") or {}).get("desc") or os.path.basename(out)
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" '
         'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
         'width="%d" height="%d" viewBox="0 0 %d %d">' % (Wd, H, Wd, H),
         '<title>%s</title>' % LB.xml_esc(title),
         '<desc>全矢量图：文字为可编辑的真 text 元素，平滑渐变为真 gradient（不是色阶台阶），'
         '其余为逐像素临摹的色块矢量。'
         '图层 = 面板(panel) -> 物理元素(element) -> path；'
         '每个面板另有 text 子层。元素命名见 panels.py 的 ELEMENTS 表。</desc>',
         '<g id="figure" data-role="figure" inkscape:groupmode="layer" inkscape:label="Figure">',
         '<rect id="canvas-background" x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (Wd, H)]
    manifest = {"source": os.path.basename(src), "canvas": [Wd, H], "panels": []}
    ntxt = 0
    md = ["# 图层清单 — %s" % os.path.basename(out), "",
          "图层树：`面板 panel` → `物理元素 element` → `<path>`。",
          "★ 图层只按【物理元素】分，**不按颜色分层** —— 人打开图层面板看到的应该是",
          "物理（nucleus-A / photon-B / arrow-b…），不是 white / orange / gray。",
          "同色矩形仍会并成一条 path（那只是体积优化），颜色挂在 `data-color` 上；",
          "要把一个元素再拆成子结构（如 `nucleus-A-body` / `nucleus-A-outline`），"
          "用 `panels.py` 的 `SPLIT` 显式写，而不是靠自动的颜色分组。",
          "在 Illustrator 里打开「图层」面板即可按下面的名字点选；在 Inkscape 里是子图层。", "",
          "| 面板 | 物理元素 | 说明 | 包围盒 (x0,y0,x1,y1) | 路径数 | 像素 |", "|---|---|---|---|---|---|"]
    text_layers = []
    for cid in order:
        m = meta[cid]
        L.append('<g id="%s" data-role="%s" data-panel="%s" data-label="%s" '
                 'inkscape:groupmode="layer" inkscape:label="%s">'
                 % (cid, m["role"], m["panel"] or "-", LB.xml_esc(m["desc"]), LB.xml_esc(cid)))
        L.append('<title>%s</title>' % LB.xml_esc(m["desc"]))
        L.append('<desc>%s</desc>' % LB.xml_esc(m["desc"]))
        pinfo = {"id": cid, "panel": m["panel"], "role": m["role"], "label": m["desc"],
                 "rects": m["rects"], "elements": []}
        for eid in elem_order(cid, per):
            elab = labels.get((cid, eid), eid)
            bbox = elem_bbox(per[cid][eid])          # ★ 在丢台阶块**之前**算：
            g = grads.get((cid, eid))                #   画出渐变的元素可能只剩描边/网格线
            if g is not None:
                for col in list(per[cid][eid]):
                    keep_r = [r for r in per[cid][eid][col]
                              if not GFT.rect_covered(r[0], r[1], r[2], r[3], g)]
                    if keep_r:
                        per[cid][eid][col] = keep_r
                    else:
                        del per[cid][eid][col]
            shd = SH.get((cid, eid))
            epx = sum(w * h for rs in per[cid][eid].values() for (_, _, w, h) in rs)
            en = _npath(cid, eid, per[cid][eid])
            gtag = ''
            if shd is not None and shd["mode"] == "grad":
                gtag = (' data-shading="grad-%s" data-shading-resid="%.2f" data-shading-levels="%d"'
                        % (shd["g"]["kind"], shd["resid"], shd["levels"]))
                elab += " + 真%s渐变 body + 明度层（残差 %.2f）" % (shd["g"]["kind"], shd["resid"])
            elif shd is not None:
                gtag = (' data-shading="k%dx%d" data-shading-resid="%.2f"'
                        ' data-base-colors="%s"'
                        % (shd["k"], shd["levels"], shd["resid"],
                           ",".join(SHD.hexs(c) for c in shd["bases"])))
                elab += " + 基色x%d + 明度层（残差 %.2f）" % (shd["k"], shd["resid"])
            if g is not None:
                gtag = (' data-gradient="%s" data-gradient-resid="%.2f"'
                        ' data-gradient-px="%d"' % (g["kind"], g["resid"], int(g["mask"].sum())))
                elab += " + 真 %sGradient（残差 %.2f）" % (g["kind"], g["resid"])
            L.append('<g id="%s-%s" data-element="%s" data-label="%s" data-px="%d" '
                     'data-paths="%d" data-bbox="%d,%d,%d,%d"%s '
                     'inkscape:groupmode="layer" inkscape:label="%s">'
                     % (cid, eid, eid, LB.xml_esc(elab), epx, en, bbox[0], bbox[1], bbox[2], bbox[3],
                        gtag, LB.xml_esc(elab)))
            L.append('<title>%s</title>' % LB.xml_esc(elab))
            if g is not None:
                # 渐变形状画在该元素**最底下**：上面的网格线/描边照旧画在它上面，
                # 被丢掉的只是"落在渐变内、颜色也贴合模型"的台阶色块。
                sh, npts = GFT.svg_shape(g["gid"], g)
                if sh:
                    L.append(sh)
                    print("    %s: 真渐变形状 %d 点" % (eid, npts))
            einfo = {"id": eid, "label": elab, "bbox": list(bbox), "px": epx,
                     "paths": en, "colors": []}
            if shd is not None and shd["mode"] == "grad":
                einfo["shading"] = {"model": "gradient+opacity", "kind": shd["g"]["kind"],
                                    "levels": shd["levels"], "resid": round(shd["resid"], 3),
                                    "stops": ["#%02x%02x%02x" % (int(round(c[0])), int(round(c[1])),
                                                                 int(round(c[2])))
                                              for c in shd["g"]["stops"]],
                                    "bands": len({(t, l) for _, _, t, l in shd["assign"]
                                                  if t in (0, 1) and l > 0}),
                                    "remnants": shd.get("nrem", 0) + shd.get("nleft", 0)}
            elif shd is not None:
                einfo["shading"] = {"model": "base+opacity", "k": shd["k"],
                                    "levels": shd["levels"], "resid": round(shd["resid"], 3),
                                    "bases": [SHD.hexs(c) for c in shd["bases"]],
                                    "bands": len({(t, l) for _, t, l in shd["assign"].values()
                                                  if t in (0, 1) and l > 0}),
                                                  "remnants": len({shd["bases"][v[0]] for v in shd["assign"].values() if v[1] == 2})}
            if g is not None:
                einfo["gradient"] = {"kind": g["kind"], "resid": round(g["resid"], 3),
                                     "px": int(g["mask"].sum()),
                                     "stops": ["#%02x%02x%02x" % (int(round(c[0])),
                                               int(round(c[1])), int(round(c[2])))
                                               for c in g["stops"]]}
            # ★ 不再插一层「颜色族」<g>：图层树必须是 panel -> element -> <path>。
            #   实测问题（2026-09-26）：人打开图层面板看到的是
            #     p-photon-A / p-photon-A-orange / p-photon-A-gray / p-photon-A-white
            #   —— 中间那层是**按颜色**分的，跟物理没关系，选择/改色时要多点好几次。
            #   「同色矩形并成一条 path」仍然保留（那是体积优化，不是图层结构）：
            #   实测 UPC 图 48071 条色块 → 22655 条 <path>，并了 53%。
            #   要按物理再拆子结构，用 panels.py 的 SPLIT 显式写。
            if shd is not None and shd["mode"] == "grad":
                # ★ 结构：**一条真渐变 body**（改 <defs> 里的 stop 就是整体改这个
                #   物理色块）+ 少量 color-neutral 明暗层补残差。
                gid = "%s-%s-grad" % (cid, eid)
                gdefs.append(GFT.svg_defs(gid, shd["g"]))
                d, npts = shd["shape"]
                body = ('<path id="%s-%s-body" data-role="element-body" data-gradient="%s" '
                        'data-gradient-resid="%.2f" data-px="%d" fill="url(#%s)" d="%s"/>'
                        % (cid, eid, shd["g"]["kind"], shd["g"]["resid"],
                           int(shd["g"]["mask"].sum()), gid, d))
                # ★ aradial 的 body 坐标在**局部空间**，必须包一层 <g transform> 拉回画布；
                #   渐变定义也按局部坐标写（cx=0 cy=0 r=1）。见 shade.fit_grad 的注释。
                xf = shd.get("xform")
                if xf:
                    body = ('<g transform="matrix(%.6f %.6f %.6f %.6f %.2f %.2f)" '
                            'data-role="gradient-wrap">%s</g>'
                            % (xf[0], xf[1], xf[2], xf[3], xf[4], xf[5], body))
                L.append(body)
                einfo["colors"].append({"color": "url(#%s)" % gid, "family": "gradient",
                                        "role": "element-body",
                                        "stops": ["#%02x%02x%02x" % (int(round(c[0])),
                                                                     int(round(c[1])),
                                                                     int(round(c[2])))
                                                  for c in shd["g"]["stops"]],
                                        "px": int(shd["g"]["mask"].sum())})
                bands, lo = {}, {}
                for col, (rx, ry, rw, rh), tone, lev in shd["assign"]:
                    if tone == 2:
                        lo.setdefault(col, []).append((rx, ry, rw, rh))
                    elif lev > 0.0:
                        bands.setdefault((tone, lev), []).append((rx, ry, rw, rh))
                # body 轮廓盖不到的碎块 / 高 alpha 的色块：按原色平涂（同色并成一条 path）
                for col, r in shd.get("leftover") or ():
                    lo.setdefault(col, []).append(r)
                print("    %s: 真%s渐变 body %d 点 + 明暗层 %d 条 + 碎块 %d 条"
                      % (eid, shd["g"]["kind"], npts, len(bands), len(lo)))
            elif shd is not None:
                # ★ 结构：k 个基色块（fill 就是基色 -> 整体改色的把手）+ 明暗层。
                #   明暗层是黑/白 + fill-opacity，**不带颜色**，所以换基色时
                #   整个元素的明暗关系自动跟着走（这正是「整体改一个物理色块」）。
                bodies, bands, lo = {}, {}, {}
                for col, rects in per[cid][eid].items():
                    ki, tone, lev = shd["assign"][col]
                    if tone == 2:
                        lo.setdefault(col, []).extend(rects)
                        continue
                    bodies.setdefault(ki, []).extend(rects)
                    if lev > 0.0:
                        bands.setdefault((tone, lev), []).extend(rects)
                _sw = seam_of(eid)
                for j, ki in enumerate(sorted(bodies)):
                    rects = sorted(bodies[ki], key=lambda r: (r[1], r[0]))
                    px = sum(w * h for _, _, w, h in rects)
                    _hc = SHD.hexs(shd["bases"][ki])
                    L.append('<path id="%s-%s-body%d" data-role="element-body" '
                             'data-base="%s" data-px="%d" fill="%s"%s d="%s"/>'
                             % (cid, eid, j + 1, _hc, px, _hc,
                                _seam_attr(_hc, _sw), SHD.d_of(rects)))
                    einfo["colors"].append({"color": SHD.hexs(shd["bases"][ki]),
                                            "family": "base", "role": "element-body",
                                            "px": px, "rects": len(rects)})
            else:
                items = sorted(per[cid][eid].items(),
                               key=lambda t: -sum(w * h for _, _, w, h in t[1]))
                _sw = seam_of(eid)
                for i, (col, rects) in enumerate(items, 1):
                    d = "".join("M%d %dh%dv%dh-%dz" % (x, y, w, h, w) for x, y, w, h in rects)
                    px = sum(w * h for _, _, w, h in rects)
                    _hc = hexs(col)
                    L.append('<path id="%s-%s-%02d" data-color="%s" data-px="%d" fill="%s"%s d="%s"/>'
                             % (cid, eid, i, _hc, px, _hc, _seam_attr(_hc, _sw), d))
                    einfo["colors"].append({"color": hexs(col), "family": cname(*col),
                                            "px": px, "rects": len(rects)})
            if shd is not None:
                for col, rects in sorted(lo.items(),
                                         key=lambda z: -sum(w * h for _, _, w, h in z[1])):
                    rects = sorted(rects, key=lambda r: (r[1], r[0]))
                    px = sum(w * h for _, _, w, h in rects)
                    _hc = hexs(col)
                    L.append('<path id="%s-%s-lo-%s" data-role="element-remnant" '
                             'data-color="%s" data-px="%d" fill="%s"%s d="%s"/>'
                             % (cid, eid, _hc[1:], _hc, px, _hc,
                                _seam_attr(_hc, seam_of(eid)), SHD.d_of(rects)))
                    einfo["colors"].append({"color": hexs(col), "family": "remnant",
                                            "role": "element-remnant", "px": px,
                                            "rects": len(rects)})
            if shd is not None:
                    for (tone, lev) in sorted(bands):
                        rects = sorted(bands[(tone, lev)], key=lambda r: (r[1], r[0]))
                        px = sum(w * h for _, _, w, h in rects)
                        fillc = "#000000" if tone == 0 else "#ffffff"
                        L.append('<path id="%s-%s-%s%03d" data-role="shade" data-tone="%s" '
                                 'data-level="%.4f" data-px="%d" fill="%s" fill-opacity="%.4f" '
                                 'd="%s"/>'
                                 % (cid, eid, "d" if tone == 0 else "l", int(round(lev * 1000)),
                                    "dark" if tone == 0 else "light", lev, px, fillc, lev,
                                    SHD.d_of(rects)))
                        einfo["colors"].append({"color": fillc, "family": "shade",
                                                "role": "shade",
                                                "opacity": lev, "px": px, "rects": len(rects)})
            L.append('</g>')
            pinfo["elements"].append(einfo)
            md.append("| `%s` | `%s-%s` | %s | %d,%d,%d,%d | %d | %d |"
                      % (cid, cid, eid, elab, bbox[0], bbox[1], bbox[2], bbox[3], en, epx))
        mine = [k for k in kept if cid_of(k["box"], idx) == cid]
        mrot = [r for r in rot if r.get("ok") and cid_of(r["box"], idx) == cid]
        if mine or mrot:
            text_layers.append((cid, mine, mrot))
            ntxt += len(mine) + len(mrot)
            pinfo["texts"] = len(mine) + len(mrot)
            md.append("| `%s` | `%s-text` | text layer (%d editable <text>) | - | %d | - |"
                      % (cid, cid, len(mine) + len(mrot), len(mine) + len(mrot)))
        L.append('</g>')
        manifest["panels"].append(pinfo)
    # ★ 文字层统一放到所有面板之后：文字框常跨面板边界，留在面板内时
    #   后面面板的不透明背景色块会盖住它的尾巴（实测 "Pressure-driven" 在
    #   x=950 处被切断、"Low-energy method" 在 x=320 处被切断）
    if text_layers:
        L.append('<g id="text-layer" data-role="text" '
                 'inkscape:groupmode="layer" inkscape:label="Text (all panels)">')
        for cid, mine, mrot in text_layers:
            L.append('<g id="%s-text" data-role="text" data-count="%d" '
                     'inkscape:groupmode="layer" inkscape:label="%s (text)">'
                     % (cid, len(mine) + len(mrot), cid))
            for i, k in enumerate(mine, 1):
                LB.set_fam(*k["fam"])
                L.append(LB.svg(k["res"], k["runs"], k["color"], k["bold"],
                                elem_id="%s-t%d" % (cid, i),
                                extra=' data-plain="%s"' % LB.xml_esc(LB.plain(k["runs"]))))
            for j, r in enumerate(mrot, 1):
                LB.set_fam(r["fampath"], r["fam"])   # rot_el 要按这条标签的字体排版
                L.append(LB.rot_el(r, elem_id="%s-r%d" % (cid, j)))
            L.append('</g>')
        L.append('</g>')
    L.append('</g>')
    if gdefs:
        # 渐变定义放最后：SVG 的 id 是全文档解析的，引用在前、定义在后没问题
        # （cairosvg / Edge / Inkscape / Illustrator 都实测过）。
        L.append('<defs>%s</defs>' % "".join(gdefs))
    L.append('</svg>')
    open(out, "w", encoding="utf-8").write("\n".join(L))
    manifest["stats"] = {"paths": npath, "rects": nrun, "texts": ntxt,
                         "leaves": nleaf, "elements": nelem}
    json.dump(manifest, open(man, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if legend:
        md += ["", "## 怎么改", "",
               "- 改某个物理内容（火球 / 核子 / 流箭头 / 曲面 / 坐标轴 / 介质管…）：选中对应 `panel-element` 图层改颜色或形状。",
               "- 改文字：选中 `panel-text` 里的真 `<text>`，字体、字号、内容都可直接编辑。",
               "- 要重命名/调整元素范围：编辑 `panels.py` 的 `ELEMENTS`（框 + 颜色条件）与 `SPLIT`，再重跑 groupvec.py。",
                "- 元素名字带「+ 真X渐变 body + 明度层」的：该元素的整体颜色就是一条真渐变，",
                "  改 <defs> 里那条 gradient 的 stop 即整体改色；明暗层是黑/白 + fill-opacity，",
               "- 元素名字带「+ 基色xN + 明度层」的：N 个基色块各有一个 fill（整体改色的把手），",
               "  明暗层是黑/白 + fill-opacity（不含颜色），换基色时明暗关系自动跟着走。",
               "- 元素名字带「+ 真 radialGradient/linearGradient」的：该元素的大片平滑渐变已",
               "  合并成一条 `data-role=\"gradient-shape\"` 的 path（渐变定义在文件末尾的 `<defs>`），",
               "  底色台阶已丢掉；改渐变色/中心就在 `<defs>` 里改那个 gradient。"]
        open(legend, "w", encoding="utf-8", newline="\n").write("\n".join(md) + "\n")
        print("  %s 图层清单(可读版)" % legend)
    print("  %s %.2f MB | <path> %d | <text> %d | <image> 0"
          % (out, os.path.getsize(out) / 1048576.0, npath, ntxt))
    print("  %s 图层清单" % man)
    if stats:
        for p in manifest["panels"]:
            top = ", ".join('%s(%d)' % (e["id"], e["paths"]) for e in p["elements"][:8])
            print("    %-16s 元素 %2d  %s" % (p["id"], len(p["elements"]), top))


if __name__ == "__main__":
    main()
