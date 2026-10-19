#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""svg_spline -- 把「单连通大形体」的元素边界从 1px 台阶换成光滑样条（纯 CPU，vtracer）

为什么要这一步：
    临摹层的几何是「可见像素轮廓」，边缘天然带 1px 台阶；v4.21 的 `_q32` 退路只是把
    台阶变细，台阶还在。vtracer 的 spline 拟合能把同一块形体变成一条闭合 Bézier 曲线，
    实测 UPC 两个核：1 条 path、面积 +1.0%/+0.8%、IoU 0.9893/0.9923。
    它只改**边界**，不动明暗（明暗仍由临摹层的四分块负责）。

用法：
    # 直接命令行
    python tools/svg_spline.py --svg in.svg --png src.png --elmap elmap.npy \
        --el-names S1,N1,N2,... -o out.svg [--min-px 5000] [--grow 2] [--skip S1]

    # 或给 groupvec 的 ids 表（一个元素对应多个整数值时用这个）
    python tools/svg_spline.py --svg in.svg --png src.png --elmap elmap.npy \
        --ids elmap.npy.ids.txt -o out.svg

实现要点（踩过的坑，别改回去）：
  1. vtracer 把图形**居中到原点**，真实位置写在 `<path transform="translate(tx,ty)">` 里。
     只取 `d`、丢掉 transform，路径就会整体错位并把画布涂满 —— 这是第一版最严重的 bug。
  2. 样条相对像素台阶会「鼓出去/缩进来」半像素，所以要在掩膜内外各留一条补色带
     （外 grow px、内 inner px），颜色取**最近的元素自身像素**，画在该组最底层。
  3. 写进 SVG 前先回渲染算 IoU，< --min-iou 就跳过该元素 —— 宁可不光滑，也不写出坏图。

不碰：多连通元素（箭头/弹簧/三轴/文字）、小元素、文字层。
"""
from __future__ import annotations
import argparse, io, os, re, sys, tempfile
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

try:
    import vtracer
except ImportError:
    vtracer = None
try:
    import cairosvg
except ImportError:
    cairosvg = None

TRANS = re.compile(r'transform="translate\(\s*([-\d.eE]+)[,\s]+([-\d.eE]+)\s*\)"')


def hexc(c, bits):
    step = 1 << (8 - bits)
    out = []
    for v in c:
        q = int(round(float(v) / step)) * step
        out.append(min(255, max(0, q)))
    return "#%02x%02x%02x" % tuple(out)


def run_rects(xs, ys, cols):
    out = {}
    for x, y, c in zip(xs.tolist(), ys.tolist(), cols):
        out.setdefault(c, []).append("M%d %dh1v1h-1z" % (x, y))
    return {c: "".join(v) for c, v in out.items()}


def vtracer_paths(mask, pad=4):
    """返回 [(d, tx, ty)]，tx/ty 已是「裁切原点 + vtracer transform」的画布平移"""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    y0, y1 = max(0, int(ys.min()) - pad), min(h, int(ys.max()) + 1 + pad)
    x0, x1 = max(0, int(xs.min()) - pad), min(w, int(xs.max()) + 1 + pad)
    sub = mask[y0:y1, x0:x1]
    fd, tmp_png = tempfile.mkstemp(suffix=".png"); os.close(fd)
    fd, tmp_svg = tempfile.mkstemp(suffix=".svg"); os.close(fd)
    Image.fromarray(np.where(sub, 0, 255).astype(np.uint8)).save(tmp_png)
    try:
        vtracer.convert_image_to_svg_py(tmp_png, tmp_svg, colormode="binary", mode="spline",
                                        filter_speckle=4, corner_threshold=60,
                                        length_threshold=2.0, max_iterations=10,
                                        splice_threshold=45, path_precision=3)
        s = io.open(tmp_svg, encoding="utf-8").read()
    finally:
        for p in (tmp_png, tmp_svg):
            try:
                os.remove(p)
            except OSError:
                pass
    out = []
    for m in re.finditer(r"<path\b([^>]*)/>", s):
        attrs = m.group(1)
        dm = re.search(r'\bd="([^"]+)"', attrs)
        if not dm:
            continue
        tm = TRANS.search(attrs)
        tx = float(tm.group(1)) if tm else 0.0
        ty = float(tm.group(2)) if tm else 0.0
        out.append((dm.group(1), x0 + tx, y0 + ty))
    return out


def clip_iou(paths, mask):
    """把路径回渲染一遍，与掩膜算 IoU（兜底：防止写出坏 clip）"""
    if cairosvg is None:
        return 1.0
    h, w = mask.shape[:2]
    body = "".join('<path transform="translate(%.3f %.3f)" d="%s" fill="#000"/>' % (tx, ty, d)
                   for d, tx, ty in paths)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d"><rect width="%d" height="%d" fill="#fff"/>%s</svg>'
           % (w, h, w, h, w, h, body))
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=w, output_height=h)
    a = np.asarray(Image.open(io.BytesIO(png)).convert("L")) < 128
    uni = (a | mask).sum()
    return float((a & mask).sum() / uni) if uni else 1.0


def read_ids(path):
    """groupvec 的 <elmap>.ids.txt：i<TAB>cell<TAB>element -> {label: element}"""
    out = {}
    for line in io.open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3:
            out[int(parts[0])] = parts[2]
    return out


def run(svg, png, elmap, out, label_to_name, skip=(), min_px=5000, pad=4,
        grow=2, inner=2, quant=6, min_iou=0.95, max_cost=2.0e6, quiet=False):
    """给 svg 里的大形体元素加样条 clipPath + 补色带，写到 out。返回逐元素读数。"""
    if vtracer is None:
        raise RuntimeError("需要 vtracer：python -m pip install vtracer")
    s = io.open(svg, encoding="utf-8").read()
    img = np.asarray(Image.open(png).convert("RGB")).astype(np.int16)
    el = np.load(elmap)
    skip = set(skip)

    groups = {}
    for lab, name in label_to_name.items():
        groups.setdefault(name, []).append(lab)

    defs, rows = [], []
    for eid, labs in groups.items():
        if eid in skip:
            continue
        mask = np.isin(el, labs)
        if mask.sum() < min_px:
            continue
        lab2, _ = ndi.label(mask)
        cnt = np.bincount(lab2.ravel()); cnt[0] = 0
        main_m = (lab2 == int(np.argmax(cnt)))
        if main_m.sum() < 0.9 * mask.sum():
            rows.append(dict(eid=eid, status="multi", px=int(mask.sum()),
                             frac=float(main_m.sum()) / mask.sum()))
            continue
        extra = mask & ~main_m

        paths = vtracer_paths(main_m, pad)
        if not paths:
            rows.append(dict(eid=eid, status="no-path", px=int(mask.sum())))
            continue
        iou = clip_iou(paths, main_m)
        if iou < min_iou:
            rows.append(dict(eid=eid, status="low-iou", px=int(mask.sum()), iou=iou))
            continue

        # ★ 代价闸门：cairosvg 会把 clip 路径写进每一条被裁的 path 里，
        #   体积 ~ 段数 x 该组 path 数。实测 UPC 的板 S1（1002 段 x 8504 path）
        #   PDF 563 MB / 渲染 >12 min，而对回渲染 MAE 的贡献是 0.000（1.287 vs 1.287）。
        pat0 = r'<g\s[^>]*\bdata-element="%s"[^>]*>' % re.escape(eid)
        hit0 = list(re.finditer(pat0, s))
        n_paths = s.count("<path", hit0[0].end(), s.find("</g>", hit0[0].end())) if hit0 else 0
        seg = sum(d.count("C") for d, _tx, _ty in paths)
        cost = float(seg) * max(n_paths, 1)
        if cost > max_cost:
            rows.append(dict(eid=eid, status="too-costly", px=int(mask.sum()),
                             seg=seg, paths=n_paths, cost=cost))
            continue

        frag = ""
        if extra.any():
            ey, ex = np.nonzero(extra)
            frag = "".join("M%d %dh1v1h-1z" % (x, y) for y, x in zip(ey.tolist(), ex.tolist()))

        clip = ['<clipPath id="spl-%s" clipPathUnits="userSpaceOnUse">' % eid]
        for d, tx, ty in paths:
            clip.append('<path transform="translate(%.3f %.3f)" d="%s"/>' % (tx, ty, d))
        if frag:
            clip.append('<path d="%s"/>' % frag)
        clip.append("</clipPath>")
        defs.append("".join(clip))

        band = (ndi.binary_dilation(mask, iterations=grow)
                & ~ndi.binary_erosion(mask, iterations=inner + grow))
        _, (iy, ix) = ndi.distance_transform_edt(~mask, return_indices=True)
        by, bx = np.nonzero(band)
        cols = [hexc(img[iy[y, x], ix[y, x]], quant) for y, x in zip(by.tolist(), bx.tolist())]
        pbody = "".join('<path data-band="1" fill="%s" stroke="%s" stroke-width="1.00" '
                        'stroke-linejoin="round" d="%s"/>' % (c, c, dd)
                        for c, dd in run_rects(bx, by, cols).items())

        pat = r'<g\s[^>]*\bdata-element="%s"[^>]*>' % re.escape(eid)
        hits = list(re.finditer(pat, s))
        if len(hits) != 1:
            rows.append(dict(eid=eid, status=("multi-group" if hits else "no-group"),
                             px=int(mask.sum()), groups=len(hits)))
            continue
        i0, j0 = hits[0].start(), hits[0].end()
        head = hits[0].group(0)
        if "clip-path=" in head:
            rows.append(dict(eid=eid, status="has-clip", px=int(mask.sum())))
            continue
        s = s[:i0] + head[:-1] + ' clip-path="url(#spl-%s)">' % eid + s[j0:]
        i1 = s.find("</title>", i0) + len("</title>")
        s = s[:i1] + pbody + s[i1:]
        rows.append(dict(eid=eid, status="ok", px=int(mask.sum()), iou=iou,
                         frags=int(extra.sum()), band=int(len(cols)),
                         paths=len(paths), spline_paths=len(paths)))

    if defs:
        k = s.find("</desc>") + len("</desc>")
        s = s[:k] + "\n<defs>\n" + "\n".join(defs) + "\n</defs>" + s[k:]
    io.open(out, "w", encoding="utf-8").write(s)
    if not quiet:
        for r in rows:
            if r["status"] == "ok":
                print("  spline %-4s mask=%-6d IoU=%.4f frags=%-5d band-px=%-6d"
                      % (r["eid"], r["px"], r["iou"], r["frags"], r["band"]))
            elif r["status"] == "multi":
                print("  skip   %-4s 多连通（最大块只占 %.1f%%）" % (r["eid"], 100 * r["frac"]))
            elif r["status"] == "too-costly":
                print("  skip   %-4s 代价过高（%d 段 x %d path = %.1e > %.1e）"
                      % (r["eid"], r["seg"], r["paths"], r["cost"], max_cost))
            elif r["status"] == "low-iou":
                print("  skip   %-4s spline IoU=%.4f < %.2f" % (r["eid"], r["iou"], min_iou))
            else:
                print("  skip   %-4s %s" % (r["eid"], r["status"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--elmap", required=True)
    ap.add_argument("--el-names", default="", help="逗号分隔，按 npy 里的整数值 0,1,2...")
    ap.add_argument("--ids", default="", help="groupvec 的 <elmap>.ids.txt（一个元素多个 label 时用）")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--min-px", type=int, default=5000)
    ap.add_argument("--pad", type=int, default=4)
    ap.add_argument("--grow", type=int, default=2, help="补色带向外扩多少像素")
    ap.add_argument("--inner", type=int, default=2, help="补色带向内扩多少像素")
    ap.add_argument("--quant", type=int, default=6, help="补色带颜色量化位数（bit/通道）")
    ap.add_argument("--min-iou", type=float, default=0.95)
    ap.add_argument("--max-cost", type=float, default=2.0e6,
                    help="段数 x 该组 path 数 的上限；超了就不做（PDF 会按这个量级膨胀）")
    ap.add_argument("--skip", default="")
    a = ap.parse_args()

    if a.ids:
        mapping = read_ids(a.ids)
    elif a.el_names:
        mapping = {i: n for i, n in enumerate(x for x in a.el_names.split(",") if x)}
    else:
        ap.error("给 --el-names 或 --ids 至少一个")

    rows = run(a.svg, a.png, a.elmap, a.out, mapping,
               skip=[x for x in a.skip.split(",") if x],
               min_px=a.min_px, pad=a.pad, grow=a.grow, inner=a.inner,
               quant=a.quant, min_iou=a.min_iou, max_cost=a.max_cost)
    print("-> %s（%d 个元素加样条）" % (a.out, sum(1 for r in rows if r["status"] == "ok")))


if __name__ == "__main__":
    main()
