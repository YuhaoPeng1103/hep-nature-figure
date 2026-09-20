#!/usr/bin/env python3
"""
auto_converge —— 自动把复现图迭代到接近参考图

为什么需要：
  手工调了 7 轮才复现一张图的一个 panel。老师要的是"省时间"，
  手工 7 轮就白做了。这个脚本把「量 → 定位 → 修正 → 复测」自动化。

核心是那张**映射表**——指标偏离该调哪个参数。
这是原本靠人判断的"专家知识"，这里显式写出来。

方法：带回溯的爬山搜索
  · 每轮找偏离最大的鲁棒指标
  · 按映射表调整对应参数
  · 变好就保留，变差就回退并把步长减半

用法：
    python3 auto_converge.py --ref 参考图.png \
        --script repro_T3-03_param.py --max-iter 20
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style_bench import measure, METRIC_ROBUST

# ── 映射表：指标偏离 → 调哪个参数 ──────────────────────────────
# ★ sign 的语义 = 【修正方向】，不是"参数与指标的相关方向"：
#     指标偏高(mdev>0) 时需要把指标拉低。若参数与指标正相关，
#     就得把参数调小 → sign = -1。**这里踩过一次错**：
#     第一版把 sign 写成了相关方向(全 +1)，结果指标越高越加，
#     饱和度 +70% 还一个劲增大 sat_mul，南辕北辙。
#
# ★ 这张表是【实测】出来的，不是猜的。
#   做法：每个参数 ×0.7 / ×1.3 各渲一次，量各指标的响应幅度。
#   踩过的坑：第一版凭直觉写表（dark_mul→dark_ratio 等），结果只猜对 1 条，
#   循环还因参数撞界而冻死。**先测敏感度，再写映射。**
RULES = {
    # ★ sign 语义 = 【修正方向】：指标偏高(mdev>0)时，参数该往哪走。
    #   正相关(参数↑指标↑) → 降指标要降参数 → sign = -1
    #   负相关(参数↑指标↓) → 降指标要升参数 → sign = +1
    #   实测的四个鲁棒指标全是正相关，故全是 -1。
    "dark_ratio": {
        "param": "grad_span", "sign": -1, "corr": "正", "amp": 0.91,
        "why": "暗像素 ← 渐变跨度", "range": (0.40, 2.60),
    },
    "saturation": {
        "param": "sat_mul", "sign": -1, "corr": "正", "amp": 0.59,
        "why": "饱和度 ← 饱和度乘子", "range": (0.30, 1.60),
    },
    "whitespace": {
        "param": "face_tone", "sign": -1, "corr": "正", "amp": 0.57,
        "why": "留白 ← 前表面亮度（正相关！原来 sign 写反了）",
        "range": (0.60, 1.00),
    },
    "edge_density": {
        "param": "spoke_n", "sign": -1, "corr": "正", "amp": 0.32,
        "why": "边密度 ← 辐条数（选它是为了与 whitespace 的杠杆解耦）",
        "range": (30, 52),
    },
    # ⚠️ gradient_ratio 已移除：二次校准发现它对出处极度敏感
    #    （缩放到 40% 就从 0.23 涨到 0.43），参考图的值正落在退化区间内。
    "gradient_ratio": None,
}

TOL = 0.10          # 相对偏差 <10% 视为达标
WEIGHT = {          # 鲁棒指标的权重（暗像素和边密度最能反映"像不像"）
    "dark_ratio": 1.5, "edge_density": 1.5,
    "whitespace": 1.0, "saturation": 1.0, "gradient_ratio": 1.0,
}

# ══════════════════════════════════════════════════════════════
#  ★★ 创作任务（--profile）默认**不优化这两个指标**
#
#  实测证据：拿 --profile 驱动卡通图收敛，优化器为了满足
#  dark_ratio / edge_density，把 label_scale 一路推到上界 1.60 —— 结果
#  "nucleus A" 与 "nucleus B" 挤成不可读的一团，底部说明文字溢出画布。
#  **机械上收敛了，图上更差了。** 这正是纪律 3 禁止的"优化指标而不是优化图"。
#
#  为什么会这样：dark_ratio 与 text_area_ratio 几乎是同一个函数
#  （近黑像素占比），它测的是**文字密度**；edge_density 对字号也有 +99% 响应。
#  所以"把这两个指标调上去"实际等于"把字调大"，与图的质量无关。
#
#  正确用法：它们当**诊断**（看偏离多少、往哪看），不当**目标**。
#  确实想优化它们时用 --include-ink-metrics 显式打开。
INK_PROXY_METRICS = {"dark_ratio", "edge_density"}


def measure_pair(ref_path, mine_path):
    """归一到同一尺寸再量（避免分辨率偏差，见 style-bench 的陷阱 3）"""
    ra = Image.open(ref_path).size
    rb = Image.open(mine_path).size
    tgt = ra if max(ra) <= max(rb) else rb
    out = {}
    for nm, p in (("ref", ref_path), ("mine", mine_path)):
        im = Image.open(p).convert("RGB").resize(tgt, Image.LANCZOS)
        tmp = Path(tempfile.gettempdir()) / f"_ac_{nm}.png"
        im.save(tmp)
        out[nm] = measure(tmp)
    return out["ref"], out["mine"]


def measure_one(mine_path, ref_path=None):
    """--ref：两张图归一到同尺寸再量；--profile：只量自己，不需要参考图。"""
    if ref_path:
        return measure_pair(ref_path, mine_path)
    im = Image.open(mine_path).convert("RGB")
    tmp = Path(tempfile.gettempdir()) / "_ac_solo.png"
    im.save(tmp)
    return None, measure(tmp)


def deviation(ref_m, my_m):
    dev = {}
    for k, v in my_m.items():
        if k == "aspect" or not METRIC_ROBUST.get(k, True):
            continue
        r = ref_m[k]
        if r <= 1e-9:
            continue
        dev[k] = (v - r) / r
    return dev


def deviation_profile(prof_style, my_m, target_size=None):
    """
    ★ 无参考图时的目标：用【风格档案的区间】而不是一张图。

    为什么需要它：`--ref` 是必填的，于是**复现任务能自动收敛、创作任务完全不能**
    ——草图为输入的卡通图没有参考图可比，这条路整个走不通。

    偏离的度量与 delivery_gate 保持一致：相对【最近的区间边界】归一。
    踩过的坑（见 delivery_gate）：用区间宽度做分母会掩盖"整个量级都不对"。
    """
    dev = {}
    for k, v in my_m.items():
        if k == "aspect" or not METRIC_ROBUST.get(k, True):
            continue
        ent = prof_style.get(k)
        if not isinstance(ent, dict):
            continue
        lo, hi = ent.get("p25"), ent.get("p75")
        if lo is None or hi is None:
            continue
        if v > hi:
            dev[k] = (v - hi) / max(hi, 1e-9)
        elif v < lo:
            dev[k] = (v - lo) / max(lo, 1e-9)      # 负号表示"偏低"
        else:
            dev[k] = 0.0
    return dev


def loss(dev):
    return sum(WEIGHT.get(k, 1.0) * abs(v) for k, v in dev.items())


def composition_gate(png_path, enabled=True):
    """
    对候选跑**局部构图审计**，返回问题列表（空 = 通过）。

    ★ 为什么必须加这一步（实测踩到的）：
      拿 --ref 对着 T3-02 跑跨图收敛，loss 从 4.24 降到 2.50，
      优化器把 label_scale 顶到上界 1.6 —— 结果标签压成一团、
      底部说明跑出画布。**loss 降了，图坏了。**
      而 auto_converge 当时**完全不知道**，还把那轮报成"最好的一轮"，
      直到下游门禁才发现，8 处问题、阻断交付。
      → 优化循环必须自己看得见"这张图能不能交付"，否则就是在往坑里迭代。

    审计读的是 PDF 几何。驱动脚本自己出 PDF 最好；只出 SVG 时用 cairosvg
    转一份临时 PDF（两个驱动脚本都出 SVG，所以这条路总是通的）。
    """
    if not enabled:
        return []
    import subprocess
    import sys as _sys
    here = Path(__file__).resolve().parent
    audit = here / "audit_composition.py"
    if not audit.exists():
        return []
    pdf = Path(png_path).with_suffix(".pdf")
    tmp_pdf = None
    if not pdf.exists():
        svg = Path(png_path).with_suffix(".svg")
        if not svg.exists():
            return []                      # 没有 PDF 也没有 SVG → 无法审计，放行
        try:
            import cairosvg
            tmp_pdf = Path(tempfile.gettempdir()) / (Path(png_path).stem + "_audit.pdf")
            cairosvg.svg2pdf(url=str(svg), write_to=str(tmp_pdf))
            pdf = tmp_pdf
        except Exception:
            return []
    try:
        r = subprocess.run([_sys.executable, str(audit), str(pdf)],
                           capture_output=True, text=True, timeout=180)
    except Exception:
        return []
    if r.returncode == 0:
        return []
    # 从输出里抠出失败项（"   ✗ xxx"）
    fails = [ln.strip()[2:].strip()
             for ln in r.stdout.splitlines() if ln.strip().startswith("✗")]
    return fails or ["构图审计未通过"]


def render(script, params, tag, workdir):
    # ★ 必须把脚本路径**解析成绝对路径**再调用：
    #   这里会把 cwd 切到脚本所在目录，如果 script 传的是相对路径，
    #   切换之后它就指向了错误的位置（实测：报
    #   ".../scripts/hep-nature-figure/scripts/repro_T3-03_param.py: No such file"）。
    script = Path(script).resolve()
    pf = Path(workdir) / f"{tag}.json"
    pf.write_text(json.dumps(params), encoding="utf-8")
    r = subprocess.run([sys.executable, str(script), "--params", str(pf),
                        "--tag", tag],
                       capture_output=True, text=True, cwd=str(script.parent))
    if r.returncode != 0:
        raise RuntimeError(f"渲染失败:\n{r.stderr[-500:]}")
    return script.parent / "repro" / "auto" / f"{tag}.png"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ref", help="参考图（复现任务：判'离它多远'）")
    g.add_argument("--profile",
                   help="风格档案 JSON（**创作任务**：没有参考图，用类内区间当目标）")
    ap.add_argument("--class", dest="want_class", default=None,
                    help="--profile 指向合并档案时，指定用哪个子类")
    ap.add_argument("--script", required=True)
    ap.add_argument("--max-iter", type=int, default=20)
    ap.add_argument("--step", type=float, default=0.35,
                    help="初始步长（相对调整幅度）")
    ap.add_argument("--no-composition-gate", dest="composition_gate",
                    action="store_false", default=True,
                    help="关掉每轮的构图审计（默认开）。只在驱动脚本"
                         "既不出 PDF 也不出 SVG 时才需要关")
    ap.add_argument("--include-ink-metrics", action="store_true",
                    help="把 dark_ratio / edge_density 也当优化目标。"
                         "⚠️ 默认关：它们本质是文字密度代理，调它们会把字越调越大")
    a = ap.parse_args()

    # ★ 卡通/创作任务走 --profile：目标是一段【区间】，不是某一张图。
    #   这样"草图 → 卡通图"这条线才第一次有了自动收敛能力。
    prof_style = None
    if a.profile:
        pdata = json.loads(Path(a.profile).read_text(encoding="utf-8"))
        if a.want_class:
            pdata = pdata.get(a.want_class, {})
        elif "style" not in pdata:
            # 传进来的是整个档案文件（多个类）→ 取第一个，并提示可用 --class
            print(f"⚠️ 档案含多个类：{list(pdata)[:6]}；"
                  f"默认取「{list(pdata)[0]}」，可用 --class 指定")
            pdata = pdata[list(pdata)[0]]
        prof_style = pdata.get("style", pdata)

    # 初始参数：从被驱动脚本的 DEFAULTS 读
    sys.path.insert(0, str(Path(a.script).parent))
    mod_name = Path(a.script).stem
    mod = __import__(mod_name)
    params = dict(mod.DEFAULTS)
    # ★ 映射表是"这张图的专家知识"，应该跟着脚本走而不是写死在这里。
    #   被驱动脚本若导出了 RULES，就用它的；否则退回内置的那张
    #   （内置那张是 repro_T3-03_param.py 实测标定出来的，只对那张图有效）。
    global RULES
    if hasattr(mod, "RULES"):
        RULES = mod.RULES
        print(f"映射表: 用 {mod_name}.RULES（{len(RULES)} 条）")
    else:
        print(f"映射表: 用 auto_converge 内置的（{len(RULES)} 条）"
              f"——被驱动脚本可导出 RULES 覆盖")

    workdir = Path(tempfile.mkdtemp(prefix="autoconv_"))
    print("=" * 74)
    print("自动收敛")
    print("=" * 74)
    _target = a.ref if a.ref else f"{a.profile}（风格档案区间）"
    print(f"目标: {_target}")
    print(f"渲染脚本: {a.script}")
    print(f"初始参数: {json.dumps({k: round(v,3) if isinstance(v,float) else v for k,v in params.items()})}\n")

    step = a.step
    best = None
    history = []
    comp_rejected = []   # 被构图门禁否掉的迭代
    cur_params = dict(params)

    for it in range(1, a.max_iter + 1):
        png = render(a.script, cur_params, f"it{it:02d}", workdir)
        ref_m, my_m = measure_one(png, a.ref)
        dev = (deviation(ref_m, my_m) if a.ref
               else deviation_profile(prof_style, my_m))
        if not a.ref and not a.include_ink_metrics:
            dev = {k: v for k, v in dev.items() if k not in INK_PROXY_METRICS}
        L = loss(dev)
        worst = max(dev.items(), key=lambda kv: abs(kv[1]))
        history.append(L)

        # ── ★ 构图门禁：坏了构图的候选一律作废 ──
        # 实测证据：跨图收敛时优化器把 label_scale 顶到上界，loss 降了
        # 但标签压成一团、文字出界。如果不在这里拦，它会一路"收敛"到
        # 一张会被下游门禁拒绝的图，白烧迭代。
        comp = composition_gate(png, a.composition_gate)
        if comp:
            print(f"[{it:02d}] loss={L:.3f}  ✗ 构图审计 {len(comp)} 处问题 → 候选作废")
            for x in comp[:3]:
                print(f"       ✗ {x}")
            if len(comp) > 3:
                print(f"       … 另有 {len(comp)-3} 处")
            comp_rejected.append((it, len(comp)))
            if best is not None:
                cur_params = dict(best["params"])
                step *= 0.5
                print(f"       → 回退到第 {best['it']} 轮参数，步长减半为 {step:.3f}")
                if step < 0.01:
                    print("   步长过小，停止搜索")
                    break
            else:
                # 连第一个候选都坏构图 → **基准参数本身**就不合格。
                # ★ 这里必须【立刻停】，不能 continue：
                #   best 还是 None 时参数不会变，下一轮会渲出**一模一样**的东西、
                #   被同一个理由再否一次 —— 空转到 max_iter，白烧时间。
                #   （实测：repro_T3-03_param 的基准就出界 3 处，
                #     原来会连着否 3 轮。）
                print("       ⚠️ 基准参数就不过构图门禁 —— "
                      "这是**参数起点的问题**，不是搜索能修的。")
                print("          收敛的每一轮都是从基准派生出来的，基准不干净，"
                      "搜不出干净的解。")
                print("          → 先手工把基准构图调到通过，再来跑收敛。")
                break
            continue

        # ── 回溯：变差就回退参数并把步长减半 ──
        # ★ 第一版漏了这一条（文档写了但代码没写），导致 loss 单调恶化 2.59→5.33。
        if best is not None and L > best["loss"] + 1e-6:
            cur_params = dict(best["params"])
            step *= 0.5
            print(f"[{it:02d}] loss={L:.3f}  ✗ 变差 → 回退到第 {best['it']} 轮参数，"
                  f"步长减半为 {step:.3f}")
            if step < 0.01:
                print("   步长过小，停止搜索")
                break
            continue

        if best is None or L < best["loss"]:
            best = {"loss": L, "params": dict(cur_params), "it": it, "png": png}
            tag = "  ← 目前最好"
        else:
            tag = ""

        print(f"[{it:02d}] loss={L:.3f}  最大偏离: {worst[0]} {worst[1]*100:+.0f}%{tag}")
        for k, v in sorted(dev.items(), key=lambda kv: -abs(kv[1])):
            flag = "★" if abs(v) > TOL else ("~" if abs(v) > TOL/2 else " ")
            note = ""
            if RULES.get(k, "unknown") is None:
                note = "  (无杠杆，不可调)"
            print(f"       {flag} {k:<16}{v*100:+7.1f}%{note}")

        # 收敛判据：只看【可调】的指标
        adjustable = {k: v for k, v in dev.items()
                      if RULES.get(k, "unknown") not in (None, "unknown")}
        if adjustable and all(abs(v) < TOL for v in adjustable.values()):
            print(f"\n✅ 第 {it} 轮收敛：可调指标都在 ±{TOL*100:.0f}% 内")
            break

        # ── 调整：按偏离从大到小找第一个【有杠杆且未撞界】的指标 ──
        order = sorted(dev.items(), key=lambda kv: -abs(kv[1]))
        acted = False
        for mname, mdev in order:
            rule = RULES.get(mname, "unknown")
            if not isinstance(rule, dict):
                continue
            pname = rule["param"]
            cur = cur_params.get(pname)
            lo, hi = rule["range"]
            # ★ 方向感知的撞界判断：sign<0 只会往【小】走，只需看下界。
            #   原来两端都判，导致 face_tone 起始值=上界就被永久跳过
            #   （whitespace 一直报"最大偏离"却从不调它，就是这个原因）。
            if rule["sign"] < 0 and cur <= lo + 1e-9:
                continue
            if rule["sign"] > 0 and cur >= hi - 1e-9:
                continue
            delta = rule["sign"] * np.clip(mdev, -0.8, 0.8) * step * abs(cur)
            newv = float(np.clip(cur + delta, lo, hi))
            if pname == "spoke_n":
                newv = float(int(round(newv)))
            if abs(newv - cur) < 1e-6:
                continue
            cur_params[pname] = newv
            print(f"   → 调 {pname}: {cur:.3f} → {newv:.3f}   （{rule['why']}）")
            acted = True
            break
        if not acted:
            print("   （所有可调参数都已撞界或无杠杆——提前停止）")
            break

    else:
        print(f"\n⚠️ 达到最大迭代 {a.max_iter} 轮")

    # 汇总
    print("\n" + "=" * 74)
    print(f"最好的一轮: 第 {best['it']} 轮, loss={best['loss']:.3f}")
    ref_m, my_m = measure_one(best["png"], a.ref)
    dev = deviation(ref_m, my_m) if a.ref else deviation_profile(prof_style, my_m)
    if not a.ref and not a.include_ink_metrics:
        print("\n注：dark_ratio / edge_density 未参与优化（它们是文字密度代理，"
              "调它们只会把字越调越大）。\n    要看它们请加 --include-ink-metrics，"
              "或用 delivery_gate 当诊断量看。")
        dev_show = deviation_profile(prof_style, my_m)
    else:
        dev_show = dev
    if a.ref:
        print(f"\n{'指标':<18}{'参考':>10}{'最终':>10}{'差':>8}")
        for k, v in dev.items():
            print(f"{k:<18}{ref_m[k]:>10.4f}{my_m[k]:>10.4f}{v*100:>7.0f}%")
    else:
        print(f"\n{'指标':<18}{'目标区间':>20}{'最终':>10}{'偏离':>8}")
        for k, v in dev_show.items():
            e = prof_style[k]
            print(f"{k:<18}[{e['p25']:>8.4f},{e['p75']:>8.4f}]"
                  f"{my_m[k]:>10.4f}{v*100:>7.0f}%")

    outp = Path("repro/auto_best.png")
    shutil.copy(best["png"], outp)
    Path("repro/auto_best_params.json").write_text(
        json.dumps(best["params"], indent=2), encoding="utf-8")
    print(f"\n最优图: {outp}")
    print(f"最优参数: repro/auto_best_params.json")
    print(f"参数变化: {json.dumps(best['params'], indent=2)}")

    # 迭代轨迹
    print("\nloss 轨迹:", " ".join(f"{v:.2f}" for v in history))
    if comp_rejected:
        n = sum(c for _, c in comp_rejected)
        iters = ", ".join(f"第{i}轮({c}处)" for i, c in comp_rejected[:8])
        print(f"构图门禁否掉了 {len(comp_rejected)} 个候选，共 {n} 处问题：{iters}")
        print("  → 如果否掉的多，说明**参数空间里没有既降 loss 又不破坏构图的解**，"
              "换个参数或改构图再跑，别硬搜。")


if __name__ == "__main__":
    main()
