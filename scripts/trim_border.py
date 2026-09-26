#!/usr/bin/env python3
"""
trim_border —— 把生图模型在四周画的那条 1~2px 外框【真的裁掉】
=========================================================================
## 为什么需要它（实测，2026-09-26）

生图模型（qwen-image-3.0 / mm 端点）**稳定地**在画面四周画一条细外框。
实测「自旋关联」算例：

    gen/sketch_s5.png      row0,row1 全命中，col0,col1 全命中   → 2px 实心黑框
    gen/sketch_s7.png      同上                                  → 2px 实心黑框
    gen_neg/sketch_s5/7/9  带 negative_prompt 也一样有框         → 5/5 全有

两条已经试过、**都没用**的办法：
  ① 简报里写「不要画外框」—— `ir_to_genbrief.py` 一直在写，模型照画；
  ② `--negative` 里加 border/frame/box outline/picture frame/…—— A/B 同 seed
     对比：加了 negative 的 3 张**仍然全部有框**（见上面的 gen_neg 行）。

所以别再求模型了，**裁掉**它。这条外框是确定性的像素级瑕疵，
用一个确定性的像素级步骤解决。

## 判据（区分「细外框」和「内容真的顶到边」）

从每条边往里走：
  · 连续若干行/列满足「≥85% 像素不是背景（灰 < 0.94）」→ 记作一个 run；
  · run 结束后第一条不是这样的行/列，**必须**几乎是空的（< 20% 不是背景）
    —— 这才说明刚才那几行是一条**孤立的细线**（外框），不是内容；
  · run 长度 > --max（默认 6）→ 当成内容，不裁（防止吃掉实心色块）。

四个边各自判断，互不影响（模型有时只画一边）。

## 用法

    # 报告会裁掉什么，不写文件
    python3 scripts/trim_border.py gen/sketch_s7.png --dry-run

    # 真的裁，输出干净图
    python3 scripts/trim_border.py gen/sketch_s7.png -o gen/sketch_s7_clean.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

BG = 0.94          # 灰度 < 它算"有内容"
LINE_FRAC = 0.85   # 一行里 ≥ 这么多像素有内容 → 像"框线"
EMPTY_FRAC = 0.20  # run 之后第一条必须 < 这么多 → 才认可是"孤立细线"


def _lines(img, axis, reverse):
    """按 axis（0=行, 1=列）从某条边往里，返回 '框线 run 长度' 或 0。"""
    g = np.asarray(img.convert("L")).astype(np.float32) / 255.0
    nb = g < BG
    if axis == 1:
        nb = nb.T
    if reverse:
        nb = nb[::-1]
    n_total = nb.shape[1]
    run = 0
    for row in nb:
        if row.mean() >= LINE_FRAC:
            run += 1
        else:
            break
    if run == 0:
        return 0, float(nb[0].mean())
    nxt = float(nb[run].mean()) if run < nb.shape[0] else 0.0
    ok = nxt < EMPTY_FRAC
    return run, nxt if not ok else nxt


def detect(img, max_px=6):
    """返回 {'left':n,'right':n,'top':n,'bottom':n}（要裁掉的像素数）。"""
    out = {}
    for name, axis, rev in (("top", 0, False), ("bottom", 0, True),
                            ("left", 1, False), ("right", 1, True)):
        run, nxt = _lines(img, axis, rev)
        if run == 0:
            out[name] = (0, "没找到框线")
        elif run > max_px:
            out[name] = (0, "连续 %d px 都有内容 → 判为内容顶到边，不裁" % run)
        elif nxt >= EMPTY_FRAC:
            out[name] = (0, "框线内侧紧跟着内容（%.0f%%）→ 判为内容，不裁" % (nxt * 100))
        else:
            out[name] = (run, "裁掉 %d px" % run)
    return out


def main():
    ap = argparse.ArgumentParser(description="裁掉生图模型画的 1~2px 外框")
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--max", dest="max_px", type=int, default=6,
                    help="单边最多裁多少 px（超过就当成内容，默认 6）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = Path(a.image)
    img = Image.open(p)
    W, H = img.size
    res = detect(img, a.max_px)
    print("trim_border  %s  (%dx%d)" % (p.name, W, H))
    n_any = 0
    for k in ("top", "bottom", "left", "right"):
        n, why = res[k]
        n_any += n
        print("  %-6s %s" % (k, why))
    if not n_any:
        print("  → 没找到外框（或判为内容），不裁")
        if a.out and not a.dry_run:
            img.save(a.out)
            print("  仍写出 %s" % a.out)
        return 0

    t, b = res["top"][0], res["bottom"][0]
    l, r = res["left"][0], res["right"][0]
    box = (l, t, W - r, H - b)
    print("  → 裁 %s  →  %dx%d" % (str(box), box[2] - box[0], box[3] - box[1]))
    if a.dry_run:
        print("  --dry-run：不写文件")
        return 0
    out = Path(a.out) if a.out else p.with_name(p.stem + "_clean" + p.suffix)
    img.crop(box).save(out)
    print("  已写出 %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())