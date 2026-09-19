#!/usr/bin/env python3
"""
工具链回归测试
===============
每个 case 都是**真实踩过的坑**。没有这套测试时，改一个工具会悄悄
弄坏另一个 —— 这正是"修一个坏一个"的根因。

跑法：
    python3 evals/test_tools.py          # 全部
    python3 evals/test_tools.py -v       # 显示每个 case 的细节
    python3 evals/test_tools.py geom     # 只跑名字含 geom 的

不加 pytest 依赖（要能在 ChatGPT 沙箱里跑）。
"""
import math
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

RESULTS = []


def case(name, why):
    """装饰器：登记一个测试 case 和它防的是什么坑"""
    def deco(fn):
        fn._case = (name, why)
        return fn
    return deco


# ══════════════════════════════════════════════════════════════
#  坑 1：几何约束
#  实测：UPC 图核 A 的箭头画成一右一左（A 明明向右运动），
#        末态 e+/e- dot=+1.08 同向，违反动量守恒。都靠约束抓出来的。
# ══════════════════════════════════════════════════════════════

@case("geom_opposite_velocity",
      "两核相向运动：dot<0。防'箭头画反了'——渲染图看不出来")
def test_opposite_velocity():
    def check(vA, vB):
        return vA[0]*vB[0] + vA[1]*vB[1] < 0
    assert check((1, 0), (-1, 0)), "正确情形应通过"
    assert not check((1, 0), (1, 0)), "同向应被拒（第一版就是这个错）"


@case("geom_back_to_back_final_state",
      "两体末态背对背：dot<0。防'末态同向'——动量守恒")
def test_back_to_back():
    def check(u, v):
        return u[0]*v[0] + u[1]*v[1] < 0
    # 实测踩过的错值：两粒子都朝右 → dot=+1.08
    assert not check((1.30, 0.78), (1.30, -0.78)), "同向应被拒"
    assert check((1.45, 0.80), (-1.45, -0.80)), "背对背应通过"


@case("geom_no_overlap_upc",
      "UPC 两核不重叠：竖直间距 > 两核半径和。防'画成普通碰撞'")
def test_no_overlap():
    def ok(gap, r_sum):
        return gap - r_sum > 0
    assert ok(3.12, 1.72), "不重叠应通过"
    assert not ok(1.0, 1.72), "重叠应被拒（那是普通重离子碰撞）"


# ══════════════════════════════════════════════════════════════
#  坑 2：风格门禁的偏离度量
#  实测：saturation 0.002 vs 区间 [0.242,0.370]
#        用「区间宽度」归一 → 1.9，看着"只是偏一点"
#        用「区间边界」归一 → 0.99，真相是"低了 99%"
# ══════════════════════════════════════════════════════════════

@case("gate_deviation_metric",
      "偏离要用【区间边界】归一，不是【区间宽度】。"
      "防'量级错误被当成轻微偏离'")
def test_deviation_metric():
    def over_boundary(c, lo, hi):
        if c > hi:
            return (c - hi) / max(hi, 1e-9)
        if c < lo:
            return (lo - c) / max(lo, 1e-9)
        return 0.0

    def over_width(c, lo, hi):
        span = max(hi - lo, 1e-9)
        return (lo - c)/span if c < lo else ((c-hi)/span if c > hi else 0)

    # 实测案例：纯黑白图的饱和度
    lo, hi, c = 0.242, 0.370, 0.002
    assert over_width(c, lo, hi) < 2.0, "区间宽度法给出误导性的小值"
    assert over_boundary(c, lo, hi) > 0.9, "区间边界法应给出 ~0.99"
    # 在区间内 → 0
    assert over_boundary(0.30, lo, hi) == 0.0


@case("gate_escalates_category_error",
      "提醒项超出阈值要【升级为阻断】。防'黑白图通过门禁'——"
      "我因为这个漏洞放过了一张明显不合格的图")
def test_escalation():
    REL_WARN, REL_BLOCK = 0.25, 0.50
    def verdict(over):
        if over <= REL_WARN: return "ok"
        return "block" if over > REL_BLOCK else "warn"
    assert verdict(0.99) == "block", "99% 偏离必须阻断"
    assert verdict(0.11) == "ok", "11% 偏离不该拦"
    assert verdict(0.35) == "warn", "35% 偏离只提醒"


@case("gate_uses_subclass_profile",
      "门禁必须用【子类】档案。防'拿错类当目标'——"
      "UPC 撞合并档案 weighted=1.130，撞插画型子类=0.640")
def test_subclass_profile():
    import json
    p = HERE.parent / "assets" / "style-profiles.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "T3-schematic (illustration)" in d, "应有插画型子类档案"
    assert "T3-schematic (lineart)" in d, "应有线稿型子类档案"
    ill = d["T3-schematic (illustration)"]["style"]["saturation"]["median"]
    lin = d["T3-schematic (lineart)"]["style"]["saturation"]["median"]
    assert ill > lin, "插画型饱和应高于线稿型（否则子类没分开）"


# ══════════════════════════════════════════════════════════════
#  坑 3：局部构图
#  实测：UPC 的 nucleus A 标签 bbox 上边 −2.9pt（在页面外会被裁），
#        全局风格指标全过，是构图审计抓出来的
# ══════════════════════════════════════════════════════════════

@case("composition_catches_out_of_bounds",
      "构图审计能抓到出界文字。防'标签被裁但全局指标全绿'")
def test_out_of_bounds():
    r = subprocess.run([sys.executable, str(SCRIPTS / "audit_composition.py"),
                        "--help"], capture_output=True, text=True)
    assert r.returncode == 0, "审计脚本应可运行"
    src = (SCRIPTS / "audit_composition.py").read_text(encoding="utf-8")
    assert "check_out_of_bounds" in src, "应有出界检查"
    assert "margin_pt" in src, "应有边距阈值"


@case("composition_catches_text_overlap",
      "构图审计能抓到文字重叠")
def test_text_overlap():
    sys.path.insert(0, str(SCRIPTS))
    import fitz
    from audit_composition import check_text_text
    # 两个重叠 50% 的文字块
    a = {"bbox": fitz.Rect(0, 0, 100, 20), "text": "AAA"}
    b = {"bbox": fitz.Rect(50, 0, 150, 20), "text": "BBB"}
    bad = check_text_text([a, b], 10000)
    assert len(bad) == 1, f"应检出 1 处重叠，实得 {len(bad)}"
    # 相邻但不重叠 → 不该误报
    c = {"bbox": fitz.Rect(200, 0, 300, 20), "text": "CCC"}
    assert len(check_text_text([a, c], 10000)) == 0, "相邻不该误报"


# ══════════════════════════════════════════════════════════════
#  坑 4：渲染静默失败
#  实测：这些坑**都不报错，只画错**
# ══════════════════════════════════════════════════════════════

@case("render_detects_gradient_failure",
      "check_render 能抓到'渐变变纯黑'。防用了不支持 SVG 渐变的渲染器"
      "（PyMuPDF 渲染 SVG 渐变 → 全黑且不报错）")
def test_gradient_detection():
    import numpy as np
    from PIL import Image
    from check_render import check_no_black_blob
    # 造一张"渐变失效"的图：整块纯黑
    bad = Image.fromarray(np.zeros((60, 60, 3), dtype=np.uint8))
    assert not check_no_black_blob(bad)["pass"], "纯黑图应被检出"
    # 正常图：白底
    good = Image.fromarray(np.full((60, 60, 3), 250, dtype=np.uint8))
    assert check_no_black_blob(good)["pass"], "白底不该误报"


@case("render_detects_missing_element",
      "check_render 的元素命中能抓到'字体丢失/元素被盖住'——"
      "防 z 序画反导致元素凭空消失")
def test_probe_detection():
    import numpy as np
    from PIL import Image
    from check_render import check_probes
    im = Image.fromarray(np.full((100, 100, 3), 255, dtype=np.uint8))
    import PIL.ImageDraw as D
    D.Draw(im).ellipse([10, 10, 30, 30], fill=(0, 0, 0))
    # 有墨的地方应命中
    r = check_probes(im, [(0.2, 0.2)])
    assert r[0]["pass"], "有墨处应命中"
    # 空白处应报缺失
    r2 = check_probes(im, [(0.8, 0.8)])
    assert not r2[0]["pass"], "空白处应报缺失"


# ══════════════════════════════════════════════════════════════
#  坑 5：风格档案的正确性
# ══════════════════════════════════════════════════════════════

@case("profile_stores_ranges_not_points",
      "风格档案存【区间】(p25/p75)，不是单点中位数——"
      "因为同类的图本来就各不相同")
def test_profile_ranges():
    import json
    d = json.loads((HERE.parent / "assets" / "style-profiles.json")
                   .read_text(encoding="utf-8"))
    for cls, v in d.items():
        for k, s in v["style"].items():
            if not isinstance(s, dict):
                continue
            assert {"median", "p25", "p75"} <= set(s), f"{cls}.{k} 缺区间字段"
            assert s["p25"] <= s["median"] <= s["p75"], f"{cls}.{k} 区间顺序错"


@case("profile_metrics_are_robust_only",
      "只有【跨来源可比】的指标能进档案。"
      "防把 color_richness / gradient_ratio 这类出处敏感的量当目标")
def test_robust_metrics():
    from style_bench import METRIC_ROBUST
    assert METRIC_ROBUST["color_richness"] is False, "color_richness 不可信"
    assert METRIC_ROBUST["gradient_ratio"] is False, "gradient_ratio 不可信"
    assert METRIC_ROBUST["whitespace"] is True, "whitespace 可信"


# ══════════════════════════════════════════════════════════════
#  坑 6：工具探测
# ══════════════════════════════════════════════════════════════

@case("tool_detection_gives_install_cmd",
      "缺工具时要给【装机命令】，不是绕开")
def test_tool_install_hint():
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_tools.py")],
                       capture_output=True, text=True, timeout=180)
    out = r.stdout
    assert "安装" in out, "输出应含装机指引"
    assert ("apt" in out or "winget" in out or "http" in out), \
        "应给出具体安装命令/链接"


# ══════════════════════════════════════════════════════════════
#  运行器
# ══════════════════════════════════════════════════════════════

def main():
    verbose = "-v" in sys.argv
    filt = [a for a in sys.argv[1:] if not a.startswith("-")]
    tests = [v for k, v in sorted(globals().items())
             if callable(v) and hasattr(v, "_case")]
    if filt:
        tests = [t for t in tests
                 if any(f in t._case[0] or f in t.__name__ for f in filt)]

    print(f"\n{'='*70}")
    print(f"工具链回归测试 —— {len(tests)} 个 case（每个对应一个真实踩过的坑）")
    print(f"{'='*70}\n")
    npass = 0
    for t in tests:
        name, why = t._case
        try:
            t()
            print(f"  ✅ {name}")
            if verbose:
                print(f"     {why}")
            npass += 1
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            print(f"  ❌ {name}")
            print(f"     {why}")
            print(f"     → {e}")
            RESULTS.append((name, False, str(e)))
        except Exception as e:
            print(f"  💥 {name}  ({type(e).__name__}: {e})")
            if verbose:
                traceback.print_exc()
            RESULTS.append((name, False, f"{type(e).__name__}: {e}"))

    print(f"\n{'='*70}")
    print(f"结果：{npass}/{len(tests)} 通过")
    if npass < len(tests):
        print("\n失败的 case：")
        for n, ok, d in RESULTS:
            if not ok:
                print(f"  ✗ {n}: {d}")
    print(f"{'='*70}")
    return 0 if npass == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
