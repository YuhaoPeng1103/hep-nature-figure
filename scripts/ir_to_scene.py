#!/usr/bin/env python3
"""
ir_to_scene —— 从 IR 生成可运行的构图骨架
=========================================================================
解决的问题：IR 里的 `params` 原来是**中文散文**
（`"约 0.34 画布宽"`、`"偏向右上，距介质中心约 0.21 介质半径"`），
于是 IR → 图这一步无法自动化，每张草图都要人从零写一个 250–300 行脚本。

这跟当年 `geometry_constraints` 遇到的是**同一个问题**，同一种修法：
把模糊描述逼成**可执行的数值**。

现在 IR 的 `elements[]` 要求：
  · `primitive` —— 必须是 `cartoon_lib.PRIMITIVES` 里的注册名
  · `params`    —— 扁平数值字典，坐标用**归一化值**

归一化约定（关键，写 IR 时必须遵守）：
  · 位置 `cx` / `cy` ∈ [0,1]，分别乘画布 宽 / 高
  · 尺寸 `R` / `r` / `rx` / `ry` / `w` / `h` ∈ [0,1]，乘画布**宽**
  · 其余参数（`seed` / `n` / `ry` 这类比值）原样传递

生成的骨架是**可直接运行**的 Python：坐标已换算好，图元调用已按 z 序排好，
图层已开好。人/AI 只需要补细节（颜色、额外的装饰元素），不用再从零搭。

用法：
    python3 ir_to_scene.py ir/sketch5_upc.ir.yaml -o build_upc.py
    python3 ir_to_scene.py ir/sketch5_upc.ir.yaml --check   # 只校验 IR 合不合规
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cartoon_lib import PRIMITIVES  # noqa: E402

# ══════════════════════════════════════════════════════════════
#  单位声明：**按图元**声明每个参数是什么单位
#
#  ★ 为什么不能按参数名一刀切：实测踩到——
#      `ry` 在 `qgp_blob` 里是**扁平比**（比值，0.78），
#      在 `lorentz_nucleus` 里是**纵向半径**（尺寸，0.13）。
#      按名字一刀切会把扁平比也乘上画布高，生成 `ry=499.2` 这种垃圾。
#    所以必须逐图元声明。
#
#  单位取值：
#    'x'     位置横坐标，×画布宽      'y'     位置纵坐标，×画布高
#    'size_w' 尺寸（横向），×画布宽    'size_h' 尺寸（纵向），×画布高
#    'ratio'  比值 / 计数 / 开关，原样传递
# ══════════════════════════════════════════════════════════════
PARAM_UNITS = {
    "qgp_blob":        {"cx": "x", "cy": "y", "R": "size_w",
                        "ry": "ratio", "seed": "ratio", "n_spots": "ratio",
                        "glow": "ratio", "wobble": "ratio",
                        "edge_w": "ratio"},
    "qgp_fireball":    {"cx": "x", "cy": "y", "r": "size_w",
                        "vortices": "ratio"},
    "lorentz_nucleus": {"cx": "x", "cy": "y", "rx": "size_w",
                        "ry": "size_h", "shift": "size_w",
                        "sep": "ratio", "n_stripes": "ratio"},
    "nucleus_cluster": {"cx": "x", "cy": "y", "R": "size_w",
                        "seed": "ratio", "n": "ratio"},
    "shaded_sphere":   {"cx": "x", "cy": "y", "r": "size_w",
                        "n_lon": "ratio", "n_lat": "ratio"},
    "hard_vertex":     {"x": "x", "y": "y", "r": "size_w", "n": "ratio"},
    "jet":             {"x0": "x", "y0": "y", "x1": "x", "y1": "y",
                        "w0": "ratio", "w1": "ratio"},
    "gluon_radiation": {"x0": "x", "y0": "y", "x1": "x", "y1": "y",
                        "n": "ratio", "seed": "ratio", "amp": "ratio"},
    "medium_wake":     {"x0": "x", "y0": "y", "x1": "x", "y1": "y",
                        "n": "ratio", "r0": "ratio", "dr": "ratio"},
    "arrow":           {"x1": "x", "y1": "y", "x2": "x", "y2": "y",
                        "w": "ratio", "head": "ratio"},
    "tapered_arrow":   {"x1": "x", "y1": "y", "x2": "x", "y2": "y",
                        "w": "ratio", "curve": "ratio"},
    "radial_rays":     {"cx": "x", "cy": "y", "R": "size_w", "n": "ratio",
                        "inner": "ratio", "width": "ratio",
                        "phase": "ratio", "glow_core": "ratio"},
    "radial_arrows":   {"cx": "x", "cy": "y", "R": "size_w", "n": "ratio",
                        "r_in": "ratio", "r_out": "ratio", "ry": "ratio",
                        "w": "ratio"},
    "poisson_discs":   {"cx": "x", "cy": "y", "n": "ratio",
                        "d_min": "size_w", "d_max": "size_w",
                        "ry": "ratio", "seed": "ratio", "r_scale": "ratio"},
    "light_cone":      {"ox": "x", "oy": "y", "L": "size_w",
                        "slope": "ratio", "width": "ratio"},
    "proper_time_family": {"ox": "x", "oy": "y", "width": "ratio"},
    "backplate":       {"cx": "x", "cy": "y", "w": "size_w",
                        "h": "size_h", "tilt": "ratio"},
    "cast_shadow":     {"cx": "x", "cy": "y", "rx": "size_w", "ry": "size_w",
                        "height": "ratio", "opacity": "ratio",
                        "blur": "ratio"},
    "contact_shadow":  {"cx": "x", "cy": "y", "rx": "size_w", "ry": "size_w",
                        "opacity": "ratio", "blur": "ratio"},
    "label":           {"x": "x", "y": "y", "size": "ratio"},
}

# 兜底：没在 PARAM_UNITS 里声明的图元/参数，按名字猜
_FALLBACK = {}
for _k in ("x", "x0", "x1", "x2", "cx", "ox", "VX"):
    _FALLBACK[_k] = "x"
for _k in ("y", "y0", "y1", "y2", "cy", "oy", "VY"):
    _FALLBACK[_k] = "y"
for _k in ("R", "r", "rx", "w", "L", "d_min", "d_max", "width",
           "r_in", "r_out", "glow_core", "inner", "amp"):
    _FALLBACK[_k] = "size_w"
for _k in ("ry", "h"):
    _FALLBACK[_k] = "size_h"
# 原样传递（比值 / 计数 / 开关）
PASSTHRU = {"seed", "n", "n_spots", "n_stripes", "sep", "shift", "tilt",
            "wobble", "glow", "vortices", "slope", "phase", "amp", "curve",
            "bold", "anchor", "color", "weight", "cjk", "palette", "ry_ratio"}
# 明确不认识的键报错而不是静默丢弃


def load_ir(path: Path) -> dict:
    """
    读 IR。优先 PyYAML；没有 PyYAML 时退到 JSON
    （IR 是机器生成的，转 JSON 无损——受限环境里请把 IR 存成 .json）。
    """
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit(
            f"读不了 {path.name}：环境里没有 PyYAML，而文件也不是 JSON。\n"
            f"  装：pip install pyyaml\n"
            f"  或在受限环境里把 IR 存成 .json（IR 是机器生成的，转换无损）。")


def normalise_params(prim: str, raw: dict, W: float, H: float):
    """
    归一化参数字典 → 像素参数字典。单位**按图元声明**查（见 PARAM_UNITS）。
    返回 (像素参数, 未声明的键)。
    """
    units = PARAM_UNITS.get(prim, {})
    out, unknown = {}, []
    for k, v in (raw or {}).items():
        if not isinstance(v, (int, float)):
            out[k] = v
            continue
        u = units.get(k) or _FALLBACK.get(k)
        if u is None:
            out[k] = v
            unknown.append(k)
        elif u == "x":
            out[k] = round(v * W, 1)
        elif u == "y":
            out[k] = round(v * H, 1)
        elif u == "size_w":
            out[k] = round(v * W, 1)
        elif u == "size_h":
            out[k] = round(v * H, 1)
        else:                       # ratio：原样
            out[k] = v
    return out, unknown


def _signature(prim):
    """取图元函数的参数名集合（不含 self）。"""
    import inspect
    from cartoon_lib import Cartoon
    fn = getattr(Cartoon, prim, None)
    if fn is None:
        return None
    try:
        return set(inspect.signature(fn).parameters) - {"self"}
    except (TypeError, ValueError):
        return None


def check(ir: dict, name: str) -> list:
    """校验 IR 是否已『可执行化』。返回问题列表。"""
    problems = []
    if "elements" not in ir:
        problems.append("IR 里没有 elements 段")
        return problems
    for e in ir["elements"]:
        eid = e.get("id", "?")
        prim = e.get("primitive", "")
        if prim not in PRIMITIVES:
            problems.append(
                f"{eid} 的 primitive=`{prim}` 不在注册表里。"
                f"可用的：{', '.join(sorted(PRIMITIVES))}")
        else:
            # ★ 参数名必须真的在这个图元的签名里。
            #   实测踩到：jet 的签名是 (x0,y0,x1,y1)，IR 里写成 (x1,y1,x2,y2)
            #   → 生成出来的调用会 TypeError。这类错必须在生成【之前】报出来，
            #   否则"骨架能生成"会给人"IR 没问题"的错觉。
            sig = _signature(prim)
            if sig:
                given = set((e.get("params") or {}).keys())
                for k in given:
                    if k not in sig:
                        near = ", ".join(sorted(sig))[:88]
                        problems.append(
                            f"{eid}.params.{k} 不是 {prim}() 的参数。"
                            f"该图元接受：{near}")
                # ★ 必填参数漏了也要查。实测：IR 里没写 shaded_sphere 的
                #   `base`，--check 放行，生成的骨架跑到一半才 TypeError。
                #   "参数名对得上"不等于"调用能成立"。
                import inspect
                from cartoon_lib import Cartoon
                try:
                    ps = inspect.signature(getattr(Cartoon, prim)).parameters
                    missing = [n for n, prm in ps.items()
                               if n != "self"
                               and prm.default is inspect.Parameter.empty
                               and prm.kind in (prm.POSITIONAL_OR_KEYWORD,
                                                prm.KEYWORD_ONLY)
                               and n not in given]
                    if missing:
                        problems.append(
                            f"{eid} 缺 {prim}() 的必填参数：{', '.join(missing)}"
                            f"（生成出来会 TypeError）")
                except (TypeError, ValueError):
                    pass
        params = e.get("params") or {}
        for k, v in params.items():
            if isinstance(v, str) and any(
                    ch in v for ch in "约大概左右画布宽倍的，、"):
                problems.append(
                    f"{eid}.params.{k} 是散文（`{v}`）——需要可执行数值。"
                    f"坐标用归一化 [0,1]，尺寸也归一化到画布宽")
        if e.get("physics_role") in (None, "", "装饰"):
            problems.append(f"{eid} 缺 physics_role（不能是'装饰'）")
    return problems


def generate(ir: dict, name: str, W: float, H: float) -> str:
    """按 z 序生成构图骨架。"""
    elems = sorted(ir["elements"], key=lambda e: e.get("z", 0))
    L = [
        "#!/usr/bin/env python3",
        f'"""由 ir_to_scene.py 从 IR 生成 —— {name}',
        "",
        "坐标已从 IR 的归一化值换算好，图元调用已按 z 序排好。",
        "补细节（颜色/装饰/标注）之后即可运行。",
        f'"""',
        "import sys",
        "from pathlib import Path",
        "",
        'sys.path.insert(0, str(Path(__file__).parent / "hep-nature-figure" / "scripts"))',
        "from cartoon_lib import Cartoon",
        "",
        f"W, H = {W:.0f}, {H:.0f}",
        "",
        "",
        "def main():",
        "    c = Cartoon(W, H)",
        "",
    ]
    for e in elems:
        eid = e.get("id", "?")
        prim = e["primitive"]
        role = (e.get("physics_role") or "").strip().splitlines()
        role = role[0][:60] if role else ""
        args, unknown = normalise_params(prim, e.get("params"), W, H)

        L.append(f"    # ── {eid} {e.get('name','')}（z={e.get('z','?')}）"
                 f"{(chr(10) + '    #    ' + role) if role else ''}")
        L.append(f'    c.begin_layer("{eid}", "{eid} {e.get("name","")}")')
        argstr = ", ".join(
            f'{k}={v!r}' if not isinstance(v, str) else f'{k}={v!r}'
            for k, v in args.items())
        L.append(f"    c.{prim}({argstr})")
        L.append("    c.end_layer()")
        if unknown:
            L.append(f"    # ⚠️ 未识别的参数键（请确认单位）：{unknown}")
        L.append("")

    # ★ 输出名跟 IR 走，不要写死 "fig"。
    #   实测踩到：生成出来的成品叫 fig.svg / fig.png / fig.pdf，
    #   和目录里别的东西混在一起根本认不出是哪个任务的产物。
    #   IR 叫什么，产物就叫什么。
    L += [
        f'    c.save("{name}.svg")',
        f'    c.render("{name}.png", width=1900)',
        f'    c.render("{name}.pdf")',
        f'    print("已输出 {name}.svg / {name}.png / {name}.pdf")',
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
    ]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ir")
    ap.add_argument("-o", "--out", help="输出的骨架脚本")
    ap.add_argument("--check", action="store_true", help="只校验 IR，不生成")
    ap.add_argument("--size", default="1020x640", help="画布 WxH，默认 1020x640")
    ap.add_argument("--canvas", action="store_true",
                    help="同时写一份画布尺寸的 JSON 供参考")
    a = ap.parse_args()

    p = Path(a.ir)
    ir = load_ir(p)
    # 输出名去掉 .yaml/.json，也去掉常见的 .ir / .exec 后缀
    # （否则 T2b_NEW_deformation.ir.yaml 会产出 "T2b_NEW_deformation.ir.png"）
    name = p.stem
    for suf in (".exec", ".ir"):
        if name.endswith(suf):
            name = name[: -len(suf)]
    probs = check(ir, name)

    print(f"IR: {p}")
    print(f"元素 {len(ir.get('elements', []))} 个"
          f" | 图层 {len({e.get('z') for e in ir.get('elements', [])})} 层")
    if probs:
        print(f"\n❌ {len(probs)} 处不合规 —— IR 尚未『可执行化』：")
        for x in probs[:20]:
            print(f"   · {x}")
        print("\n   修法见 references/ir-spec.md 的「params 可执行化」一节。")
        if a.check:
            return 1
    else:
        print("✅ IR 合规")

    if a.check:
        return 0

    # ★ 画布尺寸优先读 IR 里声明的（figure.canvas），否则用 --size。
    #   实测踩到：IR 写了 canvas 1400×560，生成器却用默认 1020×640 ——
    #   归一化的 rx/ry 乘到不同画布上，**形变核的长短轴比从 1.86 缩成 1.18**，
    #   而"核是形变的不是球"正是那张图的物理要点。
    #   画布尺寸会改变物理观感，所以它必须来自 IR 而不是命令行默认值。
    W, H = (float(x) for x in a.size.lower().split("x"))
    cv = (ir.get("figure") or {}).get("canvas")
    if isinstance(cv, dict) and cv.get("w") and cv.get("h"):
        W, H = float(cv["w"]), float(cv["h"])
        print(f"画布: {W:.0f}×{H:.0f}（取自 IR 的 figure.canvas）")
    else:
        print(f"画布: {W:.0f}×{H:.0f}（IR 未声明 canvas，用 --size）")

    src = generate(ir, name, W, H)
    out = Path(a.out) if a.out else Path(f"build_{name}.py")
    out.write_text(src, encoding="utf-8")
    print(f"\n已生成骨架：{out}  （{len(src.splitlines())} 行）")
    print(f"   补完细节后：python3 {out}")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main())
