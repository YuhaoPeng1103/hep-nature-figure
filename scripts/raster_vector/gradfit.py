# -*- coding: utf-8 -*-
"""gradfit —— 把大块「平滑渐变」的量化台阶合并回一个**真** <radialGradient>/<linearGradient>

为什么必须做
------------
四叉树 + 颜色量化（--q）把连续渐变压成一级级台阶。对**低对比的冷灰渐变**
（形变核那种蓝灰球面）台阶还会沿 R/G/B 三通道错开，肉眼就是一块块"蓝斑" ——
实测 gen/render_s31_clean.png 的形变核本体里有 25793 px 的 b-r>=6 偏蓝像素，
q=16 量化后它们就变成互不连通的台阶块。调小 --R / 调大 --q 只能减轻，消不掉。

做法（先理解，再合并）
----------------------
1. 拿到某个物理元素的像素掩膜 M（groupvec 的 eid_full）
2. 迭代 4 遍（抗离群：描边、网格线、子结构都算离群）：
     三种模型，都用同样的 nstops 个 bin 的「bin 内平均色」当函数值 ——
       radial   色 = f(|p-c|)                     （圆形等色线）
       aradial  色 = f(|C^-1/2 (p-c)|)            （等色线 = 区域协方差椭圆，
                                                   经 gradientTransform 精确表达）
       linear   色 = f((p-c)·d)，d 由最小二乘定方向
     取「在重新判定的渐变内像素上残差最小」的那个
3. 残差 > tol 就**放弃**（说明这块不是干净渐变，宁可与原来一样留台阶）
4. 掩膜闭运算 + 填洞 -> 外轮廓 -> Douglas-Peucker 简化 -> 一条 <path>
5. 输出梯度定义 + 形状；元素里凡是「落在渐变内、且自身颜色也贴合模型」的色块
   由调用方丢掉（台阶没了），**网格线与描边不在渐变内**，照旧留着画在上面

只认实测：残差、像素数、轮廓点数都由调用方打印。
"""
from __future__ import annotations

import numpy as np

NEIGH = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


# ------------------------------------------------------------------ 轮廓
def trace_outer(mask):
    """Moore 邻域跟踪，返回单连通区域的外轮廓 [(x,y)...]。输入必须先填洞。"""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    y0 = ys.min()
    start = (y0, int(xs[ys == y0].min()))
    cur, back = start, (start[0], start[1] - 1)
    pts = [start]
    cap = 8 * int(mask.sum()) + 64
    for _ in range(cap):
        d0 = (back[0] - cur[0], back[1] - cur[1])
        i0 = NEIGH.index(d0) if d0 in NEIGH else 0
        nxt = None
        for k in range(1, 9):
            d = NEIGH[(i0 + k) % 8]
            ny, nx = cur[0] + d[0], cur[1] + d[1]
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx]:
                nb = NEIGH[(i0 + k - 1) % 8]
                nxt, back = (ny, nx), (cur[0] + nb[0], cur[1] + nb[1])
                break
        if nxt is None:
            break
        cur = nxt
        if cur == start and len(pts) > 3:
            break
        pts.append(cur)
    return [(p[1], p[0]) for p in pts]


def dp(pts, eps):
    """Douglas-Peucker 抽稀"""
    if len(pts) < 3:
        return pts
    P = np.asarray(pts, float)
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        A, AB = P[i], P[j] - P[i]
        seg = P[i + 1:j]
        L = float(np.hypot(*AB))
        if L < 1e-9:
            dist = np.hypot(seg[:, 0] - A[0], seg[:, 1] - A[1])
        else:
            dist = np.abs(AB[0] * (seg[:, 1] - A[1]) - AB[1] * (seg[:, 0] - A[0])) / L
        k = int(np.argmax(dist))
        if dist[k] > eps:
            idx = i + 1 + k
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [tuple(p) for p in P[keep]]


def mask_path(mask, eps=1.1):
    """掩膜 -> SVG path 的 d（L 折线 + Z）。返回 (d, 点数)"""
    pts = dp(trace_outer(mask), eps)
    if len(pts) < 3:
        return None, 0
    d = "M%s" % " ".join("%.1f %.1f" % (x, y) for x, y in pts) + "Z"
    return d, len(pts)


# ------------------------------------------------------------------ 拟合
def _binstat(t, cols, n):
    tn = (t - t.min()) / max(float(t.max() - t.min()), 1e-9)
    idx = np.clip((tn * n).astype(int), 0, n - 1)
    cnt = np.bincount(idx, minlength=n).astype(float)
    mean = np.zeros((n, 3), np.float64)
    for c in range(3):
        mean[:, c] = np.bincount(idx, weights=cols[:, c].astype(np.float64),
                                 minlength=n) / np.maximum(cnt, 1.0)
    # 空 bin 用最近的非空 bin 补（避免 gradient stop 出现 0,0,0）
    good = cnt > 0
    if not good.any():
        return None, None
    pos = np.nonzero(good)[0]
    for i in range(n):
        if not good[i]:
            mean[i] = mean[pos[np.argmin(np.abs(pos - i))]]
    resid = float(np.abs(cols - mean[idx]).mean())
    return mean, resid


def _candidates(xx, yy, cc, W, H):
    """三种模型的 (kind, geom, t)，t 是未归一化的模型坐标"""
    out = []
    cx, cy = float(xx.mean()), float(yy.mean())
    out.append(("radial", {"cx": cx, "cy": cy}, np.hypot(yy - cy, xx - cx)))
    P = np.stack([xx - cx, yy - cy], 1).astype(np.float64)
    if len(P) > 8:
        C = (P.T @ P) / max(len(P) - 1, 1)
        try:
            wv, V = np.linalg.eigh(C)
            wv = np.maximum(wv, 1e-6)
            R = V @ np.diag(np.sqrt(wv)) @ V.T          # C^(1/2)
            Q = np.linalg.inv(R)                        # 白化：等色线 = 区域协方差椭圆
            t = np.hypot(*(P @ Q.T).T)
            out.append(("aradial", {"cx": cx, "cy": cy, "Q": Q.tolist()}, t))
            # ★ saradial：白化空间里把「等色线中心」也搜一遍。
            #   渲染球体的高光不在几何中心（平行光），只准用质心时径向模型会输给
            #   线性模型 —— 实测形变核就是这样（linear 残差 7.03 胜过 aradial）。
            #   搜索半径取 ±0.6 个「椭圆半轴」：再远就不像球面明暗了。
            U = P @ Q.T
            for ou in (-0.6, -0.3, 0.0, 0.3, 0.6):
                for ov in (-0.6, -0.3, 0.0, 0.3, 0.6):
                    if ou == 0.0 and ov == 0.0:
                        continue
                    c2 = np.array([cx, cy]) + R @ np.array([ou, ov])
                    out.append(("aradial", {"cx": float(c2[0]), "cy": float(c2[1]),
                                            "Q": Q.tolist()},
                                np.hypot(U[:, 0] - ou, U[:, 1] - ov)))
        except np.linalg.LinAlgError:
            pass
    # linear：先解「位置 -> 颜色」的 2x3 线性映射，再取「单位位移让颜色变化最大」
    # 的那个方向（= M^T M 的最大特征向量）。★ 不能按通道分别定方向：三个通道的
    # 方向可能不同，逐通道取 hypot 会得到长度 3 的数组（实测 TypeError）。
    if len(xx) > 8:
        Xc = np.stack([xx - cx, yy - cy], 1).astype(np.float64)
        Cc = cc.astype(np.float64) - cc.astype(np.float64).mean(0)
        M = np.linalg.lstsq(Xc, Cc, rcond=None)[0]        # (2,3)
        wv, V = np.linalg.eigh(M @ M.T)                   # (2,2) 对称
        d = V[:, -1]
        n = float(np.hypot(*d))
        if n > 1e-9:
            d = d / n
            out.append(("linear", {"cx": cx, "cy": cy, "dir": d.tolist()},
                        (xx - cx) * d[0] + (yy - cy) * d[1]))
    return out


def _project(kind, geom, xs, ys):
    if kind == "radial":
        return np.hypot(ys - geom["cy"], xs - geom["cx"])
    if kind == "aradial":
        Q = np.asarray(geom["Q"], float)
        P = np.stack([xs - geom["cx"], ys - geom["cy"]], 1)
        return np.hypot(*(P @ Q.T).T)
    d = np.asarray(geom["dir"], float)
    return (xs - geom["cx"]) * d[0] + (ys - geom["cy"]) * d[1]


def fit(a, M, nstops=8, tol=26, minpx=1500, iters=4, src=None, drop_tol=None):
    """拟合一块区域的渐变。返回 dict 或 None（残差过大 = 不是干净渐变，放弃）。

    a   —— 用来定几何/颜色统计的图（通常是**量化前**的原图）
    M   —— 渐变内像素掩膜（来自量化图的元素划分，几何不受量化影响）
    src —— 若给了就用它的颜色（不量化更准：量化误差本身就有 ±8.5/通道）

    dict: kind / geom / stops(每档 RGB) / tmin / tmax / mask(最终渐变内掩膜) / resid / px
    """
    ys, xs = np.nonzero(M)
    if len(ys) < minpx:
        return None
    H, W = a.shape[:2]
    C_all = (src if src is not None else a)[ys, xs].astype(np.float64)
    keep = np.ones(len(ys), bool)
    best = None
    for _ in range(iters):
        if keep.sum() < minpx:
            return None
        cand = _candidates(xs[keep].astype(float), ys[keep].astype(float),
                          C_all[keep], W, H)
        pick = None
        for kind, geom, t in cand:
            mean, resid = _binstat(t, C_all[keep], nstops)
            if mean is None:
                continue
            if pick is None or resid < pick[3]:
                pick = (kind, geom, mean, resid, t)
        if pick is None:
            return None
        kind, geom, mean, resid, _t = pick
        t_all = _project(kind, geom, xs.astype(float), ys.astype(float))
        tmin, tmax = float(t_all[keep].min()), float(t_all[keep].max())
        tn = (t_all - tmin) / max(tmax - tmin, 1e-9)
        idx = np.clip((tn * nstops).astype(int), 0, nstops - 1)
        keep = np.abs(C_all - mean[idx]).max(1) <= tol
        best = (kind, geom, mean, tmin, tmax)
    if best is None or keep.sum() < minpx:
        return None
    kind, geom, mean, tmin, tmax = best
    t_all = _project(kind, geom, xs.astype(float), ys.astype(float))
    tn = (t_all - tmin) / max(tmax - tmin, 1e-9)
    idx = np.clip((tn * nstops).astype(int), 0, nstops - 1)
    resid = float(np.abs(C_all[keep] - mean[idx[keep]]).mean())
    if resid > tol:
        return None
    from scipy import ndimage
    m2 = np.zeros((H, W), bool)
    m2[ys[keep], xs[keep]] = True
    m2 = ndimage.binary_closing(m2, np.ones((3, 3)), iterations=2)
    m2 = ndimage.binary_fill_holes(m2)
    if m2.sum() < minpx:
        return None
    dev = np.abs(C_all - mean[idx]).max(1)
    fm = np.zeros((H, W), bool)
    fm[ys[keep], xs[keep]] = True
    # ★ dropmask 与 fitmask 分开：拟合容差 tol 要宽（不然模型欠拟合），
    #   但"丢台阶块"的容差必须**更紧** —— 浅色球面上网格线只比底色暗 30~50 级，
    #   在偏暗的区域（左下）两者会挤到 tol 以内，用 tol 判就会把网格线丢成虚线。
    dt = float(drop_tol) if drop_tol is not None else min(float(tol), 20.0)
    dm = np.zeros((H, W), bool)
    sel = dev <= dt
    dm[ys[sel], xs[sel]] = True
    return dict(kind=kind, geom=geom, stops=mean, tmin=tmin, tmax=tmax,
                mask=m2, fitmask=fm, dropmask=dm, resid=resid, px=int(keep.sum()))


def svg_defs(gid, g):
    """梯度定义（放进 <defs>）"""
    st = "".join('<stop offset="%.3f" stop-color="#%02x%02x%02x"/>'
                 % (i / max(len(g["stops"]) - 1, 1),
                    int(round(c[0])), int(round(c[1])), int(round(c[2])))
                 for i, c in enumerate(g["stops"]))
    if g["kind"] == "linear":
        d = np.asarray(g["geom"]["dir"], float)
        c = np.array([g["geom"]["cx"], g["geom"]["cy"]])
        p0 = c + d * g["tmin"]
        p1 = c + d * g["tmax"]
        return ('<linearGradient id="%s" gradientUnits="userSpaceOnUse" '
                'x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f">%s</linearGradient>'
                % (gid, p0[0], p0[1], p1[0], p1[1], st))
    if g["kind"] == "radial":
        return ('<radialGradient id="%s" gradientUnits="userSpaceOnUse" '
                'cx="%.1f" cy="%.1f" r="%.1f">%s</radialGradient>'
                % (gid, g["geom"]["cx"], g["geom"]["cy"],
                   max(g["tmax"], 1e-6), st))
    # ★ aradial（等色线 = 区域协方差椭圆）**不能用 gradientTransform**：
    #   实测 cairosvg 会忽略径向渐变的 gradientTransform —— 200x200 的对照图里
    #   `matrix(.005 0 0 .01 100 100)` 与不带 transform 的渲染逐像素相同：渐变中心
    #   根本没动，整块填成最外档颜色（stage2 / stage3-核A / stage4-核子 三块第一次
    #   跑崩就是这个原因）。改成把形状写进 `<g transform>`、渐变用**局部坐标系**里的
    #   普通圆形 radialGradient（形状路径的坐标由 svg_shape 反算），任何渲染器都对。
    return ('<radialGradient id="%s" gradientUnits="userSpaceOnUse" '
            'cx="0" cy="0" r="1">%s</radialGradient>' % (gid, st))


def svg_shape(gid, g, eps=1.1):
    """渐变形状。aradial 要额外包一层 <g transform>（见 svg_defs 的注释）。"""
    if g["kind"] != "aradial":
        d, npts = mask_path(g["mask"], eps)
        if d is None:
            return None, 0
        return ('<path id="%s-shape" data-role="gradient-shape" data-resid="%.2f" '
                'data-px="%d" fill="url(#%s)" d="%s"/>'
                % (gid, g["resid"], int(g["mask"].sum()), gid, d), npts)
    Q = np.asarray(g["geom"]["Q"], float) / max(g["tmax"], 1e-6)   # user -> local
    R = np.linalg.inv(Q)                                          # local -> user
    c = np.array([g["geom"]["cx"], g["geom"]["cy"]])
    pts = dp(trace_outer(g["mask"]), eps)
    if len(pts) < 3:
        return None, 0
    u = (np.asarray(pts, float) - c) @ Q.T
    d = "M" + " ".join("%.3f %.3f" % (a, b) for a, b in u) + "Z"
    return ('<g transform="matrix(%.6f %.6f %.6f %.6f %.2f %.2f)" '
            'data-role="gradient-wrap"><path id="%s-shape" data-role="gradient-shape" '
            'data-resid="%.2f" data-px="%d" fill="url(#%s)" d="%s"/></g>'
            % (R[0, 0], R[1, 0], R[0, 1], R[1, 1], c[0], c[1],
               gid, g["resid"], int(g["mask"].sum()), gid, d), len(pts))


def rect_covered(x, y, w, h, g, bad_frac=0.03):
    """这条矩形色块该不该丢：**整块像素**都得在渐变里。

    ★ 不能用「块心 + 颜色容差」：浅色球面上的网格线只比底色暗 30~50 级，四叉树
      在线上切出来的碎块其平均色已被底色拉回来，容差 30 就会把网格线一起丢掉
      （实测第一次跑 stage1/stage3 的网格线整片消失）。改成逐像素判定后，
      含网格线/描边的块一定留着、纯渐变块才丢。
    """
    fm = g.get("dropmask")
    if fm is None:
        return False
    # ★ 细条一律不丢：网格线只有 1~2px 宽，它的**抗锯齿过渡像素**与底色只差十几级，
    #   光靠颜色判据必然被当成"渐变内"丢掉 -> 网格线断成虚线（实测两轮都是这个病）。
    #   四叉树在细线/描边处会一路细分，细线的块必然是"细条"（min(w,h) < 3），
    #   拿形状当第二道闸就稳了：只有够大的平整色块才可能是渐变的台阶。
    if min(w, h) < 3:
        return False
    x0, y0 = int(x), int(y)
    x1, y1 = min(fm.shape[1], int(x + w)), min(fm.shape[0], int(y + h))
    if x1 <= x0 or y1 <= y0:
        return False
    sub = fm[y0:y1, x0:x1]
    area = sub.size
    return int((~sub).sum()) * 100 <= bad_frac * 100 * area
