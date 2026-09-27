# -*- coding: utf-8 -*-
"""eval_svg.py -- 对一组 SVG 用 sweep.py 同一套指标打分（MAE / 贴边比 / path 数 / 体积）

用法: python eval_svg.py --src gen/render_s31_clean.png <a.svg> <b.svg> ...
"""
import argparse, io, os, re
import numpy as np
from PIL import Image
from scipy import ndimage
import cairosvg

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("svgs", nargs="+")
a = ap.parse_args()
src_img = Image.open(a.src).convert("RGB")
W, H = src_img.size
src = np.asarray(src_img, float)
LUM = np.array([0.299, 0.587, 0.114])
Ls = src @ LUM
med = ndimage.median_filter(Ls, size=21)
flat = (med < 232) & (np.abs(med - Ls) < 10)
fx = flat[:, :-1] & flat[:, 1:]
fy = flat[:-1, :] & flat[1:, :]
ex0 = np.abs(np.diff(Ls, axis=1))[fx].mean()
ey0 = np.abs(np.diff(Ls, axis=0))[fy].mean()
print("%-26s %7s %8s %7s %7s %8s %7s %7s %7s %7s" %
      ("file", "MAE", "MAEmax", ">8%", ">32%", "PSNR", "贴边x", "贴边y", "path", "MB"))
for f in a.svgs:
    txt = io.open(f, encoding="utf-8").read()
    npath = txt.count("<path")
    png = cairosvg.svg2png(url=os.path.abspath(f), output_width=W, output_height=H)
    re_ = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), float)
    d = np.abs(src - re_).max(2)
    Lr = re_ @ LUM
    rx = np.abs(np.diff(Lr, axis=1))[fx].mean() / ex0
    ry = np.abs(np.diff(Lr, axis=0))[fy].mean() / ey0
    mse = ((src - re_) ** 2).mean()
    print("%-26s %7.3f %8.3f %6.2f%% %6.2f%% %7.2fdB %7.2f %7.2f %7d %7.2f" %
          (os.path.basename(f), np.abs(src - re_).mean(), d.mean(), (d > 8).mean() * 100,
           (d > 32).mean() * 100, 10 * np.log10(255 * 255 / max(1e-9, mse)), rx, ry,
           npath, os.path.getsize(f) / 1e6))