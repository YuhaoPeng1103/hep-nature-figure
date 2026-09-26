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


# ── 位图门禁 ───────────────────────────────────────────────────────
# 位图本身不违规（照片、3D 渲染、SEM 图本来就是位图），Nature 也收。
# 违规的是「**本该是矢量却被栅格化**」。所以门禁分三条，缺一即失败：
#   ① 位图只能出现在受控区域 —— 单张盖住整页 = 整页被栅格化，拒收
#   ② 有效 dpi 有下限 —— 拿像素数 ÷ 物理尺寸实算，不看"标称 dpi"
#   ③ 必须有矢量轮廓 —— 位图之外页面还得有可编辑的矢量内容
DPI_MIN = 300        # Nature 对连续调位图的下限
DPI_LINE = 600       # 线条图 / 半调图建议下限
COVER_FAIL = 0.90    # 单张位图占页比例 ≥ 它就判失败（受控区域原则）
COVER_WARN = 0.50


def real_image_xrefs(doc):
    """PDF 里真·图像 XObject 的 xref 集合。

    ★ 为什么不能直接信 page.get_image_info()：
      MuPDF 会把**渐变填充（shading pattern）**也合成成一条"图像"记录，
      特征是 xref=0、像素尺寸正好等于该图元的 bbox。实测（本机 PyMuPDF）：
        · 最小复现：只含 1 个 radialGradient + 1 个 linearGradient 的 SVG，
          走 Edge print-to-pdf —— get_images()=0、原始字节里 /Subtype /Image
          出现 0 次（只有 /Shading），但 get_image_info() 报 **2 张**
          "57×64 px" 的位图 → 旧版本直接判 ❌ 有效 dpi 72 < 300。
        · 反向对照：真塞一张 240×160 PNG 进 HTML 再导出，
          get_images()=1、xref 扫描找到 xref 4，
          get_image_info(xrefs=True) 给出的 xref 也正是 4。
      所以判据是「有 xref，且该 xref 的对象 Subtype 真的是 /Image」。
      也别退回 page.get_images()：它只读页面资源字典，
      会漏掉嵌套 Form XObject 里的图（正是"整页被栅格化"的典型形态）。
    """
    out = set()
    for x in range(1, doc.xref_length()):
        try:
            if (doc.xref_get_key(x, "Subtype") or ("", ""))[1] == "/Image":
                out.add(x)
        except Exception:
            pass
    return out


def page_bitmaps(page, doc):
    """返回 (真位图信息列表, 被剔除的伪位图条数)。"""
    try:
        infos = page.get_image_info(xrefs=True)
    except TypeError:      # 老版本 PyMuPDF 没有 xrefs 参数
        sys.exit("PyMuPDF 太旧：get_image_info 不支持 xrefs=True，"
                 "无法把真位图和渐变 shading 区分开。请 pip install -U pymupdf")
    real = real_image_xrefs(doc)
    good = [i for i in infos if i.get("xref") in real]
    return good, len(infos) - len(good)


def check_bitmaps(infos, pw, ph):
    """位图只允许在受控区域 + dpi 达标 + 有矢量轮廓。返回是否通过。"""
    if not infos:
        return True
    pw, ph = page.rect.width, page.rect.height
    area = max(pw * ph, 1e-6)
    print("  ── 位图逐张 ──")
    ok = True
    for k, inf in enumerate(infos):
        bb = fitz.Rect(inf["bbox"])
        w_px, h_px = inf.get("width", 0), inf.get("height", 0)
        w_in = bb.width / 72
        # ★ 有效 dpi 必须实算：PDF 里的 /Width 只说明像素数，与版面上
        #   放多大无关。同一张 600px 图放 1cm 是 1524dpi，放 20cm 只有 76dpi。
        dpi = (w_px / w_in) if w_in > 1e-6 else 0.0
        cover = (bb.width * bb.height) / area
        flag = "✅"
        if dpi < DPI_MIN:
            flag = "❌"
            ok = False
        elif dpi < DPI_LINE:
            flag = "⚠️"
        print(f"   #{k}  {bb.width/72*25.4:.0f}×{bb.height/72*25.4:.0f} mm  "
              f"{w_px}×{h_px} px  →  有效 {dpi:.0f} dpi  "
              f"占页 {cover*100:.0f}%  {flag}")
        if dpi < DPI_MIN:
            print(f"        ❌ 有效 dpi {dpi:.0f} < {DPI_MIN} —— "
                  f"低于 Nature 下限，印出来会糊")
        elif dpi < DPI_LINE:
            print(f"        ⚠️  有效 dpi {dpi:.0f} < {DPI_LINE} —— "
                  f"连续调图够用；若是线条/半调图会被质疑")
        if cover > COVER_FAIL:
            print(f"        ❌ 这一张就盖住 {cover*100:.0f}% 的页面 —— "
                  f"等于整页被栅格化，美术团队改不动任何东西")
            ok = False
        elif cover > COVER_WARN:
            print(f"        ⚠️  大幅面位图（占页 {cover*100:.0f}%）—— "
                  f"确认它不是「本该是矢量」的部分")
    return ok


def check_pdf(path):
    p = Path(path)
    doc = fitz.open(p)
    print(f"\n{'='*66}\n{p.name}\n{'='*66}")
    ok = True
    for i, page in enumerate(doc):
        if i > 0:
            print(f"  -- 第 {i+1} 页 --")
        mm = 72 / 25.4
        n_xobj = len(page.get_xobjects()) if hasattr(page, "get_xobjects") else 0
        n_draw = len(page.get_drawings())
        txt = page.get_text().strip()
        infos, n_phantom = page_bitmaps(page, doc)
        n_img = len(infos)

        print(f"  页面      {page.rect.width/mm:.0f} × {page.rect.height/mm:.0f} mm")
        print(f"  矢量对象  {n_draw} 条顶层指令"
              + (f" + {n_xobj} 个 XObject" if n_xobj else ""))
        print(f"  嵌入位图  {n_img} 个"
              + (f"（另有 {n_phantom} 条矢量渐变填充被 MuPDF 记成伪位图，已剔除）"
                 if n_phantom else ""))
        print(f"  可提取文字 {len(txt)} 字符")

        # 判定 —— 位图要过三道闸，不是"提醒一下"就放行
        raster_ok = check_bitmaps(infos, page.rect.width, page.rect.height)
        if n_draw < 5 and n_xobj == 0:
            print("  ❌ 几乎没有矢量内容 —— 可能整页被栅格化")
            ok = False
        elif not txt:
            print("  ⚠️  提取不到文字 —— 文字可能被转成了轮廓，"
                  "美术团队无法重新排版")
            ok &= raster_ok
        elif not raster_ok:
            ok = False
        else:
            print("  ✅ 矢量轮廓齐全"
                  + (" + 位图在受控区域" if n_img else "（纯矢量）")
                  + " + 文字可编辑")
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
