#!/usr/bin/env python3
"""
pick_best —— 从多张候选里按**闸口的机器项**排序，只把人眼留给入围者
======================================================================

## 为什么需要它（实测，2026-09-27）

`pick_best` 补的是流程里一个一直没人管的缺口：**一次出多张，然后怎么挑？**

实测（UPC 算例）：`qwen-image-3.0` 8 个 seed 出图，只有 3 张同时满足物理约束。
以前的做法是「一张一张跑 check_sketch，人眼逐张看」—— 8 张里 5 张本来
机器就否掉了，人眼白看了 5 次；而且没有排序，容易先看到哪张就选哪张。

现在：`check_sketch.py` 一次吃多张、落 `--json`，本脚本按机器判据排序，
**只把没有硬伤的排到前面**，人眼只审这几张。

## 排序判据（从硬到软）

1. 硬伤条数（0 最优）—— 几何/物理/画布比例，机器否掉的不进人眼
2. 画布比例偏差 —— 比例越接近 IR 越好（IR 的归一化坐标才成立）
3. 软警条数 —— 留白/重心这类「还能用但差一点」
4. **构图保真 r**（大者优）—— 与上一步草图的布局相关，越高越像草图
5. 文件名 —— 只为了结果稳定（同分不乱序）

## 用法

    python3 scripts/check_sketch.py gen/sketch_s*.png --ir ir/xxx.ir.yaml \\
        --json gen/check.json
    python3 scripts/pick_best.py gen/check.json

退出码：0 = 有干净候选（可以进人眼）；1 = **全部有硬伤** —— 别挑，改简报重出。
"""
from __future__ import annotations

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8

import argparse
import json
import sys
from pathlib import Path


def _w(s):
    """显示宽度：CJK 算 2 列（否则中文列全错位）。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def _pad(s, n):
    s = str(s)
    return s + " " * max(0, n - _w(s))


def _rank_key(r):
    """越小越优。None 的比例偏差按 0 处理（没查 = 不罚）。"""
    dev = r.get("ratio_dev")
    fid = r.get("fidelity_r")
    return (len(r.get("hard") or []),
            dev if dev is not None else 0.0,
            len(r.get("soft") or []),
            -(fid if fid is not None else 0.0),
            r.get("file", ""))


def load(paths):
    rows = []
    for p in paths:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        imgs = d.get("images")
        if imgs is None:                      # 也允许直接给一个单张的 dict
            imgs = [d]
        for r in imgs:
            r = dict(r)
            r["_report"] = Path(p).name
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(
        description="按闸口机器项给候选图排序（人眼只审入围的）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("report", nargs="+", help="check_sketch.py --json 写出的报告")
    ap.add_argument("--top", type=int, default=3,
                    help="入围（无硬伤）时最多列几张给人看（默认 3）")
    ap.add_argument("--json", default=None, help="把排序结果也写一份 json")
    a = ap.parse_args()

    rows = load(a.report)
    if not rows:
        raise SystemExit("报告里一张图都没有 —— 先跑 check_sketch.py --json")

    rows.sort(key=_rank_key)
    clean = [r for r in rows if not (r.get("hard") or [])]

    print("=" * 78)
    print("候选排序（%d 张；判据：硬伤 → 比例偏差 → 软警 → 构图保真 → 文件名）"
          % len(rows))
    print("=" * 78)
    print("  " + "  ".join([_pad("#", 2), _pad("文件", 26), _pad("硬伤", 6),
                            _pad("比例偏差", 10), _pad("软警", 6),
                            _pad("保真 r", 9), "为什么不选"]))
    for i, r in enumerate(rows, 1):
        hard = r.get("hard") or []
        dev = r.get("ratio_dev")
        fid = r.get("fidelity_r")
        why = ""
        if hard:
            why = "硬伤：" + "；".join(str(x) for x in hard)[:70]
        elif i == 1:
            why = "★ 首选"
        else:
            why = "干净，但排序更靠后"
        print("  " + "  ".join([
            _pad(i, 2), _pad(str(r.get("file", "?"))[:26], 26), _pad(len(hard), 6),
            _pad(("%.1f%%" % (dev * 100)) if dev is not None else "n/a", 10),
            _pad(len(r.get("soft") or []), 6),
            _pad(("%.3f" % fid) if fid is not None else "n/a", 9), why]))

    print()
    if not clean:
        print("❌ 全部 %d 张都有硬伤 —— **别挑**。改简报/改 IR 重出，不要往下走。"
              % len(rows))
        print("   （硬伤是机器判的几何/物理/画布比例，人眼审也救不回来）")
        return 1
    print("✅ 干净候选 %d 张，人眼只需审这些：%s"
          % (len(clean), ", ".join(str(r.get("file")) for r in clean[:a.top])))
    print("   → 选定后**复制成固定名字**（如 gen/chosen.png）再进下一步，"
          "别让下游脚本去猜 seed。")
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"ranked": [{k: v for k, v in r.items() if k != "_report"}
                        for r in rows],
             "clean": [r.get("file") for r in clean]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("   排序结果已写出 %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
