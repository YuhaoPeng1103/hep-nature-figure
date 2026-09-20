#!/usr/bin/env python3
"""
raster_to_vector —— 位图 → 分层矢量（"GPT 出图 → skill 精修"这条路的第一半）
=========================================================================
## 这条路解决什么

模型用图像生成出的图**好看但不可编辑**（位图、文字不可选、不能改字号）。
本脚本把它转成**可分层的矢量**，交出"可编辑"。

## ★ 本质权衡（必须先说清，否则会失望）

**描摹是"压平成色块"** —— 它会把渐变、柔和光影、抗锯齿过渡
统统变成一级一级的台阶。**而那些恰恰是让图好看的东西。**

所以这条路换来的是「可编辑」，代价是「变平」。
色阶数（`--levels`）就是这个权衡的旋钮：
  少 → 干净、路径少、但更平
  多 → 更接近原图、但路径爆炸、文件巨大

## 它做不了、必须人/模型补的三件事

脚本会在报告里逐条列出：
  1. **文字被转成了路径** —— 描摹不认识字。需要人/模型照原图重写成 `<text>`
     （不做这一步的话，`check_delivery.py` 会判"文字不可提取"= 不合规）
  2. **图层是"按颜色"分的，不是按语义** —— 需要重新归组成
     「介质/核/喷注/标注」这类有含义的图层
  3. **渐变退化成了色阶** —— 需要把连续几级合并回一个 `linearGradient`

## 用法

    python3 raster_to_vector.py gpt_output.png -o refined.svg --levels 12
    python3 raster_to_vector.py gpt_output.png -o refined.svg --levels 24 --tol 1.2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ══════════════════════════════════════════════════════════════
def get_tracer():
    """
    轮廓提取后端。优先 cv2（成熟快），退到 skimage。
    两个都没有就明确报错——**不假装能做**。
    """
    try:
        import cv2
        return "cv2", cv2
    except ImportError:
        pass
    try:
        from skimage import measure  # noqa: F401
        return "skimage", measure
    except ImportError:
        raise SystemExit(
            "描摹需要轮廓提取后端，但 cv2 和 skimage 都没有。\n"
            "  装任一个：pip install opencv-python-headless  或  pip install scikit-image\n"
            "  注意：ChatGPT 沙箱里这两个可能都没有 —— 那条环境请改用\n"
            "  「模型直接写 SVG」的路线，不要走描摹。")


def quantize(img: Image.Image, levels: int):
    """
    颜色量化 → (调色板, 索引图)。用 PIL 自带的中位切分，无第三方依赖。
    """
    q = img.convert("RGB").quantize(colors=levels, method=Image.MEDIANCUT,
                                    dither=Image.Dither.NONE)
    pal = q.getpalette()[: levels * 3]
    colors = [tuple(pal[i * 3:i * 3 + 3]) for i in range(levels)]
    return colors, np.asarray(q, dtype=np.int32)


def trace_mask(mask, backend, mod, tol):
    """二值 mask → 多边形列表（每个是 [(x,y), ...]）。坐标已按 tol 简化。"""
    polys = []
    m = (mask.astype(np.uint8)) * 255
    if backend == "cv2":
        cnts, _ = mod.findContours(m, mod.RETR_CCOMP, mod.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if len(c) < 3:
                continue
            ap = mod.approxPolyDP(c, tol, True).reshape(-1, 2)
            if len(ap) >= 3:
                polys.append(ap.tolist())
    else:
        for c in mod.find_contours(mask.astype(float), 0.5):
            if len(c) < 3:
                continue
            ap = mod.approximate_polygon(c, tolerance=tol)
            if len(ap) >= 3:
                polys.append([(float(x), float(y)) for y, x in ap])
    return polys


def poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def main():
    ap = argparse.ArgumentParser(description="位图 → 分层矢量")
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="refined.svg")
    ap.add_argument("--levels", type=int, default=12,
                    help="色阶数。**这是「好看 vs 可编辑」的主旋钮**："
                         "少=干净但更平，多=接近原图但路径爆炸（默认 12）")
    ap.add_argument("--tol", type=float, default=1.0,
                    help="路径简化容差（px）。越大越简洁（默认 1.0）")
    ap.add_argument("--min-area", type=float, default=12.0,
                    help="丢掉小于此面积的多边形（px²），防噪点路径（默认 12）")
    ap.add_argument("--bg-tolerance", type=float, default=8.0,
                    help="与最外层颜色相差小于此值的色阶并进背景（默认 8）")
    a = ap.parse_args()

    src = Path(a.image)
    if not src.exists():
        raise SystemExit(f"找不到 {src}")
    img = Image.open(src).convert("RGB")
    W, H = img.size

    backend, mod = get_tracer()
    colors, idx = quantize(img, a.levels)

    # 统计每色占比
    counts = np.bincount(idx.ravel(), minlength=len(colors))
    order = np.argsort(-counts)                      # 从多到少画 = 背景在底

    print(f"源图 {W}×{H}  |  描摹后端 {backend}  |  色阶 {a.levels}")
    print(f"色调板：{len(colors)} 色，最大占比 "
          f"{counts[order[0]] / idx.size * 100:.1f}%")

    body = []
    total_paths = 0
    dropped = 0
    for rank, ci in enumerate(order):
        if counts[ci] == 0:
            continue
        r, g, b = colors[ci]
        mask = (idx == ci)
        polys = trace_mask(mask, backend, mod, a.tol)
        keep = []
        for p in polys:
            if poly_area(p) >= a.min_area:
                keep.append(p)
            else:
                dropped += 1
        if not keep:
            continue
        total_paths += len(keep)
        label = f"{rank:02d} {('#%02x%02x%02x' % (r, g, b))}"
        body.append(f'<g inkscape:label="{label}">')
        d_all = []
        for p in keep:
            d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in p) + " Z"
            d_all.append(d)
        body.append(f'<path d="{" ".join(d_all)}" fill="#{r:02x}{g:02x}{b:02x}" '
                    f'fill-rule="evenodd"/>')
        body.append('</g>')

    svg = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        *body,
        '</svg>'])
    Path(a.out).write_text(svg, encoding="utf-8")

    size_kb = Path(a.out).stat().st_size / 1024
    print(f"\n已输出 {a.out}  —  {total_paths} 条路径 / {len(body)//3} 个颜色图层"
          f" / {size_kb:.0f} KB")
    if dropped:
        print(f"（丢弃 {dropped} 个小多边形，< {a.min_area}px²）")

    # ══ 报告：脚本做不到、必须补的三件事 ══
    print("""
────────────────────────────────────────────────────────────────
⚠️  描摹只完成了一半。以下三件必须人/模型补，否则过不了门禁：

1. **文字被转成了路径** —— 描摹不认识字。
   → 照原图把标题/标签重写成真正的 <text>，否则
     check_delivery.py 会判「文字不可提取」= 不合规（Nature 要求可编辑文字）。

2. **图层是按【颜色】分的，不是按语义**。
   → 重新归组成「介质 / 入射核 / 喷注 / 标注」这类有含义的图层，
     否则人精修时找不到东西。

3. **渐变退化成了色阶**（这正是"变平"的来源）。
   → 把连续几级同色系合并回一个 <linearGradient> / <radialGradient>。
     色阶数调高能减轻，但路径数会涨。

补完跑：
    python3 audit_composition.py refined.pdf
    python3 check_delivery.py refined.pdf
    python3 repair_brief.py refined.svg --profile style-profiles.json
────────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
