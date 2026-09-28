#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sketch_handoff —— 把「多张草图候选」打包成**给人挑**的一页（v3.0 人机交接）
================================================================================

## 它在流程里的位置

    生图 ──▶ 多张草图位图 ──▶ 闸口① ──★本脚本★──▶ handoff/candidates.md（给人看）
                                                    │
                        ┌───────────────────────────┴────────────────────────────┐
                        ▼                                                        ▼
              用户说「用第 N 张」                                用户下载 cand_NN.svg 改完再传回
                        │                                                        │
                        └──────────────► scripts/sketch_ingest.py ◄──────────────┘
                                                  │
                                                  ▼
                                      成品位图（--content-ref 用回流的草图）

## 为什么要有这一步

机器只能**排序**，不能**拍板**：`pick_best.py` 把没有硬伤的排到前面，但
"哪张更像我要讲的物理、哪个构图更好看"只有作者知道。而草图是**最便宜的返工点** ——
在草图上改一笔，比在成品位图上返工便宜得多（成品位图一次出图要花钱、之后还要重过闸口②
再重新矢量化）。所以交接点放在闸口① 之后、成品位图之前。

★ 同时把草图**矢量化成可编辑 SVG** 一起交出去：PNG 只能干瞪眼，
SVG 才能在 Illustrator / Inkscape 里直接拖、删、改（每个连通域是独立子层 `part-01`…）。

## 用法

    # 常规：候选全给，脚本自己跑闸口①
    python3 scripts/sketch_handoff.py gen/sketch_s*_clean.png --ir ir/x.ir.yaml \
        --outdir handoff

    # 已经跑过闸口① → 复用那份报告（不重复算）
    python3 scripts/sketch_handoff.py gen/sketch_s*_clean.png --ir ir/x.ir.yaml \
        --json gen/check1.json --outdir handoff

    # 有硬伤的也想摆出来给人看
    python3 scripts/sketch_handoff.py ... --all

    # 只要清单不要 SVG（省时间；但人就改不了了）
    python3 scripts/sketch_handoff.py ... --no-svg

## 产物

    handoff/candidates.md        给人看的一页：表格 + 预览图 + 三种回音怎么回
    handoff/cand_01.svg          可编辑草图（人改的就是它）
    handoff/cand_01_preview.png  预览位图（在聊天里直接显示）
    handoff/handoff.json         机器账本（候选、指标、排序）
"""
from __future__ import annotations

from _console import init_console

init_console()          # Windows：stdout 被管道/重定向时是 gbk，打印 ✅ 会崩

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pick_best import _rank_key        # ★ 与 pick_best 共用同一套排序判据，别各写一份


def sh(cmd, **kw):
    print("  $ %s" % " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], **kw)


def run_gate(images, ir, report_json):
    """闸口①：没有现成报告就跑 check_sketch.py。返回报告 dict。"""
    if report_json.exists():
        print("复用已有闸口报告：%s" % report_json.name)
    else:
        sh([sys.executable, HERE / "check_sketch.py", *images,
            "--ir", ir, "--json", report_json])
    return json.loads(report_json.read_text(encoding="utf-8"))


def to_svg(png, svg, q, R):
    """草图位图 → 人可改的 SVG（不写 panels.py，靠自动切分）"""
    r = sh([sys.executable, HERE / "sketch_to_vector.py", png, "-o", svg,
            "--q", str(q), "--R", str(R)],
           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("  ⚠️ 矢量化失败：%s" % (r.stderr or r.stdout or "")[-300:])
    return r.returncode == 0


def make_preview(svg, png, width):
    """SVG → PNG 预览。没装 cairosvg 就退回源位图（不阻断交接）。"""
    try:
        import cairosvg
    except ImportError:
        print("  ⚠️ 没装 cairosvg → 预览用草图位图代替（SVG 照样给了）")
        return False
    cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=width)
    return True


def _abs(p):
    """给聊天渲染用的绝对路径（正斜杠；Codex 里 ![x](/abs/path) 才显示得出来）"""
    return str(pathlib.Path(p).resolve()).replace("\\", "/")


def main():
    ap = argparse.ArgumentParser(
        description="多张草图候选 → 给人挑的一页 + 可编辑 SVG（v3.0 人机交接）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("image", nargs="+", help="草图位图（通常 gen/sketch_s*_clean.png）")
    ap.add_argument("--ir", required=True, help="对应 IR —— 闸口①的几何断言从它来")
    ap.add_argument("--json", default=None,
                    help="现成的闸口①报告（有就复用，不重跑）")
    ap.add_argument("--outdir", default="handoff")
    ap.add_argument("--q", type=int, default=16,
                    help="草图的颜色量化级数（默认 16 = 人能改；0 = 更忠实但路径碎成几万条）")
    ap.add_argument("--R", type=float, default=12.0, help="四叉树色差阈值")
    ap.add_argument("--preview-w", type=int, default=900, help="预览图宽度")
    ap.add_argument("--all", action="store_true",
                    help="有硬伤的也标成「可选」（默认只推荐没硬伤的，但仍全部列出）")
    ap.add_argument("--no-svg", action="store_true", help="不矢量化（省时间，但人改不了）")
    a = ap.parse_args()

    out = pathlib.Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    report = run_gate(a.image, a.ir,
                      pathlib.Path(a.json) if a.json else out / "check.json")
    rows = sorted(report["images"], key=_rank_key)

    clean = [r for r in rows if not (r.get("hard") or [])]
    pickable = rows if a.all else clean

    print()
    print("=" * 66)
    print("候选 %d 张 → 没有硬伤 %d 张" % (len(rows), len(clean)))

    cands = []
    for i, r in enumerate(rows, 1):
        cid = "cand_%02d" % i
        src = pathlib.Path(r["path"])
        svg = out / (cid + ".svg")
        prev = out / (cid + "_preview.png")
        ok_svg = False
        if not a.no_svg:
            ok_svg = to_svg(str(src), str(svg), a.q, a.R)
            if ok_svg:
                make_preview(svg, prev, a.preview_w)
        cands.append(dict(
            cid=cid, rank=i, src=str(src),
            svg=(str(svg) if ok_svg else None),
            preview=(str(prev) if (ok_svg and prev.exists()) else str(src)),
            selectable=bool(r in pickable),
            hard=r.get("hard") or [], soft=r.get("soft") or [],
            fidelity=r.get("fidelity_r"), ratio_dev=r.get("ratio_dev"),
            size=r.get("size"), ratio=r.get("ratio")))
        print("  %s %-28s 硬伤 %d  软警 %d  保真 %s"
              % ("✅" if not cands[-1]["hard"] else "❌", src.name,
                 len(cands[-1]["hard"]), len(cands[-1]["soft"]),
                 ("%.3f" % r["fidelity_r"]) if r.get("fidelity_r") is not None else "n/a"))

    # ── 给人看的一页 ───────────────────────────────────────────
    md = []
    md.append("# 草图交接：%d 张候选（IR: %s）" % (len(cands), a.ir))
    md.append("")
    md.append("**怎么回**（两种都行，回一句就行）：")
    md.append("")
    md.append("- 说「**用第 N 张**」→ 我直接拿它出成品位图（下一步要花钱，所以先问过你）")
    md.append("- 说「**我改一下**」→ 下载下面的 `cand_NN.svg`，在 Illustrator / Inkscape 里改完传回，"
              "我跑 `sketch_ingest.py` 灌回来（**改完仍要过一遍闸口①**，物理断言不过会被拒）")
    md.append("- 都不满意 → 说一声，改简报 / 换 seed 重出（草图上返工最便宜）")
    md.append("")
    md.append("| 候选 | 硬伤 | 软警 | 构图保真 | 比例偏差 | 草图位图 | 可编辑 SVG |")
    md.append("|---|---|---|---|---|---|---|")
    for c in cands:
        mark = "" if c["selectable"] else "（不推荐）"
        md.append("| **%s** %s | %d | %d | %s | %s | `%s` | %s |" % (
            c["cid"], mark, len(c["hard"]), len(c["soft"]),
            ("%.3f" % c["fidelity"]) if c["fidelity"] is not None else "n/a",
            ("%.4f" % c["ratio_dev"]) if c["ratio_dev"] is not None else "n/a",
            pathlib.Path(c["src"]).name,
            ("`%s`" % pathlib.Path(c["svg"]).name) if c["svg"] else "（--no-svg）"))
    md.append("")
    for c in cands:
        md.append("## %s%s" % (c["cid"], "" if c["selectable"] else "（不推荐：有硬伤）"))
        md.append("")
        md.append("![%s](%s)" % (c["cid"], _abs(c["preview"])))
        md.append("")
        if c["hard"]:
            md.append("- ❌ **硬伤**：%s" % "；".join(c["hard"]))
        if c["soft"]:
            md.append("- ⚠️ 软警：%s" % "；".join(c["soft"]))
        wh = ("%dx%d" % tuple(c["size"])) if c["size"] else "n/a"
        md.append("- 尺寸 %s（比例 %s；与 IR 的比例偏差 %s）"
                  % (wh, c["ratio"], c["ratio_dev"]))
        if c["svg"]:
            md.append("- 可编辑 SVG：`%s`" % c["svg"])
        md.append("")
    md.append("---")
    md.append("")
    md.append("> 改 SVG 时只改**形体与构图**：草图里的文字是**占位**，"
              "正式文字在「成品位图 → 矢量」那一步才重写（在草图上精修文字是白费功夫）。")
    md.append("> 改完传回后走："
              "`python3 scripts/sketch_ingest.py <你改的.svg> --ir %s --size <WxH> -o gen/sketch_edited_clean.png`" % a.ir)
    (out / "candidates.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "handoff.json").write_text(json.dumps(
        {"ir": a.ir, "report": str(report.get("ok")), "candidates": cands},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("已写出 %s" % (out / "candidates.md"))
    print("已写出 %s（候选 %d 张，可推荐 %d 张）"
          % (out / "handoff.json", len(cands), sum(1 for c in cands if c["selectable"])))
    print()
    print("★ 交接点：把 candidates.md 展示给用户，问清两件事 ——")
    print("    ① 用第几张继续？  ② 还是下载 SVG 自己改、改完传回？")
    print("  在拿到回音之前**不要**跑第 5 步（成品位图要花钱）。")
    return 0 if cands else 1


if __name__ == "__main__":
    sys.exit(main())
