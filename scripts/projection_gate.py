#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""projection_gate —— T3 立体示意图的【投影 + 空间关系】闸口
=========================================================================

## ★ 为什么这个闸口量的是 IR，不是渲染出来的图

一开始想做的是"从出图里量出它实际用了什么投影"。**做了两个探针，都被校准否掉**：

| 探针 | 想法 | 为什么废 |
|---|---|---|
| 塑形覆盖率 | 量形体内部低频亮度起伏 | 把**扁的**判成更有立体感 |
| 边线方向直方图 | 边线方向只落在几个固定角度 | 代码矢量图上完全正确，**一到真图就废**：T3-30 真图 6.0%、T3-02 6.8%，和生图模型的 5.7–9.3% 分不开 —— 它量的是边缘锐利度，不是投影一致性 |

（详见 `references/3d-checklist.md` 第 6 节。）

**所以换个思路：闸口不量图，量【声明】。**
「板正对读者 + z 画成有长度的箭头」这个致命组合，在 IR 里就是**可判定的自相矛盾**
——不需要出图就能抓。而至于是不是照着画了，交给返修单/事后校正那条线。

## 判据（P 层 + G 层）

    P0  T3 图必须有 projection（含 主平面）
    P1  三条轴里除 y 可竖直外，不许有 0° / ±90°
    P2  主平面的法线轴，前缩必须明显 < 1
    P3  不许用"透视"（示意图形变不可控）
    G1  T3 图必须声明 穿透（谁穿过主平面）
    G2  T3 图必须声明 遮挡（板边压住物体后半）

## 用法

    python3 scripts/projection_gate.py ir/xxx.ir.yaml
    python3 scripts/projection_gate.py ir/*.ir.yaml --strict   # 警告也算失败
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK, WARN, FAIL = "✅", "⚠️", "❌"
# 判定「这是不是一张 T3 立体示意图」的关键词
T3_HINT = ("3d", "3D", "三维", "立体", "体积", "球面明暗", "半写实", "透视", "斜投影", "等轴测")


def _load(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _is_t3(ir: dict) -> bool:
    st = ir.get("style") or {}
    blob = " ".join(str(st.get(k, "")) for k in ("classification", "evidence", "mode", "look"))
    blob += " " + " ".join(str(x) for x in (st.get("characteristics") or []))
    return any(h in blob for h in T3_HINT)


def check(ir: dict, strict: bool = False):
    """→ (rows, ok)。rows 是 [(级别, 判据, 说明)]。"""
    rows = []
    comp = ir.get("composition") or {}
    proj = comp.get("projection") or comp.get("投影")
    plane = comp.get("主平面")
    t3 = _is_t3(ir)

    if not t3:
        return [(OK, "P0", "非 T3 图，跳过投影闸口")], True

    # ── P0：有没有声明 ──
    if not proj:
        rows.append((FAIL, "P0", "T3 图必须写 composition.projection"
                                "（类型 / 轴方向_deg / 前缩）—— 光写「视角」锁不住投影："
                                "实测把 z 的屏幕方向算到小数点后三位写进简报，4 个 seed 只有 1 个照做"))
        return rows, False
    rows.append((OK, "P0", "有 projection"))

    # ── P3：类型不许是透视 ──
    typ = str(proj.get("类型") or "")
    if "透视" in typ and "斜" not in typ:
        rows.append((FAIL, "P3", f"投影类型写的是「{typ}」—— 示意图形变不可控，"
                                 "应写 斜二测 / 等轴测 / 斜投影"))
    else:
        rows.append((OK, "P3", f"类型：{typ or '（未写）'}"))

    # ── P1：轴方向 ──
    ad = proj.get("轴方向_deg") or {}
    if not ad:
        rows.append((FAIL, "P1", "缺 轴方向_deg —— 三轴在画面上的方向没给数"))
    else:
        for ax in ("x", "y", "z"):
            d = ad.get(ax)
            if d is None:
                rows.append((FAIL, "P1", f"缺 {ax} 轴方向"))
                continue
            d = float(d)
            near = min(abs(d % 180), abs(d % 180 - 90), abs(d % 180 - 180)) <= 4.0
            if near and ax != "y":
                rows.append((FAIL, "P1", f"{ax} 轴 {d:g}° 与画面的水平/垂直方向重合 —— "
                                       "有一条这样的轴，等于没有投影，整张图必然扁平"))
            else:
                rows.append((OK, "P1", f"{ax} 轴 {d:g}°"))
        dirs = [float(ad[a]) % 180 for a in ("x", "y", "z") if ad.get(a) is not None]
        if len(dirs) == 3:
            ds = sorted(dirs)
            gaps = [ds[1] - ds[0], ds[2] - ds[1], 180 - (ds[2] - ds[0])]
            if min(gaps) < 8:
                rows.append((FAIL, "P1", f"有两条轴几乎同向（最小夹角 {min(gaps):.1f}°）"
                                       "—— 三轴挤在一起，平面朝向读不出来"))
            else:
                rows.append((OK, "P1", f"三轴分离度 {min(gaps):.1f}°"))

    # ── P2：法线轴前缩 ──
    fo = proj.get("前缩") or {}
    if not fo:
        rows.append((FAIL, "P2", "缺 前缩 —— 法线轴的前缩比没给，"
                                 "模型会把 z 画得和 x/y 一样长（= 宣称板子正对读者）"))
    else:
        vals = {k: float(v) for k, v in fo.items() if isinstance(v, (int, float))}
        if not vals:
            rows.append((WARN, "P2", f"前缩 写得认不出：{fo}"))
        else:
            mn = min(vals.values())
            if mn >= 0.88:
                rows.append((FAIL, "P2", f"最小前缩 {mn:g} —— 没有明显短于 1 的轴。"
                                        "法线轴必须前缩，否则和「板子斜置」自相矛盾"))
            else:
                k = min(vals, key=vals.get)
                rows.append((OK, "P2", f"前缩最小的是 {k} = {mn:g}"))

    # ── G1 / G2：空间关系 ──
    pierce = comp.get("穿透") or []
    occl = comp.get("遮挡")
    if not pierce:
        rows.append((FAIL, "G1", "没声明 穿透 —— 立体感的一大半来自「物体穿过主平面」，"
                                 "不写这句，出来的图物体是「贴」在板前面的"))
    else:
        n = len(pierce) if isinstance(pierce, (list, tuple)) else 1
        rows.append((OK, "G1", f"声明了 {n} 处穿透"))
    if not occl:
        rows.append((FAIL, "G2", "没声明 遮挡 —— 板边/网格必须压在物体后半上，"
                                 "否则物体像「浮」在板前面"))
    else:
        rows.append((OK, "G2", "声明了遮挡"))

    if not plane:
        rows.append((WARN, "P0", "没写 主平面 —— 建议写明是哪张平面、张在哪两个轴上"))

    ok = all(r[0] != FAIL for r in rows) and (not strict or all(r[0] == OK for r in rows))
    return rows, ok


def main() -> int:
    ap = argparse.ArgumentParser(description="T3 示意图的投影 + 空间关系闸口")
    ap.add_argument("irs", nargs="+")
    ap.add_argument("--strict", action="store_true", help="警告也算失败")
    a = ap.parse_args()

    bad = 0
    for p in a.irs:
        path = Path(p)
        if not path.exists():
            print(f"{FAIL} 找不到 {path}")
            bad += 1
            continue
        rows, ok = check(_load(path), a.strict)
        print(f"\n{'='*70}\n{path.name}   {'通过' if ok else '不通过'}")
        print(f"{'='*70}")
        for lvl, code, msg in rows:
            print(f"  {lvl} {code}  {msg}")
        if not ok:
            bad += 1
    print(f"\n{'='*70}\n{len(a.irs) - bad} / {len(a.irs)} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
