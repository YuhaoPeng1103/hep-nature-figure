#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_3d_generic -- 通用 3D 闸门（图种无关）。作者 2026-10-04 要求（v4.1 起随 skill 发布）：

    「一定要是 3D」

为什么不复用别的东西
    · skill 的 scripts/check_3d.py 与工作区 tools/check_3d.py 都把搜索窗
      **硬编码在动量轮那张图**上（WHEEL = (118,170,34,68) mm），换图就废。
    · tools/check_render_mode.py 自己写着它判不了「扁平 vs 3D」。
    · 墨色指标（ink_colors）量的是**细节密度 + 文字量**，不是渲染方式 ——
      反例：3D 位图 collective_flow/gen/chosen.png = 215，肉眼看着平的
      figures/out/figC_upc.png = 377。
    所以这里有 4 条**直接量像素**的判据，而且**不用窗**（主体与地面都由像素自己找）。

判据（HARD = 非零退出）
    3D0 主体存在      最大彩色形体 >= 0.3% 画布
    3D1 地面/板面     最大「浅灰面」连通块 >= 3% 画布        （IR 声明有板面时 HARD）
    3D2 接触阴影      板面内比板面中位亮度暗 6% 的像素 >= 8% 板面，
                      且至少一块 >= 0.08% 画布            （IR 声明有板面时 HARD）
    3D3 体积明暗      主体最亮点偏离几何中心 > 0.08 半轴    （总是 HARD）
    读数（不判死）：limb 变暗、外发光、平滑渐变占比、灰面占比

    ★ 3D1/3D2 需要知道「这张图该不该有板面」。IR 里有
      elements[].name 含 板/平面/网格/plane，或 composition.地面，就算「有板面」。
      也可用 --expect-plane yes|no 直接指定。

回归标定（改过这里就要重跑）
    应当 PASS  fig_qgp_3d/gen/sketch_s324_clean.png   (第 2 轮，有板、有接触阴影)
    应当 PASS  fig_upc_3d/gen/chosen.png
    应当 FAIL  fig_qgp_3d/gen/sketch_s301_clean.png   (第 1 轮，「2D 贴纸」)
    应当 FAIL  figures/out/figC_upc.png               (扁平稿)
    --expect-plane no 时：collective_flow/gen/chosen.png 应 PASS（无板，但火球有体积明暗）
\u2605 \u5df2\u77e5\u9650\u5236\uff1a3D1/3D2 \u53ea\u8ba4\u300c\u6d45\u7070\u300d\u677f\u9762\uff1b\u677f\u9762\u7528\u6df1\u8272/\u5f69\u8272\u8868\u8fbe\u7684\u56fe\n      \uff08\u5982\u98ce\u683c\u4e66 T3-01 / T3-34\uff09\u4f1a\u88ab\u8bef\u5224 \u2192 \u7528 --expect-plane no \u53ea\u67e5 3D3\uff08\u4f53\u79ef\u660e\u6697\uff09\u3002\n      \u6362\u56fe\u5148\u770b\u8bfb\u6570\u518d\u5b9a\u3002\n"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


TH_PLANE_FRAC = 0.030     # 浅灰面 >= 3% 画布
TH_SHADOW_FRAC = 0.080    # 板面内「暗于中位 6%」的像素 >= 8% 板面
TH_SHADOW_BLOB = 0.0008   # 至少一块阴影 >= 0.08% 画布
TH_OFFCENTRE = 0.08       # 主体最亮点偏离几何中心 > 0.08 半轴
TH_BODY = 0.003           # 主体 >= 0.3% 画布


def read_ir_plane(ir):
    try:
        import yaml
        doc = yaml.safe_load(io.open(ir, encoding="utf-8").read())
    except Exception:
        return None, "IR 读不了"
    if not isinstance(doc, dict):
        return None, "IR 不是 mapping"
    comp = doc.get("composition") or {}
    if isinstance(comp, dict):
        g = comp.get("\u5730\u9762") or comp.get("ground") or comp.get("slab")
        if g:
            s = str(g)
            if any(k in s for k in ("\u65e0", "none", "None", "no ")):
                return False, "composition.\u5730\u9762 = %s" % s[:40]
            return True, "composition.\u5730\u9762 = %s" % s[:40]
    for el in (doc.get("elements") or []):
        if not isinstance(el, dict):
            continue
        nm = str(el.get("name", "")) + str(el.get("primitive", ""))
        if any(k in nm for k in ("\u677f", "\u5e73\u9762", "\u7f51\u683c", "plane", "grid", "slab")):
            return True, "elements[%s].name \u542b \u677f/\u5e73\u9762/\u7f51\u683c" % el.get("id")
    return None, "\u672a\u58f0\u660e"


def main():
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="通用 3D 闸门（见文件头）")
    ap.add_argument("image")
    ap.add_argument("--ir", default=None)
    ap.add_argument("--expect-plane", choices=("auto", "yes", "no"), default="auto")
    ap.add_argument("--json", default=None)
    ap.add_argument("--annot", default=None)
    a = ap.parse_args()

    from PIL import Image, ImageDraw
    import cv2

    rep = {"checks": [], "fails": [], "warns": [], "readings": {}}

    def ck(ok, label, detail, hard=True):
        rep["checks"].append({"ok": bool(ok), "label": label, "detail": detail, "hard": bool(hard)})
        print("  [%s] %-50s %s" % ("ok  " if ok else ("FAIL" if hard else "warn"), label, detail))
        if not ok:
            (rep["fails"] if hard else rep["warns"]).append("%s (%s)" % (label, detail))

    im = Image.open(a.image).convert("RGB")
    arr = np.asarray(im).astype(np.float64)
    H, W = arr.shape[:2]
    L = (0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]) / 255.0
    mx = arr.max(2); mn = arr.min(2); sat = mx - mn
    print("check_3d_generic  %s  (%dx%d)" % (a.image, W, H))

    # 期望：这张图该不该有板面
    plane_want, plane_src = None, "(--expect-plane)"
    if a.expect_plane == "yes":
        plane_want = True
    elif a.expect_plane == "no":
        plane_want = False
    elif a.ir:
        plane_want, plane_src = read_ir_plane(a.ir)
    print("  板面期望：%s  %s" % (plane_want, plane_src))
    rep["readings"]["expect_plane"] = plane_want

    # ── 3D0 主体 ──
    col = ((sat > 40) & (mx > 90)).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(col, 8)
    print("\n3D0 主体")
    if n < 2:
        ck(False, "3D0 找到彩色主体", "画布里没有 >40 饱和度的形体")
        body = None
    else:
        j = 1 + int(np.argmax(st[1:, 4]))
        bfrac = st[j, 4] / float(W * H)
        body = {"bbox": (int(st[j, 0]), int(st[j, 1]), int(st[j, 2]), int(st[j, 3])),
                "c": (float(cen[j][0]), float(cen[j][1])), "frac": float(bfrac),
                "mask": (lab == j)}
        ck(bfrac >= TH_BODY, "3D0 最大彩色主体 >= 0.3% 画布",
           "%.3f%%   bbox x%d..%d y%d..%d" % (bfrac * 100, body["bbox"][0],
                                              body["bbox"][0] + body["bbox"][2],
                                              body["bbox"][1], body["bbox"][1] + body["bbox"][3]))
        rep["readings"]["body_frac"] = round(bfrac, 4)

    # ── 3D1 地面 / 板面 ──
    gray = ((sat < 40) & (L > 0.50) & (L < 0.97)).astype(np.uint8)
    print("\n3D1 地面 / 板面（浅灰、低饱和、成一大块）")
    n2, l2, s2, c2 = cv2.connectedComponentsWithStats(gray, 8)
    plane = None
    if n2 >= 2:
        i = 1 + int(np.argmax(s2[1:, 4]))
        pfrac = s2[i, 4] / float(W * H)
        plane = {"mask": (l2 == i), "frac": float(pfrac),
                 "bbox": (int(s2[i, 0]), int(s2[i, 1]), int(s2[i, 2]), int(s2[i, 3]))}
        rep["readings"]["plane_frac"] = round(pfrac, 4)
        ck(pfrac >= TH_PLANE_FRAC, "3D1 有一块浅灰面 >= 3% 画布",
           "%.2f%%  bbox x%d..%d y%d..%d" % (pfrac * 100, plane["bbox"][0],
                                             plane["bbox"][0] + plane["bbox"][2],
                                             plane["bbox"][1], plane["bbox"][1] + plane["bbox"][3]),
           hard=(plane_want is not False))
    else:
        rep["readings"]["plane_frac"] = 0.0
        ck(False, "3D1 有一块浅灰面 >= 3% 画布", "找不到任何浅灰面",
           hard=(plane_want is not False))
        if plane_want is False:
            rep["warns"].append("3D1 无板面（IR 已声明无板面，符合）")

    # ── 3D2 接触阴影 ──
    print("\n3D2 接触阴影（物体坐在板面上，把板压暗）")
    annot = im.copy()
    dr = ImageDraw.Draw(annot)
    if plane is not None:
        pmed = float(np.median(L[plane["mask"]]))
        sh = (plane["mask"] & (L < pmed * 0.94))
        sf = float(sh.sum()) / max(1.0, float(plane["mask"].sum()))
        nb, lb2, sb2, cb2 = cv2.connectedComponentsWithStats(sh.astype(np.uint8), 8)
        blobs = sorted([int(sb2[k, 4]) for k in range(1, nb)], reverse=True) if nb > 1 else []
        big = (blobs[0] / float(W * H)) if blobs else 0.0
        rep["readings"]["plane_median_L"] = round(pmed, 3)
        rep["readings"]["shadow_frac"] = round(sf, 4)
        rep["readings"]["shadow_bigblob"] = round(big, 4)
        if a.annot:
            _cn = cv2.findContours(plane["mask"].astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
            cont = _cn[-2]
            for c in cont:
                dr.line([tuple(q[0]) for q in c] + [tuple(c[0][0])], fill=(0, 120, 255), width=4)
            for k in range(1, nb):
                x0, y0, w0, h0 = sb2[k, 0], sb2[k, 1], sb2[k, 2], sb2[k, 3]
                if sb2[k, 4] / float(W * H) >= TH_SHADOW_BLOB:
                    dr.rectangle([x0, y0, x0 + w0, y0 + h0], outline=(255, 0, 0), width=4)
        ck(sf >= TH_SHADOW_FRAC and big >= TH_SHADOW_BLOB, "3D2 板面上有接触阴影",
           "暗像素 %.1f%% 板面（需 >=%.0f%%），最大暗块 %.3f%% 画布（需 >=%.2f%%）"
           % (sf * 100, TH_SHADOW_FRAC * 100, big * 100, TH_SHADOW_BLOB * 100),
           hard=(plane_want is not False))
        if plane_want is False and (sf < TH_SHADOW_FRAC or big < TH_SHADOW_BLOB):
            rep["warns"].append("3D2 无接触阴影（IR 声明无板面，符合）")
    else:
        ck(False, "3D2 板面上有接触阴影", "没有板面可查", hard=(plane_want is not False))

    # ── 3D3 体积明暗 ──
    print("\n3D3 体积明暗（高光偏离几何中心）")
    offc = 0.0; limb = 0.0; glow = 0.0
    if body is not None:
        bm = body["mask"]
        cx, cy = body["c"]
        x0, y0, bw, bh = body["bbox"]
        A, B = bw / 2.0, bh / 2.0
        Lb = np.where(bm, L, -1.0)
        k = int(np.argmax(Lb)); hy, hx = divmod(k, W)
        offc = math.hypot(hx - cx, hy - cy) / max(1.0, 0.5 * (A + B))
        mids, edges = [], []
        for th in np.linspace(0.0, 2 * math.pi, 72, endpoint=False):
            rmax, r = 0.0, 0.0
            while r <= 1.2 * max(A, B):
                px, py = int(cx + math.cos(th) * r), int(cy + math.sin(th) * r)
                if 0 <= px < W and 0 <= py < H and bm[py, px]:
                    rmax = r
                elif rmax > 0 and r > rmax + 2:
                    break
                r += 1.0
            if rmax > 10:
                for f, acc in ((0.45, mids), (0.9, edges)):
                    px, py = int(cx + math.cos(th) * f * rmax), int(cy + math.sin(th) * f * rmax)
                    if 0 <= px < W and 0 <= py < H:
                        acc.append(L[py, px])
        if mids and edges:
            limb = float(np.mean(mids) - np.mean(edges))
        # 外发光：主体外一圈暖色弥散
        yy, xx = np.mgrid[0:H, 0:W]
        dist = np.hypot(xx - cx, yy - cy)
        ring = (dist > 1.02 * max(A, B)) & (dist < 1.35 * max(A, B))
        warm = (arr[:, :, 0] > 120) & (arr[:, :, 0] - arr[:, :, 2] > 40) & (sat > 25)
        glow = float((ring & warm).sum()) / max(1.0, float(ring.sum()))
        dr.ellipse([hx - 12, hy - 12, hx + 12, hy + 12], outline=(0, 200, 0), width=5)
        dr.rectangle([x0, y0, x0 + bw, y0 + bh], outline=(180, 0, 180), width=4)
        dr.line([cx, cy, hx, hy], fill=(0, 200, 0), width=4)
        rep["readings"].update({"offcentre": round(offc, 3), "limb": round(limb, 4),
                                "glow": round(glow, 4)})
        ck(offc >= TH_OFFCENTRE, "3D3 最亮点偏离几何中心 > 0.08 半轴",
           "偏离 %.3f 半轴（高光偏移 = 有法线场，不是纯热芯）" % offc)
        ck(limb >= -0.02, "3D3b 边缘不比中部更亮（limb 变暗或至少不反号）",
           "limb = %+.3f" % limb, hard=False)
        ck(glow > 0.02, "3D4 主体外有发光弥散（高温对象）", "ring 暖色占比 %.3f" % glow, hard=False)

    # ── 平滑渐变占比（读数） ──
    gx = cv2.Sobel(L, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(L, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    grad_frac = float(((mag > 0.02) & (mag < 0.35)).mean())
    edge_frac = float((mag >= 0.35).mean())
    rep["readings"].update({"grad_frac": round(grad_frac, 4), "edge_frac": round(edge_frac, 4),
                            "gray_frac": round(float(gray.mean()), 4)})
    print("\n读数：平滑渐变 %.3f   硬边 %.3f   灰面总占比 %.3f"
          % (grad_frac, edge_frac, float(gray.mean())))

    if a.annot:
        annot.save(a.annot)
        print("标注图 -> %s" % a.annot)
    print("\n读数：%s" % json.dumps(rep["readings"], ensure_ascii=False))
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2))
        print("报告 -> %s" % a.json)
    if rep["fails"]:
        print("\n结论：3D 闸门未过 —— 这张图读起来不是「立体渲染」。硬伤：")
        for f in rep["fails"]:
            print("   - %s" % f)
        return 1
    print("\n结论：3D 闸门通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
