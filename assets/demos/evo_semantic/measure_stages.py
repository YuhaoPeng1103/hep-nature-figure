# -*- coding: utf-8 -*-
"""measure_stages.py —— 四阶段演化链的几何/颜色【量测】（不目测）

用途：闸口①/② 里「人答」的那几条，用这个脚本出数字。
量的是：阶段横向位置与顺序、箭头方向、阶段内笔画是否连成一体（=相互重叠）、
各阶段颜色饱和度（冷/热）、标签是否落在对应阶段正下方。

用法：python measure_stages.py <图.png> [--stage4-round]
"""
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage


def analyze(path, verbose=True):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    H, W = a.shape[:2]
    m = a.mean(2) < 240
    L, n = ndimage.label(m, np.ones((3, 3)))
    for i in range(1, n + 1):                     # 去掉裁外框残留的孤立杂点
        if (L == i).sum() < 20:
            m[L == i] = False
    ys, xs = np.where(m)
    rows = m.sum(1)
    # 形状带 / 标签带：内容行里的最大空段
    empty = [y for y in range(ys.min(), ys.max() + 1) if rows[y] == 0]
    if empty:
        # 取最长的连续空段
        runs, s = [], empty[0]
        for i in range(1, len(empty)):
            if empty[i] != empty[i - 1] + 1:
                runs.append((s, empty[i - 1])); s = empty[i]
        runs.append((s, empty[-1]))
        gap = max(runs, key=lambda r: r[1] - r[0])
    else:
        gap = None
    shape_end = (gap[0] - 1) if gap else ys.max()
    label_start = (gap[1] + 1) if gap else ys.min()

    def comps(mask, minpx):
        Lc, nc = ndimage.label(mask, np.ones((3, 3)))
        out = []
        for i in range(1, nc + 1):
            yy, xx = np.where(Lc == i)
            if len(yy) < minpx:
                continue
            out.append(dict(box=(int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())),
                            px=len(yy), cx=float(xx.mean())))
        return sorted(out, key=lambda d: d["cx"])

    band = np.zeros_like(m); band[ys.min():shape_end + 1] = m[ys.min():shape_end + 1]
    cs = comps(band, 800)
    stages = [c for c in cs if c["px"] > 12000]
    arrows = [c for c in cs if 1200 < c["px"] <= 12000]
    res = dict(size=(W, H), content_box=(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
               stages=[], arrows=[], labels=[], ok={})
    for d in stages:
        res["stages"].append(dict(cx=d["cx"], box=d["box"]))
    res["ok"]["1_阶段x递增"] = all(res["stages"][i]["cx"] < res["stages"][i + 1]["cx"]
                                  for i in range(len(res["stages"]) - 1))
    for d in arrows:
        bx0, by0, bx1, by1 = d["box"]
        sub = band[by0:by1 + 1, bx0:bx1 + 1]
        prof = sub.sum(0).astype(float)
        n_ = len(prof); t = max(1, n_ // 3)
        left, right = float(prof[:t].max()), float(prof[-t:].max())
        xa = float(np.argmax(prof)) / max(1, n_)
        res["arrows"].append(dict(box=d["box"], left=left, right=right, xmax=xa,
                                  rightward=bool(right > left and xa > 0.55)))
    res["ok"]["2_箭头全向右"] = all(d["rightward"] for d in res["arrows"]) and len(res["arrows"]) == 3
    # 阶段3/4 内部是否连成一体（=相互重叠）
    if len(stages) >= 4:
        s3, s4 = stages[2], stages[3]
        w1 = stages[0]["box"][2] - stages[0]["box"][0] + 1
        w3 = s3["box"][2] - s3["box"][0] + 1
        res["overlap_width_px"] = 2 * w1 - w3
        res["ok"]["4_阶段3部分重叠"] = 0 < res["overlap_width_px"] < w1
        bx = s4["box"]
        ix0 = bx[0] + int((bx[2] - bx[0]) * 0.22); ix1 = bx[2] - int((bx[2] - bx[0]) * 0.22)
        iy0 = bx[1] + int((bx[3] - bx[1]) * 0.22); iy1 = bx[3] - int((bx[3] - bx[1]) * 0.22)
        c4 = comps(band[iy0:iy1 + 1, ix0:ix1 + 1], 100)
        res["n_stage4_inner_blobs"] = len(c4)
        res["ok"]["5_阶段4核子相互重叠"] = len(c4) < 4
    # 阶段2 内部连通域数
    if len(stages) >= 2:
        s2 = stages[1]
        c2 = comps(band[:, s2["box"][0]:s2["box"][2] + 1], 800)
        res["n_stage2_blobs"] = len(c2)
        res["ok"]["3_阶段2椭圆相互重叠"] = len(c2) == 1
    # 颜色
    def sat_of(x0, x1, y0_, y1_):
        sub = a[y0_:y1_ + 1, x0:x1 + 1]; mm = m[y0_:y1_ + 1, x0:x1 + 1]
        if mm.sum() < 50:
            return None, None
        px = sub[mm]; mx, mn = px.max(1), px.min(1)
        return float(((mx - mn) / np.maximum(mx, 1e-6)).mean()), px.mean(0)
    res["stage_sat"] = []
    for d in stages:
        s, rgb = sat_of(d["box"][0], d["box"][2], d["box"][1], d["box"][3])
        res["stage_sat"].append(s)
    if len(res["stage_sat"]) >= 4:
        cold = max(res["stage_sat"][:3]); hot = res["stage_sat"][3]
        res["ok"]["6_冷热分明"] = bool(hot > 0.4 and cold < 0.2)
    # 标签
    lab = np.zeros_like(m); lab[label_start:ys.max() + 1] = m[label_start:ys.max() + 1]
    tl = comps(lab, 25)
    groups, cur = [], None
    for d in tl:
        if cur is None or d["box"][0] - cur[-1]["box"][2] > 70:
            groups.append([d]); cur = groups[-1]
        else:
            cur.append(d)
    for g in groups:
        x0 = min(d["box"][0] for d in g); x1 = max(d["box"][2] for d in g)
        cx = (x0 + x1) / 2
        res["labels"].append(dict(cx=cx, box=(x0, x1)))
    if len(groups) == len(stages):
        res["ok"]["7_标签对齐"] = all(s["box"][0] <= l["cx"] <= s["box"][2]
                                     for s, l in zip(stages, res["labels"]))
    if verbose:
        print("图 %s  %dx%d  内容 bbox=%s" % (path.split("\\")[-1], W, H, res["content_box"]))
        print("  阶段横向中心:", ["%.0f" % s["cx"] for s in res["stages"]])
        for i, d in enumerate(res["arrows"], 1):
            print("  箭头%d box=%s 前1/3厚=%.0f 后1/3厚=%.0f 最厚处x=%.2f → %s"
                  % (i, d["box"], d["left"], d["right"], d["xmax"],
                     "向右" if d["rightward"] else "可疑"))
        print("  阶段2 连通域=%s  阶段3 交叠=%s px  阶段4 内部连通域=%s"
              % (res.get("n_stage2_blobs"), res.get("overlap_width_px"),
                 res.get("n_stage4_inner_blobs")))
        print("  各阶段平均饱和度:", ["%.3f" % s for s in res["stage_sat"]])
        print("  标签组:", ["%.0f" % l["cx"] for l in res["labels"]])
        print("  ── 闸口人答题: " + "  ".join(
            "%s=%s" % (k, "是" if v else "否") for k, v in sorted(res["ok"].items())))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    a = ap.parse_args()
    analyze(a.image)