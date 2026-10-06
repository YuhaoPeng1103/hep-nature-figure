#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ladder_gate —— 提示词阶梯闸门（A → B → C，作者 2026-10-06 要求）
=========================================================================

作者原话：「你要确保后续别的用户使用都是严格按照 ABC 档来的啊」；
同日另一句：「a 档是一句话加参考图……B 档（+ 面板序列 + 标签白名单 + 不许标题/图例）、
C 档（+ 物理增量）按需往上加，加什么由上一轮真画错的地方决定」。

这条以前只写在文档里 —— 拦不住。实测（2026-10-06，一个会话连出 4 轮草图）：
简报从 4148 字符一路涨到 6437 字符，**A 档一次都没跑过**，直接拿累计规格书起手。
所以做成闸门：不合规就**不许调生图接口**（钱花在构图上之前先拦住）。

## 账本

每张图一个账本 `<gen-dir>/ladder.json`：

    {"rungs": [{"rung": "A", "brief": "A_brief.md", "brief_chars": 30,
                "outdir": ".../gen/A", "refs": [...], "seeds": ["1401"],
                "sim_max": 0.36, "sim": {...}, "inc_chars": 0}, ...]}

`<gen-dir>` 由 `--outdir` 往上找最近的、含 `ladder.json` 的目录；找不到就是 `--outdir` 的父目录。

## 硬判据

    L1  顺序不许跳档：第 1 段必须是 A、第 2 段必须是 B、之后都是 C。
    L2  A 档 = 一句话：简报 <= 80 字符 + 至少一张风格参考图；A 档产物**只作诊断**，
        不许进交付链（--stage render 时构图依据来自 A 档的 outdir → 硬伤）。
    L3  B 档必须同时有三样：① 面板序列；② 输出硬约束（标签白名单 / 不要图例标题说明文字）；
        ③ **反抄写**（「不要照抄参考图的内容」这类话必须显式写）——
        不写这句，模型会把风格参考图的**内容**一起搬（实测 A 档 sim 0.36 时，
        图上出现参考图的装置名、脚注换算、图题）。
    L4  每一轮 C 必须带「上一轮错在哪 → 改成什么」那一节，且 <= 3000 字符（增量，不是规格书）；
        简报还得是累积稿（上一轮简报的内容在里面）。
    L5  **不许照抄风格参考图**：A 档以外，任何一段的 ref_sim 最大值 >= 0.60 判硬伤
        （0.30 ~ 0.60 软警）。读数从 <outdir>/calls.jsonl 取。
    L6  出成品位图之前，阶梯必须至少有 A、B、C 三段。
    L7  **风格参考图必须贯穿整条阶梯**：B/C 档的 `--ref` 必须与 A 档一致
        （作者 2026-10-07：「BC档和A档完全不一样啊，BC档是辅助A档物理错误的」）——
        B/C 是 A 的续（只补面板序列 / 输出硬约束 / 物理修正），中途换风格图 = 另起一张。

## 用法

    # 出图前查（ref_guard.py --run 会自动调）
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md --ref <风格图>
    # 出图后登记（ref_guard.py --run 成功退出后自动调）
    python3 scripts/ladder_gate.py --record --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md
    # 单独查账本
    python3 scripts/ladder_gate.py --gen-dir <fig>/gen --stage render

`--waive "理由"` 可放行（理由会被打印出来，交付说明里必须照抄）。
"""

import argparse
import json
import os
import sys
from pathlib import Path

MAX_A_CHARS = 80
MAX_B_CHARS = 1500
MAX_INC_CHARS = 3000
SIM_HARD = 0.60
SIM_SOFT = 0.30

PANEL_MARKERS = ("面板", "从左到右", "a/b/c", "a b c", "三个面板", "两个面板", "四面板")
NO_DECOR_MARKERS = ("不要图例", "不要标题", "不要说明文字", "不成段", "不图例", "不色卡",
                    "不章节编号", "不要边框")
WHITELIST_MARKERS = ("只许出现这些标签", "只允许出现这些标签", "只许写这些标签",
                     "标签白名单", "图上只允许出现", "只许出现", "白名单")
ANTICOPY_MARKERS = ("不要照抄", "不许照抄", "别照抄", "不是要你抄", "不要抄参考",
                    "参考图只给风格", "参考图只当风格", "参考图只作风格", "只学风格",
                    "不要把参考图", "不许把参考图", "不要把参考图里", "照抄参考图")
FAIL_MARKERS = ("错", "改成", "上一轮", "这一轮必须改对", "没做对", "改成什么")
INC_SEPS = ("上一轮画错", "上一轮真画错", "上一版画错", "上一轮（", "上一轮(", "════", "====")


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def find_gen_dir(outdir, explicit=None):
    if explicit:
        return Path(explicit).resolve()
    cur = Path(outdir or ".").resolve()
    for cand in [cur, cur.parent, cur.parent.parent, cur.parent.parent.parent]:
        if (cand / "ladder.json").exists():
            return cand
    return cur.parent


def ledger_path(gen_dir):
    return Path(gen_dir) / "ladder.json"


def load_ledger(gen_dir):
    p = ledger_path(gen_dir)
    if not p.exists():
        return {"version": 1, "gen_dir": str(gen_dir), "rungs": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "gen_dir": str(gen_dir), "rungs": []}


def save_ledger(gen_dir, led):
    p = ledger_path(gen_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def rung_name(idx):
    return "ABC"[idx] if idx < 3 else "C"


def read_calls(outdir):
    p = Path(outdir or "") / "calls.jsonl"
    if not p.exists():
        return None
    sims, seeds, refs, content_refs, stages = {}, [], [], [], set()
    for line in _read(p).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        stages.add(d.get("stage"))
        if d.get("seed") is not None:
            seeds.append(d["seed"])
        for r in d.get("refs") or []:
            if r not in refs:
                refs.append(r)
        for r in d.get("content_refs") or []:
            if r not in content_refs:
                content_refs.append(r)
        for k, v in (d.get("ref_sim") or {}).items():
            if isinstance(v, (int, float)):
                sims[k] = max(sims.get(k, -9.0), float(v))
    return {"sim": sims, "sim_max": (max(sims.values()) if sims else None),
            "seeds": seeds, "refs": refs, "content_refs": content_refs,
            "stages": sorted(x for x in stages if x)}


def extract_increment(text):
    """取「上一轮错在哪 -> 改成什么」那一节（C 档的增量）。"""
    best = -1
    for s in INC_SEPS:
        i = text.rfind(s)
        if i > best:
            best = i
    return text[best:].strip() if best >= 0 else ""


def brief_shape(rung, text, refs, prev_text):
    v, w = [], []
    n = len(text.strip())
    if rung == "A":
        if n > MAX_A_CHARS:
            v.append("L2 A 档必须是一句话（<= %d 字符），这份简报 %d 字符 —— A 档是用来"
                     "看模型对这个题材的先验的，不是交付稿；要加约束请走 B 档。" % (MAX_A_CHARS, n))
        if not refs:
            v.append("L2 A 档必须带风格参考图（--ref）：只给一句话、不给风格图，会退化成通用信息图。")
    elif rung == "B":
        if n < 40:
            v.append("L3 B 档太短（%d 字符）：B = A + 面板序列 + 输出硬约束。" % n)
        if n > MAX_B_CHARS:
            v.append("L3 B 档太长（%d 字符 > %d）：这一档只加面板序列与输出硬约束，"
                     "物理增量留给 C 档。" % (n, MAX_B_CHARS))
        if not any(k in text for k in PANEL_MARKERS):
            v.append("L3 B 档缺【面板序列】（「面板 a/b/c」「从左到右」这类）。")
        if not any(k in text for k in WHITELIST_MARKERS + NO_DECOR_MARKERS):
            v.append("L3 B 档缺【输出硬约束】（标签白名单 / 不要图例标题说明文字）。")
        if not any(k in text for k in ANTICOPY_MARKERS):
            v.append("L3 B 档缺【反抄写】：必须显式写「不要照抄参考图的内容 / 参考图只给风格」——"
                     "不写这句，模型会把风格参考图的**内容**（装置名、脚注、图题）一起搬过来。")
    else:
        inc = extract_increment(text)
        if not inc:
            v.append("L4 C 档缺【上一轮真画错的清单】：简报里要有"
                     "「上一轮画错的地方 → 这一轮必须改对」那一节。")
        else:
            if len(inc) > MAX_INC_CHARS:
                v.append("L4 增量那一节太长（%d 字符 > %d）：C 档只补上一轮真画错的那几条，"
                         "不是再发一次规格书。" % (len(inc), MAX_INC_CHARS))
            if not any(k in inc for k in FAIL_MARKERS):
                v.append("L4 增量那一节看不出「错在哪 → 改成什么」。")
        if prev_text and prev_text.strip() and prev_text.strip() not in text:
            w.append("L4 这一轮简报不是累积稿（上一轮简报的内容不在里面）——"
                     "确认是有意重写，还是漏了。")
    return v, w


def check_sim(rung, calls, label):
    v, w = [], []
    if not calls:
        w.append("L5 %s 没找到 calls.jsonl —— 照抄判据（ref_sim）没测成。" % label)
        return v, w
    sm = calls.get("sim_max")
    if sm is None:
        return v, w
    if rung != "A" and sm >= SIM_HARD:
        v.append("L5 %s 内容照抄风格参考图：ref_sim = %.2f >= %.2f。" % (label, sm, SIM_HARD))
    elif sm >= SIM_SOFT:
        w.append("L5 %s ref_sim = %.2f（%.2f ~ %.2f 偏高）—— 看一眼像不像参考图的内容。"
                 % (label, sm, SIM_SOFT, SIM_HARD))
    return v, w


def order_checks(led):
    rungs = led.get("rungs") or []
    names = [r.get("rung") for r in rungs]
    want = [rung_name(i) for i in range(len(names))]
    if names != want:
        return ["L1 阶梯跳档：账本里是 %s，必须是 %s（A → B → C…）。" % (names, want)]
    return []


def precheck(gen_dir, brief_path, outdir, refs, stage):
    led = load_ledger(gen_dir)
    rungs = led.get("rungs") or []
    v, w = order_checks(led), []
    text = _read(brief_path) if brief_path else ""
    if brief_path and not text:
        v.append("L0 简报文件读不到：%s" % brief_path)
    idx = len(rungs)
    rung = rung_name(idx)
    if outdir:
        od = os.path.abspath(outdir)
        for r in rungs:
            if r.get("outdir") and os.path.abspath(r["outdir"]) == od:
                v.append("L1 这个 outdir 已经登记过第 %s 段了 —— 换 outdir，或先删账本里那一段。"
                         % r.get("rung"))
    prev = rungs[-1] if rungs else None
    prev_text = ""
    if prev and prev.get("brief"):
        bp = Path(prev["brief"])
        prev_text = _read(bp if bp.is_absolute() else Path(gen_dir) / bp)
    if not refs and prev:
        refs = prev.get("refs") or []
    # L7 风格参考图必须贯穿整条阶梯（作者 2026-10-07：「B/C 是辅助 A 档物理错误的」）
    if rungs:
        a_refs = sorted(os.path.basename(x) for x in (rungs[0].get("refs") or []))
        now_refs = sorted(os.path.basename(x) for x in (refs or []))
        if a_refs and now_refs and a_refs != now_refs:
            v.append("L7 风格参考图与本条阶梯的 A 档不一致：A 档用 %s，这一轮用 %s —— "
                     "B/C 档是 A 档的续（只补面板序列 / 输出硬约束 / 物理修正），"
                     "中途换风格图 = 另起一张，就不是「辅助 A 档」了。" % (a_refs, now_refs))
    bv, bw = brief_shape(rung, text, refs, prev_text)
    v += bv
    w += bw
    if stage == "render":
        names = [r.get("rung") for r in rungs]
        if not ("A" in names and "B" in names and "C" in names):
            v.append("L6 出成品位图之前阶梯必须至少有 A、B、C 三段（现在只有 %s）。" % names)
        for r in rungs:
            if r.get("rung") == "A":
                continue
            sm = r.get("sim_max")
            if sm is not None and sm >= SIM_HARD:
                v.append("L5 第 %s 段照抄了风格参考图（ref_sim %.2f）。" % (r.get("rung"), sm))
        if outdir:
            od = os.path.abspath(outdir)
            for r in rungs:
                if r.get("rung") == "A" and r.get("outdir") and os.path.abspath(r["outdir"]) == od:
                    v.append("L2 构图依据来自 A 档（%s）—— A 档只作诊断，不许进交付链。" % od)
    return rung, v, w, idx


def do_record(gen_dir, brief_path, outdir, refs, add=None):
    led = load_ledger(gen_dir)
    rungs = led.get("rungs") or []
    idx = len(rungs)
    rung = rung_name(idx)
    text = _read(brief_path) if brief_path else ""
    inc = extract_increment(text)
    calls = read_calls(outdir) if outdir else None
    rel_add = None
    if add and Path(add).exists():
        try:
            rel_add = os.path.relpath(Path(add).resolve(), Path(gen_dir)).replace("\\", "/")
        except Exception:
            rel_add = str(Path(add).resolve())
    entry = {
        "rung": rung,
        "brief": (os.path.relpath(Path(brief_path).resolve(), Path(gen_dir)).replace("\\", "/")
                  if brief_path else None),
        "brief_chars": len(text.strip()),
        "outdir": str(Path(outdir).resolve()) if outdir else None,
        "refs": (calls or {}).get("refs") or list(refs or []),
        "content_refs": (calls or {}).get("content_refs") or [],
        "seeds": (calls or {}).get("seeds") or [],
        "sim": (calls or {}).get("sim") or {},
        "sim_max": (calls or {}).get("sim_max"),
        "inc_chars": len(inc),
        "add": rel_add,
    }
    rungs.append(entry)
    led["rungs"] = rungs
    led["gen_dir"] = str(Path(gen_dir).resolve())
    p = save_ledger(gen_dir, led)
    return entry, p


def main():
    ap = argparse.ArgumentParser(
        description="提示词阶梯闸门 A → B → C（见文件头）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gen-dir", default=None, help="账本目录（缺省由 --outdir 往上找）")
    ap.add_argument("--outdir", default=None, help="这一轮出图的目录")
    ap.add_argument("--brief", default=None, help="这一轮的简报 .md")
    ap.add_argument("--add", default=None, help="C 档：上一轮的错误清单 .md（登记时可给）")
    ap.add_argument("--ref", action="append", default=[], help="这一轮的风格参考图")
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch")
    ap.add_argument("--record", action="store_true", help="出图成功后登记这一段")
    ap.add_argument("--waive", default=None, help="确实要放行时的理由（会打印出来）")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    gen_dir = find_gen_dir(a.outdir or ".", a.gen_dir)
    print("=" * 70)
    print("ladder_gate —— 提示词阶梯闸门（A → B → C）")
    print("=" * 70)
    print("账本 : %s" % ledger_path(gen_dir))

    if a.record:
        entry, p = do_record(gen_dir, a.brief, a.outdir, a.ref, a.add)
        n = len(load_ledger(gen_dir)["rungs"])
        print("已登记第 %d 段：%s 档 | 简报 %d 字符 | 增量 %d 字符 | ref_sim_max=%s"
              % (n, entry["rung"], entry["brief_chars"], entry["inc_chars"], entry["sim_max"]))
        print("账本 -> %s" % p)
        return 0

    rung, v, w, idx = precheck(gen_dir, a.brief, a.outdir, a.ref, a.stage)
    print("这一轮 : 第 %d 段 = %s 档%s" % (idx + 1, rung,
          "（A 档只作诊断，不许进交付链）" if rung == "A" else ""))
    for x in w:
        print("  [warn] %s" % x)
    if v:
        for x in v:
            print("  [FAIL] %s" % x)
        if a.waive:
            print("  ★ --waive %r：放行。理由必须照抄进交付说明。" % a.waive)
            v = []
        else:
            print("-" * 70)
            print("结论：阶梯不合规 —— 不许调生图接口。")
            print("  阶梯：A（一句话 + 风格图，只作诊断）→ B（+ 面板序列 + 输出硬约束 + 反抄写）"
                  "→ C（只补上一轮真画错的）")
            if a.json:
                Path(a.json).write_text(json.dumps(
                    {"gen_dir": str(gen_dir), "rung": rung, "index": idx,
                     "violations": v, "warnings": w}, ensure_ascii=False, indent=1), encoding="utf-8")
            return 2
    print("-" * 70)
    print("结论：阶梯合规（第 %d 段 = %s 档）。" % (idx + 1, rung))
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"gen_dir": str(gen_dir), "rung": rung, "index": idx,
             "violations": v, "warnings": w}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
