#!/usr/bin/env python3
"""
raster_to_vector —— 位图 → 分层矢量（"GPT 出图 → skill 精修"这条路的第一半）
=========================================================================
## 这条路解决什么

模型用图像生成出的图**好看但不可编辑**（位图、文字不可选、不能改字号）。
本脚本把它转成**可分层的矢量**，交出"可编辑"。

## ★ 混合临摹：图形逐像素 + 文字重建（2026-09-21）

**为什么必须混合**：Nature 硬性要求**文字可编辑**。
纯临摹出来的文字是**轮廓路径** —— `check_delivery.py` 会判"文字不可提取"= 不合规。

所以流程是：

   ① 模型看图 → 标出「哪些区域是文字」+「写的是什么」（它读得出来）
   ② 本脚本：**文字区域先用周围底色擦掉**，其余部分逐像素临摹
   ③ 文字用真 <text> 写回去（位置/字号/内容照模型标的）

**这样既拿到像素级忠实，又保住文字可编辑。**

用法：
    python3 raster_to_vector.py fig.png -o fig.svg --text-spec texts.yaml

texts.yaml（模型看图后写）：
    texts:
      - {content: "escaping jet", x: 0.62, y: 0.10, size: 13, anchor: start}
      - {content: "QGP medium",   x: 0.35, y: 0.78, size: 15}

## ★ 本质权衡（必须先说清，否则会失望）

**描摹是"压平成色块"** —— 它会把渐变、柔和光影、抗锯齿过渡
统统变成一级一级的台阶。**而那些恰恰是让图好看的东西。**

所以这条路换来的是「可编辑」，代价是「变平」。
色阶数（`--levels`）就是这个权衡的旋钮：
  少 → 干净、路径少、但更平
  多 → 更接近原图、但路径爆炸、文件巨大

## 它做不了、必须人/模型补的三件事

脚本会在报告里逐条列出：
  1. **文字** —— 若**没给 `--text-spec`**，文字会被转成路径（描摹不认识字）。需要人/模型照原图重写成 `<text>`
     （不做这一步的话，`check_delivery.py` 会判"文字不可提取"= 不合规）
  2. **图层是"按颜色"分的，不是按语义** —— 需要重新归组成
     「介质/核/喷注/标注」这类有含义的图层
  3. **渐变退化成了色阶** —— 需要把连续几级合并回一个 `linearGradient`

## 用法

    python3 raster_to_vector.py gpt_output.png -o refined.svg --levels 12
    python3 raster_to_vector.py gpt_output.png -o refined.svg --levels 24 --tol 1.2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ══════════════════════════════════════════════════════════════
def get_tracer():
    """
    轮廓提取后端。优先 cv2（成熟快），退到 skimage。
    两个都没有就明确报错——**不假装能做**。
    """
    try:
        import cv2
        return "cv2", cv2
    except ImportError:
        pass
    try:
        from skimage import measure  # noqa: F401
        return "skimage", measure
    except ImportError:
        raise SystemExit(
            "描摹需要轮廓提取后端，但 cv2 和 skimage 都没有。\n"
            "  装任一个：pip install opencv-python-headless  或  pip install scikit-image\n"
            "  注意：ChatGPT 沙箱里这两个可能都没有 —— 那条环境请改用\n"
            "  「模型直接写 SVG」的路线，不要走描摹。")


def quantize(img: Image.Image, levels: int):
    """
    颜色量化 → (调色板, 索引图)。用 PIL 自带的中位切分，无第三方依赖。
    """
    q = img.convert("RGB").quantize(colors=levels, method=Image.MEDIANCUT,
                                    dither=Image.Dither.NONE)
    pal = q.getpalette()[: levels * 3]
    colors = [tuple(pal[i * 3:i * 3 + 3]) for i in range(levels)]
    return colors, np.asarray(q, dtype=np.int32)


def trace_mask(mask, backend, mod, tol):
    """二值 mask → 多边形列表（每个是 [(x,y), ...]）。坐标已按 tol 简化。"""
    polys = []
    m = (mask.astype(np.uint8)) * 255
    if backend == "cv2":
        cnts, _ = mod.findContours(m, mod.RETR_CCOMP, mod.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            if len(c) < 3:
                continue
            ap = mod.approxPolyDP(c, tol, True).reshape(-1, 2)
            if len(ap) >= 3:
                polys.append(ap.tolist())
    else:
        for c in mod.find_contours(mask.astype(float), 0.5):
            if len(c) < 3:
                continue
            ap = mod.approximate_polygon(c, tolerance=tol)
            if len(ap) >= 3:
                polys.append([(float(x), float(y)) for y, x in ap])
    return polys


def load_spec(p: Path) -> dict:
    txt = p.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(txt)
    except ImportError:
        pass
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        raise SystemExit(f"读不了 {p.name}：无 PyYAML 且不是 JSON")


def _box(tx, W, H):
    """文字项 → 像素 bbox。给了 w/h 就用，否则按内容长度×字号估。"""
    cx, cy = float(tx.get("x", 0.5)) * W, float(tx.get("y", 0.5)) * H
    size = float(tx.get("size", 13))
    n = len(str(tx.get("content", "")))
    w = float(tx.get("w")) * W if tx.get("w") else n * size * 0.62
    h = float(tx.get("h")) * H if tx.get("h") else size * 1.6
    anchor = tx.get("anchor", "middle")
    x0 = cx - w / 2 if anchor == "middle" else (cx if anchor == "start" else cx - w)
    return int(x0 - 3), int(cy - h * 0.78), int(x0 + w + 3), int(cy + h * 0.26)


def erase_text_regions(img: Image.Image, texts) -> Image.Image:
    """
    把文字区域用**周围底色**填掉 —— 这样描摹时不会描出文字轮廓。
    底色从区域外圈一圈像素取中位数（比取全图背景稳，应付渐变背景）。
    """
    a = np.asarray(img.convert("RGB")).copy()
    H, W = a.shape[:2]
    for tx in texts:
        x0, y0, x1, y1 = _box(tx, W, H)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        m = 3
        ring = np.concatenate([
            a[max(0, y0 - m):y0, x0:x1].reshape(-1, 3),
            a[y1:min(H, y1 + m), x0:x1].reshape(-1, 3),
            a[y0:y1, max(0, x0 - m):x0].reshape(-1, 3),
            a[y0:y1, x1:min(W, x1 + m)].reshape(-1, 3),
        ]) if True else None
        if ring is None or ring.size == 0:
            continue
        bg = np.median(ring, axis=0).astype(np.uint8)
        a[y0:y1, x0:x1] = bg
    return Image.fromarray(a)


def text_el(tx, W, H, i):
    """一条文字 → SVG <text>。字体按字符集自动选（见 svg_lib）。"""
    import svg_lib
    content = str(tx.get("content", ""))
    x = float(tx.get("x", 0.5)) * W
    y = float(tx.get("y", 0.5)) * H
    size = float(tx.get("size", 13))
    anchor = tx.get("anchor", "middle")
    color = tx.get("color", "#0d0d0d")
    cjk = any("　" <= c <= "鿿" for c in content)
    fam = svg_lib.FONT_CJK if cjk else svg_lib.FONT_LATIN
    return (f'<text id="txt{i}" x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'font-family="{fam}" fill="{color}" text-anchor="{anchor}">'
            f'{svg_lib.esc(content)}</text>')


def point_in_poly(pt, poly):
    """射线法：点是否在多边形内。"""
    x, y = pt
    n, inside = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
                inside = not inside
        j = i
    return inside


def assign_group(poly, groups, W, H):
    """
    给一条描摹路径定归属。**最内层优先** ——
    否则"介质里的核"会被介质那层吃掉。
    返回 (组名, 该组面积) 或 (None, inf)。
    """
    best, best_area = None, float("inf")
    for g in groups:
        pts = g.get("at") or []
        if pts and isinstance(pts[0], (int, float)):
            pts = [pts]                       # 允许 [x,y] 简写
        area = poly_area(poly)
        for p in pts:
            px, py = float(p[0]) * W, float(p[1]) * H
            if point_in_poly((px, py), poly) and area < best_area:
                best, best_area = g.get("name"), area
    return best, best_area


def poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def main():
    ap = argparse.ArgumentParser(description="位图 → 分层矢量")
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default="refined.svg")
    ap.add_argument("--levels", type=int, default=12,
                    help="色阶数。**这是「好看 vs 可编辑」的主旋钮**："
                         "少=干净但更平，多=接近原图但路径爆炸（默认 12）")
    ap.add_argument("--tol", type=float, default=1.0,
                    help="路径简化容差（px）。越大越简洁（默认 1.0）")
    ap.add_argument("--min-area", type=float, default=12.0,
                    help="丢掉小于此面积的多边形（px²），防噪点路径（默认 12）")
    ap.add_argument("--groups", default=None,
                    help="语义分组标注（yaml/json）：模型看图后给每个语义对象一个"
                         "代表点，工具把描摹出的路径按归属打标。"
                         "★ 默认**不改绘制顺序** —— 渲染逐像素不变，只加归属信息")
    ap.add_argument("--regroup", action="store_true",
                    help="真正按语义重排图层顺序。⚠️ 会改变遮挡关系，"
                         "**必须人看图确认**（默认关）")
    ap.add_argument("--text-spec", default=None,
                    help="文字清单（yaml/json）：模型看图后标的文字位置与内容。"
                         "给了它就做混合临摹 —— 文字区域擦掉、用真 <text> 重写")
    ap.add_argument("--bg-tolerance", type=float, default=8.0,
                    help="与最外层颜色相差小于此值的色阶并进背景（默认 8）")
    a = ap.parse_args()

    src = Path(a.image)
    if not src.exists():
        raise SystemExit(f"找不到 {src}")
    img = Image.open(src).convert("RGB")
    W, H = img.size

    backend, mod = get_tracer()
    group_hits, group_map = {}, []

    groups = []
    if a.groups:
        gp = Path(a.groups)
        if not gp.exists():
            raise SystemExit(f"找不到 {gp}")
        groups = (load_spec(gp).get("groups") or [])
        if groups and a.regroup:
            print("⚠️ --regroup：按语义重排图层顺序 —— "
                  "**会改变遮挡关系，必须人看图确认**")

    # ── ★ 混合临摹：先用周围底色擦掉文字区域 ──
    texts = []
    if a.text_spec:
        sp = Path(a.text_spec)
        if not sp.exists():
            raise SystemExit(f"找不到 {sp}")
        spec = load_spec(sp)
        texts = spec.get("texts") or []
        if texts:
            img = erase_text_regions(img, texts)
            print(f"混合临摹：擦掉 {len(texts)} 处文字区域，改用真 <text> 重写")

    colors, idx = quantize(img, a.levels)

    # 统计每色占比
    counts = np.bincount(idx.ravel(), minlength=len(colors))
    order = np.argsort(-counts)                      # 从多到少画 = 背景在底

    print(f"源图 {W}×{H}  |  描摹后端 {backend}  |  色阶 {a.levels}")
    print(f"色调板：{len(colors)} 色，最大占比 "
          f"{counts[order[0]] / idx.size * 100:.1f}%")

    body = []
    total_paths = 0
    dropped = 0
    for rank, ci in enumerate(order):
        if counts[ci] == 0:
            continue
        r, g, b = colors[ci]
        mask = (idx == ci)
        polys = trace_mask(mask, backend, mod, a.tol)
        keep = []
        for p in polys:
            if poly_area(p) >= a.min_area:
                keep.append(p)
            else:
                dropped += 1
        if not keep:
            continue
        total_paths += len(keep)
        label = f"{rank:02d} {('#%02x%02x%02x' % (r, g, b))}"
        body.append(f'<g inkscape:label="{label}">')
        d_all = []
        for p in keep:
            d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in p) + " Z"
            d_all.append(d)
            if groups:
                gname, _ = assign_group(p, groups, W, H)
                key = gname or "（未归属）"
                group_hits[key] = group_hits.get(key, 0) + 1
                group_map.append((rank, len(d_all) - 1, gname or "（未归属）"))
        # ★ 必须**合并成一个 <path>**：`fill-rule="evenodd"` 靠同色多边形
        #   互相抵消来产生洞（环形就是这么描出来的）。
        #   拆成独立 <path> 各自填充 → **洞会消失**，图就变了。
        #   （实测：拆开后最大像素差 255。）
        #   所以归属信息不能挂在 path 上，改用旁路索引（见文件末尾的 <metadata>）。
        body.append(f'<path d="{" ".join(d_all)}" fill="#{r:02x}{g:02x}{b:02x}" '
                    f'fill-rule="evenodd"/>')
        body.append('</g>')

    # ── ★ 文字层：真 <text>，可编辑（Nature 硬要求）──
    if texts:
        body.append('<g inkscape:label="ZZ 文字（可编辑）">')
        for i, tx in enumerate(texts, 1):
            body.append(text_el(tx, W, H, i))
        body.append('</g>')

    # ── 语义归属索引（旁路，不改绘制结构）──
    if groups and group_map:
        import json as _json
        body.append("<metadata>")
        body.append("<!-- 语义归属索引：[颜色序, 该颜色内第几个子路径, 组名]")
        body.append("     为什么不做成 <g> 分组：合并路径的 evenodd 靠同色多边形")
        body.append("     互相抵消产生洞，拆开洞就没了。所以归属只能旁路记录。 -->")
        body.append(_json.dumps({"group_index": group_map,
                                 "groups": [g.get("name") for g in groups]},
                                ensure_ascii=False))
        body.append("</metadata>")

    svg = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        *body,
        '</svg>'])
    Path(a.out).write_text(svg, encoding="utf-8")

    size_kb = Path(a.out).stat().st_size / 1024
    print(f"\n已输出 {a.out}  —  {total_paths} 条路径 / {len(body)//3} 个颜色图层"
          f" / {size_kb:.0f} KB")
    if dropped:
        print(f"（丢弃 {dropped} 个小多边形，< {a.min_area}px²）")
    if groups:
        print("\n语义归属（**只打标，未改绘制顺序** —— 渲染与不归组时相同）：")
        for g in groups:
            n = group_hits.get(g.get("name"), 0)
            print(f"  · {g.get('name')}: {n} 条路径")
        un = group_hits.get("（未归属）", 0)
        if un:
            print(f"  · （未归属）: {un} 条 —— 代表点没落进去，"
                  f"补个点或调位置即可")

    # ══ 报告：脚本做不到、必须补的三件事 ══
    print("""
────────────────────────────────────────────────────────────────
⚠️  描摹只完成了一半。以下三件必须人/模型补，否则过不了门禁：

1. **文字** —— 若**没给 `--text-spec`**，文字会被转成路径（描摹不认识字）。
   → 照原图把标题/标签重写成真正的 <text>，否则
     check_delivery.py 会判「文字不可提取」= 不合规（Nature 要求可编辑文字）。

2. **图层是按【颜色】分的，不是按语义**。
   → 重新归组成「介质 / 入射核 / 喷注 / 标注」这类有含义的图层，
     否则人精修时找不到东西。

3. **渐变退化成了色阶**（这正是"变平"的来源）。
   → 把连续几级同色系合并回一个 <linearGradient> / <radialGradient>。
     色阶数调高能减轻，但路径数会涨。

补完跑：
    python3 audit_composition.py refined.pdf
    python3 check_delivery.py refined.pdf
    python3 repair_brief.py refined.svg --profile style-profiles.json
────────────────────────────────────────────────────────────────""")


if __name__ == "__main__":
    main()
