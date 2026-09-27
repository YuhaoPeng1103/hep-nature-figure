#!/usr/bin/env python3
"""
style_profile —— 从目标图提取【风格档案】（数字，不是图片）

为什么是数字不是图：
  1. 版权受限的论文配图不能随仓库分发，但【测量结果】是事实，可以
  2. 对 skill 更有用——它需要知道"目标图的线宽/配色/密度是多少"，
     不需要那张图本身

用法：
    # 从一张目标图提取档案
    python3 style_profile.py extract 目标图.png -o profile.json

    # 从多张同风格的图提取【合并档案】（更稳）
    python3 style_profile.py extract refs/*.png -o profile.json --name hep-t3

    # 查看档案
    python3 style_profile.py show profile.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from style_bench import measure, METRIC_ROBUST

# 除了全局统计，再提取一批【可直接照着做的量】
EXTRA_KEYS = ["stroke_width_est", "palette", "text_area_ratio",
              "saturation_p90", "bg_luminance"]


def stroke_width_est(a):
    """
    线宽估计：用亮度梯度的半高宽近似。
    反映"这张图用多粗的线"——这是最难靠肉眼定的量之一。
    """
    g = a.mean(axis=2)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    strong = mag > np.percentile(mag, 99.0)
    if strong.sum() < 20:
        return 0.0
    # 强边像素的连通宽度中位数（粗估）
    from scipy import ndimage
    lab, n = ndimage.label(strong)
    if n == 0:
        return 0.0
    widths = []
    for i in range(1, min(n, 400) + 1):
        ys, xs = np.nonzero(lab == i)
        if 2 <= len(ys) <= 5000:
            widths.append(2.0 * np.sqrt(len(ys) / np.pi))
    return float(np.median(widths)) if widths else 0.0


def palette(a, k=6, max_px=60000):
    """主色板：k-means 聚类出图中最主要的 k 个颜色（hex）"""
    px = a.reshape(-1, 3)
    if len(px) > max_px:
        idx = np.random.default_rng(0).choice(len(px), max_px, replace=False)
        px = px[idx]
    px = px[px.mean(axis=1) < 0.96]          # 去掉白底
    if len(px) < 50:
        return []
    try:
        from scipy.cluster.vq import kmeans2
        cent, _ = kmeans2(px.astype(float), k, minit="++", seed=0)
        cent = np.clip(cent, 0, 1)
        # 按出现的像素数排序
        d = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        order = np.argsort([-(lab == i).sum() for i in range(k)])
        return ["#%02x%02x%02x" % tuple(int(v * 255) for v in cent[i])
                for i in order]
    except Exception:
        return []


def text_area_ratio(a):
    """文字面积占比：近黑且高对比的小块（文字的特征）"""
    lum = a.mean(axis=2)
    dark = lum < 0.30
    return float(dark.mean())


def extract_one(path):
    m = measure(path)
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = 800 / max(w, h)
    if s < 1:
        im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255.0

    rec = {k: v for k, v in m.items()}
    rec["stroke_width_est"] = round(stroke_width_est(a), 2)
    rec["palette"] = palette(a)
    rec["text_area_ratio"] = round(text_area_ratio(a), 4)
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    lum = a.mean(axis=2)
    rec["saturation_p90"] = round(float(np.percentile(sat[lum < 0.96], 90)), 4)
    rec["bg_luminance"] = round(float(np.percentile(lum, 95)), 4)
    return rec


def extract_many(paths, name="profile"):
    """多张图 → 合并档案（取中位数，比单张稳）"""
    recs = [extract_one(p) for p in paths]
    keys = [k for k in recs[0] if k != "palette"]
    prof = {"name": name, "n_sources": len(recs),
            "sources": [str(p) for p in paths], "style": {}}
    for k in keys:
        vals = [r[k] for r in recs]
        prof["style"][k] = {
            "median": float(np.median(vals)),
            "p25": float(np.percentile(vals, 25)),
            "p75": float(np.percentile(vals, 75)),
        }
    # 色板：所有来源汇总
    allc = [c for r in recs for c in r["palette"]]
    prof["style"]["palette"] = allc[:24]
    return prof


def show(prof):
    s = prof["style"]
    print(f"\n风格档案: {prof['name']}   （来自 {prof['n_sources']} 张图）")
    print("─" * 62)
    for k in ["whitespace", "saturation", "edge_density", "dark_ratio",
              "stroke_width_est", "text_area_ratio", "bg_luminance"]:
        if k not in s:
            continue
        v = s[k]
        tag = "" if METRIC_ROBUST.get(k, True) else "  ⚠不可信"
        print(f"  {k:<20} {v['median']:>9.4f}   "
              f"[{v['p25']:.4f}, {v['p75']:.4f}]{tag}")
    if s.get("palette"):
        print(f"\n  主色板 ({len(s['palette'])} 色):")
        for i in range(0, min(len(s["palette"]), 12), 6):
            print("    " + "  ".join(s["palette"][i:i+6]))


def main():
    ap = argparse.ArgumentParser(description="提取/查看风格档案")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("images", nargs="+")
    e.add_argument("-o", "--out", default="style_profile.json")
    e.add_argument("--name", default="profile")
    s = sub.add_parser("show")
    s.add_argument("profile")
    a = ap.parse_args()

    if a.cmd == "extract":
        prof = extract_many([Path(p) for p in a.images], a.name)
        Path(a.out).write_text(
            json.dumps(prof, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ 档案已写入 {a.out}")
        show(prof)
    else:
        show(json.loads(Path(a.profile).read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
