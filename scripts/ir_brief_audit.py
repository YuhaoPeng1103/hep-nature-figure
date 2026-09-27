#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ir_brief_audit —— IR → 生图简报 的「无损体检」
=========================================================================

**这个脚本防的是什么**

`ir_to_genbrief.py` 是 IR 和生图模型之间**唯一的**翻译层。模型永远看不到 IR，
它只收到简报 —— 所以**编译器丢掉的字段，等于从来没写过**。

这件事已经踩过三次坑（每次都是"IR 明明写了，出的图却不照做"）：

| 版本 | 被丢 / 被写死的字段 | 后果 |
|---|---|---|
| v2.6.4 | `style.conventions` | IR 写「纵向压扁」，4/4 把两核画成横扁 |
| v2.6.7 | `style.palette` + 风格档写死成扁平 | IR 要 3D，简报反过来禁 3D → 火球=纯色圆盘 |
| v2.6.9 | `elements[].material` | IR 写「哑光 / 三层壳 / 组元颗粒」一个字没进 → 火球=光滑糖球 |
| v2.6.10 | `composition.view` / `约束[].为什么` / `元素布局` … | 见下面的表 |

**做法**：给 IR 的每个叶子字段塞一个唯一哨兵字符串，编译成简报，
再逐个查哨兵在不在。**不靠读代码猜**，靠编译结果说话。

用法：
    python3 scripts/ir_brief_audit.py              # 两个阶段都查
    python3 scripts/ir_brief_audit.py --stage render
    python3 scripts/ir_brief_audit.py --verbose
退出码：有「必须到达」的字段没到达 -> 1（可以挂进 CI / 回归测试）

字段分四类：
    carry        必须到达（两个阶段都要）
    carry-render 只要求 render 阶段到达（sketch 刻意不带，见 --verbose 的理由）
    context      到达，但简报里明说「仅供理解，不要画进图里」
    skip         刻意不带 —— 给工具/人/后端选型用，不该塞给图像模型
"""
from __future__ import annotations

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8（否则打印 ✅ 会崩）

import argparse
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ir_to_genbrief as IG          # noqa: E402


# ────────────────────────────────────────────────────────── 体检表
# (字段路径, 哨兵, 分类, 为什么)
FIELDS = [
    # ── ① figure 层 ──
    ("figure.physics_claim",      "S_claim",      "carry",        "这张图要表达什么物理（第一节正文）"),
    ("figure.archetype",          "S_archetype",  "context",      "图型：示意图 ≠ 定量面板，影响画法"),
    ("figure.canvas.ratio",       "S_ratio",      "context",      "IR 声明的画布比例"),
    ("figure.canvas.用途",         "S_canvas_use", "context",      "单栏 / 双栏"),
    ("figure.title",              "S_title",      "skip",         "图题通常不进画面（画上去就是错）"),
    ("figure.id",                 "S_fid",        "skip",         "回溯用"),
    ("figure.source",             "S_fsrc",       "skip",         "文献出处"),
    ("figure.panels_count",       "S_panels",     "skip",         "工具用（分面板后端才需要）"),

    # ── ② elements 层 ──
    ("elements.name",             "S_name",       "carry",        "元素名"),
    ("elements.physics_role",     "S_role",       "carry",        "物理含义（防花里胡哨的关键）"),
    ("elements.primitive",        "S_prim",       "carry",        "形态"),
    ("elements.params.<非坐标>",   "S_pnote",      "carry",        "形态参数（坐标由构图层负责）"),
    ("elements.material",         "S_mat",        "carry",        "★ v2.6.9 前整段丢"),
    ("elements.z",                "S_z",          "skip",         "折进「叠放顺序」一行，不单独送"),

    # ── ③ geometry_constraints ──
    ("geometry_constraints.名",    "S_gcname",     "carry",        "第三节逐条对账的标题"),
    ("geometry_constraints.量",    "S_gcmeas",     "carry",        "可计算的量"),
    ("geometry_constraints.要求",  "S_gcreq",      "carry",        "判据"),
    ("geometry_constraints.为什么", "S_gcwhy",      "carry",        "★ v2.6.10 前整段丢：不说为什么，模型分不清哪条能让"),

    # ── ④ composition ──
    ("composition.view",          "S_view",       "carry",        "★ v2.6.10 前整段丢：视角是几何约束的前提"),
    ("composition.layout[]",      "S_layout",     "carry",        "布局"),
    ("composition.note",          "S_note",       "carry",        "构图备注（常含「不要画什么」）"),
    ("composition.分区",           "S_zone",       "carry",        "★ v2.6.10 前整段丢"),
    ("composition.叠放关系",        "S_stack",      "carry",        "★ v2.6.10 前整段丢（prose 版，比 z 排序多细节）"),
    ("composition.元素布局[].锚点", "S_anchor",     "carry",        "★ v2.6.10 前整段丢，而同义的 params.cx/cy 却能进"),
    ("composition.元素布局[].相对尺寸", "S_size",   "carry",        "★ 同上"),
    ("composition.元素布局[].备注",  "S_remark",    "carry",        "★ 同上"),

    # ── ⑤ style ──
    ("style.classification",      "S_class",      "carry-render", "风格定位（sketch 档刻意不带：那一步要扁平，带它会打架）"),
    ("style.evidence",            "S_evid",       "skip",         "判据（给人看的分类理由）"),
    ("style.characteristics[]",   "S_char",       "carry-render", "风格特征逐条（同上，sketch 档刻意不带）"),
    ("style.palette",             "S_pal",        "carry",        "★ v2.6.10 前 sketch 档整段丢：草图会自己乱配色"),
    ("style.line_widths",         "S_lw",         "carry-render", "线宽"),
    ("style.fonts",               "S_font",       "skip",         "字体名对图像模型无意义（文字最后重写成真 <text>）"),
    ("style.conventions[]",       "S_conv",       "carry",        "形态约定（v2.6.4 修过）"),

    # ── ⑥ execution / ⑦ assertions ──
    ("execution.*",               "S_exec",       "skip",         "后端选型：给路由器用，不是画面内容"),
    ("assertions.machine[]",      "S_asm",        "skip",         "验收：给 check 脚本用"),
    ("assertions.human[]",        "S_ahm",        "skip",         "验收：给人用"),
]


def T(name: str) -> str:
    """哨兵外面包一层分隔符。

    为什么必须包：`S_z` 是 `S_zone` 的前缀 —— 纯子串匹配会把
    「z 折进叠放顺序、没单独送」误判成「z 到达了」。加 @@ 后
    `@@S_z@@` 不再是 `@@S_zone@@` 的子串，判定才准。
    """
    return "@@" + name + "@@"


def _wrap(v):
    """把探针里所有 S_xxx 字面量包上分隔符（递归）。"""
    if isinstance(v, str) and v.startswith("S_"):
        return T(v)
    if isinstance(v, dict):
        return {k: _wrap(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_wrap(x) for x in v]
    return v


def probe_ir() -> dict:
    """每个叶子字段一个唯一哨兵。"""
    return {
        "figure": {"id": "S_fid", "source": "S_fsrc", "title": "S_title",
                   "physics_claim": "S_claim", "archetype": "S_archetype",
                   "panels_count": 3,
                   "canvas": {"w": 1000, "h": 600, "ratio": "S_ratio",
                              "用途": "S_canvas_use"}},
        "elements": [{"id": "E1", "name": "S_name", "z": "S_z",
                      "physics_role": "S_role", "primitive": "S_prim",
                      "params": {"note": "S_pnote"}, "material": "S_mat"}],
        "geometry_constraints": {"约束": [
            {"名": "S_gcname", "量": "S_gcmeas", "要求": "S_gcreq",
             "为什么": "S_gcwhy"}]},
        "composition": {"view": "S_view", "layout": ["S_layout"], "note": "S_note",
                        "分区": "S_zone", "叠放关系": "S_stack",
                        "元素布局": [{"id": "E1", "锚点": ["S_anchor", 0.5],
                                     "相对尺寸": "S_size", "备注": "S_remark"}]},
        "style": {"classification": "S_class", "evidence": "S_evid",
                  "characteristics": ["S_char"], "palette": {"p": "S_pal"},
                  "line_widths": {"outline": "S_lw"}, "fonts": {"latin": "S_font"},
                  "conventions": ["S_conv"]},
        "execution": {"primary": "S_exec"},
        "assertions": {"machine": ["S_asm"], "human": ["S_ahm"]},
    }


def audit(stage: str):
    brief = IG.build(_wrap(probe_ir()), None, stage)
    rows = []
    for path, tok, kind, why in FIELDS:
        if kind == "skip":
            want = False
        elif kind == "carry-render":
            want = (stage == "render")
        else:
            want = True
        got = T(tok) in brief
        rows.append((path, tok, kind, want, got, why))
    return brief, rows


def main():
    ap = argparse.ArgumentParser(
        description="IR -> 简报 的无损体检（哨兵法：每个字段塞唯一串，编译后查在不在）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法：")[-1])
    ap.add_argument("--stage", choices=("sketch", "render", "both"), default="both")
    ap.add_argument("--verbose", action="store_true", help="每行都打理由")
    a = ap.parse_args()

    stages = ("sketch", "render") if a.stage == "both" else (a.stage,)
    bad_total = 0
    for stage in stages:
        brief, rows = audit(stage)
        print("=" * 96)
        print("阶段 %s   简报 %d 字符" % (stage, len(brief)))
        print("=" * 96)
        print("  %-34s %-14s %-6s %s" % ("IR 字段", "分类", "到达?", ""))
        print("  " + "-" * 92)
        bad = []
        for path, tok, kind, want, got, why in rows:
            mark = "✅" if got else "❌"
            ok = (got == want)
            if not ok:
                bad.append((path, want, got, why))
            print("  %-34s %-14s %-6s %s" % (path, kind, mark,
                  ("  ←← 不一致：" + ("该到没到" if want else "不该到却到了") + "；" + why)
                  if not ok else ("  " + why if a.verbose else "")))
        print()
        if bad:
            print("  ★ %d 项不一致：" % len(bad))
            for path, want, got, why in bad:
                print("      %s  期望到达=%s 实际=%s   （%s）" % (path, want, got, why))
        else:
            print("  ★ 全部一致 ✅（该到的都到了、不该到的都没到）")
        print()
        bad_total += len(bad)

    if bad_total:
        print("结论：有 %d 项不一致 —— 编译器丢字段，就是 IR 白写。" % bad_total)
        return 1
    print("结论：IR -> 简报 无损（按上面的分类标准）✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
