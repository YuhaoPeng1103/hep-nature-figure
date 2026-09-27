#!/usr/bin/env python3
"""
check_sketch —— 位图闸口（★ 同一个脚本在流程里跑 **两次**）
=========================================================================
## 它在流程里的位置

    草图/描述 ──生图──▶ 草图 ──★闸口①★──▶ 成品位图 ──★闸口②★──▶ 矢量
                        （矢量化输出，人可改）

★ **两道闸口用的是同一个脚本**，只是喂进去的图不同：
  · 闸口① 草图 → 成品位图 之间：构图错了，重出的代价最小；
  · 闸口② 成品位图 → 矢量 之间：**成品位图是矢量那一步的唯一依据**，
    它错了后面全错。以前只跑了闸口①，闸口②是漏的。

★ 为什么成品位图也要查：矢量那一步（重画 / 混合临摹）都会**忠实照抄位图**，
  位图里的物理错误会被原样带进交付的矢量图里 —— 而位图本身没有第二个人看过。

## ★ 为什么必须分成两类检查

**机器判不了物理。** 图像模型可能把喷注画反、把非中心碰撞画成同心、
把 L 画成面内箭头 —— 这些从像素上量不出来，只能"看懂图"才能判。

所以本脚本输出两块：

  ■ 自动测到的    构图/风格这类**能量**的（留白、内容边界、偏心、饱和度）
  ■ 必须你回答的  IR 的 `geometry_constraints` **逐条变成待答问题**
                  —— 让"检查物理"从一句原则变成一个必须填的动作

**有任何一条答「否」→ 改 prompt 重出，不要往下走。**
往下走的代价是：错误会被带进成品位图、再带进矢量，越往后越贵。

## 用法

    # 闸口① 草图
    python3 check_sketch.py gen/sketch_s1.png --ir ir/xxx.ir.yaml
    # 闸口② 成品位图（喂同一个 IR），并量「构图有没有沿用草图」
    python3 check_sketch.py gen/render_s22_clean.png --ir ir/xxx.ir.yaml \\
        --sketch gen/sketch_s1_clean.png

    python3 check_sketch.py gen/render_s22.png --ir ir/xxx.ir.yaml \\
        --profile assets/style-profiles.json --class "T3-schematic (illustration)"

    # ★ 多张一次查 + 落 json，再自动排序挑图（8 个 seed 出图后的推荐做法）
    python3 check_sketch.py gen/sketch_s*.png --ir ir/xxx.ir.yaml --json gen/check.json
    python3 pick_best.py gen/check.json
"""
from __future__ import annotations

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8（否则打印 ✅ 会崩）

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ir_canvas          # 画布的唯一读取口（composition.canvas 优先）


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
    # ★ 贴边细边框检测：生图模型常在四周画一条 1px 淡灰外框
    #   （实测 2026-09-26：同一简报 3/3 命中）。它会把“内容边界”拉成整幅图，
    #   于是被误报成“内容出界”。这里把它认出来，报错时直接点名。
    frame = None
    band = 4
    ring = np.zeros_like(nonbg)
    ring[:band, :] = ring[-band:, :] = True
    ring[:, :band] = ring[:, -band:] = True
    inner = nonbg & ~ring
    if inner.any():
        iy, ix = np.where(inner)
        inset = min(ix.min() / W, iy.min() / H,
                    1 - (ix.max() + 1) / W, 1 - (iy.max() + 1) / H)
        rp = a[ring & nonbg]
        # 判据只看“拿掉最外圈后内容是不是就离边了”——
        #   真正出界的大色块会一直往里延伸，内容边界不会因此收进来；
        #   只有“贴边的一条细线”才会。不能拿灰度当判据（模型画的框有时深有时浅）。
        if rp.size and inset >= 0.02:
            frame = {"inset": round(float(inset), 3),
                     "gray": round(float(rp.mean()), 3), "px": int(rp.size)}
    # ★ 贴边的是「细线出画布」还是「内容被裁」？
    #   束流线 / 参考线**本来就该跑到画布外**（参考图 T3-33 就是：两条虚线
    #   一直顶到左右边）。旧版一律报「内容贴边/出界 —— 会被裁」，实测连
    #   参考图自己都过不了 —— 假阳性，而且会让人开始忽略这条闸口。
    #   判据：贴边那一圈里非背景像素占比。细线 0.5~2%，被裁的实心块几十 %，
    #   中间取 10%。
    band = max(4, int(round(min(H, W) * 0.02)))
    edge_frac = {}
    for name, rs, cs, dist in (
            ("left", slice(None), slice(0, band), x0),
            ("right", slice(None), slice(W - band, W), 1 - x1),
            ("top", slice(0, band), slice(None), y0),
            ("bottom", slice(H - band, H), slice(None), 1 - y1)):
        if dist < 0.01:
            edge_frac[name] = round(float(nonbg[rs, cs].mean()), 4)
    return {"bbox": (round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)),
            "centroid": (round(cx, 3), round(cy, 3)),
            "whitespace": round(1 - nonbg.mean(), 4),
            "frame": frame,
            "edge_frac": edge_frac,
            "empty_cells": empty}


# ══ 机器能判的几何：Lorentz 收缩方向 ═════════════════════════════════
# ★ 2026-09-26 实测抓到的问题：UPC 那张图的 IR 明写「核必须画成纵向压扁的椭圆
#   （Lorentz 收缩）」，草图 + 成品位图 4/4 全画成**横扁** —— 两核沿水平束流运动，
#   压扁方向却垂直于运动方向。旧的 geometry_constraints 四条全是「核与核之间」的
#   关系，**没有一条管单个形体的朝向**，所以两版位图都"通过"了闸口。
#
# 判据链（全部从像素来，不需要人回答）：
#   ① 核物质是整张图里唯一的大面积**彩色**对象（核子气是红/绿/蓝小球；
#      其余元素都是深色线、箭头、文字）→ 用饱和度取大块
#   ② 单个核子之间有空隙，连通域会是几百个小圆 → 先膨胀合并，
#      再取**未膨胀**像素的 bbox（否则框会被结构元素撑大 2k px）
#   ③ 束流方向由 IR 声明（`束流方向: horizontal|vertical`，可从 composition.视角
#      抄）。收敛沿束流方向 → 束流水平 ⇒ 每个核应该**高 > 宽**；竖直 ⇒ 宽 > 高
SAT_MIN = 40            # max(RGB)-min(RGB) ≥ 它才算"彩色"
BLOB_MIN_FRAC = 0.004   # 大块面积下限（占画布比）—— 小于它的当噪声


def colorful_blobs(img, min_frac=BLOB_MIN_FRAC):
    """图里的大面积彩色块（＝核）。按面积降序返回 [{px, box, wh}]。"""
    from scipy import ndimage as ndi
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    m = (a.max(2) - a.min(2)) >= SAT_MIN
    if not m.any():
        return []
    k = max(3, int(round(W * 0.012)))
    md = ndi.binary_dilation(m, np.ones((3, 3), bool), iterations=k)
    lab, n = ndi.label(md, np.ones((3, 3), int))
    out = []
    for i in range(1, n + 1):
        mm = m & (lab == i)
        px = int(mm.sum())
        if px < min_frac * H * W:
            continue
        ys, xs = np.nonzero(mm)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        out.append({"px": px, "box": box,
                    "wh": (box[2] - box[0], box[3] - box[1])})
    out.sort(key=lambda d: -d["px"])
    return out


def lorentz_check(img, specs):
    """IR 的 `geometry_constraints.机器` 里名含「压扁/收缩」的条目，逐条量。

    每条至少要有：`名`、`束流方向: horizontal|vertical`；可选 `阈值`（默认 1.25，
    ratio 得 ≥ 它才算"确实压扁了"，太接近 1 的圆是没画收缩）。
    返回 (lines, hard)。
    """
    lines, hard = [], []
    blobs = colorful_blobs(img)
    if len(blobs) < 2:
        lines.append("  ⚠️ 只找到 %d 个彩色大块（核应该是整张图里唯一的大面积彩色"
                     "对象）—— 这条没测成" % len(blobs))
        return lines, hard
    for sp in specs:
        beam = str(sp.get("束流方向", "")).strip().lower()
        if beam.startswith(("h", "水", "横")):
            horiz = True
        elif beam.startswith(("v", "竖", "纵")):
            horiz = False
        else:
            lines.append("  ⚠️ %s：IR 没写 `束流方向: horizontal|vertical`，"
                         "这条没测成" % sp.get("名", "?"))
            continue
        try:
            thr = float(sp.get("阈值", 1.25))
        except (TypeError, ValueError):
            thr = 1.25
        # ★ 2026-09-26：「核 = 面积最大的两个彩色块」是**启发式**，不是识别。
        #   实测踩到（自旋关联算例）：(a) 面板的 QGP 火球 + 紫色 L 箭头 +
        #   青色 Λ̄ 被膨胀合并成一个大彩色块，**面积排到第 2**，顶替了真正的
        #   第 2 个核（红核，面积第 3）。那次结论恰好是对的（2.08 也 ≥1.25），
        #   但**量错了对象** —— 闸口不能惄惄量错东西。
        #   试过「加 fill（像素/bbox 面积）过滤掉稀疏的合并团块」，**不能用**：
        #   run2 那张画反的 render_s31，错误的那个核恰好就是个 fill=0.20
        #   的合并团块 —— 滤掉它 = 漏掉真错误（已实测）。
        #   所以判据不动（仍用面积前二定好坏，避免放松），但**把所有彩色块都列出来**，
        #   带上 fill（实心核 ~0.6、合并团块 ~0.1），让人一眼看出被量的到底是不是核。
        for i, b in enumerate(blobs, 1):
            w, h = b["wh"]
            ratio = (h / w) if horiz else (w / h)
            axis = "高/宽" if horiz else "宽/高"
            fill = b["px"] / float(w * h)
            if i > 2:
                lines.append("     · 彩色块#%d box=%s %d×%d  %s=%.2f  fill=%.2f"
                             "（未参与判定）" % (i, b["box"], w, h, axis, ratio, fill))
                continue
            good = ratio >= thr
            if good:
                note = "沿%s束流方向压扁（Lorentz 收缩）— 对" % ("水平" if horiz else "竖直")
            else:
                note = "**压扁方向垂直于运动方向** —— 画反了"
            lines.append("  %s 核#%d box=%s %d×%d  %s=%.2f  fill=%.2f  %s"
                         % ("✅" if good else "❌", i, b["box"], w, h, axis, ratio, fill, note))
            if not good:
                hard.append("核#%d 的 Lorentz 收缩方向画反（%s=%.2f < %.2f）"
                            % (i, axis, ratio, thr))
    if len(blobs) > 2:
        lines.append("     → ▲ 上面列了全部 %d 个彩色块；判定只用前两个。"
                     "fill 接近 0.6 = 实心核；fill ~0.1 = 多个物体被膨胀合并的团块。"
                     "被量的不是核 → 人工看一眼这行。" % len(blobs))
    return lines, hard



# ══ 机器能判的几何：喷注穿过介质的路径长度不对称 ══════════════════════════
# ★ 2026-09-27 实测抓到的问题（喷注淬火那张图）：IR 写「朝左下的喷注穿过介质
#   路径长（被淬火）、朝右上的短」—— 但按 IR 自己给的两个端点算，
#   顶点放在介质左下 ⇒ 朝左下 0.09W 就出射、朝右上反而 0.30W，**恰好是反的**。
#   3/3 草图忠实照抄了这个反的几何。旧闸口全是「谁在谁里面」这类定性约束，
#   没有一条能量出路径长度，所以三张都"通过"了闸口。
#
# 判据链（全部从像素来，不需要人回答）：
#   ① 介质 = 整张图里最大的高饱和色块 → 取**凸包** → 二阶矩拟合椭圆。
#      ★ 必须走凸包：喷注不透明、画在介质上，会把介质"咬"掉一块；直接在掩膜上
#        量弦长会在喷注处提前出射（实测 s25 量成 62px，真值 ~300px）。
#   ② 两条喷注轴 = 蓝锥（高饱和）/ 灰锥（低饱和）各自最大连通域的 PCA 主轴，
#      按"从介质中心往外"定向 —— 只取方向，不取直线的位置。
#   ③ 顶点 = 蓝锥掩膜沿自身轴向的**极小投影点**（= 锥尖 = 硬散射顶点）。
#      ★ 不能用"两轴交点"：两个喷注背对背时两轴几乎平行（实测 s25 夹角偏差
#        只有 0.4°），交点病态，算到 (-1.2, 2.9) 去了。
#   ④ 弦长 = 顶点沿每条轴到拟合椭圆交点的解析解（不是像素步进）。
#
# IR 里这样写：
#   geometry_constraints:
#     机器:
#       - 名: 喷注路径不对称（弦长比）
#         长路径色: gray     # gray=低饱和那一侧的锥（被淬火）；反了就报错
#         阈值: 1.8          # 长 / 短 ≥ 它才算成立
_JET_MIN_PX = 1200        # 喷注锥连通域像素下限
_JET_MIN_ELONG = 2.0      # 锥体细长比下限（s[0]/s[1]）


def medium_ellipse(img):
    """把介质（最大的高饱和色块）拟合成椭圆。返回 dict 或 None。

    走凸包是为了补掉"不透明喷注压在介质上咬出的缺口"。
    """
    from scipy import ndimage as ndi
    from scipy.spatial import ConvexHull
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    m = ((R > 150) & (G > 35) & (G < 215) & (B < 140)
         & (R - B > 60) & (R - G > 25))
    m = ndi.binary_closing(m, np.ones((13, 13)))
    lab, n = ndi.label(ndi.binary_opening(m, np.ones((5, 5))))
    if n == 0:
        return None
    sz = ndi.sum(m, lab, range(1, n + 1))
    mm = ndi.binary_fill_holes(lab == (int(np.argmax(sz)) + 1))
    ys, xs = np.nonzero(mm)
    if len(xs) < 500:
        return None
    pts = np.stack([xs, ys], 1).astype(float)
    try:
        hp = pts[ConvexHull(pts).vertices]
    except Exception:
        return None
    rows = np.full((H, 2), np.nan)
    for i in range(len(hp)):
        x0, y0 = hp[i]
        x1, y1 = hp[(i + 1) % len(hp)]
        if y0 == y1:
            continue
        for y in range(max(0, int(np.ceil(min(y0, y1)))),
                       min(H - 1, int(np.floor(max(y0, y1)))) + 1):
            t = (y - y0) / (y1 - y0)
            x = x0 + t * (x1 - x0)
            r = rows[y]
            if np.isnan(r[0]) or x < r[0]:
                r[0] = x
            if np.isnan(r[1]) or x > r[1]:
                r[1] = x
    fill = np.zeros((H, W), bool)
    for y in range(H):
        if np.isnan(rows[y][0]):
            continue
        fill[y, max(0, int(np.floor(rows[y][0]))):
                min(W, int(np.ceil(rows[y][1])) + 1)] = True
    fy, fx = np.nonzero(fill)
    if len(fx) < 500:
        return None
    cx, cy = float(fx.mean()), float(fy.mean())
    C = np.cov(np.stack([fx - cx, fy - cy]).astype(float))
    val, vec = np.linalg.eigh(C)
    A = 2.0 * float(np.sqrt(max(val[1], 1e-9)))     # 半长轴
    B = 2.0 * float(np.sqrt(max(val[0], 1e-9)))     # 半短轴
    return {"cx": cx, "cy": cy, "A": A, "B": B,
            "theta": float(np.arctan2(vec[1, 1], vec[0, 1])),
            "mask": fill, "H": H, "W": W}


def _jet_cone(mask, away, min_px=_JET_MIN_PX, min_elong=_JET_MIN_ELONG):
    """mask 里最细长的连通域 → {c,d,px,elong,apex,span}；d 朝远离 away 的方向。"""
    from scipy import ndimage as ndi
    lab, n = ndi.label(ndi.binary_opening(mask, np.ones((3, 3))))
    best = None
    for i in range(1, n + 1):
        mm = lab == i
        ys, xs = np.nonzero(mm)
        if len(xs) < min_px:
            continue
        P = np.stack([xs - xs.mean(), ys - ys.mean()], 1).astype(float)
        _, s, vt = np.linalg.svd(P, full_matrices=False)
        e = s[0] / max(s[1], 1e-6)
        if e < min_elong:
            continue
        if best is not None and len(xs) <= best["px"]:
            continue
        c = np.array([xs.mean(), ys.mean()])
        d = vt[0] / np.linalg.norm(vt[0])
        if np.dot(d, c - away) < 0:
            d = -d
        pr = (xs - c[0]) * d[0] + (ys - c[1]) * d[1]
        k = int(np.argmin(pr))
        best = {"c": c, "d": d, "px": int(len(xs)), "elong": float(e),
                "apex": np.array([xs[k], ys[k]]),
                "span": float(pr.max() - pr.min())}
    return best


def _ray_ellipse(d, v, e):
    """射线 v + t*d（d 单位）与椭圆 e 的交点 t。返回 (t_back, t_fwd) 或 None。"""
    ct, st = math.cos(e["theta"]), math.sin(e["theta"])

    def loc(u, w):
        du, dw = u - e["cx"], w - e["cy"]
        return du * ct + dw * st, -du * st + dw * ct

    px, py = loc(v[0], v[1])
    qx, qy = loc(v[0] + d[0], v[1] + d[1])
    qx -= px
    qy -= py
    A, B = e["A"], e["B"]
    a2 = (qx / A) ** 2 + (qy / B) ** 2
    if a2 <= 1e-12:
        return None
    b2 = 2 * (px * qx / A ** 2 + py * qy / B ** 2)
    c2 = (px / A) ** 2 + (py / B) ** 2 - 1
    disc = b2 * b2 - 4 * a2 * c2
    if disc <= 0:
        return None
    r = math.sqrt(disc)
    return ((-b2 - r) / (2 * a2), (-b2 + r) / (2 * a2))


def path_asym_check(img, specs):
    """IR 的 `geometry_constraints.机器` 里名含「路径 / 弦长」的条目，逐条量。"""
    from scipy import ndimage as ndi
    lines, hard = [], []
    e = medium_ellipse(img)
    if e is None:
        lines.append("  ⚠️ 找不到介质（应该是整张图里最大的高饱和色块）"
                     "—— 这条没测成，别当成通过")
        return lines, hard
    H, W = e["H"], e["W"]
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    R, G, B = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    lum = 0.299 * R + 0.587 * G + 0.114 * B
    blue = (B - R > 55) & (B > 140) & (G < 190)
    gray = ((mx - mn) < 62) & (lum > 105) & (lum < 218) & (B >= R - 6) & (~blue)
    away = np.array([e["cx"], e["cy"]])
    cb = _jet_cone(blue, away)
    cg = _jet_cone(gray, away, min_px=900, min_elong=1.6)
    if cb is None or cg is None:
        lines.append("  ⚠️ 只找到 %s —— 这条没测成，别当成通过"
                     % ("蓝锥" if cb is None else "灰锥"))
        return lines, hard
    v = cb["apex"]
    ang = 180.0 - math.degrees(math.acos(
        float(min(1.0, max(-1.0, np.dot(cb["d"], cg["d"]))))))
    r1 = _ray_ellipse(cb["d"], v, e)
    r2 = _ray_ellipse(cg["d"], v, e)
    l1 = 0.0 if r1 is None else max(float(r1[1]), 0.0)
    l2 = 0.0 if r2 is None else max(float(r2[1]), 0.0)
    print_apx = np.hypot(*(cg["apex"] - v))
    lines.append("  介质椭圆 c=(%.2f,%.2f)  半轴 %.0f×%.0f px  高/宽=%.2f"
                 % (e["cx"] / W, e["cy"] / H, e["B"], e["A"], 2 * e["A"] / (2 * e["B"])))
    lines.append("  蓝锥（高饱和）轴=(%+.2f,%+.2f)  灰锥（低饱和）轴=(%+.2f,%+.2f)"
                 "  夹角偏离 180° = %.1f°" % (cb["d"][0], cb["d"][1],
                                              cg["d"][0], cg["d"][1], ang))
    lines.append("  硬散射顶点（蓝锥锥尖，机器测）=(%.3f,%.3f)  在介质内=%s"
                 "（灰锥锥尖离它 %.0f px）"
                 % (v[0] / W, v[1] / H,
                    e["mask"][int(v[1]), int(v[0])], print_apx))
    for sp in specs:
        try:
            thr = float(sp.get("阈值", 1.8))
        except (TypeError, ValueError):
            thr = 1.8
        want = str(sp.get("长路径色", "")).strip().lower()
        if want.startswith(("b", "蓝")):
            longl, shortl, wtxt = l1, l2, "蓝锥（高饱和那一侧）"
        elif want.startswith(("g", "灰")):
            longl, shortl, wtxt = l2, l1, "灰锥（低饱和那一侧）"
        else:
            longl, shortl = max(l1, l2), min(l1, l2)
            wtxt = "长的那一侧（IR 没写 `长路径色`）"
        ratio = longl / shortl if shortl > 1e-9 else float("inf")
        good = ratio >= thr
        lines.append("  %s 弦长（穿过介质）：蓝锥=%.0f px (%.3fW)  灰锥=%.0f px (%.3fW)"
                     % ("✅" if good else "❌", l1, l1 / W, l2, l2 / W))
        lines.append("     要的是「%s」更长：%.2f × 短的那侧，阈值 %.2f"
                     % (wtxt, ratio, thr))
        if not good:
            hard.append("喷注穿过介质的路径长度不对称不成立"
                        "（长/短=%.2f < %.2f）" % (ratio, thr))
    return lines, hard




def check_one(img_path, a, ir):
    """查一张图。返回机器可读的结果 dict（人眼那一节照旧打印出来）。"""

    img_path = Path(img_path)
    hard, soft = [], []
    want = dev = fid_r = None
    if not img_path.exists():
        raise SystemExit(f"找不到 {img_path}")
    img = Image.open(img_path)
    if a.trim:
        w0, h0 = img.size
        img = img.crop((a.trim, a.trim, w0 - a.trim, h0 - a.trim))
        print("已裁掉四周 %d px（符合宽高比检查用原图）: %dx%d"
              % (a.trim, img.size[0], img.size[1]))
    W, H = img.size
    ir = load_ir(Path(a.ir))

    print(f"【位图闸口】（草图 / 成品位图通用）{img_path.name}")
    print(f"  尺寸 {W}×{H}  宽高比 {W/H:.2f}")

    # 画布比例是否照 IR 走
    # ★ 2026-09-27：画布只由 ir_canvas 读。规范把画布写在 composition.canvas，
    #   这里以前读 figure.canvas —— 仓库 8 份 IR 有 6 份被静默丢掉，比例被改
    #   也不报（「无损体检」照样绿）。现在两种位置都认，比例不符算**硬伤**。
    why = ""
    if a.canvas:
        px = ir_canvas.parse_size(a.canvas)
        if px:
            want, why = px[0] / px[1], "--canvas 指定"
        else:
            print("  ⚠️ --canvas 要写成 WxH（如 1664x928），实得 %r —— 忽略" % a.canvas)
    if want is None:
        want = ir_canvas.declared_ratio(ir)
        if want:
            node, src = ir_canvas.canvas_node(ir)
            why = src if ir_canvas.pixel_size(ir) else (src + " 的 ratio")
    if want:
        dev = abs(W / H - want) / want
        flag = "✅" if dev < 0.12 else "❌"
        print(f"  {flag} IR 声明的比例 {want:.2f}（{why}），实际 {W/H:.2f}"
              f"（偏差 {dev*100:.0f}%）")
        if dev >= 0.12:
            print("     → 比例被改了。比例变了，IR 里的归一化坐标全部失效。")
            hard.append("画布比例不符（%.2f vs %.2f）" % (W / H, want))
    else:
        print("  （IR 没写画布比例、也没给 --canvas —— 比例这一项没查）")
    print()

    # ══ 一、自动测 ══
    print("■ 自动测到的（这些机器能判）")
    st = content_stats(img)
    if st is None:
        print("  ❌ 整张图几乎是白的 —— 没画出东西")
        hard.append("图为空白")
    else:
        print(f"  内容边界 (x0,y0,x1,y1) = {st['bbox']}")
        print(f"  留白 {st['whitespace']:.3f}")
        print(f"  内容重心 ({st['centroid'][0]:.2f}, {st['centroid'][1]:.2f})")
        x0, y0, x1, y1 = st["bbox"]
        if min(x0, y0, 1 - x1, 1 - y1) < 0.01:
            fr = st.get("frame")
            if fr:
                print("  ❌ 贴边细边框 —— 四周有一条淡色外框"
                      "（灰度 %.2f，%s px；拿掉它后内容离边 %.1f%%）"
                      % (fr["gray"], fr["px"], fr["inset"] * 100))
                print("     → 这是生图模型的固定毛病："
                      "简报里加一句『**不要画外框**』再重出一张")
                hard.append("贴边细边框")
            elif st.get("edge_frac") and max(st["edge_frac"].values()) <= 0.10:
                who = ", ".join("%s %.1f%%" % (k, v * 100)
                                for k, v in st["edge_frac"].items())
                print("  ⚠️ 内容出画布（贴边那一圈的非背景占比：%s）——" % who)
                print("     看着是**线条本来就该跑到画布外**（束流线/参考线这类），"
                      "不是被裁。确认一下就行。")
                soft.append("内容出画布")
            else:
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

    # ★ 机器能判的几何：IR 的 `geometry_constraints.机器`（现在只实现 Lorentz 收缩）
    mcons = []
    for c in ((ir.get("geometry_constraints") or {}).get("机器") or []):
        if not isinstance(c, dict):
            continue
        # 实现了"压扁/收缩"和"路径长度不对称"两族；别的名字原样跳过（免得假装测了）
        nm = str(c.get("名", ""))
        if ("压扁" in nm or "收缩" in nm):
            mcons.append(("lorentz", c))
        elif ("路径" in nm or "弦长" in nm):
            mcons.append(("path", c))
    if [c for k, c in mcons if k == "lorentz"]:
        print()
        print("  ├ Lorentz 收缩方向（★ 机器量的，不用人回答）")
        lines, lhard = lorentz_check(img, [c for k, c in mcons if k == "lorentz"])
        for ln in lines:
            print(ln)
        if lhard:
            print("     → 两核必须**沿运动方向**压扁（收缩轴 ∥ 速度）。"
                  "画成横扁 = 收缩轴垂直于速度 = 物理错。")
            print("       修法：IR 的 style.conventions 已写明形状 → 简报里"
                  "（ir_to_genbrief 会带过去）必须有这一条；没有就补上再重出。")
        hard += lhard

    if [c for k, c in mcons if k == "path"]:
        print()
        print("  ├ 喷注穿过介质的路径长度（★ 机器量的，不用人回答）")
        lines, phard = path_asym_check(img, [c for k, c in mcons if k == "path"])
        for ln in lines:
            print(ln)
        if phard:
            print("     → 能量损失 ∝ 穿过介质的路径长度。长路径那侧必须明显更长"
                  "（阈值见 IR）。")
            print("       修法：IR 里喷注的两个端点和顶点位置要配套 —— 顶点偏哪边，"
                  "哪边的出射路径就短。改 IR 再重出，别改阈值。")
        hard += phard

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

    # ★ 构图保真（v2.8）：成品位图 vs 上一步的草图。闸口以前只查「照抄参考图」，
    #   没人查「有没有把草图的构图丢掉」—— 实测（形变核→火球，seed 53）不送构图
    #   参考时布局相关掉到 0.696，得肉眼看到出图才发现。
    if a.sketch:
        sp = Path(a.sketch)
        if not sp.exists():
            print("  ⚠️ --sketch 不存在：%s —— 保真这一项跳过" % sp)
        else:
            try:
                import ref_leak_check as RLC
                fid_r = RLC.corr(str(img_path), str(sp))
            except Exception as e:
                print("  ⚠️ 构图保真量不了（%s: %s）" % (type(e).__name__, e))
            if fid_r is not None:
                ok_fid = fid_r >= a.fidelity_min
                print("  %s 构图保真：与草图 %s 的布局相关 r=%.3f（下限 %.2f）"
                      % ("✅" if ok_fid else "❌", sp.name, fid_r, a.fidelity_min))
                print("     （锚点：降级送草图 0.904 / 原样送 0.873 / 完全不带 0.696）")
                if not ok_fid:
                    print("     → 构图跑掉了：成品位图没沿用草图的布局。先查 gen_figure "
                          "是不是漏了 `--content-ref <草图>`。")
                    hard.append("构图保真 %.3f < %.2f" % (fid_r, a.fidelity_min))

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
    return {"file": img_path.name, "path": str(img_path),
            "size": [W, H], "ratio": round(W / H, 4),
            "ratio_want": (round(want, 4) if want else None),
            "ratio_dev": (round(dev, 4) if dev is not None else None),
            "fidelity_r": (round(fid_r, 4) if fid_r is not None else None),
            "hard": hard, "soft": soft, "ok": not hard}


def main():
    ap = argparse.ArgumentParser(
        description="位图闸口 —— 草图 / 成品位图通用，流程里跑两次",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("image", nargs="+",
                    help="要查的位图；★ 可以一次给多张（8 个 seed 出图后一次全查）")
    ap.add_argument("--ir", required=True, help="对应的 IR —— 几何约束从它来")
    ap.add_argument("--profile", help="风格档案（可选）")
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--canvas", help="覆盖 IR 的画布比例，写 WxH（如 1664x928）")
    ap.add_argument("--trim", type=int, default=0,
                    help="先裁掉四周 N px 再测（处理生图模型画的贴边细外框）")
    ap.add_argument("--sketch", default=None,
                    help="构图依据（上一步选中的草图）—— 量成品位图的**构图保真**，"
                         "低于 --fidelity-min 直接算硬伤（按原图量，--trim 不影响它）")
    ap.add_argument("--fidelity-min", type=float, default=0.70,
                    help="构图保真下限（默认 0.70）")
    ap.add_argument("--json", default=None,
                    help="把机器结果写成 json；多张时配 scripts/pick_best.py 排序挑图")
    a = ap.parse_args()

    ir = load_ir(Path(a.ir))
    report = [check_one(Path(one), a, ir) for one in a.image]

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"images": report, "ok": all(r["ok"] for r in report),
             "hard_total": sum(len(r["hard"]) for r in report)},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("已写出机器结果 %s" % a.json)
    if len(report) > 1:
        print("=" * 62)
        print("多张汇总（%d 张）—— 人眼只需审没有硬伤的：" % len(report))
        for r in sorted(report, key=lambda x: (len(x["hard"]), len(x["soft"]))):
            print("  %s %-30s 硬伤 %d  软警 %d  保真 %s"
                  % ("❌" if r["hard"] else "✅", r["file"], len(r["hard"]),
                     len(r["soft"]),
                     ("%.3f" % r["fidelity_r"]) if r["fidelity_r"] is not None
                     else "n/a"))
        print("  → 排序挑图：python3 scripts/pick_best.py %s"
              % (a.json or "<--json 写出的报告.json>"))
    return 1 if any(r["hard"] for r in report) else 0


if __name__ == "__main__":
    sys.exit(main())
