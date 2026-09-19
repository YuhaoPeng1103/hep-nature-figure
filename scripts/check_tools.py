#!/usr/bin/env python3
"""
check_tools —— 科研配图工具能力探测

skill 要能"按图选工具"，就得先知道**这台机器上有什么**。
缺了不是放弃，而是**告诉用户装什么、怎么装**。

用法：
    python3 check_tools.py            # 探测并给建议
    python3 check_tools.py --for 示意图   # 只报告某类图需要的工具
"""
import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ── 工具清单 ─────────────────────────────────────────────────────
# 每项：命令名 / 用途 / 装法 / 对应哪类图
TOOLS = [
    dict(key="python", cmd=None, name="Python + matplotlib",
         use="数据图、3D 曲面",
         check="import matplotlib",
         install={"linux": "conda install matplotlib numpy scipy",
                  "win": "pip install matplotlib numpy scipy"},
         figures=["数据图", "3D曲面"]),
    dict(key="cairosvg", cmd=None, name="cairosvg",
         use="SVG → PNG/PDF 渲染（**必须**，PyMuPDF 渲染 SVG 会丢渐变）",
         check="import cairosvg",
         install={"linux": "pip install cairosvg", "win": "pip install cairosvg"},
         figures=["示意图"]),
    dict(key="fitz", cmd=None, name="PyMuPDF",
         use="PDF 几何审计、复合图拼版、从论文切图",
         check="import fitz",
         install={"linux": "pip install pymupdf", "win": "pip install pymupdf"},
         figures=["拼版"]),
    dict(key="inkscape", cmd="inkscape", name="Inkscape",
         use="矢量精修：路径布尔运算、描边、渐变、手工调整。"
             "**Illustrator 的开源替代**，且**有 CLI 可被脚本调用**",
         install={"linux": "sudo apt install inkscape",
                  "win": "winget install Inkscape.Inkscape  或 https://inkscape.org/release/"},
         figures=["示意图", "精修"]),
    dict(key="pdflatex", cmd="pdflatex", name="LaTeX (pdflatex)",
         use="TikZ 示意图、图内公式、PDF+LaTeX 工作流",
         install={"linux": "sudo apt install texlive-latex-recommended texlive-pictures",
                  "win": "安装 TeX Live 或 MiKTeX"},
         figures=["数学密集图", "精修"]),
    dict(key="ipe", cmd="ipe", name="Ipe",
         use="LaTeX 原生矢量编辑器，公式密集的物理图首选",
         install={"linux": "sudo apt install ipe",
                  "win": "https://ipe.otfried.org/"},
         figures=["数学密集图"]),
    dict(key="asy", cmd="asy", name="Asymptote",
         use="程序化矢量图（Vector Graphics Language），数学表达强",
         install={"linux": "sudo apt install asymptote", "win": "https://asymptote.sourceforge.io/"},
         figures=["数学密集图", "3D曲面"]),
    dict(key="blender", cmd="blender", name="Blender",
         use="**真 3D**：几何本身是科学内容时用（探测器几何、CAD）",
         install={"linux": "下载便携版：https://www.blender.org/download/",
                  "win": "winget install BlenderFoundation.Blender"},
         figures=["真3D"]),
    dict(key="root", cmd="root", name="ROOT",
         use="HEP 领域标准：读 .root 文件、大数据量、领域惯例图",
         install={"linux": "https://root.cern/install/", "win": "见 root.cern"},
         figures=["数据图", "ROOT文件"]),
    dict(key="wolframscript", cmd="wolframscript", name="Wolfram / Mathematica",
         use="符号计算 + 2D 出版级图。"
             "⚠️ 实测其 **3D 导出会栅格化**（PDF 内嵌位图），3D 别用它",
         install={"linux": "https://www.wolfram.com/engine/", "win": "同左"},
         figures=["数据图"]),
    dict(key="illustrator", cmd=None, name="Adobe Illustrator",
         use="Nature 官方首选（线稿/示意图/合成）。**需人工操作**，"
             "skill 只能产出它可直接打开的分层 SVG",
         check_file=[
             "/mnt/c/Program Files/Adobe/Adobe Illustrator 2024/Support Files/Contents/Windows/Illustrator.exe",
             "/Applications/Adobe Illustrator 2024/Adobe Illustrator.app",
         ],
         install={"linux": "不支持（Windows/macOS 专有）",
                  "win": "Adobe Creative Cloud 订阅"},
         figures=["精修"]),
]

FIGURES = ["数据图", "3D曲面", "示意图", "精修", "拼版", "真3D",
           "数学密集图", "ROOT文件"]


def os_key():
    return "win" if platform.system() == "Windows" else "linux"


def probe(t):
    """返回 (是否可用, 版本或路径)"""
    # 命令行工具
    if t.get("cmd"):
        p = shutil.which(t["cmd"])
        if p:
            try:
                v = subprocess.run([t["cmd"], "--version"], capture_output=True,
                                   text=True, timeout=25)
                return True, (v.stdout or v.stderr).strip().split("\n")[0][:48]
            except Exception:
                return True, p
        # 有些工具在 Windows 侧
        return False, ""
    # Python 模块
    if t.get("check"):
        try:
            __import__(t["check"].replace("import ", "").strip())
            mod = t["check"].replace("import ", "").strip()
            m = sys.modules[mod]
            return True, getattr(m, "__version__", "已安装")
        except Exception:
            return False, ""
    # 特定文件
    if t.get("check_file"):
        for f in t["check_file"]:
            if Path(f).exists():
                return True, f
        return False, ""
    return False, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--for", dest="figtype", default=None,
                    help="只报告某类图需要的工具")
    a = ap.parse_args()

    print("=" * 72)
    print("科研配图工具能力探测")
    print("=" * 72)
    print(f"系统: {platform.system()} {platform.release()}  |  "
          f"Python {platform.python_version()}\n")

    ok, missing = [], []
    for t in TOOLS:
        if a.figtype and a.figtype not in t["figures"]:
            continue
        avail, info = probe(t)
        (ok if avail else missing).append((t, info))

    if ok:
        print(f"✅ 已可用（{len(ok)}）")
        for t, info in ok:
            print(f"   {t['name']:<26} {info}")
    print()
    if missing:
        print(f"❌ 缺失（{len(missing)}）—— 按需安装")
        for t, _ in missing:
            print(f"\n   ▸ {t['name']}")
            print(f"     用途：{t['use']}")
            print(f"     适用：{', '.join(t['figures'])}")
            print(f"     安装：{t['install'].get(os_key(), t['install']['linux'])}")

    # 按图型给建议
    print("\n" + "=" * 72)
    print("按图型选工具")
    print("=" * 72)
    have = {t["key"] for t, _ in ok}
    for fig in FIGURES:
        if a.figtype and fig != a.figtype:
            continue
        need = [t for t in TOOLS if fig in t["figures"]]
        if not need:
            continue
        mark = []
        for t in need:
            mark.append(("✓" if t["key"] in have else "✗") + t["name"].split()[0])
        print(f"  {fig:<10} {'  '.join(mark)}")

    # LaTeX 宏包（只查常用的，缺了会编译失败）
    print("\n" + "=" * 72)
    print("LaTeX 宏包（缺了公式会编译失败）")
    print("=" * 72)
    for pkg, why in [("amsmath.sty", "数学公式基础"),
                     ("amssymb.sty", "数学符号"),
                     ("tikz.sty", "TikZ 绘图"),
                     ("newtxtext.sty", "Times 风格字体（可选，实测常缺）"),
                     ("standalone.cls", "单图编译")]:
        r = subprocess.run(["kpsewhich", pkg], capture_output=True, text=True)
        got = bool(r.stdout.strip())
        print(f"  {'✓' if got else '✗'} {pkg:<18}{why}")
    print("\n  缺失安装：sudo apt install texlive-latex-recommended "
          "texlive-pictures texlive-fonts-extra")

    print("\n注：✓ = 已装，✗ = 需安装。缺工具不是放弃的理由 —— "
          "先装，再调用。")
    return 0 if not missing else 0


if __name__ == "__main__":
    sys.exit(main())
