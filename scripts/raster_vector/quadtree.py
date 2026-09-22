# -*- coding: utf-8 -*-
"""quadtree.py —— 扁平分色块四叉树（位图 -> 严格不相交的矩形）

对「色块 + 硬边」类图（科研示意图 / 三维渲染示意图）精度远高于梯度网格。

★ 两条必须遵守的规则（都是踩过的坑）：
  1) 合并只能「**列相邻 且 同色**」—— 否则矩形互相重叠，出图顺序一变整张图就错。
     实测：重叠 66.8%（max 覆盖 8 层）时，逆序出图 MAE 12.47 vs 自然序 0.25。
  2) 矩形必须按面板边界切开（见 groupvec.runs_cells），否则后画的面板会盖住
     前一个面板的文字（实测「Head-on col」整个消失）。

参数：R = 允许的最大色差（0-255，越大块越粗），K = 最粗边长 2^K。
  R=16, K=7（基准 1200px 宽）实测：MAE 0.227（非文字区），PSNR 49.4 dB。
  R=32, K=6 更小更快，但 MAE 升到 0.28。
"""
import numpy as np


def pyramid(a, K):
    ph, pw = (-a.shape[0]) % (1 << K), (-a.shape[1]) % (1 << K)
    A = np.pad(a, ((0, ph), (0, pw), (0, 0)), mode="edge")
    me = [A]; mx = [A]; mn = [A]
    for k in range(1, K + 1):
        n, w = mx[-1].shape[0] // 2 * 2, mx[-1].shape[1] // 2 * 2
        me.append(me[-1][:n, :w].reshape(n // 2, 2, w // 2, 2, 3).mean((1, 3)))
        mx.append(mx[-1][:n, :w].reshape(n // 2, 2, w // 2, 2, 3).max((1, 3)))
        mn.append(mn[-1][:n, :w].reshape(n // 2, 2, w // 2, 2, 3).min((1, 3)))
    return me, [(mx[k] - mn[k]).max(2) for k in range(K + 1)]


def build(a, R, K):
    me, RG = pyramid(a, K)
    leaves = {k: [] for k in range(K + 1)}
    leaves[K] = [(i, j) for i in range(me[K].shape[0]) for j in range(me[K].shape[1])]
    for k in range(K, 0, -1):
        keep = []
        for (i, j) in leaves[k]:
            if RG[k][i, j] > R:
                for di in (0, 1):
                    for dj in (0, 1):
                        leaves[k - 1].append((2 * i + di, 2 * j + dj))
            else:
                keep.append((i, j))
        leaves[k] = keep
    return me, leaves


def runs(me, leaves, Wd, H, K):
    """叶块 -> 同色水平合并的矩形条，按颜色分组"""
    from itertools import groupby
    bycol = {}
    for k in range(K + 1):
        if not leaves[k]:
            continue
        s = 1 << k; m = me[k]
        for r, grp in groupby(sorted(leaves[k]), key=lambda t: t[0]):
            row = [j for _, j in grp]
            start = 0
            for t in range(1, len(row) + 1):
                if t == len(row) or not np.array_equal(m[r, row[t]], m[r, row[t - 1]]):
                    j0, j1 = row[start], row[t - 1] + 1
                    x0, x1 = min(j0 * s, Wd), min(j1 * s, Wd)
                    y0, y1 = min(r * s, H), min((r + 1) * s, H)
                    if x1 > x0 and y1 > y0:
                        c = m[r, row[start]]
                        key = (int(round(c[0])), int(round(c[1])), int(round(c[2])))
                        bycol.setdefault(key, []).append((x0, y0, x1 - x0, y1 - y0))
                    start = t
    return bycol
