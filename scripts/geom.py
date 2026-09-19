#!/usr/bin/env python3
"""
geom —— 几何布尔运算 → SVG path

为什么不需要 Inkscape 的布尔运算：
  shapely 就是干这个的，纯 Python、已装、可 pip 安装。
  Inkscape/Illustrator 不可替代的是【人能打开编辑】，不是【会算几何】。

     需求              工具
     布尔并/差/交      shapely（本模块）
     描边偏移/外轮廓    shapely buffer()
     生成 SVG          svg_lib
     渲染导出          cairosvg
     人工精修          Inkscape / Illustrator   ← 唯一必须人的一步

用法：
    from geom import poly_to_path, union_circles, outline_offset
"""
import math

try:
    from shapely.geometry import Point, Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False


def _rings(geom):
    """从 shapely 几何里取出所有外环坐标（支持 Polygon / MultiPolygon）"""
    if geom.geom_type == "Polygon":
        yield list(geom.exterior.coords)
        for h in geom.interiors:
            yield list(h.coords)
    elif geom.geom_type == "MultiPolygon":
        for g in geom.geoms:
            yield from _rings(g)


def poly_to_path(geom, precision=2, invert_y=False):
    """shapely 几何 → SVG path 的 d 属性（支持多块 + 内洞）。"""
    parts = []
    for ring in _rings(geom):
        if len(ring) < 3:
            continue
        pts = [(x, -y if invert_y else y) for x, y in ring]
        d = f"M {pts[0][0]:.{precision}f} {pts[0][1]:.{precision}f} "
        d += " ".join(f"L {x:.{precision}f} {y:.{precision}f}" for x, y in pts[1:])
        parts.append(d + "Z")
    return " ".join(parts)


def circles_union(circles):
    """多个圆求并集。circles = [(cx, cy, r), ...]"""
    return unary_union([Point(cx, cy).buffer(r, resolution=24)
                        for cx, cy, r in circles])


def discs_union_with_holes(outer, holes):
    """外轮廓 - 内洞。outer/holes 都是 shapely 几何。"""
    return outer.difference(unary_union(holes))


def outline_offset(geom, width):
    """
    外轮廓：把几何向外扩张 width，得到一条"描边带"的基础形体。
    配合 even-odd 填充规则可以画出均匀粗细的外轮廓 ——
    这正是 Nature 图里那种干净边线的做法（等价于描边转路径）。
    """
    return geom.buffer(width, join_style=2, mitre_limit=3.0)


def blob(cx, cy, rx, ry, wobble=0.0, n=48, seed=0):
    """
    有机团块：带正弦扰动的椭圆（比正椭圆更像手绘/膨胀的火球边界）。
    wobble 是扰动幅度（相对半径）。
    """
    import random
    rng = random.Random(seed)
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        k = 1.0
        if wobble:
            k += wobble * (0.6 * math.sin(2 * t + ph[0])
                           + 0.3 * math.sin(3 * t + ph[1])
                           + 0.1 * math.sin(5 * t + ph[2]))
        pts.append((cx + rx * k * math.cos(t), cy + ry * k * math.sin(t)))
    return Polygon(pts)


def check():
    if not HAVE_SHAPELY:
        print("❌ 缺 shapely。安装：pip install shapely")
        return False
    print(f"✅ shapely {__import__('shapely').__version__}")
    a = circles_union([(0, 0, 40), (50, 0, 40), (25, 30, 30)])
    print(f"   三圆并集 → {a.geom_type}, 面积 {a.area:.0f}")
    o = outline_offset(a, 6)
    print(f"   向外偏移 6 → 面积 {o.area:.0f}（可用于画外轮廓）")
    b = blob(0, 0, 60, 40, wobble=0.10, seed=3)
    print(f"   有机团块 → 面积 {b.area:.0f}")
    return True


if __name__ == "__main__":
    check()
