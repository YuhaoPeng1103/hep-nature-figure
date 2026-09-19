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

MM = 72.0 / 25.4


def boxes(page):
    """返回 (文字块, 绘制块) 的 bbox 列表"""
    texts, draws = [], []
    d = page.get_text("dict")
    for b in d["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    texts.append({"bbox": fitz.Rect(s["bbox"]),
                                  "text": s["text"].strip()[:24],
                                  "size": round(s["size"], 1)})
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.width > 0.4 or r.height > 0.4:      # 忽略极小点
            draws.append({"bbox": r, "type": dr.get("type", "?")})
    return texts, draws


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


def check_line_through_text(texts, draws):
    """
    ② 线条穿过文字：绘制块与文字 bbox 交叠，且绘制块是细长条
       （细长 = 线；粗大 = 底色块，不算）
    """
    bad = []
    for t in texts:
        tb = t["bbox"]
        for d in draws:
            db = d["bbox"]
            ov = overlap_area(tb, db)
            if ov <= 0:
                continue
            thin = (db.height < 3.0 or db.width < 3.0)
            # 交叠超过文字面积 15% 且是细线 → 线压在字上
            if thin and ov / max(tb.get_area(), 1e-6) > 0.15:
                bad.append((t["text"], round(ov / tb.get_area() * 100)))
                break
    return bad


def check_out_of_bounds(texts, draws, page_rect, margin_pt=1.0):
    """③ 元素出界或贴边"""
    bad = []
    for t in texts:
        r = t["bbox"]
        if (r.x0 < margin_pt or r.y0 < margin_pt
                or r.x1 > page_rect.x1 - margin_pt
                or r.y1 > page_rect.y1 - margin_pt):
            bad.append(("文字", t["text"]))
    for d in draws:
        r = d["bbox"]
        if (r.x0 < -0.5 or r.y0 < -0.5
                or r.x1 > page_rect.x1 + 0.5 or r.y1 > page_rect.y1 + 0.5):
            bad.append(("图形", f"{r.width:.0f}×{r.height:.0f}pt @ "
                              f"({r.x0:.0f},{r.y0:.0f})"))
    return bad


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
    texts, draws = boxes(page)
    page_rect = page.rect
    page_area = page_rect.get_area()

    print(f"\n{'='*68}\n构图审计: {p.name}\n{'='*68}")
    print(f"  页面 {page_rect.width:.0f}×{page_rect.height:.0f} pt"
          f"  ({page_rect.width/MM:.0f}×{page_rect.height/MM:.0f} mm)")
    print(f"  文字块 {len(texts)} | 绘制块 {len(draws)}")

    fails, warns = [], []

    tt = check_text_text(texts, page_area)
    print(f"\n① 文字-文字重叠: {len(tt)} 处")
    for x, y, pct in tt[:8]:
        print(f"   ❌ 「{x}」×「{y}」重叠 {pct}%")
        fails.append(f"文字重叠: {x} × {y}")

    lt = check_line_through_text(texts, draws)
    print(f"\n② 线条穿过文字: {len(lt)} 处")
    for x, pct in lt[:8]:
        print(f"   ❌ 「{x}」被线穿过 {pct}%")
        fails.append(f"线穿文字: {x}")

    oob = check_out_of_bounds(texts, draws, page_rect)
    print(f"\n③ 出界/贴边: {len(oob)} 处")
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
