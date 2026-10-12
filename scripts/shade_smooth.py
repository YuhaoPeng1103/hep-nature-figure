#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shade_smooth -- 位图 + 临摹 → 光滑档 SVG（第 ③-B 档，默认交付）

几何只来自第 ② 步的临摹层。每个物理元素重做成：

  (a) clipPath  —— 该元素在临摹图里的精确可见轮廓（Chaikin 平滑 + Douglas-Peucker）；
  (b) 渐变网格  —— 每 CELL 像素一条横向 linearGradient（颜色简化到最少 stop），
                   每个色带矩形画两遍：一遍用本行渐变，一遍用下一行渐变 + 纵向 mask，
                   于是纵向也插值 —— 这是"放大不糊"的来源（不是 SVG 滤镜）；
  (c) 线稿贴回  —— 网格解释不了的残差（|src - base| > thr）单独铺一层细网格
                   （DC 像素一格，边缘按距离场羽化），把描边 / 切割线 / 穿球格线贴回；
  (d) 真文字    —— 临摹图里 data-role="text" 的 <text> 原样保留（可选）。

为什么需要它：③-A 对象档能改形状但天生不平滑；本档专门换"光滑"，
判据见 scripts/smooth_metric.py（只在位图本身平滑的像素上量相邻通道跳变）。

与"区域式描摹"（VTracer / Potrace / Illustrator 彩色描摹）的差别：那些工具把一颗柔渐变球
量化成一层层等色环，放大看得见台阶、点一下选中一条环；本档的 clip 是**物理元素**，
台阶在 grid 尺度以下。

依赖：numpy scipy opencv-python Pillow cairosvg（临摹层渲染用）。

用法
----
    python scripts/shade_smooth.py \
        --src  gen/chosen.png --trace gen/chosen_trace.svg \
        --stem fig --outdir out --size 1664x909 \
        --cell background=12,plate=8,default=4

产出 <outdir>/<stem>_mesh.svg。★ 带 <mask>，用 cairosvg 渲染会丢旁衬层 ——
回渲染请用 Edge/Chrome（headless 截图）。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time

import numpy as np
from scipy import ndimage
from PIL import Image
import cv2

MINSZ = 32
ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


def attrs(tag):
    return dict(ATTR.findall(tag))


def group_body(s, m):
    """m 指向 <g ...> 的开头；返回该 <g> 的平衡内容（嵌套 <g> 也算）。"""
    start, i, depth = m.end(), m.end(), 1
    while depth:
        n, c = s.find("<g", i), s.find("</g>", i)
        if c < 0:
            break
        if n != -1 and n < c:
            depth += 1
            i = n + 2
        else:
            depth -= 1
            i = c + 4
    return s[start:i - 4]


def svg_head(trace):
    a = trace.index("<svg")
    return trace[:trace.index(">", a) + 1]


def parse_trace(trace):
    """返回 (W, H, els)：els 按文档顺序，每项 dict(element, body, attrs)。"""
    head = trace[:trace.index(">", trace.index("<svg")) + 1]
    ha = attrs(head)
    m = re.search(r'viewBox="([\d.eE+-]+)[ ,]+([\d.eE+-]+)[ ,]+([\d.eE+-]+)[ ,]+([\d.eE+-]+)"', head)
    if m:
        W, H = float(m.group(3)), float(m.group(4))
    else:
        W = float(re.sub(r"[^0-9.eE+-]", "", ha.get("width", "0")) or 0)
        H = float(re.sub(r"[^0-9.eE+-]", "", ha.get("height", "0")) or 0)
    els = []
    for m in re.finditer(r'<g\b[^>]*\bdata-element="([^"]*)"[^>]*>', trace):
        a = attrs(m.group(0))
        els.append(dict(element=a["data-element"], label=a.get("data-label", ""),
                        body=group_body(trace, m)))
    return int(round(W)), int(round(H)), els, head


def parse_text(trace, head):
    """临摹图里 data-role="text" 组内的 <text> 原样抽出来（真文字，可编辑）。"""
    out = []
    for m in re.finditer(r'<g\b[^>]*\bdata-role="text"[^>]*>', trace):
        body = group_body(trace, m)
        for t in re.finditer(r"<text([^>]*)>(.*?)</text>", body, re.S):
            a = attrs(t.group(1))
            txt = re.sub(r"<[^>]+>", "", t.group(2))
            if txt.strip() and "x" in a and "y" in a:
                out.append((a, txt))
    return out


def rasterize(head, body, W, H):
    """把一个元素的 <g> 单独渲染成掩膜：非白即属于该元素。cairosvg 只认页面级 svg。"""
    import cairosvg
    svg = (head + '\n<rect x="-8" y="-8" width="%d" height="%d" fill="#ffffff"/>' % (W + 16, H + 16)
           + body + "\n</svg>\n")
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                           output_width=W, output_height=H, background_color="white")
    A = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), np.int16)
    return (255 - A.min(2)) > 8


def smoothed_clip_svg(mask, iters=2, eps=0.55, dilate=1, prec=2):
    """像素掩膜的 Chaikin 平滑轮廓 → SVG path 'd'（子路径 + even-odd 洞里）。"""
    m = np.ascontiguousarray(mask.astype(np.uint8))
    if dilate:
        m = cv2.dilate(m, np.ones((2 * dilate + 1, 2 * dilate + 1), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for c in cnts:
        if len(c) < 4:
            continue
        p = c[:, 0, :].astype(np.float64)
        for _ in range(iters):
            q = np.empty((2 * len(p), 2))
            q[0::2] = 0.75 * p + 0.25 * np.roll(p, -1, axis=0)
            q[1::2] = 0.25 * p + 0.75 * np.roll(p, -1, axis=0)
            p = q
        ap = cv2.approxPolyDP(p.reshape(-1, 1, 2).astype(np.float32), eps, True)
        if len(ap) < 3:
            ap = p.reshape(-1, 1, 2).astype(np.float32)
        pp = ap[:, 0, :]
        d = ["M%.*f %.*f" % (prec, pp[0][0], prec, pp[0][1])]
        d += ["L%.*f %.*f" % (prec, q2[0], prec, q2[1]) for q2 in pp[1:]]
        d.append("Z")
        parts.append("".join(d))
    return "".join(parts) if parts else None


def component_lattice(fieldF, comp, cell, W, H):
    ysi, xsi = np.nonzero(comp)
    if len(xsi) < 4:
        return None
    gx0 = int(np.floor(xsi.min() / cell) * cell)
    gx1 = int(np.ceil(xsi.max() / cell) * cell)
    gy0 = int(np.floor(ysi.min() / cell) * cell)
    gy1 = int(np.ceil(ysi.max() / cell) * cell)
    xs = np.arange(gx0, gx1 + 1, cell).astype(np.int64)
    ys = np.arange(gy0, gy1 + 1, cell).astype(np.int64)
    if len(xs) < 2 or len(ys) < 2:
        return None
    xsc = np.clip(xs, 0, W - 1)
    ysc = np.clip(ys, 0, H - 1)
    V = np.ascontiguousarray(fieldF[np.ix_(ysc, xsc)])
    return dict(xs=xs.astype(np.int32), ys=ys.astype(np.int32), V=V,
                x0=int(xsi.min()), x1=int(xsi.max()), y0=int(ysi.min()), y1=int(ysi.max()))


def predict_span(xs, ys, V, x0, x1, y0, y1):
    px = np.arange(x0, x1 + 1, dtype=np.float32)
    py = np.arange(y0, y1 + 1, dtype=np.float32)
    u = ((px - xs[0]) / float(xs[1] - xs[0]))[None, :]
    v = ((py - ys[0]) / float(ys[1] - ys[0]))[:, None]
    mapx = np.ascontiguousarray(np.repeat(u, v.shape[0], axis=0), dtype=np.float32)
    mapy = np.ascontiguousarray(np.repeat(v, u.shape[1], axis=1), dtype=np.float32)
    return cv2.remap(np.ascontiguousarray(V, np.float32), mapx, mapy,
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def row_gradient(pid, j, xs, V, eps=1.6):
    """第 j 行一条横向 linearGradient，颜色简化到最少 stop。"""
    cols = len(xs)
    row = V[j]
    keep = [0]
    anchor, i = 0, 1
    while i < cols:
        seg = np.asarray(row[anchor:i + 1], np.float64)
        t = np.arange(len(seg), dtype=np.float64) / float(i - anchor)
        pred = seg[0] + (seg[-1] - seg[0]) * t[:, None]
        if float(np.abs(seg - pred).max()) <= eps:
            i += 1
        else:
            keep.append(i - 1)
            anchor = i - 1
            i = anchor + 1
    if keep[-1] != cols - 1:
        keep.append(cols - 1)
    x0 = float(xs[0]) + 0.5
    x1 = float(xs[-1]) + 0.5
    rng = max(1e-6, x1 - x0)
    out = ['<linearGradient id="g%d_%d" gradientUnits="userSpaceOnUse" x1="%g" y1="0" x2="%g" y2="0">'
           % (pid, j, x0, x1)]
    for k in keep:
        off = (float(xs[k]) + 0.5 - x0) / rng
        c = row[k]
        out.append('<stop offset="%.5f" stop-color="#%02x%02x%02x"/>'
                   % (off, int(min(255, max(0, round(float(c[0]))))),
                      int(min(255, max(0, round(float(c[1]))))),
                      int(min(255, max(0, round(float(c[2])))))))
    out.append("</linearGradient>")
    return "".join(out), len(keep)


def main():
    ap = argparse.ArgumentParser(description="位图 + 临摹 → 光滑档 SVG（③-B）")
    ap.add_argument("--src", required=True, help="客户选定的位图（几何的亮度来源）")
    ap.add_argument("--trace", required=True, help="第 ② 步的临摹 SVG（带 <g data-element>）")
    ap.add_argument("--stem", required=True, help="输出名（→ <outdir>/<stem>_mesh.svg）")
    ap.add_argument("--outdir", default=".", help="输出目录")
    ap.add_argument("--size", default="", help="WxH；默认从临摹 SVG 的 viewBox 读")
    ap.add_argument("--cell", default="background=12,plate=8,default=4",
                    help="每个元素拟合网格的格距（px）；default 兜底，可 per-element")
    ap.add_argument("--dc", type=int, default=2, help="线稿残差层的格距")
    ap.add_argument("--tile", type=int, default=64, help="残差层切块边长")
    ap.add_argument("--thr", type=float, default=7, help="残差阈值 |src-base|")
    ap.add_argument("--mind", type=int, default=6, help="残差连通块最小像素")
    ap.add_argument("--feather", type=float, default=4, help="残差边缘羽化（距离场尺度）")
    ap.add_argument("--width-mm", type=float, default=183.0, help="成品物理宽度（mm）")
    ap.add_argument("--no-detail", action="store_true", help="不出线稿残差层")
    ap.add_argument("--no-text", action="store_true", help="不搬临摹图里的真 <text>")
    a = ap.parse_args()

    t0 = time.time()
    trace = io.open(a.trace, encoding="utf-8", errors="replace").read()
    W, H, els, head = parse_trace(trace)
    TW, TH = W, H                       # 临摹 SVG 自己的坐标系（文字坐标是这一套）
    if a.size:
        W, H = (int(v) for v in a.size.lower().split("x"))
    sx, sy = W / float(TW), H / float(TH)
    if W <= 0 or H <= 0:
        sys.exit("无法从临摹 SVG 读到尺寸，请用 --size WxH")
    src = np.ascontiguousarray(np.asarray(Image.open(a.src).convert("RGB")).astype(np.float32))
    if src.shape[1] != W or src.shape[0] != H:
        src = np.ascontiguousarray(np.asarray(
            Image.open(a.src).convert("RGB").resize((W, H), Image.LANCZOS)).astype(np.float32))
    spec = {}
    for kv in a.cell.split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            spec[k.strip()] = float(v)
    dcell = spec.get("default", 4.0)
    os.makedirs(a.outdir, exist_ok=True)
    print("src %s %dx%d  trace %s  elements %d  %.1fs"
          % (a.src, W, H, os.path.basename(a.trace), len(els), time.time() - t0), flush=True)

    # ---- 掩膜：每个元素单独渲染（own region）；再按文档顺序 back→front 叠成分区 ----
    vis = {}
    for e in els:
        vis[e["element"]] = rasterize(head, e["body"], W, H)
        print("  %-16s %8d px" % (e["element"], vis[e["element"]].sum()), flush=True)
    assigned = np.zeros((H, W), np.int16) - 1
    for k, e in enumerate(els):
        assigned[vis[e["element"]]] = k
    gap = assigned < 0
    if gap.any():
        # 画布上的空白是背景，不是"离谁近算谁"—— 后者会把元素糊出边界。
        bg = next((k for k, e in enumerate(els) if e["element"] == "background"), -1)
        if bg >= 0:
            assigned[gap] = bg
            # 背景 = 画布填充：白色的空白要算进它的【拟合区】，否则颜色场会被
            # 它自己的深色引线带偏 → base 发灰 → 残差层被迫重画整张画布。
            vis[els[bg]["element"]] = vis[els[bg]["element"]] | gap
            print("  gap %.2f%% -> background" % (100.0 * gap.mean()), flush=True)
        else:
            print("  gap %.2f%% left unassigned (no data-element=\"background\")"
                  % (100.0 * gap.mean()), flush=True)
    meas, fill = vis, assigned

    # ---- 层 A：每个元素一条 clipPath + 逐行渐变网格 ----
    piecesA = []
    for k, e in enumerate(els):
        M = meas.get(e["element"])
        R = (fill == k)
        if M is None or M.sum() < MINSZ or R.sum() < MINSZ:
            print("  %-16s SKIP" % e["element"], flush=True)
            continue
        cell = spec.get(e["element"], dcell)
        idx = ndimage.distance_transform_edt(~M, return_distances=False, return_indices=True)
        fieldF = src[idx[0], idx[1]]
        box = 2 * max(1, int(round(cell * 0.3))) + 1
        F = ndimage.uniform_filter(fieldF, size=(box, box, 1), mode="nearest")
        n, lab, st, cen = cv2.connectedComponentsWithStats(R.astype(np.uint8), 8)
        keepc = [j for j in range(1, n) if st[j, 4] >= MINSZ]
        print("  %-16s cell %4.1f  cover %8d  comps %d"
              % (e["element"], cell, int(R.sum()), len(keepc)), flush=True)
        for j in keepc:
            cm = (lab == j)
            f = component_lattice(F, cm, cell, W, H)
            if f is None:
                continue
            piecesA.append((e["element"], dict(f, mask=cm)))
    print("layer A: %d pieces  %.1fs" % (len(piecesA), time.time() - t0), flush=True)

    # ---- 层 B：残差（网格解释不了的线稿）→ 细网格 + 羽化 ----
    base = np.zeros((H, W, 3), np.float32)
    base_cov = np.zeros((H, W), bool)
    for _n, f in piecesA:
        pr = predict_span(f["xs"], f["ys"], f["V"], f["x0"], f["x1"], f["y0"], f["y1"])
        sub = base[f["y0"]:f["y1"] + 1, f["x0"]:f["x1"] + 1]
        cov = base_cov[f["y0"]:f["y1"] + 1, f["x0"]:f["x1"] + 1]
        mk = f["mask"][f["y0"]:f["y1"] + 1, f["x0"]:f["x1"] + 1]
        sub[mk] = pr[mk]
        cov[mk] = True
    print("layer A coverage %.2f%% of canvas" % (100.0 * base_cov.mean()), flush=True)
    det = []
    if not a.no_detail:
        d = np.abs(src - base).max(2)
        need = (d > a.thr)
        nl, lab, st, _ = cv2.connectedComponentsWithStats(need.astype(np.uint8), 8)
        keep = np.zeros(nl, bool)
        for j in range(1, nl):
            if st[j, 4] >= a.mind:
                keep[j] = True
        Mm = keep[lab]
        Mm |= (base_cov == False)  # noqa: E712
        Mm = ndimage.binary_fill_holes(Mm)
        Mm = cv2.dilate(Mm.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        print("detail mask %.2f%% of canvas" % (100.0 * Mm.mean()), flush=True)
        din = ndimage.distance_transform_edt(Mm).astype(np.float32)
        dc, tile = a.dc, a.tile
        for ty in range(0, H, tile):
            for tx in range(0, W, tile):
                ty1, tx1 = min(ty + tile, H), min(tx + tile, W)
                sub = Mm[ty:ty1, tx:tx1]
                if sub.sum() < 24:
                    continue
                ysi, xsi = np.nonzero(sub)
                ax0 = max(0, ((int(xsi.min()) + tx) // dc) * dc - 2 * dc)
                ax1 = min(W - 1, ((int(xsi.max()) + tx) // dc + 3) * dc)
                ay0 = max(0, ((int(ysi.min()) + ty) // dc) * dc - 2 * dc)
                ay1 = min(H - 1, ((int(ysi.max()) + ty) // dc + 3) * dc)
                xs = np.arange(ax0, ax1 + 1, dc)
                ys = np.arange(ay0, ay1 + 1, dc)
                if len(xs) < 2 or len(ys) < 2:
                    continue
                xsc = np.clip(xs, 0, W - 1)
                ysc = np.clip(ys, 0, H - 1)
                Vs = src[np.ix_(ysc, xsc)]
                Vb = base[np.ix_(ysc, xsc)]
                ww = np.clip(din[np.ix_(ysc, xsc)] / a.feather, 0.0, 1.0)[:, :, None]
                V = np.ascontiguousarray(ww * Vs + (1.0 - ww) * Vb)
                full = np.zeros((H, W), np.uint8)
                full[ty:ty1, tx:tx1] = sub.astype(np.uint8)
                dstr = smoothed_clip_svg(full, iters=2, eps=0.55, dilate=1)
                if dstr is None:
                    continue
                det.append((dstr, xs.astype(np.int32), ys.astype(np.int32), V))
        nv = sum(len(x) * len(y) for _, x, y, _ in det)
        print("layer B: %d tiles, %d verts (~%.1f MB)" % (len(det), nv, nv * 7 / 1048576.), flush=True)

    # ---- 装配 ----
    pieces = [(n, f["mask"], f["xs"], f["ys"], f["V"]) for n, f in piecesA]
    pieces += [("detail-layer", d_, xs_, ys_, V_) for (d_, xs_, ys_, V_) in det]
    defs = ['<linearGradient id="vbl" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="#000000"/><stop offset="1" stop-color="#ffffff"/>'
            '</linearGradient>',
            '<mask id="vmsk" maskContentUnits="objectBoundingBox">'
            '<rect x="0" y="0" width="1" height="1" fill="url(#vbl)"/></mask>']
    body, nstops, nrect, cur_el = [], 0, 0, None
    for pid, (ename, mask, xs, ys, V) in enumerate(pieces):
        if len(ys) < 2 or len(xs) < 2:
            continue
        d = mask if isinstance(mask, str) else smoothed_clip_svg(mask, iters=2, eps=0.55, dilate=1)
        if not d:
            continue
        defs.append('<clipPath id="c%d" clipPathUnits="userSpaceOnUse"><path d="%s"/></clipPath>' % (pid, d))
        for j in range(len(ys)):
            g, ns = row_gradient(pid, j, xs, V)
            defs.append(g)
            nstops += ns
        x0 = float(xs[0])
        wd = float(xs[-1]) + 1.0 - x0
        band = ['<g clip-path="url(#c%d)">' % pid]
        for j in range(len(ys) - 1):
            y0 = float(ys[j])
            hh = float(ys[j + 1]) - y0
            band.append('<rect x="%g" y="%g" width="%g" height="%g" fill="url(#g%d_%d)"/>'
                        % (x0, y0, wd, hh, pid, j))
            band.append('<rect x="%g" y="%g" width="%g" height="%g" fill="url(#g%d_%d)" mask="url(#vmsk)"/>'
                        % (x0, y0, wd, hh, pid, j + 1))
            nrect += 2
        band.append("</g>")
        if ename != cur_el:
            if cur_el is not None:
                body.append("</g>")
            body.append('<g id="el-%s" data-element="%s">' % (ename, ename))
            cur_el = ename
        body.append("".join(band))
    print("  gradients %d  stops %d (~%.1f MB)  rects %d"
          % (len(defs), nstops, nstops * 46 / 1048576., nrect), flush=True)
    if cur_el is not None:
        body.append("</g>")

    ntext = 0
    if not a.no_text:
        seen = set()
        for a2, txt in parse_text(trace, head):
            key = (a2["x"], a2["y"], a2.get("font-size", ""), txt)
            if key in seen:                 # data-role="text" 组会嵌套，去重
                continue
            seen.add(key)
            # ★ 文字坐标是【临摹 SVG 自己的坐标系】，要按输出尺寸缩放
            x, y = float(a2["x"]) * sx, float(a2["y"]) * sy
            fs = float(a2.get("font-size", "50")) * sx
            ls = float(a2.get("letter-spacing", "0")) * sx
            wt = ' font-weight="bold"' if a2.get("font-weight", "").lower() in ("bold", "700") else ""
            lsx = (' letter-spacing="%g"' % ls) if ls else ""
            body.append('<text x="%g" y="%g" font-family="Helvetica,Arial,sans-serif" font-size="%g"%s%s '
                        'fill="%s">%s</text>'
                        % (x, y, fs, wt, lsx, a2.get("fill", "#000000"),
                           txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")))
            ntext += 1
        print("  text runs %d" % ntext, flush=True)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%.4fmm" height="%.4fmm" viewBox="0 0 %d %d">'
           % (a.width_mm, a.width_mm * H / float(W), W, H),
           '<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H),
           "<defs>", "".join(defs), "</defs>"]
    out.extend(body)
    out.append("</svg>")
    dst = os.path.join(a.outdir, "%s_mesh.svg" % a.stem)
    io.open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("wrote %s  %.2f MB  (%.1fs)" % (dst, os.path.getsize(dst) / 1048576., time.time() - t0))


if __name__ == "__main__":
    main()
