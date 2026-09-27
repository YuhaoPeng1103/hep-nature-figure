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

## 风格档（2026-09-27）

    --style-mode auto | flat | render3d      （默认 auto）

    auto     = 按 IR 的 `style` 段判断：含 3D/体积/网格线/半写实 等词 -> render3d；
               含 扁平/平涂 -> flat；判不出 -> **ref（跟随参考图）**
    flat     = 扁平矢量插画（老行为）
    render3d = 3D 渲染的期刊插画（球面明暗 + 高光 + 柔和阴影 + 真渐变 + 网格线）

★ 修的是这个坑：简报以前**把风格写死成扁平矢量**并禁止 3D，与 IR 的 `style`
  段无关。实测（形变核->火球）：IR 要「半写实 3D / 球面明暗 + 网格线 /
  火球橙->红渐变」，简报却写「不是 3D 渲染图」-> 火球被画成纯色圆盘。
  现在 render 档按风格档分叉，`sketch` 档**保持扁平**（那是为了能切矢量图层，
  不是最终风格）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ir_canvas          # 画布的唯一读取口（composition.canvas 优先）

# 图像生成模型最常犯的错——写进"禁止项"，比事后修便宜
#
# ★ 2026-09-27：原来第 4 条**无条件**写着「不是 3D 渲染图、不是写实材质」。
#   后果（形变核->火球 算例实测）：IR 的 style 明写「半写实插画 / 3D 椭球 /
#   球面明暗 + 网格线 / 火球橙->红渐变」，生成的简报却反过来禁止 3D ——
#   IR 与简报**直接打架**，模型照简报走，火球被画成一个纯色圆盘。
#   3D 渲染风（球面明暗/高光/柔和阴影/平滑渐变/网格线）在矢量化时会变成
#   真 <gradient>，**并不**降低交付质量，不该被禁。现在按风格档分叉。
_COMMON_FAILURES_HEAD = [
    "**不要添加 IR 元素清单里没有的【独立物体/箭头/文字/装饰光晕】**。模型最爱加"
    "装饰性的光晕、星星、多余箭头——那些会被带进矢量，且违背物理内容。"
    "★ 但第一节【材质】里**写明**的内部结构（分层 / 组元颗粒 / 场线 / 亮核 / 外壳 / "
    "日冕…）**必须画出来** —— 那是规格，不是装饰。",
    "**文字不要画错**。位图里的文字只当占位（下一步会重写成真 `<text>`），"
    "但拼写和数字必须对，否则临摹时会照抄错值。",
    "**不要改视角或投影**。IR 里写了视角约定就照办；换视角会让几何约束全部失效。",
]
_COMMON_FAILURES_TAIL_FLAT = [
    "**不要画成照片级**。目标是**扁平矢量插画风**（干净的形体 + 明确的描边），"
    "不是 3D 渲染图、不是写实材质。",
    "**不要加渐变背景、光斑、镜头光晕**这些摄影感的东西。",
]
_COMMON_FAILURES_TAIL_3D = [
    "**不要画成照片级**。**允许** 3D 渲染的立体感（球面明暗 / 高光 / 柔和阴影 / "
    "平滑渐变 / 表面网格线）—— 这些矢量化后是真 `<gradient>`，是加分项；"
    "但**不要**照片级材质纹理、胶片颗粒/噪点纹理、景深虚化、镜头光晕。"
    "（示意性的细小符号——组元点、场线、网格线——不算「颗粒噪点」，该画就画。）",
    "**不要加渐变背景、装饰性光斑**这些摄影感的东西（背景保持纯白）。",
]


def common_failures(style_mode: str = "flat"):
    """按风格档给「明确禁止」清单：扁平档禁 3D，3D 档反而鼓励 3D。"""
    tail = (_COMMON_FAILURES_TAIL_FLAT if style_mode == "flat"
            else _COMMON_FAILURES_TAIL_3D)
    return _COMMON_FAILURES_HEAD + tail


# ★ 2026-09-27：风格档。生图简报以前**把风格写死成扁平矢量**，与 IR 的
#   style 段无关 —— IR 说了要 3D 也没用。现在三档：
#     flat     = 扁平矢量插画（旧行为）
#     render3d = 3D 渲染的期刊插画（球面明暗/高光/柔和阴影/真渐变）
#     ref      = 跟随参考图（参考图 = 风格书；IR 没提示时的默认）
STYLE_MODE_LABELS = {
    "flat": "扁平矢量插画风",
    "render3d": "3D 渲染的期刊插画风",
    "ref": "跟随参考图（参考图是风格书）",
}
# 判据关键词：IR 的 style 段里出现这些 = 这张图要的是 3D 渲染质感
_RENDER3D_HINTS = (
    "3d", "3D", "三维", "立体", "体积感", "球面明暗", "网格线", "经纬",
    "渲染", "半写实", "高光", "环境遮蔽", "volumetric",
)
_FLAT_HINTS = ("扁平", "平涂", "纯色填充", "flat", "描边插画")


def style_mode_hits(ir: dict):
    """返回命中的关键词列表 —— 说清「风格档是凭哪个词判的」，便于事后对账。"""
    st = ir.get("style") or {}
    bits = []
    for k in ("mode", "look", "render", "classification", "evidence",
              "conventions", "note"):
        v = st.get(k)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            bits.extend(str(x) for x in v)
        elif isinstance(v, dict):
            bits.extend(str(x) for x in v.values())
        else:
            bits.append(str(v))
    low = " ".join(bits).lower()
    return [h for h in _RENDER3D_HINTS if h.lower() in low] + \
           [h for h in _FLAT_HINTS if h.lower() in low]


def resolve_style_mode(ir: dict, cli_mode: str = "auto") -> str:
    """定风格档：命令行 > IR 的 style 段关键词 > 默认 ref（跟随参考图）。

    ★ 不默认 flat：参考图是风格书，默认应该跟着参考图走，而不是退回扁平。
      （实测教训：IR 要 3D，简报却写死扁平 -> 火球变纯色圆盘。）
    """
    if cli_mode in ("flat", "render3d"):
        return cli_mode
    st = ir.get("style") or {}
    bits = []
    for k in ("mode", "look", "render", "classification", "evidence",
              "conventions", "note"):
        v = st.get(k)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            bits.extend(str(x) for x in v)
        elif isinstance(v, dict):
            bits.extend(str(x) for x in v.values())
        else:
            bits.append(str(v))
    low = " ".join(bits).lower()
    if any(h.lower() in low for h in _RENDER3D_HINTS):
        return "render3d"
    if any(h.lower() in low for h in _FLAT_HINTS):
        return "flat"
    return "ref"


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


# ★ 2026-09-26：IR 的 `primitive` / `params` 是**形态规格**（弹簧线、星芒、
#   长宽比、波数、射线数…），简报以前把它们**整个丢掉**——只用 primitive 做了
#   分类，从没打到纸面上。实测后果（UPC 算例）：
#     · IR 写「弹簧线（螺旋）」→ 模型画成一根**虚线**（规格没给，只能猜）
#     · IR 写「射线数 11」   → 模型画成一个**实心点**
#     · IR 写「长宽比 约 2.2:1」→ 模型画成横扁椭圆（这条同时是压扁方向画错的
#       一半原因；另一半是 style.conventions 没进简报）
#   下面这两个键是**坐标**，已经由「二、构图」那节负责，别在这儿重复。
SHAPE_SKIP_KEYS = {"cx", "cy", "x", "y", "x1", "y1", "r", "R", "rx", "ry"}


def shape_hint(e: dict) -> str:
    """把一条元素的形态规格压成一行人读文本；没有就返回空串。"""
    bits = []
    prim = " ".join(str(e.get("primitive") or "").split())
    if prim:
        bits.append(prim)
    ps = e.get("params") or {}
    kv = ", ".join(f"{k}={v}" for k, v in ps.items()
                   if k not in SHAPE_SKIP_KEYS and not str(k).startswith("_"))
    if kv:
        bits.append(kv)
    return "；".join(bits)


def _fmt_num(v):
    """params 里的数值 → 可读字符串。★ 支持**列表**。

    ★ 实测（2026-09-27，形变核→火球 四阶段图）：IR 里「三个演化箭头」自然写成
      `params: {cx: [0.175, 0.385, 0.655], cy: 0.50}`，而这里原来直接
      `f"{x:.2f}"` → TypeError: unsupported format string passed to list.__format__，
      **整个简报生成崩掉**（而且报的是 Python 内部错，看不出是 IR 写法问题）。
      一个「写得更清楚反而炸」的坑。现在列表会原样打印成 [0.18, 0.39, 0.66]。
    """
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt_num(i) for i in v) + "]"
    try:
        return "%.2f" % float(v)
    except (TypeError, ValueError):
        return str(v)


def build(ir: dict, style: dict | None, stage: str = "sketch",
          style_mode: str | None = None) -> str:
    if style_mode is None:
        style_mode = resolve_style_mode(ir)
    fig = ir.get("figure", {})
    elems = sorted(ir.get("elements", []), key=lambda e: e.get("z", 0))
    # ★ 2026-09-27：画布只能由 ir_canvas 读。规范（references/ir-spec.md）把画布
    #   写在 composition.canvas，这里以前读 figure.canvas —— 仓库 8 份 IR 有 6 份
    #   按规范写，画布被**静默丢弃**：简报照默认 1400×560（2.50）走，gen_figure
    #   又按 --size 默认请求 1664×928（1.79），同一张图三个比例。
    cv, cv_src = ir_canvas.canvas_node(ir)
    W, H, cv_why = ir_canvas.canvas_for_brief(ir)

    L = []
    if stage == "sketch":
        L.append("【任务】把下面这份物理构图**画成一张扁平矢量风草图稿**。")
        L.append("")
        L.append("★ 这一步**只要构图，不要质感**。画成 Illustrator 里的扁平矢量稿那样：")
        L.append("  · **平涂纯色**：每个元素一种纯色填充，**禁止**渐变、阴影、高光、反射；")
        L.append("  · **禁止 3D 立体感和材质纹理**（不要球体高光、不要金属/塑料质感、不要颗粒）；")
        L.append("  · **每个元素只画一层形状**：核子就用一层规则的圆/椭圆表示，")
        L.append("    **不要**画成几百个带高光的小球；")
        L.append("  · 细描边勾轮廓，边界清晰、不模糊。")
        L.append("")
        L.append("  为什么这么苛刻：下一步要把这张图**自动切成矢量图层给人改**。")
        L.append("  实测：带渐变的渲染稿切出 **13.8 万条**碎路径（人改不动）；")
        L.append("  平涂稿能切出**几十个**干净的形体图层。质感由**下一步**的成品位图负责。")
    else:
        L.append("【任务】按下面这份构图，出一张**高质量成品位图**。")
        L.append("")
        L.append("★ 这一步要求**质感和光影到位**（上一步只出了构图稿）。")
        L.append("  但仍然：形体要清楚可辨认，不要靠模糊和噪点营造氛围 ——")
        L.append("  因为下一步还要把它转成矢量。")
        L.append(f"★ 风格基调：**{STYLE_MODE_LABELS.get(style_mode, style_mode)}**"
                 "（详见第四节；参考图是风格书，质感照它）")
    L.append("")
    L.append("★ **必须随本简报一起，把参考图传给模型**"
             "（`gen_figure.py --ref 图.png`，可多张）。")
    L.append("  只给文字 → 出来一定是「通用插画脸」。参考图的作用是**给风格**"
             "（配色 / 线条 / 材质 / 光影），**不是给构图** —— 构图以本文为准。")
    if stage == "render":
        # ★ 2026-09-26 实测：这一步以前**只传风格参考图**，没传上一步的草图。
        #   结果成品位图自己重猜了一遍构图 —— 本次 UPC 算例里它把核 B 画成了
        #   横扁（草图/IR 都要求高瘦），而构图闸口拦不住（形状朝向原本没人测）。
        #   草图是**已经过闸口①**的构图依据，必须一起传，否则"根据草图生成位图"
        #   这句话在流程里是空的。
        L.append("")
        L.append("★ **必须把上一步的草图也一起 `--ref` 传进来** —— 草图是**构图依据**"
                 "（它已经过了闸口①）。")
        L.append("  只传风格参考图 = 让模型重新猜一遍构图，构图会被改坏。")
        L.append("  正确调用：`gen_figure.py --brief brief2.md --stage render \\")
        L.append("      --content-ref <上一步选中的草图.png> --ref <风格参考图.png> --seeds ...`")
    L.append("")
    L.append("★★ **参考图只给风格，不许抄内容**：参考图里的物体、数量、布局、箭头方向、"
             "文字与标注**一律不得照搬**；本图的物体/数量/位置/方向"
             "**全部以本文（一、二、三节）为准**，冲突时永远以本文为准。")
    L.append("  （实测：qwen-image 是**图生图**，参考图内容越像目标越容易被整幅照抄 —— "
             "出的图会直接变成参考图的样子。选参考图优先「**内容不同、风格相同**」；"
             "只有同类图时，就裁它的配色/材质局部当参考。出图后跑 "
             "`scripts/ref_leak_check.py` 量一下，r>=0.85 就是照抄。）")
    L.append("  ★ **反过来也成立：本图内容可以和参考图完全不同。** 参考图是**风格书**"
             "（配色 / 线条 / 材质 / 光影 / 渲染方式），**不是内容模板** —— "
             "不是每个任务都要照它的布局、物体、箭头画。参考图里**没有**的物理对象，"
             "按本文（一、二、三节）画出来即可，绝不会因为「参考图里没有」就不画。")
    L.append("")
    L.append("★ **不要画外框**：图片四周不要边框、不要矩形画框、不要装饰性的外框线。")
    L.append("  （实测：模型 3/3 会在四周画一条 1px 淡灰细框，"
             "导致出图被裁、构图检测也跟着失效。）")
    L.append("")
    L.append(f"画布比例：{W}×{H}（宽高比 {W/H:.2f}；{cv_why}）。白底。")
    # ★ v2.6.10 无损体检：figure.archetype / canvas.用途 / canvas.ratio 以前整段丢。
    #   这几条是"这张图是什么性质"的上下文（示意图 ≠ 定量面板），
    #   但它们**不是画面内容** —— 明说不要画进图里，否则模型会当标题画上去。
    _meta = []
    if fig.get("archetype"):
        _meta.append("图型 %s" % fig["archetype"])
    if cv.get("用途"):
        _meta.append("用途 %s" % " ".join(str(cv["用途"]).split()))
    if cv.get("ratio"):
        _meta.append("IR 声明的画布比例 %s" % " ".join(str(cv["ratio"]).split()))
    if cv_src == "figure.canvas":
        _meta.append("画布写在 figure.canvas（旧写法；规范是 composition.canvas）")
    if _meta:
        L.append("（本图定位：" + "；".join(_meta) + " —— **仅供理解，不要画进图里**）")
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
    # ★ 2026-09-26：原来只认英文 "label"。UPC 那条 IR 写的是 `primitive: 文字`，
    #   于是**标签文字整段没进简报** —— 模型只能自己编，编出来是中文「核A / 核B」，
    #   而 IR 要的是 A / B。中文 IR 写中文 primitive 是很自然的，必须一起认。
    ANNOT_PRIMS = {"label", "text", "文字", "标注"}
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
        mat = " ".join(str(e.get("material") or "").split())
        if f in seen:
            seen[f]["n"] += 1
            if not seen[f]["shape"] and shape_hint(e):
                seen[f]["shape"] = shape_hint(e)
            if mat and not seen[f]["material"]:
                seen[f]["material"] = mat
            # 只在原 role 更实质时补充
            if role and not role.startswith(("同", "同上")) and len(role) > len(seen[f]["role"]):
                seen[f]["role"] = role
        else:
            entry = {"n": 1, "shape": shape_hint(e), "material": mat,
                     "role": role if not role.startswith(("同", "同上")) else ""}
            seen[f] = entry
            families.append((f, entry))

    L.append("图中要出现的**物理对象**（数量要对，但不能把实现细节当内容）：")
    for f, info in families:
        cnt = f" ×{info['n']}" if info["n"] > 1 else ""
        L.append(f"  · {f}{cnt}" + (f" —— {info['role']}" if info["role"] else "")
                 + (f"【形态：{info['shape']}】" if info.get("shape") else "")
                 + (f"【材质：{info['material']}】" if info.get("material") else ""))
    if has_shadow:
        L.append("  · （各主要形体带**柔和的投影与接触阴影**，让它们看起来是浮在纸面上"
                 "而不是贴上去的）")
    L.append("")

    if annots:
        L.append("图中**文字**（拼写和数值必须完全正确 —— 下一步会重写成真正的矢量文字，"
                 "现在画错就会被照抄）：")
        for e in annots:
            txt = (e.get("params") or {}).get("t") or e.get("text")
            if txt:
                L.append(f'  · "{txt}"')
        L.append("  ★ **逐字照写上面这些字符串**（大小写、上下标 e⁺ / e⁻ 都要对），"
                 "**不要翻译成中文、不要自己加标签**。")
        L.append("")
    L.append("")

    # ── 构图 ──
    # ★ v2.6.10 无损体检：这一节原来只读 composition.layout / note，
    #   而 view（视角）/ 分区 / 元素布局 / 叠放关系 **整段丢**。
    #   实测（形变核→火球 算例）：IR 里 `view: "斜视 3D，四个阶段沿水平方向排成一行"`
    #   一个字都没进简报 —— 用户只能把视角**再抄一遍进 figure.physics_claim** 才生效。
    #   而视角是几何约束的前提：视角一换，第三节所有约束全部失效。
    comp = ir.get("composition") or {}
    layout = comp.get("layout")
    note = comp.get("note")
    view = comp.get("view") or comp.get("视角")     # view(实测 IR 写法) 与 视角(规范写法) 都认
    zone = comp.get("分区")
    stack = comp.get("叠放关系")
    places = comp.get("元素布局") or []
    if layout or view or zone or stack or places:
        L.append("═══ 二、构图 ═══")
        if view:
            L.append("视角：%s" % " ".join(str(view).split()))
        if zone:
            L.append("分区：%s" % " ".join(str(zone).split()))
        if layout:
            if isinstance(layout, (list, tuple)):
                L.append("布局：")
                for it in layout:
                    L.append("  · %s" % it)
            else:
                L.append(f"布局：{layout}")
        if note:
            L.append(" ".join(str(note).split()))
        L.append("")
        # ★ v2.6.10：composition.元素布局（结构化锚点）以前整段丢，而同一件事
        #   写进 elements[].params.cx/cy 却能进简报 —— 两种写法一种活一种死，是陷阱。
        if places:
            L.append("各元素位置（IR 的 composition.元素布局；与下面的 params 坐标"
                     "冲突时**以本表为准**）：")
            for it in places:
                a = it.get("锚点") or []
                _s = "  · %s" % it.get("id", "")
                if isinstance(a, (list, tuple)) and len(a) >= 2:
                    _s += "  锚点 (x=%s, y=%s)" % (_fmt_num(a[0]), _fmt_num(a[1]))
                if it.get("相对尺寸"):
                    _s += "，相对尺寸 %s" % it["相对尺寸"]
                if it.get("备注"):
                    _s += "（%s）" % it["备注"]
                L.append(_s)
            L.append("")
        L.append("各元素位置（相对画布，x 从左 0→1，y 从上 0→1）：")
        for e in elems:
            p = e.get("params") or {}
            x = p.get("cx", p.get("x", p.get("x1")))
            y = p.get("cy", p.get("y", p.get("y1")))
            if x is None or y is None:
                continue
            size = p.get("R", p.get("r", p.get("rx")))
            s = "  位置 (%s, %s)" % (_fmt_num(x), _fmt_num(y))
            if size is not None:
                s += "，半径/半宽约 %s×画布宽" % _fmt_num(size)
            L.append(f"  · {e.get('name','')}{s}")
        L.append("")
        if stack:
            L.append("叠放关系：%s" % " ".join(str(stack).split()))
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
            _line = f"  · {c.get('名','')}：{c.get('量','')}  要求 {c.get('要求','')}"
            # ★ v2.6.10：`为什么` 以前整段丢。这一层存在的理由就是防「画得漂亮但物理错」；
            #   只说"要满足什么"、不说"为什么不能让"，模型就分不清哪条可以妥协。
            if c.get("为什么"):
                _line += "   ← **为什么**：" + " ".join(str(c["为什么"]).split())
            L.append(_line)
        L.append("")

    # ── 形态约定（IR 的 style.conventions）──
    # ★ 2026-09-26 实测：这一段以前**根本没进简报**。UPC 那条算例的 IR 里写着
    #   「核必须画成纵向压扁的椭圆（Lorentz 收缩）」，简报里却一个字都没有 ——
    #   于是草图 + 成品位图 4/4 把两核画成**横扁**椭圆（压扁方向垂直于运动方向，
    #   而它们沿水平束流运动），旧闸口还量不出来（它只查「相向 / 不重叠 /
    #   光子线在两核之间 / 末态背对背」四条，没有一条管形状朝向）。
    #   约定只写在 IR 里 = 没人执行。必须显式落到简报上。
    conv = (ir.get("style") or {}).get("conventions") or []
    if conv:
        L.append("═══ 三·补、★ 形态约定（照画，不许自己发挥）═══")
        for c in conv:
            L.append(f"  · {c}")
        L.append("")

    # ── 风格 ──
    if stage == "sketch":
        L.append("═══ 四、风格（这一步**不要质感**）═══")
        L.append("**扁平矢量风：平涂纯色 + 细描边。**")
        L.append("明确**禁止**：渐变填充、投影/内阴影、高光、反射、")
        L.append("3D 立体渲染、画布质感（噪点/纸纹/颗粒）。")
        L.append("★ 这里的「扁平」**只是这一步的要求**（为了能自动切成矢量图层），")
        L.append("  **不是最终风格** —— 最终质感由成品位图那步跟随参考图决定：")
        L.append("  参考图是 3D 渲染风，成品就该是 3D 渲染风（本步扁平不影响它）。")
        L.append("比「好看」更重要的一件事：**形体边界要清晰**（下一步靠边界切图层）。")
        L.append("")
    elif style_mode == "flat":
        L.append("═══ 四、风格（扁平矢量插画风）═══")
        L.append("  · 形体用清晰的**深色描边**勾出来（参考图的描边是实的，不是发光的）")
        L.append("  · 体积感来自**少量明暗渐变**，不是靠投影滤镜")
        L.append("  · **先定一个全局光源**（比如左上方 45°），"
                 "所有高光、阴影、投影都从它推导 —— 不要每个物体各拍一个方向")
    elif style_mode == "render3d":
        L.append("═══ 四、风格（★ 3D 渲染的期刊插画风 —— 这一步就要质感）═══")
        L.append("目标是**期刊里 3D 渲染的矢量插画**（`_T3精选` 里 T3-02 那条线）：")
        L.append("  · 形体是**有体积的 3D 椭球/团块**：球面明暗 + 高光 + 环境遮蔽（AO），"
                 "表面可带**经纬网线**表现三维（参考图就是这么做的）")
        L.append("  · **允许并鼓励**平滑渐变 / 高光 / 柔和阴影 / 半透明叠色 —— "
                 "这些在矢量化时会变成真 `<gradient>` 与 `fill-opacity`，"
                 "**不会**降低交付质量，正是这一步要的东西")
        # ★ 2026-09-27：这一行原来是**硬编码**的「火球 = 内亮外暗的多层半透明渐变，
        #   边缘柔和」—— 不管 IR 的 material 写什么，都把火球定成一颗光滑高光球。
        #   实测（形变核→火球 算例）：出图就是一颗光滑塑料感的橙色糖球
        #   （内部 5 个半透明圆球），而同一份 IR 让别的模型画、或人工补上内部结构后，
        #   是「亮核 + 等离子体壳 + 外层日冕 + 内部组元点/场线」的富结构等离子体团。
        #   即「不好看」不是模型的锅，是这里的硬编码把模型按在了一颗空球上。
        L.append("  · **发光体 / 热区怎么画，以第一节各元素的【材质】为准**"
                 "（分层 / 组元 / 亮核 / 外壳 / 日冕…那张表说什么就是什么）。"
                 "材质没写清楚 = 模型只能画一颗**光滑高光球**，"
                 "那是通用 CG 球、不是物理对象。")
        L.append("  · **先定一个全局光源**（比如左上方 45°），"
                 "所有高光、阴影、投影都从它推导 —— 不要每个物体各拍一个方向")
        L.append("  · **仍然不要**：照片级材质纹理、胶片颗粒/噪点纹理、景深虚化、"
                 "镜头光晕、渐变背景 —— 这些矢量化后是噪声，会毁掉图层结构"
                 "（示意性的细小符号 ≠ 颗粒噪点，该画就画）")
    else:  # ref —— 跟随参考图
        L.append("═══ 四、风格（★ 跟随参考图 —— 参考图是**风格书**）═══")
        L.append("**渲染风格由参考图决定，不要默认成扁平矢量风。**")
        L.append("  · 先看参考图是哪种：2D 扁平矢量 / 3D 渲染插画 / 半写实 —— 照它来；")
        L.append("  · 参考图若是 **3D 渲染**：就画成有体积的 3D 形体（球面明暗 + 高光 + "
                 "柔和阴影 + 平滑渐变 + 表面网格线），配色 / 材质 / 光源方向照参考图；")
        L.append("  · **允许并鼓励**平滑渐变 / 高光 / 柔和阴影 / 半透明叠色"
                 "（矢量化时变成真 `<gradient>`，不降低交付质量）；")
        # ★ 同上：发光体长什么样以 IR 的 material 为准，别硬编码成「光滑渐变球」
        L.append("  · **发光体 / 热区怎么画，以第一节各元素的【材质】为准**"
                 "（分层 / 组元 / 亮核 / 外壳 / 日冕…那张表说什么就是什么）。"
                 "材质没写清楚 = 模型只能画一颗**光滑高光球**，"
                 "那是通用 CG 球、不是物理对象。")
        L.append("  · **仍然不要**：照片级材质纹理、胶片颗粒/噪点纹理、景深虚化、"
                 "镜头光晕、渐变背景（示意性的细小符号 ≠ 颗粒噪点，该画就画）。")
    # ★ v2.6.10 无损体检：这一段原来整个 `if stage == "render"`，
    #   于是 **sketch 阶段连 palette 都拿不到** —— 草图会自己乱配色。
    #   草图虽然是平涂，但"哪块冷哪块热"本身就是信息（IR 的 conventions 里
    #   经常明写"颜色是信息"），配色必须两个阶段都送。
    _ist = ir.get("style") or {}
    if stage == "render":
        if _ist.get("classification"):
            L.append(f"  · IR 给的风格定位：{_ist['classification']}")
    _pal = _ist.get("palette")
    if _pal:
        L.append("  · IR 指定的配色（**照这个用**%s）："
                 % ("；草图仍是平涂，但色相不许改" if stage == "sketch" else ""))
        if isinstance(_pal, dict):
            for _k, _v in _pal.items():
                L.append(f"     {_k}: {_v}")
        elif isinstance(_pal, (list, tuple)):
            L.append("     " + " / ".join(str(x) for x in _pal))
        else:
            L.append(f"     {_pal}")
    if stage == "render":
        _lw = _ist.get("line_widths")
        if isinstance(_lw, dict) and _lw:
            L.append("  · IR 指定的线宽：" + "，".join(
                f"{k}={v}" for k, v in _lw.items()))
        # ★ v2.6.10：style.characteristics 以前整段丢（它是 classification 的逐条展开）
        _ch = _ist.get("characteristics")
        if _ch:
            L.append("  · IR 列的风格特征（逐条对照着画）：")
            for _c in (_ch if isinstance(_ch, (list, tuple)) else [_ch]):
                L.append(f"     - {_c}")
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
    for i, f in enumerate(common_failures(style_mode), 1):
        L.append(f"{i}. {f}")
    L.append("")

    # ── 输出 ──
    L.append("═══ 六、输出 ═══")
    # ★ 上限别写成 2000：gen_figure 的默认画布长边才 1664 —— 简报提一个
    #   调用根本达不到的要求，模型只会把画布比例改坏去凑（v2.7.3 前实测）。
    L.append(f"  · 位图，长边 ≥ {max(W, H)} px（按上面画布比例出 {W}×{H} 即可；"
             "下一步要描摹，分辨率低了边会糊）")
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
    ap.add_argument("--style-mode", choices=("auto", "flat", "render3d"),
                    default="auto",
                    help="生图风格档。auto=按 IR 的 style 段判断（含 3D/体积/"
                         "网格线 等词 -> render3d；含 扁平/平涂 -> flat；"
                         "判不出 -> 跟随参考图）。flat=扁平矢量；"
                         "render3d=3D 渲染的期刊插画（球面明暗/高光/真渐变）")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    p = Path(a.ir)
    if not p.exists():
        raise SystemExit(f"找不到 {p}")
    ir = load_ir(p)
    style = load_style(a.style_profile, a.want_class)
    style_mode = resolve_style_mode(ir, a.style_mode)
    brief = build(ir, style, a.stage, style_mode=style_mode)

    if a.out:
        Path(a.out).write_text(brief, encoding="utf-8")
        _hits = style_mode_hits(ir)
        print(f"已输出 {a.out}（{len(brief)} 字符，风格档 {style_mode}"
              + ("；判据关键词：" + "/".join(_hits) if _hits
                 else "；IR 的 style 段没给判据")
              + "）")
    else:
        print(brief)


# ★ Windows：stdout 被管道/重定向时是 gbk —— 报告里的中文/✅ 会乱码
#   或被 UnicodeEncodeError 打断（见 scripts/_console.py）。
from _console import init_console

init_console()


if __name__ == "__main__":
    main()
