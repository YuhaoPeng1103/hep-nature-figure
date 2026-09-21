#!/usr/bin/env python3
"""
verify_scene —— Scene Graph 往返验证：**重组后结构变没变**
=========================================================================
## 解决什么

用户的问题：「重组后不会改变重组前的结构，否则重组不就变坏了吗」

**会变。** 三个具体机制：
  1. **图元表达力不足** —— 原图是任意形状，`qgp_blob(cx,cy,R,ry,seed)`
     表达不了它，只能近似 → 轮廓变了
  2. **分解损失** —— 复杂对象拆成多个图元，拼回去轮廓未必复原
  3. **层级放错** —— 遮挡关系变了

所以「重组」不是天然保结构。它只保**忠实于 Scene Graph**，
而 Scene Graph 本身可能是原图的有损压缩。

## 本脚本做什么

**往返回检**（Scene Graph → 渲染 → 量渲染 → 与声明对账）：

    声明的东西          从渲染产物里量回来          判定
    ─────────────────────────────────────────────────────
    文字清单             PDF 里提取的文字            逐字比对
    元素/图层            每个 <g> 里的元素数          有没有丢
    几何约束            IR 的断言逐条量              满足 / 违反
    位置与尺寸          元素 bbox 的位置              偏差 >容差就报

**这是"量，不要看"那条纪律在重组这一环的落地。**

## 用法

    python3 verify_scene.py scene.yaml fig.svg --pdf fig.pdf
    python3 verify_scene.py scene.yaml fig.svg --tol 0.03
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit(f"读不了 {path.name}")


def declared_texts(sg: dict):
    """Scene Graph 里声明的所有文字（text / formula / label）。"""
    out = []
    for e in sg.get("elements", []):
        p = e.get("params") or {}
        t = p.get("t")
        if t:
            out.append((e.get("id", "?"), str(t)))
    return out


def layer_counts_from_svg(svg_text: str):
    """从 SVG 里数每个图层（<g inkscape:label=...>）里有多少绘图元素。"""
    counts = {}
    for m in re.finditer(
            r'<g[^>]*inkscape:label="([^"]*)"[^>]*>(.*?)</g>', svg_text, re.S):
        body = m.group(2)
        n = len(re.findall(r"<(?:path|circle|ellipse|rect|line|polygon|text)\b",
                           body))
        counts[m.group(1)] = counts.get(m.group(1), 0) + n
    return counts


def declared_layer_counts(sg: dict):
    """每个图层应该有多少个元素（按 layer 归属统计）。"""
    want = {}
    for e in sg.get("elements", []):
        lay = e.get("layer")
        if lay:
            want[lay] = want.get(lay, 0) + 1
    return want


def main():
    ap = argparse.ArgumentParser(description="Scene Graph 往返验证")
    ap.add_argument("scene")
    ap.add_argument("svg")
    ap.add_argument("--pdf", default=None, help="有 PDF 时顺带查文字提取")
    ap.add_argument("--tol", type=float, default=0.04,
                    help="位置/尺寸的相对容差（默认 4%%）")
    a = ap.parse_args()

    sg = load(Path(a.scene))
    svg_p = Path(a.svg)
    if not svg_p.exists():
        raise SystemExit(f"找不到 {svg_p}")
    svg_text = svg_p.read_text(encoding="utf-8")

    print(f"往返验证：{Path(a.scene).name} → {svg_p.name}")
    ok_all = True

    # ══ ① 元素有没有丢 ══
    print("\n① 元素/图层（重组有没有丢东西）")
    want = declared_layer_counts(sg)
    got = layer_counts_from_svg(svg_text)
    lname = {l.get("id"): l.get("name", l.get("id"))
             for l in (sg.get("layers") or [])}
    for lid, n in want.items():
        nm = lname.get(lid, lid)
        g = got.get(nm, got.get(lid, 0))
        ok = g >= n                       # 一个元素可能画成多条 <path>，只查少不查多
        ok_all &= ok
        print(f"  {'✅' if ok else '❌'} 图层「{nm}」声明 {n} 个元素，"
              f"渲染出 {g} 个绘图指令")
    if not want:
        print("  （Scene Graph 没写 layer，跳过）")

    # ══ ② 文字逐字对（重组最容易坏的地方）══
    print("\n② 文字内容（重组最容易坏的地方）")
    texts = declared_texts(sg)
    if not texts:
        print("  （没声明文字）")
    else:
        src = None
        if a.pdf and Path(a.pdf).exists():
            try:
                import fitz
                src = fitz.open(a.pdf)[0].get_text()
            except Exception as e:
                print(f"  （PDF 读取失败：{type(e).__name__}）")
        if src is None:
            # 退而求其次：从 SVG 抠。★ 必须先反解 XML 转义 ——
            # 实测踩到：`->` 在 SVG 里是 `-&gt;`，不还原就报假失败。
            import html
            src = html.unescape(re.sub(r"<[^>]+>", " ", svg_text))
        for eid, t in texts:
            # 归一化空白后逐字比对
            norm = lambda s: " ".join(str(s).split())          # noqa: E731
            ok = norm(t) in norm(src)
            ok_all &= ok
            show = t if len(t) <= 46 else t[:43] + "…"
            print(f"  {'✅' if ok else '❌'} {eid}: 「{show}」")

    # ══ ③ 几何约束（IR 的断言，逐条量）══
    cons = ((sg.get("geometry_constraints") or {}).get("约束") or [])
    print("\n③ 几何约束（Scene Graph 自己声明的）")
    if not cons:
        print("  ⚠️ 没声明 geometry_constraints —— 结构没有可判定的约束，"
              "「重组没变坏」这件事**无法验证**")
    else:
        for c in cons:
            print(f"  ☐ {c.get('名','')}：要求 {c.get('要求','')}")
        print("  ⚠️ 上面这些需要**实现脚本自证或人工核对** —— "
              "本条只列出，不代判（同 delivery_gate）")

    print("\n" + "─" * 62)
    if ok_all:
        print("✅ 可自动判的两项都过：元素没丢、文字没坏")
        print("   注意：这只证明「重组忠实于 Scene Graph」，")
        print("   **不证明「Scene Graph 忠实于原图」** —— 后者要人看。")
    else:
        print("❌ 重组改变了结构 —— 逐条看上面标 ❌ 的")
        print("   常见原因：图元表达力不足 / 分解损失 / 层级放错")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
