#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pick_layer -- 位图 → 矢量 四档里的【第 ④ 档】：不可见的「拾取层」（点一下 = 一个物理结构）

   ① 位图       客户选定 / 确认的那张 raster
   ② 临摹       raster_to_vector_semantic.py  -> 每个物理元素一个 <g data-element="...">
   ③ 重建       trace_rebuild.py（对象档）/ mesh_tier（光滑档）-> 成品矢量
   ④ 拾取层     本脚本：在成品上再叠一层「每个物理结构一条闭合路径」

为什么要第 ④ 档
    ③ 的成品内部是**几百到几万条 <path>**（碎矩形 / 逐行渐变带 / 线稿）。一次点击命中的是
    **那一条 path**，不是物理对象 —— 于是"点一下球，选中的是一段渐变带"。
    做法：在 <svg> 的最后面加 `<g id="pick">`，里面每个物理结构一条 **闭合路径**，
    `fill-opacity="0" pointer-events="all"`。它什么都不画，但接管点击。

    ★ 一次点击由**最后画的那条路径**决定 ⇒ `--sil` 里的顺序必须 = 图里的真实遮挡
      （back → front）。`pick_verify.py` 的探针表就是拿来验这件事的。

    ★ 子物体（可选）：`--sub` 传 `{"element": {"paths": [d, ...]}}`（例如两个 Pb 核里
      逐核子一条路径）。子路径画在**父级之后** ⇒ 点球选球、点没被切开的区域选核。
      位图把背排的球画在一起、没给边界时，父级就是兜底，保证不存在"点不到"的地方。

用法
    python3 scripts/pick_layer.py mesh.svg --sil build/mesh/_sil.json -o out/mesh_pick.svg
    python3 scripts/pick_layer.py mesh.svg --sil .../_sil.json --sub .../_nuc_balls.json -o out/mesh_pick.svg

输入格式
    --sil  {"element": "<svg path d>", ...}                每个结构一条闭合路径（按 back→front 排列）
    --sub  {"element": {"paths": ["<d>", ...]}, ...}      可选；也可带 count/markers/面积读数

自检（缺一不可）
    1. **不可见**：用 Edge/Chrome 渲染「成品」与「带拾取层的成品」各一次，比 MD5 —— 必须**逐字节相同**。
       ★ 不要用 cairosvg：它不画 <mask>，光滑档的旁衬层会整块丢掉，两次都不一样。
    2. **点得对**：`scripts/pick_verify.py` 出覆盖表 + 探针表（点这里实际选中谁）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(description="add an invisible one-path-per-physics-object pick layer")
    ap.add_argument("svg", help="成品矢量（②/③ 的产物）")
    ap.add_argument("--sil", required=True,
                    help='{"element": "<path d>", ...} —— 每个物理结构一条闭合路径，按 back→front 排列')
    ap.add_argument("--sub", default="",
                    help='可选 {"element": {"paths": [d, ...]}} —— 子物体（如逐核子），画在父级之后')
    ap.add_argument("-o", "--out", required=True, help="输出 svg")
    ap.add_argument("--gid", default="pick", help="拾取层的 <g id>（默认 pick）")
    a = ap.parse_args()

    src = io.open(a.svg, encoding="utf-8", errors="replace").read()
    if "</svg>" not in src:
        sys.exit("no </svg> in %s" % a.svg)
    sil = json.load(io.open(a.sil, encoding="utf-8"))
    subs = {}
    if a.sub and os.path.exists(a.sub):
        subs = json.load(io.open(a.sub, encoding="utf-8"))

    def body(el, d):
        return ('<path id="pick-%s" data-element="%s" data-object="1" fill="#000000" '
                'fill-opacity="0" stroke="none" pointer-events="all" d="%s"/>' % (el, el, d))

    out = ['<g id="%s" data-role="object-pick" data-object="1" '
           'data-note="invisible click targets: one closed path per physics structure; '
           'sub-objects (if any) are painted after their parent so the child wins a click, '
           'while the parent still covers everything the bitmap merges">' % a.gid]
    n_sub = 0
    for el, d in sil.items():
        sub = subs.get(el)
        paths = (sub or {}).get("paths") or []
        if not paths:
            out.append(body(el, d))
            continue
        out.append('<g id="pick-group-%s" data-element="%s" data-object="1" '
                   'data-sub="sub-objects" data-n="%d">' % (el, el, len(paths)))
        out.append(body(el, d))                       # 父级先画
        for i, nd in enumerate(paths, 1):
            out.append('<path id="pick-sub-%s-%02d" data-element="%s" data-object="1" '
                       'data-sub="sub-object" fill="#000000" fill-opacity="0" stroke="none" '
                       'pointer-events="all" d="%s"/>' % (el, i, el, nd))
            n_sub += 1
        out.append("</g>")
    out.append("</g>")

    dst = src.replace("</svg>", "\n".join(out) + "\n</svg>")
    io.open(a.out, "w", encoding="utf-8", newline="\n").write(dst)
    print("wrote %s  (%.2f -> %.2f MB, +%d pick paths, +%d sub-object paths)"
          % (a.out, len(src.encode()) / 1048576., len(dst.encode()) / 1048576., len(sil), n_sub))


if __name__ == "__main__":
    main()
