#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sam_probe.py -- SAM / MobileSAM 探针：把「模型自动分割」跟 IR 声明的物理元素对账。

为什么有这个脚本（2026-10-15，作者问）：
  「为什么不采用语义分割，你试过吗？」「现在的分割不是分割物理轮廓？SAM 是分割物理轮廓的？」
  以前只有文字推断，没有读数。本脚本把这件事做成可复跑的实测。

实测结论（UPC 3D 位图 cand_s4192.png，2324x1268，1024px 输入，默认参数）：
  - SAM 切出来的是「视觉上一致的块」，不是物理轮廓。
  - 反应平面 S1 占画布 20.3%，是最大的物理元素，却 **98% 的像素没有任何 SAM 块覆盖**；
    换宽松参数也只降到 84%（最大块只覆盖板面的 8%）。
  - 两个核是同一种物理东西，因为配色不同：一个最大块覆盖 88%，
    另一个最大块只覆盖 1%（要 37 块才拼到 30%）。
  - 同一张图换一组阈值（0.88/0.95 -> 0.80/0.90）：N1 的最大块从 1% 跳到 90%。
    => 判据不稳定，不可审计；而 IR 引导的 ir_contour_seg.py 是 10/10 元素各 1 层。
  详细读数见 references/bitmap-to-vector.md §2.6。

依赖安装（本机 pip 的 TLS 是坏的，走不了 index；2026-10-15 实测可用的手装路径）：
  1) torch CPU 205 MB:
     https://download.pytorch.org/whl/cpu/torch-2.5.1%2Bcpu-cp310-cp310-win_amd64.whl
     依赖（纯 py，从 https://pypi.org/pypi/<pkg>/json 取 wheel URL）：
     filelock(<=4.1.0, py3.10) / sympy / mpmath / jinja2 / fsspec
     -> python -m pip install --no-index --no-deps <下好的 wheel>
  2) torchvision 0.20.1+cpu（automatic_mask_generator 要 torchvision.ops.boxes）
  3) timm==0.9.16（MobileSAM 要 timm.models.layers / timm.models.registry）
  4) git clone --depth 1 https://github.com/ChaoningZhang/MobileSAM.git
     权重 40 MB: https://huggingface.co/dhkim2810/MobileSAM/resolve/main/mobile_sam.pt

用法：
  python scripts/sam_probe.py --bitmap <图.png> --repo <MobileSAM目录> --ckpt mobile_sam.pt \
      --seg-dir <ir_contour_seg 输出目录> --outdir <dir> [--loose]
"""
from __future__ import annotations
import argparse, collections, io, json, os, sys, time


def die(msg, code=2):
    sys.stderr.write("[sam_probe] " + str(msg) + "\n")
    raise SystemExit(code)


def parse():
    p = argparse.ArgumentParser(description="SAM probe vs IR-declared physical elements")
    p.add_argument("--bitmap", required=True)
    p.add_argument("--engine", default="mobile_sam", choices=["mobile_sam", "sam"])
    p.add_argument("--repo", default="", help="MobileSAM 代码目录（--engine mobile_sam）")
    p.add_argument("--ckpt", default="", help="mobile_sam.pt / sam_vit_*.pth")
    p.add_argument("--seg-dir", default="", help="ir_contour_seg.py 的输出目录（含 elmap.npy + report.json）")
    p.add_argument("--outdir", default="")
    p.add_argument("--long-side", type=int, default=1024)
    p.add_argument("--points-per-side", type=int, default=0)
    p.add_argument("--pred-iou", type=float, default=0.0)
    p.add_argument("--stability", type=float, default=0.0)
    p.add_argument("--min-area", type=int, default=0)
    p.add_argument("--loose", action="store_true", help="宽松档：48/0.80/0.90/50")
    a = p.parse_args()
    if a.loose:
        a.points_per_side = a.points_per_side or 48
        a.pred_iou = a.pred_iou or 0.80
        a.stability = a.stability or 0.90
        a.min_area = a.min_area or 50
    else:
        a.points_per_side = a.points_per_side or 32
        a.pred_iou = a.pred_iou or 0.88
        a.stability = a.stability or 0.95
        a.min_area = a.min_area or 100
    if not a.outdir:
        a.outdir = os.path.join(os.path.dirname(os.path.abspath(a.bitmap)), "sam_probe")
    return a


def build_mask_generator(a):
    try:
        import torch
    except Exception as e:
        die("没有 torch：%s\n  按文件头的安装步骤手装（本机 pip 的 TLS 坏了，--index-url 一律失败）" % e)
    torch.set_num_threads(max(1, (os.cpu_count() or 4)))
    if a.engine == "mobile_sam":
        if not (a.repo and a.ckpt):
            die("--engine mobile_sam 需要 --repo <MobileSAM 目录> 与 --ckpt <mobile_sam.pt>")
        sys.path.insert(0, os.path.abspath(a.repo))
        try:
            from mobile_sam import sam_model_registry, SamAutomaticMaskGenerator
        except Exception as e:
            die("import mobile_sam 失败：%s\n  缺 torch / torchvision / timm 时按文件头装" % e)
        sam = sam_model_registry["vit_t"](checkpoint=a.ckpt)
    else:
        if not a.ckpt:
            die("--engine sam 需要 --ckpt <sam_vit_b_01ec64.pth>")
        try:
            from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
        except Exception as e:
            die("import segment_anything 失败：%s" % e)
        sam = sam_model_registry["vit_b"](checkpoint=a.ckpt)
    sam.eval()
    return sam, SamAutomaticMaskGenerator


def greedy_pieces(inter, sel, masks, A):
    """按交叠面积从大到小贪心，返回 (用了多少块, 实际覆盖比例)。"""
    covered = sel.copy()
    covered[:] = False
    used = 0
    acc = 0
    order = sorted(range(len(inter)), key=lambda i: -inter[i])
    for i in order:
        if inter[i] <= 0:
            break
        newly = int((masks[i] & sel & ~covered).sum())
        if newly <= 0:
            continue
        covered |= masks[i]
        acc += newly
        used += 1
        if acc >= 0.8 * A:
            break
    return used, (acc / max(A, 1))


def main():
    a = parse()
    import numpy as np
    import cv2
    bgr = cv2.imread(a.bitmap)
    if bgr is None:
        die("读不到位图 " + a.bitmap)
    H, W = bgr.shape[:2]
    s = a.long_side / float(max(H, W))
    small = cv2.resize(bgr, (int(round(W * s)), int(round(H * s))), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    os.makedirs(a.outdir, exist_ok=True)

    sam, AMG = build_mask_generator(a)
    amg = AMG(sam, points_per_side=a.points_per_side, pred_iou_thresh=a.pred_iou,
              stability_score_thresh=a.stability, crop_n_layers=0,
              min_mask_region_area=a.min_area)
    t0 = time.time()
    res = amg.generate(rgb)
    dt = time.time() - t0
    res.sort(key=lambda r: -r["area"])
    masks = np.stack([r["segmentation"] for r in res]).astype(bool) if res else np.zeros((0, h, w), bool)
    np.savez_compressed(os.path.join(a.outdir, "masks.npz"), masks=masks.astype(np.uint8))
    print("[sam_probe] engine=%s  settings pps=%d pIoU=%.2f stab=%.2f min_area=%d"
          % (a.engine, a.points_per_side, a.pred_iou, a.stability, a.min_area))
    print("[sam_probe] masks=%d  %.1fs  input %dx%d (orig %dx%d)" % (len(res), dt, w, h, W, H))

    rep = dict(bitmap=os.path.abspath(a.bitmap), engine=a.engine, long_side=a.long_side,
               settings=dict(points_per_side=a.points_per_side, pred_iou=a.pred_iou,
                             stability=a.stability, min_area=a.min_area),
               seconds=round(dt, 1), canvas=[w, h], n_masks=len(res),
               areas=[int(r["area"]) for r in res], union_frac=None, per_element=[], notes=[])
    if len(res):
        rep["union_frac"] = round(float(masks.any(0).sum()) / (w * h), 4)
        rep["largest_block_frac"] = round(float(masks[0].sum()) / (w * h), 4)

    # ---- 与 IR 元素对账（可选）----
    if a.seg_dir:
        el_path = os.path.join(a.seg_dir, "elmap.npy")
        rp_path = os.path.join(a.seg_dir, "report.json")
        if not (os.path.exists(el_path) and os.path.exists(rp_path)):
            die("--seg-dir 里缺 elmap.npy / report.json（先跑 tools/ir_contour_seg.py）")
        el = cv2.resize(np.load(el_path).astype(np.int32), (w, h), interpolation=cv2.INTER_NEAREST)
        ids = [e["id"] for e in json.load(io.open(rp_path, encoding="utf-8"))["elements"]]
        rows = []
        for k, eid in enumerate(ids):
            sel = (el == k)
            A = int(sel.sum())
            if A == 0:
                continue
            inter = [int((m & sel).sum()) for m in masks] if len(res) else []
            touch = int(sum(1 for c in inter if c >= max(20, 0.01 * A)))
            used, cov = greedy_pieces(inter, sel, masks, A) if len(res) else (0, 0.0)
            best = max(inter) if inter else 0
            rows.append(dict(id=eid, area_px=A, sam_touch=touch, pieces_for_80pct=used,
                             coverage_80pct=round(cov, 3), largest_block=int(best),
                             largest_block_frac=round(best / A, 3)))
            print("  %-5s A=%-8d SAM_touch=%-4d pieces=%-4d cover=%-6.2f largest=%-7d (%.0f%% of element)"
                  % (eid, A, touch, used, cov, best, 100.0 * best / A))
        rep["per_element"] = rows
        spans = collections.Counter()
        for m in masks:
            am = int(m.sum())
            hit = sorted([int((m & (el == k)).sum()) for k in range(len(ids))], reverse=True)
            hit = [x for x in hit if x > 0]
            spans[len([c for c in hit if c >= 0.10 * am])] += 1
        rep["masks_by_element_count"] = dict(sorted(spans.items()))
        # 板面未被任何块覆盖的比例（最能说明问题的那一个读数）
        for row in rows:
            k = ids.index(row["id"])
            sel = (el == k)
            unc = float((sel & ~masks.any(0)).sum()) / max(int(sel.sum()), 1)
            row["uncovered_frac"] = round(unc, 3)
        # 可视化：块边界 + 「没被任何块覆盖」的元素像素涂红
        vis = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).copy()
        for m in masks:
            cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(vis, cs, -1, (255, 0, 255), 1, cv2.LINE_AA)
        big = max(rows, key=lambda r: r["area_px"])["id"]
        sel = (el == ids.index(big)) & (~masks.any(0))
        vis[sel] = (0.42 * vis[sel] + 0.58 * np.array([0, 0, 255])).astype(np.uint8)
        cv2.imwrite(os.path.join(a.outdir, "vis_bound.png"), vis)
        rep["notes"].append("magenta = SAM block boundaries; red = pixels of %s covered by NO block" % big)

    json.dump(rep, io.open(os.path.join(a.outdir, "report.json"), "w", encoding="utf-8"), indent=1)
    print("[sam_probe] -> %s" % os.path.join(a.outdir, "report.json"))
    print("[sam_probe] 判据提醒：SAM 的块是「视觉一致的区域」，不是物理物体；"
          "要物理轮廓请用 IR 引导的 ir_contour_seg.py，把 SAM 只当边界细化提议器。")


if __name__ == "__main__":
    main()
