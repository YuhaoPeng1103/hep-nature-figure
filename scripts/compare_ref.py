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
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def build(ref, mine, out, height=900, gap=30, labels=("参考", "复现")):
    a = Image.open(ref).convert("RGB")
    b = Image.open(mine).convert("RGB")
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


def main():
    ap = argparse.ArgumentParser(description="参考图与复现图并排对比")
    ap.add_argument("ref")
    ap.add_argument("mine")
    ap.add_argument("-o", "--out", default="compare.png")
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()
    size = build(args.ref, args.mine, args.out, args.height)
    print(f"对比图 {size[0]}x{size[1]} -> {args.out}")


if __name__ == "__main__":
    main()
