#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_brief_gate -- 位图简报硬闸门：**位图是润色草图，不是重画**。

为什么需要它（2026-10-08，作者原话）：
    「位图是润色完善草图的，可是现在你很多图位图比草图还难看，如果草图的
     元素都是符合物理的就不要删除啊，错误的就修改，需要增加的就添加元素」

实测的病：
  · collective_flow v49：草图 C11 那批还有核子堆 / 接触阴影，位图简报里
    **一个字都没写「保留」**，模型于是当新图重画 → 核退化成光滑球
    （`gen/v49/final/chosen.png`，见 `_nucleon_before_after.png`）。
  · 由 IR 编译出来的 render 简报天生只写「要有什么」，从不写「草图里已经
    对了什么」—— 所以「把草图已有的东西删掉」在流程上是**默认行为**。
  · 约定拦不住（AGENTS.md §0.2 的教训），只有闸门拦得住 —— 所以做成闸门。

硬性四块（缺一块 = 硬伤；`ref_guard.py --run --stage render` 会自动带上它）：

  ═══ 必须原样保留（草图里已经画对的东西：一个字都不许改、不许简化、不许删）═══
  ═══ 必须改对（草图里画错的：逐条「错在哪 → 改成什么」，不许照抄错的）═══
  ═══ 必须补上（IR 要求、草图里没有的）═══
  ═══ 标签白名单（图上只许出现这些字符串，一个都不许多）═══

判据：
  R1 四个块标题都在（字面量见上面的块名）；
  R2 「保留」块 >= 3 条条目（少于 3 条基本是敷衍 —— 一张物理示意图里
     能称得上「已画对」的东西不会只有一两个）；
  R3 「改对」块必须真写了改法（条目里出现 "→" 或 "改成"）；
  R4 「补上」块非空（真的没有就显式写「无」）；
  R5 白名单块里 >= 2 个标签 token（逗号 / 顿号 / 空格 分隔）；
  R6 全文出现「不许简化」/「不要简化」/「不许重画」之一 —— 把「润色」
     这件事写死，否则模型会把「质感到位」理解成「重新画一遍」。

用法：
    python scripts/render_brief_gate.py collective_flow/gen/v55/brief_render.md
    python scripts/render_brief_gate.py <brief> --json <报告.json>

退出码：0 = 过；1 = 有硬伤（不许调 API）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

KEEP = ("必须原样保留",)
FIX = ("必须改对",)
ADD = ("必须补上",)
WHITE = ("只许出现这些标签", "只许出现这些字符串")

ANTI_SIMPLIFY = ("不许简化", "不要简化", "不许重画", "不要重画")


def block_lines(text: str, markers):
    """取 markers 之一所在行之后、到下一个 '══' 块标题（或文末）之间的正文行。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if any(m in ln for m in markers):
            start = i + 1
            break
    if start is None:
        return None
    out = []
    for ln in lines[start:]:
        s = ln.strip()
        if s.startswith("══") and len(s) > 3:
            break
        out.append(ln)
    return out


def items(block):
    """块里的条目：以 · - * 或 数字. 开头的行。"""
    if not block:
        return []
    out = []
    for ln in block:
        s = ln.strip()
        if not s:
            continue
        if s[0] in "·-*•" or re.match(r"^\d+[.、)]", s):
            out.append(s)
    return out


def check(path: str, ir: str | None = None):
    text = open(path, encoding="utf-8").read()
    hard, info = [], {}

    blocks = {}
    for name, markers in (("KEEP", KEEP), ("FIX", FIX), ("ADD", ADD), ("WHITE", WHITE)):
        b = block_lines(text, markers)
        blocks[name] = b
        if b is None:
            hard.append(("R1", "/".join(markers), "缺块标题 —— 简报里必须有这一块"))

    keep = items(blocks.get("KEEP"))
    info["保留条目"] = len(keep)
    if blocks.get("KEEP") is not None and len(keep) < 3:
        hard.append(("R2", KEEP[0], "只有 %d 条保留条目（要求 >= 3）—— 草图里画对的东西不止这一两个" % len(keep)))

    fix = items(blocks.get("FIX"))
    info["改对条目"] = len(fix)
    if blocks.get("FIX") is not None:
        if not fix:
            hard.append(("R3", FIX[0], "块里没有条目 —— 那这一块就是空的"))
        elif not any(("→" in x or "改成" in x) for x in fix):
            hard.append(("R3", FIX[0], "条目里没有一条写了「→ 改成…」—— 只写「错了」不改，模型还是会照抄"))

    add = items(blocks.get("ADD"))
    info["补上条目"] = len(add)
    if blocks.get("ADD") is not None and not add:
        hard.append(("R4", ADD[0], "块里没有条目（真没有要补的就写「无」）"))

    white = blocks.get("WHITE")
    if white is not None:
        toks = []
        for ln in white:
            s = ln.strip()
            if not s or s[0] in "·-*•" or re.match(r"^\d+[.、)]", s):
                continue  # 说明性条目不算标签
            for t in re.split(r"[,，、;；\s]+", s):
                t = t.strip().strip("`\"'")
                if t and t not in ("·", "-"):
                    toks.append(t)
        info["白名单标签数"] = len(toks)
        if len(toks) < 2:
            hard.append(("R5", WHITE[0], "白名单里只有 %d 个 token —— 至少要列出图上允许出现的标签" % len(toks)))
    else:
        info["白名单标签数"] = 0

    # R7（作者 2026-10-11「否决权分层」）：位图简报的「必须改对」块里，每一条都必须能
    #   追溯到 IR 里的一条 [HPn] 硬物理。为什么：IR 以前把「物理」和「画法」混在一句里，
    #   写简报的人可以凭自己的口味把作者参考图里有用的元素当成"错的"删掉
    #   （A->C 丢 −b/2/b/2 碰撞几何插图那次）。追溯不到的改动 = 第 2 层外观建议，
    #   不许写成「必须改对」。只在 IR 确实声明了 hard_physics 时启用 —— 老简报不受影响。
    hp_ids = []
    if ir:
        try:
            import yaml
            _d = yaml.safe_load(open(ir, encoding="utf-8").read()) or {}
            for _k, _it in enumerate(_d.get("hard_physics") or [], 1):
                hp_ids.append(str((_it or {}).get("id") or ("HP%d" % _k)))
        except Exception as e:
            hard.append(("R7", "--ir", "IR 读不了：%r" % (e,)))
    if hp_ids:
        info["硬物理条数"] = len(hp_ids)
        _cited, _bad = set(), []
        for x in fix:
            _ms = re.findall(r"\[(HP[^\]]*)\]", x)
            if not _ms:
                _bad.append(x)
            _cited.update(_ms)
        if _bad:
            hard.append(("R7", FIX[0],
                         "%d 条「改对」没写 [HPn] 出处（IR 里只有 %s）—— 追溯不到的改动"
                         "属于第 2 层画法，不许写成「必须改对」（作者 2026-10-11）"
                         % (len(_bad), ",".join(hp_ids))))
        _unk = sorted(c for c in _cited if c not in hp_ids)
        if _unk:
            hard.append(("R8", FIX[0], "引用了 IR 里没有的硬物理 id：%s（IR 里只有 %s）"
                         % (",".join(_unk), ",".join(hp_ids))))

    if not any(k in text for k in ANTI_SIMPLIFY):
        hard.append(("R6", "润色条款",
                     "全文没有「%s」之一 —— 不写死这一条，模型会把「质感到位」理解成「重新画一遍」"
                     % "/".join(ANTI_SIMPLIFY)))

    return hard, info


def main():
    ap = argparse.ArgumentParser(description="位图简报硬闸门（位图 = 润色草图，不是重画）")
    ap.add_argument("brief", nargs="?", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--ir", default=None,
                    help="对应 IR；声明了 hard_physics 时启用 R7（改对必须带 [HPn] 出处）")
    a = ap.parse_args()

    if not a.brief:
        print("[FAIL] 没给简报路径 —— 位图阶段必须交一份带「保留/改对/补上/白名单」的简报")
        return 1

    try:
        hard, info = check(a.brief, a.ir)
    except FileNotFoundError:
        print("[FAIL] 找不到简报：%s" % a.brief)
        return 1

    print("=" * 74)
    print("render_brief_gate -- 位图简报闸门（位图 = 润色草图，不是重画）")
    print("=" * 74)
    print("  简报：%s" % a.brief)
    print("  读数：保留 %(保留条目)d 条 / 改对 %(改对条目)d 条 / 补上 %(补上条目)d 条 / 白名单 %(白名单标签数)d 个标签"
          % info)
    if hard:
        print()
        for code, where, why in hard:
            print("[FAIL] %-3s %-14s %s" % (code, where, why))
        print()
        print("  结果：❌ 有硬伤 —— 位图简报必须写清「保留 / 改对 / 补上 + 标签白名单 + 不许简化」")
    else:
        print()
        print("  结果：✅ 通过")
    print("=" * 74)

    if a.json:
        json.dump({"brief": a.brief, "info": info,
                   "hard": [{"code": c, "where": w, "why": y} for c, w, y in hard]},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
