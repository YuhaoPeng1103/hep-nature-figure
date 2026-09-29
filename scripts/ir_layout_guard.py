#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ir_layout_guard -- 查「IR 有没有把整张版式写死」

为什么需要它（实测，2026-09-29）：
    ir_to_genbrief.py 会把下面这些字段**逐字**搬进给图像模型的简报：
        composition.分区        -> 每个面板的毫米坐标（"slab a x 6.0-58.3 mm ..."）
        composition.元素布局    -> 每个元素的**归一化锚点**（脚本注释还写「以本表为准」）
        elements[].params       -> 绝对画布毫米（tx_mm=[6.0, 66.0, 126.0] ...）
        style.conventions       -> **逐面板布局脚本**（"Panel a: ..."/"Panel b: ..."）、
                                   每面板两行图注、过渡箭头、以及
                                   "This figure has exactly THREE panels in ONE ROW"
    后果：同一份物理 + 任何 seed，模型拿到的是一份**已经排好版**的施工图 ——
          出草图时唯一的变量只剩 seed。量出来的：v3 草图内部两两版式相关 0.782，
          v4（只换参考图、IR 没动）0.803。也就是说这条才是「每次一样」的主因。

怎么判：不信 IR 的字面，**把简报真的编译出来**再扫（简报才是模型看到的东西）。

    python scripts/ir_layout_guard.py <IR> [--stage sketch|render] [--brief out.md]

退出码 0 = 版式没被写死；1 = 写死了（附命中位置和原文）。
确实**有意**要固定版式时（例如复现论文图 A 类任务），加 --allow-layout-lock "理由"，
它会把「有意固定」写进报告，但仍然要求你在交付说明里写清楚。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# 简报里出现这些 = 版式被写死
BRIEF_SIGNS = [
    ("composition.分区", re.compile(r"^\s*分区：", re.M),
     "composition.分区 把每个面板的毫米坐标写进了简报"),
    ("composition.元素布局", re.compile(r"^\s*各元素位置（IR 的 composition\.元素布局", re.M),
     "composition.元素布局 把每个元素的归一化锚点写进了简报"),
    ("composition.元素布局", re.compile(r"^\s*各元素位置（相对画布[^\n]*\n[ \t]*·[ \t]*\S", re.M),
     "简报里带一张「各元素位置」表（表头后面真的跟了条目）"),
    ("style.conventions", re.compile(r"^\s*·\s*Panel\s+[A-Za-z0-9]\s*[:：]", re.M | re.I),
     "style.conventions 里有**逐面板布局脚本**（Panel a: ... / Panel b: ...）"),
    ("style.conventions", re.compile(r"exactly\s+\w+\s+panels?\s+in\s+one\s+row", re.I),
     "style.conventions 里写死了面板数量与排布方式"),
    ("style.conventions", re.compile(r"^\s*·\s*(Panel captions|Two chunky .*transition arrows)", re.M | re.I),
     "style.conventions 里写死了图注位置与过渡箭头"),
]

# IR 里出现这些键 = 绝对画布坐标（版式）
ABS_PARAM = re.compile(r"\b(cx|cy|tx|ty|x|y|x1|y1|origin|points)_(mm|px|pt)\b", re.I)


def find_skill():
    # 本脚本自己所在的仓库根排最前：装进 skill 的 scripts/ 之后不设 HEP_SKILL 也能用
    cands = [os.environ.get("HEP_SKILL"),
             os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
             os.path.expanduser("~/.codex/skills/hep-nature-figure"),
             os.path.join(os.environ.get("CODEX_HOME", ""), "skills", "hep-nature-figure")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "scripts", "ir_to_genbrief.py")):
            return c
    return None


def scan_ir(ir_path):
    if yaml is None:
        return []
    try:
        d = yaml.safe_load(Path(ir_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    hits = []
    comp = d.get("composition") or {}
    if comp.get("分区"):
        hits.append(("composition.分区", "IR 里有 composition.分区"))
    if comp.get("元素布局"):
        hits.append(("composition.元素布局", "IR 里有 composition.元素布局（归一化锚点）"))
    for e in (d.get("elements") or []):
        ps = e.get("params") or {}
        for k in ps:
            if ABS_PARAM.fullmatch(str(k)):
                hits.append(("elements[%s].params.%s" % (e.get("id"), k),
                             "元素 params 带绝对画布坐标 %s=%s" % (k, ps[k])))
    for c in ((d.get("style") or {}).get("conventions") or []):
        s = str(c)
        if re.search(r"^\s*\**\s*Panel\s+[A-Za-z0-9]\s*[:：]", s, re.I):
            hits.append(("style.conventions", "约定里含逐面板布局脚本：" + s[:70] + "..."))
        elif re.search(r"exactly\s+\w+\s+panels?\s+in\s+one\s+row", s, re.I):
            hits.append(("style.conventions", "约定里写死了面板数量与排布：" + s[:70] + "..."))
    return hits


def compile_brief(ir_path, stage, out=None):
    skill = find_skill()
    if not skill:
        return None, "找不到 skill（设 HEP_SKILL 环境变量）"
    dst = Path(out) if out else Path(tempfile.mkdtemp()) / "brief.md"
    r = subprocess.run([sys.executable, os.path.join(skill, "scripts", "ir_to_genbrief.py"),
                        str(ir_path), "--stage", stage, "-o", str(dst)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not dst.exists():
        return None, (r.stdout or "") + (r.stderr or "")
    return dst.read_text(encoding="utf-8"), None


def main():
    ap = argparse.ArgumentParser(description="查 IR 有没有把版式写死（见文件头）")
    ap.add_argument("ir")
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch")
    ap.add_argument("--brief", default=None, help="顺便把简报写到这个路径")
    ap.add_argument("--allow-layout-lock", default=None,
                    help="有意固定版式时的理由（复现论文图这类 A 类任务）；给了就只警告不算失败")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    hits = scan_ir(a.ir)
    brief, err = compile_brief(a.ir, a.stage, a.brief)
    brief_hits = []
    if brief is None:
        print("  ⚠️ 简报没编译出来（%s）—— 只查 IR 字面" % (err or "?").strip()[:200])
    else:
        for who, rx, why in BRIEF_SIGNS:
            m = rx.search(brief)
            if m:
                ln = brief[:m.start()].count("\n") + 1
                line = brief.splitlines()[ln - 1].strip()
                brief_hits.append((who, ln, line[:130], why))

    print("=" * 72)
    print("ir_layout_guard -- IR：%s（stage=%s）" % (a.ir, a.stage))
    print("=" * 72)
    if not hits and not brief_hits:
        print("  结果：✅ 版式没被写死 —— 面板数量/排布/元素坐标都留给插画师")
    else:
        print("  结果：❌ IR 把版式写死了（%d 处 IR 字面 + %d 处简报命中）"
              % (len(hits), len(brief_hits)))
        for who, why in hits:
            print("    · [IR] %-28s %s" % (who, why))
        for who, ln, line, why in brief_hits:
            print("    · [简报 L%-4d] %-22s %s" % (ln, who, why))
            print("        > %s" % line)
        print()
        print("  修法：把这些从 IR 里删掉/改成比率描述 ——")
        print("    · 版式属于 elements + geometry_constraints，不属于 composition 的毫米坐标；")
        print("    · style.conventions 只该写**风格与材质语言**；")
        print("    · 只保留「因为它是物理才保留」的构图事实（例如视角、画在带厚度的薄板上）。")
    if a.allow_layout_lock:
        print()
        print("  ★ --allow-layout-lock：已声明为**有意固定版式**，理由：%s" % a.allow_layout_lock)
        print("    交付说明里必须写明这一点，并说明版式从哪来（复现哪张源图）。")

    if a.json:
        import json
        Path(a.json).write_text(json.dumps(
            {"ir": a.ir, "stage": a.stage,
             "ir_hits": [{"where": w, "why": y} for w, y in hits],
             "brief_hits": [{"where": w, "line": l, "text": t, "why": y} for w, l, t, y in brief_hits],
             "allowed": bool(a.allow_layout_lock), "ok": not (hits or brief_hits)},
            ensure_ascii=False, indent=2), encoding="utf-8")

    if (hits or brief_hits) and not a.allow_layout_lock:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())