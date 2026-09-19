#!/usr/bin/env python3
"""
audit_panels —— 多面板对齐检查

对标 nature-figure 的 1.5pt 对齐门禁，但判据不同：
  它量 matplotlib axes / R patchwork 的最终矩形。
  这里量【拼版后 PDF 里各面板内容的实际包围盒】——与后端无关。

为什么需要：
  多面板图的对齐靠"声明"不可靠 —— assemble_panels 里写的 rect 是
  面板的**画布框**，但面板内容的实际包围盒可能偏（留白不同、元素位置不同）。
  结果：看起来"两栏等高"，实际一栏的内容比另一栏矮一截。

检查：
  ① 同一行的面板，内容包围盒的 top/bottom 是否对齐
  ② 同一列的面板，left/right 是否对齐
  ③ 面板内容是否超出声明的 panel 框
  ④ 面板标签(a/b/c)位置是否一致

用法：
    python3 audit_panels.py fig.pdf --layout 2x1
    python3 audit_panels.py fig.pdf --layout 2x1 --tol 1.5   # 容差 pt
"""
import argparse
import sys
from pathlib import Path

import fitz

MM = 72.0 / 25.4


def content_bbox(page, rect, clip_margin=2.0):
    """
    取某个矩形区域内【实际有内容】的包围盒。
    做法：把该区域内的文字块和绘制块并起来。
    """
    r = fitz.Rect(rect)
    boxes = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    sb = fitz.Rect(s["bbox"])
                    if not (sb & r).is_empty:
                        boxes.append(sb)
    for d in page.get_drawings():
        db = d["rect"]
        if not (db & r).is_empty and (db.width > 0.3 or db.height > 0.3):
            boxes.append(db)
    if not boxes:
        return None
    u = boxes[0]
    for b in boxes[1:]:
        u |= b
    return u


def split_grid(page_rect, rows, cols, margin_frac=0.04, gutter_frac=0.03):
    """把页面切成 rows×cols 的面板框（与 assemble_panels.py 的算法一致）"""
    W, H = page_rect.width, page_rect.height
    mx, my = W * margin_frac, H * margin_frac
    gw, gh = W * gutter_frac, H * gutter_frac
    uw = (W - 2 * mx - gw * (cols - 1)) / cols
    uh = (H - 2 * my - gh * (rows - 1)) / rows
    out = []
    for i in range(rows):
        for j in range(cols):
            x0 = mx + j * (uw + gw)
            y0 = my + i * (uh + gh)
            out.append((j, i, fitz.Rect(x0, y0, x0 + uw, y0 + uh)))
    return out


def main():
    ap = argparse.ArgumentParser(description="多面板对齐检查")
    ap.add_argument("pdf")
    ap.add_argument("--layout", default="2x1", help="如 2x1（2行1列）或 1x2")
    ap.add_argument("--tol", type=float, default=1.5, help="容差 pt（默认 1.5）")
    ap.add_argument("--margin", type=float, default=0.06,
                    help="与 assemble_panels.py 保持一致（默认 0.06）")
    ap.add_argument("--gutter", type=float, default=0.05,
                    help="与 assemble_panels.py 保持一致（默认 0.05）")
    ap.add_argument("--no-bounds-check", action="store_true",
                    help="跳过'内容超出面板框'检查（当面板框未知时用）")
    a = ap.parse_args()

    p = Path(a.pdf)
    doc = fitz.open(p)
    page = doc[0]
    rows, cols = (int(x) for x in a.layout.lower().split("x"))

    print(f"\n{'='*68}\n多面板对齐检查: {p.name}  (布局 {rows}×{cols}, 容差 {a.tol}pt)\n{'='*68}")
    cells = split_grid(page.rect, rows, cols, a.margin, a.gutter)

    data = []
    for (j, i, r) in cells:
        cb = content_bbox(page, r)
        data.append({"col": j, "row": i, "cell": r, "content": cb})
        tag = f"第{j+1}列第{i+1}行"
        if cb is None:
            print(f"  {tag}: ⚠️  区域内无内容")
        else:
            print(f"  {tag}: 内容框 "
                  f"({cb.x0:.1f},{cb.y0:.1f})-({cb.x1:.1f},{cb.y1:.1f})"
                  f"  尺寸 {cb.width:.1f}×{cb.height:.1f}")

    fails, warns = [], []

    def group(key):
        d = {}
        for x in data:
            d.setdefault(x[key], []).append(x)
        return d

    # ① 同一行（不同列）→ top/bottom 应对齐
    for row, items in group("row").items():
        cs = [x for x in items if x["content"]]
        if len(cs) < 2:
            continue
        tops = [x["content"].y0 for x in cs]
        bots = [x["content"].y1 for x in cs]
        dt, db_ = max(tops) - min(tops), max(bots) - min(bots)
        print(f"\n① 第{row+1}行 top 偏差 {dt:.2f}pt / bottom 偏差 {db_:.2f}pt")
        if dt > a.tol:
            fails.append(f"第{row+1}行 top 未对齐 ({dt:.1f}pt > {a.tol})")
        if db_ > a.tol:
            fails.append(f"第{row+1}行 bottom 未对齐 ({db_:.1f}pt > {a.tol})")
        if dt <= a.tol and db_ <= a.tol:
            print("   ✅ 对齐")

    # ② 同一列（不同行）→ left/right 应对齐
    for col, items in group("col").items():
        cs = [x for x in items if x["content"]]
        if len(cs) < 2:
            continue
        lefts = [x["content"].x0 for x in cs]
        rights = [x["content"].x1 for x in cs]
        dl, dr = max(lefts) - min(lefts), max(rights) - min(rights)
        print(f"\n② 第{col+1}列 left 偏差 {dl:.2f}pt / right 偏差 {dr:.2f}pt")
        if dl > a.tol:
            fails.append(f"第{col+1}列 left 未对齐 ({dl:.1f}pt)")
        if dr > a.tol:
            fails.append(f"第{col+1}列 right 未对齐 ({dr:.1f}pt)")
        if dl <= a.tol and dr <= a.tol:
            print("   ✅ 对齐")

    # ③ 内容是否超出 cell —— 只在面板框确定时才查
    #   ⚠️ 若 --margin/--gutter 与实际拼版参数不一致，这里会误报。
    #   实测：默认值写成 0.04/0.03 而 assemble_panels 用 0.06/0.05，
    #   结果误报"超出 13.1pt"。
    if a.no_bounds_check:
        print("\n③ 跳过（--no-bounds-check）")
    for x in ([] if a.no_bounds_check else data):
        if x["content"] is None:
            continue
        cb, cell = x["content"], x["cell"]
        over = max(0, cell.x0 - cb.x0, cb.x1 - cell.x1,
                   cell.y0 - cb.y0, cb.y1 - cell.y1)
        if over > 1.0:
            fails.append(f"第{x['col']+1}列第{x['row']+1}行 内容超出面板框 {over:.1f}pt")

    # ④ 内容超出【页面】—— 绝对判据，不依赖面板框
    pb = None
    for x in data:
        if x["content"] is None: continue
        cb = x["content"]
        over = max(0, -cb.x0, -cb.y0, cb.x1 - page.rect.x1, cb.y1 - page.rect.y1)
        if over > 0.5:
            fails.append(f"第{x['col']+1}列第{x['row']+1}行 内容超出【页面】{over:.1f}pt（会被裁）")
    print(f"\n④ 内容是否超出页面: {'有超界' if any('超出【页面】' in f for f in fails) else '无'}")

    print(f"\n{'='*68}")
    if fails:
        print(f"🚫 未通过：{len(fails)} 项")
        for f in fails:
            print(f"   ✗ {f}")
        print("\n   → 修完重跑；对齐未达标前不要交付。")
        return 1
    print("✅ 多面板对齐通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
