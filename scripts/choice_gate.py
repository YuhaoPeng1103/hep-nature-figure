#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
choice_gate -- 「客户挑草图」的硬闸门：没有客户回执，就不许出成品位图。

为什么需要它（2026-09-29）：
    出成品位图要花钱，草图是全链最便宜的返工点，而「哪张更像你要讲的物理」
    只有提需求的人知道。skill 第 4.5 步本来就写着这里是**交接点、要停下来问**；
    sketch_handoff.py 也把材料（candidates.md / 4up / 可编辑 SVG）都产出来了 ——
    但缺两样东西：
      (1) 一个**客户能实际点的入口**（不是让客户在仓库里翻 markdown）→ make_picker.py
      (2) 一道**机械闸门**：没有客户回执就不许进第 5 步 → 本脚本
    实测代价：collective_flow v3 那次 handoff/ 里材料全有，但工作区里**找不到任何
    客户回执**，最后是 agent 自己挑了 chosen_sketch.png。也就是「问过」这件事
    根本没发生，而流程一点没拦住。

回执文件（handoff/choice.json）长这样：
    {
      "code": "V5-cand_06",          # 选择码（pick.html 上点出来的那串）
      "candidate": "cand_06",
      "png": "gen/v5/candB/sketch_s94_clean.png",
      "svg": "gen/v5/handoff/cand_06.svg",
      "decided_by": "client",        # 必须是 client / 作者 / 客户，不能是 agent
      "reply": "用第 6 张，B 那个版式", # 客户**原话**
      "decided_at": "2026-09-29T18:22:00+08:00"
    }

用法：
    # 客户回话之后，由我写回执（--record 会把上面那些字段补全并落盘）
    python scripts/choice_gate.py --handoff collective_flow/gen/v5/handoff \
        --record --code V5-cand_06 --reply "用第 6 张，B 那个版式" --by client

    # 出成品位图之前必须查（ref_guard.py --run 在 stage=render 时会自动带上它）
    python scripts/choice_gate.py --choice collective_flow/gen/v5/handoff/choice.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

CLIENT_WORDS = {"client", "customer", "author", "user", "客户", "作者", "用户", "甲方"}
AGENT_WORDS = {"agent", "assistant", "ai", "auto", "自动", "我自己", "我", "codex"}
MANUAL_TAKEOVER = "manual"


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def find_handoff_for(start: Path):
    """从某个目录往上/往里找 handoff.json。"""
    start = Path(start).resolve()
    for d in [start] + list(start.parents)[:4]:
        for cand in (d / "handoff", d):
            if (cand / "handoff.json").exists():
                return cand
    return None


def check(choice_path: Path, handoff_dir: Path | None = None):
    """返回 (ok, violations, info)"""
    v, info = [], {}
    if not choice_path or not Path(choice_path).exists():
        return False, [("choice.json", "缺文件",
                        "找不到客户回执 —— 还没让客户挑，或者挑了没落盘。"
                        "先跑 tools/make_picker.py 出 pick.html，客户点完再 --record 写回执")], info
    try:
        c = load_json(choice_path)
    except Exception as e:
        return False, [("choice.json", "读不了", "%s: %s" % (type(e).__name__, e))], info

    hd = Path(handoff_dir) if handoff_dir else find_handoff_for(Path(choice_path).parent)
    info["handoff"] = str(hd) if hd else None
    cands = {}
    if hd and (hd / "handoff.json").exists():
        for x in load_json(hd / "handoff.json").get("candidates", []):
            cands[x["cid"]] = x

    cid = c.get("candidate")
    if not cid:
        v.append(("choice.json", "缺 candidate", "回执里没有 candidate 字段"))
    elif cands and cid not in cands:
        v.append(("choice.json", "candidate 不存在",
                  "%s 不在 %s 的候选表里（可选：%s）" % (cid, hd, ", ".join(sorted(cands)))))
    else:
        info["candidate"] = cid
        x = cands.get(cid) or {}
        bad = len(x.get("hard") or [])
        if bad:
            v.append(("choice.json", "候选有硬伤",
                      "%s 在闸口①里有 %d 处硬伤，不能作为成品依据：%s"
                      % (cid, bad, "; ".join(str(h) for h in x.get("hard")))))
        info["hard"] = bad
        info["png"] = x.get("src") or c.get("png")
        info["svg"] = x.get("svg") or c.get("svg")

    by = str(c.get("decided_by") or "").strip().lower()
    if not by:
        v.append(("choice.json", "缺 decided_by", "回执里没有 decided_by —— 谁拍的板？"))
    elif by in AGENT_WORDS:
        v.append(("choice.json", "拍板人是 agent",
                  "decided_by=%r：选择必须是**客户**做的（作者 2026-09-29）。"
                  "agent 自己挑不算过闸口" % c.get("decided_by")))
    elif by not in CLIENT_WORDS and by != MANUAL_TAKEOVER:
        v.append(("choice.json", "decided_by 不认识",
                  "decided_by=%r；只认 %s（或 %s 表示客户明确说「你定」）"
                  % (c.get("decided_by"), "/".join(sorted(CLIENT_WORDS)), MANUAL_TAKEOVER)))

    rep = str(c.get("reply") or "").strip()
    if not rep:
        v.append(("choice.json", "缺 reply",
                  "回执里没有客户原话 —— 要有客户说的那一句，便于事后对账"))
    if not c.get("decided_at"):
        v.append(("choice.json", "缺 decided_at", "回执里没有时间戳"))

    for k in ("png",):
        p = info.get(k)
        if p and not Path(p).exists():
            q = (hd / p) if hd else Path(p)
            if not q.exists():
                v.append(("choice.json", "位图找不到", "%s 不存在" % p))
    return (not v), v, info


def record(handoff_dir: Path, code, reply, by, png=None, svg=None, when=None):
    hd = Path(handoff_dir).resolve()
    hj = hd / "handoff.json"
    if not hj.exists():
        raise SystemExit("找不到 %s" % hj)
    d = load_json(hj)
    cands = {x["cid"]: x for x in d.get("candidates", [])}
    cid = None
    if code:
        cid = code.split("-")[-1]
    if cid not in cands:
        raise SystemExit("选择码 %r 认不出来；可选：%s" % (code, ", ".join(sorted(cands))))
    x = cands[cid]
    rec = {"code": code, "candidate": cid,
           "png": png or x.get("src"), "svg": svg or x.get("svg"),
           "decided_by": by, "reply": str(reply),
           "decided_at": when or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "hard": x.get("hard") or [], "soft": x.get("soft") or [],
           "ir": d.get("ir")}
    (hd / "choice.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return hd / "choice.json", rec


def main():
    ap = argparse.ArgumentParser(description="客户挑草图的硬闸门（见文件头）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--choice", help="choice.json 的路径")
    g.add_argument("--handoff", help="handoff 目录（配合 --record 写回执）")
    ap.add_argument("--record", action="store_true", help="写回执")
    ap.add_argument("--code", help="选择码，例如 V5-cand_06")
    ap.add_argument("--reply", default="", help="客户原话")
    ap.add_argument("--by", default="client", help="谁拍的板：client / 作者 / manual(客户说「你定」)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    if a.record:
        p, rec = record(a.handoff, a.code, a.reply, a.by)
        print("已写出 %s" % p)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return 0

    ch = a.choice or (str(Path(a.handoff) / "choice.json") if a.handoff else None)
    ok, v, info = check(Path(ch) if ch else None, Path(a.handoff) if a.handoff else None)
    print("=" * 74)
    print("choice_gate -- 客户挑草图")
    print("=" * 74)
    if info.get("candidate"):
        print("  候选      : %s（闸口① 硬伤 %s）" % (info["candidate"], info.get("hard")))
        print("  位图      : %s" % info.get("png"))
    if info.get("handoff"):
        print("  handoff   : %s" % info["handoff"])
    print("")
    if v:
        print("  结果：❌ 不许出成品位图（%d 条）" % len(v))
        for who, k, why in v:
            print("    · [%s] %s" % (k, why))
        print("")
        print("  怎么让客户挑：")
        print("    1) python tools/make_picker.py --handoff <handoff 目录> --tag <TAG>")
        print("       -> <handoff>/pick.html （客户双击就能看、能点、能拿到选择码）")
        print("    2) 把 pick_sheet.png 贴给客户，请客户回一个选择码")
        print("    3) 客户回话后：")
        print("       python scripts/choice_gate.py --handoff <handoff 目录> --record \\")
        print("           --code <TAG>-cand_NN --reply \"客户原话\" --by client")
    else:
        print("  结果：✅ 有客户回执，可以进第 5 步")
    if a.json:
        Path(a.json).write_text(json.dumps({"ok": ok, "info": info,
                                            "violations": [{"kind": k, "why": w} for _a, k, w in v]},
                                           ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())