# -*- coding: utf-8 -*-
"""元素级「基色 + 明度层」重写：把「一个物理元素几千条单色 <path>」压成
   「k 个基色块 + 若干条 fill-opacity 明暗层」，让**整个物理色块**能一次改。

为什么需要它（实测）
--------------------
逐像素临摹的产物，结构上必然是「一种颜色一条 <path>」。交付版 `evo.svg`
（--q 0）实测：

    stage1-nucleus   5162 条 path = 5162 种 fill   （没有一条同色可并）
    stage4-fireball  6696 条 path = 6696 种 fill

图层虽然按【物理元素】分了（panel -> element -> path），但元素内部仍是
「色素集合」，改色只能一条一条改 —— 用户要的「改变整个物理的色块」做不到。

模型
----
每个元素用 k 个基色 C0 近似，元素内的像素只能沿两条**颜色无关**的方向偏离 C0：

    变暗： c = C0 * (1 - t)           ->  body(C0) + <path fill="#000" fill-opacity="t">
    变亮： c = C0 + (255 - C0) * s    ->  body(C0) + <path fill="#fff" fill-opacity="s">

t / s 量化成 `levels` 档，于是同元素内同 (tone, level) 的色块并成一条 path。
明暗层是黑/白 + opacity，**不含颜色**：改基色块的 fill，整个元素的明暗关系
自动跟着走 —— 这就是「整体改一个物理色块」。

实测（evo 算例，1662x925 工作分辨率，R=5 四叉树；数字见 CHANGELOG）：
    --shade auto:16:1  31005 条 path -> 541 条 | 1.84 MB | MAE 0.626 -> 0.919
                        （其中火球/交叠透镜走真渐变 body，其余走基色块）

参数
----
    levels    明度档数（16~128）。档越细越像、path 越多：128 档 2086 path / MAE 0.820。
    k         基色个数，"auto"= 自适应 1~3（残差降到 1.35 倍以内就不再加基色）。
    gradient  要不要试真渐变 body（radial/linear）。径向渐变**必须**用它，否则出色环。
    rem_err   色相偏得连"黑/白 + opacity"都补不回来的色块（残差 > 该值，级）改按原色
              平涂（remnant）。实测本图 22 -> 1421 path/MAE 0.897、45 -> 633/0.916、
              60 -> 541/0.919 —— 多 880 条 path 只换 0.022 MAE，默认 60。
"""
import numpy as np

from . import gradfit as GFT

LUM = np.array([0.299, 0.587, 0.114], np.float32)


def _dark_err(C, C0, levels):
    """变暗模型 t 量化成 levels 档后的逐通道平均误差"""
    t = np.clip(1.0 - (C @ C0) / max(1e-6, float(C0 @ C0)), 0.0, 1.0)
    tq = np.round(t * levels) / levels
    return np.abs(C - C0 * (1.0 - tq)[:, None]).mean(1)


def _light_err(C, C0, levels):
    U = 255.0 - C0
    if float(U @ U) < 1e-6:
        return np.full(len(C), 255.0, np.float32)
    s = np.clip(((C - C0) @ U) / float(U @ U), 0.0, 1.0)
    sq = np.round(s * levels) / levels
    return np.abs(C - (C0 + U * sq[:, None])).mean(1)


def _err(C, C0, levels):
    return np.minimum(_dark_err(C, C0, levels), _light_err(C, C0, levels))


def _resid(C, W, C0, levels):
    e = _err(C, C0, levels)
    return float((e * W).sum() / W.sum())


def _best_base(C, W, levels, pcts=(60, 70, 80, 85, 90, 95, 99, 100)):
    """基色候选 = 按亮度分位数取**原色**：平均色往往不是元素里真实存在的颜色，
    当基色会凭空多出一层色偏。"""
    lum = C @ LUM
    order = np.argsort(lum, kind="stable")
    cw = np.cumsum(W[order])
    cw = cw / cw[-1]
    best = None
    for pc in pcts:
        idx = order[-1] if pc >= 100 else order[min(len(C) - 1, int(np.searchsorted(cw, pc / 100.0)))]
        r = _resid(C, W, C[idx], levels)
        if best is None or r < best[0]:
            best = (r, C[idx].copy())
    return best


def _em(C, W, k, levels, iters=4):
    """加权 EM：E 步按「基色 + 明度」误差把颜色分给最近的基色，M 步重选该族基色。

    权重 = 色块像素数（四叉树叶块可能很大，不能按「颜色个数」平均）。
    """
    lum = C @ LUM
    order = np.argsort(lum, kind="stable")
    cw = np.cumsum(W[order])
    cw = cw / cw[-1]
    cen = [C[order[min(len(C) - 1, int(np.searchsorted(cw, (i + 1.0) / (k + 1))))]]
           for i in range(k)]
    lab = np.zeros(len(C), np.int32)
    for _ in range(iters):
        E = np.stack([_err(C, c, levels) for c in cen], 1)
        lab = E.argmin(1)
        nxt = []
        for j in range(k):
            sel = lab == j
            if not sel.any():
                nxt.append(cen[j])
                continue
            _, c0 = _best_base(C[sel], W[sel], levels)
            nxt.append(c0)
        same = all(np.allclose(a, b) for a, b in zip(cen, nxt))
        cen = nxt
        if same:
            break
    E = np.stack([_err(C, c, levels) for c in cen], 1)
    lab = E.argmin(1)
    return cen, lab, E.min(1)


def fit(items, levels=16, kmax=3, tol=1.35, resid_cap=8.0, kforce=None, rem_err=60.0):
    """items = [(color_tuple, [rects]), ...]（同一元素内的全部色块）

    返回 None（不划算，建议保留原色阶）或 dict：
        bases   k 个基色 [(r,g,b), ...]
        assign  {color_tuple: (k_index, tone, level)}   tone 0=变暗 1=变亮
        resid   加权平均绝对误差（0~255 级）  k / levels / kmax
    """
    if not items:
        return None
    C = np.stack([np.asarray(c, np.float32) for c, _ in items])
    W = np.array([sum(float(r[2]) * float(r[3]) for r in rs) for _, rs in items], np.float64)
    if W.sum() <= 0:
        return None
    kmax = max(1, min(int(kmax), len(items)))
    cands = []
    for k in range(1, kmax + 1):
        cen, lab, e = _em(C, W, k, levels)
        cands.append((k, cen, lab, float((e * W).sum() / W.sum())))
    rmin = min(c[3] for c in cands)
    k, cen, lab, res = cands[0]
    if kforce:                            # 写死基色个数（--shade k:levels 里的 k）
        k, cen, lab, res = cands[min(int(kforce), len(cands)) - 1]
    else:                                 # 自适应：最小的 k 只要已接近最好（<= tol×最好）就用它
        for c in cands:
            if c[3] <= max(tol * rmin, 0.25):
                k, cen, lab, res = c
                break
    if res > resid_cap:
        return None
    assign = {}
    for i, (col, _) in enumerate(items):
        C0 = cen[lab[i]]
        U = 255.0 - C0
        t = float(np.clip(1.0 - (C[i] @ C0) / max(1e-6, float(C0 @ C0)), 0.0, 1.0))
        s = (float(np.clip(((C[i] - C0) @ U) / float(U @ U), 0.0, 1.0))
             if float(U @ U) > 1e-6 else 0.0)
        ed = float(np.abs(C[i] - C0 * (1.0 - t)).mean())
        el = float(np.abs(C[i] - (C0 + U * s)).mean())
        if ed <= el:
            tone, lev = 0, round(t * levels) / levels
        else:
            tone, lev = 1, round(s * levels) / levels
        if min(ed, el) > rem_err:
            # ★ 明度怎么调都不像（残差是**色相**偏，不是明度偏）——比如擦字补背景留下的
            #   深色残迹，用"黑 + opacity"糊出来就是一块黑斑。改成 remnant：按原色平涂。
            tone, lev = 2, 0.0
        assign[col] = (int(lab[i]), tone, float(lev))
    return dict(mode="flat", bases=[tuple(float(v) for v in c) for c in cen],
                assign=assign, resid=res, k=int(k), levels=int(levels), kmax=int(kmax))


def d_of(rects):
    return "".join("M%d %dh%dv%dh-%dz" % (x, y, w, h, w) for x, y, w, h in rects)


def hexs(c):
    return "#%02x%02x%02x" % (int(round(c[0])), int(round(c[1])), int(round(c[2])))

# --------------------------------------------------- 真渐变 body（径向渐变上的色环解药）
def fit_grad(a, mask, items, levels=16, nstops=16, tol=26, minpx=800, eps=1.0,
             rem_err=60.0):
    """元素 = **一条真 <radialGradient>/<linearGradient> body** + 少量明度层残差。

    为什么不能只用平涂基色：径向渐变（火球）用「平涂基色 + N 档明度层」近似时，
    每一档都沿等半径连成一个环 —— 实测 N=24 时球面上出现肉眼可见的同心色环，
    正是用户最不想要的「色阶退化」。干脆让真渐变去画那条平滑的径向 ramp，
    明度层只补残差（残差 2.4 级 < 半档，于是绝大多数色块根本不画层）。

    只在梯度**单一连通域**（多连通会漏画别的连通块）时启用；
    kind=aradial 要用 <g transform>（cairosvg 会忽略径向渐变的 gradientTransform），
    本函数直接放弃 aradial —— 那些元素改用平涂模型，实测残差本来也更低。

    返回 None 或 dict(mode="grad", g=梯度, resid, assign=[(rect, tone, lev)...], shape=(d,npts))
    """
    from scipy import ndimage
    m = np.asarray(mask, bool)
    if m.sum() < minpx:
        return None
    # ★ 元素掩膜常常是「1 大块 + 若干小碎块」（擦字补背景的散点、被 SPLIT 切走的
    #   核子留下的洞边）。轮廓跟踪只能跟**单连通**区域，所以：只把最大连通块当 body
    #   形状，覆盖率不够就放弃；不在 body 里的色块原样按平涂色块画（见 leftover）。
    m2 = ndimage.binary_fill_holes(ndimage.binary_closing(m, np.ones((3, 3)), iterations=2))
    lab, n = ndimage.label(m2)
    if n < 1:
        return None
    if n > 1:
        cnt = ndimage.sum(m2, lab, np.arange(1, n + 1))
        m2 = lab == (int(np.argmax(cnt)) + 1)
    if m2.sum() < 0.98 * m.sum():
        return None
    g = GFT.fit(a, m, nstops=nstops, tol=tol, minpx=minpx)
    if g is None or g["kind"] == "aradial":
        return None
    stops = np.asarray(g["stops"], np.float64)
    cols, cx, cy, area, flat = [], [], [], [], []
    for col, rects in items:
        for (x, y, w, h) in rects:
            cols.append(col); cx.append(x + w * 0.5); cy.append(y + h * 0.5)
            area.append(float(w) * float(h)); flat.append((x, y, w, h))
    C = np.asarray(cols, np.float64)
    t = GFT._project(g["kind"], g["geom"], np.asarray(cx, float), np.asarray(cy, float))
    tn = np.clip((t - g["tmin"]) / max(g["tmax"] - g["tmin"], 1e-9), 0.0, 1.0)
    # ★ 预测色必须按**渲染器真正的语义**算：SVG 的 stop 是均匀 offset（i/(n-1)）上
    #   线性插值，不是"分箱取平均"。用分箱均值当预测色，会在箱边界上差出一整档，
    #   于是大片像素被判成"明度层补不了" -> 变成几百条 remnant（实测火球 28 -> 760 条）。
    n = len(stops)
    u = tn * (n - 1)
    k0 = np.clip(np.floor(u).astype(int), 0, n - 1)
    fr = (u - k0)[:, None]
    P = stops[k0] * (1.0 - fr) + stops[np.minimum(k0 + 1, n - 1)] * fr
    U = 255.0 - P
    dt = np.clip(1.0 - (C * P).sum(1) / np.maximum(1e-6, (P * P).sum(1)), 0.0, 1.0)
    ls = np.clip(((C - P) * U).sum(1) / np.maximum(1e-6, (U * U).sum(1)), 0.0, 1.0)
    ed = np.abs(C - P * (1.0 - dt)[:, None]).mean(1)
    el = np.abs(C - (P + U * ls[:, None])).mean(1)
    dark = ed <= el
    lev = np.round(np.where(dark, dt, ls) * levels) / levels
    e = np.where(dark, ed, el)
    W = np.asarray(area, np.float64)
    resid_bands = float((e * W).sum() / W.sum())
    # ★ 拿**渐变本身的残差**当"选型指标"，不是"渐变+明度层"的残差：
    #   明度层是按「色块中心处的预测色」补的，而大色块横跨 ramp 时
    #   块内平均色 ≠ 块心处的渐变色 —— 补出来就是一块块斑（实测形变核上
    #   出现明显的方块）。渐变本身的残差才是"这条路值不值得走"的真判据。
    resid = float(g["resid"])
    d, npts = GFT.mask_path(m2, eps)
    if not d:
        return None
    assign = []
    for i in range(len(flat)):
        tone = int(0 if dark[i] else 1)
        if e[i] > rem_err:
            tone = 2
        assign.append((cols[i], flat[i], tone, float(lev[i])))
    # body 盖不到的色块（小碎块）：原样按平涂色块画，别让它们落在背景上变白
    leftover = [(cols[i], flat[i]) for i in range(len(flat))
                if not m2[min(m2.shape[0] - 1, int(cy[i])), min(m2.shape[1] - 1, int(cx[i]))]]
    nleft = len({c for c, _ in leftover})
    nrem = len({c for c, _, t, _ in assign if t == 2})
    return dict(mode="grad", g=g, resid=resid, resid_bands=resid_bands, assign=assign,
                shape=(d, npts), leftover=leftover, nleft=nleft, nrem=nrem,
                levels=int(levels))
