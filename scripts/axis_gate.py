#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""axis_gate -- 三轴物理闸门（作者 2026-10-04 要求；v4.1 起随 skill 发布，脚本在 scripts/）

作者原话：
    「你要确保以后每次生成的图三轴物理不会错」

为什么必须是机器判据（实测，2026-10-04）：
    fig_upc_3d 里生图模型把**同一根 x 轴的两端标成了两个名字**（一端 x、一端 y）：
        fig_upc_3d/trace/upc_trace_prelabel.svg  的 data-plain = y, y, z, x
        fig_upc_3d/trace/upc_trace.svg           的 data-plain = y, x, z, x  （已修）
    这个错在交付件上是**物理错误**：读者会把反应平面读成另一个平面。
    它躲过了五道门禁 —— 因为五道门禁一条也不看轴名与轴杆的对应关系。

判据（HARD，非零退出 = 不许交付）
    X1  必须声明坐标约定：IR 的 composition.坐标约定（或 elements[].params 张成轴/法线轴）
        —— 没声明 = 硬伤。约定必须写成一句可核对的话，交付说明里照抄。
    X2  三轴名必须是互不相同的三个（默认 x / y / z），且与声明的「面内 ∪ 法线」一致。
    X3  同一轴名最多出现两次（同一根轴两端各标一次），且两次位置必须落在
        **同一根轴杆的两端**（杆端各在 tol 内）—— 这一条把「两根不同的轴共用一个名字」抓出来。
    X4  三个轴名对应的轴杆方向两两相差 > 15 度（防「三轴画成两组」）。
    X5  同一张图不许同时出现「第四个单字母轴名」（除白名单外）。

输入
    --svg  交付/重建后的 SVG（有真 <text data-plain>）—— 权威读数
    --png  同图的位图（可选）—— 走无 OCR 的字形识别，用来
           (a) 在**位图阶段**就抓到模型的错标，(b) 与 SVG 读数交叉对账
           （SVG 改了、位图没重渲 = 两者轴名多重集不一致 = 硬伤）
    --ir   IR，用来读坐标约定
    --json 报告；--annot 标注图（人 5 秒能判）

用法
    python scripts/axis_gate.py --svg <fig.svg> --png <fig.png> --ir <ir.yaml> --json <rep.json> --annot <a.png>
    python scripts/axis_gate.py --png <草图.png> --ir <ir.yaml>        # 草图/仅位图模式
        -> X1/X2/X5 仍是硬判据；X3b/X4（轴杆几何）降级为读数 + 软警
           （草图上的轴杆检测不稳，误杀不起 —— 矢量交付时必须给 --svg）
    --allow-missing-axis：X2「缺轴名」降级为软警 —— 只在该图**有意不画轴字母**时用
           （如只标 beam），理由必须写进交付说明

回归标定（改过这里就要重跑；本仓库只带 T3 正样本）
    PASS  fig_upc_3d/out/upc_3d.svg
    FAIL  fig_upc_3d/trace/upc_trace_prelabel.svg
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

AXIS_RE = re.compile(r"^([xyzXYZ])(['\u2032\u2019]?)$")
# 单字母白名单：这些不是轴名（碰撞参数 / 速度 / 半径 / 核名 / 温度 …）
LETTER_WHITELIST = set("bvneEtTpgA R".replace(" ", "")) | {"\u03b3", "\u03c4", "\u03c8", "\u03c6", "\u03c1"}
ALLOWED_NONAXIS_WORDS = {"b", "v", "\u03b3", "e+", "e-", "\u03c4", "qgp", "glasma", "hadrons",
                         "nucleus a", "nucleus b", "t_c", "ep", "em"}


def norm(tok: str):
    """把文字归一成轴名（x/y/z）或 None。"""
    t = (tok or "").strip()
    m = AXIS_RE.match(t)
    if m:
        return m.group(1).lower()
    return None


# ── IR：坐标约定 ───────────────────────────────────────────────────────────
def ir_convention(ir_path):
    """返回 (面内轴列表, 法线轴, 来源说明, 原文行)。读不到就 (None, None, ...)。"""
    try:
        import yaml
    except ImportError:
        return None, None, "no yaml module", None
    try:
        doc = yaml.safe_load(io.open(ir_path, encoding="utf-8").read())
    except Exception as e:
        return None, None, "IR 读不了: %r" % (e,), None
    if not isinstance(doc, dict):
        return None, None, "IR 不是 mapping", None
    comp = doc.get("composition") or {}
    for key in ("\u5750\u6807\u7ea6\u5b9a", "coordinate_convention", "convention"):
        blk = comp.get(key) if isinstance(comp, dict) else None
        if isinstance(blk, dict):
            inplane = blk.get("\u9762\u5185") or blk.get("in_plane") or blk.get("plane")
            normal = blk.get("\u6cd5\u7ebf") or blk.get("normal")
            if inplane and normal:
                if isinstance(inplane, str):
                    inplane = [s for s in re.split(r"[\s,\u3001/\u2013-]+", inplane) if s]
                return [str(s).lower() for s in inplane], str(normal).lower(), \
                       "composition.%s" % key, json.dumps(blk, ensure_ascii=False)
    # 退路：elements[].params 里的 张成轴 / 法线轴
    for el in (doc.get("elements") or []):
        if not isinstance(el, dict):
            continue
        params = el.get("params") or {}
        if not isinstance(params, dict):
            continue
        plane = params.get("\u5f20\u6210\u8f74") or params.get("plane_axes")
        normal = params.get("\u6cd5\u7ebf\u8f74") or params.get("normal_axis")
        if plane and normal:
            if isinstance(plane, str):
                plane = [s for s in re.split(r"[\s,\u3001/\u2013-]+", plane) if s]
            return ([str(s).lower() for s in plane], str(normal).lower(),
                    "elements[%s].params.\u5f20\u6210\u8f74/\u6cd5\u7ebf\u8f74" % el.get("id"), None)
    return None, None, "\u672a\u627e\u5230\u5750\u6807\u7ea6\u5b9a", None


def ir_axes_multiset(ir_path):
    """IR 若显式写了 composition.坐标约定.轴标签 多重集，就用它当期望。"""
    try:
        import yaml
        doc = yaml.safe_load(io.open(ir_path, encoding="utf-8").read())
    except Exception:
        return None
    comp = (doc or {}).get("composition") or {}
    if not isinstance(comp, dict):
        return None
    blk = comp.get("\u5750\u6807\u7ea6\u5b9a") or {}
    if isinstance(blk, dict):
        lab = blk.get("\u8f74\u6807\u7b7e") or blk.get("axis_labels")
        if lab:
            return [norm(str(s)) for s in lab]
    return None


# ── SVG 文字层 ─────────────────────────────────────────────────────────────
def svg_labels(path):
    s = io.open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"<svg[^>]*\bwidth\s*=\s*.([0-9.]+).", s)
    m2 = re.search(r"<svg[^>]*\bheight\s*=\s*.([0-9.]+).", s)
    W = float(m.group(1)) if m else None
    H = float(m2.group(1)) if m2 else None
    out = []
    for mm in re.finditer(r"<text\b([^>]*)>(.*?)</text>", s, re.S):
        at, inner = mm.group(1), mm.group(2)
        pl = re.search(r"data-plain\s*=\s*.([^\"]*).", at)
        xs = re.search(r"\bx\s*=\s*.([0-9.\-]+).", at)
        ys = re.search(r"\by\s*=\s*.([0-9.\-]+).", at)
        fs = re.search(r"font-size\s*=\s*.([0-9.\-]+).", at)
        if not (xs and ys):
            continue
        txt = pl.group(1) if pl else re.sub(r"<[^>]+>", "", inner)
        f = float(fs.group(1)) if fs else 20.0
        out.append({"t": txt.strip(),
                    "x": float(xs.group(1)) + 0.30 * f,   # 大致取字形中心
                    "y": float(ys.group(1)) - 0.35 * f,
                    "src": "svg"})
    return W, H, out


# ── 位图字形识别（无 OCR） ──────────────────────────────────────────────────
def _font_files():
    cands = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/verdana.ttf",
             "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    return [p for p in cands if os.path.exists(p)]


def _templates(chars, N=40):
    from PIL import Image, ImageDraw, ImageFont
    templ = {}
    for fp in _font_files():
        for c in chars:
            for size in (30, 36, 44):
                try:
                    f = ImageFont.truetype(fp, size)
                except Exception:
                    continue
                img = Image.new("L", (size * 2, size * 2), 255)
                ImageDraw.Draw(img).text((size // 2, size // 2), c, font=f, fill=0)
                a = np.asarray(img) < 128
                ys, xs = np.nonzero(a)
                if len(xs) == 0:
                    continue
                a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                h, w = a.shape
                im2 = Image.fromarray((~a * 255).astype(np.uint8))
                s = N / float(max(h, w))
                im2 = im2.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))),
                                 Image.LANCZOS)
                cat = np.asarray(im2) < 128
                out = np.zeros((N, N), bool)
                oh, ow = cat.shape
                out[(N - oh) // 2:(N - oh) // 2 + oh, (N - ow) // 2:(N - ow) // 2 + ow] = cat
                templ.setdefault(c, []).append(out)
    return templ


def png_labels(path, chars=None, min_score=0.55, margin=0.04, lum_thr=130):
    """连通域 -> 行聚类 -> 单字符字形 -> 模板匹配。返回 [(tok, score, x, y)]。"""
    from PIL import Image
    from scipy import ndimage
    chars = chars or list("xyzbve") + ["\u03b3", "+", "-"]
    templ = _templates(chars)
    im = Image.open(path).convert("RGB")
    A = np.asarray(im, np.int16)
    lum = 0.299 * A[..., 0] + 0.587 * A[..., 1] + 0.114 * A[..., 2]
    mask = lum < lum_thr
    lab, n = ndimage.label(mask)
    objs = ndimage.find_objects(lab)
    H, W = mask.shape
    comps = []
    for i, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        h, w = y1 - y0, x1 - x0
        if not (10 <= h <= 0.12 * H):
            continue
        if not (2 <= w <= 0.06 * W):
            continue
        if ndimage.sum(mask[sl], lab[sl], i) < 25:
            continue
        comps.append([x0, y0, x1, y1])
    if not comps:
        return [], im
    med_h = float(np.median([c[3] - c[1] for c in comps]))
    lines = []
    for c in sorted(comps, key=lambda c: (c[1], c[0])):
        put = False
        for L in lines:
            ov = min(L["y1"], c[3]) - max(L["y0"], c[1])
            if ov > 0.5 * min(L["y1"] - L["y0"], c[3] - c[1]):
                L["c"].append(c)
                L["y0"] = min(L["y0"], c[1]); L["y1"] = max(L["y1"], c[3])
                put = True
                break
        if not put:
            lines.append({"y0": c[1], "y1": c[3], "c": [c]})
    words = []
    for L in lines:
        cs = sorted(L["c"], key=lambda c: c[0])
        cur = list(cs[0])
        grp = [cs[0]]
        for c in cs[1:]:
            if c[0] - cur[2] <= max(14.0, 0.7 * med_h):
                cur[2] = max(cur[2], c[2]); cur[3] = max(cur[3], c[3])
                cur[1] = min(cur[1], c[1])
                grp.append(c)
            else:
                words.append((cur, grp)); cur = list(c); grp = [c]
        words.append((cur, grp))
    N = 40
    found = []

    def _tpl(patch, min_sc):
        """一个字形位图 -> (char, score)；不过 min_sc / margin 就 None。"""
        h, w = patch.shape
        if h <= 0 or w <= 0:
            return None
        im2 = Image.fromarray((~patch * 255).astype(np.uint8))
        s = N / float(max(h, w))
        im2 = im2.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))), Image.LANCZOS)
        cat = np.asarray(im2) < 128
        out = np.zeros((N, N), bool)
        oh, ow = cat.shape
        out[(N - oh) // 2:(N - oh) // 2 + oh, (N - ow) // 2:(N - ow) // 2 + ow] = cat
        scores = []
        for c, ts in templ.items():
            best = max(float((out & t).sum()) / max(1.0, float((out | t).sum())) for t in ts)
            scores.append((best, c))
        scores.sort(reverse=True)
        (s1, c1), (s2, c2) = scores[0], scores[1]
        if s1 >= min_sc and s1 - s2 >= margin:
            return c1, s1
        return None

    retry = []
    for (x0, y0, x1, y1), grp in words:
        h, w = y1 - y0, x1 - x0
        r = None
        if not (h <= 0 or not (0.30 <= w / float(h) <= 2.2)):
            r = _tpl(mask[y0:y1, x0:x1], min_score)
        if r:
            found.append({"t": r[0], "score": round(r[1], 3), "x": (x0 + x1) / 2.0,
                          "y": (y0 + y1) / 2.0, "src": "png"})
            continue
        # 整个「词」没判出来 —— 轴标签被并进了旁边的箭头 / 文字里（实测 collective_flow
        # v40/C/sketch_s1121 的 x 就是这么丢的）—— 记下来按单个连通域再试一次
        if 1 < len(grp) <= 6:
            retry.append(grp)
    # 兜底：按单个连通域再试（min_score 更严 0.08，防把别的字误认成轴名）
    for grp in retry:
        for x0, y0, x1, y1 in grp:
            h, w = y1 - y0, x1 - x0
            if h <= 0 or not (0.30 <= w / float(h) <= 2.2):
                continue
            r = _tpl(mask[y0:y1, x0:x1], min_score + 0.08)
            if r:
                found.append({"t": r[0], "score": round(r[1], 3), "x": (x0 + x1) / 2.0,
                              "y": (y0 + y1) / 2.0, "src": "png"})
    return found, im



# ── 板面（网格面）方向 ─────────────────────────────────────────────────────
def plane_dirs(path, min_area=0.02):
    """最大浅灰面内的两条网格/边方向（度，y-up，mod 180）。无面返回 (None, None)。"""
    import cv2
    from PIL import Image
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float64)
    H, W = a.shape[:2]
    L = (0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]) / 255.0
    mx = a.max(2); mn = a.min(2); sat = mx - mn
    gray = ((sat < 40) & (L > 0.50) & (L < 0.97)).astype(np.uint8)
    gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(gray, 8)
    if n < 2:
        return None, None, 0.0
    i = 1 + int(np.argmax(st[1:, 4]))
    frac = st[i, 4] / float(W * H)
    if frac < min_area:
        return None, None, frac
    surf = (lab == i)
    inner = cv2.erode(surf.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    if inner.sum() < 0.5 * surf.sum():
        inner = surf
    surf = inner
    med = float(np.median(L[surf]))
    grid = (surf & (L < med * 0.985)).astype(np.uint8)
    lines = cv2.HoughLinesP(grid * 255, 1, np.pi / 1080, threshold=40,
                            minLineLength=max(30, int(0.05 * W)), maxLineGap=6)
    if lines is None:
        return surf, None, frac
    bins = {}
    for l in lines[:, 0]:
        x1, y1, x2, y2 = map(float, l)
        Ln = math.hypot(x2 - x1, y2 - y1)
        if Ln < 0.05 * W:
            continue
        ang = math.degrees(math.atan2(-(y2 - y1), x2 - x1)) % 180.0
        k = int(round(ang / 2.0)) * 2 % 180
        bins[k] = bins.get(k, 0.0) + Ln
    if not bins:
        return surf, None, frac
    top = max(bins.values())
    peaks = []
    for ang, v in sorted(bins.items(), key=lambda t: -t[1]):
        if v < 0.35 * top:
            break
        if all(min(abs(ang - q), 180 - abs(ang - q)) > 15 for q, _ in peaks):
            peaks.append((ang, v))
        if len(peaks) >= 2:
            break
    return surf, [(float(a_), float(v)) for a_, v in peaks], frac


# ── 轴杆检测 ───────────────────────────────────────────────────────────────
def detect_rods(path, thr=0.55, sm=40, minlen=0.045, gap=4):
    import cv2
    from PIL import Image
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float64)
    L = (0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]) / 255.0
    mx = a.max(2); mn = a.min(2); sat = mx - mn
    m = ((L < thr) & (sat < sm)).astype(np.uint8)
    W, H = im.width, im.height
    lines = cv2.HoughLinesP(m * 255, 1, np.pi / 1080, threshold=50,
                            minLineLength=int(minlen * W), maxLineGap=gap)
    if lines is None:
        return [], W, H
    segs = []
    for l in lines[:, 0]:
        x1, y1, x2, y2 = map(float, l)
        Ln = math.hypot(x2 - x1, y2 - y1)
        ang = math.degrees(math.atan2(-(y2 - y1), x2 - x1)) % 180.0
        k = max(10, int(Ln / 2))
        ts = np.linspace(0.05, 0.95, k)
        px = (x1 + (x2 - x1) * ts).astype(int)
        py = (y1 + (y2 - y1) * ts).astype(int)
        ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        sup = m[py[ok], px[ok]].mean() if ok.any() else 0.0
        if sup < 0.9:
            continue
        segs.append((Ln, ang, (x1, y1), (x2, y2)))
    rods = []

    def proj(R, px, py):
        th = math.radians(R["a"])
        dx, dy = px - R["c"][0], py - R["c"][1]
        d = (-dx * math.sin(th) - dy * math.cos(th))
        t = dx * math.cos(th) - dy * math.sin(th)
        return d, t

    for Ln, ang, p1, p2 in sorted(segs, key=lambda s: -s[0]):
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        hit = None
        for R in rods:
            da = min(abs(ang - R["a"]), 180 - abs(ang - R["a"]))
            d, t = proj(R, mid[0], mid[1])
            if da < 6.0 and abs(d) < 0.010 * W and abs(t) < R["halflen"] + 0.05 * W:
                hit = R
                break
        if hit is None:
            rods.append({"a": ang, "c": mid, "halflen": Ln / 2.0, "tot": Ln, "n": 1,
                         "tmin": -Ln / 2.0, "tmax": Ln / 2.0})
        else:
            k = hit["n"] + 1
            hit["c"] = ((hit["c"][0] * hit["n"] + mid[0]) / k,
                        (hit["c"][1] * hit["n"] + mid[1]) / k)
            hit["a"] = (hit["a"] * hit["n"] + ang) / k
            _, t1 = proj(hit, p1[0], p1[1])
            _, t2 = proj(hit, p2[0], p2[1])
            hit["tmin"] = min(hit["tmin"], t1, t2)
            hit["tmax"] = max(hit["tmax"], t1, t2)
            hit["halflen"] = max(abs(hit["tmin"]), abs(hit["tmax"]))
            hit["tot"] += Ln
            hit["n"] = k
    for R in rods:
        th = math.radians(R["a"])
        u = (math.cos(th), -math.sin(th))
        R["end1"] = (R["c"][0] + R["tmin"] * u[0], R["c"][1] + R["tmin"] * u[1])
        R["end2"] = (R["c"][0] + R["tmax"] * u[0], R["c"][1] + R["tmax"] * u[1])
    rods.sort(key=lambda R: -R["tot"])
    return rods, W, H


def _dist_t(R, px, py):
    th = math.radians(R["a"])
    dx, dy = px - R["c"][0], py - R["c"][1]
    return abs(-dx * math.sin(th) - dy * math.cos(th)), dx * math.cos(th) - dy * math.sin(th)


def main():
    ap = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="三轴物理闸门（见文件头）")
    ap.add_argument("--svg", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--ir", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--annot", default=None)
    ap.add_argument("--tol", type=float, default=0.030, help="标签到轴杆的容许垂距（画布宽的比例）")
    ap.add_argument("--allow-axis", action="append", default=[],
                    help="额外允许的单字母标签（如 n / R）")
    ap.add_argument("--expect", default=None,
                    help="期望的轴名多重集，逗号分隔，如 x,x,y,z；不给则从 IR 读")
    ap.add_argument("--min-score", type=float, default=0.55, help="位图字形识别的最低分")
    ap.add_argument("--strict-x0", action="store_true",
                    help="把「SVG 与位图轴名不一致」也判成硬伤（位图也是交付件时用）")
    ap.add_argument("--allow-missing-axis", action="store_true",
                    help="X2「缺轴名」降级为软警 —— 只在该图有意不画轴字母时用（如只标 beam），"
                         "交付说明里必须写明理由")
    a = ap.parse_args()

    rep = {"checks": [], "fails": [], "warns": [], "readings": {}}

    def ck(ok, label, detail, hard=True):
        rep["checks"].append({"ok": bool(ok), "label": label, "detail": detail,
                              "hard": bool(hard)})
        print("  [%s] %-52s %s" % ("ok  " if ok else ("FAIL" if hard else "warn"), label, detail))
        if not ok:
            (rep["fails"] if hard else rep["warns"]).append("%s (%s)" % (label, detail))

    print("axis_gate  svg=%s  png=%s" % (a.svg, a.png))

    # ── 读数 ──
    labs = []
    Wsvg = Hsvg = None
    png_wh = None
    if a.png:
        from PIL import Image as _I
        png_wh = _I.open(a.png).size
    if a.svg:
        Wsvg, Hsvg, labs_svg = svg_labels(a.svg)
        if png_wh and Wsvg and abs(png_wh[0] / Wsvg - 1.0) > 0.01:
            sc = png_wh[0] / float(Wsvg)
            print("   [坐标换算] SVG %.0f px -> 位图 %d px，比例 %.4f"
                  % (Wsvg, png_wh[0], sc))
            for l in labs_svg:
                l["x"] *= sc
                l["y"] *= sc
        labs += labs_svg
    labs_png = []
    png_img = None
    if a.png:
        labs_png, png_img = png_labels(a.png, min_score=a.min_score)
        labs += labs_png

    print("\n标签读数")
    for l in labs:
        print("   %-4s %-4s (%5.0f,%5.0f)  score %s" % (
            l["src"], l["t"], l["x"], l["y"], l.get("score", "-")))
    if not labs:
        print("\n结论：读不到任何标签 —— 无轴图或文字层缺失。闸门跳过（需人工确认）。")
        rep["skipped"] = True
        if a.json:
            io.open(a.json, "w", encoding="utf-8").write(
                json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    ax_svg = [l for l in labs if l["src"] == "svg" and norm(l["t"])]
    ax_png = [l for l in labs if l["src"] == "png" and norm(l["t"])]
    ax = ax_svg if ax_svg else ax_png
    if a.svg and a.png and ax_svg and ax_png:
        ms, mp = sorted(norm(l["t"]) for l in ax_svg), sorted(norm(l["t"]) for l in ax_png)
        ck(ms == mp, "X0 SVG 与位图的轴名多重集一致",
           "svg=%s  png=%s%s" % (ms, mp, "" if ms == mp else
                                 "  <- SVG 与位图不一致：要么位图没重渲，要么只改了其中一份"),
           hard=a.strict_x0)
    ax = ax_svg or ax_png
    names = [norm(l["t"]) for l in ax]

    # ── X1 约定声明 ──
    print("\nX1  坐标约定必须被声明")
    conv = None
    if a.ir:
        inplane, normal, src, raw = ir_convention(a.ir)
        if inplane and normal:
            conv = (inplane, normal)
            ck(True, "X1 坐标约定已声明", "面内=%s 法线=%s  (%s)" % (inplane, normal, src))
            rep["readings"]["convention"] = {"in_plane": inplane, "normal": normal,
                                             "source": src}
        else:
            ck(False, "X1 坐标约定已声明", "读不到（%s）—— IR 里补 composition.坐标约定：{面内:[?],法线:?}" % src)
    else:
        ck(False, "X1 坐标约定已声明", "没给 --ir —— 交付说明必须写「束流=? b=? 反应平面=? 张成 法线=?」",
           hard=False)

    # ── X2/X3 轴名 ──
    print("\nX2/X3 轴名")
    expect = None
    if a.expect:
        expect = [norm(s) for s in a.expect.split(",") if norm(s)]
    elif a.ir:
        expect = ir_axes_multiset(a.ir)
    if expect:
        ck(sorted(names) == sorted(expect), "X2 轴名多重集 == 声明",
           "实测 %s  声明 %s" % (sorted(names), sorted(expect)),
           hard=not a.allow_missing_axis)
    else:
        want = None
        if conv:
            want = conv[0] + [conv[1]]
        uniq = sorted(set(names))
        ck(len(uniq) == 3, "X2 恰好三个互不相同的轴名", "实测 %s" % uniq,
           hard=not a.allow_missing_axis)
        if want:
            ck(sorted(uniq) == sorted(want), "X2 轴名集合 == 约定",
               "实测 %s  约定 %s" % (uniq, sorted(want)),
               hard=not a.allow_missing_axis)
    from collections import Counter
    cnt = Counter(names)
    for nm, k in sorted(cnt.items()):
        ck(k <= 2, "X3 %s 出现次数 <= 2" % nm, "%d 次（同一轴两端各一次是允许的）" % k)
    extra = sorted({l["t"] for l in ax if l["t"] not in {"x", "y", "z"}})
    if extra:
        ck(False, "X5 无第四个轴名", "多出的轴名 %s" % extra)
    else:
        ck(True, "X5 无第四个轴名", "只有 x / y / z")

    # ── X3b/X4 几何：轴杆 ──
    # 草图/仅位图模式（没给 --svg）：位图上的轴杆检测不稳，X3b/X4 只作读数 + 软警
    geom_hard = bool(a.svg)
    rods = []
    if a.png:
        if not geom_hard:
            print("   （无 --svg：草图/仅位图模式 —— X3b/X4 降级为读数 + 软警；矢量交付时必须给 --svg）")
        rods, W, H = detect_rods(a.png)
        print("\n轴杆检测（%d 根，按支持度排序，前 8）" % len(rods))
        for i, R in enumerate(rods[:8]):
            print("   rod%-2d dir %6.1f  c(%5.0f,%5.0f)  halflen %5.0f  tot %6.0f"
                  % (i, R["a"], R["c"][0], R["c"][1], R["halflen"], R["tot"]))
        Wc = W
        tol = a.tol * Wc
        tol_end = max(2.5 * tol, 0.10 * Wc)
        by_name = {}
        for l in ax:
            by_name.setdefault(norm(l["t"]), []).append(l)
        assoc = {}
        for nm, lst in sorted(by_name.items()):
            if len(lst) == 2:
                (l1, l2) = lst
                best = None
                for i, R in enumerate(rods):
                    d1 = math.hypot(l1["x"] - R["end1"][0], l1["y"] - R["end1"][1])
                    d2 = math.hypot(l2["x"] - R["end2"][0], l2["y"] - R["end2"][1])
                    d3 = math.hypot(l1["x"] - R["end2"][0], l1["y"] - R["end2"][1])
                    d4 = math.hypot(l2["x"] - R["end1"][0], l2["y"] - R["end1"][1])
                    m = min(max(d1, d2), max(d3, d4))
                    if best is None or m < best[0]:
                        best = (m, i)
                if best and best[0] <= tol_end:
                    assoc[nm] = rods[best[1]]["a"]
                    ck(True, "X3 %s 的两次标注在同一根轴杆两端" % nm,
                       "rod dir %.1f, 端距 %.0f px (容许 %.0f)" % (rods[best[1]]["a"], best[0], tol_end),
                       hard=geom_hard)
                else:
                    assoc[nm] = None
                    ck(False, "X3 %s 的两次标注在同一根轴杆两端" % nm,
                       "最近的杆端距 %.0f px > 容许 %.0f —— 两根不同的轴共用一个名字？" % (
                           best[0] if best else -1, tol_end), hard=geom_hard)
            else:
                best = None
                for i, R in enumerate(rods):
                    d, t = _dist_t(R, lst[0]["x"], lst[0]["y"])
                    if abs(t) <= R["halflen"] + 0.03 * Wc and (best is None or d < best[0]):
                        best = (d, i)
                if best and best[0] <= tol:
                    assoc[nm] = rods[best[1]]["a"]
                else:
                    assoc[nm] = None
                    ck(False, "X4 %s 标注贴在一根轴杆上" % nm,
                       "最近的杆垂距 %.0f px > 容许 %.0f" % (best[0] if best else -1, tol), hard=False)
        got = [(nm, ang) for nm, ang in assoc.items() if ang is not None]
        if len(got) >= 3:
            bad = []
            for i in range(len(got)):
                for j in range(i + 1, len(got)):
                    d = min(abs(got[i][1] - got[j][1]), 180 - abs(got[i][1] - got[j][1]))
                    if d <= 15.0:
                        bad.append("%s/%s 相差 %.1f 度" % (got[i][0], got[j][0], d))
            ck(not bad, "X4 三轴方向两两相差 > 15 度",
               "；".join(bad) if bad else "；".join("%s=%.1f" % g for g in got), hard=geom_hard)

        # ── X6 板面 vs 三轴：板在哪个平面、哪根轴是法线 ──
        surf, pdirs, pfrac = plane_dirs(a.png)
        if pdirs and len(pdirs) == 2 and assoc:
            print("\nX6  板面与三轴同一投影（板面占比 %.3f，两条边方向 %s）"
                  % (pfrac, ["%.1f" % d for d, _ in pdirs]))
            pd = [d for d, _ in pdirs]
            inplane_expected = set(conv[0]) if conv else None
            normal_expected = conv[1] if conv else None
            for nm, ang in sorted(assoc.items()):
                if ang is None:
                    continue
                dm = min(min(abs(ang - d), 180 - abs(ang - d)) for d in pd)
                par = dm <= 15.0
                role = "面内" if par else "面外"
                ok = True
                why = ""
                if normal_expected:
                    if nm == normal_expected and par:
                        ok, why = False, "约定说 %s 是法线，但它与板的一条边平行" % nm
                    if nm in (inplane_expected or set()) and not par:
                        ok, why = False, "约定说 %s 在面内，但它与板的两条边都差 %.0f 度" % (nm, dm)
                ck(dm <= 30.0, "X6 %s 与板面关系 = %s" % (nm, role),
                   "与最近板边差 %.1f 度%s%s" % (
                       dm, "" if ok else "",
                       ("  <- " + why) if why else ""),
                   hard=False)
                if why and dm <= 30.0:
                    rep["warns"].append("X6 %s: %s" % (nm, why))
                    print("         warn: %s" % why)
            rep["readings"]["plane"] = {"frac": round(pfrac, 3),
                                        "edges": [round(d, 1) for d in pd]}

        rep["readings"]["rods"] = [{"dir": round(R["a"], 1),
                                    "centre": [round(R["c"][0]), round(R["c"][1])],
                                    "halflen": round(R["halflen"])} for R in rods[:12]]
        rep["readings"]["name_to_dir"] = {k: (round(v, 1) if v is not None else None)
                                          for k, v in assoc.items()}

        if a.annot and png_img is not None:
            from PIL import ImageDraw
            im2 = png_img.copy()
            d = ImageDraw.Draw(im2)
            for R in rods[:12]:
                d.line([R["end1"], R["end2"]], fill=(0, 160, 255), width=3)
            for l in ax:
                d.ellipse([l["x"] - 22, l["y"] - 22, l["x"] + 22, l["y"] + 22],
                          outline=(0, 200, 0) if l["src"] == "svg" else (255, 0, 255), width=4)
                d.text((l["x"] + 24, l["y"] - 30), "%s" % l["t"], fill=(200, 0, 0))
            im2.save(a.annot)
            print("\n标注图 -> %s" % a.annot)

    print("\n读数：%s" % json.dumps(rep["readings"], ensure_ascii=False))
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2))
        print("报告 -> %s" % a.json)
    if rep["fails"]:
        print("\n结论：三轴物理闸门未过 —— 不许交付。硬伤：")
        for f in rep["fails"]:
            print("   - %s" % f)
        return 1
    print("\n结论：三轴物理闸门通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
