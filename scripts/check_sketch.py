#!/usr/bin/env python3
"""
check_sketch —— 中间稿检查（路径 2 的闸口）
=========================================================================
## 它在流程里的位置

    草图/描述 ──生图──▶ 【更好的草图】 ──★这里检查★──▶ 成品位图 ──绘画──▶ 矢量

## ★ 为什么必须分成两类检查

**机器判不了物理。** 图像模型可能把喷注画反、把非中心碰撞画成同心、
把 L 画成面内箭头 —— 这些从像素上量不出来，只能"看懂图"才能判。

所以本脚本输出两块：

  ■ 自动测到的    构图/风格这类**能量**的（留白、内容边界、偏心、饱和度）
  ■ 必须你回答的  IR 的 `geometry_constraints` **逐条变成待答问题**
                  —— 让"检查物理"从一句原则变成一个必须填的动作

**有任何一条答"否" → 改 prompt 重出，不要往下走。**
往下走的代价是：错误会被带进成品位图、再带进矢量，越往后越贵。

## 用法

    python3 check_sketch.py sketch_v1.png --ir ir/xxx.ir.yaml
    python3 check_sketch.py sketch_v1.png --ir ir/xxx.ir.yaml \\
        --profile assets/style-profiles.json --class "T3-schematic (illustration)"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_ir(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit(f"读不了 {path.name}：无 PyYAML 且不是 JSON")


def content_stats(img: Image.Image):
    """
    内容边界 / 留白 / 重心。白底图里"非白"的就是内容。
    用途：判"内容是不是挤在一角""四周有没有被裁"。
    """
    a = np.asarray(img.convert("L")).astype(np.float32) / 255.0
    nonbg = a < 0.94
    if not nonbg.any():
        return None
    ys, xs = np.where(nonbg)
    H, W = a.shape
    x0, x1 = float(xs.min()) / W, float(xs.max()) / W
    y0, y1 = float(ys.min()) / H, float(ys.max()) / H
    cx, cy = float(xs.mean()) / W, float(ys.mean()) / H
    # 3×3 空格检测
    empty = []
    for i in range(3):
        for j in range(3):
            cell = nonbg[int(i * H / 3):int((i + 1) * H / 3),
                         int(j * W / 3):int((j + 1) * W / 3)]
            if cell.mean() < 0.002:
                empty.append((j, i))
    return {"bbox": (round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)),
            "centroid": (round(cx, 3), round(cy, 3)),
            "whitespace": round(1 - nonbg.mean(), 4),
            "empty_cells": empty}


def main():
    ap = argparse.ArgumentParser(description="中间稿检查（路径 2 的闸口）")
    ap.add_argument("image")
    ap.add_argument("--ir", required=True, help="对应的 IR —— 几何约束从它来")
    ap.add_argument("--profile", help="风格档案（可选）")
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--canvas", help="IR 声明的画布 WxH，用于查比例是否被改")
    a = ap.parse_args()

    img_path = Path(a.image)
    if not img_path.exists():
        raise SystemExit(f"找不到 {img_path}")
    img = Image.open(img_path)
    W, H = img.size
    ir = load_ir(Path(a.ir))

    print(f"【中间稿检查】{img_path.name}")
    print(f"  尺寸 {W}×{H}  宽高比 {W/H:.2f}")

    # 画布比例是否照 IR 走
    cv = (ir.get("figure") or {}).get("canvas") or {}
    if cv.get("w") and cv.get("h"):
        want = cv["w"] / cv["h"]
        dev = abs(W / H - want) / want
        flag = "✅" if dev < 0.12 else "❌"
        print(f"  {flag} IR 声明的比例 {want:.2f}，实际 {W/H:.2f}"
              f"（偏差 {dev*100:.0f}%）")
        if dev >= 0.12:
            print("     → 比例被改了。比例变了，IR 里的归一化坐标全部失效。")
    print()

    # ══ 一、自动测 ══
    print("■ 自动测到的（这些机器能判）")
    st = content_stats(img)
    hard, soft = [], []
    if st is None:
        print("  ❌ 整张图几乎是白的 —— 没画出东西")
        hard.append("图为空白")
    else:
        print(f"  内容边界 (x0,y0,x1,y1) = {st['bbox']}")
        print(f"  留白 {st['whitespace']:.3f}")
        print(f"  内容重心 ({st['centroid'][0]:.2f}, {st['centroid'][1]:.2f})")
        x0, y0, x1, y1 = st["bbox"]
        if min(x0, y0, 1 - x1, 1 - y1) < 0.01:
            print("  ❌ 内容贴边/出界 —— 会被裁")
            hard.append("内容贴边或出界")
        if not (0.28 < st["centroid"][0] < 0.72):
            print("  ⚠️ 内容重心偏左右 —— 构图可能失衡")
            soft.append("重心偏左右")
        if st["empty_cells"]:
            pos = ", ".join(f"第{j+1}列第{i+1}行" for j, i in st["empty_cells"])
            print(f"  ⚠️ {len(st['empty_cells'])}/9 格全空（{pos}）—— 构图可能失衡")
            soft.append("留白失衡")
        else:
            print("  ✅ 9 格都有内容")

    # 风格（有档案时）
    if a.profile and Path(a.profile).exists():
        try:
            from style_bench import measure, METRIC_ROBUST
            pd = json.loads(Path(a.profile).read_text(encoding="utf-8"))
            ent = pd.get(a.want_class) or pd.get("T3-schematic (illustration)") \
                or pd[list(pd)[0]]
            stl = ent.get("style", {})
            m = measure(str(img_path))
            print(f"\n  风格 vs 档案「{ent.get('name','?')}」：")
            for k, v in m.items():
                e = stl.get(k)
                if not isinstance(e, dict) or not METRIC_ROBUST.get(k, True):
                    continue
                lo, hi = e.get("p25"), e.get("p75")
                if lo is None:
                    continue
                inr = lo <= v <= hi
                print(f"    {'✅' if inr else '  '} {k:<16}{v:>8.4f}"
                      f"   类内区间 [{lo:.4f}, {hi:.4f}]")
            print("    （中间稿不追风格 —— 这些只作参考，别为它们改构图）")
        except Exception as e:
            print(f"  （风格量测跳过：{type(e).__name__}）")
    print()

    # ══ 二、必须人/模型回答 ══
    cons = ((ir.get("geometry_constraints") or {}).get("约束") or [])
    print("■ 必须【看图】逐条回答的（机器判不了物理）")
    print("  ⚠️ 这一节不能跳。图像模型不知道物理，错就错在这里。")
    print()
    if cons:
        for i, c in enumerate(cons, 1):
            print(f"  {i}. {c.get('名','')}")
            if c.get("量"):
                print(f"     量：{c.get('量')}")
            if c.get("要求"):
                print(f"     要求：{c.get('要求')}")
            print("     图上是否满足？  □ 是   □ 否 —— 若否，错在哪：__________")
            print()
    else:
        print("  （IR 里没写 geometry_constraints —— 这条图缺了物理约束，"
              "建议先补上再检查）")
        print()

    # ══ 结论 ══
    print("─" * 62)
    if hard:
        print(f"❌ 自动检查不过（{len(hard)} 项）：{'; '.join(hard)}")
        print("   → 改 prompt 重出，不要往下走。")
    elif cons:
        print("⏸  自动检查通过，但**上面那一串问题还没答**。")
        print("   逐条答完、全部为「是」才能往下走 ——")
        print("   往下走的代价是：错误会被带进成品位图、再带进矢量，越往后越贵。")
    else:
        print("✅ 自动检查通过（但没有几何约束可核，物理没人把过关）")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
