# -*- coding: utf-8 -*-
"""keep_gate —— 「上一版有 → 这一版没了」的形体删除闸门（作者 2026-10-13 追问「你怎么把入射的核子删了」）

为什么要有它
------------
sketch 阶梯的 B/C 档必须把「修改前的图」交给模型（`ladder_gate.py` 的 **L9**）。
但**给了图不等于保得住**：
简报里的「画面元素」枚举与「标签白名单」是**闭集合**，没被点名的形体会被静默删掉。
实测（fig_jet_quench）：A 档从风格图带进来的**两侧入射核子簇**（"Nuclear Fragments"），
在 B/C 里整块消失，而简报里没有一句话提到它们 —— 这是「只改错的」做不到的第二种形状。

它做什么
--------
不做语义识别，只做**机械对账**：
  残留 = 上一版有内容的像素  ∩  这一版在该处**附近也没有内容**
（"附近"用 --tol 像素的容差，避免一点点位移/发光就误报）
再把残留取连通域，逐个报 bbox / 面积 / 该处上一版的颜色族（文字 / 暖色 / 灰金属 / 冷色）。
颜色族只是**读数**，方便你 5 秒判「这团是核子还是文字」。

★ 还有第二条形状：**东西还在、但材质被换掉了**（作者 2026-10-13：「不许重画、不许换材质」）。
上一版粗糙的火焰状火球介质，下一版被重画成光滑的橙色球 —— 面积一点没少，上面的残留法报 0 处。
所以再加一段**质感读数**（`material_reading`）：在两版都有内容处铺网格，量每格的**平均色差**与
**对比度塌陷**，打印最差的三格坐标与配色。它是**读数不是判决**：同一轮换 seed 也能到 0.33，
真换材质 0.50–0.87（同一张图自比 0.000）。要当硬伤用加 `--material-strict`。

适用与不适用
------------
- **适用**：同一阶梯相邻两档（B ← A，C ← B）。它们按 L9/L10 就是「上一版 + 只改几条」，
  版式应当基本一致，所以残留里冒出来的都是「真被删掉的东西」。
- **不适用**：跨两档（A vs C2）、跨版式比较 —— 版式一挪，残留会大面积误报。
  标定：同图自比 0；B2→C2 0；A→B2 会大量报（A 档是风格图复刻，版式本来就不同）。
- 它是**诊断**不是判决：删对了的（例如风格图带进来的无关插图）也会被报出来。
  默认只出清单（rc=0）；要当硬伤用加 --strict。
"""
import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

BG_MAX_CH = 232
BG_SPREAD = 24


def load(p, size):
    im = Image.open(p).convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return im


def masks(im):
    a = np.asarray(im).astype(np.int16)
    mx = a.max(axis=2); mn = a.min(axis=2)
    bg = (mn > BG_MAX_CH) | ((mx > 245) & ((mx - mn) < BG_SPREAD))
    return ~bg, a


def family(a, m):
    """残留像素的颜色族读数（吃饱和度和亮度）"""
    px = a[m]
    if len(px) == 0:
        return "空"
    r, g, b = px[:, 0].astype(float), px[:, 1].astype(float), px[:, 2].astype(float)
    mx = px.max(axis=1).astype(float); mn = px.min(axis=1).astype(float)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    dark = float((lum < 0.25).mean())
    warm = float(((sat > 0.35) & (r > b)).mean())
    cool = float(((sat > 0.25) & (b >= r)).mean())
    grey = float(((sat <= 0.25) & (lum >= 0.25)).mean())
    tags = sorted([("文字/线稿", dark), ("暖色", warm), ("冷色", cool), ("灰金属", grey)],
                  key=lambda t: -t[1])
    return "%s %.0f%%" % (tags[0][0], tags[0][1] * 100)


def _hex(v):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(x)))) for x in v)


def material_reading(prev_im, new_im, mp, mn, grid=10, tol=6, cell_min=300):
    """「物体还在、但材质/质感被换掉了」的读数（作者 2026-10-13：不许重画、不许换材质）。

    为什么单开一个读数：`--strict` 那条只查「上一版有 → 这一版没了」（**存在性**）。
    实测的第二种形状是**东西还在、但换了材质** —— 上一版粗糙的火焰状火球介质，
    下一版被重画成光滑的橙色球（甚至换成灰金属球），形体面积一点没少，`--strict` 报 0 处。

    做法：在两版**都有内容**的地方铺 grid×grid 网格；每格若共享像素够多，就量
      ① 该格两版的**平均颜色距离**（0–1）；
      ② 该格的**局部对比度**（亮度 std）变化 —— 换材质常伴随纹理塌陷。
    换材质会表现为**一整片格子同时颜色漂移 + 对比度塌陷**，所以打印最差的三格坐标与配色。

    ★ 弱判据，别当判决：不同种子本来就会重画整张图。实测（fig_jet_quench）：
      同一轮不同 seed（材质没换）0.06–0.33；真换材质 0.50–0.87；同一张图自比 0.000。
    所以默认**只当读数**（漂移 >= 0.55 打软警），`--material-strict` 才当硬伤。
    """
    size = new_im.size
    apx = np.asarray(prev_im).astype(np.float64)
    anx = np.asarray(new_im).astype(np.float64)
    st = ndimage.generate_binary_structure(2, 2)
    shared = mp & ndimage.binary_dilation(mn, structure=st, iterations=tol)
    ys, xs = np.where(shared)
    if len(ys) == 0:
        return {"frac_shift": 0.0, "frac_flat": 0.0, "max_dcol": 0.0, "top": []}
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    lp = 0.299 * apx[..., 0] + 0.587 * apx[..., 1] + 0.114 * apx[..., 2]
    ln = 0.299 * anx[..., 0] + 0.587 * anx[..., 1] + 0.114 * anx[..., 2]
    h0, w0 = y1 - y0 + 1, x1 - x0 + 1
    cells = []
    for gy in range(grid):
        for gx in range(grid):
            cy0 = y0 + gy * h0 // grid; cy1 = y0 + (gy + 1) * h0 // grid
            cx0 = x0 + gx * w0 // grid; cx1 = x0 + (gx + 1) * w0 // grid
            sub = shared[cy0:cy1, cx0:cx1]
            cnt = int(sub.sum())
            if cnt < cell_min:
                continue
            px = apx[cy0:cy1, cx0:cx1][sub]
            nx = anx[cy0:cy1, cx0:cx1][sub]
            cells.append({
                "bbox": [cx0, cy0, cx1, cy1], "cnt": cnt,
                "d_col": float(np.linalg.norm(px.mean(axis=0) - nx.mean(axis=0))) / 255.0,
                "std_prev": float(lp[cy0:cy1, cx0:cx1][sub].std()),
                "std_new": float(ln[cy0:cy1, cx0:cx1][sub].std()),
                "prev_hex": _hex(px.mean(axis=0)), "new_hex": _hex(nx.mean(axis=0)),
            })
    tot = sum(c["cnt"] for c in cells) or 1
    return {
        "frac_shift": round(sum(c["cnt"] for c in cells if c["d_col"] > 0.18) / tot, 3),
        "frac_flat": round(sum(c["cnt"] for c in cells
                               if c["std_prev"] > 10 and c["std_new"] < 0.7 * c["std_prev"]) / tot, 3),
        "max_dcol": round(max((c["d_col"] for c in cells), default=0.0), 3),
        "top": sorted(cells, key=lambda c: -c["d_col"])[:3],
    }


def main():
    ap = argparse.ArgumentParser(description="上一版有 -> 这一版没了（形体删除对账）")
    ap.add_argument("--prev", required=True, help="修改前的图（上一轮的图）")
    ap.add_argument("--new", required=True, help="修改后的图（这一轮的图）")
    ap.add_argument("--tol", type=int, default=14,
                    help="容差像素：这一版在这么近的地方有东西就算「还在」")
    ap.add_argument("--min-frac", type=float, default=0.0015,
                    help="残留连通域最小面积（占画布比例）才算一条")
    ap.add_argument("--strict", action="store_true", help="有残留就当硬伤（rc=1）")
    ap.add_argument("--material-strict", action="store_true",
                    help="把「质感漂移 >= 0.55」也当硬伤（默认只作读数 + 软警）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--annot", default=None, help="标注图：把残留区域框在**这一版**上")
    a = ap.parse_args()

    base = Image.open(a.new).convert("RGB")
    size = base.size
    prev_im = load(a.prev, size)

    mp, apx = masks(prev_im)
    mn, _ = masks(base)

    # 这一版在附近有没有东西
    st = ndimage.generate_binary_structure(2, 2)
    near = ndimage.binary_dilation(mn, structure=st, iterations=a.tol)
    resid = mp & (~near)

    lab, n = ndimage.label(resid, structure=st)
    if n:
        sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    else:
        sizes = np.array([])
    area_min = a.min_frac * size[0] * size[1]

    regions = []
    for i in np.argsort(-sizes):
        idx = i + 1
        if sizes[i] < area_min:
            continue
        ys, xs = np.where(lab == idx)
        m = np.zeros_like(resid)
        m[ys, xs] = True
        regions.append({
            "area": int(sizes[i]),
            "area_frac": round(float(sizes[i]) / (size[0] * size[1]), 5),
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "kind_prev": family(apx, m),
        })

    print("=" * 74)
    print("keep_gate —— 「上一版有 → 这一版没了」形体删除对账")
    print("=" * 74)
    print("  上一版 : %s" % a.prev)
    print("  这一版 : %s" % a.new)
    print("  容差   : %d px（这一版在这么近处有东西就算「还在」）" % a.tol)
    print("  最小面积: %.3f%% 画布" % (a.min_frac * 100))
    print()
    print("  上一版有、这一版没了的地方（%d 处）：" % len(regions))
    for i, r in enumerate(regions, 1):
        x0, y0, x1, y1 = r["bbox"]
        print("   #%-2d x%d..%d y%d..%d   面积 %.2f%% 画布   上一版那里主要是：%s"
              % (i, x0, x1, y0, y1, r["area_frac"] * 100, r["kind_prev"]))
    if not regions:
        print("   （无）—— 上一版有东西的地方，这一版都还在")
    print()
    print("  ★ 诊断，不是判决：删对了的（如风格图带进来的无关插图）也会报。"
          "逐条判「该保留 / 该删」，判过的写进交付说明。")

    # ── 质感对账：东西还在、但材质被换掉了（作者 2026-10-13「不许重画、不许换材质」）──
    mat = material_reading(prev_im, base, mp, mn)
    print()
    print("  质感读数（两版都有内容处，格子平均色差 / 对比度塌陷）：")
    print("     漂移像素占比 %.3f   塌陷像素占比 %.3f   最差格色差 %.3f"
          % (mat["frac_shift"], mat["frac_flat"], mat["max_dcol"]))
    for i, c in enumerate(mat["top"], 1):
        print("     #%d x%d..%d y%d..%d  色差 %.3f  %s -> %s  对比度 %.0f -> %.0f"
              % (i, c["bbox"][0], c["bbox"][2], c["bbox"][1], c["bbox"][3], c["d_col"],
                 c["prev_hex"], c["new_hex"], c["std_prev"], c["std_new"]))
    if mat["frac_shift"] >= 0.55:
        print("  ⚠️ 漂移像素占比 %.3f >= 0.55 —— 很像「上一版的东西还在，但材质/质感被换掉了」"
              % mat["frac_shift"])
    print("  ★ 这条是读数不是判决（同一轮换 seed 也能到 0.33；真换材质 0.50–0.87）。")

    if a.annot and regions:
        ann = base.copy()
        d = ImageDraw.Draw(ann)
        for i, r in enumerate(regions, 1):
            x0, y0, x1, y1 = r["bbox"]
            d.rectangle([x0 - 3, y0 - 3, x1 + 3, y1 + 3], outline=(230, 0, 0), width=3)
            d.rectangle([x0 - 3, y0 - 3, x0 + 26, y0 + 20], fill=(255, 255, 255))
            d.text((x0 + 1, y0 - 1), "#%d" % i, fill=(200, 0, 0))
        ann.save(a.annot)
        print("\n  标注图 -> %s" % a.annot)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"prev": a.prev, "new": a.new, "tol": a.tol,
                       "min_frac": a.min_frac, "regions": regions, "material": mat},
                      f, ensure_ascii=False, indent=1)
        print("  报告 -> %s" % a.json)

    hard = (a.strict and regions) or (a.material_strict and mat["frac_shift"] >= 0.55)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
