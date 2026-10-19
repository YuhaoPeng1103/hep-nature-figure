#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ir_contour_seg -- IR 引导的「可见像素物理轮廓」分割（v3）

作者 2026-10-15：「我现在需要的就是在可见像素的物理轮廓上分割，你可以配合 IR 使物理轮廓
分割更正确啊。AmodalSVG 走的就是这条：VLM 引导 + grounded segmentation + inpaint 补全 ——
它也没指望分割器自己给出『完整物理物体』。」

所以本工具的职责边界（= AmodalSVG 的第一、二步）：
  · **语义**由 IR 给（哪个元素是什么、叠放序、谁遮谁、形态族、数量、位置）；
  · **边界**只落在**可见像素**上（不猜被完全遮住的部分）；
  · 遮挡/被切掉的部分**不给假轮廓**，只出读数（看到多少、缺多少），交给 inpaint 那一步。
  · 位图与 IR 不一致的地方**必须报出来**，不许静默按 IR 硬套 —— 实测见 §"IR vs 位图"。

与现有路线（scripts/raster_vector/elements.py + segsem.py）的差别，实测读数见 report.json
的 `route_compare`：那条路线切的是**颜色类**（16 色调色板 + 同色连通 + 邻近合并），
于是「一个物理物体被切成 N 个颜色类、一个颜色类里塞了多个物理物体」。本工具切的是
**物理轮廓**：核 = 核子球团的整体剪影（不是逐个球）、光子线 / 顶点 / 末态箭头尽管同为橙色
也必须分开（按厚度与亮度切开）。

IR 里用到的先验（都在 elements[] / composition 里现成写着）：
  elements[].z           叠放序（大 = 靠前）
  elements[].primitive   形态族（实心箭头 / 波浪线 / 椭球 / 薄板 / 发光球 / 双向箭头+虚线）
  elements[].material    声明配色（**只当确认与仲裁，不当主判据** —— 见下）
  elements[].name        位置（「上核」/「下核」）与数量（×N）
  composition.穿透/遮挡   谁压谁、被压的部分还看不看得见

★ 实测教训一（本图，fig_upc_v415/render/pick/cand_s4192.png）：**配色先验会失效**。
  位图把核画成「红球 + 蓝灰球」的球团，IR 声明的却是纯色渐变（N1 #a9bcf3→#38489f、
  N2 #f6b39c→#a8342a）；速度箭头 IR 声明深灰 #2b2f38，位图画成一红一蓝。
  实测 LabΔ：N1 57.1、N2 49.5、A1 52.1、G1 41.7（都超阈值 26）；S1 14.2 / B1 18.5 / V1 19.5 一致。
  所以主判据必须是**形态 + 数量 + 位置 + z 序**；配色只用来在同类候选里仲裁，
  或作为「IR 与位图不一致」的读数报出来（这一列同时也在说生成模型有没有听 IR 的话）。

★ 实测教训二：**读数是用来发现「位图与 IR 不一致」的，不是拿来硬套 IR 的**。同图量出：
  · HP3 核的压扁比：IR 说 2.2:1，实测 bbox 1.11 / 1.15、主轴比 1.21 / 1.23 —— 核接近球形；
  · HP5 末态对背对背：IR 要求夹角 > 90°，实测约 63~75° —— 张口不够，点积 > 0；
  · 「板把核切一半」（composition.穿透）：可见剪影完整 —— 位图把板画在核后面，压根没切。
  判「真被切掉一整块」不能用凸包差额（球团毛边天生占 ~20%），要用缺口的最大内切半径
  与物体等效半径比（> 0.35 才算）。

★ v4.18 增加三件事（2026-10-15）：
  1. **新引擎** `discover_ir()`：IR 的 material 编译成颜色模型（hex 锚点 +
     「A → B」梯度线段 + 语义色词兜底），**相对阈值**建池；再用
     形态族闸门 × 数量 n × 位置词（轴正/负侧、上/下核、相对位置）× z 序消费选候选。
  2. **双引擎仲裁** `arbitrate()`：逐元素，**老引擎掩膜过 HARD_GATE 就保留**，
     不过才换新引擎。标定：UPC 10/10 不回归 / 喷注深火 N1 N2 B1 G1 换新引擎。
     ★ 切换方向不能反：UPC 位图与 IR 偏差极大（N1 LabDelta 57.1），新引擎在那张图上只有 6/10。
  3. **SAM 边界细化** `sam_refine()`（`--sam`）：MobileSAM vit_t 点提示，只做
     **有界并集** `new = m | (sam & dilate(m, grow*短边))` —— 绝不整块替换、绝不删像素；
     IoU < min_iou 或面积出 [0.5,3] 倍就只报读数跳过。

用法：
    python tools/ir_contour_seg.py --bitmap <png> --ir <ir.yaml> --outdir <dir> [--debug-pieces]
    python tools/ir_contour_seg.py --bitmap <png> --ir <ir.yaml> --outdir <dir> --sam
    python tools/ir_contour_seg.py --bitmap <png> --ir <ir.yaml> --outdir <dir> --no-arbitrate   # 纯 v4.17c 对照
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

# ── 形态族。★ 判序要紧：越具体的排越前 ─────────────────────────────────────
FAMILY_KEYS = [
    ("axes",    ("坐标三轴", "三轴", "坐标轴")),
    ("arc",     ("同心弧", "弧线", "马赫", "尾迹", "激波")),
    ("jet",     ("喷注", "射流")),
    ("blob",    ("火球", "团块", "介质", "等离子体", "发光体", "QGP")),
    ("dim",     ("双向", "尺寸", "参考线", "虚线")),
    ("glow",    ("发光球", "星芒")),
    ("plane",   ("薄板", "网格板", "板面", "平面", "平行四边形")),
    ("cluster", ("球团", "椭球", "扁球", "球簇", "核子")),
    ("stroke",  ("波浪", "弹簧", "螺旋", "辐射线")),
    ("arrow",   ("箭头",)),
    ("text",    ("文字", "标注")),
]
# ★ glow 的键里【不能】留「顶点」：P1 的 primitive 写着「两支...实体箭头，从顶点向外」，
#   判序在 arrow 之前就会被误认成发光顶点（实测 P1 变成 glow、V1 剥到 0 px）。
HEX = re.compile(r"#([0-9a-fA-F]{6})")
EID = re.compile(r"\b([A-Z]\d{1,2})\b")


def family_of(elem):
    # ★ 先看【元素名】，再看 primitive：G1「胶子辐射线」的 primitive 里写着「从淬火喷注
    #   侧向分出」—— 混在一起判就会被 jet 抢走（实测 G1 与 J2 拿到同一块 33423 px）。
    nm = elem.get("name") or ""
    for fam, keys in FAMILY_KEYS:
        if any(k in nm for k in keys):
            return fam
    s = "%s %s" % (elem.get("primitive") or "", nm)
    for fam, keys in FAMILY_KEYS:
        if any(k in s for k in keys):
            return fam
    return "other"


def count_of(elem):
    m = re.search(r"[×x]\s*(\d+)", elem.get("name") or "")
    if m:
        return int(m.group(1))
    v = (elem.get("params") or {}).get("数量")          # IR 常把「×N」写在 params.数量
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        m2 = re.search(r"(\d+)", v)
        if m2:
            return int(m2.group(1))
    return 1


def parse_ir(path):
    import yaml
    d = yaml.safe_load(io.open(path, encoding="utf-8").read()) or {}
    out = []
    for k, e in enumerate(d.get("elements") or []):
        cols = [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
                for h in HEX.findall(e.get("material") or "")]
        out.append(dict(id=e.get("id") or "E%d" % k, name=(e.get("name") or "").strip(),
                        z=int(e.get("z") or (k + 1)), family=family_of(e),
                        n=count_of(e), colors=cols, primitive=(e.get("primitive") or ""),
                        material=(e.get("material") or ""),
                        params=(e.get("params") or {}), role=(e.get("physics_role") or ""),
                        text=(e.get("text") or "")))
    out.sort(key=lambda x: x["z"])
    return out, (d.get("composition") or {})


# ── 颜色 ───────────────────────────────────────────────────────────────────
def _f(t):
    t = t / 255.0
    return np.where(t <= 0.04045, t / 12.92, ((t + 0.055) / 1.055) ** 2.4)


def to_lab(rgb):
    rgb = np.asarray(rgb, np.float32)
    X = _f(rgb[..., 0]) * 0.4124 + _f(rgb[..., 1]) * 0.3576 + _f(rgb[..., 2]) * 0.1805
    Y = _f(rgb[..., 0]) * 0.2126 + _f(rgb[..., 1]) * 0.7152 + _f(rgb[..., 2]) * 0.0722
    Z = _f(rgb[..., 0]) * 0.0193 + _f(rgb[..., 1]) * 0.1192 + _f(rgb[..., 2]) * 0.9505
    f = lambda t: np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)
    fx, fy, fz = f(X), f(Y), f(Z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], -1)


def stats(A):
    mx, mn = A.max(2), A.min(2)
    return dict(A=A, r=A[..., 0], g=A[..., 1], b=A[..., 2], mx=mx, mn=mn,
                sat=(mx - mn) / np.maximum(mx, 1e-6), L=A.mean(2) / 255.0,
                ink=255.0 - mn, lab=to_lab(A))


def _bbox(m):
    ys, xs = np.nonzero(m)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def _mean(S, m):
    return [float(v) for v in np.stack([S["r"], S["g"], S["b"]], -1)[m].mean(0)]


def _grow(mask, rad):
    return ndi.distance_transform_edt(~mask) <= rad


def _pieces(mask, minpx, close=0):
    m = ndi.binary_closing(mask, np.ones((close, close))) if close else mask
    lab, n = ndi.label(m)
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    return [(lab == k, int(cnt[k])) for k in np.argsort(cnt[1:])[::-1] + 1 if cnt[k] >= minpx]


def _desc(S, m):
    ys, xs = np.nonzero(m)
    d = ndi.distance_transform_edt(m)
    return dict(mask=m, px=int(m.sum()),
                bbox=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                w=int(xs.max() - xs.min() + 1), h=int(ys.max() - ys.min() + 1),
                fill=float(m.sum()) / max(1, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)),
                maxthick=float(d.max()), mean=_mean(S, m))


def _thick(mask, rad):
    d = ndi.distance_transform_edt(mask)
    return ndi.binary_dilation(d > rad, iterations=int(rad)) & mask


def _plane_para(S, seed):
    """把「板」拟合成【平行四边形】：两组平行边各取最外一条，四条线交点 = 4 角。

    ★ 为什么不用可见像素的凸包：板会被介质挡住一角（喷注淬火：QGP 压住板的后左角）。
      凸包只能沿着可见边界走，必然缺角；平行四边形是板的真实几何约束，能把被挡的那一角
      补回来（amodal completion），而且顺带把“亮角”（近白、被当成背景）一起补上。
    ★ 四道闸门，任一不过就返回 None（退回旧的 _quad）：
      ① 两个方向的平行边族都要有 >=2 条（长边族 / 短边族）；
      ② 4 个交点都在画布内；
      ③ 与种子掩膜（凸包）的 IoU >= 0.45；
      ④ 面积在种子掩膜的 0.5–2 倍之间。
    """
    try:
        import cv2
    except Exception:
        return None
    L, sat = S["L"], S["sat"]
    H, W = L.shape
    bh = ndi.grey_closing(L, size=(11, 11)) - L
    g = (bh > 0.05) & (sat < 0.22) & (L > 0.45) & (L < 0.99)
    g &= ndi.binary_dilation(ndi.binary_fill_holes(seed), iterations=150)
    g = ndi.binary_opening(g, np.ones((2, 2)))
    if g.sum() < 500:
        return None
    edges = cv2.Canny((np.clip(L, 0, 1) * 255).astype(np.uint8), 30, 90)
    edges = edges & ndi.binary_dilation(g, iterations=6).astype(np.uint8)
    segs = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=40,
                           minLineLength=70, maxLineGap=14)
    if segs is None:
        return None
    seg = segs.reshape(-1, 4)
    ang = np.degrees(np.arctan2(seg[:, 3] - seg[:, 1], seg[:, 2] - seg[:, 0])) % 180
    ln = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    h, be = np.histogram(ang, bins=36, range=(0, 180), weights=ln)
    order = list(np.argsort(h)[::-1])
    a1 = (be[order[0]] + be[order[0] + 1]) / 2.0
    a2 = None
    for k in order[1:]:
        a = (be[k] + be[k + 1]) / 2.0
        d = abs(a - a1)
        d = min(d, 180 - d)
        if 25 <= d <= 155 and h[k] >= 0.25 * h[order[0]]:
            a2 = a
            break
    if a2 is None:
        return None

    def fam(a, tol=12.0):
        d = np.abs(ang - a)
        return seg[np.minimum(d, 180 - d) < tol]

    f1, f2 = fam(a1), fam(a2)
    if len(f1) < 2 or len(f2) < 2:
        return None
    # 四条极值线：方向取 Hough 的两个主族；偏移取「线段端点 + 板证据像素」的极值。
    # ★ 只用 Hough 线段会漏掉「近白的板边」（白对白没有 Canny 边），板的厚度侧壁就补不上；
    #   只用证据像素又会被断线带偏。两者合并，取 1%/99% 分位抗离群。
    ys, xs = np.nonzero(seed)
    P = np.stack([xs, ys], 1).astype(np.float64)

    def extremes(a, sel):
        # ★ 偏移只用【证据像素】的分位数：Hough 线段的端点会顺着延长线跑到板外
        #   （实测 y 轴箭头那条线把角点推到 x=-37 / x=1193）。
        n = np.array([-np.sin(np.radians(a)), np.cos(np.radians(a))])
        rv = P @ n
        return (n, float(np.percentile(rv, 1))), (n, float(np.percentile(rv, 99)))

    l1a, l1b = extremes(a1, f1)
    l2a, l2b = extremes(a2, f2)

    def cross(p, q):
        M_ = np.array([p[0], q[0]])
        if abs(np.linalg.det(M_)) < 1e-6:
            return None
        return np.linalg.solve(M_, np.array([p[1], q[1]]))

    cs = [cross(l1a, l2a), cross(l1a, l2b), cross(l1b, l2b), cross(l1b, l2a)]
    if any(c is None for c in cs):
        return None
    cs = np.array(cs, np.float64)
    if (cs[:, 0].min() < -5 or cs[:, 0].max() > W + 5
            or cs[:, 1].min() < -5 or cs[:, 1].max() > H + 5):
        return None
    out = np.zeros((H, W), np.uint8)
    cv2.fillPoly(out, [cs.astype(np.int32)], 1)
    q = out.astype(bool)
    # ③ 检出的灰必须几乎全在拟合四边形里（seed 是「可见证据」，不是「完整面积」——
    #    用 IoU 会误杀：证据只覆盖板的可见部分，拟合要补的是被挡住/近白的那部分）。
    sv = float(seed.sum())
    if sv <= 0 or float((q & seed).sum()) / sv < 0.80:
        return None
    # ④ 面积不许离证据太远（1.2x–6x；实测喷注淬火 42.4k -> 167k = 3.9x）
    if not (1.2 * sv <= float(q.sum()) <= 6.0 * sv):
        return None

    # ⑤ ★ 外接平行四边形的「空角」要裁掉（v4.21）。平行四边形是**外接**拟合：
    #   证据少一个角（被别的物体挡住）时，两条边的延长线会在空处相交，整块背景
    #   被算成板 —— 实测喷注淬火图右后角被推到 (1131,595)，那里是纯背景，
    #   S1 的 bbox 因此比真板宽 100 px，SLIC 边界吸附又把这 100 px 撑成台阶。
    #   裁法：只保留「离可见证据 <= tol」的部分（被 QGP 挡住的那一角本来也归 QGP 的
    #   z 序，裁掉不丢可见像素）；保住直边的形状，不做任何重拟合。
    tol = int(max(24.0, 0.030 * min(H, W)))
    qq = q & ndi.binary_dilation(seed, iterations=tol)
    if float(qq.sum()) < 1.05 * sv:     # 裁过头（板只有几块可见碎片）就别用平行四边形
        return None
    if float(q.sum() - qq.sum()) > 0.02 * float(q.sum()):
        # 真被裁过：裁出来的边界是「膨胀 27 px」的锯齿边，再收一次成 4 角直线边
        #（不这么做，边界吸附会沿锯齿长出台阶 —— 实测 S1 右缘全是 30 px 的台阶）
        qq = _quad(ndi.binary_fill_holes(qq))
    return qq


def _quad(mask):
    """把一个平面块的凸包简化成 4 个角（板是斜的平行四边形）"""
    try:
        import cv2
    except Exception:
        return mask
    m = ndi.binary_fill_holes(ndi.binary_closing(mask, np.ones((31, 31))))
    m = ndi.binary_erosion(m, iterations=3)
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return mask
    c = max(cs, key=cv2.contourArea)
    hull = cv2.convexHull(c)
    for eps in (0.002, 0.005, 0.01, 0.02, 0.04):
        ap = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
        if len(ap) == 4:
            out = np.zeros(mask.shape, np.uint8)
            cv2.fillPoly(out, [ap], 1)
            return out.astype(bool)
    return mask


# ── 地标发现：**只按形态**，不看 IR（IR 在下一步才来认领） ────────────────
def _ellipsoids(S, minpx=4000, maxfrac=0.10):
    """单色椭球团块（核子）：只按【形状】认，与颜色无关。

    ★ 为什么需要（v4.21 实测，UPC）：① 的球团判据是「红蓝两色在同一半径内共现」，
      只适用于「一撮核子球」画法的核；UPC 那种整块椭球核压根不触发，于是两个核
      落进 ③「深 + 饱和 + 够大」的实心箭头里 —— 实测蓝核 73.8% / 红核 46.1%
      被 A1 拿走，剩下的才轮到板（26.2% / 10.8%）。
    判据（全部与色相无关）：对【整块】拟合椭圆、长宽比 1.5–3.6、椭圆填充率
      >=0.80、凸性 >=0.85、bbox 短边 >=45、面积 4000..10% 画布。
    标定：UPC 命中 2 个（29296 / 31442 px，bbox 139x272 / 156x253）；
      喷注淬火 QGP 长宽比 1.26 -> 0 命中（seg_v18 与 seg_v17b 逐元素 px 完全一致）。
    """
    try:
        import cv2
    except Exception:
        return []
    mx, sat = S["mx"], S["sat"]
    H, W = mx.shape
    # ★ 只用饱和度、不压亮度上限：红核的高光面 mx 可到 230+，旧判据 mx<210
    #   把核切掉一半，拟合出的椭圆只剩暗侧（UPC 实测 N2 7668 px / A1 抢走 14897 px）。
    m = ((sat > 0.18) & (mx < 248)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        a = int(st[i, cv2.CC_STAT_AREA])
        if a < minpx or a > maxfrac * H * W:
            continue
        w, h = int(st[i, cv2.CC_STAT_WIDTH]), int(st[i, cv2.CC_STAT_HEIGHT])
        if min(w, h) < 45 or max(w, h) < 90:
            continue
        comp = (lb == i)
        # ★ v4.21c：对【整块】拟合。上面 (sat>0.18)&(mx<248) 的掩膜已经把中性灰
        #   速度箭头排除在外（UPC 实测两块 bbox 139x272 / 156x253，正好是核本身），
        #   所以不需要再用「厚核」缩小范围 —— 用厚核拟合会把椭圆缩到 74x198，
        #   只剩核的暗侧，反而让 A1 的 z 序把另一半抢走。
        cnts = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_NONE)[0]
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        if len(c) < 5:
            continue
        (cx, cy), (MA, ma), ang = cv2.fitEllipse(c)
        ellA = np.pi * (MA / 2.0) * (ma / 2.0) + 1e-6
        fillE = a / ellA
        sol = a / (cv2.contourArea(cv2.convexHull(c)) + 1e-6)
        asp = max(MA, ma) / max(1.0, min(MA, ma))
        if 1.5 <= asp <= 3.6 and fillE >= 0.80 and sol >= 0.85:
            ell = np.zeros(mx.shape, np.uint8)
            cv2.ellipse(ell, ((cx, cy), (MA, ma), ang), 1, -1)
            out.append(comp & ndi.binary_dilation(ell > 0, iterations=2))
    return out


def landmarks(S):
    """只按形态找地标（IR 在下一步才来认领）。顺序有依赖：球团/暖橙的掩膜后面要用。"""
    L, sat, ink = S["L"], S["sat"], S["ink"]
    r, g, b, mx, mn = S["r"], S["g"], S["b"], S["mx"], S["mn"]
    out = {"solid": [], "cluster": [], "warm": [], "plane": [], "dark": []}

    # ① 核子球团（种子）：红蓝两色在同一个半径内共现 —— 一个物理核 = 一撮球，不是逐个球
    redm = (r > b + 18) & (sat > 0.25) & (g < r - 10)
    bluem = (b > r + 12) & (sat > 0.25)
    both = _grow(redm, 30) & _grow(bluem, 30)
    both = ndi.binary_fill_holes(ndi.binary_closing(both, np.ones((15, 15))))
    for m, px in _pieces(both, 40000):
        out["cluster"].append(_desc(S, m))

    # ①b 单色椭球核（v4.21）：整块椭球的核不满足「红蓝共现」，会被 ③ 当成实心箭头
    for m in _ellipsoids(S):
        d = _desc(S, m)
        d["src"] = "ellipse"
        out["cluster"].append(d)

    # ② 暖橙：光子线 + 顶点 + 末态箭头在位图上连成一片，留给 split_warm 按 z 序剥。
    #   ★ 顶点的【白热核心是白色】（实测 RGB(246,224,204)、r-b=42 但 b=204>130），
    #     压根不在「暖橙」颜色判据里 —— 必须按「亮 + 微暖 + 紧凑」单独认回来，
    #     否则那块 3584 px 的白核谁也认领不到（旧版实测它落在 lab==-1 的洞里）。
    warm_s = (r > 140) & (b < 130) & (r - b > 60) & (g > b + 15) & (g < r - 5)
    orange = (r > b + 35) & (r > g + 15) & (sat > 0.30)      # 暗橙边也算橙，但要挨着暖色
    warm = warm_s | (ndi.binary_dilation(warm_s, iterations=6) & orange)
    gc = (L >= 0.80) & (sat > 0.06) & (r >= b + 15)
    lg, ng = ndi.label(ndi.binary_closing(gc, np.ones((5, 5))))
    cg = np.bincount(lg.ravel(), minlength=ng + 1)
    gcore = np.zeros(mx.shape, bool)
    for k in np.argsort(cg[1:])[::-1] + 1:
        if cg[k] < 500:
            break
        ys, xs = np.nonzero(lg == k)
        if float(cg[k]) / max(1, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) >= 0.50:
            gcore = (lg == k)
            break
    # ★ v4.21d：椭球核（尤其红核）本身落在暖橙色判据里，若不排除，split_warm()
    #   会把红核左半当成「末态轻子对」的厚箭头抢走（UPC 实测 N2 左半 79% 归 P1）。
    cl_seed = np.zeros(mx.shape, bool)
    for d in out["cluster"]:
        cl_seed |= d["mask"]
    wa_all = np.zeros(mx.shape, bool)
    for m, px in _pieces((warm | gcore) & ~cl_seed, 4000, close=7):
        out["warm"].append(_desc(S, m))
        wa_all |= m

    # ③ 实心实体箭头（速度箭头）：深 + 饱和 + 够大，且**不在球团 / 暖橙里**。
    #   ★ 旧规则漏了这两条排除：核子球团里的暗红球连成 115437 / 85623 px 的大块，
    #     按「取最大的 ×2」就把整个核当成了速度箭头（实测 A1 bbox 1343x801 横跨两核）。
    cl_all = np.zeros(mx.shape, bool)
    for d in out["cluster"]:
        cl_all |= d["mask"]
    for m, px in _pieces((mx < 175) & (sat > 0.30) & ~cl_all & ~wa_all, 12000):
        out["solid"].append(_desc(S, m))
    so_all = np.zeros(mx.shape, bool)
    for d in out["solid"]:
        so_all |= d["mask"]

    # ④ 浅灰板面：低饱和的灰 -> 收成 4 角平行四边形。
    #   ★ 两级判据（v4.19）：
    #     ④a【严】sat<0.12 & 0.50<L<0.90 —— 真板的颜色。喷注淬火图里 QGP 的火光在
    #        旧宽判据（sat<0.22）下会把板、QGP 外晕、网格线连成一整块（实测 708766 px，
    #        bbox 1361x809 = 87% 画布高，QGP 被整块吞进板里）。严判据只留板。
    #     ④b【宽】旧判据保留，供「板占画面大半 + 下半被压暗」的图（UPC）用。
    #     两个候选都交给 assign()，由 _plane_ok() 用「几何 + 颜色纯度」选，不是谁大选谁。
    bg0 = (L > 0.965) & (sat < 0.045)
    bg_strict = (L > 0.992) & (sat < 0.03)
    Himg, Wimg = mx.shape

    def _pl(m, src, seed=None):
        # 用板上的网格线把凸包撑开（亮角在主掩膜凸包之外），再用四边形收边
        near = ndi.binary_dilation(ndi.binary_fill_holes(m), iterations=40)
        grid = near & (sat < 0.22) & (ink > 6) & (L > 0.50) & (L < 0.965) & (~bg_strict)
        hull = _hull_mask(ndi.binary_fill_holes(m) | grid)
        bright = (~bg_strict) & (sat < 0.25) & (L > 0.45)
        m2 = ndi.binary_fill_holes(m | (hull & bright))
        qp = _plane_para(S, seed if seed is not None else m)
        d = _desc(S, qp if qp is not None else _quad(m2))
        d["para"] = bool(qp is not None)
        d["px"] = int(m2.sum())
        d["src"] = src
        d["medsat"] = float(np.median(sat[d["mask"]]))
        d["medL"] = float(np.median(L[d["mask"]]))
        out["plane"].append(d)

    # ④a 严：真正的板是严格低饱和的灰；只要落在下半画布的连通块（上半的灰多是箭头）
    gm = (~bg0) & (sat < 0.12) & (L > 0.50) & (L < 0.90) & (ink > 6)
    labg, ng = ndi.label(ndi.binary_closing(gm, np.ones((15, 15))))
    cg = np.bincount(labg.ravel(), minlength=ng + 1)
    cand = np.zeros(mx.shape, bool)
    for k in np.argsort(cg[1:])[::-1] + 1:
        if cg[k] < 500:
            break
        ys, xs = np.nonzero(labg == k)
        if (xs.max() - xs.min() + 1) < 50 or (ys.max() - ys.min() + 1) < 20:
            continue
        if (ys.min() + ys.max()) / 2.0 < 0.42 * Himg:
            continue
        cand |= (labg == k)
    if cand.any():
        # 最大那块 = 板本体；同色判据下的文字抗锯齿 / 轴杆只参与凸包，不参与平行四边形拟合
        #（实测：把 [227,394] 的「gluon」字抗锯齿算进证据，拟合出的角会被推到板外）
        labc, nc = ndi.label(ndi.binary_closing(cand, np.ones((15, 15))))
        cc = np.bincount(labc.ravel(), minlength=nc + 1)
        main = (labc == int(np.argmax(cc[1:])) + 1)
        _pl(ndi.binary_fill_holes(ndi.binary_closing(cand, np.ones((15, 15)))), "strict",
            seed=ndi.binary_fill_holes(ndi.binary_closing(main, np.ones((15, 15)))))

    # ④b 宽：旧判据（板占画面大半、下半被压暗的图，如 UPC）
    for m, px in _pieces((~bg0) & (sat < 0.22) & (L > 0.52) & (L < 0.995) & (ink > 6),
                         60000, close=41):
        _pl(m, "broad")

    # ⑤ ★ 把球团的【可见剪影】补全：种子的形态判据（两色共现半径 30 px）会在核的边缘
    #    切掉一圈暗边（实测左核左边被切掉一块 3017 px 的暗红 —— 那是核物质，不是背景）。
    #    做法：在「非背景 / 非板灰 / 非实体箭头 / 非暖橙」的域里，离种子 45 px 以内取连通域。
    #    45 px 的上限保证不会顺着板面爬到别处去。
    #    ★ 板灰判据取 (sat<0.22)&(L>0.55)：收紧到 (sat<0.12)&(L>0.60) 时板的网格线与暗面
    #      会留在域里，两个核顺着它们连成一片（实测 N2 剪影炸到 480934 px / 1475x876）。
    bg = (L > 0.965) & (sat < 0.035)
    plane_obv = (sat < 0.22) & (L > 0.55)
    dom = (~bg) & (~plane_obv) & (~so_all) & (~wa_all)
    ld, nd_ = ndi.label(dom)
    cdom = np.bincount(ld.ravel(), minlength=nd_ + 1)
    cl_all = np.zeros(mx.shape, bool)
    for d in out["cluster"]:
        if d.get("src") == "ellipse":
            # ★ 椭球种子已经是完整的可见剪影（含高光面），不能再走 ⑤ 的 dom：
            #   dom 会排除「低饱和 + 亮」的像素，恰好把红核顶部的高光切掉
            #   （UPC 实测 N2 只剩 75.7%，其余 24.2% 归了身后的板 S1）。
            m = ndi.binary_fill_holes(d["mask"])
            d.update(_desc(S, m))
            cl_all |= d["mask"]
            continue
        # 球团种子仍按旧逻辑补 45 px 暗边。
        grow = _grow(d["mask"], 45) & dom
        lbg, ng = ndi.label(grow)
        if ng:
            ov = np.bincount(lbg[d["mask"]].ravel(), minlength=ng + 1).astype(float)
            ov[0] = 0
            if ov.any():
                m = ndi.binary_fill_holes(lbg == int(np.argmax(ov)))
                d["seed_px"] = d["px"]
                d["seed_bbox"] = d["bbox"]
                d.update(_desc(S, m))
        cl_all |= d["mask"]

    # ⑥ 深色笔画（三轴图标 / 文字 / b 标注）
    #   ★ 只按「有多暗」（mn<110）判，**不能带 sat 条件** —— 纯黑像素 sat=(mx-0)/mx≈1.0，
    #     实测把 b 的虚线整段漏掉了。且 minpx 设 250 太大：虚线只有 26x7=181 px/段。
    #   ★ obj（= 不是什么独立元素）只算 实体箭头 / 球团 / 暖橙，**不能算板** ——
    #     板的外接四边形覆盖整张画布，一算就把所有深色块都判成「在物体里」。
    obj = (ndi.binary_dilation(so_all | cl_all, iterations=5)
           | ndi.binary_dilation(wa_all, iterations=8))
    # ★ v4.19：被暖色物体【整块包住】的暗块（介质表面的暗纹 / 网格）也算「在里面」。
    #   旧判据只看「离物体 8 px 内的重叠 >= 60%」—— 介质里 190x135 的暗纹洞离边界 8 px
    #   以上，判成「不在物体里」，于是被当成字形塞进文字层（实测 32.8k px 的 L1 里
    #   有 21k px 是介质暗纹）。拓扑判据：落在 fill_holes(物体) 里面就是它的纹理。
    wa_fill = ndi.binary_fill_holes(wa_all)
    cl_fill = ndi.binary_fill_holes(cl_all)
    for m, px in _pieces((mn < 110) & ~so_all & ~wa_all, 120, close=3):
        d = _desc(S, m)
        d["in_obj"] = (float((d["mask"] & obj).sum()) / max(1, d["px"]) >= 0.60
                       or float((d["mask"] & (wa_fill | cl_fill)).sum()) >= 0.90 * d["px"])
        out["dark"].append(d)

    # ⑦ ★ 落在物体里的深色像素 = 那个物体自己的暗面 / 描边（实体箭头的暗描边、末态箭头
    #    背光的暗面、核的暗球），归回给所属物体。不归就会在成图上留一堆黑洞
    #    （实测 162k px 非背景像素没人认领，其中就有末态箭头背光的三大块）。
    #    归属判据：与该物体外扩 8 px 的重叠最大，且重叠 >= 该块的 30%；
    #    只把「离该物体 14 px 以内」的部分并进去，免得顺手吞掉远处的字。
    objs = out["solid"] + out["cluster"] + out["warm"]
    for d in out["dark"]:
        if not d["in_obj"]:
            continue
        best, bs, inside = None, 0.0, False
        for o in objs:
            v = float((d["mask"] & ndi.binary_dilation(o["mask"], iterations=8)).sum())
            if float((d["mask"] & ndi.binary_fill_holes(o["mask"])).sum()) >= 0.90 * d["px"]:
                v, inside = float(d["px"]), True       # 整块在物体外轮廓内部
            if v > bs:
                best, bs, ins = o, v, inside
        if best is None or bs < 0.30 * d["px"]:
            continue
        if ins:
            add = d["mask"]                          # 内部纹理：整块都归它
        else:
            add = d["mask"] & ndi.binary_dilation(best["mask"], iterations=14)
        if add.sum() < 0.50 * d["px"]:
            continue
        best.update(_desc(S, best["mask"] | add))
    return out


def _iou_bbox(b1, b2):
    x0, y0 = max(b1[0], b2[0]), max(b1[1], b2[1])
    x1, y1 = min(b1[2], b2[2]), min(b1[3], b2[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    return inter / max(1, a1) > 0.5


def pick_axes(darks):
    """三轴图标 = 深色细笔画里【填充率极低 + 笔画极细 + 够大 + 没压在实体块上】的那块。
    ★ 实测标定（cand_s4192）：三轴图标 fill=0.08 / maxthick=14.4 / 335x356；
      左核球团的暗球连通块 fill=0.38 / maxthick=33.2（旧规则「取最大」就错在这儿）；
      红/蓝箭头暗描边 fill=0.06 但落在实体块里（in_obj -> 不是独立元素）。

已知边界：**本步不做遮挡补全** —— 完全被挡住的元素拿不到轮廓，只出「缺了多少」的读数。
IR 里声明「穿过、半透、还看得见」的（composition.穿透 + 露出）算可见像素，在本步内。
配套说明见 skill 的 references/bitmap-to-vector.md §2.5。"""
    c = [d for d in darks if d["fill"] < 0.20 and d["maxthick"] <= 24
         and min(d["w"], d["h"]) >= 120 and not d["in_obj"]]
    return max(c, key=lambda d: d["px"]) if c else None


def pick_dim(darks, used):
    """碰撞参数 b 这类「标注」= 竖直双向细箭头 + 两端水平虚线（+ 竖直虚线参考线）。
    实测（cand_s4192）：杆 51x221（h/w=4.3，maxthick≈7）；虚线每段约 40x12。
    ★ 虚线判据用「拉长或近矩形」，不能用 fill 阈值 —— 字形 b(44x62,fill .46)、
      gamma(42x68)、e-(43x45) 都不满足，虚线满足；竖直参考线也是同一族。"""
    free = [d for d in darks if not used.get(id(d)) and not d["in_obj"]]

    def elong(d):
        return (max(d["w"], d["h"]) / max(1.0, min(d["w"], d["h"])) >= 2.0) or d["fill"] >= 0.70

    cand = [d for d in free if d["h"] / max(1, d["w"]) >= 2.2 and 90 <= d["h"] <= 900
            and d["maxthick"] <= 30 and d["fill"] <= 0.75]
    if not cand:
        return None, []
    shaft = max(cand, key=lambda d: d["px"])
    y0, y1 = shaft["bbox"][1], shaft["bbox"][3]
    dashes = []
    for d in free:
        if d is shaft or d["px"] < 120 or max(d["w"], d["h"]) > 200 or not elong(d):
            continue
        cy = (d["bbox"][1] + d["bbox"][3]) / 2.0
        if abs(cy - y0) <= 45 or abs(cy - y1) <= 45:
            dashes.append(d)
    if dashes:
        xs = [d["bbox"][0] for d in dashes] + [shaft["bbox"][0]]
        xe = [d["bbox"][2] for d in dashes] + [shaft["bbox"][2]]
        reg = (min(xs) - 60, y0 - 60, max(xe) + 60, y1 + 60)
        for d in free:
            if (d is shaft or any(d is x for x in dashes) or d["px"] < 120
                    or max(d["w"], d["h"]) > 200 or not elong(d)):
                continue
            cx = (d["bbox"][0] + d["bbox"][2]) / 2.0
            cy = (d["bbox"][1] + d["bbox"][3]) / 2.0
            if reg[0] <= cx <= reg[2] and reg[1] <= cy <= reg[3]:
                dashes.append(d)
    return shaft, dashes


def geometry_refine(ir, got, lms, S):
    """v4.21f：同色深灰元素按【几何 + 核/顶点锚点】重判。

    UPC 实测：速度箭头 A1、b、末态轻子对 P1、光子线 G1、三轴 T1 全是同一种深灰，
    颜色上完全不可分。旧流程里 P1 拿到左下速度箭头、G1 拿到 b、B1 拿到右轻子箭头
    + y 轴、T1 拿到左轻子箭头，A1 只剩 252 px。这里不再看颜色，改用：
      - 核旁水平实体箭头 -> A1（每个核一支）
      - 两核之间、竖直双向细箭头 -> B1
      - 顶点两侧、近水平的实体箭头 -> P1（最多两支）
      - 顶点上下、细而低填充的波形线 -> G1（两条）
      - 其余右侧三杆 -> T1
    只对名字里明确写了「速度 / 末态轻子 / 光子」的元素生效，别的图不会被误改。
    """
    H, W = S["L"].shape
    dark = np.zeros((H, W), bool)
    for d in lms.get("dark", []):
        dark |= d["mask"]
    nuc = [got[e["id"]] for e in ir
           if e["family"] == "cluster" and e["id"] in got]
    if len(nuc) < 2 or not dark.any():
        return got, []
    nuc_all = np.zeros((H, W), bool)
    for d in nuc:
        nuc_all |= d["mask"]

    def met(c):
        ys, xs = np.nonzero(c)
        w = int(xs.max() - xs.min() + 1)
        h = int(ys.max() - ys.min() + 1)
        th = float(ndi.distance_transform_edt(c).max())
        return (int(c.sum()), w, h, th, float(c.sum()) / max(1, w * h),
                float(xs.min() + xs.max()) / 2.0, float(ys.min() + ys.max()) / 2.0)

    # 顶点：V1 已经认出来就用它的中心；没有就用两核中心的中点
    vx = vy = None
    for e in ir:
        if e["family"] == "glow" and e["id"] in got:
            ys, xs = np.nonzero(got[e["id"]]["mask"])
            if len(xs):
                vx = float(xs.min() + xs.max()) / 2.0
                vy = float(ys.min() + ys.max()) / 2.0
            break
    ncent = [((d["bbox"][0] + d["bbox"][2]) / 2.0,
              (d["bbox"][1] + d["bbox"][3]) / 2.0) for d in nuc]
    if vx is None:
        vx = float(np.mean([c[0] for c in ncent]))
        vy = float(np.mean([c[1] for c in ncent]))

    e_speed = next((e for e in ir if e["family"] == "arrow" and e.get("n", 1) >= 2
                    and ("速度" in str(e.get("name", ""))
                         or "velocity" in str(e.get("name", "")).lower())), None)
    e_dim = next((e for e in ir if e["family"] == "dim"), None)
    e_lep = next((e for e in ir if e["family"] == "arrow" and e.get("n", 1) == 1
                  and ("末态" in str(e.get("name", ""))
                       or "轻子" in str(e.get("name", ""))
                       or "lepton" in str(e.get("name", "")).lower())), None)
    e_ph = next((e for e in ir if e["family"] == "stroke"
                 and ("光子" in str(e.get("name", ""))
                      or "photon" in str(e.get("name", "")).lower())), None)
    e_ax = next((e for e in ir if e["family"] == "axes"), None)

    # ① 速度箭头：核旁水平带状区域里，减去核本身后剩下的水平厚实体
    speed = np.zeros((H, W), bool)
    if e_speed is not None:
        for d in nuc:
            nm = d["mask"]
            ys, xs = np.nonzero(nm)
            cy = 0.5 * (ys.min() + ys.max())
            hh = ys.max() - ys.min() + 1
            band = np.zeros((H, W), bool)
            band[max(0, int(cy - 0.55 * hh)):min(H, int(cy + 0.22 * hh)), :] = True
            rem = dark & ~ndi.binary_dilation(nm, iterations=4) & band
            lab, k = ndi.label(rem)
            for i in range(1, k + 1):
                c = (lab == i)
                a, w, h, th, fill, cx, cyc = met(c)
                if a >= 400 and w >= 80 and w / max(1, h) >= 2.0 and 4.0 <= th <= 45.0:
                    speed |= c
        if speed.any():
            speed |= (ndi.binary_dilation(speed, iterations=1)
                      & (S["L"] < 0.82) & ~ndi.binary_dilation(nuc_all, iterations=2))

    # ② b：两核之间唯一一根竖直双向细箭头（离核最近的那根，不是右侧 y 轴）
    bmask = np.zeros((H, W), bool)
    if e_dim is not None:
        rest = dark & ~speed & ~nuc_all
        lab, k = ndi.label(rest)
        cand = []
        for i in range(1, k + 1):
            c = (lab == i)
            a, w, h, th, fill, cx, cyc = met(c)
            if a < 300 or h / max(1, w) < 2.2 or h < 90 or th > 35 or fill > 0.75:
                continue
            dmin = min(abs(cx - nc[0]) for nc in ncent)
            cand.append((dmin, -a, c))
        if cand:
            bmask = min(cand, key=lambda t: (t[0], t[1]))[2]
            bmask |= (ndi.binary_dilation(bmask, iterations=1)
                      & (S["L"] < 0.85) & ~ndi.binary_dilation(nuc_all, iterations=2))

    # ③ 末态轻子对：顶点两侧、近水平的实体箭头（最多左右各一支）
    lep = np.zeros((H, W), bool)
    if e_lep is not None:
        rest = dark & ~speed & ~bmask & ~nuc_all
        lab, k = ndi.label(rest)
        for i in range(1, k + 1):
            c = (lab == i)
            a, w, h, th, fill, cx, cyc = met(c)
            if a < 400 or w / max(1, h) < 2.0 or w < 100 or th > 25 or fill > 0.80:
                continue
            if abs(cyc - vy) <= 0.12 * H and abs(cx - vx) <= 0.22 * W:
                lep |= c
        if lep.any():
            lep |= (ndi.binary_dilation(lep, iterations=1)
                    & (S["L"] < 0.85) & ~ndi.binary_dilation(nuc_all, iterations=2))

    # ④ 光子交换线：顶点上下、细而低填充的波形线
    ph = np.zeros((H, W), bool)
    if e_ph is not None:
        rest = dark & ~speed & ~bmask & ~lep & ~nuc_all
        ny0 = min(d["bbox"][1] for d in nuc)
        ny1 = max(d["bbox"][3] for d in nuc)
        lab, k = ndi.label(rest)
        for i in range(1, k + 1):
            c = (lab == i)
            a, w, h, th, fill, cx, cyc = met(c)
            if a < 80 or th > 6 or fill > 0.45 or max(w, h) < 40:
                continue
            if abs(cx - vx) <= 0.06 * W and ny0 <= cyc <= ny1:
                ph |= c
        if ph.any():
            ph |= (ndi.binary_dilation(ph, iterations=1)
                   & (S["L"] < 0.92) & ~ndi.binary_dilation(nuc_all, iterations=2))

    # ⑤ 三轴：当前 axes 掩膜里去掉轻子箭头 / b / 速度箭头
    axes = np.zeros((H, W), bool)
    if e_ax is not None and e_ax["id"] in got:
        axes = got[e_ax["id"]]["mask"] & ~lep & ~bmask & ~speed
    elif e_ax is not None:
        # ★ 初始检测漏掉三轴时（UPC 实测：三根杆全压在板面上 -> in_obj；唯一在板外的
        #   种子是那支标错的短箭头，删掉它就再也认不出三轴），改用专用中灰阈值
        #   （杆身 mn≈120，板面 mn≈230）+ 右侧聚类重新组：
        #   cx>=0.60W、足够长的笔画、不与文字层抢。字形（<80 px）与公式不会进来。
        txt = np.zeros((H, W), bool)
        for e2 in ir:
            if e2["family"] == "text" and e2["id"] in got:
                txt |= got[e2["id"]]["mask"]
        axm = ((S["mn"] < 150) & ~speed & ~bmask & ~lep & ~ph & ~nuc_all
               & ~ndi.binary_dilation(txt, iterations=2))
        lab, k = ndi.label(ndi.binary_closing(axm, np.ones((3, 3))))
        rods = []
        for i in range(1, k + 1):
            c = (lab == i)
            a, w, h, th, fill, cx, cyc = met(c)
            if a < 250 or max(w, h) < 80 or th > 30:
                continue
            if cx < 0.60 * W:
                continue
            if float((c & txt).sum()) > 0.30 * a:
                continue
            ys2, xs2 = np.nonzero(c)
            q = np.stack([xs2 - xs2.mean(), ys2 - ys2.mean()], 1).astype(np.float64)
            ev, evec = np.linalg.eigh(np.cov(q.T))
            ang = float(np.degrees(np.arctan2(evec[1, -1], evec[0, -1]))) % 180.0
            rods.append((a, ang, _bbox(c), c))
        if len(rods) >= 2:
            def _rgap(b1, b2):
                dx = max(0, max(b1[0], b2[0]) - min(b1[2], b2[2]))
                dy = max(0, max(b1[1], b2[1]) - min(b1[3], b2[3]))
                return float(np.hypot(dx, dy))
            pair = False
            for i2 in range(len(rods)):
                for j2 in range(i2 + 1, len(rods)):
                    da = abs(rods[i2][1] - rods[j2][1])
                    da = min(da, 180.0 - da)
                    if da > 20.0 and _rgap(rods[i2][2], rods[j2][2]) <= 80.0:
                        pair = True
                        break
                if pair:
                    break
            if pair:
                axes = np.zeros((H, W), bool)
                for r in rods:
                    axes |= r[3]
                for d in got.values():
                    d["mask"] = d["mask"] & ~axes
                    d["px"] = int(d["mask"].sum())
                    d["bbox"] = _bbox(d["mask"])
                got[e_ax["id"]] = _wrap("axes", axes, S)
                print("   [三轴] 初始未找到 -> 几何重组 %d 根暗杆（%d px）"
                      % (len(rods), int(axes.sum())))

    rows = []
    for e in ir:
        eid = e["id"]
        if eid not in got:
            continue
        if e is e_speed and speed.any():
            got[eid] = _wrap("arrow", speed, S)
            rows.append((eid, "几何重判：核旁水平实体箭头 ×2（%d px）" % int(speed.sum())))
        elif e is e_dim and bmask.any():
            got[eid] = _wrap("dim", bmask, S)
            rows.append((eid, "几何重判：两核之间竖直双向箭头（%d px）" % int(bmask.sum())))
        elif e is e_lep and lep.any():
            got[eid] = _wrap("arrow", lep, S)
            rows.append((eid, "几何重判：顶点两侧近水平实体箭头（%d px）" % int(lep.sum())))
        elif e is e_ph and ph.any():
            got[eid] = _wrap("stroke", ph, S)
            rows.append((eid, "几何重判：顶点上下两条细波形线（%d px）" % int(ph.sum())))
        elif e is e_ax and axes.any():
            got[eid] = _wrap("axes", axes, S)
            rows.append((eid, "几何重判：去掉轻子箭头后的三轴（%d px）" % int(axes.sum())))
    return got, rows


def _disk_mask(r):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r * r

def _open_disk(mask, r):
    """半径 r 的圆盘开运算。scipy 的大 footprint 侵蚀是 O(N·r²)：1.5 M 像素要 40 s；
    cv2 的椭圆核是优化过的，同一张图 < 0.1 s。"""
    try:
        import cv2
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
    except Exception:
        return ndi.binary_opening(mask, _disk_mask(r))


def pick_blob(warm_list, S):
    """从暖色连通块里取「大而厚」的介质主体：大半径圆盘开运算去掉细喷注/光丝。

    返回 (主体掩膜, 全部暖色掩膜, 白热顶点核心掩膜)。
    ★ 判据只有【厚度】：介质是唯一能容下 r≈3% 短边 圆盘的那一块；喷注是细锥/细线，
      开运算后一定消失（实测喷注淬火：r=28 时 200602 -> 取最大块 184157，两条喷注
      整体被剥掉；宽 20-40 px 的喷管容不下 57x57 的圆盘）。
    ★ 开运算会削掉介质的【羽化外晕】一圈：外晕颜色仍是暖橙、又落在主体外轮廓凸包内
      —— 按「凸包内 + 暖橙（g/r<=0.62）」并回来。亮黄喷注的 g/r 明显更高，不会被吞。
    """
    if not warm_list:
        return None, None, None
    warm = np.zeros(S["L"].shape, bool)
    for d in warm_list:
        warm |= d["mask"]
    H, W = warm.shape
    r = max(12, int(round(0.030 * min(H, W))))
    op = _open_disk(warm, r)
    lab, n = ndi.label(op, np.ones((3, 3)))
    if n == 0:
        return None, warm, None
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    k = int(np.argmax(cnt[1:])) + 1
    if cnt[k] < 0.12 * warm.sum():                 # 没有明显更厚的块 = 这张图没有介质主体
        return None, warm, None
    q = ndi.binary_fill_holes(ndi.binary_closing(lab == k, np.ones((15, 15))))
    hull = _hull_mask(q)
    halo = warm & hull & ~q
    if halo.any():
        ly, nx = ndi.label(halo, np.ones((3, 3)))
        add = np.zeros_like(q)
        for kk in range(1, int(nx) + 1):
            mm = ly == kk
            if mm.sum() < 40:
                continue
            gr = float(S["g"][mm].mean()) / max(1.0, float(S["r"][mm].mean()))
            if gr <= 0.62:
                add |= mm
        if add.any():
            q = ndi.binary_fill_holes(q | add)
    # 顶点留给 pick_jets：它要用「两条喷注轴线的延长线」来定，光看亮度会选错
    return q, warm, None


def medium_strokes(q, jets_mask, S):
    """介质内部的【细亮笔画】（胶子轫致辐射线 / 分支线）。

    ★ 白顶帽（L - grey_opening）能把「局部比背景亮」的线提出来，但介质边缘的高光带
      比介质内部亮得多，也会被提出来。两条排除：
      ① 离介质边界 > 20 px（高光带贴着轮廓）；
      ② 笔画厚度 <= 5 px（高光带是 15-25 px 的厚带）。
    产物是「介质自己的表面纹理 + 从顶点分出的细线」，不含边缘高光、不含喷注主锥。
    """
    L = S["L"]
    th = L - ndi.grey_opening(L, size=(19, 19))
    din = ndi.distance_transform_edt(q)
    cand = (q & (th > 0.10) & (S["g"] > 0.35 * S["r"]) & (S["g"] < 0.78 * S["r"])
            & (din > 20) & ~jets_mask)
    thick = ndi.distance_transform_edt(cand)
    m = cand & (thick <= 5.0)
    lab, n = ndi.label(m, np.ones((3, 3)))
    if n == 0:
        return m
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    return np.isin(lab, [k for k in range(1, n + 1) if cnt[k] >= 40])


def _pick_vertex(q, comps, S, anchor=None):
    """顶点 = 介质内的【白热紧凑核】。选法按可靠性排序：

    ① IR 给了 `params.锚点`（归一化）-> 在锚点附近取白热核（最可靠：IR 是语义来源）；
    ② 否则退到「峰值最亮 + 离介质边界足够远」—— 只用亮度会选到介质边缘的白色高光点
      （实测 V1 跑到 (540,640)，喷注的左右分割线随之全错）。
    """
    cc, nc = ndi.label(np.where(q, S["L"] >= 0.78, False))
    if not nc:
        return np.zeros_like(q)
    cnt = np.bincount(cc.ravel(), minlength=nc + 1)
    ok = [k for k in range(1, int(nc) + 1) if 30 <= cnt[k] <= 2000]
    if not ok:
        return np.zeros_like(q)
    # 轴线 = 「入口（离介质最近的点） -> 远端（离入口最远的点）」
    # ★ 不能用 PCA 主轴：宽扇形喷注（被淬火那条）的主轴会被宽度带成水平，
    #   实测把 (540,640) 的白色高光点判成在轴线上（偏差 46 px < 50）。
    qy, qx = np.nonzero(q)
    qc = np.array([qx.mean(), qy.mean()]) if len(qx) else np.zeros(2)
    lines = []
    for m, cx, px in comps[:2]:
        ys, xs = np.nonzero(m)
        if len(xs) < 50:
            continue
        i0 = int(np.argmin((xs - qc[0]) ** 2 + (ys - qc[1]) ** 2))
        e = np.array([xs[i0], ys[i0]], float)
        j = int(np.argmax((xs - e[0]) ** 2 + (ys - e[1]) ** 2))
        d = np.array([xs[j], ys[j]], float) - e
        lines.append((e, d / max(1e-9, float(np.linalg.norm(d)))))
    if not lines:
        return np.zeros_like(q)
    H, W = q.shape
    vals = ndi.maximum(S["L"], cc, ok)
    din = ndi.distance_transform_edt(q)
    floor = 0.05 * min(H, W)
    cand = []
    for i, k in enumerate(ok):
        ys, xs = np.nonzero(cc == k)
        cand.append((float(vals[i]), k, np.array([xs.mean(), ys.mean()]),
                     float(din[cc == k].max())))
    if not cand:
        return np.zeros_like(q)
    # 物理闸门：顶点必须在介质【里面】，不能是贴着轮廓的高光（边界上 d_in≈0）
    good = [t for t in cand if t[3] >= floor] or cand
    if anchor is not None and len(anchor) == 2:
        ax, ay = float(anchor[0]) * W, float(anchor[1]) * H
        b = min(good, key=lambda t: (t[2][0] - ax) ** 2 + (t[2][1] - ay) ** 2)
        return (cc == b[1])
    return (cc == max(good, key=lambda t: t[0])[1])


def pick_jets(warm, q, core, ir, S, anchor=None):
    """把介质之外的暖色块按左右分给两条喷注；介质内部的亮黄段也按【顶点】左右分。

    ★ 分割线取【顶点】的 x，不是介质几何中心的 x —— 顶点本来就偏在一侧，用介质中心
      会把淬火喷注靠顶点的那一段分到对面去。
    ★ 逐个连通域不行（顶点处喷注与介质粘连）：介质外的按左右分；介质内的按顶点分。
    """
    H, W = q.shape
    rem = warm & ~ndi.binary_dilation(q, iterations=3)
    lab, n = ndi.label(rem, np.ones((3, 3)))
    comps = []
    if n:
        cnt = np.bincount(lab.ravel(), minlength=n + 1)
        for k in np.argsort(cnt[1:])[::-1] + 1:
            if cnt[k] < 300:
                break
            ys, xs = np.nonzero(lab == k)
            comps.append([lab == k, (xs.min() + xs.max()) / 2.0, int(cnt[k])])
    comps.sort(key=lambda t: -t[2])
    if core is None or not core.any():
        core = _pick_vertex(q, comps, S, anchor)
    left = np.zeros_like(q)
    right = np.zeros_like(q)
    for m, cx, px in comps[:2]:
        if cx < W / 2.0:
            left |= m
        else:
            right |= m
    # 邻近碎块并回同侧（喷注尾部的散点；离得远的不动，避免把别的东西吸进来）
    nl = ndi.binary_dilation(left, iterations=30) if left.any() else left
    nr = ndi.binary_dilation(right, iterations=30) if right.any() else right
    for m, cx, px in comps[2:]:
        if (m & nl).sum() >= 0.50 * px:
            left |= m
        elif (m & nr).sum() >= 0.50 * px:
            right |= m
    if core is not None and core.any():
        cy_, cx_ = np.nonzero(core)
        vx, vy = float(cx_.mean()), float(cy_.mean())
    else:
        cy_, cx_ = np.nonzero(q)
        vx = float(cx_.mean()) if q.any() else W / 2.0
        vy = float(cy_.mean()) if q.any() else q.shape[0] / 2.0
    # ★ 介质内的喷注段不能用「颜色阈值」抓：介质边缘的高光带也是亮黄（实测把 QGP
    #   右上缘 26k px 整条并进了逃逸喷注）。用几何：**顶点 -> 该侧外侧可见段质心** 的
    #   锥形走廊（半角 13°），喷注必须在这条线上；介质高光带很快偏离这条线。
    def _cone(m_out, half=5.0, rmax=0.020):
        ys, xs = np.nonzero(m_out)
        if len(xs) < 20:
            return np.zeros_like(q)
        ux, uy = xs.mean() - vx, ys.mean() - vy
        n = float(np.hypot(ux, uy))
        if n < 5:
            return np.zeros_like(q)
        ux, uy = ux / n, uy / n
        yy, xx = np.nonzero(q)
        px, py = xx - vx, yy - vy
        proj = px * ux + py * uy
        perp = np.abs(px * uy - py * ux)
        # 里侧段只到「外侧可见段的起点」为止：再往外走就是介质的另一侧轮廓了
        p_out = (xs - vx) * ux + (ys - vy) * uy
        p_end = float(np.percentile(p_out, 2))
        cap = max(10.0, rmax * W)
        ok = ((proj > 0) & (proj <= p_end)
              & (perp <= np.minimum(cap, np.maximum(6.0, np.tan(np.radians(half)) * proj))))
        m = np.zeros_like(q)
        m[yy[ok], xx[ok]] = True
        return m
    jetcol = (S["g"] > 0.65 * S["r"]) & (S["L"] > 0.55)
    inner = ((_cone(left) | _cone(right)) & jetcol & q & ~core)
    iy, ix = np.nonzero(inner)
    left[iy[ix < vx], ix[ix < vx]] = True
    right[iy[ix >= vx], ix[ix >= vx]] = True
    out = {}
    for e in ir:
        if e["family"] != "jet":
            continue
        nm = e["name"] or ""
        want_right = ("逃逸" in nm) or ("escape" in nm.lower()) or ("右" in nm)
        m = right if want_right else left
        out[e["id"]] = _wrap("jet", m, S) if m.any() else None
    return out, comps, core


def split_warm(blob, S, order):
    """把「橙色一大块」按 IR 的 z 序从前往后剥。
    ★ 三处实测标定（cand_s4192）：
      1) rad 取 blob 最大半宽的 0.45（末态箭头半宽最大 51.1、波浪线最大 13.4）——
         旧的固定 rad=7 把 96% 的橙色块都判成箭头；
      2) 顶点核心**必须锚在「最亮那一点所在连通域」**上，不能取「所有 L>阈值」——
         末态箭头上也有很亮的高光条，按阈值取会把整支箭的根部算成顶点；
         平滑后再找峰，避免单像素尖刺把核心判成 1 px；
      3) 光晕画在箭头【后面】：箭头在前先占，扣掉箭头后剩下的才是 V1 的可见光晕
         （IR z：P1=8 > V1=7 > G1=6）。只从箭头层里扣【白热核心】，不扣光晕。"""
    rem = blob.copy()
    rad = max(8.0, 0.45 * ndi.distance_transform_edt(blob).max())
    Ls = np.where(blob, ndi.gaussian_filter(S["L"], 5.0), -1.0)
    iy, ix = np.unravel_index(int(np.argmax(Ls)), Ls.shape)
    cc, _ = ndi.label(np.where(blob, Ls >= 0.72, False))
    core = (cc == cc[iy, ix]) & blob
    if core.sum() < 20:
        core = np.zeros_like(blob)
    H = max(30, int(round(0.020 * blob.shape[1])))          # 光晕宽度 ~ 画布宽的 2%
    halo = blob & ndi.binary_dilation(core, iterations=H) & (S["L"] >= 0.58)
    parts = []
    for e, kind in order:
        if kind == "arrow":
            m = _thick(rem, rad) & ~core
        elif kind == "glow":
            m = halo | core
        else:
            m = rem
        m = m & rem
        parts.append((e, m))
        rem = rem & ~m
    return parts, rem, core


def _angle_split(ang, k=2):
    """把「从同一点发出来的几支箭头」按方向角切成 k 组（圆上的 k-means，
    初值取直方图里间隔 >= 40° 的最高几个峰）。"""
    h = np.histogram(ang, bins=72, range=(0, 360))[0].astype(float)
    g = np.exp(-0.5 * (np.arange(-3, 4) / 1.2) ** 2)
    g /= g.sum()
    hs = np.convolve(np.r_[h[-3:], h, h[:3]], g, "same")[3:-3]
    cen = []
    for kk in np.argsort(hs)[::-1]:
        a = kk * 5.0 + 2.5
        if all(min(abs(a - c), 360 - abs(a - c)) > 40 for c in cen):
            cen.append(a)
        if len(cen) == k:
            break
    cen = np.array(cen, np.float64)
    lab = np.zeros(len(ang), int)
    for _ in range(20):
        d = np.abs(ang[:, None] - cen[None, :])
        d = np.minimum(d, 360 - d)
        lab = d.argmin(1)
        for j in range(len(cen)):
            if (lab == j).any():
                v = np.radians(ang[lab == j])
                cen[j] = np.degrees(np.arctan2(np.sin(v).mean(), np.cos(v).mean())) % 360.0
    return lab, cen


def arrow_dirs(mask, vertex=None, away=None):
    """量箭头的【有向】指向。
    · 从同一顶点发出来的几支（末态 e⁺e⁻）：**按相对顶点的方向角聚类**切开 ——
      用连通域不行（顶点处粘连，切开后只剩残段，主轴量出来是错的）。
    · 各自独立的一两支（速度箭头）：按连通域拆开，再用「哪一端尖」定方向。
      ★ PCA 只给无向的轴 —— 实测两支速度箭头 166.4° / 167.9° 看着平行，其实【相向】。
    """
    if vertex is not None:
        ys, xs = np.nonzero(mask)
        if len(ys) < 100:
            return []
        ang = np.degrees(np.arctan2(ys - vertex[1], xs - vertex[0])) % 360.0
        lab, cen = _angle_split(ang, 2)
        out = []
        # ★ 从顶点分出来的两支本来就各占总像素的一半左右；UPC 的 P1 合计 4164 px，
        #   按 3000 px 的硬阈值会把两支都丢掉（实测 ⑥ 里 P1 显示 "-"）。
        need = max(600, int(0.12 * int(mask.sum())))
        for j in range(cen.size):
            sel = lab == j
            if sel.sum() < need:
                continue
            qx = (xs[sel] - vertex[0]).astype(np.float64)
            qy = (ys[sel] - vertex[1]).astype(np.float64)
            rr = np.hypot(qx, qy)
            # ★ 只用「离顶点半径 50% 以远」的像素量方向：顶点附近两支箭的根部互相搭着，
            #   把那坨算进来会把方向往中间拉（实测 e⁻ 被拉到 75°，真值 ~95°）。
            keep = rr >= 0.50 * rr.max()
            qx, qy = qx[keep], qy[keep]
            rr = rr[keep]
            ev, evec = np.linalg.eigh(np.cov(np.stack([qx, qy], 1).T))
            u = evec[:, -1]
            if float(u @ np.array([qx.mean(), qy.mean()])) < 0:
                u = -u
            ang_pca = float(np.degrees(np.arctan2(u[1], u[0]))) % 360.0
            far = rr >= 0.75 * rr.max()
            ang_far = float(np.degrees(np.arctan2(qy[far].mean(), qx[far].mean()))) % 360.0
            out.append(dict(px=int(sel.sum()), angle=round(ang_pca, 1),
                            angle_far=round(ang_far, 1),
                            elong=round(float(np.sqrt(max(ev[-1], 1e-9) / max(ev[0], 1e-9))), 2),
                            center=[round(float(xs[sel].mean()), 1),
                                    round(float(ys[sel].mean()), 1)],
                            bbox=[int(xs[sel].min()), int(ys[sel].min()),
                                  int(xs[sel].max()), int(ys[sel].max())]))
        return sorted(out, key=lambda d: -d["px"])

    lab, n = ndi.label(mask)
    cnt = np.bincount(lab.ravel(), minlength=n + 1)
    out = []
    for k in np.argsort(cnt[1:])[::-1] + 1:
        if cnt[k] < 3000:
            continue
        ys, xs = np.nonzero(lab == k)
        p = np.stack([xs, ys], 1).astype(np.float64)
        cx, cy = p.mean(0)
        q = p - [cx, cy]
        w, v = np.linalg.eigh(np.cov(q.T))
        u, perp = v[:, -1], v[:, 0]
        t = q @ u
        span = float(t.max() - t.min())
        def wid(hi):
            sel = (t >= t.max() - 0.08 * span) if hi else (t <= t.min() + 0.08 * span)
            if sel.sum() < 10:
                return 1e9
            pp = q[sel] @ perp
            return float(pp.max() - pp.min())
        if away:
            # ★ 速度箭头：箭头尖端一定指向【远离自己那个核】的一端。
            #   宽度启发式会被「靠核那一端更宽」骗到（UPC 实测下箭头被量成 356°，
            #   明明该是向左）。用核中心 -> 箭头质心的方向给 PCA 轴定符号。
            nb = min(away, key=lambda p: (cx - p[0]) ** 2 + (cy - p[1]) ** 2)
            v = np.array([cx - nb[0], cy - nb[1]], float)
            tip = u if float(u @ v) >= 0 else -u
        else:
            tip = u if wid(True) < wid(False) else -u
        ang = float(np.degrees(np.arctan2(tip[1], tip[0]))) % 360.0
        elong = float(np.sqrt(max(w[-1], 1e-6) / max(w[0], 1e-6)))
        out.append(dict(px=int(cnt[k]), angle=round(ang, 1), elong=round(elong, 2),
                        center=[round(float(cx), 1), round(float(cy), 1)],
                        bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                        w_hi=round(wid(True), 1), w_lo=round(wid(False), 1)))
    return out


def _hull_mask(m):
    import cv2
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return m
    h = np.zeros(m.shape, np.uint8)
    cv2.fillPoly(h, [cv2.convexHull(max(cs, key=cv2.contourArea))], 1)
    return h.astype(bool)


def moment_ratio(m):
    """二阶矩主轴比 = 椭圆的长短轴比（与朝向无关）。bbox 的 h/w 会被倾斜压低。"""
    ys, xs = np.nonzero(m)
    q = np.stack([xs, ys], 1).astype(np.float64)
    q -= q.mean(0)
    w = np.linalg.eigvalsh(np.cov(q.T))
    return float(np.sqrt(max(w[-1], 1e-9) / max(w[0], 1e-9)))


def _wrap(fam, m, S, **extra):
    d = dict(family=fam, mask=m, px=int(m.sum()), bbox=_bbox(m), mean=_mean(S, m))
    d.update(extra)
    return d



# ═══════════════════════════════════════════════════════════════════════════
# v4.18  IR 驱动发现（候选源 x 形状族 x 数量 x 位置词 x z 序）+ 双引擎仲裁 + SAM 边界细化
#
# 为什么加：v4.17 的 landmarks() 用【写死的颜色族】（红蓝=核、橙=暖色系）建池，
# 完全没读 IR 的 material —— 于是换一张图就废（实测喷注淬火图：7/12，且 B1 认成
# 421901 px 的橙色火球）。本段把 material 编译成【颜色模型】：hex 锚点 +
# 「A → B」连成的**梯度线段**（渐变的中间色才不会漏）+ 语义色词兜底；
# 再用「相对阈值」建池（阈值 = 该元素最近的簇距离 + 族宽），所以位图配色漂移
# （实测 UPC N1 LabΔ 57.1）不影响建池。
#
# 不变量：**IR 给语义，可见像素给边界**；位图与 IR 不一致必须报出来，不许硬套。
# ═══════════════════════════════════════════════════════════════════════════
COLOR_WORDS = [("银灰", (198, 204, 214)), ("灰蓝", (140, 150, 170)), ("青蓝", (70, 190, 255)),
               ("暗红", (150, 40, 35)), ("深灰", (70, 74, 84)), ("浅灰", (214, 220, 226)),
               ("银", (200, 205, 215)), ("灰", (150, 155, 165)), ("黑", (30, 30, 34)),
               ("橙", (232, 135, 58)), ("青", (70, 190, 255)), ("蓝", (60, 100, 220)),
               ("红", (200, 60, 50)), ("绿", (60, 160, 80)), ("黄", (230, 200, 60)),
               ("紫", (120, 80, 200)), ("金", (230, 190, 120)), ("白", (252, 252, 250))]
SCREEN_DIR = [("右上", (1, -1)), ("左上", (-1, -1)), ("右下", (1, 1)), ("左下", (-1, 1)),
              ("右侧", (1, 0)), ("左侧", (-1, 0)), ("右边", (1, 0)), ("左边", (-1, 0)),
              ("上方", (0, -1)), ("下方", (0, 1)), ("之上", (0, -1)), ("之下", (0, 1))]
# 族的池宽（Lab 距离，加在该元素「最近的簇」之上）
# 球团（核子簇）纹理源的取值区间：低饱和灰。CLU_L_LO 决定“被遮住的暗侧腿”能不能进来（实测：
# 0.40 会把核子簇下缘的阴影腿整块排除，N1 对参考的覆盖率只 0.82）。
CLU_SAT, CLU_L_LO, CLU_L_HI = 0.22, 0.22, 0.92
#   标定（jet_q_final_2x，对 trace 参考）：0.40 -> N1 IoU 0.600 / 覆盖 0.766、N2 0.552 / 0.633；
#   0.22 -> N1 0.625 / 0.800、N2 0.582 / 0.678，纯度不降（0.735->0.741、0.812->0.804），
#   其余元素逐项不动。UPC 不受影响（十项老引擎全过闸门，用不到新引擎的球团源）。
TAU_BY_FAMILY = {"cluster": 9.0, "blob": 30.0, "arrow": 30.0, "stroke": 20.0,
                 "glow": 22.0, "arc": 14.0, "plane": 14.0, "other": 14.0}
# v4.18 闸门：旧引擎（v4.17 landmarks）的掩膜要是过不了这张表，才用新引擎替换
# ★ 标定（2026-10-15，读数来自 _mat_t/probe_feats.py；改过这里就重跑）
#   UPC cand_s4192.png（2324x1268）老引擎全过 -> 10/10 不回归：
#     N1 a%6.489 aspect1.11 elong1.21 sol0.93 / N2 a%7.535 aspect1.15 sol0.91 /
#     A1 a%2.827 elong27.73 sol1.50 / G1 a%1.524 细 / V1 见上 / P1 a%2.779 sol0.53
#   jet_q_final_2x.png（3328x1818）四项不过 -> 换新引擎：
#     N1 elong9.78（细长碎片）/ N2 a%0.009（太小）/ G1 a%8.451 thickrel0.14（吞掉整个场景）/
#     B1 arrow sol0.49 elong7.17
HARD_GATE = {
    "cluster": lambda f: (1.0e-4 <= f["area_frac"] <= 0.10 and f["aspect"] <= 2.6
                          and f["elong"] <= 3.2 and f["sol"] >= 0.55),
    "blob":    lambda f: (2.0e-3 <= f["area_frac"] <= 0.35 and f["aspect"] <= 2.6
                          and f["sol"] >= 0.55),
    "arrow":   lambda f: (5.0e-5 <= f["area_frac"] <= 0.12 and f["elong"] >= 1.5
                          and f["sol"] >= 0.50),
    "stroke":  lambda f: (1.0e-5 <= f["area_frac"] <= 0.05 and f["thickrel"] <= 0.12),
    # ★ glow 的判据（实测 2026-10-15 标定，两个方向都踩过坑）：
    #   ① 不能用【绝对亮度】：UPC 的顶点画在浅灰板上（老掩膜 L=0.801 反而低于板面
    #      L≈0.85），「L>=0.88」会把对的判失败，换成 159 px 的亮核碎块。
    #   ② 不能用【实心度 sol】：jet 的硬散射顶点是「星芒」（短射线放射），
    #      sol=0.23 天生低，「sol>=0.35」会把 5796 px 的正确候选判失败（实测回归）。
    #   发光点 = 「小面积 + 细长比低」+「要么饱和热点、要么白热核」：
    #     UPC V1  a%0.296 aspect1.41 elong1.10 chroma19.07 L0.801  -> 过
    #     jet V1  a%0.096 aspect1.11 elong1.07 chroma14.97 L0.950  -> 过
    "glow":    lambda f: (f["area_frac"] <= 0.01 and f["aspect"] <= 3.0
                          and f["elong"] <= 3.0
                          and (f["chroma"] >= 12.0 or f["L"] >= 0.88)),
    "arc":     lambda f: (3.0e-5 <= f["area_frac"] <= 0.15 and f["elong"] >= 1.3),
}


def _lab1(rgb):
    return to_lab(np.array([[list(rgb)]], np.float32))[0, 0]


def _seg_d(P, a, b):
    """点集 P(n,3) 到线段 ab 的距离"""
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-9:
        return np.linalg.norm(P - a, axis=1)
    t = np.clip(((P - a) @ ab) / L2, 0, 1)[:, None]
    return np.linalg.norm(P - (a + t * ab), axis=1)


def color_model(elem):
    """IR 的 material -> (锚点, 梯度线段)。★ 只有「A → B」形式（中间夹箭头）才连线段：
    否则「红 #d94b3a / 蓝 #3a5fd9」这种并列色会被连成一条穿过灰区的假线段。"""
    txt = elem.get("material") or ""
    hs = [(m.start(), tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)))
          for m in HEX.finditer(txt)]
    pts = [_lab1(c) for _, c in hs]
    segs = []
    for (p0, c0), (p1, c1) in zip(hs, hs[1:]):
        if any(ch in txt[p0:p1] for ch in ("→", "->", "–", "—", "~")):
            segs.append((_lab1(c0), _lab1(c1)))
    if not pts:
        for w, rgb in COLOR_WORDS:
            if w in txt or w in (elem.get("name") or ""):
                pts.append(_lab1(rgb))
    return pts, segs


def figure_palette(S, k=32):
    """全图 Lab 调色板（k-means）。用来把「颜色区域」变成可数的连通域。"""
    import cv2
    Lab = S["lab"]
    h, w, _ = Lab.shape
    sub = Lab[::3, ::3].reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.4)
    _, _, centers = cv2.kmeans(sub, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    lab = np.zeros(h * w, np.int16)
    best = np.full(h * w, 1e18, np.float32)
    f = Lab.reshape(-1, 3).astype(np.float32)
    for c in range(k):
        d = ((f - centers[c]) ** 2).sum(1)
        hit = d < best
        best[hit] = d[hit]
        lab[hit] = c
    return centers.astype(np.float64), lab.reshape(h, w)


def background_anchors(S, k=4):
    """背景色锚点（近白像素的 k-means 中心）。★ 必须有这个：material 里的
    「白 #ffffff」「近白 #fffbe8」与纯白背景在 Lab 里几乎重合，不设背景竞争者，
    近白元素会把整张背景吃掉（实测 W1 拿到 58.9% 画布）。"""
    import cv2
    m = (S["L"] > 0.965) & (S["sat"] < 0.030)
    if m.sum() < 1000:
        return np.zeros((0, 3))
    P = S["lab"][m].astype(np.float32)
    if len(P) > 60000:
        P = P[::max(1, len(P) // 60000)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.4)
    _, _, c = cv2.kmeans(P, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    return c.astype(np.float64)


def feats_crop(mask, S, bp, res):
    """在 bbox 内算形状特征（整幅 6M 像素上直接 hull/EDT 会慢 10 倍）"""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    h, w = mask.shape
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    sub = mask[y0:y1, x0:x1]
    px = int(sub.sum())
    bw, bh = x1 - x0, y1 - y0
    d = ndi.distance_transform_edt(sub)
    hull = _hull_mask(sub)
    sl = (slice(y0, y1), slice(x0, x1))
    labm = S["lab"][sl][sub].mean(0)
    rgbm = np.stack([S["r"][sl], S["g"][sl], S["b"][sl]], -1)[sub].mean(0)
    return dict(px=px, area_frac=float(px) / float(h * w), bbox=[x0, y0, x1, y1],
                w=bw, h=bh, fill=float(px) / max(1, bw * bh), maxthick=float(d.max()),
                thickrel=float(d.max()) / max(1, max(bw, bh)), elong=moment_ratio(sub),
                sol=float(px) / max(1.0, float(hull.sum())),
                tex=float(bp[sl][sub].mean()), fres=float(res[sl][sub].mean()),
                cxy=[float((x0 + x1 - 1) / 2.0), float((y0 + y1 - 1) / 2.0)],
                aspect=float(max(bw, bh)) / max(1.0, float(min(bw, bh))),
                mean=[float(v) for v in rgbm], L=float(S["L"][sl][sub].mean()),
                chroma=float(np.linalg.norm(labm[1:])), labm=labm)


def prune_spurs(m, rel=0.06):
    """剪掉“贴在主体上的细尖刺”。

    ★ 为什么需要（实测 2026-10-15，喷注图左核）：新引擎的球团池会把
    “板边细线 + 束流箭头尖”跟核子连成一个连通块，于是可见轮廓上多了一条
    斜细尾（核子本身最厚 242 px，那条尾只 2–3 px）。

    不能用 opening-by-reconstruction（尾跟主体连着，重建会原样长回来），
    也不能直接输出 opening（会把身体边缘磨掉一圈）。用“开运算定主体 →
    只保留主体周围 rel×等效半径 内的原像素”：主体完整保留，只剪掉“离任何
    厚部分都超过 rel×R ”的特征。

    只对 IR 里声明为「团块 / 包络近似球形」的 cluster 用（箭头、细线、
    轮廓本来就是细的，不能剪）。
    """
    area = int(m.sum())
    if area <= 0:
        return m
    r = max(3, int(round(rel * np.sqrt(area / np.pi))))
    core = ndi.binary_opening(m, iterations=r)
    if not core.any():
        return m
    return m & ndi.binary_dilation(core, iterations=r)


def _ramp(x, lo, hi):
    if hi <= lo:
        return 1.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def shape_score(fam, f):
    """族专属的形状似然 0..1（0 = 这个族不可能是这个形状）"""
    a = f["area_frac"]
    if fam == "cluster":
        if a < 1.0e-4 or a > 0.10 or f["aspect"] > 2.6:
            return 0.0
        return (_ramp(f["sol"], 0.40, 0.68) * (1.0 - _ramp(f["elong"], 2.8, 6.0))
                * (0.55 + 0.45 * _ramp(f["tex"], 0.006, 0.020))
                * (0.60 + 0.40 * _ramp(a, 3e-4, 0.015)))
    if fam == "blob":
        if a < 2e-3 or a > 0.35 or f["aspect"] > 2.6:
            return 0.0
        return (_ramp(f["sol"], 0.40, 0.72) * (1.0 - _ramp(f["elong"], 2.2, 4.5))
                * (0.30 + 0.70 * _ramp(f["chroma"], 8.0, 30.0)))
    if fam == "arrow":
        if a < 5e-5 or a > 0.12 or f["elong"] < 1.5:
            return 0.0
        return _ramp(f["elong"], 1.5, 2.6) * _ramp(f["sol"], 0.35, 0.65)
    if fam == "stroke":
        return (1.0 - _ramp(f["thickrel"], 0.05, 0.15)) * _ramp(f["elong"], 1.5, 3.5)
    if fam == "glow":
        return (_ramp(f["L"], 0.84, 0.95) * (1.0 - _ramp(f["elong"], 2.0, 4.0))
                * (1.0 - _ramp(a, 0.002, 0.012)))
    if fam == "arc":
        if a < 3e-5 or a > 0.15:
            return 0.0
        return (_ramp(f["elong"], 1.1, 2.4) * (1.0 - _ramp(f["thickrel"], 0.12, 0.35))
                * _ramp(f["fres"], 0.003, 0.025))
    return 0.0


def axis_frame(comp):
    """IR 的 composition.projection.轴方向_deg -> 屏幕上该轴单位方向。
    约定（与 IR 文字一致）：0° = 屏幕右、正角向下；y=-90° 即竖直向上。"""
    ang = ((comp.get("projection") or {}).get("轴方向_deg") or {})
    fr = {}
    for k, deg in ang.items():
        if isinstance(deg, (int, float)):
            t = np.deg2rad(float(deg))
            fr[str(k)] = np.array([np.cos(t), np.sin(t)], float)
    return fr


def pos_hints(elem, ir):
    """位置词 -> [("axis", 轴名, ±1) | ("rel", 别的元素 id, 屏幕方向)]。
    实测这是消歧的关键：喷注图两个 Pb 的 material 一字不差，只有位置词能分开
    （N1「沿束流轴 z 的负侧一端」「画面上在火球的左下」/ N2 对应正侧、右上）。"""
    txt = " ".join([elem.get("name") or "",
                    json.dumps(elem.get("params") or {}, ensure_ascii=False),
                    elem.get("role") or ""])
    flat = txt.replace(" ", "").replace("的", "")
    out = []
    for ax in ("x", "y", "z"):
        if (ax + "正侧") in flat:
            out.append(("axis", ax, 1))
        elif (ax + "负侧") in flat:
            out.append(("axis", ax, -1))
    if "上核" in txt:
        out.append(("axis", "y", 1))
    if "下核" in txt:
        out.append(("axis", "y", -1))
    for o in ir:
        if o["id"] == elem["id"]:
            continue
        keys = set(re.findall(r"[\u4e00-\u9fa5]{2,}", o["name"] or ""))
        if o["name"]:
            keys.add(o["name"])
        for k in keys:
            p = txt.find(k)
            if p < 0:
                continue
            tail = txt[p + len(k): p + len(k) + 14]
            for w2, d in SCREEN_DIR:
                if w2 in tail:
                    out.append(("rel", o["id"], d))
                    break
    return out


def discover_ir(ir, comp, S, skip=()):
    """IR 驱动发现：返回 (got, notes)。skip = 已经认好、不必重做的元素 id。"""
    import cv2
    H, W = S["L"].shape
    notes = []
    got = {}
    bp = np.abs(S["L"] - ndi.gaussian_filter(S["L"], 8.0))
    b30 = np.abs(S["L"] - ndi.gaussian_filter(S["L"], 30.0))
    med = ndi.median_filter(S["L"], 61)
    res = S["L"] - med
    centers, plab = figure_palette(S, 32)
    bga = background_anchors(S)
    Dbg = np.full(len(centers), 1e9)
    for b in bga:
        Dbg = np.minimum(Dbg, np.linalg.norm(centers - b, axis=1))
    CM, De, dmin = {}, {}, {}
    for e in ir:
        pts, segs = color_model(e)
        CM[e["id"]] = (pts, segs)
        dd = np.full(len(centers), 1e9)
        for p in pts:
            dd = np.minimum(dd, np.linalg.norm(centers - p, axis=1))
        for s0, s1 in segs:
            dd = np.minimum(dd, _seg_d(centers, s0, s1))
        De[e["id"]] = dd
        dmin[e["id"]] = float(dd.min())
    pool = {}
    for e in ir:
        if not (CM[e["id"]][0] or CM[e["id"]][1]):
            pool[e["id"]] = np.zeros((H, W), bool)
            dmin[e["id"]] = float("inf")
            continue
        tau = dmin[e["id"]] + TAU_BY_FAMILY.get(e["family"], 14.0)
        sel = (De[e["id"]] <= tau) & (De[e["id"]] < Dbg - 3.0)
        pool[e["id"]] = np.isin(plab, np.nonzero(sel)[0]) if sel.any() else np.zeros((H, W), bool)
    gb = (S["sat"] < CLU_SAT) & (S["L"] > CLU_L_LO) & (S["L"] < CLU_L_HI)
    cthr = max(0.015, float(np.percentile(b30[gb], 70.0))) if gb.any() else 1.0
    cluM = (gb & (b30 > cthr)) if gb.any() else np.zeros((H, W), bool)
    cluM = ndi.binary_opening(ndi.binary_closing(cluM, np.ones((21, 21))), np.ones((9, 9)))
    rt = float(max(0.006, np.percentile(res, 99.0)))
    arcM = (res > rt) & (S["sat"] < 0.25) & (S["L"] < 0.997)
    # ★ hotM 必须排掉纯白背景再取分位（实测）：jet 图背景有 >0.3% 的纯白像素，
    #   导致 p99.7 == 1.0，旧写法 L > p99.7 恒为空 -> 亮核源是死代码。
    nb = S["L"] < 0.999
    hotq = float(np.percentile(S["L"][nb], 99.5)) if nb.any() else 1.0
    hotM = nb & (S["L"] >= hotq) & (S["sat"] < 0.40)
    notes.append(("__cfg__", "v4.18 IR 驱动：调色板 k=32 / 背景锚点 %d 个 / "
                  "球团纹理阈 %.4f（%.2f%%）/ 残差阈 %.4f（%.2f%%）/ 高亮阈 %.2f%%"
                  % (len(bga), cthr, 100 * cluM.mean(), rt, 100 * arcM.mean(), 100 * hotM.mean())))
    ctr = np.array([W / 2.0, H / 2.0])
    diag = float(np.hypot(W, H))
    Fr = axis_frame(comp)
    taken = np.zeros((H, W), bool)
    cyc = {}
    for e in sorted(ir, key=lambda x: -x["z"]):
        eid, fam = e["id"], e["family"]
        if eid in skip or fam in ("plane", "dim", "axes", "text"):
            continue
        if fam == "cluster":
            srcs = [pool[eid], cluM]
        elif fam == "stroke":
            P = pool[eid]
            srcs = [P & ~ndi.binary_erosion(P, np.ones((13, 13)))]
        elif fam == "arc":
            srcs = [arcM]
        elif fam == "glow":
            P = pool[eid]
            srcs = [(P & (S["L"] >= float(np.percentile(S["L"][P], 88)))) if P.any() else P, hotM]
        else:
            srcs = [pool[eid]]
        minpx = 60 if fam == "arc" else max(120, int(2e-6 * W * H))
        hints = pos_hints(e, ir)
        cands = []
        for src in srcs:
            src = src & (S["L"] < 0.985) & ~taken
            if fam in ("cluster", "blob", "arrow"):
                src = ndi.binary_fill_holes(ndi.binary_closing(src, np.ones((7, 7))))
            if fam == "arc":
                src = ndi.binary_closing(src, np.ones((5, 5)))
            for mm, px in _pieces(src, minpx):
                f = feats_crop(mm, S, bp, res)
                if f is None:
                    continue
                ss = shape_score(fam, f)
                if ss <= 0:
                    continue
                pts, segs = CM[eid]
                if not pts and not segs:
                    cs = 0.60
                else:
                    dl = [float(np.linalg.norm(f["labm"] - p)) for p in pts]
                    for s0, s1 in segs:
                        dl.append(float(_seg_d(f["labm"][None, :], s0, s1)[0]))
                    cs = float(np.exp(-max(0.0, min(dl) - 12.0) / 22.0))
                vals = []
                v = np.array(f["cxy"]) - ctr
                for h_ in hints:
                    if h_[0] == "axis":
                        d0 = Fr.get(h_[1])
                        if d0 is None:
                            continue
                        vals.append(np.tanh(float(v @ d0) * h_[2] / (0.20 * diag)) * 0.5 + 0.5)
                    elif h_[0] == "rel":
                        base = cyc.get(h_[1], ctr)
                        vv = np.array(f["cxy"]) - base
                        vals.append(np.tanh(float(vv @ np.array(h_[2], float))
                                            / (0.16 * diag)) * 0.5 + 0.5)
                ps = float(np.mean(vals)) if vals else 0.5
                cands.append((cs * ss * (0.30 + 0.70 * ps), cs, ss, ps, f, mm))
        cands.sort(key=lambda x: -x[0])
        n = max(1, e["n"])
        if not cands or cands[0][0] <= 0.05:
            notes.append((eid, "★ 新引擎没找到合格候选（形状族 %s；池 %.2f%%）"
                          % (fam, 100.0 * pool[eid].mean())))
            continue
        m = np.zeros((H, W), bool)
        ntake = 0
        parts = []
        for k in range(n):
            if k < len(cands) and cands[k][0] > 0.05:
                m |= cands[k][5]
                taken |= cands[k][5]
                ntake += 1
                parts.append("col=%.2f shp=%.2f pos=%.2f a%%=%.3f" % (
                    cands[k][1], cands[k][2], cands[k][3], 100 * cands[k][4]["area_frac"]))
        if not m.any():
            continue
        pruned = 0
        if fam == "cluster":
            m2 = prune_spurs(m)
            pruned = int(m.sum() - m2.sum())
            m = m2
        got[eid] = _wrap(fam, m, S)
        ys2, xs2 = np.nonzero(m)
        cyc[eid] = np.array([float(xs2.mean()), float(ys2.mean())])
        notes.append((eid, "v4.18 IR 驱动：取 %d/%d 支（%s）｜池 %.2f%%｜位置词 %s"
                      % (ntake, n, "；".join(parts), 100.0 * pool[eid].mean(),
                         ",".join("%s%s" % (h_[1] if h_[0] == "axis" else h_[1], h_[2] if h_[0] == "rel"
                                            else ("+" if h_[2] > 0 else "-")) for h_ in hints) or "无")
                      + ("；另剪掉 %d px 细尖刺" % pruned if pruned else "")))
    return got, notes


# ── SAM 边界细化（MobileSAM 点提示；只做「有界并集」，不换语义） ───────────────
def _spread_points(mask, k, dmin):
    d = ndi.distance_transform_edt(mask)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((0, 2))
    order = np.argsort(-d[ys, xs])
    cand = np.stack([xs[order], ys[order]], 1)
    pts = []
    for p in cand:
        if all(((p - q) ** 2).sum() > dmin * dmin for q in pts):
            pts.append(p)
        if len(pts) >= k:
            break
    return np.array(pts, np.float64) if pts else cand[:1].astype(np.float64)


def sam_refine(got, S, A, repo, ckpt, notes, grow=0.02, min_iou=0.25, max_ratio=3.0,
               min_thick_rel=0.10):
    """对每个已认领的掩膜做一次 SAM 点提示，把边界**吸附**到 SAM 给的那条边界上。
    规则（保守，可审计）：
      · 正点 = 掩膜内最远点采样的 5 个点；负点 = 掩膜外 20~90 px 环带里采 3 个点；
      · 只在 3 个候选里取「与现掩膜 IoU 最大、且面积在 [0.5, 3.0] 倍内」的那一个；
      · 只有 IoU >= min_iou 才接受（否则报读数并跳过 —— 例如板面这种 SAM 只会切出
        子区域的物体，实测 IoU 0.5 上下，直接跳过更安全）；
      · 结果为**有界并集**：new = m | (sam & dilate(m, grow*短边))，绝不整块替换、
        绝不删除已认领的像素（删除属于 z 序仲裁的事，不在这里做）；
      · **细尖刺拦截**：新增的每个连通块，厚度必须 >= min_thick_rel × 本物体最厚处
        （EDT 最大值，下限 2 px）。★ 实测（2026-10-15，喷注图左核）：SAM 会把
        「束流箭头尖 + 板边细线」并进核子，并占在可见轮廓上（核子最厚 240 px，
        细线只有 2–3 px）——这条把它截掉。
    """
    try:
        import torch
    except Exception as ek:
        notes.append(("__sam__", "★ 没装 torch，跳过 SAM 细化：%s" % ek))
        return got, None
    try:
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from mobile_sam import sam_model_registry, SamPredictor
    except Exception as ek:
        notes.append(("__sam__",
                      "★ 装不上 MobileSAM，跳过：%s"
                      "（默认会去 %s 找仓库、%s 找权重；"
                      "装法见 scripts/sam_probe.py 文件头 —— 本机 pip 的 TLS 是坏的，"
                      "必须 urllib 下 wheel 再 pip install --no-index）"
                      % (ek, repo, ckpt)))
        return got, None
    torch.set_num_threads(max(1, (os.cpu_count() or 4)))
    sam = sam_model_registry["vit_t"](checkpoint=ckpt)
    sam.eval()
    pred = SamPredictor(sam)
    H, W = S["L"].shape
    short = float(min(H, W))
    rows = []
    for eid, d in got.items():
        m = d["mask"]
        if m.sum() < 30:
            continue
        b = d["bbox"]
        pad = int(0.06 * max(b[2] - b[0], b[3] - b[1])) + 24
        x0, y0 = max(0, b[0] - pad), max(0, b[1] - pad)
        x1, y1 = min(W, b[2] + pad), min(H, b[3] + pad)
        crop = A[y0:y1, x0:x1]
        if crop.dtype != np.uint8:
            crop = np.clip(crop, 0, 255).astype(np.uint8)
        if min(crop.shape[:2]) < 24:
            continue
        mc = m[y0:y1, x0:x1]
        Am = int(mc.sum())
        pred.set_image(crop)
        pos = _spread_points(mc, 5, 0.22 * np.sqrt(Am / np.pi))
        ring = (ndi.binary_dilation(mc, iterations=int(0.06 * short))
                & ~ndi.binary_dilation(mc, iterations=20))
        neg = _spread_points(ring, 3, 0.20 * np.sqrt(Am / np.pi))
        pts = np.concatenate([pos, neg], 0) if len(neg) else pos
        labs = np.array([1] * len(pos) + [0] * len(neg))
        try:
            ms, sc, _ = pred.predict(point_coords=pts, point_labels=labs,
                                     multimask_output=True)
        except Exception as ek:
            rows.append(dict(id=eid, family=d.get("family"), iou=None, add_px=0,
                             verdict="★ SAM 报错 %s" % ek))
            continue
        bi, bv = -1, -1.0
        for j, mm in enumerate(ms):
            v = float((mm & mc).sum()) / max(1.0, float((mm | mc).sum()))
            ratio = float(mm.sum()) / max(1.0, float(Am))
            if 0.5 <= ratio <= max_ratio and v > bv:
                bi, bv = j, v
        if bi < 0:
            rows.append(dict(id=eid, family=d.get("family"), iou=None, add_px=0,
                             verdict="★ SAM 三个候选面积都不在 [0.5,3] 倍内（现掩膜 %d px），跳过" % Am))
            continue
        if bv < min_iou:
            rows.append(dict(id=eid, family=d.get("family"), iou=round(bv, 3), add_px=0,
                             verdict="SAM 与现掩膜 IoU %.3f < %.2f：SAM 只切到子区域，跳过（读数）"
                             % (bv, min_iou)))
            continue
        rad = max(8, int(grow * short))
        add = ms[bi] & ndi.binary_dilation(mc, iterations=rad)
        add &= ~mc
        thin = 0
        if add.any():
            thr = max(2.0, min_thick_rel * float(ndi.distance_transform_edt(mc).max()))
            lab_a, na = ndi.label(add)
            keep = np.zeros_like(add)
            for k in range(1, na + 1):
                c = lab_a == k
                if float(ndi.distance_transform_edt(c).max()) >= thr:
                    keep |= c
            thin = int(add.sum() - keep.sum())
            add = keep
        if add.sum() == 0:
            rows.append(dict(id=eid, family=d.get("family"), iou=round(bv, 3), add_px=0,
                             verdict="SAM 边界与现掩膜一致，无新增"))
            continue
        newc = mc | add
        full = np.zeros((H, W), bool)
        full[y0:y1, x0:x1] = newc
        d["mask"] = full
        d["px"] = int(full.sum())
        d["bbox"] = _bbox(full)
        d["sam_iou"] = round(bv, 3)
        rows.append(dict(id=eid, family=d.get("family"), iou=round(bv, 3), add_px=int(add.sum()),
                         add_frac=round(100.0 * add.sum() / (H * W), 4), thin_dropped=thin,
                         verdict="接受：+%d px（%.2f%% 画布），边界吸附到 SAM%s"
                                 % (int(add.sum()), 100.0 * add.sum() / (H * W),
                                    "；另截掉 %d px 细尖刺（厚度 < %.0f%% 本体最厚处）"
                                    % (thin, 100 * min_thick_rel) if thin else "")))
    add_tot = sum(r["add_px"] for r in rows)
    notes.append(("__sam__", "SAM 边界细化：尝试 %d 个元素，接受 %d 个（合计 +%d px）、跳过 %d 个（详见 ⑨）"
                  % (len(rows), sum(1 for r in rows if r["add_px"] > 0), add_tot,
                     sum(1 for r in rows if r["add_px"] == 0))))
    return got, rows


# ── 双引擎仲裁 ────────────────────────────────────────────────────────────
def arbitrate(legacy_got, new_got, ir, S, bp, res):
    """逐元素：老引擎（v4.17 landmarks）的掩膜过不了 HARD_GATE 才换成新引擎的。

    ★ 为什么不一刀切新引擎：实测 UPC 位图与 IR 偏差极大（N1 LabDelta 57.1），
    新引擎（IR 颜色模型驱动）反而更差（N1 40248 px / IoU 0.002），老引擎是 10/10；
    而喷注淬火图反过来 —— 老引擎 N1/N2/B1/G1 不过闸门，新引擎 8/9 认对。
    所以规则的形状必须是「旧的不合格才换」，而不是「新的更好就换」。

    返回 rows = 逐元素结构化记录（写进 report.json，矢量重建那一步要按它判依据）。
    """
    rows = []
    out = dict(legacy_got)
    for e in ir:
        eid, fam = e["id"], e["family"]
        gate = HARD_GATE.get(fam)
        if gate is None:
            continue
        lm = legacy_got.get(eid, {}).get("mask")
        lf = feats_crop(lm, S, bp, res) if lm is not None and lm.any() else None
        nf = new_got.get(eid, {}).get("mask")
        nfe = feats_crop(nf, S, bp, res) if nf is not None and nf.any() else None
        l_ok = bool(lf is not None and gate(lf))
        n_ok = bool(nfe is not None and gate(nfe))
        r = dict(id=eid, family=fam, keep="legacy",
                 legacy_px=int(lm.sum()) if lm is not None else None,
                 new_px=int(nf.sum()) if nf is not None else None,
                 legacy_ok=l_ok, new_ok=n_ok, why="")
        if lm is None:
            if n_ok:
                out[eid] = new_got[eid]
                r["keep"] = "new"
                r["why"] = "老引擎没认出来 -> 用新引擎"
            else:
                r["keep"] = "none"
                r["why"] = ("* 两个引擎都没认出来（新引擎有候选 %s px 但不过闸门）"
                            % (r["new_px"] if nfe is not None else "无"))
            rows.append(r)
            continue
        if l_ok:
            if n_ok:
                cl = _col_fit(lf, ir, eid, S)
                cn = _col_fit(nfe, ir, eid, S)
                r["legacy_col"], r["new_col"] = round(cl, 3), round(cn, 3)
                r["why"] = ("老引擎掩膜过闸门 -> 保留（新引擎 col=%.2f vs 老 col=%.2f，"
                            "形状老的好）" % (cn, cl))
            else:
                r["why"] = "老引擎掩膜过闸门 -> 保留（新引擎候不过闸门）"
            rows.append(r)
            continue
        if n_ok:
            out[eid] = new_got[eid]
            r["keep"] = "new"
            r["why"] = "老引擎掩膜不过闸门（%s）-> 换成新引擎" % _why(fam, lf)
        else:
            r["keep"] = "legacy-fail"
            r["why"] = ("* 老引擎不过闸门（%s）且新引擎也没合格候选 -> 保留老结果并报错"
                        % _why(fam, lf))
        rows.append(r)
    return out, rows



def _col_fit(f, ir, eid, S):
    e = [x for x in ir if x["id"] == eid][0]
    pts, segs = color_model(e)
    if not pts and not segs:
        return float("nan")
    dl = [float(np.linalg.norm(f["labm"] - p)) for p in pts]
    for s0, s1 in segs:
        dl.append(float(_seg_d(f["labm"][None, :], s0, s1)[0]))
    return float(np.exp(-max(0.0, min(dl) - 12.0) / 22.0))


def _why(fam, f):
    if f is None:
        return "没掩膜"
    bits = []
    if fam == "cluster":
        if not (1.0e-4 <= f["area_frac"] <= 0.10):
            bits.append("面积 %.3f%% 出界" % (100 * f["area_frac"]))
        if f["aspect"] > 2.6:
            bits.append("高宽比 %.2f > 2.6" % f["aspect"])
        if f["elong"] > 3.2:
            bits.append("主轴比 %.2f > 3.2（细长，不是团块）" % f["elong"])
        if f["sol"] < 0.55:
            bits.append("凸性 %.2f < 0.55" % f["sol"])
    elif fam == "arrow":
        if f["elong"] < 1.5:
            bits.append("主轴比 %.2f < 1.5（不够细长，不像箭头）" % f["elong"])
        if not (5e-5 <= f["area_frac"] <= 0.12):
            bits.append("面积 %.3f%% 出界" % (100 * f["area_frac"]))
    elif fam == "stroke":
        if f["thickrel"] > 0.12:
            bits.append("粗细比 %.2f > 0.12（不是细线）" % f["thickrel"])
        if not (1e-5 <= f["area_frac"] <= 0.05):
            bits.append("面积 %.3f%% 出界" % (100 * f["area_frac"]))
    elif fam == "glow":
        if f["L"] < 0.88:
            bits.append("亮度 %.2f < 0.88" % f["L"])
        if f["area_frac"] > 0.01:
            bits.append("面积 %.3f%% 过大" % (100 * f["area_frac"]))
    elif fam == "blob":
        if not (2e-3 <= f["area_frac"] <= 0.35):
            bits.append("面积 %.3f%% 出界" % (100 * f["area_frac"]))
        if f["sol"] < 0.55:
            bits.append("凸性 %.2f < 0.55" % f["sol"])
    elif fam == "arc":
        if f["elong"] < 1.3:
            bits.append("主轴比 %.2f < 1.3" % f["elong"])
    return "；".join(bits) or "形状不合格"


# ── 认领：IR 声明 -> 可见像素轮廓 ──────────────────────────────────────────
def _plane_ok(d, S):
    """板面候选的合理性检查。★ 不能「谁大选谁」：喷注淬火图的宽候选把 QGP 并进板里，
    bbox 1361x809（87% 画布高、85% 宽）、中位饱和 0.192 —— 一条都能否掉它。"""
    H, W = S["L"].shape
    x0, y0, x1, y1 = d["bbox"]
    area = float(d["mask"].sum())
    if area < 0.005 * H * W or area > 0.55 * H * W:
        return False
    if (y1 - y0) > 0.80 * H and (x1 - x0) > 0.75 * W:   # 框住整张画布 = 吞了别的东西
        return False
    if d.get("medsat", 1.0) > 0.16:                     # 板必须是灰的
        return False
    if d.get("medL", 0.0) < 0.55:                       # 板必须是亮的
        return False
    return True


def assign(ir, lms, S):
    got, notes, used = {}, [], {}
    byid = {e["id"]: e for e in ir}

    # ① 板面：候选必须过「几何 + 颜色纯度」检查（谁大选谁是错的 —— 喷注淬火图的
    #    宽候选把 QGP 整块并进板里，bbox 覆盖 87% 画布高、中位饱和 0.192）。
    if lms["plane"]:
        okp = [d for d in lms["plane"] if _plane_ok(d, S)]
        if okp:
            d = max(okp, key=lambda x: x["px"])
            used[id(d)] = True
            for e in ir:
                if e["family"] == "plane":
                    got[e["id"]] = _wrap("plane", d["mask"], S)
                    notes.append((e["id"], "低饱和灰板面（%s 候选，中位饱和 %.2f / 亮度 %.2f）"
                                           "-> 凸包补亮角 + 4 角平行四边形"
                                  % (d.get("src", "?"), d.get("medsat", -1), d.get("medL", -1))))
        else:
            notes.append(("plane", "★ %d 个板面候选全部被合理性判据否掉（框住画布 / 中位饱和过高）"
                          % len(lms["plane"])))

    # ② 核球团：按 IR 名里的「上核 / 下核」对上 y 中心
    cl = sorted([d for d in lms["cluster"] if not used.get(id(d))],
                key=lambda d: (d["bbox"][1] + d["bbox"][3]) / 2.0)
    ren = sorted([e for e in ir if e["family"] == "cluster"],
                 key=lambda e: 0 if "上核" in e["name"] else 1)
    for e, d in zip(ren, cl):
        used[id(d)] = True
        got[e["id"]] = _wrap("cluster", d["mask"], S, seed_px=d.get("seed_px"),
                             seed_bbox=d.get("seed_bbox"))
        how = ("单色椭球核：整块拟合椭圆 / 长宽比 1.5–3.6 / 填充率 >=0.80 / 凸性 >=0.85"
               if d.get("src") == "ellipse" else
               "红蓝核子球团（同半径内两色共现）")
        notes.append((e["id"], "%s，按「上/下核」对 y 中心认领（与色相无关，不吃 IR 配色）" % how))

    # ③ 实心实体箭头（×N）
    sol = sorted([d for d in lms["solid"] if not used.get(id(d))], key=lambda d: -d["px"])
    for e in sorted([x for x in ir if x["family"] == "arrow" and x["n"] >= 2], key=lambda x: -x["z"]):
        if e["id"] in got or not sol:
            continue
        take = sol[:e["n"]]
        sol = sol[e["n"]:]
        m = np.zeros(S["L"].shape, bool)
        for d in take:
            m |= d["mask"]
            used[id(d)] = True
        got[e["id"]] = _wrap("arrow", m, S)
        notes.append((e["id"], "按 IR 的 ×%d 取到 %d 支纯色实体箭头" % (e["n"], len(take))))

    # ④ 标注（双向细箭头 + 两端虚线）
    for e in sorted([x for x in ir if x["family"] == "dim"], key=lambda x: -x["z"]):
        if e["id"] in got:
            continue
        shaft, dashes = pick_dim(lms["dark"], used)
        if shaft is None:
            notes.append((e["id"], "★ 没找到「竖直双向细箭头」"))
            continue
        m = shaft["mask"].copy()
        used[id(shaft)] = True
        for d in dashes:
            m |= d["mask"]
            used[id(d)] = True
        got[e["id"]] = _wrap("dim", m, S)
        notes.append((e["id"], "竖直双向细箭头(%.0fx%.0f) + 两端 %d 段虚线"
                      % (shaft["w"], shaft["h"], len(dashes))))

    # ⑤ 三轴图标
    rem_dark = [d for d in lms["dark"] if not used.get(id(d)) and not d["in_obj"]]
    for e in sorted([x for x in ir if x["family"] == "axes"], key=lambda x: -x["z"]):
        if e["id"] in got:
            continue
        d = pick_axes(rem_dark)
        if d is None:
            notes.append((e["id"], "★ 没找到「低填充率细三杆」"))
            continue
        used[id(d)] = True
        rem_dark = [x for x in rem_dark if x is not d]
        m = d["mask"].copy()
        extra = 0
        # ★ 有的图画成【三根互不相连的箭头】（喷注淬火：z 在顶上、x/y 在板角）。
        #   pick_axes 只返回一支；把其余「细长 + 有箭头宽度（maxthick>=5）+ 长度 60..420」
        #   的暗笔画并进来。标注引线（maxthick~3.5）与字形（长度<40）不会进来。
        for x in list(rem_dark):
            if x["in_obj"] or x["maxthick"] < 5.0 or x["maxthick"] > 14:
                continue
            if x["fill"] > 0.40 or min(x["w"], x["h"]) > 60:
                continue
            if not (60 <= max(x["w"], x["h"]) <= 420):
                continue
            if (x["mask"] & ndi.binary_dilation(m, iterations=25)).sum() >= 0.30 * x["px"]:
                continue
            m |= x["mask"]
            used[id(x)] = True
            rem_dark[:] = [y for y in rem_dark if y is not x]   # dict 里含 ndarray，list.remove 会 ValueError
            extra += 1
        got[e["id"]] = _wrap("axes", m, S)
        notes.append((e["id"], "细笔画里 fill=%.2f / maxthick=%.1f（三杆交汇的图标）"
                               "%s" % (d["fill"], d["maxthick"],
                                       "；另并入 %d 根独立的细轴杆" % extra if extra else "")))

    # ⑥ 文字：剩下所有深色小块（字形）
    for e in sorted([x for x in ir if x["family"] == "text"], key=lambda x: -x["z"]):
        if e["id"] in got:
            continue
        # ★ 字形必须是【小 + 细】的：旧判据只卡 max(w,h)<=200，介质暗纹（190x135、
        #   6-10k px、厚 20-30 px）被当成字形吞进文字层（实测 L1 里 21k px 是暗纹）。
        glyph = [d for d in rem_dark if not d["in_obj"] and max(d["w"], d["h"]) <= 200
                 and d["px"] <= 2500 and d["maxthick"] <= 14]
        m = np.zeros(S["L"].shape, bool)
        for d in glyph:
            m |= d["mask"]
            used[id(d)] = True
        rem_dark = [d for d in rem_dark if all(d is not g for g in glyph)]
        if m.any():
            got[e["id"]] = _wrap("text", m, S)
            notes.append((e["id"], "其余深色小块（字形）"))

    # ⑦ 介质（blob）+ 喷注（jet）：先用【厚度】把介质大团块与细喷注拆开
    blobs = sorted([x for x in ir if x["family"] == "blob"], key=lambda x: -x["z"])
    jets = sorted([x for x in ir if x["family"] == "jet"], key=lambda x: -x["z"])
    wi = [d for d in lms["warm"] if not used.get(id(d))]
    warm_all = np.zeros(S["L"].shape, bool)
    for d in wi:
        warm_all |= d["mask"]
        used[id(d)] = True
    qmask = np.zeros(S["L"].shape, bool)
    jmask = np.zeros(S["L"].shape, bool)
    vcore = None
    if wi and (blobs or jets):
        q, _, _ = pick_blob(wi, S)
        if q is not None:
            qmask = q
            for e in blobs:
                got[e["id"]] = _wrap("blob", q, S)
                notes.append((e["id"],
                              "暖色总掩膜做半径 %d px 圆盘开运算：只有介质主体容得下这个圆盘，"
                              "细喷注/光丝被剥掉；闭运算+填洞补回表面暗纹；"
                              "凸包内仍是暖橙的碎片并回本体（自己的羽化光晕）"
                              % max(12, int(round(0.030 * min(q.shape))))))
        if jets and q is not None:
            vanc = None
            for e in ir:
                if e["family"] == "glow":
                    vanc = (e.get("params") or {}).get("锚点")
                    break
            jm, jcomps, vcore = pick_jets(warm_all, qmask, None, ir, S, anchor=vanc)
            for e in jets:
                d = jm.get(e["id"])
                if d is not None and d["px"] > 0:
                    got[e["id"]] = d
                    jmask |= d["mask"]
                    notes.append((e["id"], "介质外的暖色块按【左右】分配 + 介质内亮黄段按【顶点】"
                                           "左右分配；邻近 >300 px 碎块并回同侧（%d px）" % d["px"]))
                else:
                    notes.append((e["id"], "★ 没找到这条喷注的可见像素"))
        strokes = [e for e in ir if e["family"] == "stroke" and e["id"] not in got]
        if strokes and qmask.any():
            sm = medium_strokes(qmask, jmask, S)
            if sm.sum() >= 300:
                for e in strokes:
                    got[e["id"]] = _wrap("stroke", sm, S)
                    notes.append((e["id"], "白顶帽（局部亮度 - 大尺度亮度）+ 离介质边界 >20 px "
                                           "+ 笔画厚度 <=5 px：介质表面的细亮线（胶子辐射）"))
                jmask = jmask | sm
            else:
                notes.append((strokes[0]["id"], "★ 介质内没找到足够细亮笔画（%d px）" % sm.sum()))
        if vcore is not None and vcore.any():
            for e in ir:
                if e["family"] == "glow" and e["id"] not in got:
                    Hh = max(8, int(round(0.010 * S["L"].shape[1])))
                    m = vcore | (warm_all & ndi.binary_dilation(vcore, iterations=Hh)
                                 & (S["L"] >= 0.72))
                    got[e["id"]] = _wrap("glow", m, S, core_mask=vcore)
                    notes.append((e["id"], "介质内部【白热核】= 最亮且紧凑的连通域（%d px）+ "
                                           "%d px 亮晕；锚在核上，不会落到喷管上"
                                  % (int(vcore.sum()), Hh)))

    # ⑧ 暖橙剩下的部分：按 IR z 序（前 -> 后）剥离
    vcore_holder = {}
    order = [(e, e["family"]) for e in sorted(
        [x for x in ir if x["family"] in ("arrow", "glow", "stroke") and x["id"] not in got],
        key=lambda x: -x["z"])]
    blob = warm_all & ~qmask & ~jmask
    if (not order) and blob.any() and qmask.any():
        # 没有待剥的暖色元素：剩下的暖色碎片是介质自己的羽化外晕 -> 并回介质
        for e in blobs:
            d = got[e["id"]]
            d["mask"] = d["mask"] | blob
            d["px"] = int(d["mask"].sum())
            d["bbox"] = _bbox(d["mask"])
        blob = np.zeros(S["L"].shape, bool)
    if blob.any() and order:
        parts, rest, vc2 = split_warm(blob, S, order)
        for e, m in parts:
            if e["family"] == "glow":
                vcore_holder["m"] = vc2
            if not m.any():
                notes.append((e["id"], "★ 橙色块里没剥出这一层"))
                continue
            kind = "arrow" if e["family"] == "arrow" else ("glow" if e["family"] == "glow" else "stroke")
            got[e["id"]] = _wrap(kind, m, S)
            why = {"arrow": "橙色块里【厚度】最大的那层（实体箭头，不是细线）",
                   "glow": "橙色块里【亮度】最高的核心 + 光晕（颜色与箭头完全切不开）",
                   "stroke": "橙色块里剩下的【细波浪线】"}[kind]
            notes.append((e["id"], why))
    if vcore_holder.get("m") is not None:
        for e in ir:
            if e["family"] == "glow" and e["id"] in got:
                got[e["id"]]["core_mask"] = vcore_holder["m"]
    return got, notes, [d for d in lms["dark"] if not used.get(id(d))]


# ── 遮挡对账（用 IR 的 composition.穿透 / 遮挡） ──────────────────────────
def occlusion_ledger(ir, got, comp):
    byid = {e["id"]: e for e in ir}
    rows = []
    per = comp.get("穿透") or []
    if isinstance(per, dict):
        per = [per]
    for ent in per:
        if not isinstance(ent, dict):
            continue
        objs = ent.get("物体") or []
        if isinstance(objs, str):
            objs = re.findall(r"[A-Z]\d{1,2}", objs)
        occ = [k for k in EID.findall(str(ent.get("穿什么") or "")) if k in byid]
        exp = str(ent.get("露出") or "")
        for oid in objs:
            if oid not in got:
                continue
            om = got[oid]["mask"]
            hs = _hull_mask(om)
            defc = hs & ~om
            r = dict(obj=oid, thru=occ, ir_says=exp, visible=int(om.sum()),
                     hull=int(hs.sum()), visible_frac=round(float(om.sum()) / max(1, hs.sum()), 3),
                     deficit_px=int(defc.sum()),
                     deficit_frac=round(float(defc.sum()) / max(1, hs.sum()), 4))
            # ★ 不能用「凸包差额」直接当被遮掉的部分：球团的外轮廓是毛边，
            #   凸包差额本身就有一圈（实测两核各 ~22%）。真被板切掉一整块时，
            #   缺口是【一片厚实的帽】，用「缺口的最大内切半径」和物体等效半径比才分得开。
            if defc.sum() > 0:
                r["deficit_maxthick"] = round(float(ndi.distance_transform_edt(defc).max()), 1)
            r["obj_radius"] = round(float(np.sqrt(om.sum() / np.pi)), 1)
            thick = r.get("deficit_maxthick", 0.0)
            if thick > 0.35 * r["obj_radius"]:
                r["verdict"] = "被切掉一整块（缺口厚 %.0f px -> 不可见，交给 inpaint）" % thick
            else:
                r["verdict"] = ("可见剪影完整（凸包差额只有 %.0f px 厚 = 球团毛边，"
                                "不是被遮掉一整块）" % thick)
            rows.append(r)
    return rows


def consistency(ir, got, S, tol=26.0):
    rows = []
    for e in ir:
        if e["id"] not in got:
            rows.append(dict(id=e["id"], verdict="★ 图上没找到"))
            continue
        m = got[e["id"]]["mask"]
        if not e["colors"]:
            rows.append(dict(id=e["id"], verdict="IR 未声明配色 -> 无法核对"))
            continue
        lab = to_lab(np.stack([S["r"], S["g"], S["b"]], -1)[m])
        mins = np.min(np.stack([np.linalg.norm(lab - to_lab(np.array(c, np.float32)), axis=-1)
                                for c in e["colors"]], 0), 0)
        hit = float((mins <= tol).mean())
        rows.append(dict(id=e["id"], hit=round(hit, 3), median=round(float(np.median(mins)), 1),
                         verdict="一致" if hit > 0.5 else "★ 位图色与 IR 声明不符"))
    return rows


def route_compare(ir, got, A, skill, ncol=16):
    """与现有路线对照：它的「元素」= 16 色调色板类。量两件事 ——
       碎片率（一个物理物体被切成几个颜色类）/ 混淆率（一个颜色类里塞了几个物理物体）。"""
    try:
        sys.path.insert(0, os.path.join(skill, "scripts"))
        from raster_vector import segsem as SS
    except Exception as ex:
        return dict(available=False, why=str(ex))
    lab, pal = SS.quantize(A, ncol)
    npal = len(pal)
    frag = []
    for e in ir:
        if e["id"] not in got:
            continue
        m = got[e["id"]]["mask"]
        if m.sum() < 2000:
            continue
        cnt = np.bincount(lab[m].ravel(), minlength=npal).astype(np.float64)
        sh = cnt / cnt.sum()
        big = int((sh >= 0.05).sum())
        k = int(np.argmax(sh))
        frag.append(dict(id=e["id"], fragments=big, top=round(float(sh.max()), 3),
                         top_color="#%02x%02x%02x" % tuple(int(v) for v in pal[k])))
    share = {}
    for k in range(npal):
        ck = lab == k
        if ck.sum() < 0.01 * ck.size:
            continue
        who = []
        for e in ir:
            if e["id"] in got:
                mk = got[e["id"]]["mask"]
                if (mk & ck).sum() >= 0.25 * ck.sum():
                    who.append(e["id"])
        if len(who) >= 2:
            share["#%02x%02x%02x" % tuple(int(v) for v in pal[k])] = who
    return dict(available=True, palette_size=npal, per_element=frag, shared_classes=share)


# ── v4.21：边界吸附（SLIC 超像素 + 有界投票） ────────────────────────────────
#   IR 分割给的是【物理归属】，边界是形态学算出来的 —— 它可能横穿一片平滑的颜色
#   过渡（QGP 边缘的高光、板面的接触阴影）。装配器给每个色块加 0.5 px 同色描边来
#   堵 PDF 接缝，边界一旦不在颜色边上，这 0.5 px 就把邻元素的颜色抹过去：实测
#   喷注淬火图里 M1/S1 的复现误差 70% 集中在元素边界 1.5 px 内。
#   超像素的边界天然贴着图像边，所以把「谁的边界」吸附到超像素边界上：
#     ① 细结构（轴 / 字 / 胶子线 / 顶点）整块冻结 —— 吸附会把 1~2 px 的杆吃掉；
#     ② 只有大块（blob / plane / jet）与背景参与重判；
#     ③ 一个超像素只有在「可动像素的多数派占比 >= min_share」时才整块判给多数派，
#        否决权仍归物理（判据不变，只是把边界挪到图像边上）。
_REFINE_FAM = {"blob", "plane", "jet"}


def refine_edges(lab, owner, S, A, n_segments=2500, compact=12.0,
                 min_share=0.55, allow_bg=True, verbose=True):
    """把元素边界吸附到真实图像边（SLIC 超像素 + 有界投票）。in-place 改 lab。"""
    try:
        from skimage.segmentation import slic
    except Exception as e:                                    # 没装 scikit-image 就原样返回
        if verbose:
            print("   [边界吸附] 跳过：%s" % e)
        return lab, []
    H, W = lab.shape
    n = int(max(600, min(6000, round(n_segments * (H * W) / (1664.0 * 928.0)))))
    seg = slic(A.astype(np.float32) / 255.0, n_segments=n, compactness=compact,
               start_label=0, sigma=1.0, enforce_connectivity=True, channel_axis=-1)
    ns = int(seg.max()) + 1
    K = len(owner) + 1                       # 标签 0 = 背景(-1)，i+1 = owner[i]

    fixed = np.zeros((H, W), bool)
    allowed = np.zeros(K, bool)
    if allow_bg:
        allowed[0] = True
    for i, e in owner.items():
        if e.get("family") in _REFINE_FAM:
            allowed[i + 1] = True
        else:
            fixed |= (lab == i)

    sid = seg.ravel().astype(np.int64)
    lid = (lab.ravel().astype(np.int64) + 1)
    valid = ~fixed.ravel()
    hist = np.bincount(sid[valid] * K + lid[valid], minlength=ns * K).reshape(ns, K)
    hist[:, ~allowed] = 0
    tot = hist.sum(1)
    cnt_l = np.bincount(sid, weights=S["L"].ravel(), minlength=ns)
    cnt_s = np.bincount(sid, weights=S["sat"].ravel(), minlength=ns)
    npx = np.maximum(np.bincount(sid, minlength=ns), 1)
    meanL, meanS = cnt_l / npx, cnt_s / npx
    best = hist.argmax(1)
    share = hist.max(1) / np.maximum(tot, 1)

    ok = (tot > 0) & (share >= min_share)
    # 背景只有当这个超像素本身「又亮又灰」时才有资格赢（否则会把物体边缘啃掉）
    bgwin = best == 0
    ok &= ~(bgwin & ((meanL < 0.90) | (meanS > 0.10)))

    new = lab.ravel().copy()
    want = (best - 1)
    chg = ok[sid] & valid & (new != want[sid])
    new[chg] = want[sid][chg]
    lab = new.reshape(H, W)

    rows = [(e["id"], int((lab == i).sum())) for i, e in owner.items()]
    if verbose:
        print("   [边界吸附] SLIC %d 段 / compact %.1f -> 改动 %d px（冻结 %d px 细结构）"
              % (ns, compact, int(chg.sum()), int(fixed.sum())))
    return lab, rows


def resolve_z(ir, got, S):
    """z 序前向解算：z 大 = 靠前先占。边界因此落在【前面那个物体的轮廓】上。"""
    lab = np.full(S["L"].shape, -1, np.int32)
    owner, idx = {}, 0
    for e in sorted(ir, key=lambda x: -x["z"]):
        if e["id"] not in got:
            continue
        m = got[e["id"]]["mask"] & (lab < 0)
        if m.sum() < 150:
            continue
        lab[m] = idx
        owner[idx] = e
        idx += 1
    return lab, owner


def main():
    ap = argparse.ArgumentParser(description="IR 引导的可见像素物理轮廓分割")
    ap.add_argument("--bitmap", required=True)
    ap.add_argument("--ir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--skill", default=os.path.expanduser("~/.codex/skills/hep-nature-figure"))
    ap.add_argument("--debug-pieces", action="store_true")
    ap.add_argument("--no-arbitrate", action="store_true",
                    help="不跑 v4.18 新引擎（纯 v4.17c 老引擎，用于回归对照）")
    ap.add_argument("--sam", action="store_true", help="接上 MobileSAM 做边界细化（有界并集，只加不删）")
    ap.add_argument("--sam-repo", default=os.path.join("fig_upc_v415", "seg", "_sam", "MobileSAM"))
    ap.add_argument("--sam-ckpt", default=os.path.join("fig_upc_v415", "seg", "_sam", "mobile_sam.pt"))
    ap.add_argument("--refine-edges", action="store_true",
                    help="v4.21 实验项：SLIC 超像素把元素边界吸附到图像边上。默认关 —— "
                         "实测会把边界吸附成 25 px 的块状台阶（喷注淬火 S1 右缘），"
                         "位图回渲染 MAE 也变差，边界吸附要等「边感知」版本再默认开")
    ap.add_argument("--slic-segments", type=int, default=2500, help="边界吸附的超像素数（按 1664x928 标定）")
    ap.add_argument("--slic-compact", type=float, default=12.0, help="SLIC compactness：小=更贴边，大=更规整")
    ap.add_argument("--slic-share", type=float, default=0.55, help="超像素整块改判所需的多数派占比")
    ap.add_argument("--sam-min-iou", type=float, default=0.25)
    ap.add_argument("--sam-grow", type=float, default=0.02,
                    help="有界并集的容许外扩量（×短边）")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    A = np.asarray(Image.open(a.bitmap).convert("RGB")).astype(np.float32)
    ir, comp = parse_ir(a.ir)
    S = stats(A)

    lms = landmarks(S)
    if a.debug_pieces:
        print("--- dark pieces (px>=250) ---")
        for d in lms["dark"]:
            print("   x%d..%d y%d..%d %dx%d fill=%.2f mt=%.1f px=%-7d in_obj=%s"
                  % (d["bbox"][0], d["bbox"][2], d["bbox"][1], d["bbox"][3], d["w"], d["h"],
                     d["fill"], d["maxthick"], d["px"], d["in_obj"]))
        for k in ("solid", "cluster", "warm", "plane"):
            print("--- %s ---" % k)
            for d in lms[k]:
                print("   x%d..%d y%d..%d %dx%d fill=%.2f mt=%.1f px=%d"
                      % (d["bbox"][0], d["bbox"][2], d["bbox"][1], d["bbox"][3], d["w"], d["h"],
                         d["fill"], d["maxthick"], d["px"]))

    got, notes, leftover = assign(ir, lms, S)

    # ── v4.18：新引擎（IR 颜色模型驱动发现）+ 双引擎仲裁 + SAM 边界细化 ──
    arb_rows, new_rows, sam_rows = [], [], None
    if a.no_arbitrate:
        print("   [新引擎已关闭 --no-arbitrate：只跑 v4.17c 老引擎]")
    else:
        bp = np.abs(S["L"] - ndi.gaussian_filter(S["L"], 8.0))
        res = S["L"] - ndi.median_filter(S["L"], 61)
        new_got, new_notes = discover_ir(ir, comp, S)
        new_rows = [dict(id=e["id"], family=e["family"], px=int(new_got[e["id"]]["mask"].sum()))
                    for e in ir if e["id"] in new_got]
        got, arb_rows = arbitrate(got, new_got, ir, S, bp, res)
        notes.append(("__cfg__", new_notes[0][1]) if new_notes else ("__cfg__", ""))
    if a.sam:
        got, sam_rows = sam_refine(got, S, A, a.sam_repo, a.sam_ckpt, notes,
                                   grow=a.sam_grow, min_iou=a.sam_min_iou)
    # ── 全覆盖：非背景像素必须有主 ──────────────────────────────────────────
    #   ★ 装配器（groupvec 的 --elmap-in）遇到 -1 的叶块是 `continue` —— 直接不画。
    #   于是「没人认领」的坐标轴金属杆、喷注末端的强子球、板的暗描边会在 SVG 里整块消失
    #   （实测喷注淬火：轴与强子球全部丢失）。这里按【最近元素】兜底，只补不抢。
    owned = np.zeros(S["L"].shape, bool)
    for d in got.values():
        owned |= d["mask"]
    bgm = (S["L"] > 0.965) & (S["sat"] < 0.05)
    todo = (~owned) & (~bgm)
    cov = int(todo.sum())
    if cov:
        idx = np.full(S["L"].shape, -1, np.int32)
        gl = list(got.values())
        for k, d in enumerate(gl):
            idx[d["mask"]] = k
        _, (iy, ix) = ndi.distance_transform_edt(~owned, return_indices=True)
        src = idx[iy, ix]
        for k, d in enumerate(gl):
            add = todo & (src == k)
            if add.any():
                d["mask"] = d["mask"] | add
                d["px"] = int(d["mask"].sum())
                d["bbox"] = _bbox(d["mask"])
        notes.append(("__cov__", "未归属的非背景像素 %d 个（%.2f%% 画布）按最近元素兜底"
                                 % (cov, 100.0 * cov / (A.shape[0] * A.shape[1]))))
    else:
        notes.append(("__cov__", "全覆盖：没有未归属的非背景像素"))

    # ── v4.21f：同色深灰元素的几何重判（A1 / B1 / P1 / G1 / T1） ────────────
    #   ★ 必须放在全覆盖之后：否则被移走的箭头像素会被「最近元素兜底」又塞回去。
    got, geo_rows = geometry_refine(ir, got, lms, S)
    notes.extend(geo_rows)

    lab, owner = resolve_z(ir, got, S)
    if a.refine_edges:
        lab, _ = refine_edges(lab, owner, S, A, n_segments=a.slic_segments,
                              compact=a.slic_compact, min_share=a.slic_share)
        for i, e in owner.items():
            m = (lab == i)
            if m.sum() >= 150:
                got[e["id"]]["mask"] = m
                got[e["id"]]["px"] = int(m.sum())
                got[e["id"]]["bbox"] = _bbox(m)
    cons = consistency(ir, got, S)
    occ = occlusion_ledger(ir, got, comp)
    cmp_route = route_compare(ir, got, A, a.skill)

    print("=" * 92)
    print("ir_contour_seg v3 —— IR 引导的「可见像素物理轮廓」分割")
    print("  位图 %s  %dx%d      元素 %d 个" % (a.bitmap, A.shape[1], A.shape[0], len(ir)))
    print("=" * 92)
    print("① IR 先验（分割真正用到的：形态族 / 数量 / 位置 / z 序 / 配色）")
    for e in ir:
        print("   z=%-2d %-4s %-20s %-8s ×%-2d %s"
              % (e["z"], e["id"], e["name"][:18], e["family"], e["n"],
                 ",".join("#%02x%02x%02x" % c for c in e["colors"]) or "-"))

    rows = []
    print("\n② 可见物理轮廓（z 序解算后）")
    print("   %-4s %-18s %-8s %9s  %-11s %-5s %s" % ("id", "name", "family", "px", "w × h", "h/w", "均色"))
    for i, e in owner.items():
        m = lab == i
        bb = _bbox(m)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        rows.append(dict(id=e["id"], name=e["name"], family=e["family"], z=e["z"], px=int(m.sum()),
                         bbox=bb, w=w, h=h, hw=round(h / max(w, 1), 3),
                         ax_ratio=round(moment_ratio(m), 3), mean=_mean(S, m)))
    for r in sorted(rows, key=lambda r: -r["px"]):
        print("   %-4s %-18s %-8s %9d  %4dx%-6d %-5.2f #%02x%02x%02x"
              % (r["id"], r["name"][:16], r["family"], r["px"], r["w"], r["h"], r["hw"],
                 int(r["mean"][0]), int(r["mean"][1]), int(r["mean"][2])))
    miss = [e["id"] for e in ir if e["id"] not in got]
    if miss:
        print("   ！IR 声明了、图上没找到：%s" % ", ".join(miss))

    print("\n③ 每个元素是怎么认出来的（IR 声明 -> 图上的形状）")
    for k, v in notes:
        print("   %-4s %s" % (k, v))

    print("\n④ IR 声明 vs 位图实测")
    print("   %-4s %-10s %-10s %s" % ("id", "配色命中", "中位色差", "判定"))
    for c in cons:
        if "hit" in c:
            print("   %-4s %-10.2f %-10.1f %s" % (c["id"], c["hit"], c["median"], c["verdict"]))
        else:
            print("   %-4s %s" % (c["id"], c["verdict"]))
    for r in rows:
        if r["family"] == "cluster":
            e = [x for x in ir if x["id"] == r["id"]][0]
            mm = re.search(r"(\d+(?:\.\d+)?)\s*:\s*1", e["primitive"] or "")
            exp = ("%s:1" % mm.group(1)) if mm else "?"
            print("   %-4s IR 声明高/宽 %-6s 图上实测 bbox %.2f / 主轴比 %.2f  %s"
                  % (r["id"], exp, r["hw"], r["ax_ratio"],
                     "✓" if min(r["hw"], r["ax_ratio"]) > 1.25 else "★ 未达 HP3(>1.25)"))
            sp = got[r["id"]].get("seed_px")
            if sp:
                print("        （形态种子 %d px -> 可见剪影 %d px，补回 %+.1f%%）"
                      % (sp, r["px"], 100.0 * (r["px"] - sp) / sp))

    print("\n⑤ 遮挡对账（IR 的 composition.穿透：谁穿谁、被遮的那半还看不看得见）")
    if not occ:
        print("   （IR 没写 composition.穿透）")
    for r in occ:
        print("   %-4s 穿过 %-8s IR 说「%s」 可见 %.1f%% / 外接凸包  %s"
              % (r["obj"], ",".join(r["thru"]) or "-", r["ir_says"], 100 * r["visible_frac"], r["verdict"]))

    print("\n⑥ 箭头方向物理读数（用分割出来的轮廓量，不用人眼看）")
    dirs = {}
    away_pts = []
    for ee in ir:
        if ee["family"] == "cluster" and ee["id"] in got:
            bb = got[ee["id"]]["bbox"]
            away_pts.append(((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0))
    for e in ir:
        if e["id"] in got and got[e["id"]]["family"] in ("arrow", "dim"):
            vt = None
            if "V1" in got and e["family"] == "arrow":
                # 只有【从顶点发出来】的那层才按方向角切（末态 e⁺e⁻）；
                # 速度箭头在画面另一头，离顶点很远，用方向角切会把它量错。
                vm = got["V1"].get("core_mask")
                vm = got["V1"]["mask"] if vm is None or not vm.any() else vm
                ys2, xs2 = np.nonzero(vm)
                R = float(np.sqrt(got[e["id"]]["mask"].sum() / np.pi))
                yy, xx = np.mgrid[0:vm.shape[0], 0:vm.shape[1]]
                disk = ((yy - ys2.mean()) ** 2 + (xx - xs2.mean()) ** 2) <= R * R
                if (got[e["id"]]["mask"] & ndi.binary_dilation(disk, iterations=25)).any():
                    vt = (float(xs2.mean()), float(ys2.mean()))
            away = away_pts if (e["family"] == "arrow" and e.get("n", 1) >= 2) else None
            dd = arrow_dirs(got[e["id"]]["mask"], vt, away=away)
            dirs[e["id"]] = dd
            parts2 = []
            for d in dd:
                af = d.get("angle_far")
                s2 = "指向 %.1f°" % d["angle"]
                if af is not None:
                    dt = abs(af - d["angle"]); dt = min(dt, 360 - dt)
                    s2 = "指向 %.1f° ／ 远端 %.1f°%s" % (d["angle"], af,
                                                       "  ★ 两个读数差 %.0f°（残段，以远端为准）" % dt if dt > 15 else "")
                parts2.append("%s (%dpx)" % (s2, d["px"]))
            print("   %-4s %s" % (e["id"], "   ".join(parts2) or "-"))
    if a.debug_pieces:
        for eid, dd in dirs.items():
            for d in dd:
                print("   [dbg] %s %s w_hi=%.1f w_lo=%.1f" % (eid, d.get("bbox"), d.get("w_hi", -1), d.get("w_lo", -1)))
    for pair, want, thr in (("HP2 两核速度相反", "A1", 150.0), ("HP5 末态 e⁺e⁻ 背对背", "P1", 90.0)):
        dd = dirs.get(want) or []
        if len(dd) >= 2:
            d0 = dd[0].get("angle_far", dd[0]["angle"])
            d1 = dd[1].get("angle_far", dd[1]["angle"])
            ap = abs(d0 - d1); ap = min(ap, 360 - ap)
            note = "✓" if ap > thr else "★ 不是相向/背对背"
            if want == "P1" and 90 < ap <= 110:
                note = "✓（>90° 即背对背；IR 的理想值是约 120°，实测偏小）"
            unstable = any(d.get("angle_far") is not None
                           and min(abs(d["angle_far"] - d["angle"]),
                                   360 - abs(d["angle_far"] - d["angle"])) > 15 for d in dd[:2])
            if unstable:
                note += "  ★ 但某一支的两个读数差 >15°（残段太短），这条结论【不可信】，别据此改图"
            print("   %s：两支【有向】夹角 %.1f°  %s" % (pair, ap, note))

    print("\n⑦ 与现有路线（segsem 16 色调色板）对照")
    if not cmp_route.get("available"):
        print("   （跑不了：%s）" % cmp_route.get("why"))
    else:
        print("   一个物理物体被切成几个颜色类（>=5% 的类才算）：")
        for r in sorted(cmp_route["per_element"], key=lambda r: -r["fragments"]):
            print("      %-4s %d 个颜色类，最大那个只占 %.1f%%（%s）"
                  % (r["id"], r["fragments"], 100 * r["top"], r["top_color"]))
        print("   一个颜色类里塞了多个物理物体（>=25% 的类才算）：")
        for c, who in cmp_route["shared_classes"].items():
            print("      %s -> %s" % (c, ",".join(who)))

    KEEPTXT = {"legacy": "保留老", "new": "换新引擎", "none": "都没认出",
               "legacy-fail": "★都不合格"}
    if not a.no_arbitrate:
        print("\n⑧ v4.18 双引擎仲裁（老引擎 landmarks 不过 HARD_GATE 才换新引擎 IR 颜色模型）")
        print("   %-5s %-9s %-10s %-16s %s" % ("id", "family", "决定", "老/ 新 px", "依据"))
        for r in arb_rows:
            print("   %-5s %-9s %-10s %-16s %s"
                  % (r["id"], r["family"], KEEPTXT.get(r["keep"], r["keep"]),
                     "%s / %s" % (r["legacy_px"] if r["legacy_px"] is not None else "-",
                                  r["new_px"] if r["new_px"] is not None else "-"),
                     r["why"]))
        if not arb_rows:
            print("   （没有需要仲裁的元素：IR 里没有带 HARD_GATE 的形态族）")

    if a.sam:
        print("\n⑨ SAM 边界细化（MobileSAM vit_t 点提示；有界并集，只加不删）")
        if sam_rows is None:
            print("   （没跑起来）")
        elif not sam_rows:
            print("   （没有可细化的元素）")
        else:
            print("   %-5s %-9s %8s %10s %s" % ("id", "family", "IoU", "新增 px", "结论"))
            for r in sorted(sam_rows, key=lambda r: -r["add_px"]):
                print("   %-5s %-9s %8s %10d %s"
                      % (r["id"], r.get("family") or "-",
                         "%.3f" % r["iou"] if r["iou"] is not None else "-", r["add_px"], r["verdict"]))
            tot = sum(r["add_px"] for r in sam_rows)
            print("   合计新增 %d px（%.4f%% 画布）；接受 %d 个 / 跳过 %d 个"
                  % (tot, 100.0 * tot / (A.shape[0] * A.shape[1]),
                     sum(1 for r in sam_rows if r["add_px"] > 0),
                     sum(1 for r in sam_rows if r["add_px"] == 0)))

    np.save(os.path.join(a.outdir, "elmap.npy"), lab)
    # ★ v4.21e：resolve_z() 的 owner 下标是「从前到后」（idx 0 = z 最大、最靠前），
    #   而 SVG 装配器按 elmap 下标升序绘制（后画的盖住先画的）—— 直接喂 elmap.npy
    #   会把最靠后的 S1 画到 N2 上面（UPC 实测板边盖住红核顶部 1029 px）。
    #   这里另存一份按【z 从小到大】重排的 elmap + 名字表，装配时直接用：
    #     --elmap-in elmap_z.npy --el-names "$(cat el_names_z.txt)"
    if owner:
        n_own = len(owner)
        zmap = np.full_like(lab, -1)
        for i in owner:
            zmap[lab == i] = n_own - 1 - i
        np.save(os.path.join(a.outdir, "elmap_z.npy"), zmap)
        names_z = [owner[i]["id"] for i in sorted(owner, reverse=True)]
        with open(os.path.join(a.outdir, "el_names_z.txt"), "w", encoding="utf-8") as fh:
            fh.write(",".join(names_z))
        print("   绘制顺序（z 从后往前）-> elmap_z.npy / el_names_z.txt：%s" % ",".join(names_z))
    vis = np.clip(A, 0, 255).astype(np.uint8).copy()
    rng = np.random.RandomState(7)
    cols = rng.randint(60, 250, (len(owner) + 1, 3))
    for i in owner:
        m = lab == i
        vis[m] = (0.35 * vis[m] + 0.65 * cols[i + 1]).astype(np.uint8)
        vis[m & ~ndi.binary_erosion(m, iterations=3)] = [255, 255, 255]
    Image.fromarray(vis).save(os.path.join(a.outdir, "overlay.png"))
    lbl = np.zeros_like(vis)
    for i in owner:
        lbl[lab == i] = cols[i + 1]
    Image.fromarray(lbl).save(os.path.join(a.outdir, "labels.png"))
    json.dump(dict(bitmap=a.bitmap, ir=a.ir, elements=rows, notes=notes, consistency=cons,
                   occlusion=occ, arrows=dirs, route_compare=cmp_route, missing=miss,
                   leftover_dark=[d["bbox"] for d in leftover],
                   engine=("legacy-v4.17c" if a.no_arbitrate else "arbitrate-v4.18"),
                   arbitrate=arb_rows, new_engine=new_rows, sam=sam_rows,
                   sam_cfg=(dict(enabled=bool(a.sam), min_iou=a.sam_min_iou, grow=a.sam_grow,
                                 repo=a.sam_repo, ckpt=a.sam_ckpt) if a.sam else None)),
              io.open(a.json or os.path.join(a.outdir, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n   叠加图 -> %s" % os.path.join(a.outdir, "overlay.png"))
    print("   色块图 -> %s" % os.path.join(a.outdir, "labels.png"))


if __name__ == "__main__":
    main()
