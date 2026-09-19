#!/usr/bin/env python3
"""
delivery_gate —— 阻断式交付门禁

与 nature-figure 的门禁【不同】：
  它的门禁判"是否符合固定标准"（1.5pt 对齐、字号≥5pt）——标准是死的。
  这里的门禁判"离【目标风格】还差多远"——目标是活的，可以是任意一张参考图。

  这样才能"一直改到目标风格"，而不是"改到某个通用标准"。

三类检查，任一不过 → 阻断交付（退出码 1）：

  ① 结构断言  —— 来自 IR 的 assertions.machine，逐条可判定
  ② 风格收敛  —— 与目标（参考图 或 风格档案）的偏离在容差内
  ③ 投稿合规  —— 矢量、字体内嵌、字号 ≥5pt、文字可提取

用法：
    # 对参考图收敛
    python3 delivery_gate.py fig.png --target 参考图.png

    # 对风格档案收敛（适用于目标图有版权、不能随仓库分发的情况）
    python3 delivery_gate.py fig.png --profile hep-t3.profile.json

    # 加 IR 断言
    python3 delivery_gate.py fig.png --target 参考图.png --ir ir/B1.yaml

    # 交付成套检查
    python3 delivery_gate.py fig.png --target 参考图.png --pdf fig.pdf
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from style_bench import measure, METRIC_ROBUST

# ══════════════════════════════════════════════════════════════
#  容差策略 —— 按【类内离散度】决定，不是拍脑袋定
#
#  实测（T3_schematic, n=22）：
#    留白     相对IQR 0.10  → 类内很一致  → 可以当【阻断门】
#    饱和度   相对IQR 0.47  → 分散        → 只提醒
#    边密度   相对IQR 0.24  → 分散        → 只提醒
#    暗像素   相对IQR 0.45  → 分散        → 只提醒
#
#  原则：**指标在类内一致，才配当阻断门。** 不一致的只做参考。
# ══════════════════════════════════════════════════════════════
# ── 阻断策略：两级 ──
# ① 类内一致的指标 → 一律阻断
BLOCKING_METRICS = {"whitespace"}
# ② 类内分散的指标 → 通常仅提醒，**但超出太多就升级为阻断**
ADVISORY_METRICS = {"saturation", "edge_density", "dark_ratio",
                    "stroke_width_est"}
# ★ 偏离的度量：相对【区间边界】，不是相对区间宽度。
#   踩过的坑：saturation=0.002 vs 区间 [0.242,0.370]
#     用「区间宽度」归一 → (0.242-0.002)/0.128 = 1.9，看着"只是偏一点"
#     用「下界」归一   → (0.242-0.002)/0.242 = 0.99，真相是"低了 99%"
#   区间宽度做分母会掩盖"整个量级都不对"这种情况。
REL_WARN = 0.25         # 相对偏离 >25% → 偏
REL_BLOCK = 0.50        # 相对偏离 >50% → 升级为阻断（范畴错误）


def measure_candidate(path, target_size):
    im = Image.open(path).convert("RGB").resize(target_size, Image.LANCZOS)
    tmp = Path("/tmp/_gate_norm.png")
    im.save(tmp)
    return measure(tmp)


def extra_measures(path, size):
    """线宽等补充量"""
    from style_profile import stroke_width_est
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255.0
    return {"stroke_width_est": stroke_width_est(a)}


class Report:
    def __init__(self):
        self.fails = []
        self.warns = []
        self.passes = []

    def add(self, ok, blocking, name, detail):
        if ok:
            self.passes.append((name, detail))
        elif blocking:
            self.fails.append((name, detail))
        else:
            self.warns.append((name, detail))


def check_style(rep, cand_path, target, tol_scale=1.0):
    """
    风格收敛：判"在不在目标的类内区间里"，而不是"在不在中位数上"。
    只有【类内一致】的指标才阻断；分散的只提醒。
    """
    if isinstance(target, dict) and "style" in target:
        prof = target["style"]
        name = f"档案 {target.get('name','?')}（{target.get('n_sources',1)} 张）"
        has_range = all(isinstance(v, dict) for k, v in prof.items()
                        if k != "palette")
        cand = measure(cand_path)
        cand.update(extra_measures(cand_path, Image.open(cand_path).size))
    else:
        tim = Image.open(target).convert("RGB")
        tgt_size = tim.size
        cand = measure_candidate(cand_path, tgt_size)
        cand.update(extra_measures(cand_path, tgt_size))
        single = measure(target)
        single.update(extra_measures(target, tgt_size))
        prof = {k: {"median": v, "p25": v, "p75": v}
                for k, v in single.items() if not isinstance(v, list)}
        name = Path(target).name + "（单张目标——区间即该值本身）"
        has_range = False

    print(f"\n② 风格收敛（目标：{name}）")
    if has_range:
        print(f"   判据：相对偏离 ≤{REL_WARN*100:.0f}% 通过；"
              f">{REL_BLOCK*100:.0f}% 升级为阻断")
    print(f"   {'指标':<18}{'目标区间':>20}{'本图':>9}{'偏离':>9}  判定")
    total, n_block = 0.0, 0
    for k in list(BLOCKING_METRICS) + list(ADVISORY_METRICS):
        if k not in prof:
            continue
        v = prof[k]
        lo, mid, hi = (v["p25"], v["median"], v["p75"]) \
            if isinstance(v, dict) else (v, v, v)
        c = cand.get(k)
        if c is None or mid <= 1e-9:
            continue
        # 相对【最近的边界】算偏离
        if c > hi:
            over = (c - hi) / max(hi, 1e-9)
        elif c < lo:
            over = (lo - c) / max(lo, 1e-9)
        else:
            over = 0.0
        total += over
        ok = over <= REL_WARN
        blocking = k in BLOCKING_METRICS
        escalated = False
        if not ok and not blocking and over > REL_BLOCK:
            blocking, escalated = True, True
        note = ("阻断项" if k in BLOCKING_METRICS else
                ("★升级为阻断" if escalated else "仅提醒"))
        print(f"   {k:<18}[{lo:>7.3f},{hi:>7.3f}]{c:>9.3f}{over*100:>8.0f}%  "
              f"{'OK' if ok else '超出'}  ({note})")
        if not ok:
            rep.add(False, blocking, f"风格·{k}",
                    f"在类内区间外 {over:.1f} 倍（{note}）")
            if blocking:
                n_block += 1
    print(f"   {'':<18}{'':>20}{'':>9}  加权总偏离 {total:.3f}"
          f"  阻断项 {n_block} 个")
    return total


def check_ir(rep, ir_path):
    """① 结构断言（IR 的 geometry_constraints 等）"""
    import yaml
    d = yaml.safe_load(Path(ir_path).read_text(encoding="utf-8"))
    print(f"\n① 结构断言（{Path(ir_path).name}）")
    gc = d.get("geometry_constraints")
    a = d.get("assertions", {})
    n = 0
    if gc:
        for c in gc.get("约束", []):
            print(f"   ▸ {c['名']}: {c['量']} 要求 {c['要求']}")
            n += 1
    if a.get("machine"):
        for x in a["machine"]:
            print(f"   ☐ {x}")
            n += 1
    print(f"   （{n} 条，需实现脚本自证或人工核对——本门禁不代判）")
    return n


def check_delivery(rep, pdf_path):
    """③ 投稿合规"""
    import fitz
    print(f"\n③ 投稿合规（{Path(pdf_path).name}）")
    p = fitz.open(pdf_path)[0]
    n_img = len(p.get_images())
    txt = p.get_text().strip()
    sizes = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    sizes.append(round(s["size"], 1))
    lo = min(sizes) if sizes else 0
    checks = [
        (n_img == 0, True, "无嵌入位图", f"{n_img} 个"),
        (bool(txt), True, "文字可提取", f"{len(txt)} 字符"),
        (lo >= 5.0, True, "最小字号 ≥5pt", f"{lo} pt"),
        (len(p.get_drawings()) > 5 or len(p.get_xobjects()) > 0, True,
         "含矢量内容", f"{len(p.get_drawings())} 指令 + "
                      f"{len(p.get_xobjects())} XObject"),
    ]
    for ok, blocking, name, detail in checks:
        print(f"   {'✅' if ok else '❌'} {name}: {detail}")
        rep.add(ok, blocking, f"合规·{name}", detail)


def main():
    ap = argparse.ArgumentParser(description="阻断式交付门禁")
    ap.add_argument("figure")
    ap.add_argument("--target", help="参考图（判'离它多远'）")
    ap.add_argument("--profile", help="风格档案 JSON（目标图有版权时用）")
    ap.add_argument("--ir", help="IR 文件（结构断言）")
    ap.add_argument("--pdf", help="交付 PDF（投稿合规）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    print("=" * 70)
    print("交付门禁 —— 判【离目标风格多远】，不是【符合某个固定标准】")
    print("=" * 70)
    print(f"候选: {a.figure}")

    rep = Report()
    total = None
    if a.target or a.profile:
        if a.profile:
            tgt = json.loads(Path(a.profile).read_text(encoding="utf-8"))
        else:
            tgt = a.target
        total = check_style(rep, a.figure, tgt)
    else:
        print("\n② 未指定目标（--target 或 --profile），跳过风格收敛检查")
        rep.add(False, False, "风格收敛", "未指定目标，无法判定")

    if a.ir:
        check_ir(rep, a.ir)
    if a.pdf:
        check_delivery(rep, a.pdf)

    print("\n" + "=" * 70)
    if rep.fails:
        print(f"🚫 阻断交付：{len(rep.fails)} 项未达标")
        for n, d in rep.fails:
            print(f"   ✗ {n}: {d}")
        print("\n   修完再跑本门禁；合格前不要声明交付。")
        if total is not None:
            print(f"   当前加权总偏离 {total:.3f}"
                  f"（越低越接近目标；可反复迭代直到收敛）")
        return 1
    if rep.warns:
        print(f"⚠️  可通过，但 {len(rep.warns)} 项需复核")
        for n, d in rep.warns:
            print(f"   ! {n}: {d}")
    print(f"\n✅ 门禁通过（{len(rep.passes)} 项）")
    if total is not None:
        print(f"   加权总偏离 {total:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
