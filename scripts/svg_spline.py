#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""svg_spline -- 把「单连通大形体」的元素边界从 1px 台阶换成光滑曲线（纯 CPU）

两种方法（默认 subpixel）：
  subpixel（v4.23，默认）—— 掩膜先高斯模糊成软场，取 **0.5 等值线**（亚像素，落在
      抗锯齿过渡带的中点），再拟合成闭合三次 Bézier。
      为什么更好：vtracer 是对**二值**掩膜拟合，边界落在台阶的外沿，面积系统性偏大约 1%；
      等值线落在真实的 50% 边缘上，所以既更准（band MAE 15.5 vs 18.1）又更光滑。
  vtracer（v4.22）—— 掩膜直接交给 vtracer(binary/spline)。
      ★ 它的输出把图形居中到原点，真实位置在 <path transform="translate(tx,ty)"> 里；
        只取 d、丢掉 transform，路径会整体错位并把画布涂满。

两种方法都只改**边界**，不动明暗（明暗仍由临摹层的四分块负责）。

用法：
    python tools/svg_spline.py --svg in.svg --png src.png --elmap elmap.npy \
        --el-names S1,N1,N2 -o out.svg [--method subpixel|vtracer] [--step 8]

写盘前的四道闸门（不过就跳过该元素，绝不写出坏图）：
    ① 掩膜最大连通块 >= 90%（多连通不做）
    ② 回渲染 IoU >= --min-iou（默认 0.95）
    ③ 代价 = 段数 x 该组 path 数 <= --max-cost（默认 2e6）
       —— cairosvg 会把 clip 路径摊进每一条被裁的 path，超了 PDF 会爆
    ④ 图层组必须唯一（多面板同名元素明确跳过，不猜）
"""
from __future__ import annotations
import argparse, io, os, re, sys, tempfile
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

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


# ---------------------------------------------------------------- 方法二：等值线
def subpixel_path(mask, sigma=1.4, nseg=0, step=8.0, smin=64, smax=512):
    """掩膜 -> 0.5 等值线（亚像素）-> 闭合三次 Bézier。返回 (d, 段数)"""
    from scipy.interpolate import splprep, splev
    from skimage import measure

    f = ndi.gaussian_filter(mask.astype(np.float32), sigma)
    cs = [c for c in measure.find_contours(f, 0.5) if len(c) > 32]
    if not cs:
        return "", 0
    c = max(cs, key=len)                       # (row, col)
    y, x = c[:, 0].astype(np.float64), c[:, 1].astype(np.float64)
    if np.allclose([x[0], y[0]], [x[-1], y[-1]]):
        x, y = x[:-1], y[:-1]
    per = float(np.hypot(np.diff(np.r_[x, x[0]]), np.diff(np.r_[y, y[0]])).sum())
    if not nseg:
        nseg = int(np.clip(round(per / step), smin, smax))

    tck, _u = splprep([x, y], s=0.0, per=True, k=3)
    uu = np.linspace(0.0, 1.0, nseg + 1)
    P = np.column_stack(splev(uu, tck)).astype(np.float64)
    T = np.column_stack(splev(uu, tck, der=1)).astype(np.float64)
    k = 3.0 * (len(P) - 1)
    out = ["M%.2f %.2f" % (P[0, 0], P[0, 1])]
    for i in range(len(P) - 1):
        c1 = P[i] + T[i] / k
        c2 = P[i + 1] - T[i + 1] / k
        out.append("C%.2f %.2f %.2f %.2f %.2f %.2f"
                   % (c1[0], c1[1], c2[0], c2[1], P[i + 1, 0], P[i + 1, 1]))
    return "".join(out) + "Z", nseg


# ---------------------------------------------------------------- 方法一：vtracer
def vtracer_paths(mask, pad=4):
    import vtracer
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


def clip_iou(body, mask):
    """把路径回渲染一遍，与掩膜算 IoU（兜底：防止写出坏 clip）"""
    if cairosvg is None:
        return 1.0
    h, w = mask.shape[:2]
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


def run(svg, png, elmap, out, label_to_name, skip=(), min_px=5000,
        grow=2, inner=2, quant=6, min_iou=0.95, max_cost=2.0e6,
        method="subpixel", sigma=1.4, nseg=0, step=8.0, quiet=False):
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

        # 组必须唯一
        pat0 = r'<g\s[^>]*\bdata-element="%s"[^>]*>' % re.escape(eid)
        hit0 = list(re.finditer(pat0, s))
        if len(hit0) != 1:
            rows.append(dict(eid=eid, status=("multi-group" if hit0 else "no-group"),
                             px=int(mask.sum()), groups=len(hit0)))
            continue

        if method == "vtracer":
            paths = vtracer_paths(main_m)
            if not paths:
                rows.append(dict(eid=eid, status="no-path", px=int(mask.sum())))
                continue
            body = "".join('<path transform="translate(%.3f %.3f)" d="%s" fill="#000"/>'
                           % (tx, ty, d) for d, tx, ty in paths)
            nseg_e = sum(d.count("C") for d, _tx, _ty in paths)
            clip_inner = "".join('<path transform="translate(%.3f %.3f)" d="%s"/>' % (tx, ty, d)
                                 for d, tx, ty in paths)
        else:
            d, nseg_e = subpixel_path(main_m, sigma=sigma, nseg=nseg, step=step)
            if not d:
                rows.append(dict(eid=eid, status="no-path", px=int(mask.sum())))
                continue
            body = '<path d="%s" fill="#000"/>' % d
            clip_inner = '<path d="%s"/>' % d

        iou = clip_iou(body, main_m)
        if iou < min_iou:
            rows.append(dict(eid=eid, status="low-iou", px=int(mask.sum()), iou=iou))
            continue

        # ★ 代价闸门：cairosvg 把 clip 摊进每条被裁的 path，体积 ~ 段数 x path 数
        n_paths = s.count("<path", hit0[0].end(), s.find("</g>", hit0[0].end()))
        cost = float(nseg_e) * max(n_paths, 1)
        if cost > max_cost:
            rows.append(dict(eid=eid, status="too-costly", px=int(mask.sum()),
                             seg=nseg_e, paths=n_paths, cost=cost))
            continue

        frag = ""
        if extra.any():
            ey, ex = np.nonzero(extra)
            frag = '<path d="%s"/>' % "".join("M%d %dh1v1h-1z" % (x, y)
                                              for y, x in zip(ey.tolist(), ex.tolist()))

        defs.append('<clipPath id="spl-%s" clipPathUnits="userSpaceOnUse">%s%s</clipPath>'
                    % (eid, clip_inner, frag))

        band = (ndi.binary_dilation(mask, iterations=grow)
                & ~ndi.binary_erosion(mask, iterations=inner + grow))
        _, (iy, ix) = ndi.distance_transform_edt(~mask, return_indices=True)
        by, bx = np.nonzero(band)
        cols = [hexc(img[iy[y, x], ix[y, x]], quant) for y, x in zip(by.tolist(), bx.tolist())]
        pbody = "".join('<path data-band="1" fill="%s" stroke="%s" stroke-width="1.00" '
                        'stroke-linejoin="round" d="%s"/>' % (c, c, dd)
                        for c, dd in run_rects(bx, by, cols).items())

        i0, j0 = hit0[0].start(), hit0[0].end()
        head = hit0[0].group(0)
        if "clip-path=" in head:
            rows.append(dict(eid=eid, status="has-clip", px=int(mask.sum())))
            continue
        s = s[:i0] + head[:-1] + ' clip-path="url(#spl-%s)">' % eid + s[j0:]
        i1 = s.find("</title>", i0) + len("</title>")
        s = s[:i1] + pbody + s[i1:]
        rows.append(dict(eid=eid, status="ok", px=int(mask.sum()), iou=iou,
                         frags=int(extra.sum()), band=int(len(cols)),
                         seg=nseg_e, paths=n_paths))

    if defs:
        k = s.find("</desc>") + len("</desc>")
        s = s[:k] + "\n<defs>\n" + "\n".join(defs) + "\n</defs>" + s[k:]
    io.open(out, "w", encoding="utf-8").write(s)

    if not quiet:
        for r in rows:
            if r["status"] == "ok":
                print("  spline %-4s mask=%-6d IoU=%.4f seg=%-4d frags=%-5d band-px=%-6d"
                      % (r["eid"], r["px"], r["iou"], r["seg"], r["frags"], r["band"]))
            elif r["status"] == "too-costly":
                print("  skip   %-4s 代价过高（%d 段 x %d path = %.1e > %.1e）"
                      % (r["eid"], r["seg"], r["paths"], r["cost"], max_cost))
            elif r["status"] == "multi":
                print("  skip   %-4s 多连通（最大块只占 %.1f%%）" % (r["eid"], 100 * r["frac"]))
            elif r["status"] == "multi-group":
                print("  skip   %-4s 同名图层组 %d 个（多面板，不猜）" % (r["eid"], r["groups"]))
            elif r["status"] == "low-iou":
                print("  skip   %-4s IoU=%.4f < %.2f" % (r["eid"], r["iou"], min_iou))
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
    ap.add_argument("--method", choices=["subpixel", "vtracer"], default="subpixel")
    ap.add_argument("--sigma", type=float, default=1.4, help="subpixel：软化半径（px）")
    ap.add_argument("--step", type=float, default=8.0, help="subpixel：每段弧长（px），决定段数")
    ap.add_argument("--nseg", type=int, default=0, help="subpixel：直接指定段数（0=按 step 自适应）")
    ap.add_argument("--min-px", type=int, default=5000)
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
               min_px=a.min_px, grow=a.grow, inner=a.inner, quant=a.quant,
               min_iou=a.min_iou, max_cost=a.max_cost, method=a.method,
               sigma=a.sigma, nseg=a.nseg, step=a.step)
    print("-> %s（%d 个元素加样条）" % (a.out, sum(1 for r in rows if r["status"] == "ok")))


if __name__ == "__main__":
    main()
