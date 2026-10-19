# -*- coding: utf-8 -*-
"""svg_repro_check.py —— 「矢量图回渲染 vs 源位图」的复现度对账。

单一读数不够：MAE 会被大片平背景稀释，>32 的像素才看得出「哪儿画歪了」。
所以固定给四个数 + 逐元素拆账 + 最差 32x32 方格。

用法:
  python tools/svg_repro_check.py --svg out.svg --png src.png \
         [--elmap seg/elmap.npy] [--el-names A,B,...] [--json r.json] \
         [--diff out_diff.png] [--side out_side.png]

★ --elmap 是 ir_contour_seg.py 的逐像素标签；-1 = 没归进任何元素的背景。
   逐元素读数告诉你「总量变差是哪个元素变差」，否则只能瞎猜。
"""
import argparse, io, json, os
import numpy as np


def render(svg, w, h):
    import cairosvg
    png = cairosvg.svg2png(url=svg, output_width=w, output_height=h)
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), np.float32)


def metrics(a, b, mask=None):
    d = np.abs(a - b)
    if mask is not None:
        d = d[mask]
        if d.size == 0:
            return None
        d = d.reshape(-1)
        mae = float(d.mean())
        p8 = float((d > 8).mean() * 100)
        p32 = float((d > 32).mean() * 100)
        mse = float((d ** 2).mean())
        return dict(px=int(d.size), mae=round(mae, 3), gt8=round(p8, 2),
                    gt32=round(p32, 2), psnr=round(10 * np.log10(255.0 ** 2 / max(mse, 1e-9)), 2))
    per = d.mean(axis=2)
    mae = float(per.mean())
    mse = float((per ** 2).mean())
    return dict(px=int(per.size), mae=round(mae, 3),
                gt8=round(float((per > 8).mean() * 100), 2),
                gt32=round(float((per > 32).mean() * 100), 2),
                psnr=round(10 * np.log10(255.0 ** 2 / max(mse, 1e-9)), 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--elmap", default="")
    ap.add_argument("--el-names", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--diff", default="")
    ap.add_argument("--side", default="")
    ap.add_argument("--tile", type=int, default=32)
    a = ap.parse_args()

    from PIL import Image
    src = np.asarray(Image.open(a.png).convert("RGB"), np.float32)
    H, W = src.shape[:2]
    ren = render(a.svg, W, H)
    if ren.shape[:2] != src.shape[:2]:
        import cv2
        ren = cv2.resize(ren, (W, H), interpolation=cv2.INTER_AREA)

    out = {"svg": a.svg, "png": a.png, "size": [W, H],
           "all": metrics(src, ren)}

    el = None
    names = [x for x in a.el_names.split(",") if x]
    if a.elmap:
        el = np.load(a.elmap)
        if el.shape[:2] != (H, W):
            import cv2
            el = cv2.resize(el.astype(np.int32), (W, H), interpolation=cv2.INTER_NEAREST)
    if el is not None:
        per = []
        ids = sorted(int(v) for v in np.unique(el))
        for v in ids:
            nm = names[v] if 0 <= v < len(names) else ("background" if v < 0 else "#%d" % v)
            m = el == v
            r = metrics(src, ren, mask=m)
            if r:
                r["id"] = nm
                r["idx"] = v
                per.append(r)
        out["per_element"] = per

    # 最差方格
    per = np.abs(src - ren).mean(axis=2)
    t = max(8, a.tile)
    gh, gw = H // t, W // t
    tiles = []
    for gy in range(gh):
        for gx in range(gw):
            blk = per[gy * t:(gy + 1) * t, gx * t:(gx + 1) * t]
            tiles.append((float(blk.mean()), gx * t, gy * t))
    tiles.sort(reverse=True)
    out["worst_tiles"] = [{"mae": round(v, 2), "x": x, "y": y} for v, x, y in tiles[:12]]

    print("=" * 72)
    print("回渲染复现度  %s" % os.path.basename(a.svg))
    print("  全图   MAE %.3f | >8 %.2f%% | >32 %.2f%% | PSNR %.2f dB"
          % (out["all"]["mae"], out["all"]["gt8"], out["all"]["gt32"], out["all"]["psnr"]))
    if el is not None:
        print("  %-14s %9s %8s %8s %8s" % ("元素", "像素", "MAE", ">8%", ">32%"))
        for r in out["per_element"]:
            print("  %-14s %9d %8.3f %8.2f %8.2f"
                  % (r["id"], r["px"], r["mae"], r["gt8"], r["gt32"]))
    print("  最差方格(32px): " + ", ".join("(%d,%d)=%.1f" % (d["x"], d["y"], d["mae"])
                                            for d in out["worst_tiles"][:6]))

    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.diff or a.side:
        import cv2
        vis = np.clip(np.abs(src - ren) * 3.0, 0, 255).astype(np.uint8)
        vis = cv2.applyColorMap(cv2.cvtColor(vis, cv2.COLOR_RGB2GRAY), cv2.COLORMAP_INFERNO)
        if a.diff:
            cv2.imwrite(a.diff, vis)
        if a.side:
            mid = np.full((H, 8, 3), 255, np.uint8)
            cv2.imwrite(a.side, np.hstack([cv2.cvtColor(src.astype(np.uint8), cv2.COLOR_RGB2BGR),
                                           mid,
                                           cv2.cvtColor(ren.astype(np.uint8), cv2.COLOR_RGB2BGR)]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
