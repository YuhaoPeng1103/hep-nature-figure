#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_roundtrip —— 「排版后的 PDF」回渲染，和原成品位图逐像素比

为什么需要它
------------
check_delivery.py 只回答"是不是纯矢量、文字可不可提取"，
audit_composition.py 只回答"排版有没有撞车"。
**没有一个工具回答"印出来还像不像原图"** —— 而这条恰好是临摹交付的核心指标，
也是唯一能抓住"PDF 那一步悄悄退化"的判据。

试过的错法
----------
直接把 PDF 按 W/pageWidth 渲染成 PNG 再比，MAE 会比真值**大 5 倍**
（实测本图 0.626 -> 2.998）。原因不是 PDF 画错了，而是：

  ① 页面是 519.11 pt，按 W/519.11 缩放会落在非整数像素上 → 整幅 0.5px 相位差，
     所有边缘（描边、网格线、文字）全部错位；
  ② 页面 519.11x289.0 pt 的宽高比与 1662x925 px 差 0.05% → 幅面越大错得越多。

所以这里做三件事：**超采样渲染** -> **LANCZOS 缩到原位图尺寸** ->
**±1px 亚像素对齐搜索**（取残差最小的那个位移）。三个都是纯后处理，不改交付物。

两个 MAE 口径（别混）
--------------------
    MAE     = 通道平均差 —— 与 raster_to_vector_semantic.py 的 --check 自检同一个定义
    MAEmax  = 最大通道差 —— 更严；单通道偏色不会被另外两个通道稀释

用法
----
    python3 pdf_roundtrip.py fig.pdf --src 成品位图.png -o gen/pdf_render.png -c cmp.pdf.png
    python3 pdf_roundtrip.py fig.pdf --src src.png --ss 4      # 超采样倍数（默认 4）
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

try:
    import pymupdf
except ImportError:                                   # 老版本叫 fitz
    import fitz as pymupdf


def main():
    ap = argparse.ArgumentParser(description="PDF 回渲染 vs 原成品位图：超采样 + 亚像素对齐 + 逐像素比")
    ap.add_argument("pdf")
    ap.add_argument("--src", required=True, help="原成品位图（PDF 就是照它临摹的）")
    ap.add_argument("-o", "--out", default="", help="回渲染 PNG 的落盘位置（可选）")
    ap.add_argument("-c", "--cmp", default="", help="上下并排对照图（上=位图 下=PDF）")
    ap.add_argument("--ss", type=int, default=4, help="超采样倍数（默认 4）")
    ap.add_argument("--page", type=int, default=1, help="第几页（默认 1）")
    a = ap.parse_args()

    src = Image.open(a.src).convert("RGB")
    W, H = src.size
    doc = pymupdf.open(a.pdf)
    page = doc[a.page - 1]
    zoom = a.ss * W / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                          colorspace=pymupdf.csRGB, alpha=False)
    buf = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    re_ = buf.resize((W, H), Image.LANCZOS)
    print("PDF 页面 %.2fx%.2f pt -> 超采样 %dx%d -> %s"
          % (page.rect.width, page.rect.height, pix.width, pix.height, re_.size))

    A = np.asarray(src, np.float32)

    def score(im):
        B = np.asarray(im, np.float32)
        mxe = np.abs(A - B).max(2)
        return float(np.abs(A - B).mean()), float(mxe.mean()), mxe, B

    mae, mx, d, _ = score(re_)
    print("  对齐前：        MAE %.3f (MAEmax %.3f) | >8 %.2f%% | >32 %.2f%%"
          % (mae, mx, 100 * (d > 8).mean(), 100 * (d > 32).mean()))
    best = None
    for dy in (-1.0, -0.5, 0.0, 0.5, 1.0):
        for dx in (-1.0, -0.5, 0.0, 0.5, 1.0):
            im = re_ if (dx == 0.0 and dy == 0.0) else re_.transform(
                (W, H), Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                resample=Image.BICUBIC, fillcolor=(255, 255, 255))
            mae, mx, d, B = score(im)
            if best is None or mae < best[0]:
                best = (mae, mx, d, B, dx, dy)
    mae, mx, d, B, dx, dy = best
    mse = ((A - B) ** 2).mean()
    print("  亚像素对齐后：  MAE %.3f (MAEmax %.3f) | >8 %.2f%% | >32 %.2f%% | PSNR %.2f dB"
          "   (dx=%+.1f dy=%+.1f)"
          % (mae, mx, 100 * (d > 8).mean(), 100 * (d > 32).mean(),
             10 * np.log10(255 * 255 / max(mse, 1e-9)), dx, dy))
    nw = A.min(2) < 245
    print("  只算前景(非白 %.1f%%)：MAE %.3f (MAEmax %.3f) | >8 %.2f%%"
          % (100 * nw.mean(), float(np.abs(A - B)[nw].mean()), float(d[nw].mean()),
             100 * (d[nw] > 8).mean()))
    out = Image.fromarray(B.astype(np.uint8))
    if a.out:
        out.save(a.out)
        print("  回渲染 PNG -> %s" % a.out)
    if a.cmp:
        gap = max(8, H // 60)
        c = Image.new("RGB", (W, H * 2 + gap), "white")
        c.paste(src, (0, 0))
        c.paste(out, (0, H + gap))
        c.save(a.cmp)
        print("  对照图(上=位图 下=PDF) -> %s  %dx%d" % (a.cmp, c.size[0], c.size[1]))
    return 0 if mae <= 3.0 else 1


# ★ Windows：stdout 被管道/重定向时是 gbk —— 报告里的中文/✅ 会乱码
#   或被 UnicodeEncodeError 打断（见 scripts/_console.py）。
from _console import init_console

init_console()


if __name__ == "__main__":
    sys.exit(main())