#!/usr/bin/env python3
"""
audit_composition —— 局部构图审计（补 delivery_gate 的缺口）

为什么需要：
  delivery_gate 测的是【全局统计量】（留白/饱和/边密度）。
  它测不出"标签压线""右边一片空"这类【局部】问题。

  实测：UPC 第一版右侧大片空白、'γγ→X' 标签压在顶点上，
  全局指标全过，是用户一眼看出来的。

这个脚本读 PDF 几何，做四类局部检查：

  ① 文字-文字重叠        → 阻断
  ② 线条穿过文字         → 阻断（线压在字上，读不了）
  ③ 元素出界 / 贴边      → 阻断（会被裁掉）
  ④ 留白分布不均         → 提醒（某侧太空 = 构图失衡）

用法：
    python3 audit_composition.py fig.pdf
    python3 audit_composition.py fig.pdf --json
"""
import argparse
import json
import sys
from pathlib import Path

import fitz
import numpy as np

MM = 72.0 / 25.4

# 文字可读性的对比度下限（笔画亮度 vs 背景亮度之差，0–1）。
# 0.35 是实测定的：正常黑字白底 ≈ 0.85；被同色系色带压住 ≈ 0.15–0.30。
MIN_TEXT_CONTRAST = 0.35


def boxes(page):
    """返回 (文字块, 绘制块, 被剔除的页面背景数)"""
    texts, draws = [], []
    n_bg = 0
    d = page.get_text("dict")
    for b in d["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    texts.append({"bbox": fitz.Rect(s["bbox"]),
                                  "text": s["text"].strip()[:24],
                                  "size": round(s["size"], 1)})
    pr = page.rect
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.width > 0.4 or r.height > 0.4:      # 忽略极小点
            # ★ 页面自己的白底（近白色填充 + 几乎盖满整页）不是「会被裁掉的内容」。
            #   实测（UPC 位图临摹产物 upc.pdf）：它被 ③ 报 3 处「出界」，
            #   但 3 处的 fill 全是 (1,1,1)/(1,0.996,0.996)/(1,1,0.996)，x1/y1 仅超出 0.54pt；
            #   同时 ① 文字重叠 0 处、② 线穿文字 0 处。删掉它们不会隐藏任何
            #   真问题：真正被裁的内容不会是“白上白”。
            fl = dr.get("fill")
            if fl and min(fl) >= 0.98 and r.get_area() >= 0.97 * pr.get_area():
                n_bg += 1
                continue
            draws.append({"bbox": r, "type": dr.get("type", "?"),
                          "fill": fl,
                          "fill_opacity": dr.get("fill_opacity", 1.0),
                          "stroke": dr.get("color"),
                          "stroke_opacity": dr.get("stroke_opacity", 1.0),
                          "items": dr.get("items", [])})
    return texts, draws, n_bg




def overlap_area(a, b):
    r = a & b
    return r.get_area() if not r.is_empty else 0.0


def check_text_text(texts, page_area):
    """① 文字互相重叠"""
    bad = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i]["bbox"], texts[j]["bbox"]
            ov = overlap_area(a, b)
            if ov <= 0:
                continue
            small = min(a.get_area(), b.get_area())
            if small > 0 and ov / small > 0.28:
                bad.append((texts[i]["text"], texts[j]["text"],
                            round(ov / small * 100)))
    return bad


def check_line_through_text(page, texts):
    """
    ② 图形压字：**直接量文字和它身后背景的对比度**。

    ★ 这里试错过三版，值得记下来：

      第一版（`thin = 宽或高 < 3pt`，只认细线）
        → **漏检**。实测：一张图的 `hard scattering` 被喷注色带压掉
          91% 的文字面积（放大量能看见 h 压在色带边上），
          而审计报「✅ 局部构图无问题」。色带/箭头/半透明块都不是"细线"。

      第二版（任何非底色块交叠 >15% 就报）
        → **误报满屏**。"nucleus A" 这类标签坐在介质色块【上方】，
          色块从文字背后穿过根本不影响阅读，而 bbox 交叠分不出前后。

      第三版（本版）：不猜几何关系，**量可读性本身**——
        把文字 bbox 渲染出来，最暗的一小撮像素当"字的笔画"，
        其余当"背景"。两者亮度差就是对比度。差太小 = 字被吃掉。

      这条判据不依赖前后顺序、不依赖形状，直接对应"人能不能读出来"。
    """
    bad = []
    for t in texts:
        r = t["bbox"]
        clip = fitz.Rect(r.x0 - 1.0, r.y0 - 1.0, r.x1 + 1.0, r.y1 + 1.0)
        if clip.is_empty or clip.width <= 0.5 or clip.height <= 0.5:
            continue
        try:
            pix = page.get_pixmap(
                clip=clip, matrix=fitz.Matrix(4, 4), colorspace=fitz.csGRAY)
        except Exception:
            continue
        try:
            a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width).astype(np.float32) / 255.0
        except Exception:
            continue
        if a.size < 24:
            continue
        # ★ 笔画取 2% 分位而不是 8%：实测一个连字符 "-"（3.2×10.5pt）
        #   的笔画只占 bbox 像素的极小一部分，8% 分位整个落在白底上
        #   → 对比度算成 0.000，误报"字被压住"。取 2% 才落得到笔画上。
        #   背景取中位数（比 75% 分位更稳，不受大片色块影响）。
        n_ink = int((a < (a.min() + a.max()) / 2).sum())
        if n_ink < 3:
            continue                        # 几乎没有笔画 → 量不准，跳过
        fg = float(np.percentile(a, 2))
        bg = float(np.median(a))
        contrast = bg - fg
        if contrast < MIN_TEXT_CONTRAST:
            bad.append((t["text"], round(contrast, 2)))
    return bad


def check_out_of_bounds(texts, draws, page_rect, margin_pt=1.0):
    """③ 元素出界或贴边

    ★ 纯白填充不参与判定：**白上白被裁是不可见的**，不可能是真问题。
      实测（UPC 位图临摹 upc.pdf）：面包装在白页上的背景色块被报
      3 处「出界」，但 fill 全是白/近白，且 y1 仅超出 0.54pt（Edge 打印时
      像素对齐）。同时临摹稿 ① 文字重叠 0 处、② 线穿文字 0 处。
      不剔除的话，**每一张位图临摹稿都会被误判阻断**。

    ★ 按 **subpath（item）** 判 + 越界部分要有面积 —— 2026-09-26 加。
      两个实测证据（UPC 临摹稿 upc_q16.pdf，Edge print-to-pdf）：
        ① 有一条淡紫 path 的 bbox 是 (0, 0, 461.30, 289.50)，看着像"盖住大半个
           页面还出界"。但它 396 条子路径里**只有 3 条越界**，越界部分的并集是
           (0.63, 289.19, **0.63**, 289.50) —— **宽为 0**，面积 0。
           原因：`groupvec` 会把**同色矩形并成一条 path**（体积优化），bbox 是
           全体子路径的并集。拿并集 bbox 判 =「一处贴边 ⇒ 整条 path 出界」。
        ② 另一条 (43.36, 1.87, 519.00, 289.50) 同理，越界并集是一条**竖直线段**。
      所以判据是：**越界部分的面积** > 0.5 pt²。零面积毛边（Edge 像素对齐产生
      的 hairline）裁掉也看不见，不构成"会被裁"。
    """
    bad = []
    n_white = 0
    n_sliver = 0

    def _outside_area(r):
        """r 落在页面外的面积（pt²）。页面内/贴边 ⇒ 0。"""
        inter = r & page_rect
        inside = inter.get_area() if not inter.is_empty else 0.0
        return max(0.0, r.get_area() - inside)

    def _item_rect(it):
        """一条 subpath（line / curve / rect）的 bbox。"""
        if it[0] == "re":
            return it[1]
        xs, ys = [], []
        for q in it[1:]:
            if hasattr(q, "x0"):
                xs += [q.x0, q.x1]
                ys += [q.y0, q.y1]
            # ★ 用 hasattr(q, "x") 而不是 `q is not None`：PyMuPDF 的 item 里
            #   夹着**整数**（如 ("re", Rect, 1) 的方向位、"qu" 的四元组带上
            #   一个 flag）—— 原来那样写会 AttributeError。
            elif hasattr(q, "x"):
                xs.append(q.x)
                ys.append(q.y)
        if not xs:
            return None
        return fitz.Rect(min(xs), min(ys), max(xs), max(ys))

    for t in texts:
        r = t["bbox"]
        if (r.x0 < margin_pt or r.y0 < margin_pt
                or r.x1 > page_rect.x1 - margin_pt
                or r.y1 > page_rect.y1 - margin_pt):
            bad.append(("文字", t["text"]))
    for d in draws:
        r = d["bbox"]
        if not (r.x0 < -0.5 or r.y0 < -0.5
                or r.x1 > page_rect.x1 + 0.5 or r.y1 > page_rect.y1 + 0.5):
            continue
        fl = d.get("fill")
        if fl and min(fl) >= 0.98:
            n_white += 1
            continue
        # 只看真的探出页面的 subpath
        over, worst = [], None
        for it in d.get("items") or []:
            rr = _item_rect(it)
            if rr is None:
                continue
            ar = _outside_area(rr)
            if ar > 0.5:
                over.append(rr)
                if worst is None or ar > _outside_area(worst):
                    worst = rr
        if not over:
            # bbox 探出去了，但没有一条子路径有面积的越界 → 零面积毛边
            n_sliver += 1
            continue
        u = over[0]
        for rr in over[1:]:
            u = u | rr
        bad.append(("图形", f"越界部分 {u.width:.1f}×{u.height:.1f}pt "
                          f"@ ({u.x0:.1f},{u.y0:.1f}) "
                          f"（{len(over)}/{len(d.get('items') or [])} 条子路径）；"
                          f"整条约 {r.width:.0f}×{r.height:.0f}pt"))
    return bad, n_white, n_sliver


def check_balance(draws, texts, page_rect, grid=3):
    """
    ④ 留白分布：把页面切成 grid×grid，看有没有整块是空的。
       "有整块空白" = 构图失衡（内容挤在一侧）。
    """
    allr = [d["bbox"] for d in draws] + [t["bbox"] for t in texts]
    if not allr:
        return None, []
    W, H = page_rect.width / grid, page_rect.height / grid
    empty = []
    for i in range(grid):
        for j in range(grid):
            cell = fitz.Rect(j * W, i * H, (j + 1) * W, (i + 1) * H)
            if not any(overlap_area(cell, r) > 0 for r in allr):
                empty.append((j, i))
    frac = len(empty) / (grid * grid)
    return frac, empty


def main():
    ap = argparse.ArgumentParser(description="局部构图审计")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    p = Path(a.pdf)
    doc = fitz.open(p)
    page = doc[0]
    texts, draws, n_bg = boxes(page)
    page_rect = page.rect
    page_area = page_rect.get_area()

    print(f"\n{'='*68}\n构图审计: {p.name}\n{'='*68}")
    print(f"  页面 {page_rect.width:.0f}×{page_rect.height:.0f} pt"
          f"  ({page_rect.width/MM:.0f}×{page_rect.height/MM:.0f} mm)")
    print(f"  文字块 {len(texts)} | 绘制块 {len(draws)}"
          + (f"  （另有 {n_bg} 条页面白底已剔除，不参与出界判定）" if n_bg else ""))

    fails, warns = [], []

    tt = check_text_text(texts, page_area)
    print(f"\n① 文字-文字重叠: {len(tt)} 处")
    for x, y, pct in tt[:8]:
        print(f"   ❌ 「{x}」×「{y}」重叠 {pct}%")
        fails.append(f"文字重叠: {x} × {y}")

    lt = check_line_through_text(page, texts)
    print(f"\n② 线条穿过文字: {len(lt)} 处")
    for x, pct in lt[:8]:
        print(f"   ❌ 「{x}」被线穿过 {pct}%")
        fails.append(f"线穿文字: {x}")

    oob, n_white, n_sliver = check_out_of_bounds(texts, draws, page_rect)
    print(f"\n③ 出界/贴边: {len(oob)} 处"
          + (f"  （另有 {n_white} 条纯白色块贴边，白上白不可见，不计）"
             if n_white else "")
          + (f"  （另有 {n_sliver} 条零面积毛边被忽略）" if n_sliver else ""))
    for kind, dsc in oob[:6]:
        print(f"   ❌ {kind} {dsc}")
        fails.append(f"出界: {kind} {dsc}")

    frac, empty = check_balance(draws, texts, page_rect)
    print(f"\n④ 留白分布 (3×3 网格): {len(empty)}/9 格全空")
    if empty:
        pos = ", ".join(f"第{j+1}列第{i+1}行" for j, i in empty)
        print(f"   ⚠️  空格位置: {pos}")
        if frac >= 0.33:
            print(f"   → 超过 1/3 的格子是空的，构图可能失衡")
            warns.append(f"留白分布: {len(empty)}/9 格全空")

    print(f"\n{'='*68}")
    if fails:
        print(f"🚫 阻断交付：{len(fails)} 处局部构图问题")
        for f in fails[:10]:
            print(f"   ✗ {f}")
        print("\n   （全局指标可能全过，但这类问题必须修）")
        if a.json:
            print(json.dumps({"fails": fails, "warns": warns},
                             ensure_ascii=False))
        return 1
    if warns:
        print(f"⚠️  可通过，{len(warns)} 项需复核")
        for w in warns:
            print(f"   ! {w}")
    else:
        print("✅ 局部构图无问题")
    if a.json:
        print(json.dumps({"fails": fails, "warns": warns}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
