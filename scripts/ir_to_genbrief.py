#!/usr/bin/env python3
"""
ir_to_genbrief —— IR → 给图像生成模型的**约束简报**
=========================================================================
## 两条路径（2026-09-20 定型）

    路径 1（基础）
      草图/描述 ──生图──▶ 【更好的草图】 ──绘画──▶ 矢量
                                    ↑
                        这一步只求"构图清晰、元素齐全"，
                        不追求质感；质感由最后的绘画那步负责

    路径 2（在路径 1 基础上加一段）
      草图/描述 ──生图──▶ 更好的草图 ──检查──▶ 成品位图 ──绘画──▶ 矢量

★ 为什么把生图的产物定位成"**更好的草图**"而不是"成品"：
  成品一旦出来，下一步就变成**照抄**，位图里的物理错误会被一起抄进矢量。
  定位成草图 → 绘画那步仍要按 IR 的 `geometry_constraints` **正确地执行**，
  物理约束留在了它该在的位置。

## 用法

## 用法

    python3 ir_to_genbrief.py ir/sketch6_spin_polarization.ir.yaml
    python3 ir_to_genbrief.py ir/xxx.ir.yaml --style-profile ../assets/style-profiles.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 图像生成模型最常犯的错——写进"禁止项"，比事后修便宜
COMMON_FAILURES = [
    "**不要添加 IR 元素清单里没有的东西**。模型最爱加装饰性的光晕、粒子、星星、"
    "多余箭头——那些会被带进矢量，且违背物理内容。",
    "**文字不要画错**。位图里的文字只当占位（下一步会重写成真 `<text>`），"
    "但拼写和数字必须对，否则临摹时会照抄错值。",
    "**不要改视角或投影**。IR 里写了视角约定就照办；换视角会让几何约束全部失效。",
    "**不要画成照片级**。目标是**矢量插画风**（干净的形体 + 明确的描边），"
    "不是 3D 渲染图、不是写实材质。",
    "**不要加渐变背景、光斑、镜头光晕**这些摄影感的东西。",
]


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


def load_style(profile_path, want_class):
    """从风格档案里抽可执行的风格规则（不是统计数字，是能照着画的规则）。"""
    if not profile_path:
        return None
    p = Path(profile_path)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    ent = d.get(want_class) if want_class else None
    if ent is None:
        ent = d.get("T3-schematic (illustration)") or d[list(d)[0]]
    st = ent.get("style", {})
    pal = st.get("palette") or []
    return {
        "class": ent.get("name", want_class or "?"),
        "n_sources": ent.get("n_sources"),
        "palette": pal[:8],
        "whitespace": st.get("whitespace", {}).get("median"),
        "stroke_width": st.get("stroke_width_est", {}).get("median"),
    }


def build(ir: dict, style: dict | None, stage: str = "sketch") -> str:
    fig = ir.get("figure", {})
    elems = sorted(ir.get("elements", []), key=lambda e: e.get("z", 0))
    cv = fig.get("canvas") or {}
    W, H = cv.get("w", 1400), cv.get("h", 560)

    L = []
    if stage == "sketch":
        L.append("【任务】把下面这份物理构图**画成一张清晰的草图稿**。")
        L.append("")
        L.append("★ 这一步**只求构图对、元素齐、位置准**，")
        L.append("  **不要求质感、光影、渲染效果** —— 那些下一步做。")
        L.append("  把它当成『给画师看的构图稿』：布局一眼能看懂，")
        L.append("  每个元素是什么、在哪、多大，一目了然。")
    else:
        L.append("【任务】按下面这份构图，出一张**高质量成品位图**。")
        L.append("")
        L.append("★ 这一步要求**质感和光影到位**（上一步只出了构图稿）。")
        L.append("  但仍然：形体要清楚可辨认，不要靠模糊和噪点营造氛围 ——")
        L.append("  因为下一步还要把它转成矢量。")
    L.append("")
    L.append("★ **必须随本简报一起，把风格参考图传给模型**"
             "（`gen_figure.py --ref 参考图.png`，可多张）。")
    L.append("  只给文字 → 出来一定是「通用插画脸」。参考图（如 Nature 正刊的同类示意图）"
             "让模型做的是『改风格』而不是『猜构图』。")
    L.append("")
    L.append(f"画布比例：{W}×{H}（宽高比 {W/H:.2f}）。白底。")
    L.append("")

    # ── 物理内容（不许改）──
    L.append("═══ 一、物理内容（这是图要表达的东西，不许改）═══")
    claim = (fig.get("physics_claim") or "").strip()
    if claim:
        L.append(claim)
    L.append("")
    # ★ 不能把 IR 的元素逐个倒出来。
    #   可执行 IR 里是**实现元素**（每个投影、每个自旋记号、每个标签各一条），
    #   而图像模型要的是**语义内容**（"六个 Λ，自旋全部同向"）。
    #   实测：直接倒出来是 36 条，全是噪声，模型没法用。
    #   所以按 primitive 分类 + 按名族合并。
    SHADOW_PRIMS = {"cast_shadow", "contact_shadow"}
    ANNOT_PRIMS = {"label"}
    content, annots, has_shadow = [], [], False
    for e in elems:
        prim = e.get("primitive", "")
        if prim in SHADOW_PRIMS:
            has_shadow = True
        elif prim in ANNOT_PRIMS:
            annots.append(e)
        else:
            content.append(e)

    # 按"名族"合并（去掉名字末尾的序号/数字）
    def family(name):
        # 去掉名字末尾的编号：支持 "自旋 2" / "自旋 1-6" / "自旋 1~6" 这些写法
        return re.sub(r"[\s\-—~～至]*[\d]+([\-—~～至][\d]+)?\s*$", "",
                      str(name)).strip()

    families, seen = [], {}
    for e in content:
        f = family(e.get("name", ""))
        role = " ".join((e.get("physics_role") or "").split())
        if f in seen:
            seen[f]["n"] += 1
            # 只在原 role 更实质时补充
            if role and not role.startswith(("同", "同上")) and len(role) > len(seen[f]["role"]):
                seen[f]["role"] = role
        else:
            entry = {"n": 1, "role": role if not role.startswith(("同", "同上")) else ""}
            seen[f] = entry
            families.append((f, entry))

    L.append("图中要出现的**物理对象**（数量要对，但不能把实现细节当内容）：")
    for f, info in families:
        cnt = f" ×{info['n']}" if info["n"] > 1 else ""
        L.append(f"  · {f}{cnt}" + (f" —— {info['role']}" if info["role"] else ""))
    if has_shadow:
        L.append("  · （各主要形体带**柔和的投影与接触阴影**，让它们看起来是浮在纸面上"
                 "而不是贴上去的）")
    L.append("")

    if annots:
        L.append("图中**文字**（拼写和数值必须完全正确 —— 下一步会重写成真正的矢量文字，"
                 "现在画错就会被照抄）：")
        for e in annots:
            txt = (e.get("params") or {}).get("t")
            if txt:
                L.append(f'  · "{txt}"')
        L.append("")
    L.append("")

    # ── 构图 ──
    layout = (ir.get("composition") or {}).get("layout")
    note = (ir.get("composition") or {}).get("note")
    if layout:
        L.append("═══ 二、构图 ═══")
        L.append(f"布局：{layout}")
        if note:
            L.append(" ".join(str(note).split()))
        L.append("")
        L.append("各元素位置（相对画布，x 从左 0→1，y 从上 0→1）：")
        for e in elems:
            p = e.get("params") or {}
            x = p.get("cx", p.get("x", p.get("x1")))
            y = p.get("cy", p.get("y", p.get("y1")))
            if x is None or y is None:
                continue
            size = p.get("R", p.get("r", p.get("rx")))
            s = f"  位置 ({x:.2f}, {y:.2f})"
            if size is not None:
                s += f"，半径/半宽约 {size:.3f}×画布宽"
            L.append(f"  · {e.get('name','')}{s}")
        L.append("")
        L.append(f"叠放顺序（从后往前，后画的盖住先画的）："
                 f"{' → '.join(e.get('name','') for e in elems)}")
        L.append("")

    # ── 几何约束（★ 临摹那一步必须拿它对账）──
    gc = ir.get("geometry_constraints") or {}
    cons = gc.get("约束") or []
    if cons:
        L.append("═══ 三、★ 几何约束（画错这张图就是废图）═══")
        L.append("**图像模型不知道物理，这一节是最容易画错的地方。**")
        L.append("★ 矢量那一步必须拿这一节**逐条对账**。")
        L.append("  · 位图已经过了闸口（check_sketch 答完所有几何问题）→ **就该照它画**；")
        L.append("  · 对不上 = 位图错了 → 回去改简报重出，而不是在矢量那步偷偷「修正」。")
        L.append("")
        for c in cons:
            L.append(f"  · {c.get('名','')}：{c.get('量','')}  要求 {c.get('要求','')}")
        L.append("")

    # ── 风格 ──
    if stage == "sketch":
        L.append("═══ 四、风格（这一步不用管）═══")
        L.append("**这一步只要形体清楚、能看出是什么。**")
        L.append("平涂、细描边、不用打光都行 —— 质感留给下一步。")
        L.append("唯一要求：**形体边界要清晰**，别用模糊边缘，"
                 "否则下一步看不出形体在哪。")
        L.append("")
    else:
        L.append("═══ 四、风格 ═══")
        L.append("目标是**期刊矢量插画风**，不是 3D 渲染图。具体：")
        L.append("  · 形体用清晰的**深色描边**勾出来（参考图的描边是实的，不是发光的）")
        L.append("  · 体积感来自**明暗渐变**，不是靠投影滤镜")
        L.append("  · **先定一个全局光源**（比如左上方 45°），"
                 "所有高光、阴影、投影都从它推导 —— 不要每个物体各拍一个方向")
    if style and stage == "render":
        L.append(f"  · 风格类的量测参考（{style['class']}，"
                 f"n={style['n_sources']}）：")
        if style.get("palette"):
            L.append(f"    主色族：{' '.join(style['palette'])}")
        if style.get("stroke_width"):
            L.append(f"    典型线宽：{style['stroke_width']:.1f}（相对单位）")
    L.append("")

    # ── 禁止 ──
    L.append("═══ 五、明确禁止 ═══")
    for i, f in enumerate(COMMON_FAILURES, 1):
        L.append(f"{i}. {f}")
    L.append("")

    # ── 输出 ──
    L.append("═══ 六、输出 ═══")
    L.append(f"  · 位图，长边 ≥ 2000 px（下一步要描摹，分辨率低了边会糊）")
    L.append(f"  · 白底，不要边框、不要外阴影")
    L.append(f"  · 文字清晰可读（尺寸不能太小，否则临摹时认不出）")
    L.append("")
    L.append("─" * 60)
    if stage == "sketch":
        L.append("★ 下一步（不在本次任务里）：")
        L.append("  ① **矢量化输出**（草图必须是矢量的，人要能直接改）：")
        L.append("       python3 scripts/sketch_to_vector.py <草图.png> \\")
        L.append("           -o <草图.svg> --ocr      # --ocr 让字也变成真 <text>")
        L.append("     不用写 panels.py —— 草图靠自动切分，每个形体一个子层。")
        L.append("  ② **过闸口**（第一道）：拿草图对着第三节逐条核对")
        L.append("       python3 scripts/check_sketch.py <草图.png> --ir <你的.ir.yaml>")
        L.append("     ★ 有半张输出是「必须你/模型看图逐条回答」的几何约束。")
        L.append("     任何一条答「否」→ 改简报重生，**不要往下走**。")
        L.append("  ③ 过闸口后再调一次图像模型出**成品位图**（要质感，同样带 --ref）。")
    else:
        L.append("★ 下一步（不在本次任务里）：")
        L.append("  ⓪ **先过闸口**（第二道，这一步以前漏了）：")
        L.append("       python3 scripts/check_sketch.py <成品位图.png> --ir <你的.ir.yaml>")
        L.append("     成品位图是矢量那一步的**唯一依据**，它错了后面全错。")
        L.append("  ① **首选：理解后重画**（路径 2 / 3 的默认终点）")
        L.append("       看懂位图里每个部分是什么，逐个重画成 SVG：")
        L.append("       · 图层按**结构/物理**分（nucleus-A / photon-A / vertex…），"
                 "**不按颜色分**；")
        L.append("       · 要保留**色彩和阴影**（形体用真 <gradient>，别退化成平涂）；")
        L.append("       · 文字写成真 <text>。")
        L.append("  ② **备用：混合临摹**（重画不划算/要更忠实时才用）")
        L.append("       python3 scripts/raster_to_vector_semantic.py <位图> -o fig.svg \\")
        L.append("           --words words.txt --panels panels.py --check")
        L.append("       逐像素描摹 + 文字擦掉重写真 <text>；")
        L.append("       分层同样按物理元素（颜色只是 path 的属性，不是图层）。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ir")
    ap.add_argument("--style-profile", default=None)
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch",
                    help="sketch=中间稿（只求构图，路径1 用）；"
                         "render=成品位图（要质感，路径2 的第二段用）")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    p = Path(a.ir)
    if not p.exists():
        raise SystemExit(f"找不到 {p}")
    ir = load_ir(p)
    style = load_style(a.style_profile, a.want_class)
    brief = build(ir, style, a.stage)

    if a.out:
        Path(a.out).write_text(brief, encoding="utf-8")
        print(f"已输出 {a.out}（{len(brief)} 字符）")
    else:
        print(brief)


if __name__ == "__main__":
    main()
