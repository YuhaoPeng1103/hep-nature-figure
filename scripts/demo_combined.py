#!/usr/bin/env python3
"""
联合使用多工具产出**一张**图
================================
这张图同时需要两种工具，各自做自己最擅长的部分：

  左panel 卡通示意图  ← svg_lib (Python 生成 SVG)
  右panel 物理公式    ← TikZ (LaTeX)

  合成              ← PyMuPDF (show_pdf_page，保矢量)
  交付              ← PDF (Nature 首选) + EPS (Nature 首选)

为什么不能只用一种：
  · LaTeX 公式（分式、上下标、希腊字母、期望值括号）用 SVG 手写极其痛苦，
    而且排版质量远不如 TeX。这是 TikZ 的场子。
  · 碰撞几何示意（火球、反应平面、角度箭头）用 TikZ 画也可以，
    但做渐变、发光这些"插画感"很别扭。这是 svg_lib 的场子。

  所以：**一张图，两个后端，拼版层合成。**
"""
import math
import shutil
import subprocess
import sys
from pathlib import Path

import fitz

HERE = Path(__file__).parent / "_demo_out"
HERE.mkdir(exist_ok=True)
# 陈旧路径：原为 HERE.parent/"hep-nature-figure"/"scripts"（指向不存在的目录，
# 靠 sys.path[0] 兜底才没炸）。本脚本和 svg_lib 同在 scripts/ 下，直接用自己所在目录。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_lib import SVG

MM = 72.0 / 25.4


# ---------------------------------------------------------------- 左：卡通
def build_cartoon(path):
    W, H = 330, 300
    s = SVG(W, H)
    cx, cy = 168, 158

    s.begin_layer("layer-plane", "1 反应平面")
    # 反应平面（透视平行四边形）
    p = [(52, 214), (266, 150), (312, 214), (98, 282)]
    d = "M " + " L ".join(f"{x} {y}" for x, y in p) + " Z"
    s.add(f'<path d="{d}" fill="#eaf4f8" fill-opacity="0.65" '
          f'stroke="#9fb4c2" stroke-width="1.1"/>')
    for t in [i / 5 for i in range(1, 5)]:
        def lp(a, b, t):
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        a, b = lp(p[0], p[1], t), lp(p[3], p[2], t)
        s.add(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" '
              f'y2="{b[1]:.1f}" stroke="#b8c8d2" stroke-width="0.7"/>')
    s.end_layer()

    s.begin_layer("layer-fireball", "2 火球")
    s.fireball(cx, cy, 42, glow=2.0)
    s.end_layer()

    s.begin_layer("layer-angles", "3 角度标注")
    # Ψ_RP：反应平面方向（水平线）
    s.add(f'<line x1="{cx}" y1="{cy}" x2="{cx+108}" y2="{cy}" '
          f'stroke="#c0392b" stroke-width="1.6" stroke-dasharray="5 3"/>')
    s.text(cx + 112, cy + 5, "Ψ_RP", 14)
    # ϕ：某粒子出射方向
    ang = math.radians(-38)
    x2, y2 = cx + 104 * math.cos(ang), cy + 104 * math.sin(ang)
    s.arrow(cx, cy, x2, y2, color="#2a6ae0", w=2.0, curve=0)
    s.text(x2 + 6, y2 - 4, "ϕ", 15)
    # 夹角弧
    s.add(f'<path d="M {cx+40} {cy} A 40 40 0 0 0 '
          f'{cx+40*math.cos(ang):.1f} {cy+40*math.sin(ang):.1f}" '
          f'fill="none" stroke="#666" stroke-width="1.1"/>')
    # 一个出射粒子
    s.sphere(cx + 78 * math.cos(ang), cy + 78 * math.sin(ang), 9, "#e05a2a")
    s.end_layer()

    s.begin_layer("layer-labels", "4 标注")
    s.text(10, 24, "Reaction plane and azimuthal angle", 13)
    s.end_layer()

    s.save(HERE / "cartoon.svg")
    s.render(HERE / "cartoon.pdf")
    return HERE / "cartoon.pdf"


# ---------------------------------------------------------------- 拼版
def assemble(cartoon_pdf, formula_pdf, out_pdf):
    doc = fitz.open()
    PW, PH = 180 * MM, 78 * MM
    page = doc.new_page(width=PW, height=PH)

    src1 = fitz.open(cartoon_pdf)
    src2 = fitz.open(formula_pdf)

    # 左：卡通（占 45%）
    r1 = fitz.Rect(4 * MM, 6 * MM, 82 * MM, 72 * MM)
    page.show_pdf_page(r1, src1, 0)
    # 右：公式（占 55%）
    r2 = fitz.Rect(86 * MM, 10 * MM, 176 * MM, 68 * MM)
    page.show_pdf_page(r2, src2, 0)
    # 面板标号
    page.insert_text(fitz.Point(4 * MM, 4.5 * MM), "a", fontsize=11,
                     fontname="hebo")
    page.insert_text(fitz.Point(86 * MM, 4.5 * MM), "b", fontsize=11,
                     fontname="hebo")

    doc.save(out_pdf, deflate=True, garbage=4)
    doc.close()
    src1.close()
    src2.close()
    return out_pdf


def main():
    # ★ 前置检查：本 demo 的"公式"部分依赖外部命令 pdflatex / pdftops。
    #   实测这类环境下它们**不存在**：ChatGPT 沙箱（无网络、无 TeX）、
    #   任何没装 TeX Live 的机器。原来会一路跑到 pdflatex 才失败，
    #   报错还是 subprocess 的干瘪信息。这里提前说清楚，并指明替代路径。
    need = [x for x in ("pdflatex", "pdftops") if shutil.which(x) is None]
    if need:
        print(f"   ⚠️ 缺外部命令：{', '.join(need)} —— 本 demo 的 TikZ 公式部分跳过。")
        print("      · 装：sudo apt install texlive-latex-recommended "
              "texlive-pictures poppler-utils")
        print("      · 装不了时（无网络沙箱）：**公式改用 Unicode 直接写进 SVG** ——"
              "svg_lib 的 s.text() 用 DejaVu Sans 能出 ε η φ ϕ 和下标 ₁₂₃，")
        print("        覆盖期刊图绝大多数标注需求；复杂分式才需要 TikZ。")
        print("      · 卡通部分（svg_lib）不依赖它们，继续跑。\n")

    c = build_cartoon(HERE / "cartoon.pdf")
    print(f"  ✓ 卡通  svg_lib → {c.name}")
    if need:
        print(f"  ⏭  公式  TikZ    → 跳过（缺 {', '.join(need)}）")
        print(f"  ⏭  合成  PyMuPDF → 跳过")
        return
    # ★ 路径修正：.tex 必须拷进编译目录，否则 pdflatex 找不到源文件
    #   （实测：只设 cwd 不够，源文件在父目录里 pdflatex 会直接失败并留下 texput.log）
    tex_src = Path(__file__).parent / "demo_formulas.tex"
    tex_dst = HERE / "demo_formulas.tex"
    tex_dst.write_text(tex_src.read_text(encoding="utf-8"), encoding="utf-8")
    f = HERE / "demo_formulas.pdf"
    if not f.exists():
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode",
                            "demo_formulas.tex"], cwd=HERE,
                           capture_output=True, text=True)
        if not f.exists():
            print("  ❌ TikZ 编译失败，日志尾部：")
            print("   ", (r.stdout or "")[-400:].replace("\n", " | "))
            return
    print(f"  ✓ 公式  TikZ    → {f.name}")
    out = assemble(c, f, HERE / "combined.pdf")
    print(f"  ✓ 合成  PyMuPDF → {out.name}")

    # 交付格式：Nature 首选 PDF / EPS
    subprocess.run(["pdftops", "-eps", str(out), str(HERE / "combined.eps")],
                   capture_output=True)

    d = fitz.open(out)
    p = d[0]
    print(f"\n  页面 {p.rect.width/MM:.0f}×{p.rect.height/MM:.0f} mm")
    print(f"  矢量指令 {len(p.get_drawings())} 条 | 嵌入位图 {len(p.get_images())} 个")
    print(f"  XObject {len(p.get_xobjects())} 个（两个面板各自嵌入）")
    txt = p.get_text()
    print(f"  文字可提取 {len(txt.strip())} 字符")
    print(f"  公式是否可提取: {'v_n' in txt or 'v' in txt}")
    d.close()
    for f_ in ["combined.pdf", "combined.eps"]:
        fp = HERE / f_
        if fp.exists():
            print(f"  {f_}: {fp.stat().st_size//1024} KB")


if __name__ == "__main__":
    main()
