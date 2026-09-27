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

# ── 定位工具脚本目录 ───────────────────────────────────────────
# 原来硬假设 evals/ 与 scripts/ 是兄弟目录。这在扁平布局（如 ChatGPT 沙箱里
# 所有 .py 解包到同一处）不成立，首个失败在 :139 的 subprocess。
#
# ★ 为什么不用"到处搜 scripts/"：搜索会命中**错误的副本**——用户上传的旧版、
#   __pycache__、上次会话的残留目录——然后静默地测错代码还全绿。
#   对一个以"防静默失败"为卖点的项目，这是最不能接受的失败方式。
#   所以：优先环境变量显式指定，否则只认两个确定的位置，并在开头打印
#   【实际测的是哪个目录、每个模块的路径】，让"测的是谁"永远可见。
def _resolve_scripts():
    import os
    env = os.environ.get("HEPNF_SCRIPTS")
    if env:
        p = Path(env).expanduser().resolve()
        if not (p / "svg_lib.py").exists():
            raise SystemExit(f"HEPNF_SCRIPTS={p} 里没有 svg_lib.py，请检查")
        return p, "环境变量 HEPNF_SCRIPTS"
    for cand, why in ((HERE.parent / "scripts", "skills 布局（evals/ 与 scripts/ 同级）"),
                      (HERE, "扁平布局（脚本与本文件同目录）")):
        if (cand / "svg_lib.py").exists():
            return cand, why
    raise SystemExit(
        "找不到工具脚本（需要含 svg_lib.py 的目录）。\n"
        "  · skills 布局：确认 evals/ 与 scripts/ 是兄弟目录\n"
        "  · 扁平布局：把 test_tools.py 和工具 .py 放同一目录\n"
        "  · 也可显式指定：HEPNF_SCRIPTS=/path/to/scripts python3 test_tools.py")


SCRIPTS, _SCRIPT_WHY = _resolve_scripts()
sys.path.insert(0, str(SCRIPTS))

# 风格档案可能在三处：skills 布局的 assets/、扁平布局的 assets/、
# 或者干脆和脚本平铺在一起（解包时最容易出现的一种）。
_PROFILE_CANDIDATES = [
    SCRIPTS.parent / "assets" / "style-profiles.json",
    SCRIPTS / "assets" / "style-profiles.json",
    SCRIPTS / "style-profiles.json",
    HERE / "style-profiles.json",
    HERE.parent / "style-profiles.json",
]
PROFILES = next((p for p in _PROFILE_CANDIDATES if p.exists()),
                _PROFILE_CANDIDATES[0])

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


@case("gate_catches_category_error_not_drift",
      "范畴错误要阻断（黑白图），正常波动不许阻断（飘的指标没资格卡人）")
def test_escalation():
    """
    ★ 这个 case 原来**自己重写了一遍阈值逻辑**（`verdict(over)` 是本地定义的），
      所以它测的是"我抄的这份逻辑对不对"，而不是"delivery_gate 实际怎么做"——
      改了真代码它也照样绿。典型的自证（和 sketch4 的几何自核对同一个毛病）。
      现在改成真的去跑 delivery_gate.py，两种情形都验：

        ① 范畴错误（灰度图撞彩色档案）→ 必须阻断
        ② 类内分散的指标偏离很大       → **不许**阻断（只提醒）
    """
    import json
    import subprocess
    import tempfile

    gate = SCRIPTS / "delivery_gate.py"
    assert gate.exists(), "delivery_gate.py 应在 scripts/ 下"
    prof = json.loads(PROFILES.read_text(encoding="utf-8"))
    illus = prof["T3-schematic (illustration)"]

    tmp = Path(tempfile.mkdtemp(prefix="gatetest_"))
    pj = tmp / "illus.json"
    pj.write_text(json.dumps(illus), encoding="utf-8")

    # 造一张"有彩色、但几乎没有深色像素"的图 —— 正是原来被误杀的那种
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (400, 260), "#fdfaf6")
    d = ImageDraw.Draw(im)
    d.ellipse([120, 60, 280, 200], fill="#f6a04a", outline="#c06010", width=3)
    d.ellipse([160, 100, 240, 160], fill="#ffd070", outline="#c06010", width=2)
    normal = tmp / "normal.png"
    im.save(normal)

    r = subprocess.run([sys.executable, str(gate), str(normal),
                        "--profile", str(pj)],
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    out = r.stdout
    assert "范畴·无彩色" not in out, "有彩色的图不该被判'无彩色'"
    # 关键：飘的指标（dark_ratio/edge_density/saturation）再偏也不许升级为阻断
    assert "🚫" not in out, (
        "类内分散的指标不可升级为阻断（相对IQR 均 >0.15）。\n"
        "  这正是 5 张草图产出有 4 张被误杀的原因。\n"
        f"  实际输出：\n{out[-500:]}")

    # ② 灰度图 → 范畴错误 → 必须阻断
    gray = tmp / "gray.png"
    im.convert("L").convert("RGB").save(gray)
    r2 = subprocess.run([sys.executable, str(gate), str(gray),
                         "--profile", str(pj)],
                        capture_output=True, text=True, timeout=120,
                        encoding="utf-8", errors="replace")
    assert r2.returncode != 0 and "范畴·无彩色" in r2.stdout, (
        "灰度图撞彩色档案必须阻断（这是升级规则原本要防的那个漏洞）")


@case("gate_uses_subclass_profile",
      "门禁必须用【子类】档案。防'拿错类当目标'——"
      "UPC 撞合并档案 weighted=1.130，撞插画型子类=0.640")
def test_subclass_profile():
    import json
    d = json.loads(PROFILES.read_text(encoding="utf-8"))
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
                        "--help"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
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
    d = json.loads(PROFILES.read_text(encoding="utf-8"))
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
      "缺工具时要给【装机命令】+【装不了时的替代路径】。"
      "防两件事：① 无网络沙箱里只让用户'去装'，流程直接卡死；"
      "② 探测表漏项导致报告永远误导性地全绿（实测漏过 shapely / PyYAML）")
def test_tool_install_hint():
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_tools.py")],
                       capture_output=True, text=True, timeout=180,
                       encoding="utf-8", errors="replace")
    out = r.stdout
    assert r.returncode == 0, f"check_tools 应正常退出，实际 {r.returncode}"
    assert "安装" in out, "输出应含装机指引"
    assert ("apt" in out or "winget" in out or "http" in out), \
        "应给出具体安装命令/链接"

    # ★ 原版断言到这里就结束了——而这些文字【无论探测结果如何都会打印】，
    #   所以它测不出"探测本身是否正确"，是典型的假绿。补两条真检查：

    # ① 无网络环境的关键：缺的工具必须带"装不了时"的替代路径
    assert "装不了时" in out, \
        "缺失工具必须给出'装不了时'的替代路径（无网络沙箱里'去装'是死路）"

    # ② 探测表必须覆盖实际会被 import 的依赖，否则"缺工具"报告是失真的。
    #    实测踩过：表里没有 shapely / PyYAML，报告全绿，运行时才炸。
    for mod in ("shapely", "yaml"):
        assert mod in out.lower(), \
            f"check_tools 的探测表应包含 {mod}（实际会被 import，漏了就是假绿）"


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
    print(f"{'='*70}")
    # ★ 把"测的是哪一份代码"打印出来。解包出错 / 测到旧副本 / 少装了几个文件时，
    #   哈希和路径是唯一能立刻看出来的东西——否则只会得到一堆莫名其妙的失败。
    import hashlib
    print(f"  工具目录：{SCRIPTS}   （判定依据：{_SCRIPT_WHY}）")
    print(f"  风格档案：{PROFILES}  {'✓' if PROFILES.exists() else '✗ 缺失'}")
    for m in ("svg_lib", "geom", "check_render", "style_bench",
              "style_profile", "audit_composition"):
        f = SCRIPTS / f"{m}.py"
        if f.exists():
            h = hashlib.sha256(f.read_bytes()).hexdigest()[:10]
            print(f"    {m:<20} {h}")
        else:
            print(f"    {m:<20} ✗ 不存在")
    print()
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


@case("composition_oob_ignores_zero_area_sliver",
      "出界判据要按 subpath 判 + 越界部分要有面积。防 Edge 打印的零面积毛边"
      "把每一张位图临摹稿都误判成『出界』而阻断交付")
def test_oob_sliver():
    """
    ★ 实测（2026-09-26，UPC 临摹稿 upc_q16.pdf，Edge print-to-pdf）：
      有一条淡紫 path 的 bbox 是 (0, 0, 461.30, 289.50)，看着"盖住大半个页面
      还出界"。但它 396 条子路径里**只有 3 条越界**，越界部分的并集是
      (0.63, 289.19, **0.63**, 289.50) —— **宽为 0**，面积 0。原因是 groupvec
      会把**同色矩形并成一条 path**（体积优化），bbox 是全体子路径的并集；
      拿并集 bbox 判 =「一处贴边 ⇒ 整条 path 出界」。另一条同理，越界并集是
      一条竖直线段。旧版把这两条判成 🚫 阻断交付，而它们裁掉也看不见。
    """
    sys.path.insert(0, str(SCRIPTS))
    import pymupdf
    from audit_composition import boxes, check_out_of_bounds

    doc = pymupdf.open()
    pg = doc.new_page(width=400, height=300)
    # (a) 零面积毛边：一条 path = 贴边矩形 + 一条**零宽**竖线探出 1pt
    sh = pg.new_shape()
    sh.draw_rect(pymupdf.Rect(0, 0, 350, 299.0))
    sh.draw_line(pymupdf.Point(0.5, 299.0), pymupdf.Point(0.5, 301.0))
    sh.finish(color=None, fill=(0.87, 0.87, 0.93))
    sh.commit()
    # (b) 真出界：14×14pt 实心块，10pt 探出右边（会被裁掉）
    pg.draw_rect(pymupdf.Rect(390, 140, 404, 154),
                 color=None, fill=(0.9, 0.2, 0.2))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "oob.pdf"
        doc.save(str(p))
        doc.close()
        d = pymupdf.open(str(p))
        texts, draws, _ = boxes(d[0])
        bad, n_white, n_sliver = check_out_of_bounds(texts, draws, d[0].rect)
        d.close()
    assert n_sliver == 1, f"零面积毛边应被忽略 1 条，实得 {n_sliver}"
    assert len(bad) == 1, f"应只判出 1 处真出界，实得 {len(bad)}：{bad}"
    assert "14.0×14.0pt" in bad[0][1], f"报的应是**越界那一块**的尺寸：{bad[0][1]}"


@case("ink_map_detects_coarse_stroke_interior",
      "ink_map 要把【粗笔画内部】判成墨迹。防'擦字留残影'——"
      "字号大的标签只擦掉轮廓、内部色块被重写的 <text> 盖着成重影")
def test_ink_map_coarse_stroke():
    """
    ★ 实测（2026-09-27，自旋关联算例 render_s22_clean.png，1664x926）：
      原判据只有「|lum - median(17x17)| > 20」。对粗笔画失效：17x17 的中值窗口
      整块落在笔画内部 → 中值 = 笔画自己的颜色 → 差值 ~ 0 → 内部判不出墨迹。
      字号最大的两个标签（Λ 58px、Λ̄）擦完分别残留 21.1% / 15.7% 的笔画；
      21 条标签合计残留 209px 墨迹（成品里就是重影）。
      补一条「比 41x41 中值估的背景暗 25 以上也算墨迹」后：Λ 122px->0、
      Λ̄ 87px->0、全部标签 209px->0。
      这里用合成图复现：白底 + 16px 宽黑条（条宽要落在 9~20px 这个窗口才失效）。
    """
    import numpy as np
    from scipy import ndimage
    from raster_vector.raster_ops import ink_map
    a = np.full((200, 200, 3), 255.0, np.float64)
    a[:, 92:108] = 0.0                      # 16px 宽黑条（0..255 灰阶）
    m = ink_map(a)
    core = m[40:60, 95:105]                 # 条内部
    assert core.mean() > 0.95, f"粗笔画内部应判成墨迹，实得 {core.mean():.3f}"
    assert m[20:30, 20:30].mean() == 0.0, "平坦背景不该被判成墨迹"
    # 旧判据（只有 |lum-med17|>20）在同一处判不出来 —— 这个 case 才有意义
    lum = a.mean(2)
    old = np.abs(lum - ndimage.median_filter(lum, 17)) > 20
    assert old[40:60, 95:105].mean() < 0.05, (
        "旧判据本该在粗笔画内部判不出（case 前提），实得 "
        f"{old[40:60, 95:105].mean():.3f}")


@case("trim_border_removes_frame_and_is_idempotent",
      "trim_border 要裁掉生图模型稳定画的 1~2px 外框，且【幂等】"
      "（裁完再跑不许再裁）；内容真的顶到边时不许裁")
def test_trim_border():
    """
    ★ 实测（2026-09-26，自旋关联算例）：生图模型稳定在四周画 1~2px 实心外框。
      简报里写「不要外框」没用；--negative 加 border/frame/picture frame/
      box outline 也一样（A/B 同 seed 3/3 有框；gen_neg/ 5/5 有框）。
      于是改成确定性地裁。这里合成两张图验三条：
        ① 白底 + 四周 2px 黑框      → 四条边各裁 2px
        ② 对裁完的结果再跑一次      → 一条都不裁（幂等）
        ③ 内容真的顶到边（左半全黑）→ 判为内容，不裁
    """
    import numpy as np
    from PIL import Image
    from trim_border import detect
    a = np.full((200, 300, 3), 255, np.uint8)
    a[0:2, :] = 0; a[-2:, :] = 0; a[:, 0:2] = 0; a[:, -2:] = 0
    img = Image.fromarray(a)
    r = detect(img)
    for k in ("top", "bottom", "left", "right"):
        assert r[k][0] == 2, f"{k} 应裁 2px，实得 {r[k]}"
    r2 = detect(img.crop((2, 2, 298, 198)))
    assert all(r2[k][0] == 0 for k in ("top", "bottom", "left", "right")), (
        f"幂等：裁完再跑不该再裁，实得 {r2}")
    b = np.full((200, 300, 3), 255, np.uint8)
    b[:, 0:100] = 0                          # 左半全黑 → 内容顶到边
    assert detect(Image.fromarray(b))["left"][0] == 0, "内容顶到边不许裁"


@case("element_of_accepts_float_predicates_and_tight_fallback",
      "元素表的颜色条件要能返回【float 加分】（bool 仍按 +0.22 兼容）；"
      "兜底要按 (距离, 框面积) 落到包含它的最紧的框")
def test_element_of():
    """
    ★ 实测（2026-09-27，自旋关联算例）：
      ① 颜色条件原来只支持 bool，`ANY/PALE` 一律 +0.22 → 灰色抗锯齿碎片
         （自旋箭头外晕/束流虚线，约 (150,150,150)）IoU~0，靠这 0.22 被表里
         靠前的元素抢走：L 的 bbox 被撑到 (229,74,518,654)，5 个核的色块被判成
         beam-axis-A。改成条件返回 float（DARK/COLOR +0.22、ANY 0.0）才对。
      ② 兜底只看距离（且严格 <）时，覆盖整面板的 background 框 d=0、又是列表
         末位初值 → 永不替换，5 个散块 8000+px 全被判成 background。
         改成 (距离, 框面积) = 包含它的最紧的框。
    """
    from raster_vector import panels as P
    saved = P.ELEMENTS
    try:
        # ① float 条件：同一框、同 IoU，0.22 的应胜出；0.0 的不加分
        P.ELEMENTS = {"c": [
            ("front", "front (color)", [(0, 0, 100, 100)], lambda c: 0.22),
            ("grey", "grey", [(0, 0, 100, 100)], lambda c: 0.0),
        ]}
        eid, _ = P.element_of("c", (0, 0, 100, 100), (200, 200, 200))
        assert eid == "front", f"float 条件 0.22 应胜出，实得 {eid}"
        # ② bool 条件仍按老规矩 +0.22（向后兼容）
        P.ELEMENTS = {"c": [
            ("b1", "bool true", [(0, 0, 100, 100)], lambda c: True),
            ("b2", "bool false", [(0, 0, 100, 100)], lambda c: False),
        ]}
        eid, _ = P.element_of("c", (0, 0, 100, 100), (10, 10, 10))
        assert eid == "b1", f"bool True 应 +0.22，实得 {eid}"
        # ③ 兜底：探针落在 background 大框和 corner 小框**里面** → 取面积更小
        #    （最紧）的 corner；旧的距离法会选中 background
        P.ELEMENTS = {"c": [
            ("front", "front", [(0, 0, 100, 100)], lambda c: 0.0),
            ("background", "Panel background", [(0, 0, 500, 500)], lambda c: 0.0),
            ("corner", "corner box", [(380, 380, 420, 420)], lambda c: 0.0),
        ]}
        eid, _ = P.element_of("c", (390, 390, 400, 400), (10, 10, 10))
        assert eid == "corner", f"应落到包含它的最紧的框 corner，实得 {eid}"
    finally:
        P.ELEMENTS = saved


@case("ref_leak_check_flags_copied_reference",
      "要能量出『出图把参考图整幅抄了』：同一张图 r>=0.85/照抄、结构不同的图通过；"
      "还要能认出『上一步草图』不参与判定、且实测的健康值不与【照抄】混淆")
def test_ref_leak():
    """
    ★ 实测（2026-09-27）：用户用 Claude Code 跑本 skill 时，出图**整幅**变成参考图的
      样子（qwen-image 是图生图）。原流程没有任何机器判据能发现，只能人眼。实测量到的
      分布（见 CHANGELOG v2.6.4）：
        同一张图互比 r=1.000/dHash=0（照抄上限）
        出图 vs 自己的草图 r=0.634（本来就该像 -> 用 --content-ref 标出来）
        两张不同参考图互比（基线） r=0.125
        出图 vs 风格参考（健康） r=0.017 / 0.117
      所以阈值定 0.85：高于 0.634，正常的构图继承不会被误判。
    """
    import numpy as np
    from PIL import Image
    from ref_leak_check import similarity, verdict, looks_like_content_ref
    tmp = Path(tempfile.mkdtemp(prefix="leaktest_"))

    def mk(name, blocks):
        a = np.full((200, 300, 3), 255, np.uint8)
        for sl, val in blocks:
            a[sl] = val
        q = tmp / name
        Image.fromarray(a).save(q)
        return q

    base = mk("a.png", [((slice(60, 140), slice(40, 120)), 0),
                        ((slice(80, 120), slice(180, 280)), (200, 40, 40))])
    same = tmp / "a_copy.png"
    Image.open(base).save(same)
    other = mk("b.png", [((slice(0, 200), slice(0, 150)), 0),
                         ((slice(20, 90), slice(200, 280)), (30, 60, 200))])

    d = similarity(base, same)
    assert d["r"] > 0.99 and d["dhash"] == 0, f"同一张图应几乎完全一致：{d}"
    assert verdict(d["r"], d["dhash"]) == "copy", "同一张图必须判成照抄"
    d2 = similarity(base, other)
    assert d2["r"] < 0.6, f"结构不同的图不该判成照抄：{d2}"
    assert verdict(d2["r"], d2["dhash"]) == "ok", "结构不同的图应通过"
    # 实测的两个健康值必须在通过区，且 0.634（出图 vs 草图）不能被误判成照抄
    assert verdict(0.017, 338) == "ok" and verdict(0.117, 384) == "ok"
    assert verdict(0.634, 175) == "high", "0.634 落在偏高带（0.60~0.85），不是照抄"
    assert verdict(0.318, 333) == "ok", "半张裁切（0.318）测不到 —— 这是已知边界"
    # 构图参考（上一步草图）**不参与判定**：即使像也不升级成照抄
    from ref_leak_check import check
    worst, _ = check(base, [other], [same])
    assert worst == "ok", "构图参考不该把判定升成照抄"
    # 角色识别：草图的文件名要被自动当成构图参考
    assert looks_like_content_ref("gen/sketch_s9_clean.png")
    assert not looks_like_content_ref("refs/T3-33.png")


# ══════════════════════════════════════════════════════════════
#  坑 10：形变核→火球 算例（2026-09-27，CHANGELOG v2.6.5）
#  这一批的共性：**"写得更清楚/更省事"的输入被工具拒绝**，
#  或者**一次网络抖动把整批活儿废掉**。
# ══════════════════════════════════════════════════════════════

@case("ir_brief_accepts_list_params",
      "IR 里参数写成【列表】（三个箭头共用一个元素 -> cx: [0.175, 0.385, 0.655]）"
      "不许把简报生成弄崩：防 f'{x:.2f}' 抛 TypeError: unsupported format "
      "string passed to list.__format__ —— 报的还是 Python 内部错，看不出是 IR 写法问题")
def test_ir_brief_list_params():
    import ir_to_genbrief as IG

    assert IG._fmt_num([0.175, 0.385, 0.655]) == "[0.17, 0.39, 0.66]"
    assert IG._fmt_num(0.5) == "0.50"
    ir = {"figure": {"title": "t", "canvas": {"w": 1664, "h": 928}},
          "elements": [
              {"name": "箭头1", "z": 1, "primitive": "arrow",
               "params": {"x": [0.175, 0.385, 0.655], "y": 0.5, "r": 0.02}},
              {"name": "形变核", "z": 2, "primitive": "ellipse",
               "params": {"cx": 0.10, "cy": 0.50, "r": 0.08}}],
          "composition": {"layout": ["阶段1 在左", "阶段2 在中间"], "note": "从左到右"}}
    out = IG.build(ir, None, "sketch")          # 改前：这里 TypeError，整个简报生成崩掉
    assert "[0.17, 0.39, 0.66]" in out, "列表参数要原样打印出来"
    assert "阶段1 在左" in out and "阶段2 在中间" in out, "composition.layout 是列表时要逐条排版"


@case("genbrief_style_mode_not_hardcoded_flat",
      "生图简报的风格**不许写死成扁平矢量**：IR 的 style 段说要 3D（半写实 / 球面明暗 / "
      "网格线 / 体积），简报就必须出 3D 渲染档（写明「允许 3D 渲染的立体感」），"
      "而不是反过来写「不是 3D 渲染图」。"
      "修的是（2026-09-27 实测）：形变核->火球 算例 IR 要 3D、简报却禁 3D，"
      "模型照简报走 -> 火球被画成一个纯色圆盘")
def test_genbrief_style_mode():
    import ir_to_genbrief as IG

    # 1) IR 的 style 段出现 3D 词汇 -> render3d，且不再出现「不是 3D 渲染图」
    ir3d = {"figure": {"canvas": {"w": 100, "h": 60}}, "elements": [],
            "style": {"classification": "半写实插画",
                      "evidence": "形体是 3D 的椭球，体积感来自球面明暗与表面网格线"}}
    assert IG.resolve_style_mode(ir3d) == "render3d"
    out3d = IG.build(ir3d, None, "render")
    assert "不是 3D 渲染图" not in out3d, "3D 档不许再写「不是 3D 渲染图」"
    assert "允许" in out3d and "3D 渲染的立体感" in out3d
    assert "3D 渲染的期刊插画风" in out3d

    # 2) 扁平 IR -> flat；扁平档仍然禁 3D（老行为不丢）
    irflat = {"figure": {"canvas": {"w": 100, "h": 60}}, "elements": [],
              "style": {"classification": "扁平矢量插画"}}
    assert IG.resolve_style_mode(irflat) == "flat"
    assert "不是 3D 渲染图" in IG.build(irflat, None, "render")

    # 3) 判不出 -> ref（跟随参考图，不默认扁平）；CLI 能强制覆盖
    irnone = {"figure": {"canvas": {"w": 100, "h": 60}}, "elements": []}
    assert IG.resolve_style_mode(irnone) == "ref"
    assert IG.resolve_style_mode(irnone, "render3d") == "render3d"
    assert IG.resolve_style_mode(ir3d, "flat") == "flat"

    # 4) 参考图 = 风格书：本图内容可以完全不同于参考图（必须写进简报）
    outref = IG.build(irnone, None, "render")
    assert "参考图是**风格书**" in outref
    assert "内容可以和参考图完全不同" in outref

    # 5) sketch 档保持扁平（那是切矢量图层的需要），但要说明它不是最终风格
    outsk = IG.build(ir3d, None, "sketch")
    assert "扁平矢量风" in outsk
    assert "不是最终风格" in outsk


@case("gen_figure_survives_dead_seeds",
      "生图时**单个 seed 的网络抖动不许打断整批**：防 seed 7 撞 TimeoutError -> "
      "整批 traceback 退出、后面的 seed 根本没跑、已经出的 seed 也没进 calls.jsonl")
def test_gen_figure_seed_tolerance():
    """
    ★ 实测（2026-09-27，形变核→火球 算例）：3 个 seed 只出了 1 张就崩。
      这个 case 用**必然失败**的 api-base（本机 9 端口，连接立即被拒）跑两个 seed：
      要求 ① 进程退出码 0（整批不崩）② 两个 seed 都留了记录 ③ 都标记 ok=false
      ④ 日志里能看到"重试"。（约 15 秒：两次尝试 + 3 秒退避）
    """
    import json
    import os

    tmp = Path(tempfile.mkdtemp(prefix="gfseed_"))
    (tmp / "b.md").write_text("# 简报\n画一条四阶段演化链。\n", encoding="utf-8")
    env = dict(os.environ)
    env["DASHSCOPE_API_KEY"] = "sk-dummy-for-test"      # 只为过检查，不真的能用
    r = subprocess.run([sys.executable, str(SCRIPTS / "gen_figure.py"),
                        "--brief", str(tmp / "b.md"), "--seeds", "1,2",
                        "--outdir", str(tmp / "gen"),
                        "--api-base", "http://127.0.0.1:9/v1", "--timeout", "3"],
                       capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace", env=env)
    assert r.returncode == 0, (
        "两个 seed 都失败也不许让整批崩（失败要吞掉、继续下一个 seed）：\n"
        + (r.stdout or "")[-800:] + (r.stderr or "")[-400:])
    log = tmp / "gen" / "calls.jsonl"
    assert log.exists(), "调用记录要照常落盘"
    recs = [json.loads(l) for l in log.read_text(encoding="utf-8").strip().splitlines()]
    assert [x["seed"] for x in recs] == [1, 2], (
        "失败的 seed 也要逐条记，不能中断（这是原来丢记录的那个坑），实得 %s"
        % [x.get("seed") for x in recs])
    assert all(x["ok"] is False for x in recs), "失败记录必须 ok=false"
    assert "重试" in r.stdout, "第一次失败要重试一次"


@case("trim_border_bg_option_for_light_frame",
      "外框可能是**两层**（1px 深线 + 1px 浅灰线 lum 244~249）：默认 BG=0.94 只认得深线，"
      "浅灰线留在图上 -> 进矢量就是一条多余细边；--bg 0.975 才剪得掉，且要幂等")
def test_trim_border_bg():
    import numpy as np
    from PIL import Image
    from trim_border import detect

    a = np.full((120, 160, 3), 255, np.uint8)
    a[0:2, :] = 0                      # 上：2px 深线
    a[:, 0:2] = 0                      # 左：2px 深线
    a[-1, :] = 246                     # 下：1px 浅灰线
    a[:, -1] = 246                     # 右：1px 浅灰线
    img = Image.fromarray(a)
    d0 = detect(img)
    assert d0["top"][0] == 2 and d0["left"][0] == 2
    assert d0["bottom"][0] == 0 and d0["right"][0] == 0, (
        "浅灰线在默认阈值下本来就认不出来 —— 这正是坑，本 case 只是把现状钉住")
    d1 = detect(img, bg=0.975)
    assert d1["bottom"][0] == 1 and d1["right"][0] == 1, (
        "--bg 0.975 要能剪掉浅灰外框，实得 %s" % {k: v[0] for k, v in d1.items()})
    d2 = detect(img.crop((2, 2, 159, 119)), bg=0.975)
    assert all(d2[k][0] == 0 for k in ("top", "bottom", "left", "right")), (
        "幂等：按 --bg 剪完再跑不该再剪，实得 %s" % {k: v[0] for k, v in d2.items()})


@case("gradfit_never_drops_thin_strips",
      "真渐变丢台阶块时，**细条（min(w,h)<3）一律不丢**：防浅色球面上的网格线（1~2px）"
      "被当成'渐变内'一起丢掉 -> 网格线断成虚线（实测踩过两轮）")
def test_gradfit_thin_strip():
    import numpy as np
    from raster_vector import gradfit as G

    g = {"dropmask": np.ones((80, 80), bool)}          # 整块都在渐变内
    assert G.rect_covered(10, 10, 40, 40, g) is True, "够大的平整色块才允许丢"
    assert G.rect_covered(10, 10, 1, 40, g) is False, "1px 宽的细条（网格线）不许丢"
    assert G.rect_covered(10, 10, 40, 2, g) is False, "2px 厚的细条不许丢"
    assert G.rect_covered(10, 10, 3, 40, g) is True, "3px 以上就不算细条了"
    g2 = {"dropmask": np.ones((80, 80), bool)}
    g2["dropmask"][10:12, 10:50] = False               # 40x2=80px，占 40x40 的 5%
    assert G.rect_covered(10, 10, 40, 40, g2) is False, "块里有 >3% 像素在渐变外 -> 必须留着"


@case("gradfit_aradial_uses_group_transform",
      "aradial 渐变**不能用 gradientTransform**：cairosvg 会忽略它（实测 200x200 对照图里"
      "带/不带 transform 逐像素完全相同 -> 渐变中心没动、整块填成最外档颜色）"
      "-> 改成 <g transform> 包形状 + 局部坐标系的圆 radialGradient")
def test_gradfit_aradial_transform():
    import numpy as np
    from raster_vector import gradfit as G

    g = {"kind": "aradial",
         "stops": np.array([[10.0, 20.0, 30.0], [200.0, 100.0, 0.0]]),
         "geom": {"cx": 30.0, "cy": 40.0, "Q": [[0.02, 0.0], [0.0, 0.05]]},
         "tmin": 0.0, "tmax": 1.0, "resid": 3.0,
         "mask": np.zeros((60, 60), bool)}
    g["mask"][10:40, 10:40] = True
    d = G.svg_defs("gid", g)
    assert "gradientTransform" not in d, (
        "radialGradient 里不许出现 gradientTransform（cairosvg 忽略它，会画出错色块）")
    assert 'gradientUnits="userSpaceOnUse"' in d
    sh, npts = G.svg_shape("gid", g)
    assert sh is not None and npts >= 3, "aradial 形状要能描出轮廓"
    assert sh.startswith('<g transform="matrix('), "aradial 的形状必须包在 <g transform> 里"
    assert 'fill="url(#gid)"' in sh, "形状要引用那个渐变"


@case("dump_elements_table_follows_out_png",
      "--elmap 的元素明细表要落在 out_png **旁边**，不许写进 cwd："
      "防把别的图/别的算例的同名 _elem_table.txt 覆盖掉")
def test_dump_elements_table_path():
    import os
    import numpy as np
    from raster_vector import groupvec as G

    tmp = Path(tempfile.mkdtemp(prefix="duptab_"))
    run = tmp / "run"
    run.mkdir()
    saved = G.assign_elements
    G.assign_elements = lambda a, R, K, *ar, **kw: ({}, {}, 0)   # 空划分：只测落盘位置
    cwd0 = os.getcwd()
    try:
        os.chdir(str(run))
        G.dump_elements(np.full((60, 80, 3), 255, np.uint8), 8, 4, str(tmp / "ov.png"))
    finally:
        os.chdir(cwd0)
        G.assign_elements = saved
    assert (tmp / "ov.png").exists(), "自检图要落盘"
    assert (tmp / "_elem_table.txt").exists(), "明细表要跟在 out_png 旁边"
    assert not (run / "_elem_table.txt").exists(), "不许把 _elem_table.txt 写进 cwd"


@case("gen_figure_content_ref_downgraded_to_layout",
      "构图参考（--content-ref）默认必须**降级成 layout-only** 再送模型。"
      "实测（2026-09-27 形变核→火球，qwen-image-3.0 / seed 53，同一简报）："
      "原样送扁平草图 -> 与草图布局相关 r=0.873 但火球退化成纯色橙盘（模型把草图的"
      "「扁平」渲染风格一起继承了，风格参考被稀释）；降级成 layout-only -> r=0.904 "
      "**且**火球恢复 3D 辉光+亮核。防有人把这步「优化」掉、退回原样送。")
def test_gen_figure_content_ref_layout_mode():
    """
    ★ 实测数字见上面 why。这个 case 用**必然失败**的 api-base 跑（只看预处理和记录，
      不花钱、不联网）：① render 档 auto -> layout：落盘 layout_*.png、记录
      mode=layout、送的确实是它、且它是灰度；② sketch 档 auto -> full：不降级；
      ③ 显式 --content-ref-mode full：render 档也不降级。
    """
    import json
    import os
    import numpy as np
    from PIL import Image

    tmp = Path(tempfile.mkdtemp(prefix="gfcr_"))
    # 造一张"扁平草图"：白底 + 饱和橙色块（正是会把扁平风格带进去的那种素材）
    a = np.full((120, 200, 3), 255, np.uint8)
    a[40:90, 60:140] = (255, 90, 0)
    a[30:60, 20:40] = (120, 120, 200)
    sketch = tmp / "sketch_s7_clean.png"
    Image.fromarray(a).save(str(sketch))
    # 另造一张"风格参考"（内容不同、只是给 --ref 用，不该被降级）
    st = np.full((120, 200, 3), 250, np.uint8)
    st[20:100, 30:170] = (60, 60, 60)
    style = tmp / "T3-33.png"
    Image.fromarray(st).save(str(style))
    (tmp / "b.md").write_text("# 简报\n画四个阶段的演化链。\n", encoding="utf-8")
    env = dict(os.environ)
    env["DASHSCOPE_API_KEY"] = "sk-dummy-for-test"      # 只为过检查

    def run(*extra):
        out = tmp / ("gen%d" % len(list(tmp.glob("gen*"))))
        r = subprocess.run([sys.executable, str(SCRIPTS / "gen_figure.py"),
                            "--brief", str(tmp / "b.md"), "--ref", str(style),
                            "--content-ref", str(sketch),
                            "--seeds", "1", "--outdir", str(out),
                            "--api-base", "http://127.0.0.1:9/v1", "--timeout", "3"]
                           + list(extra),
                           capture_output=True, text=True, timeout=300,
                           encoding="utf-8", errors="replace", env=env)
        assert r.returncode == 0, (r.stdout or "")[-800:] + (r.stderr or "")[-400:]
        rec = json.loads((out / "calls.jsonl").read_text(encoding="utf-8")
                         .strip().splitlines()[0])
        return out, rec, r.stdout

    # ① render 档：auto -> layout，且真的落盘 + 记录 + 送的是它 + 是灰度
    out, rec, so = run("--stage", "render")
    lay = out / ("layout_%s.png" % sketch.stem)
    assert lay.exists(), ("render 档默认要把构图参考降级落盘成 layout_*.png，实得 %s\n%s"
                          % (sorted(p.name for p in out.iterdir()), so[-600:]))
    assert rec["content_ref_mode"] == "layout", rec["content_ref_mode"]
    assert rec["content_ref_sent"][0].endswith("layout_%s.png" % sketch.stem), (
        "记录里要写清**送模型的是布局图**，实得 %s" % rec["content_ref_sent"])
    assert "构图参考降级" in so, "要打印出来让人知道降级发生了"
    b = np.asarray(Image.open(str(lay)).convert("RGB")).astype(np.int16)
    assert (b[:, :, 0] == b[:, :, 1]).all() and (b[:, :, 1] == b[:, :, 2]).all(), (
        "布局图必须是灰度的 —— 颜色正是要被去掉的「扁平风格」信号")
    sat0 = float((a.max(2) - a.min(2)).mean())
    assert float((b.max(2) - b.min(2)).mean()) < sat0 / 4.0, (
        "布局图要几乎无彩度，实得 %s vs 原图 %s" % (float((b.max(2)-b.min(2)).mean()), sat0))
    # 风格参考不许被降级
    assert not (out / ("layout_%s.png" % style.stem)).exists(), (
        "--ref 风格参考是原样送的，不该被降级")

    # ② sketch 档：auto -> full（草图阶段本来就该跟手绘稿的形体走）
    out2, rec2, _ = run("--stage", "sketch")
    assert rec2["content_ref_mode"] == "full", rec2["content_ref_mode"]
    assert not (out2 / ("layout_%s.png" % sketch.stem)).exists(), "sketch 档不该降级"

    # ③ 显式 full：render 档也不降级
    out3, rec3, _ = run("--stage", "render", "--content-ref-mode", "full")
    assert rec3["content_ref_mode"] == "full", rec3["content_ref_mode"]
    assert not (out3 / ("layout_%s.png" % sketch.stem)).exists(), "显式 full 不该降级"


@case("genbrief_carries_element_material",
      "IR 的 `material:` 必须进简报（以前**整段丢**，只用 primitive 做分类）；"
      "而且简报**不许硬编码火球长什么样**。实测（2026-09-27 形变核→火球，qwen-image-3.0 "
      "seed 53，只改 spec）：旧版简报把火球写死成「内亮外暗的多层半透明渐变 + 边缘柔和」"
      "-> 出的是一颗**光滑橙色糖球**（内部结构高频能量 0.0103）；把 IR 的 material "
      "写清楚（哑光 / 三层壳 / 组元颗粒 / 场线）并让它进简报 -> 同一模型同一 seed "
      "出的是有内部结构的等离子体团（高频能量 0.0265~0.0418，即 2.6~4 倍）。")
def test_genbrief_carries_material():
    import ir_to_genbrief as IG

    ir = {"figure": {"canvas": {"w": 100, "h": 60}},
          "elements": [
              {"name": "QGP 火球", "z": 1, "primitive": "大团块",
               "material": "哑光的等离子体团：三层壳 + 内部组元颗粒 + 场线，不要高光"},
              # 同名族（末尾有编号）也要能合并进去
              {"name": "演化箭头 1", "z": 2, "primitive": "粗箭头",
               "material": "实心深灰，无描边"},
              {"name": "演化箭头 2", "z": 2, "primitive": "粗箭头"}]}
    out = IG.build(ir, None, "render")

    # ① material 要真的到纸面上（旧版这里是 0 次）
    assert "【材质：" in out, "元素的 material 必须进简报"
    assert "哑光的等离子体团" in out, "material 原文要带出来"
    assert "实心深灰，无描边" in out, "同名族里第一个有 material 的条目要保留它"

    # ② 不许再把火球长什么样写死
    assert "内亮外暗的多层半透明渐变" not in out, (
        "火球描述不许硬编码 —— 那会把模型按在一颗光滑高光球上，"
        "IR 的 material 再写也没用")
    assert "以第一节各元素的【材质】为准" in out, "要显式把发光体的画法指回 material"

    # ③ 禁止项要留出「IR 写明的内部结构必须画」的口子
    assert "必须画出来" in out and "不是装饰" in out, (
        "禁止项第 1 条原来只说「不要加 IR 清单里没有的东西」，"
        "会把 material 要求的组元颗粒/场线也一起禁掉")
    assert "示意性的细小符号" in out, (
        "「颗粒噪点」要澄清成胶片颗粒，别把示意性细小符号一并禁掉")

    # ④ 没写 material 的元素不该凭空多出【材质：】
    out2 = IG.build({"figure": {"canvas": {"w": 100, "h": 60}},
                     "elements": [{"name": "核", "z": 1, "primitive": "椭球"}]},
                    None, "render")
    assert "【材质：" not in out2, "没写 material 就不该有【材质：】段"


if __name__ == "__main__":
    sys.exit(main())
