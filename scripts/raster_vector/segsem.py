# -*- coding: utf-8 -*-
"""segsem.py —— 面板内「物理元素」自动切分（供人工命名 / 语义分组导出）

路线：调色板量化 -> 同色连通域 -> 灰色膨胀桥接（颜色相近才合并）-> 保留大块作为
      「元素种子」-> 最近种子铺满面板 -> 得到覆盖全画布的元素编号图。
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from . import panels as P

NEI = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)   # 4 邻接
NEI8 = np.ones((3, 3), np.uint8)


def quantize(a, n=24):
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    q = im.quantize(colors=n, method=Image.MEDIANCUT, dither=Image.NONE)
    pal = np.array(q.getpalette()[:n * 3], dtype=np.float32).reshape(-1, 3)
    return np.asarray(q).astype(np.int32), pal


def merge_map(a, cells, gap=8, tol=80, ncol=24):
    """同色连通域 + 膨胀桥接合并 -> 返回 (map 相对切片, 偏移, 每标签的 bbox/size/color)"""
    x0 = min(c[3][0] for c in cells); y0 = min(c[3][1] for c in cells)
    x1 = max(c[3][2] for c in cells); y1 = max(c[3][3] for c in cells)
    sub = a[y0:y1, x0:x1]
    h, w = sub.shape[:2]
    pm = np.zeros((h, w), bool)
    for c in cells:
        cx0, cy0, cx1, cy1 = c[3]
        pm[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] = True

    lab, pal = quantize(sub, ncol)
    lab = np.where(pm, lab, -1)

    comp = np.full((h, w), -1, np.int32)
    cols, sizes, bboxes = [], [], []
    nxt = 0
    for k in range(len(pal)):
        m = lab == k
        if not m.any():
            continue
        c, n = ndi.label(m, structure=NEI)
        cnt = np.bincount(c.ravel(), minlength=n + 1)
        sl = ndi.find_objects(c)
        comp = np.where(m, np.where(c > 0, c - 1 + nxt, -1), comp)
        for i in range(1, n + 1):
            s = sl[i - 1]
            cols.append(k); sizes.append(int(cnt[i]))
            bboxes.append((s[1].start, s[0].start, s[1].stop, s[0].stop))
        nxt += n

    col_of = pal[np.array(cols, np.int32)]
    size_of = np.array(sizes, np.float64)
    cur = comp
    for _ in range(gap):
        d = ndi.grey_dilation(cur, footprint=NEI8)
        p = np.stack([cur.ravel(), d.ravel()], 1)
        p = p[(p[:, 0] >= 0) & (p[:, 1] >= 0) & (p[:, 0] != p[:, 1])]
        if not len(p):
            break
        ok = np.abs(col_of[p[:, 0]] - col_of[p[:, 1]]).sum(1) <= tol
        p = p[ok]
        if not len(p):
            continue
        g = coo_matrix((np.ones(len(p), np.float32), (p[:, 0], p[:, 1])), shape=(len(col_of),) * 2)
        lb = connected_components(g, directed=False)[1]
        ncc = lb.max() + 1
        sw = np.zeros((ncc, 3)); tw = np.zeros(ncc)
        np.add.at(sw, lb, col_of * size_of[:, None])
        np.add.at(tw, lb, size_of)
        col_of = sw / np.maximum(tw, 1.0)[:, None]
        size_of = tw
        cur = np.where(cur >= 0, lb[np.clip(cur, 0, None)], -1).astype(np.int32)
    return cur, (x0, y0), sub, pm


def partition(a, cells, gap=8, tol=80, minpx=250, ncol=24):
    """元素编号图（覆盖面板内每个像素，-1 表示不属于本面板）+ 元素统计"""
    H, W = a.shape[:2]
    cur, (x0, y0), sub, pm = merge_map(a, cells, gap, tol, ncol)
    ids = np.unique(cur); ids = ids[ids >= 0]
    cnt = {int(i): int((cur == i).sum()) for i in ids}
    seeds = [i for i in ids if cnt[int(i)] >= minpx]
    if not seeds:                       # 退化：全并成一块
        seeds = [int(max(ids, key=lambda i: cnt[int(i)]))]
    smask = np.isin(cur, seeds)
    seedlab = np.full(cur.shape, -1, np.int32)
    lut = {s: i for i, s in enumerate(seeds)}
    seedlab[smask] = np.vectorize(lut.get)(cur[smask])
    _, ind = ndi.distance_transform_edt(~smask, return_indices=True)
    el = seedlab[ind[0], ind[1]]

    stats = []
    for i, s in enumerate(seeds):
        m = el == i
        ys, xs = np.nonzero(m)
        bbox = (int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max()) + 1 + x0, int(ys.max()) + 1 + y0)
        ink = (el == i) & smask
        col = sub[ink].mean(0) if ink.any() else sub[m].mean(0)
        stats.append(dict(idx=i, seed=int(s), size=int(m.sum()), seed_px=cnt[int(s)],
                          bbox=bbox, color=[int(v) for v in col],
                          px=[int(xs.mean()) + x0, int(ys.mean()) + y0]))
    stats.sort(key=lambda s: -s["size"])
    remap = {s["idx"]: i for i, s in enumerate(stats)}
    out = np.full(cur.shape, -1, np.int32)
    for s in stats:
        out[el == s["idx"]] = remap[s["idx"]]
    for i, s in enumerate(stats):
        s["idx"] = i
    elimg = np.full((H, W), -1, np.int32); elimg[y0:y0 + cur.shape[0], x0:x0 + cur.shape[1]] = out
    return elimg, stats


def dump(a, cells, out_png="_el_overlay.png", out_txt="_el_table.txt", gap=8, tol=80, minpx=250):
    H, W = a.shape[:2]
    order = P.order(); meta = P.meta()
    vis = np.clip(a, 0, 255).astype(np.uint8).copy()
    rng = np.random.RandomState(3)
    lines = []
    allst = {}
    for cid in order:
        cs = [c for c in cells if c[0] == cid]
        el, stats = partition(a, cs, gap=gap, tol=tol, minpx=minpx)
        allst[cid] = stats
        lines.append("=== %-14s %-14s %s | 元素 %d" % (cid, meta[cid]["role"], meta[cid]["desc"], len(stats)))
        for s in stats:
            bx0, by0, bx1, by1 = s["bbox"]
            lines.append("  #%-3d seedpx=%-7d cover=%-7d box=(%4d,%4d,%4d,%4d) %4dx%-4d mean=#%02x%02x%02x center=(%4d,%4d)"
                         % (s["idx"], s["seed_px"], s["size"], bx0, by0, bx1, by1, bx1 - bx0, by1 - by0,
                            s["color"][0], s["color"][1], s["color"][2], s["px"][0], s["px"][1]))
        m = el >= 0
        cols = rng.randint(50, 256, (len(stats) + 1, 3))
        vis[m] = (0.30 * vis[m] + 0.70 * cols[el[m]]).astype(np.uint8)
    im = Image.fromarray(vis)
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 16)
    except Exception:
        f = ImageFont.load_default()
    for cid in order:
        for s in allst[cid]:
            x, y = s["px"]
            d.text((x + 1, y + 1), str(s["idx"]), fill=(0, 0, 0), font=f)
            d.text((x, y), str(s["idx"]), fill=(255, 255, 0), font=f)
    im.save(out_png)
    open(out_txt, "w", encoding="utf-8").write("\n".join(lines))
    print("写出 %s / %s" % (out_png, out_txt))
    return lines
