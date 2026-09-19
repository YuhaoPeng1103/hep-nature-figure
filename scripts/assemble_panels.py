#!/usr/bin/env python3
"""
assemble_panels —— 把多个矢量面板拼成一张期刊级复合图

解决什么问题：
  真实期刊图经常是「示意 + 定量」混排：panel a 用 SVG 画示意图，
  panel b 用 matplotlib 画数据图。svc+png 拼接会丢矢量，
  这个工具用 PyMuPDF 的 show_pdf_page 把各面板作为 PDF 矢量对象嵌入，
  保矢量、保文字可选。

用法：
    # 显式布局（单位 mm，原点在左上）
    python3 assemble_panels.py -o fig1.pdf --page 180x120 \\
        --panel a.pdf:0,0,80,120 --panel b.pdf:85,10,175,110

    # 网格布局（自动等分）
    python3 assemble_panels.py -o fig1.pdf --page 180x90 \\
        --grid 1x2 --panel a.pdf --panel b.pdf

    # 加面板标号
    python3 assemble_panels.py ... --label-a a --label-b b

输出：单页矢量 PDF（可再导出 TIFF/EPS 投稿）
"""
import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF

MM = 72.0 / 25.4          # mm -> pt


def parse_size(s):
    """'180x120mm' / '7.1x4.7in' / '510x340pt' -> (w_pt, h_pt)"""
    s = s.strip().lower()
    for unit, k in (("mm", MM), ("cm", 10 * MM), ("in", 72.0), ("pt", 1.0)):
        if s.endswith(unit):
            body = s[: -len(unit)]
            break
    else:
        body, k = s, MM          # 默认 mm
    w, h = body.replace(" ", "").split("x")
    return float(w) * k, float(h) * k


def parse_panel(spec):
    """'path.pdf:x0,y0,x1,y1' (mm) 或 'path.pdf'"""
    if ":" in spec and spec.rsplit(":", 1)[1].count(",") == 3:
        path, box = spec.rsplit(":", 1)
        vals = [float(v) * MM for v in box.split(",")]
        return path, tuple(vals)
    return spec, None


def grid_rects(n, page_w, page_h, margin=0.06, gutter=0.05,
               ratios=None, flow="row"):
    """把页面切成 n 个矩形。margin/gutter 是页面尺寸的比例。"""
    mx, my = page_w * margin, page_h * margin
    usable_w, usable_h = page_w - 2 * mx, page_h - 2 * my
    ratios = ratios or [1.0] * n
    tot = sum(ratios)
    rects = []
    if flow == "row":
        g = gutter * page_w
        avail = usable_w - g * (n - 1)
        x = mx
        for r in ratios:
            w = avail * r / tot
            rects.append((x, my, x + w, my + usable_h))
            x += w + g
    else:  # column
        g = gutter * page_h
        avail = usable_h - g * (n - 1)
        y = my
        for r in ratios:
            h = avail * r / tot
            rects.append((mx, y, mx + usable_w, y + h))
            y += h + g
    return rects


def fit_into(rect, src_w, src_h):
    """把源页面按比例居中放进目标矩形。"""
    x0, y0, x1, y1 = rect
    bw, bh = x1 - x0, y1 - y0
    scale = min(bw / src_w, bh / src_h)
    w, h = src_w * scale, src_h * scale
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return fitz.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def assemble(out_path, page, panels, labels=None, label_size=11,
             label_dy=-4.0):
    """
    panels: [(pdf_path, rect_or_None), ...]
    labels: ['a','b',...] 或 None
    """
    doc = fitz.open()
    page_w, page_h = page
    out = doc.new_page(width=page_w, height=page_h)

    for i, (p, rect) in enumerate(panels):
        src_path = Path(p)
        if not src_path.exists():
            sys.exit(f"找不到面板文件：{src_path}")
        src = fitz.open(src_path)
        if src.page_count == 0:
            sys.exit(f"面板为空：{src_path}")
        sp = src[0]
        target = fitz.Rect(*rect) if rect else fitz.Rect(
            page_w * 0.06, page_h * 0.06, page_w * 0.94, page_h * 0.94)
        # show_pdf_page 把源页作为矢量 XObject 嵌入 —— 保矢量、保文字
        out.show_pdf_page(target, src, 0)
        if labels and i < len(labels) and labels[i]:
            out.insert_text(
                fitz.Point(target.x0, target.y0 + label_dy),
                labels[i], fontsize=label_size, fontname="hebo")
        src.close()

    out_path = Path(out_path)
    doc.save(out_path, deflate=True, garbage=4)
    doc.close()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="把矢量面板拼成复合图")
    ap.add_argument("-o", "--out", default="composite.pdf")
    ap.add_argument("--page", default="180x120mm", help="页面尺寸，如 180x120mm")
    ap.add_argument("--panel", action="append", default=[],
                    help="面板：path.pdf 或 path.pdf:x0,y0,x1,y1（mm，可重复）")
    ap.add_argument("--grid", default=None, help="网格自动布局，如 1x2 或 2x1")
    ap.add_argument("--ratios", default=None, help="各面板宽度比，如 1,1.4")
    ap.add_argument("--labels", default=None, help="面板标号，如 a,b,c")
    ap.add_argument("--margin", type=float, default=0.05)
    ap.add_argument("--gutter", type=float, default=0.05)
    args = ap.parse_args()

    page = parse_size(args.page)
    panels = [parse_panel(s) for s in args.panel]
    if not panels:
        sys.exit("至少给一个 --panel")

    ratios = [float(x) for x in args.ratios.split(",")] if args.ratios else None
    labels = args.labels.split(",") if args.labels else None

    if args.grid:
        rows, cols = (int(x) for x in args.grid.lower().split("x"))
        n = rows * cols
        if len(panels) != n:
            sys.exit(f"--grid {args.grid} 需要 {n} 个面板，给了 {len(panels)} 个")
        flow = "row" if rows == 1 else "column"
        rects = grid_rects(n, *page, margin=args.margin,
                           gutter=args.gutter, ratios=ratios, flow=flow)
    else:
        rects = [r for _, r in panels]
        if any(r is None for r in rects):
            sys.exit("未指定 --grid 时，每个 --panel 都要给坐标")

    out = assemble(args.out, page, [(p, r) for (p, _), r in zip(panels, rects)],
                   labels=labels)
    info = fitz.open(out)
    pg = info[0]
    nvec = len(pg.get_drawings())
    print(f"拼版完成 -> {out}  ({pg.rect.width/MM:.0f}×{pg.rect.height/MM:.0f} mm)")
    print(f"  矢量绘制指令 {nvec} 条，字体 {len(pg.get_fonts())} 种 —— 确认是矢量输出")
    info.close()


if __name__ == "__main__":
    main()
