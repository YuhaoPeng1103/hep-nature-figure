#!/usr/bin/env python3
"""
ref_leak_check —— 量「出图是不是把参考图抄了」
=========================================================================
## 为什么需要它（实测，2026-09-27）

`qwen-image-*` 是**图生图**：参考图内容越接近目标，模型越倾向**直接抄**。
实测（用 Claude Code 跑本 skill）：出的图物体/布局/箭头/文字全变成参考图的。

原流程**没有任何机器判据**能发现这件事，只能靠人眼。这个脚本把它变成
一条命令 / 一个数字。

## 判据：96x96 灰度 z 归一化后求相关 r（主）+ 32 宽 dHash 距离（辅）

| 情形 | r | dHash 距离 |
|---|---|---|
| 同一张图（照抄上限） | 1.000 | 0 |
| 出图 vs 自己的草图（**本来就该像**） | 0.634 | 175 |
| 半张裁切 vs 原图 | 0.318 | 333 |
| 两张不同参考图互比（基线） | 0.125 | 356 |
| 出图 vs 风格参考（**健康**） | 0.017 / 0.117 | 338 / 384 |

阈值：**r >= 0.85 或 dHash <= 6 → 疑似照抄**；0.60 <= r < 0.85 → 偏高。
（0.85 定得高于「出图 vs 自己的草图」0.634，所以正常构图继承不会被误判。）

## 角色：构图参考 vs 风格参考

上一步的草图是**构图依据**，出图本来就该像它 —— 用 `--content-ref` 标出来，
只报告不判问题。文件名里含 `sketch` / `草图` 的自动按构图参考处理。

## 用法

    python3 scripts/ref_leak_check.py gen/render_s22.png \
        --ref refs/T3-33.png --content-ref gen/sketch_s9_clean.png

退出码：0 正常 / 2 疑似照抄（可直接当门禁用）。`gen_figure.py` 出图后会自动跑，
把 `ref_sim` 写进 `calls.jsonl`。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

THR_COPY = 0.85     # r >= 它 → 疑似照抄
THR_HIGH = 0.60     # r >= 它 → 偏高，人工看一眼
DHASH_COPY = 6      # 汉明距离 <= 它 → 几乎同一张图
RANK = {"ok": 0, "high": 1, "copy": 2}


def _gray(path, n=96):
    return np.asarray(Image.open(path).convert("L").resize((n, n), Image.LANCZOS),
                      dtype=np.float64)


def corr(p1, p2, n=96):
    """96x96 灰度、z 归一化后的逐像素相关（对整体构图/明暗分布敏感）。"""
    a, b = _gray(p1, n), _gray(p2, n)
    a = (a - a.mean()) / (a.std() + 1e-6)
    b = (b - b.mean()) / (b.std() + 1e-6)
    return float((a * b).mean())


def _dhash(path, n=32):
    im = Image.open(path).convert("L").resize((n + 1, n), Image.LANCZOS)
    a = np.asarray(im, dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).ravel()


def dhash_dist(p1, p2):
    return int((_dhash(p1) != _dhash(p2)).sum())


def similarity(p1, p2):
    return dict(r=corr(p1, p2), dhash=dhash_dist(p1, p2))


def verdict(r, dh):
    if r >= THR_COPY or dh <= DHASH_COPY:
        return "copy"
    if r >= THR_HIGH:
        return "high"
    return "ok"


def looks_like_content_ref(path):
    """文件名启发式：上一步的草图 = 构图依据，本来就该像。"""
    name = Path(path).name
    s = Path(path).stem.lower()
    return ("sketch" in s) or ("\u8349\u56fe" in name) or s.endswith("_sk")


def check(img, style_refs, content_refs=()):
    """给 gen_figure 直接调：返回 (worst, rows)。rows = [(角色, 名字, r, dhash, 判定)]"""
    rows, worst = [], "ok"
    for role, paths in (("content", list(content_refs)), ("style", list(style_refs))):
        for p in paths:
            d = similarity(img, p)
            v = verdict(d["r"], d["dhash"])
            if role == "content":
                v = "ok"            # 构图依据：像是对的，只报告
            elif RANK[v] > RANK[worst]:
                worst = v
            rows.append((role, Path(p).name, d["r"], d["dhash"], v))
    return worst, rows


def main():
    ap = argparse.ArgumentParser(description="量出图有没有把参考图抄了")
    ap.add_argument("image")
    ap.add_argument("--ref", action="append", default=[],
                    help="风格参考图（必须【不】像才对）")
    ap.add_argument("--content-ref", action="append", default=[],
                    help="构图参考图（上一步的草图，本来就该像）")
    ap.add_argument("--json", default=None, help="把结果写成 json")
    a = ap.parse_args()

    content = list(a.content_ref)
    style = []
    for r in a.ref:
        (content if looks_like_content_ref(r) else style).append(r)

    worst, rows = check(a.image, style, content)
    print("ref_leak_check  %s" % Path(a.image).name)
    print("  参考图                角色      r       dHash   判定")
    for role, name, r, dh, v in rows:
        mark = {"ok": "·", "high": "!", "copy": "X"}[v]
        tag = "构图依据" if role == "content" else "风格参考"
        extra = ""
        if role == "content":
            extra = "（本来就该像）"
        elif v == "copy":
            extra = " <- 疑似照抄这张"
        elif v == "high":
            extra = " <- 偏高，人工看一眼"
        print("  %-20s %s  %+.3f  %5d   %s %s%s"
              % (name[:20], tag, r, dh, mark, v, extra))
    if worst == "copy":
        print("  -> [照抄] 出图与风格参考图几乎一样：参考图选错了。"
              "换「内容不同、风格相同」的；或用 --content-ref 标出草图、"
              "减少风格参考张数。见 SKILL.md「输出变成参考图的内容」一节。")
    elif worst == "high":
        print("  -> [偏高] 没到照抄，但建议人眼对比一眼。")
    else:
        print("  -> [OK] 没有照抄迹象。")
    if a.json:
        Path(a.json).write_text(json.dumps(
            dict(image=str(a.image), worst=worst,
                 rows=[dict(role=x[0], ref=x[1], r=x[2], dhash=x[3], verdict=x[4])
                       for x in rows]), ensure_ascii=False, indent=2), encoding="utf-8")
    return 2 if worst == "copy" else 0


# ★ Windows：stdout 被管道/重定向时是 gbk —— 报告里的中文/✅ 会乱码
#   或被 UnicodeEncodeError 打断（见 scripts/_console.py）。
from _console import init_console

init_console()


if __name__ == "__main__":
    raise SystemExit(main())
