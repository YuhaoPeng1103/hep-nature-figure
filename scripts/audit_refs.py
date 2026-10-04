#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_refs -- 把全工作区的历史出图调用过一遍 ref_guard，找出还有哪些批次违反了
「出草图不给自家成品当参考 / skill 库只是风格参考」这条规则。

    python3 scripts/audit_refs.py                    # 扫全部 calls.jsonl
    python3 scripts/audit_refs.py --root collective_flow
    python3 scripts/audit_refs.py --json out/_ref_audit.json --show-ok

只读 gen_figure.py 落下的 calls.jsonl（stage / refs / content_refs），不读图片。
skill 自己的 demo 记录（路径里含 hep-nature-figure/）会被跳过 —— 那是技能作者自己的。

★ 2026-10-01：记录里的 refs 是「--content-ref + --ref」的**并集**，直接当 --ref 读会把
  每一条合规的 render 记录误判成 SAME_FILE。现在先用 split_refs() 拆回两个列表（见该函数）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ref_guard as RG


def collect(root: Path, skip_skill=True):
    for p in sorted(root.rglob("calls.jsonl")):
        s = str(p).replace("\\", "/")
        if skip_skill and "hep-nature-figure/" in s:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln in txt.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                yield p, json.loads(ln)
            except json.JSONDecodeError:
                continue


def _norm(p):
    return os.path.normcase(os.path.normpath(str(p)))


def split_refs(rec):
    """把记录里的 refs 拆回 (--ref, --content-ref)。

    ★ 为什么必须拆（2026-10-01 修）：gen_figure.py 落盘时
        refs = [str(r) for r in all_ref]，而 all_ref = a.content_ref + a.ref ——
    也就是 refs 是「构图参考 + 风格参考」的**并集**。直接把它当 --ref 读，
    于是**每一条合规的 render 记录**都会被判成
        OWN_SKETCH + SAME_FILE（「同一张图同现两槽」），
    而它其实只是把草图放在了 --content-ref 里 —— 假阳性，不是违规。
    （实测：collective_flow/gen/v8/render_p1、render_p2 都这样被误判。）

    拆法：content_refs 里出现的文件，从 refs 里**各扣掉一次**。
    真的两边都用的那张会在 refs 里出现**两次**（一次 content、一次 style），
    扣掉一次后剩下的那一次仍留在 style 里 —— 于是照旧被判 SAME_FILE。
    """
    content = list(rec.get("content_refs") or [])
    pool = list(rec.get("refs") or [])
    left = [_norm(c) for c in content]
    style = []
    for p in pool:
        n = _norm(p)
        if n in left:
            left.remove(n)
        else:
            style.append(p)
    return style, content


def main():
    ap = argparse.ArgumentParser(description="全工作区参考图角色对账")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", default=None)
    ap.add_argument("--show-ok", action="store_true", help="通过的批次也逐条列出")
    a = ap.parse_args()
    root = Path(a.root).resolve()

    runs, bad = {}, []
    n_rec = n_bad = 0
    for path, rec in collect(root):
        stage = rec.get("stage") or "sketch"
        style, content = split_refs(rec)
        if not style and not content:
            continue
        n_rec += 1
        v, w = RG.check(stage, style, content, str(root), base=str(path.parent))
        try:
            key = str(path.parent.relative_to(root))
        except ValueError:
            key = str(path.parent)
        if key in ("", "."):
            key = "."
        e = runs.setdefault(key, {"runs": 0, "bad": 0, "kinds": set(), "why": None, "eg": None,
                                  "stages": set(), "warn": 0})
        e["runs"] += 1
        e["stages"].add(stage)
        e["warn"] += len(w)
        if v:
            e["bad"] += 1
            n_bad += 1
            for _r, _p, k, why in v:
                e["kinds"].add(k)
            if e["why"] is None:
                e["why"] = v[0][3]
                p0 = v[0][1]
                if os.path.exists(RG.resolve(p0, str(path.parent))):
                    e["eg"] = p0
            if key not in [k for k, _ in bad]:
                bad.append((key, v))

    print("=" * 78)
    print("audit_refs -- %d 条出图记录，%d 条违反「参考图角色」规则" % (n_rec, n_bad))
    print("=" * 78)
    if bad:
        print("\n❌ 违反的批次（已经发生的，不回滚；目的是别再发生）：")
        for key, v in bad:
            kinds = sorted({k for _r, _p, k, _w in v})
            print("  · %-40s %s" % (key, ",".join(kinds)))
            print("      %s" % v[0][3])
            if runs[key].get("eg"):
                print("      例：%s" % runs[key]["eg"])
        print("\n  ★ 从今往后出图一律走：")
        print("      python3 scripts/ref_guard.py --run -- <gen_figure.py 的原参数>")
    else:
        print("\n✅ 没有违反的批次。")
    oklist = [(k, e) for k, e in sorted(runs.items()) if e["bad"] == 0]
    if oklist:
        print("\n✅ 通过的批次：")
        for k, e in oklist:
            print("  · %-40s %d 条（stage %s）%s"
                  % (k, e["runs"], ",".join(sorted(e["stages"])),
                     "  [%d 条警告]" % e["warn"] if e["warn"] else ""))
    if a.show_ok:
        pass

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"records": n_rec, "violations": n_bad,
             "runs": {k: {"runs": v["runs"], "bad": v["bad"], "warnings": v["warn"],
                          "kinds": sorted(v["kinds"])} for k, v in runs.items()}},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n已写出 %s" % a.json)
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
