#!/usr/bin/env python3
"""
check_tools —— 科研配图工具能力探测

skill 要能"按图选工具"，就得先知道**这台机器上有什么**。
缺了不是放弃，而是**告诉用户装什么、怎么装**。

用法：
    python3 check_tools.py            # 探测并给建议
    python3 check_tools.py --for 示意图   # 只报告某类图需要的工具
"""

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8（否则打印 ✅ 会崩）

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
         check="pymupdf|fitz",   # 新名优先；老版 pymupdf 只有 fitz
         install={"linux": "pip install pymupdf", "win": "pip install pymupdf"},
         figures=["拼版"]),
    # ★ 下面两项是补漏：原本表里没有它们，于是"缺工具"报告在目标平台上
    #   **永远误导性地全绿**，而运行时才炸。实测：ChatGPT 沙箱没有 shapely。
    dict(key="shapely", cmd=None, name="shapely",
         use="几何布尔运算 → 真外轮廓（circles_union / outline_offset）",
         check="import shapely",
         install={"linux": "pip install shapely", "win": "pip install shapely"},
         substitute="blob() + poly_to_path() 这条链**不需要** shapely，"
                    "缺了照样能画有机团块/膨胀边界；只有布尔并/差/偏移不可用",
         figures=["示意图"]),
    dict(key="yaml", cmd=None, name="PyYAML",
         use="解析 IR yaml（delivery_gate.py --ir 的结构断言）",
         check="import yaml",
         install={"linux": "pip install pyyaml", "win": "pip install pyyaml"},
         substitute="门禁会自动降级为「跳过结构断言」并打印提示，"
                    "**不阻断交付**（结构断言本来就只打印、不代判）",
         figures=["示意图", "拼版"]),
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
         # ★ 原来只写死 2024 版 + WSL 路径（/mnt/c/...）：
         #   原生 Windows 上装了任何版本的 Illustrator 都会被报成"缺失"。
         #   改成通配升级：版本号用 * 吃掉，三个平台一次覆盖（实测 2026-09-27）。
         check_glob=[
             "C:/Program Files/Adobe/Adobe Illustrator */Support Files/Contents/Windows/Illustrator.exe",
             "C:/Program Files (x86)/Adobe/Adobe Illustrator */Support Files/Contents/Windows/Illustrator.exe",
             "/mnt/c/Program Files/Adobe/Adobe Illustrator */Support Files/Contents/Windows/Illustrator.exe",
             "/Applications/Adobe Illustrator */Adobe Illustrator.app",
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
                                   # ★ 显式 utf-8：text=True 在中文 Windows 会用 gbk
                                   #   去解工具输出，遇非 ASCII 直接 UnicodeDecodeError
                                   #   （svg_lib 的 fc-list 踩过同一个坑）
                                   encoding="utf-8", errors="replace", timeout=25)
                return True, (v.stdout or v.stderr).strip().split("\n")[0][:48]
            except Exception:
                return True, p
        # 有些工具在 Windows 侧
        return False, ""
    # Python 模块
    if t.get("check"):
        # 允许 "a|b"：同一个库的不同模块名（如 pymupdf / fitz），命中任一即算已装
        for mod in t["check"].replace("import ", "").split("|"):
            mod = mod.strip()
            try:
                __import__(mod)
            except Exception:
                continue
            return True, getattr(sys.modules[mod], "__version__", "已安装")
        return False, ""
    # 特定文件
    if t.get("check_file"):
        for f in t["check_file"]:
            if Path(f).exists():
                return True, f
        return False, ""
    # 通配路径（版本号带 *，跨平台各写一条）
    if t.get("check_glob"):
        import glob
        for pat in t["check_glob"]:
            hits = sorted(glob.glob(pat))
            if hits:
                return True, hits[-1]      # 取版本号最大的那个
        return False, ""
    return False, ""


# kpsewhich 是否存在 —— 没有它时不报错、只报"没装 LaTeX"
_KPSEWHICH = shutil.which("kpsewhich")


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
        print(f"❌ 缺失（{len(missing)}）")
        for t, _ in missing:
            print(f"\n   ▸ {t['name']}")
            print(f"     用途：{t['use']}")
            print(f"     适用：{', '.join(t['figures'])}")
            # ★ 必须同时给【替代路径】：在无网络的环境（如 ChatGPT 沙箱）
            #   里装不了任何东西，只说"去装"会让流程直接卡死。
            if t.get("substitute"):
                print(f"     装不了时：{t['substitute']}")
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
    if not _KPSEWHICH:
        print("  （本机没有 kpsewhich：没装 LaTeX 时下面整排只能是 ✗，"
              "这不是探测坏了）\n")
    for pkg, why in [("amsmath.sty", "数学公式基础"),
                     ("amssymb.sty", "数学符号"),
                     ("tikz.sty", "TikZ 绘图"),
                     ("newtxtext.sty", "Times 风格字体（可选，实测常缺）"),
                     ("standalone.cls", "单图编译")]:
        # ★ 必须容错：没装 LaTeX 的机器上 kpsewhich 不存在，
        #   直接 subprocess.run(["kpsewhich",...]) 会 FileNotFoundError
        #   把整个"缺工具探测"脚本打死 —— 而这恰恰是最需要它工作的场景（已复现）。
        got = False
        if _KPSEWHICH:
            try:
                r = subprocess.run([_KPSEWHICH, pkg], capture_output=True,
                                   encoding="utf-8", errors="replace", timeout=20)
                got = bool((r.stdout or "").strip())
            except Exception:
                got = False
        print(f"  {'✓' if got else '✗'} {pkg:<18}{why}")
    print("\n  缺失安装：sudo apt install texlive-latex-recommended "
          "texlive-pictures texlive-fonts-extra")

    print("\n注：✓ = 已装，✗ = 需安装。")
    print("    能装的环境：缺工具不是放弃的理由 —— 先装，再调用。")
    print("    装不了的环境（无网络沙箱）：按上面「装不了时」给的替代路径走，"
          "**不要建议用户安装任何东西**。")
    # ★ 永远返回 0：缺工具是"报告"，不是"失败"。
    #   （原来写成 `0 if not missing else 0`，两分支同值，是明显的笔误）
    return 0


if __name__ == "__main__":
    sys.exit(main())
