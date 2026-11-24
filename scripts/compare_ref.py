#!/usr/bin/env python3
"""
compare_ref —— 生成「参考图 | 复现图」并排对比图

为什么需要：
  复现的迭代循环是「渲染 → 并排对比 → 调参数 → 再渲染」，
  光看自己的输出判断不了像不像，必须和参考图放在一起看。
  这个循环跑 3~5 轮是常态，所以对比图要一键生成。

用法：
    python3 compare_ref.py 参考图.png 复现图.png -o 对比.png
    python3 compare_ref.py 参考图.png 复现图.png -o 对比.png --height 900
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def on_white(path):
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", image.size, "white")
        return Image.alpha_composite(white, rgba).convert("RGB")


def build(ref, mine, out, height=900, gap=30, labels=("参考", "复现")):
    a = on_white(ref)
    b = on_white(mine)
    a.thumbnail((2000, height))
    b.thumbnail((2000, height))
    W = a.width + b.width + gap
    H = max(a.height, b.height) + 26
    s = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(s)
    d.text((4, 6), labels[0], fill="#888")
    d.text((a.width + gap + 4, 6), labels[1], fill="#888")
    s.paste(a, (0, 26))
    s.paste(b, (a.width + gap, 26))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    s.save(out)
    return s.size


def measure(ref, mine, regions=()):
    """Measure aligned RGB exports in original pixel coordinates."""
    import numpy as np

    a = np.asarray(on_white(ref), dtype=np.float32)
    b = np.asarray(on_white(mine), dtype=np.float32)
    if a.shape != b.shape:
        raise ValueError("metrics require aligned images with identical pixel dimensions")
    height, width = a.shape[:2]
    difference = np.abs(a - b)
    foreground = np.minimum(a.min(axis=2), b.min(axis=2)) < 235

    def summarize(delta, ink):
        pixels = int(ink.sum())
        mse = float(np.mean(delta ** 2))
        return {
            "rgb_mae": float(delta.mean()),
            "psnr_db": float(10 * np.log10(255 ** 2 / mse)) if mse else None,
            "foreground_pixels": pixels,
            "foreground_rgb_mae": float(delta[ink].mean()) if pixels else None,
        }

    panels = {}
    for name, x0, y0, x1, y1 in regions:
        if name in panels:
            raise ValueError(f"duplicate region: {name}")
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError(f"region outside image or empty: {name}")
        crop = np.s_[y0:y1, x0:x1]
        panels[name] = {"box": [x0, y0, x1, y1], **summarize(difference[crop], foreground[crop])}
    return {
        "size": [width, height],
        "foreground_cutoff": 235,
        "canvas": summarize(difference, foreground),
        "regions": panels,
    }


def main():
    ap = argparse.ArgumentParser(description="参考图与复现图并排对比")
    ap.add_argument("ref")
    ap.add_argument("mine")
    ap.add_argument("-o", "--out", default="compare.png")
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--metrics", type=Path, help="write original-size pixel diagnostics as JSON")
    ap.add_argument("--region", nargs=5, action="append", default=[],
                    metavar=("NAME", "X0", "Y0", "X1", "Y1"))
    args = ap.parse_args()
    if args.region and not args.metrics:
        ap.error("--region requires --metrics")
    if args.metrics:
        if args.metrics.resolve() in {Path(path).resolve() for path in (args.ref, args.mine, args.out)}:
            ap.error("--metrics must be a separate output file")
        try:
            regions = [(name, *map(int, coords)) for name, *coords in args.region]
            report = measure(args.ref, args.mine, regions)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    size = build(args.ref, args.mine, args.out, args.height)
    print(f"对比图 {size[0]}x{size[1]} -> {args.out}")


# ★ Windows：stdout 被管道/重定向时是 gbk —— 报告里的中文/✅ 会乱码
#   或被 UnicodeEncodeError 打断（见 scripts/_console.py）。
from _console import init_console

init_console()


if __name__ == "__main__":
    main()
