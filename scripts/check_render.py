#!/usr/bin/env python3
"""
check_render —— SVG 渲染静默失败检测器

为什么需要它：
  cookbook 里那六个坑的共同特征是「不报错，只画错」——
  中文丢了不报错、渐变变黑不报错、tspan 串位不报错。
  人工检查会漏，所以必须自动化。

检查项：
  1. 非空白     —— 图不是纯白/纯色（防渲染完全失败）
  2. 渐变生效   —— 不存在大面积纯黑区域（防用了 PyMuPDF 这类不支持渐变的渲染器）
  3. 色彩丰富度 —— 颜色数达到阈值（防渐变被压成色块）
  4. 元素命中   —— 给定「元素清单」的采样点，逐点验证该处确实有墨
                   （这是最关键的一项：防中文字体缺失导致局部空白）

用法：
    python3 check_render.py fig.png
    python3 check_render.py fig.png --probe 200,196 --probe 76,196   # 元素采样点
    python3 check_render.py fig.png --json
"""
import argparse
import json
import sys
from collections import Counter

from PIL import Image


def load(path):
    im = Image.open(path).convert("RGB")
    return im


def check_blank(im, min_ink=0.002):
    """非空白：非白像素占比。"""
    px = im.getdata()
    n = len(px)
    ink = sum(1 for p in px if sum(p) < 720)   # 非近白
    frac = ink / n
    return {
        "name": "非空白",
        "pass": frac >= min_ink,
        "detail": f"非白像素占比 {frac:.4%}（阈值 {min_ink:.2%}）",
    }


def check_no_black_blob(im, thresh=0.02):
    """
    渐变生效：纯黑像素占比不能过高。
    渐变渲染失败时整块填充会变成纯黑，占比会飙升。
    """
    px = im.getdata()
    n = len(px)
    black = sum(1 for p in px if sum(p) < 30)
    frac = black / n
    return {
        "name": "无黑块（渐变生效）",
        "pass": frac <= thresh,
        "detail": f"纯黑像素占比 {frac:.4%}（阈值 ≤{thresh:.2%}）。"
                  f"超标通常是用了不支持的 SVG 渲染器",
    }


def check_color_richness(im, min_colors=200):
    """色彩丰富度：渐变会产出大量中间色；色块化则颜色数很少。"""
    small = im.copy()
    small.thumbnail((400, 400))
    n = len(set(small.getdata()))
    return {
        "name": "色彩丰富度",
        "pass": n >= min_colors,
        "detail": f"不同颜色数 {n}（阈值 {min_colors}）。过少说明渐变丢了",
    }


def check_probes(im, probes, ink_thresh=700, win=6):
    """
    元素命中：在指定坐标附近窗口内检测是否有墨。
    用来验证「此处应该有个元素」——防字体丢失、绘制顺序错误导致的局部空白。

    坐标支持两种写法：
      0.5,0.1    归一化（推荐）—— 与渲染尺寸无关，改 output_width 不用改采样点
      460,192    绝对像素
    """
    out = []
    W, H = im.size
    px = im.load()
    norm = [(x, y) for (x, y) in probes if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0]
    for (x, y) in probes:
        if (x, y) in norm:
            x, y = int(x * W), int(y * H)
        if not (0 <= x < W and 0 <= y < H):
            out.append({"probe": [x, y], "pass": False, "ink": None,
                        "note": "坐标超出画布"})
            continue
        best = 0
        for dx in range(-win, win + 1):
            for dy in range(-win, win + 1):
                xx, yy = x + dx, y + dy
                if 0 <= xx < W and 0 <= yy < H:
                    s = sum(px[xx, yy])
                    if s < ink_thresh:
                        best = max(best, 765 - s)
        out.append({"probe": [x, y], "pass": best > 0, "ink": best})
    return out


def main():
    ap = argparse.ArgumentParser(description="SVG 渲染静默失败检测")
    ap.add_argument("image")
    ap.add_argument("--probe", action="append", default=[],
                    help="元素采样点，格式 x,y（可重复）。坐标按图片实际像素")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    im = load(args.image)
    checks = [check_blank(im), check_no_black_blob(im),
              check_color_richness(im)]

    probes = []
    for p in args.probe:
        x, y = p.split(",")
        probes.append((float(x), float(y)))
    probe_results = check_probes(im, probes) if probes else []
    if probes:
        npass = sum(1 for r in probe_results if r["pass"])
        checks.append({
            "name": "元素命中",
            "pass": npass == len(probes),
            "detail": f"{npass}/{len(probes)} 个采样点检测到墨",
        })

    failed = [c for c in checks if not c["pass"]]
    if args.json:
        print(json.dumps({"image": args.image, "checks": checks,
                          "probes": probe_results,
                          "pass": not failed}, indent=2, ensure_ascii=False))
    else:
        print(f"检查 {args.image}  ({im.size[0]}x{im.size[1]})")
        for c in checks:
            print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c['detail']}")
        for r in probe_results:
            if not r["pass"]:
                print(f"    ✗ 采样点 {r['probe']} 附近无墨 — 该处元素可能丢失")
        print("结论:", "全部通过" if not failed else f"{len(failed)} 项未通过")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
