#!/usr/bin/env python3
"""
check_delivery —— 投稿前的矢量/可编辑性检查

Nature 硬性要求可编辑矢量（美术团队要重排版、换字体）。
这个脚本检查产出文件是否真的满足。

用法：
    python3 check_delivery.py fig.pdf
    python3 check_delivery.py fig.pdf fig.eps
    python3 check_delivery.py --svg fig.svg      # 顺带查 SVG 合法性
"""
import argparse
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")


def check_pdf(path):
    p = Path(path)
    doc = fitz.open(p)
    print(f"\n{'='*66}\n{p.name}\n{'='*66}")
    ok = True
    for i, page in enumerate(doc):
        if i > 0:
            print(f"  -- 第 {i+1} 页 --")
        mm = 72 / 25.4
        n_img = len(page.get_images())
        n_xobj = len(page.get_xobjects()) if hasattr(page, "get_xobjects") else 0
        n_draw = len(page.get_drawings())
        txt = page.get_text().strip()

        print(f"  页面      {page.rect.width/mm:.0f} × {page.rect.height/mm:.0f} mm")
        print(f"  矢量对象  {n_draw} 条顶层指令"
              + (f" + {n_xobj} 个 XObject" if n_xobj else ""))
        print(f"  嵌入位图  {n_img} 个")
        print(f"  可提取文字 {len(txt)} 字符")

        # 判定
        if n_img > 0:
            print(f"  ⚠️  含 {n_img} 个位图 —— 确认这是故意的高 dpi 图，"
                  f"不是被栅格化的矢量")
        if n_draw < 5 and n_xobj == 0:
            print("  ❌ 几乎没有矢量内容 —— 可能整页被栅格化")
            ok = False
        elif not txt:
            print("  ⚠️  提取不到文字 —— 文字可能被转成了轮廓，"
                  "美术团队无法重新排版")
        else:
            print("  ✅ 矢量 + 文字可编辑")
        # 字号下限
        sizes = set()
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        sizes.add(round(s["size"], 1))
        if sizes:
            lo = min(sizes)
            flag = "✅" if lo >= 5 else "⚠️ 低于 Nature 的 5pt 下限"
            print(f"  最小字号  {lo} pt  {flag}")
    doc.close()
    return ok


def check_eps(path):
    p = Path(path)
    print(f"\n{'='*66}\n{p.name}\n{'='*66}")
    head = p.read_bytes()[:200]
    if not head.startswith(b"%!PS"):
        print("  ❌ 不是合法的 PostScript/EPS 头")
        return False
    size_mb = p.stat().st_size / 1024
    print(f"  ✅ PostScript 头正常，{size_mb:.0f} KB")
    if b"%%BoundingBox" in p.read_bytes()[:2000]:
        print("  ✅ 含 BoundingBox（EPS 必需）")
    return True


def main():
    # ★ 改成 argparse：原来直接读 sys.argv，`--help` 会被当成文件名 ——
    #   与其余 20 多个工具不一致，别人上手会踩。
    ap = argparse.ArgumentParser(
        description="投稿前检查：矢量？文字可编辑？字号达标？")
    ap.add_argument("files", nargs="*", help="PDF / EPS 文件（可多个）")
    ap.add_argument("--svg", action="append", default=[],
                    help="顺带查这些 SVG 是不是合法 XML（浏览器能开不等于 "
                         "Illustrator 能开）")
    a = ap.parse_args()

    allok = True
    # SVG 合法性（有 --svg 时）
    if a.svg:
        from repair_brief import check_svg_xml
        for s in a.svg:
            sp = Path(s)
            if not sp.exists():
                print(f"找不到 {s}")
                allok = False
                continue
            probs = check_svg_xml(sp)
            print(f"\n{'='*66}\n{sp.name}（SVG 合法性）\n{'='*66}")
            if probs:
                for x in probs:
                    print(f"  ❌ {x}")
                print("  → 浏览器宽容能渲染，但 Illustrator / cairosvg 会拒绝，"
                      "会挡投稿")
                allok = False
            else:
                print("  ✅ 合法 XML，能被严格解析器打开")

    for a_ in a.files:
        p = Path(a_)
        if not p.exists():
            print(f"找不到 {a}")
            allok = False
            continue
        if p.suffix.lower() == ".pdf":
            allok &= check_pdf(p)
        elif p.suffix.lower() in (".eps", ".ps"):
            allok &= check_eps(p)
        elif p.suffix.lower() == ".svg":
            print(f"（{p.name} 是 SVG —— 请用 --svg {p.name} 查合法性）")
        else:
            print(f"跳过 {p.name}（只查 PDF / EPS / --svg）")
    print(f"\n{'='*66}")
    print("结论:", "全部通过" if allok else "有项目需处理")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
