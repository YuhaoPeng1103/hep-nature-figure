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


if __name__ == "__main__":
    sys.exit(main())
