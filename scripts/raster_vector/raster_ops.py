# -*- coding: utf-8 -*-
"""raster_ops.py —— 词表读取 / 墨迹掩膜 / 修补（groupvec 需要的四个纯 numpy 工具）

词表格式（UTF-8，Tab 分隔，**源图的 2 倍图**坐标系）：
    x<TAB>y<TAB>w<TAB>h<TAB>text
由 Windows.Media.Ocr 产出（见 ocr_words.ps1）；没有词表就用 --no-text。

read_words 的过滤阈值按「工作分辨率 1200px 宽」为基准（高 6~40px、宽 4~400px），
并随实际工作宽度等比缩放 —— 它同时挡掉 OCR 垃圾框和公式里被切碎的小方块。

★ 以前是写死的 6~40px，于是 `--W 1664` 下高 49px 的标签会被当成垃圾丢掉（
实测 2026-09-26：7 个手写词只进了 3 个，出图只剩 1 个 <text>）。
"""
import numpy as np
from scipy import ndimage


def read_words(path, sc, work_w=1200.0):
    # 阈值随工作宽度等比缩放（基准 1200px）
    k = float(work_w) / 1200.0
    hmin, hmax, wmin, wmax = 6 * k, 40 * k, 4 * k, 400 * k
    out = []
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 5 or not p[4].strip():
            continue
        x, y, w, h = (float(v) * sc for v in p[:4])
        t = p[4]
        # 过滤 OCR 垃圾框 / 非文字框：正常文字高 8~40px（工作分辨率下）
        # 只按单边尺寸过滤：长的正文行（"Pressure-driven hydrodynamic expansion"
        # 这类）框面积必然大，用 w*h 上限会把整条都丢掉
        if h < hmin or h > hmax or w < wmin or w > wmax:
            continue
        if not any(ch.isalnum() for ch in t):
            continue
        out.append((x, y, w, h, t))
    return out


def text_mask(shape, words, sc, pad=2, ink=None):
    m = np.zeros(shape, bool)
    for x, y, w, h, t in words:
        x0 = max(0, int(x - pad * sc)); x1 = min(shape[1], int(np.ceil(x + w + pad * sc)))
        y0 = max(0, int(y - pad * sc)); y1 = min(shape[0], int(np.ceil(y + h + pad * sc)))
        m[y0:y1, x0:x1] = True
    if ink is not None:                      # 只擦真实笔画，不擦整个框
        m = m & ndimage.binary_dilation(ink, iterations=1)
    return m


def ink_map(a):
    """局部对比度 -> 笔画像素。文字/线条为真，平坦背景为假"""
    lum = a.mean(2)
    bg = ndimage.median_filter(lum, 17)
    return np.abs(lum - bg) > 20


def inpaint(a, m, sig=5.0):
    w = (~m).astype(np.float32)
    k = (0, 0, 0)
    num = ndimage.gaussian_filter(a * w[..., None], (sig, sig, 0))
    den = ndimage.gaussian_filter(w, (sig, sig))[..., None]
    return np.where(m[..., None], num / np.maximum(den, 1e-6), a).astype(np.float32)
