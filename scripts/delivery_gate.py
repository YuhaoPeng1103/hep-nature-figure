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
import tempfile
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
REL_BLOCK = 0.50        # 相对偏离 >50% → 候选升级为阻断（范畴错误）

# ★★ 升级为阻断的**前置条件**：该指标在类内必须【一致】。
#
# 踩过的坑（实测数据）：
#   「T3 插画型」档案各指标的类内相对 IQR ——
#       whitespace 0.140（一致） / dark_ratio 0.277 / edge_density 0.389
#       / saturation 0.539（很散）
#   而原来的规则是「advisory 指标偏离 >50% 就升级为阻断」。
#   于是四个 advisory 指标**全部**达不到"一致"标准，却全部能当阻断门。
#
#   后果实测：一张卡通示意图的 dark_ratio = 0.0063，
#   被判定「超出 76%、阻断」；而**真实期刊图 T3-08 的 dark_ratio 正好也是
#   0.0063**，8 张 T3 精选里有 1 张比它更暗。
#   → 门禁在拿"正常波动"当"范畴错误"，5 张草图产出有 4 张被这样误杀。
#
#   这条与本文件开头写的原则（**指标在类内一致，才配当阻断门**）直接冲突，
#   现在按该原则修：只有【一致】的指标才允许升级。
CONSISTENT_IQR = 0.15   # 类内相对 IQR 低于此值 → 一致 → 可升级为阻断


def measure_candidate(path, target_size):
    im = Image.open(path).convert("RGB").resize(target_size, Image.LANCZOS)
    # 用系统临时目录，不硬编码 /tmp —— ChatGPT 沙箱等环境未必有写权限
    tmp = Path(tempfile.gettempdir()) / "_gate_norm.png"
    im.save(tmp)
    return measure(tmp)


def chroma_mean(path, size=400):
    """
    平均彩度：像素 (max(RGB) − min(RGB)) 的均值。灰度图 ≈ 0。

    为什么需要单独一个量：
      「黑白图混进彩色档案」是**范畴错误**，不是统计偏离。
      实测：一张灰度化的图 saturation=0.000，比区间下界低 100%，
      但 saturation 这个指标在类内本身极散（相对 IQR 0.54）——
      拿它当阻断门会误杀正常图；不作阻断又放走范畴错误。
      所以范畴错误要用**范畴判据**抓，而不是把统计指标的门槛调来调去。
    """
    im = Image.open(path).convert("RGB")
    a = np.asarray(im.resize(size and (size, max(1, int(size * im.size[1]
                            / max(im.size[0], 1)))), Image.LANCZOS)
                   ).astype(np.float32) / 255.0
    return float((a.max(axis=2) - a.min(axis=2)).mean())


def extra_measures(path, size):
    """线宽等补充量"""
    from style_profile import stroke_width_est
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255.0
    return {"stroke_width_est": stroke_width_est(a)}


def _find_profiles():
    """找内置风格档案。脚本目录、上一级的 assets/、以及同目录都试。"""
    here = Path(__file__).resolve().parent
    for p in (here / "style-profiles.json",
              here.parent / "assets" / "style-profiles.json",
              here / "assets" / "style-profiles.json"):
        if p.exists():
            return p
    return None


# 兜底区间的下限宽度：即使档案帮不上忙，也至少给 ±15% 的容差。
# 理由：单张参考图本来就不该有"精确到点"的容差，塌成一点是信息缺失，
# 不是"目标很明确"。给个地板比让阻断门锁死强。
MIN_REL_HALFWIDTH = 0.15


def _class_distances(single, d):
    """每个类到 single 的距离（只用类内一致的鲁棒指标，飘的指标不参与选类）。"""
    out = []
    for key, ent in d.items():
        st = ent.get("style", {})
        if not st:
            continue
        ds = []
        for k in METRIC_ROBUST:
            v = single.get(k)
            if v is None or k not in st:
                continue
            ref = st[k]["median"] if isinstance(st[k], dict) else st[k]
            if abs(ref) < 1e-9:
                continue
            ds.append(abs(v - ref) / abs(ref))
        if ds:
            out.append((sum(ds) / len(ds), key))
    return sorted(out)


def _fallback_profile(single, want_class=None):
    """
    单张参考图时，用【最近的那个子类】档案兜底区间。

    ★ 试过"取前几名类的包络"，弃用了：包络太宽，门禁变成恒过
      （实测同一张图：单类给加权总偏离 0.169、能指出 edge_density 偏 12%；
       包络给 0.000，什么也没说）。门禁的价值在【诊断】，
       一个永远说"没问题"的门禁等于没有。

    ★ 实测的诚实交代：T3-03 那张参考图到各类的距离是
        T2_surface 0.393 / unclassified 0.450 / lineart 0.481 / T3_schematic 0.493
      ——前四名几乎并列，而且它自己明明是 T3 示例图却最像 T2。
      也就是说【这个"最近类"是不可靠的】。所以：
        · 区间与目标图自身的值取并集 → 目标自己一定通过，不会误伤
        · 再加 ±15% 地板 → 不会塌成一点
        · 把选中的类和距离【打印出来】，并提示可用 --class 纠正
      宁可让判据偏宽且说得明白，也不要假精确。

    返回 (说明字符串, {指标: {p25,median,p75}}, 是否拿到) 或 (None, None, False)。
    """
    path = _find_profiles()
    if not path:
        return None, None, False
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, None, False

    if want_class:
        ent = d.get(want_class)
        if not ent:
            print(f"   ⚠️ --class {want_class} 不在档案里，可选："
                  f"{', '.join(k for k in d)}")
            return None, None, False
        out = {k: v for k, v in ent["style"].items() if isinstance(v, dict)}
        return f"{want_class}(指定, n={ent.get('n_sources','?')})", out, True

    ranked = _class_distances(single, d)
    if not ranked:
        return None, None, False

    best_d, best_k = ranked[0]
    out = {k: dict(v) for k, v in d[best_k]["style"].items()
           if isinstance(v, dict)}
    if not out:
        return None, None, False

    desc = f"最近子类 {best_k}(n={d[best_k].get('n_sources','?')}, 距离 {best_d:.2f}"
    # 并列时明说，别让人以为这个选择很确定
    if len(ranked) > 1 and ranked[1][0] <= best_d * 1.25:
        desc += f"，但与 {ranked[1][1]}({ranked[1][0]:.2f}) 等接近，"
        desc += "可用 --class 指定"
    desc += ")"
    return desc, out, True


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


def check_style(rep, cand_path, target, tol_scale=1.0, want_class=None):
    """
    风格收敛：判"在不在目标的类内区间里"，而不是"在不在中位数上"。
    只有【类内一致】的指标才阻断；分散的只提醒。
    """
    # ★ 范畴检查：灰度图撞彩色目标 → 直接阻断。
    #   这是**范畴错误**，统计指标的门槛管不住它（理由见 chroma_mean 注释）。
    #   两种目标模式都能查：
    #     --target 图片  → 直接比两图的彩度
    #     --profile 档案 → 用档案的 saturation 下界当"这一类是有彩色的"的证据
    CHROMA_COLOR = 0.06     # 彩度高于此值 → 算"有彩色"
    CHROMA_GRAY = 0.02      # 彩度低于此值 → 算"灰度"
    _cch = chroma_mean(cand_path)
    _is_dict_target = isinstance(target, dict) and "style" in target
    if not _is_dict_target:
        _target_colored = chroma_mean(target) > CHROMA_COLOR
        _how = f"目标图彩度 {chroma_mean(target):.3f}"
    else:
        # 档案模式：用类内 saturation 下界判断"这一类是不是有彩色"
        _sat = target["style"].get("saturation")
        _lo = _sat.get("p25", 1.0) if isinstance(_sat, dict) else 1.0
        _target_colored = _lo > 0.15
        _how = f"档案 saturation 下界 {_lo:.3f}"
    if _target_colored and _cch < CHROMA_GRAY:
        rep.add(False, True, "范畴·无彩色",
                f"目标是彩色的（{_how}），候选几乎无彩色（彩度 {_cch:.3f}）"
                f"——灰度图不是风格偏离，是图错了")

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
        # ★ 单张参考图：区间会塌成一个点（p25 = p75 = 该值），
        #   而 whitespace 是【阻断项】——于是判据退化成"必须落在目标那一个点
        #   ±25% 内"。一张手绘 SVG 的留白要和一张已发表位图比在 ±25% 内，
        #   基本只能靠 auto_converge 硬迭代；门外汉环境里跑不动收敛 →
        #   **阻断门 + 无收敛工具 = 死锁**，或者更糟：逼模型"为了指标调参数"，
        #   正是纪律 3 明令禁止的。
        #   修法：把单点区间与【最近子类档案】的 p25/p75 取并集。
        #   既保住"别离目标太远"，又不会因为一张图的偶然值就把路堵死。
        desc, cls_prof, got = _fallback_profile(single, want_class)
        prof = {}
        for k, v in single.items():
            if isinstance(v, list):        # palette，跳过
                continue
            lo = hi = v
            if cls_prof and k in cls_prof:
                cv = cls_prof[k]
                lo = min(v, cv["p25"])
                hi = max(v, cv["p75"])
            # 地板：单张参考图的容差不该是 0 宽
            if v > 1e-9:
                lo = min(lo, v * (1 - MIN_REL_HALFWIDTH))
                hi = max(hi, v * (1 + MIN_REL_HALFWIDTH))
            prof[k] = {"median": v, "p25": lo, "p75": hi}
        if got:
            name = f"{Path(target).name}（单张目标 + 档案兜底：{desc}）"
        else:
            name = (f"{Path(target).name}（单张目标——无档案兜底，"
                    f"区间取 ±{MIN_REL_HALFWIDTH*100:.0f}% 地板宽度）")
        has_range = got

    print(f"\n② 风格收敛（目标：{name}）")
    if has_range:
        print(f"   判据：相对偏离 ≤{REL_WARN*100:.0f}% 通过；"
              f">{REL_BLOCK*100:.0f}% 升级为阻断")
    elif not (isinstance(target, dict) and "style" in target):
        print("   ⚠️ 单张参考图且找不到子类档案兜底 → 区间退化为一个点。")
        print("      此时【阻断项已降级为提醒】，否则会锁死。")
        print("      想要真区间：给 --profile，或放好 assets/style-profiles.json")
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
        # 升级为阻断的前提：该指标在类内【一致】。飘的指标没有资格卡人。
        rel_iqr = ((hi - lo) / mid) if mid > 1e-9 else None
        can_escalate = rel_iqr is not None and rel_iqr < CONSISTENT_IQR
        if not ok and not blocking and over > REL_BLOCK and can_escalate:
            blocking, escalated = True, True
        # ★ 保命规则：拿不到真区间（无子类档案兜底）时，不许用单点当阻断门。
        #   否则"阻断门 + 装不了收敛工具"会把流程锁死，逼模型去硬调指标
        #   ——那正是纪律 3 禁止的"优化指标而不是优化图"。
        if blocking and not has_range:
            blocking = False
            note = "仅提醒（无区间兜底，不阻断）"
        elif k in BLOCKING_METRICS:
            note = "阻断项"
        elif escalated:
            note = "★升级为阻断"
        elif not ok and over > REL_BLOCK and not can_escalate:
            # 偏离很大，但该指标在类内本身就飘 → 没资格阻断
            note = f"仅提醒（类内分散 IQR={rel_iqr:.2f}，不升级）"
        else:
            note = "仅提醒"
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
    try:
        import yaml
    except ImportError:
        # 实测：PyYAML 连 requirements.txt 都没写，ChatGPT 沙箱里未必有。
        # 本函数只【打印】约束供人核对，不代判——所以降级跳过是无损的，
        # 绝不能因为缺个 yaml 就把整道门禁炸掉。
        print(f"\n① 结构断言（{Path(ir_path).name}）")
        print("   ⚠️ 缺 PyYAML，跳过结构断言（**不阻断交付**）。")
        print("      装：pip install pyyaml")
        print("      注意：结构断言本来就只打印、不代判，跳过不影响门禁结论。")
        rep.add(False, False, "IR结构断言", "缺 PyYAML，已跳过（无损）")
        return 0
    try:
        d = yaml.safe_load(Path(ir_path).read_text(encoding="utf-8"))
    except Exception as e:
        # ★ 实测踩过：IR 文件里有一行 `"#ffd060 → #a04010"（说明）`——
        #   带引号的标量后面直接跟中文括号，不是合法 YAML。
        #   原来这里没有 try，**一个格式错误的 IR 会把整道门禁炸掉**，
        #   连风格收敛的结果都看不到。IR 断言本来就只打印、不代判，
        #   所以坏 IR 应该降级成一条提醒，不该连累其他检查。
        print(f"\n① 结构断言（{Path(ir_path).name}）")
        print(f"   ⚠️ IR 解析失败，跳过结构断言（**不阻断交付**）：")
        print(f"      {str(e).splitlines()[0]}")
        for line in str(e).splitlines()[1:4]:
            print(f"      {line.strip()}")
        print("      常见原因：引号标量后面直接跟了说明文字，或中文冒号。")
        rep.add(False, False, "IR结构断言", f"IR 解析失败：{str(e)[:60]}")
        return 0
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
    ap.add_argument("--class", dest="want_class", default=None,
                    help="单张参考图时指定用哪个子类档案兜底区间"
                         "（不给则自动按最近的几个类取包络）")
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
        total = check_style(rep, a.figure, tgt, want_class=a.want_class)
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
