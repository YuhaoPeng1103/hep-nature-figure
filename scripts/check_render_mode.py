#!/usr/bin/env python3
"""
check_render_mode —— 交付前自检：这张图是 3D 明暗风吗？

硬规则（SKILL.md「★ 默认档 = render3d」）：
    所有配图一律 3D 明暗风（render3d）；扁平只允许出现在承载定量数据的面板、
    或纯抽象流程/晶格面板上，且必须在交付说明里写明理由。

为什么需要这个脚本：技能自带的风格门禁（delivery_gate.py）**分不出扁平与 3D**。
它的可信指标白名单 METRIC_ROBUST 里（whitespace / saturation / edge_density /
dark_ratio / aspect）没有任何一条能反映"渲染方式"；而能反映的那两条
（color_richness / gradient_ratio）被技能自己标为不可信（缩放、JPEG 会污染）。
实测代价：一张扁平示意图 5 道门禁全绿。

本脚本给三层结论，**只有第 1、3 层是硬判据**：

  1 [硬]  矢量层：真有 <gradient> 吗（radial/linear 个数、stop 数、用渐变填充的形体数）。
          —— 能抓"纯平涂/细描边"，**抓不到"有渐变但没有体积语言"**。
  2 [参考] 栅格层：ink_colors —— 把 900 px 宽的图里"非白像素"量化到 16 级/通道后的颜色数。
          标定值（_T3精选 21 张）：min 316 / p25 468 / median 649。
          ★★ 但它量的是「细节密度 + 文字量」，不是「明暗渲染」。反例是决定性的：
             作者偏好的 3D 位图 集体流那张 3D 成品位图 只有 215，
             而肉眼看着很扁平的 另一张肉眼看着很扁平的 UPC 示意图 有 377。
          **所以它是参考值，不是门禁。**（这条结论是标定出来的，不是猜的。）
  3 [硬]  流程层：有没有出 <stem>_vs_ref.png（成品 × 风格参考 的并排图）。
          机器判不了 3D，就强制"人 5 秒内能判" —— 这是替代不了的一条。

用法：
    python3 scripts/check_render_mode.py out/figure_3d.svg
    python3 scripts/check_render_mode.py out/*.svg
    python3 scripts/check_render_mode.py --dir out

返回码：0 = 硬判据全过；1 = 至少一条硬判据不过。
"""

import argparse
import glob
import os
import re
import sys

import numpy as np

# 中文 Windows：stdout 被管道/重定向时是 gbk，打印 ✅/❌ 会 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

T3_BAND = (316, 468, 649)          # _T3精选 21 张 ink_colors 的 min / p25 / median
CMP_PATTERNS = ("%s_vs_ref.png", "cmp_%s*.png", "%s_cmp*.png")   # 技能 compare_ref.py 的产物名
MIN_GRAD_KINDS = 2                 # 至少两种渐变（或两个渐变）才算"有明暗"
MIN_STOPS = 6
INK_WIDTH = 900


def svg_stats(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    radial = len(re.findall(r"<radialGradient", text))
    linear = len(re.findall(r"<linearGradient", text))
    return {
        "radial": radial,
        "linear": linear,
        "stops": len(re.findall(r"<stop", text)),
        "bodies": len(re.findall(r"<(?:ellipse|circle|path|rect|polygon)\b", text)),
        "grad_fills": len(re.findall(r'fill="url\(#', text)),
        "embedded": len(re.findall(r"<image\b|data:image", text)),
        "texts": len(re.findall(r"<text\b", text)),
    }


def ink_colors(path, width=INK_WIDTH):
    """把图缩到 width 宽，量非白像素量化后的颜色数（参考值，不是门禁）。"""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, max(1, int(im.height * width / im.width))), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    ink = lum < 0.955
    if int(ink.sum()) < 500:
        return None
    q = (a[ink] * 15.0).round().astype(np.uint8)
    key = q[:, 0].astype(np.int32) * 256 + q[:, 1].astype(np.int32) * 16 + q[:, 2].astype(np.int32)
    return int(np.unique(key).size)


def check_one(stem_path):
    """stem_path = 要检查的成品文件（.svg 优先，也可给 .png/.pdf）"""
    d = os.path.dirname(os.path.abspath(stem_path))
    stem = os.path.splitext(os.path.basename(stem_path))[0]
    fails, notes = [], []

    svg = os.path.join(d, stem + ".svg")
    png = os.path.join(d, stem + ".png")
    print("=" * 72)
    print("图: %s" % os.path.relpath(svg if os.path.exists(svg) else stem_path))

    # ---- 硬判据 1：真渐变
    if os.path.exists(svg):
        s = svg_stats(svg)
        kinds = s["radial"] + s["linear"]
        print("  ① 矢量层: radial %d / linear %d / stop %d / 形体 %d / 渐变填充 %d / 嵌入位图 %d"
              % (s["radial"], s["linear"], s["stops"], s["bodies"], s["grad_fills"], s["embedded"]))
        if kinds < MIN_GRAD_KINDS or s["stops"] < MIN_STOPS:
            fails.append("渐变不足（%d 个渐变 / %d 个 stop）—— 疑似平涂" % (kinds, s["stops"]))
        if s["embedded"]:
            fails.append("有 %d 处嵌入位图" % s["embedded"])
        notes.append("① 只抓纯平涂；有渐变但没体积语言（无板/无明暗/无辉光）它抓不到 —— 靠 ③ 兜")
    else:
        notes.append("① 跳过：没有同名 .svg（PDF/PNG 无法做矢量层判定）")

    # ---- 硬判据 2：并排图
    vs = None
    for pat in CMP_PATTERNS:
        hit = sorted(glob.glob(os.path.join(d, pat % stem)))
        if hit:
            vs = hit[0]
            break
    if vs:
        print("  ③ 流程层: 并排图存在  %s" % os.path.relpath(vs))
    else:
        print("  ③ 流程层: ❌ 缺并排图（%s）" % " / ".join(p % stem for p in CMP_PATTERNS))
        fails.append("没出与风格参考的并排图（skill: scripts/compare_ref.py）"
                     "—— 机器判不了扁平/3D，这条不能省")

    # ---- 参考值：ink_colors
    if os.path.exists(png):
        n = ink_colors(png)
        if n is None:
            notes.append("② ink_colors: 墨太少，量不准")
        else:
            lo, p25, med = T3_BAND
            tag = "低于参考库下限" if n < lo else ("落在参考库 25% 分位以下" if n < p25
                                                else "落在参考库常见区间")
            print("  ② ink_colors = %d   （参考库 min %d / p25 %d / median %d → %s）"
                  % (n, lo, p25, med, tag))
            notes.append("② 仅供参考：它量的是细节密度+文字量，不是明暗渲染，别当门禁")

    for x in notes:
        print("     · %s" % x)
    for x in fails:
        print("     ❌ %s" % x)
    if not fails:
        print("     ✅ 硬判据通过")
    return not fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="成品文件（.svg / .png / .pdf）")
    ap.add_argument("--dir", action="append", default=[],
                    help="目录：自动找里面的 *.svg（排除 _ 开头）")
    args = ap.parse_args()

    targets = list(args.paths)
    for d in args.dir:
        targets += [p for p in sorted(glob.glob(os.path.join(d, "*.svg")))
                    if not os.path.basename(p).startswith("_")]

    if not targets:
        ap.error("没给要检查的文件")

    ok = True
    for t in targets:          # 不要短路：每张图都要看到结论
        if not check_one(t):
            ok = False
    print("=" * 72)
    print("RESULT: %s" % ("硬判据全过" if ok else "有硬判据不过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())