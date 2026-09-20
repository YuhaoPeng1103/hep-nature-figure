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

# ══════════════════════════════════════════════════════════════
#  无 shapely 时的降级路径
#
#  实测教训：blob() 原本无条件 `return Polygon(pts)`。在没有 shapely 的环境
#  （如 ChatGPT 沙箱）里，Polygon 这个名字根本不存在 → NameError，
#  而且报的是「name 'Polygon' is not defined」，完全指不到"缺 shapely"。
#  demo_timeline / demo_jet_quenching 都走这条路径，于是"开箱即崩"。
#
#  实际只用到 blob() → poly_to_path()，不需要布尔运算。
#  所以这里给一个纯 Python 的环状多边形替身，让这条链路在无 shapely 时照样通。
#  真正需要布尔运算的三个函数（circles_union / discs_union_with_holes /
#  outline_offset）保持"缺 shapely 就明确报错"，不假装能用。
# ══════════════════════════════════════════════════════════════

class _SimplePolygon:
    """shapely.geometry.Polygon 的最小替身：只满足 _rings() 的需要。"""

    geom_type = "Polygon"

    def __init__(self, pts):
        self._pts = [(float(x), float(y)) for x, y in pts]

    @property
    def exterior(self):
        class _Ring:
            def __init__(self, coords):
                self.coords = coords
        # 闭合环：首尾同点，与 shapely 的 coords 行为一致
        return _Ring(self._pts + [self._pts[0]] if self._pts else [])

    @property
    def interiors(self):
        return []

    @property
    def area(self):
        """鞋带公式，仅供 check() 打印。"""
        p = self._pts
        s = sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                for i in range(len(p))) if len(p) >= 3 else 0.0
        return abs(s) / 2.0


def _need_shapely(what):
    raise RuntimeError(
        f"{what} 需要 shapely，但当前环境没有。\n"
        f"  装：pip install shapely\n"
        f"  （若在无法安装包的环境里——例如 ChatGPT 沙箱——请改用 blob() + "
        f"poly_to_path()，那条路径不需要 shapely。）")


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
    if not HAVE_SHAPELY:
        _need_shapely("circles_union（圆的布尔并集）")
    return unary_union([Point(cx, cy).buffer(r, resolution=24)
                        for cx, cy, r in circles])


def discs_union_with_holes(outer, holes):
    """外轮廓 - 内洞。outer/holes 都是 shapely 几何。"""
    if not HAVE_SHAPELY:
        _need_shapely("discs_union_with_holes（差集）")
    return outer.difference(unary_union(holes))


def outline_offset(geom, width):
    """
    外轮廓：把几何向外扩张 width，得到一条"描边带"的基础形体。
    配合 even-odd 填充规则可以画出均匀粗细的外轮廓 ——
    这正是 Nature 图里那种干净边线的做法（等价于描边转路径）。
    """
    if not HAVE_SHAPELY:
        _need_shapely("outline_offset（描边偏移）")
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
    # 无 shapely 时退回纯 Python 替身 —— blob→poly_to_path 这条链不需要布尔运算，
    # 不应该因为环境里没有 shapely 就崩掉（ChatGPT 沙箱实测就缺它）。
    return Polygon(pts) if HAVE_SHAPELY else _SimplePolygon(pts)


def check():
    if not HAVE_SHAPELY:
        # 不报"❌"——因为 blob→poly_to_path 这条最常用的链在无 shapely 时仍然可用。
        # 真正不可用的是三个布尔运算函数。必须说清楚，否则用户以为整个 geom 废了。
        print("⚠️  缺 shapely：布尔运算（circles_union / discs_union_with_holes / "
              "outline_offset）不可用")
        print("   ✅ 但 blob() + poly_to_path() 仍然可用（纯 Python 替身）")
        print("   装：pip install shapely")
        b = blob(0, 0, 60, 40, wobble=0.10, seed=3)
        print(f"   验证有机团块 → {b.geom_type}, 面积 {b.area:.0f}")
        print(f"   验证转 path   → {poly_to_path(b)[:60]}…")
        return True
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
