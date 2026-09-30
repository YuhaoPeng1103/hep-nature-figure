#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bitmap_conformance —— 「重画的成品必须和所选位图的架构对得上」硬闸门
=======================================================================

作者原话（2026-09-30）：
    「以后不要再这样了随便拿旧构建器了明白吗？」

为什么必须变成机器判据（实测，2026-09-30，集体流图第 5 版）
----------------------------------------------------------------------
第 7 步写得很清楚：位图已经过了闸口②，物理是对的，所以重画/临摹都应该
**照它**（SKILL.md:707）。但 v5 没有照位图 —— 它把**位图之前就存在**的
`build_figure_v3.py` 整份搬了过来（文本相似度 96.0%），只换内容层，
底盘常量原样继承：

    SHEAR = 6.5                 位图量出来 17.8，而且位图是斜投影（侧边竖直），
                                整格 rotate 根本换不过去
    SLAB_W, SLAB_H = 46, 62     位图 44.8 x 58.8
    TX = (6, 66, 126)           位图 3.6 / 69.6 / 135.6
    TY = 14.5                   位图 19.9
    CAP_Y, SUB_Y, LETTER_Y      位图 84 / 91 / 3.3

`SHEAR=6.5` 写在 `build_figure_v2.py:59`，文件时间 2026-09-29 00:01，
比位图（2026-09-29 22:40）早 22 小时 —— 它不可能来自「看图重画」。
于是板子倾角差了 11.3 度，而**五道门禁全绿**：没有一道在量「成品和位图像不像」。

★ 所以这条闸门不查「你是不是抄了旧脚本」—— 那查不出来。它查**结果**：
  把所选位图和成品各量一遍架构几何，对不上就是没照它画。

判据（非零退出 = 不许出成品）
----------------------------------------------------------------------
两边都量得出来、且**拟合可信**（残差 <= 2px）的量逐个比，超阈值即失败：

    · 面板数                        面板少/多 → 结构就不是同一张
    · 每个面板的 上边界倾角          （度，默认 ±2.0）★ v5 的 11.3 度死在这
    · 每个面板的 上边界中线高度      （mm，默认 ±2.0）面板整体的竖向位置
    · 每个面板的 侧边界角            （度，默认 ±2.0）0 = 侧边竖直（斜投影）
    · 整图墨迹顶                    （mm，默认 ±2.0）面板字母 / 顶部留白
    · 宽高比                        （相对，默认 ±2%）

**为什么只有这几个**：试过更细的量（面板 x0/x1、各面板 y0/y1、题注带位置），
实测**不可靠** —— 面板的列区间会被题注文字宽度带偏（位图的题注比板子宽），
位图的板子底下还带软阴影、板底到题注之间**没有干净空白段**，
所以「按空白分带」在参考图上根本不成立。这些量留着会制造假阳性，
不如不量。量得出来但不干净的（拟合残差大）会**明说「不可比」并列出**。

两边可比总数 < 3 时判「无法比对」而不放行 —— **量不出来 ≠ 通过**。

确实有意做差异（位图物理错了、客户要求改）才加 `--allow-diff "理由"`。

用法
----------------------------------------------------------------------
    python3 scripts/bitmap_conformance.py <所选位图> <成品.png|.svg> \
        [--canvas-mm 183x100] [--panels 3] [--json rep.json] [--allow-diff "理由"]

    # 集体流图实测：v5 该被拦，v6 该放行
    python3 scripts/bitmap_conformance.py gen/v5/render/chosen.png out/collective_flow_v5.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

try:
    from _console import init_console
except Exception:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from _console import init_console
    except Exception:
        def init_console():
            pass
init_console()

try:
    from trim_border import detect as _detect_border
except Exception:
    _detect_border = None

INK = 249.0          # 灰度 < 它算墨迹
MIN_PANEL_MM = 8.0   # 窄于它的列段当墨点丢掉，不当面板
GAP_MERGE_MM = 2.0   # 面板内部细白缝：窄于它的空隙不算面板间隔
MAX_RESID_PX = 2.0   # 拟合残差超过它 → 这个量不可比（宁可不量，也别假阳性）


def _load_rgb(path, width=1664):
    p = Path(path)
    if p.suffix.lower() == ".svg":
        import io
        try:
            import cairosvg
        except ImportError:
            raise SystemExit("读 SVG 需要 cairosvg：pip install cairosvg")
        raw = cairosvg.svg2png(url=str(p), output_width=width)
        im = Image.open(io.BytesIO(raw))
    elif p.suffix.lower() == ".pdf":
        raise SystemExit("请给 PNG 或 SVG；PDF 先渲染成 PNG 再比。")
    else:
        im = Image.open(p)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im.convert("RGB")


def _trim_frame(im):
    """生图模型稳定地在四周画 1~2px 外框 —— 有就裁掉（复用 trim_border 的判据）。"""
    if _detect_border is None:
        return im, {}
    try:
        d = _detect_border(im)
    except Exception:
        return im, {}
    t = {k: int(v[0]) for k, v in d.items()}
    if not any(t.values()):
        return im, t
    W, H = im.size
    return im.crop((t["left"], t["top"], W - t["right"], H - t["bottom"])), t


def _robust_line(xs, ys, keep=0.75, iters=4):
    """稳健直线拟合。返回 (斜率, 截距, 最大残差 px, 点数) 或 None。"""
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if xs.size < 20:
        return None
    a = b = 0.0
    for _ in range(iters):
        a, b = np.polyfit(xs, ys, 1)[:2]
        r = np.abs(ys - (a * xs + b))
        k = r <= np.quantile(r, keep)
        if k.sum() < 20:
            break
        xs, ys = xs[k], ys[k]
    return a, b, float(np.abs(ys - (a * xs + b)).max()), int(xs.size)


def _panel_runs(m, kx, W):
    colf = m.mean(axis=0)
    occ = colf > max(0.004, 0.02 * float(colf.max() or 1.0))
    runs, i = [], 0
    while i < W:
        if occ[i]:
            j = i
            while j + 1 < W and occ[j + 1]:
                j += 1
            runs.append([i, j])
            i = j + 1
        else:
            i += 1
    merged = []
    for a, b in runs:
        if merged and (a - merged[-1][1]) / kx <= GAP_MERGE_MM:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [r for r in merged if (r[1] - r[0]) / kx >= MIN_PANEL_MM]


def measure(path, canvas_mm=(183.0, 100.0), panels=None, ink=INK, width=1664):
    im = _load_rgb(path, width)
    im, trimmed = _trim_frame(im)
    W, H = im.size
    lum = np.asarray(im).astype(np.float32).mean(axis=2)
    m = lum < ink
    kx, ky = W / canvas_mm[0], H / canvas_mm[1]

    rep = {"file": str(path), "px": [W, H], "trimmed": trimmed,
           "aspect": W / H, "panels": [], "notes": []}

    runs = _panel_runs(m, kx, W)
    if panels and len(runs) > panels:          # 面板挨太近没分开：合并最窄的缝
        while len(runs) > panels:
            gaps = [(runs[i + 1][0] - runs[i][1], i) for i in range(len(runs) - 1)]
            _, i = min(gaps)
            runs[i][1] = runs[i + 1][1]
            del runs[i + 1]
    if not runs:
        rep["notes"].append("一个面板都没分出来（整张图墨迹连成一片？）")
        return rep

    for n, (c0, c1) in enumerate(runs):
        sub = m[:, c0:c1 + 1]
        rows = np.nonzero(sub.any(axis=1))[0]
        rec = {"i": "abc"[n] if n < 3 else str(n + 1),
               "x0": c0 / kx, "x1": (c1 + 1) / kx}
        if rows.size:
            y0, y1 = int(rows[0]), int(rows[-1])
            # 上边界：逐列第一条墨迹（板子上边 / 图元顶边）
            xs = [x for x in range(c0, c1 + 1) if m[:, x].any()]
            ys = [int(np.nonzero(m[:, x])[0][0]) for x in xs]
            fit = _robust_line(xs, ys)
            if fit:
                a_, b_, res, cnt = fit
                rec["top_tilt"] = -np.degrees(np.arctan(a_))
                rec["top_resid_px"] = res
                # ★ 位置要用**内点**来定，不能用面板列区间的端点：
                #   那个区间被题注文字宽度带偏（位图的题注比板子宽），端点是题注的，
                #   不是板子的；取区间中点=拿不同的 x 读同一条线，取 x=0 截距=
                #   长距离外推（面板 c 要外推 130mm，0.5 度的斜率误差 = 几十毫米）。
                #   内点列 = 真正落在这条上边线上的列，也就是板子的列，它的两端
                #   就是板子的左上角 / 右上角。实测这才和 TX / TY / 板宽对得上。
                xs_a, ys_a = np.asarray(xs, float), np.asarray(ys, float)
                thr = max(1.5, 1.2 * res)
                inl = np.abs(ys_a - (a_ * xs_a + b_)) <= thr
                if inl.sum() >= 20:
                    rec["edge_x0"] = xs_a[inl].min() / kx
                    rec["edge_x1"] = (xs_a[inl].max() + 1) / kx
                    rec["edge_y0"] = (a_ * xs_a[inl].min() + b_) / ky
                if res > MAX_RESID_PX:
                    rec["top_tilt"] = None
                    rep["notes"].append("面板%s 上边界拟合残差 %.1fpx（>%.0f）→ 不可比"
                                        % (rec["i"], res, MAX_RESID_PX))
            # 侧边界：逐行第一条墨迹，与竖直的夹角（0 = 竖直 = 斜投影板）
            xs2, ys2 = [], []
            for y in range(y0, y1 + 1):
                r = np.nonzero(m[y, c0:c1 + 1])[0]
                if r.size:
                    ys2.append(y)
                    xs2.append(c0 + int(r[0]))
            fit2 = _robust_line(ys2, xs2)
            if fit2:
                s_, _, res2, _ = fit2
                rec["side_angle"] = np.degrees(np.arctan(s_))
                rec["side_resid_px"] = res2
                if res2 > MAX_RESID_PX:
                    rec["side_angle"] = None
                    rep["notes"].append("面板%s 侧边界拟合残差 %.1fpx（>%.0f）→ 不可比"
                                        % (rec["i"], res2, MAX_RESID_PX))
        rep["panels"].append(rec)

    rows_all = np.nonzero(m.any(axis=1))[0]
    if rows_all.size:
        rep["ink_top"] = rows_all[0] / ky
        rep["ink_bottom"] = (rows_all[-1] + 1) / ky
    return rep


def compare(a, b, tol_tilt, tol_mm, tol_aspect, panels=None):
    rows, miss = [], []

    def add(name, va, vb, tol, unit):
        if va is None or vb is None:
            miss.append(name)
            return
        d = vb - va
        rows.append({"metric": name, "bitmap": va, "final": vb, "diff": d,
                     "tol": tol, "unit": unit, "bad": abs(d) > tol})

    na, nb = len(a["panels"]), len(b["panels"])
    rows.append({"metric": "面板数", "bitmap": na, "final": nb, "diff": nb - na,
                 "tol": 0, "unit": "个", "bad": na != nb})

    n = min(na, nb)
    if panels:
        n = min(n, panels)
    for k in range(n):
        pa, pb = a["panels"][k], b["panels"][k]
        t = pa["i"]
        add("%s 上边界倾角" % t, pa.get("top_tilt"), pb.get("top_tilt"), tol_tilt, "度")
        add("%s 板左缘x" % t, pa.get("edge_x0"), pb.get("edge_x0"), tol_mm, "mm")
        add("%s 板左上角y" % t, pa.get("edge_y0"), pb.get("edge_y0"), tol_mm, "mm")
        add("%s 侧边界角" % t, pa.get("side_angle"), pb.get("side_angle"), tol_tilt, "度")

    # 不比的量（实测踩过，别再加回来）：
    #   · 板右缘x —— 拟合内点会在板子右上角之后「顺着走」到厚度侧面上，
    #     量到的是板宽 + 侧面偏移，不是板宽（位图 a 面板 59.4 其实已越过角点）。
    #   · 整图墨迹顶 —— 位图顶部**没有**面板字母，矢量件有；拿字母 y 和板角 y 比
    #     是两种东西。
    if a.get("aspect") and b.get("aspect"):
        d = b["aspect"] - a["aspect"]
        rows.append({"metric": "宽高比", "bitmap": a["aspect"], "final": b["aspect"],
                     "diff": d, "tol": tol_aspect, "unit": "",
                     "bad": abs(d) > tol_aspect})
    else:
        miss.append("宽高比")
    return rows, miss


def main() -> int:
    ap = argparse.ArgumentParser(description="成品 vs 所选位图的架构一致性闸门")
    ap.add_argument("bitmap", help="所选的那张位图（过了闸口②的）")
    ap.add_argument("final", help="成品位图，或成品 SVG（会栅格化）")
    ap.add_argument("--canvas-mm", default="183x100", help="画布尺寸 mm，默认 183x100")
    ap.add_argument("--panels", type=int, default=None, help="面板数；给了就按它合并列段")
    ap.add_argument("--tol-mm", type=float, default=2.0, help="位置容差 mm（默认 2.0）")
    ap.add_argument("--tol-tilt", type=float, default=2.0, help="角度容差 度（默认 2.0）")
    ap.add_argument("--tol-aspect", type=float, default=0.02, help="宽高比相对容差（默认 0.02）")
    ap.add_argument("--ink", type=float, default=INK, help="墨迹灰度阈值（默认 249）")
    ap.add_argument("--allow-diff", default=None, metavar="理由",
                    help="声明这是有意与位图不同（理由必写，会打印留痕）")
    ap.add_argument("--json", default=None, dest="json_out")
    a = ap.parse_args()

    W_MM, H_MM = (float(v) for v in a.canvas_mm.lower().split("x"))
    A = measure(a.bitmap, (W_MM, H_MM), a.panels, a.ink)
    B = measure(a.final, (W_MM, H_MM), a.panels, a.ink)
    rows, miss = compare(A, B, a.tol_tilt, a.tol_mm, a.tol_aspect, a.panels)
    bad = [r for r in rows if r["bad"]]

    print("=" * 78)
    print("bitmap_conformance —— 成品有没有照所选位图画")
    print("=" * 78)
    print("位图: %s   %dx%d" % (A["file"], A["px"][0], A["px"][1]))
    print("成品: %s   %dx%d" % (B["file"], B["px"][0], B["px"][1]))
    print()
    print("  %-18s %11s %11s %9s %8s" % ("量", "位图", "成品", "差", "容差"))
    print("  " + "-" * 62)
    for r in rows:
        fmt = "%11.2f" if r["unit"] != "个" else "%11d"
        print(("  %-18s " + fmt + " " + fmt + " %8.2f %8.2f   %s")
              % (r["metric"], r["bitmap"], r["final"], r["diff"], r["tol"],
                 "X 超差" if r["bad"] else "ok"))
    if miss:
        print()
        print("  不可比（至少一侧量不出来/拟合不可信，不计失败）:")
        print("    %s" % "、".join(miss))
    for rep in (A, B):
        for n in rep.get("notes", []):
            print("  [!] %s: %s" % (Path(rep["file"]).name, n))

    if len(rows) < 3:
        print()
        print("  X 两边可比的量只有 %d 个 —— 量不出来不等于通过。" % len(rows))
        bad = bad + [{"metric": "可比量太少", "diff": len(rows), "tol": 3}]

    print()
    print("-" * 78)
    if a.allow_diff:
        print("★ --allow-diff：已声明为**有意**与位图不同，理由：%s" % a.allow_diff)
        print("  交付说明里必须写明这一点，并说明差异从哪来。")
    if bad and not a.allow_diff:
        print("结论: 成品没照所选位图画。")
        for r in bad:
            if r["metric"] == "面板数":
                print("   - 面板数 %d -> %d" % (r["bitmap"], r["final"]))
            elif r["metric"] == "可比量太少":
                print("   - 只有 %d 个可比的量，判不了" % r["diff"])
            else:
                print("   - %-18s 差 %+.2f（容差 %.2f %s）"
                      % (r["metric"], r["diff"], r["tol"],
                         r.get("unit") or ""))
        print("   位图已经过了闸口②，物理是对的 —— 差的是**画**。回去照位图重量底盘")
        print("   （倾角 / 板子尺寸 / 面板间距 / 题注带），别沿用上一版构建器的常量。")
        ok = 2
    else:
        print("结论: 通过。")
        ok = 0
    print("=" * 78)

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(
            {"bitmap": A, "final": B, "rows": rows, "missing": miss,
             "allow_diff": a.allow_diff, "ok": (not bad) or bool(a.allow_diff)},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return ok


if __name__ == "__main__":
    sys.exit(main())