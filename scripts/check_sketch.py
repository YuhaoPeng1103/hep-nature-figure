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
    # 闸口② 成品位图（喂同一个 IR）
    python3 check_sketch.py gen/render_s22.png --ir ir/xxx.ir.yaml

    python3 check_sketch.py gen/render_s22.png --ir ir/xxx.ir.yaml \\
        --profile assets/style-profiles.json --class "T3-schematic (illustration)"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))


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
        for i, b in enumerate(blobs[:2], 1):
            w, h = b["wh"]
            ratio = (h / w) if horiz else (w / h)
            axis = "高/宽" if horiz else "宽/高"
            good = ratio >= thr
            if good:
                note = "沿%s束流方向压扁（Lorentz 收缩）— 对" % ("水平" if horiz else "竖直")
            else:
                note = "**压扁方向垂直于运动方向** —— 画反了"
            lines.append("  %s 核#%d box=%s %d×%d  %s=%.2f  %s"
                         % ("✅" if good else "❌", i, b["box"], w, h, axis, ratio, note))
            if not good:
                hard.append("核#%d 的 Lorentz 收缩方向画反（%s=%.2f < %.2f）"
                            % (i, axis, ratio, thr))
    return lines, hard


def main():
    ap = argparse.ArgumentParser(description="位图闸口 —— 草图 / 成品位图通用，流程里跑两次")
    ap.add_argument("image")
    ap.add_argument("--ir", required=True, help="对应的 IR —— 几何约束从它来")
    ap.add_argument("--profile", help="风格档案（可选）")
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--canvas", help="IR 声明的画布 WxH，用于查比例是否被改")
    ap.add_argument("--trim", type=int, default=0,
                    help="先裁掉四周 N px 再测（处理生图模型画的贴边细外框）")
    a = ap.parse_args()

    img_path = Path(a.image)
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
    cv = (ir.get("figure") or {}).get("canvas") or {}
    if cv.get("w") and cv.get("h"):
        want = cv["w"] / cv["h"]
        dev = abs(W / H - want) / want
        flag = "✅" if dev < 0.12 else "❌"
        print(f"  {flag} IR 声明的比例 {want:.2f}，实际 {W/H:.2f}"
              f"（偏差 {dev*100:.0f}%）")
        if dev >= 0.12:
            print("     → 比例被改了。比例变了，IR 里的归一化坐标全部失效。")
    print()

    # ══ 一、自动测 ══
    print("■ 自动测到的（这些机器能判）")
    st = content_stats(img)
    hard, soft = [], []
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
        # 现在只实现了"压扁/收缩"这一族；别的名字原样跳过（免得假装测了）
        if "压扁" in str(c.get("名", "")) or "收缩" in str(c.get("名", "")):
            mcons.append(c)
    if mcons:
        print()
        print("  ├ Lorentz 收缩方向（★ 机器量的，不用人回答）")
        lines, lhard = lorentz_check(img, mcons)
        for ln in lines:
            print(ln)
        if lhard:
            print("     → 两核必须**沿运动方向**压扁（收缩轴 ∥ 速度）。"
                  "画成横扁 = 收缩轴垂直于速度 = 物理错。")
            print("       修法：IR 的 style.conventions 已写明形状 → 简报里"
                  "（ir_to_genbrief 会带过去）必须有这一条；没有就补上再重出。")
        hard += lhard

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
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
