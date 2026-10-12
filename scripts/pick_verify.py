#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pick_verify -- 验证拾取层：「点一下 = 一个物理结构」到底成不成立（位图 → 矢量 第 ④ 档的验收）

它把 `pick_layer.py` 写进成品的**每一条路径单独栅格化**，然后报三组读数：

    1. 覆盖表   layer_coverage = |层 ∩ 拾取区| / |层|   这个结构的每个可见像素都能点到它自己
                pick_extra     = |拾取区 \ 层| / |拾取区| 这一份是**补出来的**（被遮住的部分）
                pick_on_empty  = |拾取区 \ 所有层| / |拾取区| 点在"图里什么都没有"的地方
                unc_smooth/textured  未被覆盖的那部分层，到底是**落影/柔边**还是**纹理/格线**
                                     （量出来的，不是假设的 —— 这是判"该不该再补"的关键）
    2. 探针表   每个元素取「可见体」与「被遮住处」各一个点，实测"位图上是甚么" vs "点一下选中甚么"。
                一次点击由**最后画的那条路径**决定，所以这条表就是 z 序的验收。
    3. 子物体   --nuc-balls 给 `{"element": {"paths": [...]}}` 时，逐子物体报面积/合并情况，
                并画一张编号地图（彩色 = 目标、白圈 + 编号 = 点那里选中的目标）。

用法
    python3 scripts/pick_verify.py --sil build/mesh/_sil.json --vis build/mesh/_vis_trace.npz \
        --ref gen/chosen_x2.png --size 3328x1818 --outdir out --stem jet_q \
        [--expect '{"fireball-core":"fireball"}'] [--nuc-balls build/mesh/_nuc_balls.json]

    --sil       ④ 用的那份 {"element": "<path d>"}（顺序 = back → front）
    --vis       ② 的逐元素可见掩膜（npz，值 = np.packbits 的位图；键名 = 元素名）
    --ref       ① 的位图（同尺寸）—— 探针表里"位图上是甚么"就是照它读的
    --expect    预期例外（JSON）：例如热芯点下去选中火球，是有意为之
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import cv2
import cairosvg
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

FALLBACK = [(90, 120, 255), (60, 200, 120), (0, 170, 90), (150, 150, 150), (255, 220, 60),
            (255, 120, 40), (200, 60, 200), (255, 60, 120), (60, 220, 240), (40, 40, 40),
            (170, 110, 60), (120, 200, 60), (60, 90, 170), (230, 160, 60)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sil", required=True)
    ap.add_argument("--vis", required=True, help="② 的逐元素可见掩膜 npz（packbits）")
    ap.add_argument("--ref", required=True, help="① 的位图（与 --sil 同尺寸）")
    ap.add_argument("--size", default="", help="WxH；默认从 --ref 读")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--stem", default="pick")
    ap.add_argument("--expect", default="{}", help='预期例外，如 {"fireball-core":"fireball"}')
    ap.add_argument("--nuc-balls", default="", help="可选：子物体 JSON（逐核子等）")
    ap.add_argument("--json", default="", help="覆盖/探针读数另存一份 JSON")
    a = ap.parse_args()

    ref_img = Image.open(a.ref).convert("RGB")
    WL, HL = ([int(v) for v in a.size.split("x")] if a.size else ref_img.size)
    sil = json.load(io.open(a.sil, encoding="utf-8"))
    order = list(sil)                                               # back -> front
    expect = json.loads(a.expect)

    def raster(d):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">'
               '<rect width="%d" height="%d" fill="#fff"/><path d="%s" fill="#000"/></svg>'
               % (WL, HL, WL, HL, d))
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=WL, output_height=HL,
                               background_color="white")
        return (255 - np.asarray(Image.open(io.BytesIO(png)).convert("L"), np.int16)) > 8

    pick = {el: raster(sil[el]) for el in order}
    z = np.load(a.vis, allow_pickle=True)
    layer = {n: np.unpackbits(z[n])[:WL * HL].reshape(HL, WL) > 0 for n in z.files}
    anyl = np.zeros((HL, WL), bool)
    for m in layer.values():
        anyl |= m
    ref = np.asarray(ref_img, np.float32)
    lum = cv2.cvtColor(np.asarray(ref_img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    _m = cv2.boxFilter(lum, -1, (25, 25)); _m2 = cv2.boxFilter(lum * lum, -1, (25, 25))
    sd = np.sqrt(np.maximum(_m2 - _m * _m, 0))

    print("%-14s %9s %9s %-8s %-7s %-7s %-9s %-9s %s" % ("element", "pick px", "layer px",
          "covered", "extra", "empty", "unc smooth", "unc text", "what the uncovered layer is"))
    rows = []
    for el in order:
        L, P = layer.get(el, np.zeros((HL, WL), bool)), pick[el]
        cov = float((L & P).sum()) / max(1, L.sum())
        extra = float((P & ~L).sum()) / max(1, P.sum())
        empty = float((P & ~anyl).sum()) / max(1, P.sum())
        unc = L & ~P; n_u = max(1, int(unc.sum()))
        sm = float((unc & (sd < 6)).sum()) / n_u
        tx = float((unc & (sd >= 6)).sum()) / n_u
        ut = unc & (sd >= 6)
        thick = 2.0 * float(ndimage.distance_transform_edt(ut).max()) if ut.sum() else 0.0
        din = ndimage.distance_transform_edt(~P)
        near = float((unc & (din <= 40)).sum()) / n_u
        far = float((unc & (din > 40)).sum()) / n_u
        rows.append(dict(element=el, pick_px=int(P.sum()), layer_px=int(L.sum()),
                         layer_covered=round(cov, 4), pick_extra=round(extra, 4),
                         pick_on_empty=round(empty, 4), unc_smooth_frac=round(sm, 3),
                         unc_textured_frac=round(tx, 3),
                         unc_textured_max_thickness_px=round(thick, 1),
                         unc_near_boundary_frac=round(near, 3), unc_far_frac=round(far, 3)))
        print("%-14s %9d %9d %-8.3f %-7.3f %-7.3f %-9.2f %-9.2f  uncover: %3.0f%% near the "
              "boundary, %3.0f%% far away (grid lines / arrow / shadow)"
              % (el, P.sum(), L.sum(), cov, extra, empty, sm, tx, 100 * near, 100 * far))

    def nearest(m, cx, cy):
        ys, xs = np.nonzero(m)
        if len(xs) == 0:
            return None
        i = int(np.argmin((xs - cx) ** 2 + (ys - cy) ** 2))
        return int(xs[i]), int(ys[i])

    def top_pick(x, y):
        w = [e for e in order if pick[e][y, x]]
        return w[-1] if w else "(nothing)"

    def top_layer(x, y):
        w = [e for e in order if layer.get(e) is not None and layer[e][y, x]]
        return w[-1] if w else "(canvas / nothing)"

    probes = []
    for el in order:
        L, P = layer.get(el, np.zeros((HL, WL), bool)), pick[el]
        later = np.zeros((HL, WL), bool)
        for e in order[order.index(el) + 1:]:
            later |= pick[e]
        vis_m = L & P
        if vis_m.sum():
            ys, xs = np.nonzero(vis_m); cx, cy = xs.mean(), ys.mean()
            ok = vis_m & ~later
            p = nearest(ok if ok.sum() else vis_m, cx, cy)
            if p:
                probes.append(dict(element=el, kind="visible body", x=p[0], y=p[1],
                                   bitmap_shows=top_layer(*p), click_picks=top_pick(*p),
                                   ok=top_pick(*p) == el))
        hid = P & ~L
        if hid.sum():
            ys, xs = np.nonzero(hid); cx, cy = xs.mean(), ys.mean()
            ok = hid & ~later
            if ok.sum():
                p = nearest(ok, cx, cy)
                probes.append(dict(element=el, kind="occluded part", x=p[0], y=p[1],
                                   bitmap_shows=top_layer(*p), click_picks=top_pick(*p), ok=True))
            else:
                probes.append(dict(element=el, kind="occluded part", x=None, y=None,
                                   bitmap_shows="-", click_picks="-", ok=False,
                                   note="every completed pixel is covered by a structure drawn "
                                        "in front (correct)"))
    print()
    print("%-14s %-14s %10s %-24s %-14s %s" % ("element", "probe", "xy", "bitmap shows",
                                               "a click picks", ""))
    for p in probes:
        if p["element"] in expect and p["click_picks"] == expect[p["element"]]:
            p["ok"] = True
            p["note"] = "expected exception: %s" % expect[p["element"]]
        print("%-14s %-14s %10s %-24s %-14s %s" % (p["element"], p["kind"],
              "(%s,%s)" % (p["x"], p["y"]), p["bitmap_shows"], p["click_picks"],
              "" if p["ok"] else "<-- CHECK"))
    real = [p for p in probes if not p["ok"] and not (p["x"] is None and p["click_picks"] == "-")]
    print("probes that do NOT do what is claimed (after the documented %s exception): %d"
          % (", ".join(expect) or "none", len(real)))
    if not os.path.isdir(a.outdir):
        os.makedirs(a.outdir)

    # ---- pick map + optional sub-object map
    colmap = {}
    for i, el in enumerate(order):
        colmap[el] = FALLBACK[i % len(FALLBACK)]
    over = ref * 0.40 + 255 * 0.60
    win = np.full((HL, WL), -1, np.int16)
    for i, el in enumerate(order):
        win[pick[el]] = i
    for i, el in enumerate(order):
        m = win == i
        over[m] = over[m] * 0.35 + np.array(colmap[el]) * 0.65
    pm = Image.fromarray(np.clip(over, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(pm)
    d.rectangle([16, 16, 1180, 62], fill=(0, 0, 0))
    d.text((28, 32), "PICK MAP -- a click anywhere in a colour selects that physical structure",
           fill=(255, 255, 0))
    for i, el in enumerate(order):
        d.rectangle([20, 86 + i * 42, 74, 118 + i * 42], fill=colmap[el], outline=(0, 0, 0))
        m = pick[el]; tot = max(1, int(m.sum())); sh = []
        for e in order:
            later = np.zeros((HL, WL), bool)
            for e3 in order[order.index(e) + 1:]:
                later |= pick[e3]
            c = int((m & pick[e] & ~later).sum())
            if c:
                sh.append((c / tot, e))
        sh.sort(key=lambda t: -t[0])
        lab = ("%s   (pick region %d px%s)" % (el, tot,
               "" if len(sh) <= 1 or sh[0][0] >= 0.995 else
               " -- a click here selects: %s" % ", ".join("%s %.0f%%" % (e, 100 * f)
                                                           for f, e in sh[:3])))
        d.text((88, 94 + i * 42), lab, fill=(0, 0, 0))
    pm.save(os.path.join(a.outdir, a.stem + "_pickmap.png"))
    print("saved", os.path.join(a.outdir, a.stem + "_pickmap.png"), pm.size)

    nrows = []
    bj = a.nuc_balls or a.sil.replace("_sil.json", "_nuc_balls.json")
    nuc = json.load(io.open(bj, encoding="utf-8")) if os.path.exists(bj) else {}
    ntiles = []
    for el, b in nuc.items():
        P = pick[el]
        sub = [raster(d) for d in b.get("paths", [])]
        if not sub:
            continue
        areas = sorted(int(m.sum()) for m in sub)
        med = areas[len(areas) // 2] if areas else 0
        single = [x for x in areas if x <= 1.6 * med]
        nrows.append(dict(element=el, nucleons=len(sub), nucleus_px=int(P.sum()),
                          nucleon_union_px=int(sum(int(m.sum()) for m in sub)),
                          union_share=round(float(sum(int((m & P).sum()) for m in sub))
                                            / max(1, P.sum()), 4),
                          area_min=areas[0], area_median=med, area_max=areas[-1],
                          single_ball_paths=len(single), merged_paths=len(areas) - len(single),
                          balls_the_bitmap_resolves=round(float(P.sum()) / max(1, med), 1)))
        ov = ref.copy()
        rng = np.random.RandomState(11)
        hue = rng.randint(70, 256, (len(sub) + 1, 3))
        for i, m in enumerate(sub):
            ov[m] = ov[m] * 0.35 + hue[i] * 0.65
        im = Image.fromarray(np.clip(ov, 0, 255).astype(np.uint8))
        d2 = ImageDraw.Draw(im)
        ec, _ = cv2.findContours(P.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in ec:
            pts = [tuple(p[0]) for p in c[::4]]
            if len(pts) > 1:
                d2.line(pts + [pts[0]], fill=(0, 0, 0), width=5)
        for i, m in enumerate(sub):
            ys, xs = np.nonzero(m)
            if len(xs) == 0:
                continue
            cx, cy = int(xs.mean()), int(ys.mean())
            d2.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(255, 255, 255),
                       outline=(0, 0, 0), width=3)
            d2.text((cx - 18, cy - 8), "%d" % (i + 1), fill=(0, 0, 0))
        ys, xs = np.nonzero(P)
        pad = 60
        im = im.crop((max(0, xs.min() - pad), max(0, ys.min() - pad),
                      min(WL, xs.max() + pad), min(HL, ys.max() + pad)))
        d2 = ImageDraw.Draw(im); d2.rectangle([0, 0, im.width - 1, 26], fill=(0, 0, 0))
        d2.text((6, 7), "'%s': %d sub-object click targets (the number = the target a click "
                "there selects); black outline = the parent body" % (el, len(sub)),
                fill=(255, 255, 0))
        ntiles.append(im)
        print("  %-12s %2d sub-object paths: single %d, merged %d  (areas %d / %d / %d px)"
              % (el, len(sub), len(single), len(areas) - len(single), areas[0], med, areas[-1]))
    if ntiles:
        W = max(t.width for t in ntiles); Hh = sum(t.height for t in ntiles)
        sh = Image.new("RGB", (W, Hh), (255, 255, 255)); yy = 0
        for t in ntiles:
            sh.paste(t, (0, yy)); yy += t.height
        sh.save(os.path.join(a.outdir, a.stem + "_subobjects.png"))
        print("saved", os.path.join(a.outdir, a.stem + "_subobjects.png"), sh.size)

    report = dict(coverage=rows, nucleons=nrows, probes=probes, failures=real,
                  note="probes: a click must select the structure it claims; sub-objects: one "
                       "path per child inside its parent group")
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(report, indent=1,
                                                                ensure_ascii=False))
    sys.exit(0 if not real else 1)


if __name__ == "__main__":
    main()
