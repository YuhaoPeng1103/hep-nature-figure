#!/usr/bin/env python3
"""
style_bench —— 图的风格度量与基准比对

两个用途：
  1. 建基准：扫一批期刊图，量出风格统计分布 → "Nature 级"的量化定义
  2. 做检查：新生成的图拿同一套指标量，看偏离基准多少

为什么需要：
  "达到 Nature 级质量"是个无法验收的说法。但可以拆成可量的指标：
  配色饱和度分布、线宽分布、留白比例、渐变占比、文字相对大小……
  量出来就能说"你这张比基准暗 30%、线粗一倍、留白少一半"——
  **这比"不好看"有用得多。**

⚠️⚠️ 最重要的使用纪律：这些指标是【诊断工具】，不是【优化目标】。

   做过闭环验证（改图 → 重新度量），结论：
     · 指标能响应修改（饱和度 +59%→-18%、边密度 -28%→+3%，按预期收敛）
     · 但指标互相耦合：压暗描边改善了边密度，却让渐变占比崩了 45%
     · 更糟的是，按指标整体调会把「不该动的地方」一起调——
       实测把平面压暗了，视觉上反而更不像参考图

   根因：这些是**全局平均量**，分不清"该压暗的描边"和"该保持浅色的平面"。

   正确用法：
     1. 量 → 发现问题
     2. 判断 → 是配色问题，还是别的？（要人/模型判断，指标判断不了）
     3. **只改那一个地方，别动全局**
     4. 再量 → 确认那项收敛，且别项没崩
     5. 看图 → 确认视觉真的更好了

   它能做：抓明显离群、定位往哪看。
   它不能做：当达标判据、替代看图。
   **跳到「把所有指标都调到匹配」= 优化指标而不是优化图。**

用法：
    # 建基准（扫一个目录，输出基准 JSON）
    python3 style_bench.py build refs_extracted/ -o style_baseline.json

    # 检查单张图
    python3 style_bench.py check myfigure.png -b style_baseline.json

    # 只看单张图的指标
    python3 style_bench.py measure myfigure.png
"""
import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2  # 可选，用于更好的边缘检测
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


# ---------------------------------------------------------------- 指标
def _load(path, max_side=700):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = max_side / max(w, h)
    if s < 1:
        im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    return np.asarray(im).astype(np.float32) / 255.0


def m_whitespace(a):
    """留白比例：近白像素占比。期刊图通常留白较多。"""
    lum = a.mean(axis=2)
    return float((lum > 0.96).mean())


def m_colors(a, quant=16):
    """颜色丰富度：量化后的不同颜色数 / 总像素。"""
    q = (a * (quant - 1)).astype(np.uint8)
    flat = q.reshape(-1, 3)
    uniq = len(np.unique(flat, axis=0))
    return float(uniq / len(flat) * 1000)


def m_saturation(a):
    """平均饱和度（只统计非白像素）。"""
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    lum = a.mean(axis=2)
    mask = lum < 0.96
    return float(sat[mask].mean()) if mask.any() else 0.0


def m_gradient_ratio(a):
    """
    渐变占比：局部颜色变化平缓（有渐变）的区域比例。
    这是区分「矢量插画（有渐变）」和「扁平色块」的关键指标。
    """
    g = a.mean(axis=2)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    lum = a.mean(axis=2)
    mask = lum < 0.96
    if not mask.any():
        return 0.0
    m = mag[mask]
    # 变化量很小但不为零 → 渐变；很大 → 硬边；接近零 → 平涂
    return float(((m > 0.004) & (m < 0.05)).mean())


def m_edge_density(a):
    """边缘密度：硬边占比。衡量"线条多不多"。"""
    g = a.mean(axis=2)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    return float((mag > 0.10).mean())


def m_dark_ratio(a):
    """暗像素占比：文字与描边的量。"""
    lum = a.mean(axis=2)
    return float((lum < 0.35).mean())


# ══ 2026-09-27 新增：Colour discipline + Visual hierarchy ══════════════
# 补风格维度表里两栏（能直接给图时那栏仍优先；这两条是【图不能给时的代理物】）：
#   Colour discipline -> color_families（进档案）+ stray_color（进工具，见下）
#   Visual hierarchy  -> hero_share / hier_gap / hero_contrast
# 另外三栏没加：留白已有 whitespace；Depth layering / Detail density gradient
#   要有【先验分区】（IR 的 composition.分区）才定义得了"前景/中心"是谁，
#   做成全局数字只会误导。

def palette(a, k=6, max_px=60000):
    """主色板：k-means 聚类出图中最主要的 k 个颜色（hex）。

    ★ 从 style_profile.py 挪到这儿（原来两边各有一份实现）。deps=scipy。
    ★ seed 固定 = 0：同一个输入必须给同一个色板。
    ⚠️ k 个中心是**不完整**的色板 —— 它按像素数排名，深描边/小面积次要色族
       常常挤不进 top-k。所以它不能当"色族清单"用（见 stray_color 的实测）。
    """
    px = a.reshape(-1, 3)
    if len(px) > max_px:
        idx = np.random.default_rng(0).choice(len(px), max_px, replace=False)
        px = px[idx]
    px = px[px.mean(axis=1) < 0.96]          # 去掉白底
    if len(px) < 50:
        return []
    try:
        from scipy.cluster.vq import kmeans2
        cent, _ = kmeans2(px.astype(float), k, minit="++", seed=0)
        cent = np.clip(cent, 0, 1)
        d = ((px[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        order = np.argsort([-(lab == i).sum() for i in range(k)])
        return ["#%02x%02x%02x" % tuple(int(v * 255) for v in cent[i])
                for i in order]
    except Exception:
        return []


def solid_ink(a, flat=0.004):
    """实心墨迹掩膜：非白 且 局部梯度 < flat（= m_gradient_ratio 的"平涂"同阈值）。

    ★ 所有"色族/越界色"统计都必须过这一层：不排除抗锯齿过渡带的话，
      每张图都会"满屏杂色"——过渡带天生是连续色。这是这类指标最容易做错的地方。
    """
    lum = a.mean(axis=2)
    ink = lum < 0.96
    if not ink.any():
        return ink
    gy, gx = np.gradient(lum)
    return ink & (np.hypot(gx, gy) < flat)


def m_color_families(a, q=16, share=0.04):
    """色族数 —— 直接回答「有几个色族？」。

    固定 16 级量化网格里，各自占实心墨迹 >= share 的格子数。
    ★ 刻意不用 k-means：固定网格可复现、且对缩放稳定得多（实测见校准记录）。
    ★ 它是**计数**，所以"±1 个色族"就是 25~33% 相对变化 —— 看量级（3 vs 8），
      别当连续量读。
    """
    m = solid_ink(a)
    if int(m.sum()) < 200:
        return 0.0
    qz = np.clip((a[m] * (q - 1) + 0.5).astype(np.int32), 0, q - 1)
    key = qz[:, 0] * q * q + qz[:, 1] * q + qz[:, 2]
    cnt = np.bincount(key, minlength=q ** 3).astype(float)
    cnt /= cnt.sum()
    return float((cnt >= share).sum())


def stray_color(a, pal, tol=48.0):
    """越界色占比：实心墨迹里，到【给定色板】最近色距离 > tol 的像素比例。

    ★ 必须传入色板，函数不自己抽 —— 这是 2026-09-27 实测纠正的设计错误：
      原来用**本图自己的** k-means 色板，于是任何够大的异色都会自己挣到一个
      簇中心，"越界"永远是 0（实测：加一整块荧光绿，still 0.0000）。自比色板
      的版本测的是"稀有色的长尾"，不是"颜色纪律"。
    ★ 而且**自动抽的 6 色板太不完整**，拿它当目标色板也判不了：
      实测同风格的两张 STAR 图互比 0.021、自比 0.031（= 地板），
      但换一张正常的不同图就是 0.33~0.89 —— 那不是"越界"，是 top-6 没装下
      深描边和次要色族。
    ★ 结论：只在色板**完整**时用（人写的 IR `style.palette`，带角色名那种）。
      例：喷注图 8 色登记表 -> 干净的 3 色合成图 0.117（灰家族不在表里，
      判对了）；再加一块荧光绿 -> 0.211。
    用法见 `style_bench.py stray fig.png --palette "#e27832,#2f6fd0"`。
    """
    m = solid_ink(a)
    n = int(m.sum())
    if n < 200:
        return 0.0
    pals = [c for c in (pal or []) if isinstance(c, str) and c.startswith("#")
            and len(c) >= 7]
    if not pals:
        return 0.0
    C = np.array([[int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)]
                  for c in pals], np.float32)
    px = (a[m] * 255.0).astype(np.float32)
    over = 0
    for i in range(0, len(px), 40000):    # 分块：整块 (N,k,3) 会爆内存
        q = px[i:i + 40000]
        d = ((q[:, None, :] - C[None, :, :]) ** 2).sum(2).min(1)
        over += int((np.sqrt(d) > tol).sum())
    return float(over) / n


def m_hierarchy(a, minpx_frac=0.0004):
    """视觉层级 —— 有没有"主角"，主次对比多大。

    纯像素、不依赖先验分区（所以多面板图也能量）：
      hero_share     最大墨迹连通域 / 全部墨迹  —— 有没有 hero（1.0=一个元素占满）
      hier_gap       最大 / 次大                —— 主次对比（1.0=势均力敌；单元素记 99）
      hero_contrast  |主角饱和度 - 其余区域饱和度| —— 主角有没有在【颜色上】跳出来

    ★ 必须先 3x3 闭运算再连通：抗锯齿会沿边缘切出一圈细碎连通域，
      不闭的话"次大"常常是某条边的碎片，hier_gap 直接失去意义。
    """
    from scipy import ndimage
    zero = {"hero_share": 0.0, "hier_gap": 0.0, "hero_contrast": 0.0}
    lum = a.mean(axis=2)
    ink = lum < 0.96
    if not ink.any():
        return dict(zero)
    m = ndimage.binary_closing(ink, np.ones((3, 3)))
    lab, n = ndimage.label(m, np.ones((3, 3), int))
    if n == 0:
        return dict(zero)
    sz = np.bincount(lab.ravel())[1:]
    keep = sz >= max(20, minpx_frac * ink.size)
    if not keep.any():
        return dict(zero)
    areas = np.sort(sz[keep])[::-1]
    total = float(areas.sum())
    hero_share = float(areas[0] / total)
    hier_gap = float(areas[0] / areas[1]) if len(areas) > 1 and areas[1] > 0 \
        else 99.0
    idx = int(np.argmax(np.where(keep, sz, 0))) + 1
    hero = lab == idx
    rest = m & ~hero
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    hc = (abs(float(sat[hero].mean()) - float(sat[rest].mean()))
          if rest.any() else 0.0)
    return {"hero_share": hero_share, "hier_gap": hier_gap,
            "hero_contrast": float(hc)}


def m_aspect(path):
    w, h = Image.open(path).size
    return float(w / h)


# ★ 指标鲁棒性（经实测校准，见文件末尾「校准记录」）
#   robust=True  对缩放/压缩不敏感 → 可跨来源比较
#   robust=False 对缩放/压缩敏感   → 只在同来源内比较
METRIC_ROBUST = {
    # ── 2026-09-27 新增四项（数字见文件末尾「校准记录 2026-09-27」）──
    "color_families": False,   # 计数：±1 个色族就是 25~33% → 只看量级(3 vs 8)
    "hero_share": True,        # 缩放/JPEG 最大只动 5.4%，中位 0.1%
    "hier_gap": False,         # 比值型：主角近乎独占(≈100)时，次大区一个碎片就腰斩
    "hero_contrast": True,     # 绝对值稳（实测 ≤0.02）；值≈0 时相对变化无意义

    "whitespace": True,
    "color_richness": False,   # 缩放 0.35 倍就涨 120%；JPEG q40 涨 95%
                               # （第二次校准又发现 gradient_ratio 同类问题）
    "saturation": True,
    "gradient_ratio": False,  # 缩到 40% + JPEG q60 就从 0.23 涨到 0.43；
                              # 参考图 0.356 正落在退化区间内 → 跨来源不可比
    "edge_density": True,
    "dark_ratio": True,
    "aspect": True,
}


def measure(path):
    a = _load(path)
    out = {
        "whitespace": m_whitespace(a),
        "color_richness": m_colors(a),
        "saturation": m_saturation(a),
        "gradient_ratio": m_gradient_ratio(a),
        "edge_density": m_edge_density(a),
        "dark_ratio": m_dark_ratio(a),
        "color_families": m_color_families(a),
        "aspect": m_aspect(path),
    }
    # ★ 视觉层级展开成**标量**再进字典：style_profile 的合并档案要对每个键取中位数，
    #   值一旦是 dict 就直接 TypeError（v2.7.3 设计时特意避开这个坑）。
    out.update(m_hierarchy(a))
    return out


def _measure_at(path, size):
    """把图缩放到指定尺寸后再量。用于消除两张图分辨率不同带来的偏差。"""
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    # 用系统临时目录，不硬编码 /tmp —— ChatGPT 沙箱等环境未必有写权限
    tmp = Path(tempfile.gettempdir()) / "_sb_norm.png"
    im.save(tmp)
    return measure(tmp)


def compare(path_a, path_b):
    """
    1:1 对比两张图（通常：参考图 vs 复现图）。
    比跟「类别基准」比更准，因为参考图就是这张图的目标。

    ⚠️ 前置检查：宽高比差太多说明**在比不该比的东西**
       （实测踩过：拿含两个 panel 的参考图去比只有一个 panel 的复现图，
        得出「留白多 28%」，实际裁掉 panel b 后只有 4%）。
    """
    # ★ 关键修复：必须先把两张图归一到同一像素尺寸再量。
    #   否则 _load() 的 max_side 会对大图降采样、对小图不降，
    #   降采样本身会模糊图像 → 压低边密度和暗像素 → 制造假的「你比参考少」。
    #   实测：颜色丰富度因这一项产生 -21% 的假差距（归一后只剩 -5%）。
    ra0 = measure(path_a)["aspect"]
    rb0 = measure(path_b)["aspect"]
    size_a = Image.open(path_a).size
    size_b = Image.open(path_b).size
    target = size_a if max(size_a) <= max(size_b) else size_b
    a = _measure_at(path_a, target)
    b = _measure_at(path_b, target)
    a["aspect"] = ra0
    b["aspect"] = rb0
    ra, rb = ra0, rb0
    warn = abs(ra - rb) / max(ra, rb) > 0.15
    print(f"A: {path_a}  ({ra:.2f})")
    print(f"B: {path_b}  ({rb:.2f})")
    if warn:
        print(f"\n⚠️⚠️  宽高比差 {abs(ra-rb)/max(ra,rb)*100:.0f}%，"
              f"很可能不是同范围的内容在比。")
        print("     先确认：是不是拿多 panel 的图比了单 panel 的图？")
        print("     剪裁到同范围再比，否则数字会严重误导。\n")
    print(f"\n{'指标':<18}{'A':>12}{'B':>12}{'相对差':>10}  可信")
    for k in a:
        if k == "aspect":
            continue
        ra_, rb_ = a[k], b[k]
        rel = (rb_ - ra_) / ra_ * 100 if ra_ > 1e-9 else float("nan")
        ok = "✅" if METRIC_ROBUST.get(k, True) else "⚠️不可信"
        print(f"{k:<18}{ra_:>12.4f}{rb_:>12.4f}{rel:>9.0f}%  {ok}")
    return a, b, warn


# ---------------------------------------------------------------- 分类
def classify(m):
    """
    按指标粗分图型。
    T3（3D 示意/插画）的特征：渐变多、饱和度高、留白适中、暗像素少（无坐标轴文字）
    T1（数据图）的特征：留白多、暗像素多（刻度文字）、渐变少、饱和度低
    """
    if m["gradient_ratio"] > 0.10 and m["saturation"] > 0.18 \
            and m["dark_ratio"] < 0.10:
        return "T3_schematic"
    if m["dark_ratio"] > 0.06 and m["gradient_ratio"] < 0.12:
        return "T1_dataplot"
    if m["gradient_ratio"] > 0.08:
        return "T2_surface"
    return "unclassified"


# ---------------------------------------------------------------- 基准
def build(root, out_path, pattern="**/figs/*.png"):
    root = Path(root)
    files = sorted(root.glob(pattern))
    if not files:
        sys.exit(f"{root} 下没找到匹配 {pattern} 的图")
    print(f"扫描 {len(files)} 张图…")

    rows = []
    for f in files:
        try:
            m = measure(f)
            m["_file"] = str(f)
            rows.append(m)
        except Exception as e:
            print(f"  跳过 {f.name}: {e}")

    by_class = {}
    for r in rows:
        by_class.setdefault(classify(r), []).append(r)

    metrics = ["whitespace", "color_richness", "saturation",
               "gradient_ratio", "edge_density", "dark_ratio"]
    baseline = {"n_total": len(rows), "classes": {}}
    for cls, items in by_class.items():
        stats = {}
        for m in metrics:
            vals = np.array([it[m] for it in items])
            stats[m] = {
                "mean": float(vals.mean()),
                "std": float(vals.std()),
                "p10": float(np.percentile(vals, 10)),
                "p90": float(np.percentile(vals, 90)),
            }
        baseline["classes"][cls] = {
            "n": len(items), "stats": stats,
            "examples": [it["_file"] for it in items[:40]],
        }

    Path(out_path).write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n基准已写入 {out_path}\n")
    print(f"{'图型':<16}{'数量':>5}   " + "  ".join(f"{m[:11]:>12}" for m in metrics))
    for cls, d in sorted(baseline["classes"].items(),
                         key=lambda kv: -kv[1]["n"]):
        s = d["stats"]
        vals = "  ".join(f"{s[m]['mean']:>12.4f}" for m in metrics)
        print(f"{cls:<16}{d['n']:>5}   {vals}")
    return baseline


def check(path, baseline_path):
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    m = measure(path)
    cls = classify(m)
    print(f"图：{path}")
    print(f"判定图型：{cls}")
    if cls not in base["classes"]:
        print(f"⚠️ 基准里没有 {cls} 这一类，无法比对")
        return
    st = base["classes"][cls]["stats"]
    print(f"（基准 {cls}：n={base['classes'][cls]['n']}）\n")
    print(f"{'指标':<18}{'本图':>10}{'基准均值':>10}{'偏离(σ)':>9}  判定")
    flags = []
    for k, v in m.items():
        if k not in st:
            continue
        robust = METRIC_ROBUST.get(k, True)
        mu, sd = st[k]["mean"], st[k]["std"] or 1e-9
        z = (v - mu) / sd
        if not robust:
            mark = "⚠不可信"
        elif abs(z) > 2.5:
            mark = "★偏离"
            flags.append((k, z))
        elif abs(z) > 1.5:
            mark = "偏"
        else:
            mark = "OK"
        print(f"{k:<18}{v:>10.4f}{mu:>10.4f}{z:>9.2f}  {mark}")
    print()
    print("注：标⚠的指标对分辨率/压缩敏感，跨来源比较不可信（见校准记录）。")
    if flags:
        print("\n明显偏离基准的项（仅鲁棒指标）：")
        for k, z in flags:
            d = "高于" if z > 0 else "低于"
            print(f"  · {k} {d}基准 {abs(z):.1f}σ")
        print("\n→ 这些地方最可能让图'看着不像期刊图'，优先改。")
    else:
        print("\n→ 所有鲁棒指标都在基线的 2.5σ 内。")
    return flags


def main():
    ap = argparse.ArgumentParser(description="图的风格度量与基准比对")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="从一批期刊图建立基准")
    b.add_argument("root")
    b.add_argument("-o", "--out", default="style_baseline.json")
    b.add_argument("--pattern", default="**/figs/*.png")

    c = sub.add_parser("check", help="检查单张图是否偏离基准")
    c.add_argument("image")
    c.add_argument("-b", "--baseline", required=True)

    m = sub.add_parser("measure", help="只输出单张图的指标")
    m.add_argument("image")

    cp = sub.add_parser("compare", help="1:1 对比两张图（参考 vs 复现）")
    cp.add_argument("a"); cp.add_argument("b")

    st = sub.add_parser("stray", help="越界色占比（相对手给的完整色板）")
    st.add_argument("image")
    st.add_argument("--palette", required=True,
                    help='逗号分隔的 hex 色板，如 "#e27832,#2f6fd0,#c9d2de"')
    st.add_argument("--tol", type=float, default=48.0,
                    help="到最近色板的 RGB 距离阈值（默认 48/255）")

    args = ap.parse_args()
    if args.cmd == "build":
        build(args.root, args.out, args.pattern)
    elif args.cmd == "check":
        check(args.image, args.baseline)
    elif args.cmd == "compare":
        compare(args.a, args.b)
    elif args.cmd == "stray":
        a = _load(args.image)
        pal = [c.strip() for c in args.palette.split(",") if c.strip()]
        v = stray_color(a, pal, tol=args.tol)
        print(f"越界色占比 {v:.4f}  （色板 {len(pal)} 色, tol={args.tol:g}）")
        print("  ⚠️ 只在色板完整时才有意义：自动抽的 top-6 色板装不下深描边和"
              "次要色族，会报出 0.3~0.9 的假越界（见文件末尾校准记录）")
    else:
        mm = measure(args.image)
        cls = classify(mm)
        print(f"图型判定：{cls}")
        for k, v in mm.items():
            print(f"  {k:<18}{v:.4f}")


if __name__ == "__main__":
    main()


# ================================================================ 校准记录
# 在信任任何指标之前做的仪器校准（2026-09-19）
#
# 方法：把同一张图做退化处理，看指标怎么变。
#
#   缩放 1.00 → 0.35：color_richness 0.687 → 1.515 (+120%)
#   JPEG q95 → q40  ：color_richness 0.820 → 1.341 (+95%)
#   而 dark_ratio / edge_density 在以上处理下基本不变
#
# 结论：参考图是从 PDF 低分辨率切出来的（带压缩+抗锯齿），
#      天然比干净渲染的图有更多中间色。
#      所以 color_richness 的跨来源比较会把「出处差异」误判成「风格差异」。
#
# 教训：**先校准仪器，再信读数。** 第一版跑出来的
#      "颜色丰富度低 61%" 就是伪影，差点当成真结论去改图。
#
# 要对 color_richness 做跨来源比较，须先把两张图退化到同一条件
# （同尺寸 + 同 JPEG 质量），否则不要用它下结论。


# ================================================================ 校准记录 2026-09-27（颜色纪律 + 视觉层级）
# 一次完整的「先校准仪器，再信读数」。★ 三个候选设计里两个被数据否掉了 ——
# 这段记录的主要价值就是那两个否定结论，别把它们删掉重犯。
#
# 方法（与 2026-09-19 同）：同一张图退化处理后再量，看指标怎么变。
#   缩放 1.00 -> 0.70 / 0.50 / 0.35；JPEG q95 / q75 / q40
#   样本：T3-02 / T3-03 两张 CC-BY 参考图 + 喷注淬火位图 + 自旋图位图（共 4 张）
#
# ── 留下来的（进档案，随 measure() 一起产出）──
#
#   指标            最大相对变化                中位    结论
#   hero_share        5.4% (自旋图 @0.35)        0.1%    OK  可跨来源
#   hero_contrast   107.1% (T3-03 @jpeg40)       1.5%    OK  可跨来源（见下）
#   color_families   33%   (T3-02 @jpeg40)       ~0%     !!  只看量级
#   hier_gap         57.1% (喷注淬火 @0.35)      0.1%    !!  只在 ≈1 时可信
#
# ★ hero_contrast 的 107% 是**小分母伪影**：T3-03 基线 0.0019 -> jpeg40 0.0039，
#   绝对差只有 0.002。绝对值在所有退化条件下都 <=0.02，所以标 robust=True；
#   但值接近 0 时（该图主角与其余区域饱和度本来就一样）别读它的相对变化。
#
# ★ hier_gap 中位 0.1% 看着很稳，为什么还是 False：它是**比值**。喷注淬火图
#   主角近乎独占（hier_gap 约 103），此时"次大"是一个抗锯齿碎片 ——
#   缩放 0.35 后那个碎片消失，比值直接从 103 掉到 44（-57%）。
#   即：hier_gap 约 1 时才可信（势均力敌 = 无 hero），约 100 时不可信。
#
# ★ color_families 是**计数**，所以 ±1 个色族天然就是 25~33%。
#   实测 3/3/3/3/2（T3-02 各退化档）、4/4/4/4/5/4（喷注图）——
#   稳定时纹丝不动，漂时只漂 1。用途是看量级："3 个色族"vs"8 个色族"，
#   不是"3.0 vs 3.2"。合成图三档实测：3色图->3、+1 荧光绿->4（份额够就进）。
#
# ── 被否掉的两个设计（不要重犯）──
#
# ✗ 设计一：越界色 vs **本图自己的** k-means 色板 —— 永远测不出来。
#     合成图加一整块荧光绿（占墨迹 10%），读数仍是 0.0000：
#     够大的异色会自己挣到一个簇中心，于是"它在色板里"。
#     这个版本测的是"稀有色的长尾"，不是颜色纪律。
#
# ✗ 设计二：越界色 vs **自动抽的 6 色板**（当作目标色板）—— 判不了。
#     自比 0.0314 / 同风格异图（T3-03 vs T3-02 色板）0.0211 ← 这是地板
#     换一张正常的不同图：自旋图 0.8875 / 喷注图 0.7196 / 火球图 0.3283
#     —— 那不是"越界"，是 top-6 根本没装下深描边和次要色族（k-means 按
#        像素数排名，深描边面积小，挤不进前 6）。
#
# ✓ 最终设计：stray_color(a, pal) 是**纯函数**，色板必须由调用者给。
#     只在色板完整时有意义 —— 人写的 IR style.palette（带角色名那种）。
#     实测（喷注图 8 色登记表 #e27832/#d9451f/#ffd257/#2f6fd0/#1b3f8f/#c9d2de
#           /#fffdf0/#2a2d33）：
#       干净 3 色合成图            0.1171  ← 灰 (150,150,155) 不在表里，判对了
#       再加一块荧光绿             0.2111  ← 单调响应
#       再加 6 个杂色              0.2436
#     所以它是个**工具**（`style_bench.py stray fig.png --palette "..."`），
#     不进档案、不进门禁 —— 没有完整色板时它给的是噪声。
#
# 教训（同 2026-09-19）：**先校准仪器，再信读数。** 这两栏差点就以
# "stray_color = 0.00，颜色纪律完美"的假读数进了验收表。
