#!/usr/bin/env python3
"""
scene_render —— Scene Graph → SVG 的**确定性重组后端**
=========================================================================
## 补的是哪一环

    看懂这张图  →  建 Scene Graph  →  【确定性重组】  →  矢量
     （模型）       （模型，结构化）      ← 本脚本 →        SVG

**为什么需要它**（实测过两条路，都不行）：

| 路 | 为什么不行 |
|---|---|
| 像素描摹（`raster_to_vector.py`） | **没有理解**：文字碎成色块、渐变退化成色阶台阶 |
| 让 GPT 看着位图重画 | **有理解但不忠实、不确定**：会漂移、会自己发明、两次不一样 |

**第三条路**：模型只负责「**看懂并写出结构化描述**」（Scene Graph），
**重组交给确定性代码**。理解力来自模型，忠实度与可复现性来自"重组是代码"。

## 为什么这就解决了可复现性

**同一份 Scene Graph → 逐字节相同的 SVG。** 不是"同 prompt 两次一样"，
而是"描述定了，产物就定了"。参考图库里的图只要 Scene Graph 定了，
重组结果永远一致。

## Scene Graph 的格式

在 `ir_to_scene.py` 用的可执行 IR 上扩了三样（用户点名要的）：

```yaml
figure:
  canvas: {w: 1400, h: 560}

layers:                       # ★ 层级：有名字的组，不是按颜色分
  - {id: bg,    name: "背景与衬板"}
  - {id: medium, name: "QGP 介质"}
  - {id: labels, name: "标注"}

elements:
  - id: E1
    layer: medium            # ★ 归属哪个层（不再靠 z 推）
    primitive: qgp_blob
    params: {cx: 0.44, cy: 0.50, R: 0.185, ry: 0.78, seed: 5}
    z: 1

  - id: T1
    layer: labels
    primitive: text          # ★ 文字是独立类型（不再是通用 label）
    params: {x: 0.5, y: 0.08, t: "Global spin polarization", size: 17}

  - id: F1
    layer: labels
    primitive: formula       # ★ 公式：Unicode 直写，不用 LaTeX
    params: {x: 0.5, y: 0.9, t: "P_H = 0.052 ± 0.003", size: 13}
```

## 用法

    python3 scene_render.py scene.yaml -o fig.svg
    python3 scene_render.py scene.yaml -o fig.svg --png fig.png --pdf fig.pdf
    python3 scene_render.py scene.yaml --check      # 只校验
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cartoon_lib import PRIMITIVES, Cartoon  # noqa: E402
from ir_to_scene import (PARAM_UNITS, _FALLBACK, _signature,  # noqa: E402
                         normalise_params)

# 本渲染器额外支持的两个「语义」图元 —— 它们不是画法，是内容类型
SEMANTIC = {"text", "formula"}


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
        raise SystemExit(f"读不了 {path.name}：无 PyYAML 且不是 JSON")


def check(sg: dict) -> list:
    """校验 Scene Graph。返回问题列表。"""
    probs = []
    if not sg.get("elements"):
        probs.append("没有 elements")
        return probs
    layer_ids = {l.get("id") for l in (sg.get("layers") or [])}
    seen_ids = set()
    for e in sg["elements"]:
        eid = e.get("id", "?")
        if eid in seen_ids:
            probs.append(f"{eid} 重复（id 必须唯一 —— 重组时靠它定位）")
        seen_ids.add(eid)

        prim = e.get("primitive", "")
        if prim not in PRIMITIVES and prim not in SEMANTIC:
            probs.append(f"{eid}.primitive=`{prim}` 不认识")
        elif prim not in SEMANTIC:
            sig = _signature(prim)
            if sig:
                given = set((e.get("params") or {}).keys())
                for k in given:
                    if k not in sig:
                        probs.append(
                            f"{eid}.params.{k} 不是 {prim}() 的参数")
                import inspect
                try:
                    ps = inspect.signature(getattr(Cartoon, prim)).parameters
                    miss = [n for n, p in ps.items() if n != "self"
                            and p.default is inspect.Parameter.empty
                            and n not in given]
                    if miss:
                        probs.append(f"{eid} 缺 {prim}() 必填参数：{miss}")
                except (TypeError, ValueError):
                    pass

        lay = e.get("layer")
        if lay and layer_ids and lay not in layer_ids:
            probs.append(f"{eid}.layer=`{lay}` 不在 layers 里")
        if e.get("physics_role") in (None, "", "装饰"):
            probs.append(f"{eid} 缺 physics_role")
    return probs


def render(sg: dict) -> Cartoon:
    """确定性重组：同一份 Scene Graph 永远出同一张 SVG。"""
    fig = sg.get("figure", {})
    cv = fig.get("canvas") or {}
    W, H = float(cv.get("w", 1400)), float(cv.get("h", 560))
    c = Cartoon(int(W), int(H))

    layers = sg.get("layers") or []
    # 没声明 layers 就按 z 分一个兜底层
    if not layers:
        layers = [{"id": "__all__", "name": "全部"}]
    layer_names = {l["id"]: l.get("name", l["id"]) for l in layers}

    # 按【层顺序】再按【z】排 —— 层是显式的，不再靠 z 推层级
    order = {l["id"]: i for i, l in enumerate(layers)}
    elems = sorted(sg["elements"],
                   key=lambda e: (order.get(e.get("layer", "__all__"), 0),
                                  e.get("z", 0)))

    cur = None
    for e in elems:
        lay = e.get("layer", "__all__")
        if lay != cur:                       # 换层就开新 <g>，带名字
            if cur is not None:
                c.end_layer()
            c.begin_layer(lay, layer_names.get(lay, lay))
            cur = lay

        prim = e.get("primitive")
        params = e.get("params") or {}

        if prim in SEMANTIC:
            # 文字 / 公式：Unicode 直写，保持可编辑（Nature 硬要求）
            t = params.get("t", "")
            x = float(params.get("x", 0.5)) * W
            y = float(params.get("y", 0.5)) * H
            c.label(x, y, t, size=params.get("size", 15),
                    anchor=params.get("anchor", "middle"),
                    weight=params.get("weight", ""))
        else:
            args, _unknown = normalise_params(prim, params, W, H)
            getattr(c, prim)(**args)

    if cur is not None:
        c.end_layer()
    return c


def main():
    ap = argparse.ArgumentParser(
        description="Scene Graph → 确定性 SVG 重组")
    ap.add_argument("scene", help="Scene Graph（yaml / json）")
    ap.add_argument("-o", "--out", default="fig.svg")
    ap.add_argument("--png", default=None)
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    p = Path(a.scene)
    if not p.exists():
        raise SystemExit(f"找不到 {p}")
    sg = load(p)
    probs = check(sg)

    n = len(sg.get("elements", []))
    nl = len(sg.get("layers", []) or [])
    print(f"Scene Graph: {p.name}")
    print(f"  元素 {n} 个 | 图层 {nl} 个")
    if probs:
        print(f"\n❌ {len(probs)} 处不合规：")
        for x in probs[:15]:
            print(f"   · {x}")
        if a.check:
            return 1
    else:
        print("✅ 合规")

    if a.check:
        return 0

    c = render(sg)
    c.save(a.out)
    outs = [a.out]
    if a.png:
        c.render(a.png, width=1900)
        outs.append(a.png)
    if a.pdf:
        c.render(a.pdf)
        outs.append(a.pdf)
    print(f"\n已输出 {' / '.join(outs)}")
    print(f"  图层：{', '.join(l.get('name', l.get('id')) for l in (sg.get('layers') or []) ) or '（未声明）'}")
    print("\n★ 确定性：同一份 Scene Graph 重组出的 SVG 逐字节相同。")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
