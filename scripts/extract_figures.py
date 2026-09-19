#!/usr/bin/env python3
"""
从论文 PDF 中自动提取插图（Figure/Table）。

原理：图通常由「矢量路径 + 嵌入位图」构成，正文是文字。
      所以取一页里所有 drawing 和 image 的包围盒，做邻近聚类，
      面积够大的簇就是一张图。再按簇的包围盒裁切、按高 DPI 渲染。

用法：
    python3 extract_figures.py paper.pdf                    # 输出到 ./refs_extracted/<pdf名>/
    python3 extract_figures.py paper.pdf -o /tmp/out        # 指定输出目录
    python3 extract_figures.py paper.pdf --dpi 600          # 提高分辨率
    python3 extract_figures.py paper.pdf --min-area 0.03    # 提高面积阈值（滤掉小图）
    python3 extract_figures.py paper.pdf --pages 3-7        # 只处理指定页
    python3 extract_figures.py paper.pdf --overview-only    # 只出整页预览，不切图

输出：
    <outdir>/overview/page-XX.png      整页预览（200 DPI），用来人工浏览
    <outdir>/figs/fig-pXX-N.png        切出来的图（默认 400 DPI）
    <outdir>/manifest.json             每张图的页码、包围盒、尺寸
"""
import argparse
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF


def cluster_rects(rects, gap=14.0, max_iters=60):
    """把邻近/重叠的矩形合并成簇。gap 单位是 PDF point（1pt = 1/72 inch）。"""
    boxes = [fitz.Rect(r) for r in rects]
    for _ in range(max_iters):
        merged = []
        used = [False] * len(boxes)
        changed = False
        for i, a in enumerate(boxes):
            if used[i]:
                continue
            cur = fitz.Rect(a)
            for j in range(i + 1, len(boxes)):
                if used[j]:
                    continue
                b = boxes[j]
                # 把 b 外扩 gap 后若与 cur 相交则合并
                probe = fitz.Rect(b.x0 - gap, b.y0 - gap, b.x1 + gap, b.y1 + gap)
                if cur.intersects(probe):
                    cur |= b
                    used[j] = True
                    changed = True
            used[i] = True
            merged.append(cur)
        boxes = merged
        if not changed:
            break
    return boxes


def parse_pages(spec, n):
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < n]


def extract(pdf_path, outdir, dpi=400, overview_dpi=200, min_area_frac=0.02,
            pages=None, overview_only=False, margin=6.0):
    pdf_path = Path(pdf_path)
    outdir = Path(outdir)
    figs_dir = outdir / "figs"
    ov_dir = outdir / "overview"
    figs_dir.mkdir(parents=True, exist_ok=True)
    ov_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    sel = parse_pages(pages, doc.page_count)
    manifest = []

    for pno in sel:
        page = doc[pno]
        pr = page.rect
        page_area = pr.width * pr.height

        # 整页预览
        page.get_pixmap(dpi=overview_dpi).save(
            ov_dir / f"page-{pno + 1:02d}.png")

        if overview_only:
            continue

        # 收集图形元素包围盒
        rects = []
        for d in page.get_drawings():
            r = d["rect"]
            # 滤掉细线（坐标轴刻度、分隔线等单独看很小）
            if r.width > 3 and r.height > 3:
                rects.append(r)
        for info in page.get_image_info():
            rects.append(fitz.Rect(info["bbox"]))
        for b in page.get_text("blocks"):
            # 图片块也常被标成 block type 1
            if b[6] == 1:
                rects.append(fitz.Rect(b[:4]))

        if not rects:
            continue

        clusters = cluster_rects(rects)
        kept = []
        for c in clusters:
            c = fitz.Rect(c) & pr
            if c.is_empty or c.width < 50 or c.height < 50:
                continue
            frac = (c.width * c.height) / page_area
            if frac < min_area_frac:
                continue
            if frac > 0.96:
                continue  # 几乎整页，多半是正文块误判
            kept.append(c)

        # 大簇优先，去掉被更大簇基本包含的小簇（避免重复切）
        kept.sort(key=lambda r: r.get_area(), reverse=True)
        final = []
        for c in kept:
            if any((c & big).get_area() > 0.75 * c.get_area() for big in final):
                continue
            final.append(c)
        final.sort(key=lambda r: (round(r.y0), r.x0))

        for i, c in enumerate(final, 1):
            clip = fitz.Rect(c.x0 - margin, c.y0 - margin,
                             c.x1 + margin, c.y1 + margin) & pr
            pix = page.get_pixmap(dpi=dpi, clip=clip)
            name = f"fig-p{pno + 1:02d}-{i}.png"
            pix.save(figs_dir / name)
            manifest.append({
                "file": f"figs/{name}",
                "page": pno + 1,
                "bbox_pt": [round(v, 1) for v in clip],
                "size_px": [pix.width, pix.height],
                "dpi": dpi,
            })

    (outdir / "manifest.json").write_text(
        json.dumps({
            "source_pdf": str(pdf_path),
            "page_count": doc.page_count,
            "pages_processed": [p + 1 for p in sel],
            "n_figures": len(manifest),
            "figures": manifest,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    doc.close()
    print(f"{pdf_path.name}: 处理 {len(sel)} 页，切出 {len(manifest)} 块 -> {outdir}")
    return manifest


def main():
    ap = argparse.ArgumentParser(description="从论文 PDF 中提取插图")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--outdir", default=None)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--overview-dpi", type=int, default=200)
    ap.add_argument("--min-area", type=float, default=0.02,
                    help="图占整页面积的最小比例（默认 0.02）")
    ap.add_argument("--pages", default=None, help="如 3-7 或 1,4,9")
    ap.add_argument("--overview-only", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        sys.exit(f"找不到文件：{pdf}")
    outdir = Path(args.outdir) if args.outdir else Path("refs_extracted") / pdf.stem

    extract(pdf, outdir, dpi=args.dpi, overview_dpi=args.overview_dpi,
            min_area_frac=args.min_area, pages=args.pages,
            overview_only=args.overview_only)


if __name__ == "__main__":
    main()
