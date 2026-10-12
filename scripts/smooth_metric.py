#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smooth_metric -- 「放大后会不会看出台阶」的可测判据（位图 → 矢量 的验收读数）

问的问题
    矢量化最容易翻车的地方不是"像不像"，而是**放大后能不能看见刻面/台阶**。
    "光滑"必须能测，否则只能靠嘴说。本脚本给的就是那把尺子。

判据（v4.10，实测标定）
    只在**位图本身就是平滑**的像素上量 —— 否则量到的是文字/星芒/色块边界，不是矢量的锅。
      · 平滑像素 = 相邻像素最大通道差 <= --step（默认 3），且**行、列两个方向的邻居都满足**；
      · 再按 --erode 内缩（默认 7 px，避开抗锯齿过渡带）；
      · 在这块区域上量 A 与 B 的**相邻像素最大通道差**：mean / p99 / >--thr 占比 / max。

为什么这条比 MAE 更能说明问题
    MAE 是整图平均，一条硬边摊到几万像素上就看不见了；而"跳变 >8 的像素占比"直接就是
    放大后肉眼看到的台阶/刻面。实测（喷注淬火图，火球面 137416 px 区域）：
        位图自己（对照）  mean 0.62 / p99 3 / >8 占比 0.000
        VTracer 0.6.15     mean 0.73 / p99 14 / >8 占比 0.024   <- 2.4% 的像素跳 >8
        本 skill 光滑档      mean 0.58 / p99 3 / >8 占比 0.000   <- 与位图自己无法区分
        本 skill 对象档      mean 0.73 / p99 13 / >8 占比 0.015

用法
    python3 scripts/smooth_metric.py 位图.png 成品渲染.png [--roi x0,y0,x1,y1] [--mask m.npz:fireball]
                              [--erode 7] [--step 3] [--thr 8]

    --roi   只量这个框（前闭后开）
    --mask  只量这个掩膜（用「位图 → 语义分层」的 _vis_trace.npz 键名最方便）
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image
from scipy import ndimage


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int16)


def smooth_pixels(A, step):
    def mx(a, b):
        return np.abs(a - b).max(2)
    H, W = A.shape[:2]
    gx = np.zeros((H, W), np.int16); gx[:, 1:] = mx(A[:, 1:], A[:, :-1])
    gx2 = np.zeros((H, W), np.int16); gx2[:, :-1] = gx[:, 1:]
    gy = np.zeros((H, W), np.int16); gy[1:, :] = mx(A[1:, :], A[:-1, :])
    gy2 = np.zeros((H, W), np.int16); gy2[:-1, :] = gy[1:, :]
    return (gx <= step) & (gx2 <= step) & (gy <= step) & (gy2 <= step)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", help="参考位图（判「哪些像素本来就平滑」用它的读数）")
    ap.add_argument("test", help="要检的成品渲染图（同尺寸）")
    ap.add_argument("--roi", default="", help="x0,y0,x1,y1（可选）")
    ap.add_argument("--mask", default="", help="mask.npz:key（可选；与 --roi 可叠加）")
    ap.add_argument("--erode", type=int, default=7)
    ap.add_argument("--step", type=int, default=3)
    ap.add_argument("--thr", type=int, default=8)
    a = ap.parse_args()

    A, B = load(a.ref), load(a.test)
    if A.shape != B.shape:
        sys.exit("size mismatch: %s vs %s" % (A.shape, B.shape))

    R = smooth_pixels(A, a.step)
    if a.roi:
        x0, y0, x1, y1 = [int(v) for v in a.roi.split(",")]
        box = np.zeros(R.shape, bool); box[y0:y1, x0:x1] = True
        R &= box
    if a.mask:
        p, key = a.mask.rsplit(":", 1)
        z = np.load(p, allow_pickle=True)
        m = z[key]
        if m.dtype == np.uint8 and m.size * 8 == R.size:
            m = np.unpackbits(m)[:R.size]
        m = np.asarray(m).reshape(R.shape) > 0
        R &= m
    n0 = int(R.sum())
    if a.erode:
        R = ndimage.binary_erosion(R, ndimage.generate_binary_structure(2, 2), iterations=a.erode)
    n = int(R.sum())
    if n == 0:
        sys.exit("empty region after erode (was %d px)" % n0)

    d = np.abs(A - B).max(2)[R]
    print("%-22s mean %6.2f | p99 %4.0f | >%d %7.3f | max %4d   (%d px, erode %d)"
          % (a.test.split("/")[-1], d.mean(), np.percentile(d, 99),
             a.thr, float((d > a.thr).mean()), d.max(), n, a.erode))
    print("  参考位图自己（同区域）：", end="")
    g = smooth_pixels(A, a.step)
    # 位图自身的相邻跳变（同一区域）—— 作为"无法再低"的对照
    dd = np.zeros(A.shape[:2], np.int16)
    dd[:, 1:] = np.abs(A[:, 1:] - A[:, :-1]).max(2)
    dd2 = np.zeros(A.shape[:2], np.int16)
    dd2[:, :-1] = dd[:, 1:]
    e = np.maximum(dd, dd2)[R]
    print(" mean %6.2f | p99 %4.0f | >%d %7.3f | max %4d"
          % (e.mean(), np.percentile(e, 99), a.thr, float((e > a.thr).mean()), e.max()))


if __name__ == "__main__":
    main()
