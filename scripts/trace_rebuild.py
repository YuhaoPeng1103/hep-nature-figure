#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace_rebuild -- 矢量化成品三步里的【第三步】：从「临摹矢量图」重建

本 skill 定的固定三步（v4.0）：
    ① 客户选定/确认的位图
    ② 逐像素临摹      -> raster_to_vector_semantic.py（带语义图层 <g data-element=...>）
    ③ **从临摹层重建** -> 本脚本

为什么必须从临摹层取几何（别再走颜色阈值）：
    v37 的教训（collective_flow/build/build_figure_v37.py）：轮廓是「颜色谓词 ∩ 包围盒」
    重新抠的，于是
      · a-nucleus-far 的框 (575,35,810,255) 把真 bbox (586,46,800,306) 的底边切平了；
      · 「板下淡出」是从非单连通掩膜描出来的，成了一条卷曲细带。
    v38 改成「只从 <g data-element> 的掩膜取几何」后，红/蓝/杏仁三个体积的
    MAE 从 2.49(v35)/5.28(v37) 降到 1.95。

每个体积元素重做成三件东西：
    (a) clipPath —— 该元素在临摹图里的**精确可见轮廓**（含被遮挡后的形状）；
    (b) 真渐变网格 —— 每 BAND 像素一条 linearGradient（NSTOP 个 stop），
        颜色场从原图拟合（先按 ERODE 内缩、再 SIGMA 平滑），纵向再做一次
        高斯平滑，消掉带间噪声；
    (c) 线稿逐像素保留 —— 网格解释不了的描边/切割线/穿过球面的格线，
        原样照抄临摹图里的碎矩形，保证像素级一致。
其余元素（板、三轴、文字、箭头、虚线、别的面板）整段照抄临摹图。

用法：
    python3 scripts/trace_rebuild.py \
        --trace out/figure_v17.svg --src gen/trace_src.png \
        --stem figure_v38 --elements a-nucleus-near,a-nucleus-far,a-fireball-a
    # 尺寸默认从 <trace>.svg 的 width/height 读；也可显式 --size 1500x630

产出：<outdir>/<stem>.svg / .png（默认宽 2600） / @4000.png ，并打印逐元素读数与整图 MAE。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
import cv2

TOK = re.compile(r"<g\b[^>]*>|</g>")
RECT = re.compile(r"M(\d+) (\d+)h(\d+)v(\d+)h-\d+z")


def disk(n):
    y, x = np.mgrid[-n:n + 1, -n:n + 1]
    return (x * x + y * y) <= n * n + 0.5


def largest(m):
    lab, k = ndimage.label(m, structure=np.ones((3, 3)))
    if k == 0:
        return m
    sz = ndimage.sum(m, lab, range(1, k + 1))
    return lab == (int(np.argmax(sz)) + 1)


def parse_groups(src):
    tree, stack = {}, []
    for m in TOK.finditer(src):
        t = m.group(0)
        if t.startswith("</"):
            gid, s = stack.pop()
            tree[gid] = (s, m.start() + len(t))
        else:
            g = re.search(r'id="([^"]+)"', t)
            stack.append((g.group(1) if g else "", m.start()))
    return tree


def parse_paths(inner):
    out = []
    for m in re.finditer(r"<path\b([^>]*?)/>", inner, re.S):
        attrs = m.group(1)
        dm = re.search(r'\sd="([^"]*)"', attrs)
        if not dm:
            out.append([attrs, None, None, m.group(0)])
            continue
        d = dm.group(1)
        rects = [(int(a), int(b), int(c), int(e)) for a, b, c, e in RECT.findall(d)]
        tot = sum(len("M%d %dh%dv%dh-%dz" % (r[0], r[1], r[2], r[3], r[2])) for r in rects)
        if tot != len(d):
            out.append([attrs, None, None, m.group(0)])
        else:
            out.append([attrs.replace(' d="%s"' % d, ""), None, rects, m.group(0)])
    return out


def emit_paths(paths, keep_flag=None):
    buf = []
    for i, (pre, _c, rects, orig) in enumerate(paths):
        if rects is None:
            buf.append(orig)
            continue
        rr = rects if keep_flag is None else [r for r, kf in zip(rects, keep_flag[i]) if kf]
        if not rr:
            continue
        d = "".join("M%d %dh%dv%dh-%dz" % (r[0], r[1], r[2], r[3], r[2]) for r in rr)
        buf.append('<path%s d="%s"/>' % (pre, d))
    return "".join(buf)


def loops_d(mask, eps=0.6):
    """all contours (outer + holes) of a mask -> one even-odd path d"""
    m8 = (np.asarray(mask).astype(np.uint8)) * 255
    cnts, _h = cv2.findContours(m8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for c in cnts:
        P = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float)
        if len(P) < 3 or abs(cv2.contourArea(c)) < 3:
            continue
        parts.append("M" + " ".join("%.1f %.1f" % (x, y) for x, y in P) + "Z")
    return "".join(parts)


def silhouette_d(mask, eps=0.7, win=5, rounds=2):
    m8 = (np.asarray(mask).astype(np.uint8)) * 255
    cnts, _h = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return ""
    c = max(cnts, key=cv2.contourArea)
    P = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float)
    n = len(P)
    if win and n >= win + 2:
        ix = np.arange(n)
        for _ in range(rounds):
            acc = np.zeros_like(P)
            for k in range(-(win // 2), win // 2 + 1):
                acc += P[(ix + k) % n]
            P = acc / win
    return "M" + " ".join("%.1f %.1f" % (x, y) for x, y in P) + "Z"


def size_from_svg(src, svg_path):
    m = re.search(r"<svg\b[^>]*\bwidth=\"([\d.]+)\"[^>]*\bheight=\"([\d.]+)\"", src)
    if m:
        return int(round(float(m.group(1)))), int(round(float(m.group(2))))
    raise SystemExit("读不出 %s 的 width/height，请显式给 --size WxH" % svg_path)


def main():
    ap = argparse.ArgumentParser(description="从「临摹矢量图」重建（矢量成品第三步）")
    ap.add_argument("--trace", required=True, help="第②步的逐像素临摹 SVG（带 <g data-element> 语义层）")
    ap.add_argument("--src", required=True, help="临摹所依据的位图（成品位图）")
    ap.add_argument("--stem", required=True, help="输出名（不含扩展名）")
    ap.add_argument("--outdir", default=None, help="输出目录（默认 <trace 所在目录>）")
    ap.add_argument("--elements", default="", help="要重建的语义图层 id，逗号分隔；缺省=自动找 data-element 非空的层")
    ap.add_argument("--size", default=None, help="WxH；缺省从 trace 的 width/height 读")
    ap.add_argument("--band", type=int, default=3, help="渐变网格的带高（px，默认 3）")
    ap.add_argument("--nstop", type=int, default=24, help="每带渐变 stop 数（默认 24）")
    ap.add_argument("--erode", type=int, default=4, help="拟合颜色场前把掩膜内缩的像素数（默认 4）")
    ap.add_argument("--sigma", type=float, default=1.2, help="颜色场平滑 sigma（默认 1.2）")
    ap.add_argument("--dev-keep", type=float, default=12.0, help="偏离网格超过它的碎矩形原样保留（默认 12.0）")
    ap.add_argument("--ink-dark", type=float, default=12.0, help="比局部场暗超过它 = 线稿（默认 12.0）")
    ap.add_argument("--png-width", type=int, default=2600, help="导出 png 宽度（默认 2600）")
    a = ap.parse_args()

    src = io.open(a.trace, encoding="utf-8").read()
    trace_dir = os.path.dirname(os.path.abspath(a.trace))
    OUTD = os.path.abspath(a.outdir) if a.outdir else trace_dir
    os.makedirs(OUTD, exist_ok=True)
    SVG = os.path.join(OUTD, a.stem + ".svg")
    PNG = os.path.join(OUTD, a.stem + ".png")
    PNG4 = os.path.join(OUTD, a.stem + "@4000.png")

    if a.size:
        W, H = (int(v) for v in re.split(r"[x*,]", a.size))
    else:
        try:
            import cairosvg  # noqa: F401
        except Exception:
            pass
        W, H = size_from_svg(src, a.trace)
    BAND, NSTOP, ERODE, SIGMA = a.band, a.nstop, a.erode, a.sigma
    DEV_KEEP, INK_DARK = a.dev_keep, a.ink_dark

    tree = parse_groups(src)
    if a.elements:
        ELEMENTS = [s.strip() for s in a.elements.split(",") if s.strip()]
    else:
        ELEMENTS = [g for g in sorted(tree, key=lambda g: tree[g][0])
                    if re.search(r'data-element="[^"]+"', src[tree[g][0]:src.index(">", tree[g][0]) + 1])]
    missing = [g for g in ELEMENTS if g not in tree]
    if missing:
        raise SystemExit("临摹图里没有这些图层 id：%s" % ", ".join(missing))
    print("trace=%s\nsrc=%s\nsize=%dx%d  elements=%s" % (a.trace, a.src, W, H, ELEMENTS))

    img = np.asarray(Image.open(a.src).convert("RGB")).astype(np.float64)
    if img.shape[:2] != (H, W):
        img = np.asarray(Image.fromarray(img.astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float64)

    def inner_of(gid):
        s, e = tree[gid]
        return src[src.index(">", s) + 1: e - 4]

    def open_tag(gid):
        s, _e = tree[gid]
        return src[s:src.index(">", s) + 1]

    defs, new_body, report = [], {}, []

    for gid in ELEMENTS:
        paths = parse_paths(inner_of(gid))
        mask = np.zeros((H, W), bool)
        for pre, _c, rects, _o in paths:
            if rects is None:
                continue
            for x, y, w, h in rects:
                mask[y:y + h, x:x + w] = True
        sil = ndimage.binary_fill_holes(largest(mask))
        if sil.sum() < 200:
            report.append([gid, 0, 0, 0, 0, -1.0])
            continue
        core = ndimage.binary_erosion(sil, disk(ERODE))
        idx = ndimage.distance_transform_edt(~core, return_distances=False, return_indices=True)
        F = img[idx[0], idx[1]].copy()
        for c in range(3):
            F[..., c] = ndimage.gaussian_filter(F[..., c], SIGMA)

        cid = "tr-clip-%s" % gid
        clip = ndimage.binary_dilation(sil, disk(1))
        clip_d = silhouette_d(clip, win=0)
        defs.append('<clipPath id="%s"><path d="%s"/></clipPath>' % (cid, clip_d))

        rows = []
        for y0 in range(0, H, BAND):
            y1 = min(H, y0 + BAND)
            band = clip[y0:y1]
            if not band.any():
                continue
            cols = np.nonzero(band.any(0))[0]
            x0, x1 = int(cols.min()), int(cols.max())
            xs = np.linspace(x0, x1, NSTOP)
            prof = np.zeros((NSTOP, 3))
            for y in range(y0, y1):
                for c in range(3):
                    prof[:, c] += np.interp(xs, np.arange(W), F[y, :, c])
            rows.append([y0, y1, x0, x1, prof / max(y1 - y0, 1)])
        if len(rows) > 2:
            P = np.stack([r[4] for r in rows])
            P = ndimage.gaussian_filter1d(P, 1.5, axis=0, mode="nearest")
            for i, r in enumerate(rows):
                r[4] = P[i]

        model = np.zeros((H, W, 3))
        bands = []
        for y0, y1, x0, x1, prof in rows:
            xs = np.arange(x0, x1 + 1)
            gs = [np.interp((xs - x0) / max(x1 - x0, 1), np.linspace(0, 1, NSTOP), prof[:, c])
                  for c in range(3)]
            model[y0:y1, x0:x1 + 1] = np.stack(gs, 1)
            gid_g = "tr-g-%s-%d" % (gid, y0)
            stops = "".join('<stop offset="%.4f" stop-color="#%02x%02x%02x"/>'
                            % (k / (NSTOP - 1), int(round(v[0])), int(round(v[1])), int(round(v[2])))
                            for k, v in enumerate(prof))
            defs.append('<linearGradient id="%s" gradientUnits="userSpaceOnUse" x1="%d" y1="0" '
                        'x2="%d" y2="0">%s</linearGradient>' % (gid_g, x0, x1 + 1, stops))
            bands.append('<rect x="%d" y="%d" width="%d" height="%d" fill="url(#%s)"/>'
                         % (x0, y0, x1 + 1 - x0, y1 - y0 + 1, gid_g))

        dev = np.abs(model - img).max(2)
        lum = img.max(2)
        flum = F.max(2)
        ink_px = sil & ((dev > DEV_KEEP) | ((flum - lum) > INK_DARK))
        keep_flag, nink = [], 0
        for pre, _c, rects, _o in paths:
            if rects is None:
                keep_flag.append(None)
                continue
            kf = []
            for x, y, w, h in rects:
                x1_, y1_ = min(W, x + w), min(H, y + h)
                sub = ink_px[y:y1_, x:x1_]
                if sub.size and sub.any():
                    kf.append(True); nink += 1
                else:
                    kf.append(False)
            keep_flag.append(kf)
        kept = emit_paths(paths, keep_flag)
        new_body[gid] = ('<g clip-path="url(#%s)" data-role="mesh">%s</g>%s'
                         % (cid, "".join(bands), kept))
        npx = int(sil.sum())
        ntot = sum(len(pp[2]) for pp in paths if pp[2])
        rep = float(dev[sil & ~ink_px].mean())
        report.append([gid, npx, len(bands), nink, int(ink_px.sum()), rep])

    edits = [(tree[g][0], tree[g][1], open_tag(g) + new_body[g] + "</g>") for g in new_body]
    edits.sort(key=lambda t: t[0])
    out, pos = [], 0
    for s, e, txt in edits:
        out.append(src[pos:s]); out.append(txt); pos = e
    out.append(src[pos:])
    svg = "".join(out)
    i = svg.index(">", svg.index("<svg")) + 1
    svg = svg[:i] + "<defs>" + "".join(defs) + "</defs>" + svg[i:]
    io.open(SVG, "w", encoding="utf-8", newline="\n").write(svg)
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=PNG, output_width=a.png_width)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=PNG4, output_width=4000)

    ref = np.asarray(Image.open(PNG).convert("RGB")).astype(np.float64)
    ref = np.asarray(Image.fromarray(ref.astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float64)
    mae = np.abs(ref - img).mean()
    print("wrote %s (%.0f KB)  MAE=%.3f" % (SVG, os.path.getsize(SVG) / 1024.0, mae))
    for gid, npx, nb, nk, ntot, rep in report:
        print("  %-20s px=%6d bands=%3d inkrects=%5d inkpx=%5d  shade_resid=%.2f"
              % (gid, npx, nb, nk, ntot, rep))


if __name__ == "__main__":
    main()
