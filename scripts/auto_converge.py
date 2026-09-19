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

sys.path.insert(0, str(Path(__file__).parent / "hep-nature-figure" / "scripts"))
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


def loss(dev):
    return sum(WEIGHT.get(k, 1.0) * abs(v) for k, v in dev.items())


def render(script, params, tag, workdir):
    pf = Path(workdir) / f"{tag}.json"
    pf.write_text(json.dumps(params), encoding="utf-8")
    r = subprocess.run([sys.executable, script, "--params", str(pf), "--tag", tag],
                       capture_output=True, text=True, cwd=str(Path(script).parent))
    if r.returncode != 0:
        raise RuntimeError(f"渲染失败:\n{r.stderr[-500:]}")
    return Path(script).parent / "repro" / "auto" / f"{tag}.png"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--max-iter", type=int, default=20)
    ap.add_argument("--step", type=float, default=0.35,
                    help="初始步长（相对调整幅度）")
    a = ap.parse_args()

    # 初始参数：从被驱动脚本的 DEFAULTS 读
    sys.path.insert(0, str(Path(a.script).parent))
    mod_name = Path(a.script).stem
    mod = __import__(mod_name)
    params = dict(mod.DEFAULTS)

    workdir = Path(tempfile.mkdtemp(prefix="autoconv_"))
    print("=" * 74)
    print("自动收敛")
    print("=" * 74)
    print(f"参考图: {a.ref}")
    print(f"渲染脚本: {a.script}")
    print(f"初始参数: {json.dumps({k: round(v,3) if isinstance(v,float) else v for k,v in params.items()})}\n")

    step = a.step
    best = None
    history = []
    cur_params = dict(params)

    for it in range(1, a.max_iter + 1):
        png = render(a.script, cur_params, f"it{it:02d}", workdir)
        ref_m, my_m = measure_pair(a.ref, png)
        dev = deviation(ref_m, my_m)
        L = loss(dev)
        worst = max(dev.items(), key=lambda kv: abs(kv[1]))
        history.append(L)

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
    ref_m, my_m = measure_pair(a.ref, best["png"])
    dev = deviation(ref_m, my_m)
    print(f"\n{'指标':<18}{'参考':>10}{'最终':>10}{'差':>8}")
    for k, v in dev.items():
        print(f"{k:<18}{ref_m[k]:>10.4f}{my_m[k]:>10.4f}{v*100:>7.0f}%")

    outp = Path("repro/auto_best.png")
    shutil.copy(best["png"], outp)
    Path("repro/auto_best_params.json").write_text(
        json.dumps(best["params"], indent=2), encoding="utf-8")
    print(f"\n最优图: {outp}")
    print(f"最优参数: repro/auto_best_params.json")
    print(f"参数变化: {json.dumps(best['params'], indent=2)}")

    # 迭代轨迹
    print("\nloss 轨迹:", " ".join(f"{v:.2f}" for v in history))


if __name__ == "__main__":
    main()
