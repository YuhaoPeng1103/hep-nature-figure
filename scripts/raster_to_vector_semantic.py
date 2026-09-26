#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
raster_to_vector —— 位图 → 语义分层的全矢量 SVG
================================================
和「像素描摹」的根本差别：**先理解，再临摹**。

  位图
    ├─ 文字  → 用与成品相同的渲染器（cairo）逐词对齐 → 真 <text>（可改字号/字体/内容）
    └─ 图形  → 四叉树平色块 → 严格不相交的矩形 → 按【物理元素】分组
  产出图层树： panel-a → a-nucleons → a-nucleons-gray → <path>

实测（T3-01 Jia2026 Fig.1，1200×1133）：
    MAE 1.48 | >32 1.29% | PSNR 26.5 dB | 37930 <path> | 54 <text> | 0 <image>
    非文字区（纯矢量色块）MAE 0.227，即"看不出差别"那一档

用法
----
    python3 raster_to_vector.py fig.png -o fig.svg --words words.txt \
        --panels my_panels.py --legend fig_layers.md --manifest fig.json --check

    # 没有 OCR 词表（文字会留在色块里，不过投稿门禁）：
    python3 raster_to_vector.py fig.png -o fig.svg --no-text

必须先准备的两样东西
--------------------
1. `--words words.txt`：OCR 词表（x y w h text，Tab 分隔，**源图 2 倍图**坐标）
   → Windows 上用 scripts/raster_vector/ocr_words.ps1 生成
2. `--panels panels.py`：这张图的版式/物理元素表（面板框 + 元素框 + 颜色条件）
   → 照 scripts/raster_vector/panels.py（T3-01 示例）改；不传就用那个示例

依赖：numpy scipy Pillow cairosvg cairocffi fontTools（**不需要 cv2 / skimage**）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from raster_vector import groupvec  # noqa: E402


def to_argv(a):
    argv = [str(a.image), str(a.out), a.words or "-",
            "--W", str(a.W), "--R", str(a.R), "--K", str(a.K)]
    if a.erase:
        argv.append("--erase")
    if a.no_text:
        argv.append("--no-text")
    if a.panels:
        argv += ["--panels", str(a.panels)]
    if a.manifest:
        argv += ["--manifest", str(a.manifest)]
    if a.legend:
        argv += ["--legend", str(a.legend)]
    if a.elmap:
        argv += ["--elmap", str(a.elmap)]
    if a.el_txt:
        argv += ["--el_txt", str(a.el_txt)]
    return argv


def selfcheck(out, src, W, want_text):
    """用与成品相同的渲染器回渲染，和源图逐像素比 —— 只认实测数字，不认"看着差不多" """
    try:
        import io
        import numpy as np
        import cairosvg
        from PIL import Image
    except ImportError as e:
        print("  （自检需要 cairosvg + numpy + Pillow：%s）" % e)
        return None
    ref = Image.open(src).convert("RGB")
    ref = ref.resize((W, int(round(ref.height * W / ref.width))), Image.LANCZOS)
    R = np.asarray(ref, np.float32)
    png = cairosvg.svg2png(url=str(out), output_width=W, output_height=R.shape[0])
    A = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), np.float32)
    e = np.abs(A - R)
    mae = float(e.mean())
    psnr = 10.0 * np.log10(255.0 ** 2 / max(float(((A - R) ** 2).mean()), 1e-9))
    mx = e.max(2)
    s = Path(out).read_text(encoding="utf-8")
    n_p, n_t, n_i = s.count("<path "), s.count("<text "), s.count("<image")
    print("  逐像素(同分辨率)：MAE %.3f | >8 %.2f%% | >32 %.2f%% | PSNR %.2f dB"
          % (mae, 100 * (mx > 8).mean(), 100 * (mx > 32).mean(), psnr))
    print("  <path> %d | <text> %d | <image> %d" % (n_p, n_t, n_i))
    bad = []
    if mae > 3.0:
        bad.append("MAE %.2f > 3.0（R 调小或 K 调大）" % mae)
    if n_i:
        bad.append("含 %d 个 <image> —— 投稿要求纯矢量" % n_i)
    if want_text and n_t == 0:
        bad.append("没有 <text> —— 文字还是色块")
    for b in bad:
        print("  ❌ " + b)
    print("  ✅ 自检通过" if not bad else "  → 按上面修完再交付")
    return not bad


def main():
    ap = argparse.ArgumentParser(
        description="位图 -> 语义分层的全矢量 SVG（先理解，再临摹）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法")[-1])
    ap.add_argument("image", help="源位图（png/jpg）")
    ap.add_argument("-o", "--out", default="vectorized.svg")
    ap.add_argument("--words", default="", help="OCR 词表；不给就等价于 --no-text")
    ap.add_argument("--panels", default="", help="版式/元素表 .py（默认用包里的示例）")
    ap.add_argument("--W", type=int, default=1200, help="工作分辨率宽度（默认 1200）")
    ap.add_argument("--R", type=float, default=16.0,
                    help="四叉树色差阈值：小=更准更大，大=更小更粗（默认 16）")
    ap.add_argument("--K", type=int, default=7, help="最粗边长 2^K（默认 7=128px）")
    ap.add_argument("--no-erase", dest="erase", action="store_false",
                    help="不擦掉原字笔画（默认擦掉，因为文字要重写成真 <text>）")
    ap.add_argument("--no-text", action="store_true",
                    help="不做文字层：原字留在色块里（过不了投稿门禁，但不需要 OCR）")
    ap.add_argument("--legend", default="", help="输出可读图层清单 .md")
    ap.add_argument("--manifest", default="", help="输出图层清单 .json（默认跟 -o 同名）")
    ap.add_argument("--elmap", default="", help="输出元素划分自检图 .png")
    ap.add_argument("--el_txt", default="", help="元素划分明细 .txt")
    ap.add_argument("--check", action="store_true", help="回渲染自检（推荐每次都开）")
    a = ap.parse_args()

    if not a.manifest:
        a.manifest = str(Path(a.out).with_suffix("")) + "_layers.json"

    src = Path(a.image)
    if not src.exists():
        sys.exit("找不到 %s" % src)
    words_given = bool(a.words) and Path(a.words).exists() and not a.no_text
    if a.words and not Path(a.words).exists():
        print("!! 词表 %s 不存在 —— 按 --no-text 处理" % a.words)

    old = sys.argv
    try:
        sys.argv = ["groupvec"] + to_argv(a)
        groupvec.main()
    finally:
        sys.argv = old

    if a.check:
        if not Path(a.out).exists():
            print("\n（本次只跑了诊断子命令 --elmap/--npz/--segs，没有产出 %s；"
                  "去掉它们再回渲染自检）" % a.out)
        else:
            print("\n自检（cairosvg 回渲染 vs 源图）：")
            selfcheck(a.out, a.image, a.W, words_given)

    print("""
────────────────────────────────────────────────────────────────
下一步（这三件脚本做不到，必须人/模型补）：

1. **版式表**：`panels.py` 里的 CELLS / ELEMENTS / SPLIT 是**每张图各不相同**的。
   自动切分只负责"形状"，名字和边界靠这张表。元素名字不对 → 改表重跑。
2. **文字**：OCR 漏掉的字、公式（⟨V₂(η₁)V₂*(η₂)⟩ 这类）要人工补进
   `labels.py` 的 FIX / MANUAL 表。公式用 `_{}` 下标、`^{}` 上标。
3. **渐变**：现在是色阶台阶（不是 gradient mesh）。要更平滑就调小 --R，
   路径数和体积会一起涨。真要矢量渐变网格得手工做。

验收：
    python3 check_delivery.py fig.pdf --svg fig.svg
    python3 audit_composition.py fig.pdf
────────────────────────────────────────────────────────────────""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
