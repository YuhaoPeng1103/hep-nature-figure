# -*- coding: utf-8 -*-
"""elements.py —— 面板内「物理元素」自动发现 + 人工命名

发现三步：
  1) 墨迹连通域（>=minpx）—— 分开互不接触的物体（如 b 面板的 4 个圆柱）
  2) 对每个连通域内部再做「调色板量化 + 同色连通 + 邻近合并」，
     保留 >=minpx 的子块，其余用最近种子铺满 —— 切开互相接触的物体（火球/箭头、曲面/坐标轴）
  3) 剩余非墨迹像素 -> <panel>-background
命名：panels.NAMES[(面板, 序号)]，带 bbox 指纹校验；缺名字的落 x-partN。
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from . import segsem as SS
from . import panels as P

NEI8 = np.ones((3, 3), np.uint8)
NEI4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)


def _split_comp(comp, rgb, minpx, gap=2, tol=40, ncol=16):
    """把一个连通域内部按颜色切成若干子元素（覆盖 comp 的每个像素）"""
    ys, xs = np.nonzero(comp)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    m = comp[y0:y1, x0:x1]
    crop = rgb[y0:y1, x0:x1]
    crop = np.where(m[..., None], crop, 255.0)
    lab, pal = SS.quantize(crop, ncol)
    lab = np.where(m, lab, -1)

    comp2 = np.full(m.shape, -1, np.int32)
    col_of, size_of = [], []
    nxt = 0
    for k in range(len(pal)):
        mk = lab == k
        if not mk.any():
            continue
        c, n = ndi.label(mk, structure=NEI4)
        cnt = np.bincount(c.ravel(), minlength=n + 1)
        comp2 = np.where(mk, np.where(c > 0, c - 1 + nxt, -1), comp2)
        for i in range(1, n + 1):
            col_of.append(k); size_of.append(int(cnt[i]))
        nxt += n
    col_of = pal[np.array(col_of, np.int32)]
    size_of = np.array(size_of, np.float64)
    cur = comp2
    for _ in range(gap):
        d = ndi.grey_dilation(cur, footprint=NEI8)
        p = np.stack([cur.ravel(), d.ravel()], 1)
        p = p[(p[:, 0] >= 0) & (p[:, 1] >= 0) & (p[:, 0] != p[:, 1])]
        if not len(p):
            break
        p = p[np.abs(col_of[p[:, 0]] - col_of[p[:, 1]]).sum(1) <= tol]
        if not len(p):
            continue
        g = coo_matrix((np.ones(len(p), np.float32), (p[:, 0], p[:, 1])), shape=(len(col_of),) * 2)
        lb = connected_components(g, directed=False)[1]
        ncc = int(lb.max()) + 1
        sw = np.zeros((ncc, 3)); tw = np.zeros(ncc)
        np.add.at(sw, lb, col_of * size_of[:, None]); np.add.at(tw, lb, size_of)
        col_of = sw / np.maximum(tw, 1.0)[:, None]; size_of = tw
        cur = np.where(cur >= 0, lb[np.clip(cur, 0, None)], -1)

    ids = np.unique(cur); ids = ids[ids >= 0]
    cnt = {int(i): int((cur == i).sum()) for i in ids}
    seeds = [i for i in ids if cnt[int(i)] >= minpx]
    if not seeds:
        seeds = [int(max(ids, key=lambda i: cnt[int(i)]))]
    lut = {s: i for i, s in enumerate(seeds)}
    seedmask = np.isin(cur, seeds)
    seedlab = np.full(cur.shape, -1, np.int32)
    seedlab[seedmask] = np.vectorize(lut.get)(cur[seedmask])
    _, ind = ndi.distance_transform_edt(~seedmask, return_indices=True)
    sub = seedlab[ind[0], ind[1]]
    out = []
    for i in range(len(seeds)):
        mm = np.zeros(comp.shape, bool)
        mm[y0:y1, x0:x1] = sub == i
        out.append((mm, cnt[int(seeds[i])]))
    return out


def discover(a, thr=6.0, minpx=150, close=2, sub_gap=2, sub_tol=40, sub_ncol=16, sub_minpx=None):
    """返回 {cid: (elmap, elems)}；elmap 覆盖面板内每个像素（0..N-1），-1 = 不属于本面板"""
    H, W = a.shape[:2]
    if sub_minpx is None:
        sub_minpx = max(120, minpx // 2)
    d = 255.0 - a.min(2)
    res = {}
    for cid in P.order():
        cs = [c for c in P.CELLS if c[0] == cid]
        pm = np.zeros((H, W), bool)
        for c in cs:
            pm[c[3][1]:c[3][3], c[3][0]:c[3][2]] = True
        m = (d > thr) & pm
        if close:
            m = ndi.binary_closing(m, NEI8.astype(bool), iterations=close) & pm
        lab, n = ndi.label(m, NEI8)
        cnt = np.bincount(lab.ravel(), minlength=n + 1)
        big = [i for i in range(1, n + 1) if cnt[i] >= minpx]
        elmap = np.full((H, W), -1, np.int32)
        elems = []
        for i in big:
            comp = lab == i
            for mi, c in _split_comp(comp, a, sub_minpx, gap=sub_gap, tol=sub_tol, ncol=sub_ncol):
                elmap[mi] = len(elems)
                elems.append(dict(px=c))
        nbg = len(elems)
        bgmask = pm & (elmap < 0)
        elmap[bgmask] = nbg
        elems.append(dict(px=int(bgmask.sum())))
        for k, e in enumerate(elems):
            mm = elmap == k
            ys, xs = np.nonzero(mm)
            e["bbox"] = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            e["size"] = int(mm.sum())
            e["color"] = [int(v) for v in a[mm].mean(0)]
            e["center"] = [int(xs.mean()), int(ys.mean())]
        res[cid] = (elmap, elems)
    return res


def dump(a, out_png="_el_overlay.png", out_txt="_el_table.txt", **kw):
    res = discover(a, **kw)
    vis = np.clip(a, 0, 255).astype(np.uint8).copy()
    rng = np.random.RandomState(5)
    lines = []
    for cid in P.order():
        el, elems = res[cid]
        lines.append("=== %-14s %-14s 元素 %d" % (cid, P.meta()[cid]["role"], len(elems)))
        for k, e in enumerate(elems):
            b = e["bbox"]
            lines.append("  #%-3d px=%-7d box=(%4d,%4d,%4d,%4d) %4dx%-4d mean=#%02x%02x%02x center=(%4d,%4d)"
                         % (k, e["size"], b[0], b[1], b[2], b[3], b[2] - b[0], b[3] - b[1],
                            e["color"][0], e["color"][1], e["color"][2], e["center"][0], e["center"][1]))
        mm = el >= 0
        cols = rng.randint(60, 256, (len(elems) + 1, 3))
        vis[mm] = (0.28 * vis[mm] + 0.72 * cols[el[mm] + 1]).astype(np.uint8)
    im = Image.fromarray(vis); dr = ImageDraw.Draw(im)
    try:
        from . import fonts
        f = ImageFont.truetype(fonts.pick(True)[0], 16)
    except Exception:
        f = ImageFont.load_default()
    for cid in P.order():
        el, elems = res[cid]
        for k, e in enumerate(elems):
            if e["size"] < 400:
                continue
            x, y = e["center"]
            dr.text((x + 1, y + 1), str(k), fill=(0, 0, 0), font=f)
            dr.text((x, y), str(k), fill=(255, 255, 0), font=f)
    im.save(out_png)
    open(out_txt, "w", encoding="utf-8").write("\n".join(lines))
    print("写出 %s / %s" % (out_png, out_txt))
    return res
