# -*- coding: utf-8 -*-
"""element_list.py -- 「出草图前先把 IR 的元素清单贴给客户过目」的编译 + 回执 + 闸门

作者 2026-10-15 原话：
  「出草图前，我把 IR 的**元素清单**（中文 5–10 行）贴出来给你过目/加项，你点头我才开跑」

为什么要这一步：AGENTS.md §0.1 那条实测教训 —— 简报的「画面元素」与「标签白名单」是闭集合，
会**静默删东西**（实测 fig_jet_quench：A 档两侧的入射核子簇整块消失）。清单贴在出草图**之前**，
就是让"图里该有几个物体"这件事在烧 API 的钱之前被人看一遍。

用法
----
    # ① 编译并贴给客户（默认写到 IR 同目录）
    python scripts/element_list.py --ir <IR.yaml>
    python scripts/element_list.py --ir <IR.yaml> --outdir <dir> --with-physics

    # ② 客户点头/加项后落盘回执（--by 只认客户；写 agent/auto/codex 一律判失败）
    python scripts/element_list.py --ir <IR.yaml> --record \
           --reply "可以，另外把马赫锥加上" --by client --add "马赫锥 ×1"

    # ③ 闸门自查（没回执 = 非零退出）
    python scripts/element_list.py --ir <IR.yaml> --check

产物（默认落在 IR 同目录）
--------------------------
    element_list.md    给人看的中文元素清单（就是贴进聊天窗口那一份）
    element_list.json  机器读的（每个元素的 id / z / 名称 / 数量 / 材质 / 形状）
    element_ack.json   客户回执（--record 才写）。ref_guard.py 在 --stage sketch 会查它。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

try:
    from _console import init_console  # type: ignore
    init_console()
except Exception:
    pass

# 只认客户本人 —— 与 choice_gate.py 同一张表
CLIENT_BY = {"client", "customer", "author", "user", "客户", "作者", "用户", "甲方"}
MANUAL_BY = {"manual"}

COUNT_KEYS = ("count", "数量", "个数", "n")


def load_ir(path):
    import yaml
    d = yaml.safe_load(io.open(path, encoding="utf-8").read()) or {}
    return d if isinstance(d, dict) else {}


def _text(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _short(s, n):
    s = _text(s)
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _count_of(el, params):
    """数量：优先读显式字段；否则**只认元素自己 name 里的 ×N / 三轴 这类**。

    ★ 绝不去 physics_role / primitive 里找数量：那里的"两个核"、"两组直线"是在描述
      **场景**，不是这个元素自己的个数。实测（UPC）：读 physics_role 会把"反应平面"
      误判成 ×2、而另一个核又误判成 ×1 —— 同一类物体给出不同个数。
      name 里的 ×N 是 IR 作者自己标的，才可信（如"速度箭头 ×2"）。
    """
    for src in (el, params):
        if isinstance(src, dict):
            for k in COUNT_KEYS:
                if k in src:
                    # 认 "3" 也认 "3 道" / "x2" 这种带单位/前缀的写法（取第一个整数）
                    mm = re.search(r"\d+", str(src[k]))
                    if mm:
                        v = int(mm.group(0))
                        if v > 0:
                            return v
    name = _text(el.get("name"))
    m = re.search(r"[×xX]\s*(\d+)", name)
    if m:
        return int(m.group(1))
    for cn, num in (("三轴", 3), ("三支", 3), ("三根", 3),
                    ("两条", 2), ("两支", 2), ("一对", 2), ("两个", 2)):
        if cn in name:
            return num
    return 1


def compile_list(ir):
    """IR -> (行列表, 每个元素的 dict)。行就是贴给客户看的那 5–10 行。"""
    els = ir.get("elements") or []
    if not isinstance(els, list):
        els = []
    rows, meta = [], []
    for i, el in enumerate(els):
        if not isinstance(el, dict):
            continue
        eid = _text(el.get("id")) or ("E%d" % (i + 1))
        name = _text(el.get("name")) or eid
        params = el.get("params") if isinstance(el.get("params"), dict) else {}
        try:
            z = int(el.get("z"))
        except Exception:
            z = i + 1
        cnt = _count_of(el, params)
        prim = _short(el.get("primitive"), 46)
        mat = _short(el.get("material"), 52)
        bits = []
        if prim:
            bits.append(prim)
        if mat:
            bits.append(mat)
        for k, v in list(params.items())[:2]:
            if _text(v) and k not in ("张成轴", "法线轴"):
                bits.append("%s=%s" % (_text(k), _short(v, 34)))
        disp = re.sub(r"\s*[×xX]\s*\d+\s*$", "", name).strip() or name
        rows.append(" %2d. [z%d] %s ×%d · %s"
                    % (len(rows) + 1, z, disp, cnt,
                       " · ".join(bits) if bits else "（IR 没写形状/材质）"))
        meta.append({"id": eid, "z": z, "name": name, "count": cnt,
                     "primitive": _text(el.get("primitive")),
                     "material": _text(el.get("material")),
                     "params": {str(k): _text(v) for k, v in params.items()},
                     "physics_role": _text(el.get("physics_role"))})
    return rows, meta


def coord_lines(ir):
    comp = ir.get("composition") if isinstance(ir.get("composition"), dict) else {}
    out = []
    conv = comp.get("坐标约定")
    if isinstance(conv, dict):
        parts = ["%s=%s" % (k, _text(v)) for k, v in conv.items()]
        out.append("坐标约定：" + " · ".join(parts))
    elif conv:
        out.append("坐标约定：" + _short(conv, 120))
    proj = comp.get("projection") if isinstance(comp.get("projection"), dict) else {}
    if proj:
        out.append("投影：" + " · ".join("%s=%s" % (k, _text(v)) for k, v in proj.items()))
    return out


def physics_lines(ir):
    hp = ir.get("hard_physics")
    out = []
    if isinstance(hp, list):
        for item in hp:
            if isinstance(item, dict):
                out.append("- %s ｜ 怎么量：%s" % (_short(item.get("claim"), 70),
                                                 _short(item.get("measure"), 70)))
            else:
                out.append("- " + _short(item, 130))
    elif isinstance(hp, dict):
        for k, v in hp.items():
            out.append("- %s：%s" % (_text(k), _short(v, 110)))
    return out


def build_md(ir, rows, meta, with_physics):
    fid = _text((ir.get("figure") or {}).get("id")) if isinstance(ir.get("figure"), dict) else ""
    one = _text((ir.get("figure") or {}).get("one_liner")) if isinstance(ir.get("figure"), dict) else ""
    L = []
    L.append("# 元素清单（请过目 / 加项）—— %s" % (fid or "(IR 没写 figure.id)"))
    if one:
        L.append("一句话：%s" % one)
    L.append("")
    L.extend(rows)
    L.append("")
    L.append("共 **%d** 项（上面 [zN] 里 N 小的在后面、N 大的在前面，从后往前画）。"
             % len(rows))
    cl = coord_lines(ir)
    if cl:
        L.append("　" + " ｜ ".join(cl))
    if with_physics:
        pl = physics_lines(ir)
        if pl:
            L.append("")
            L.append("硬物理（唯一有否决权的一层；每条都要能在图上量出来）：")
            L.extend(pl)
    L.append("")
    L.append("★ 上面这份就是**这张图该有的全部物体**：不在清单里的东西不要画；"
             "缺什么请直接加一行（例：`加：马赫锥 ×1，贴在火球前缘`）。")
    L.append("★ 你点头（回一句「可以」/「开工」/「按这个来」）我才开跑。")
    return "\n".join(L) + "\n"


def paths_for(ir_path, outdir):
    d = Path(outdir) if outdir else Path(ir_path).resolve().parent
    return d, d / "element_list.md", d / "element_list.json", d / "element_ack.json"


def cmd_build(ir_path, outdir, with_physics, quiet):
    ir = load_ir(ir_path)
    rows, meta = compile_list(ir)
    if not rows:
        print("!! IR 里没有 elements —— 没东西可过目（IR=%s）" % ir_path)
        return 2
    d, md_p, js_p, _ = paths_for(ir_path, outdir)
    d.mkdir(parents=True, exist_ok=True)
    md = build_md(ir, rows, meta, with_physics)
    if not quiet:
        print(md)
    md_p.write_text(md, encoding="utf-8")
    js_p.write_text(json.dumps(
        {"ir": str(ir_path), "figure": (ir.get("figure") or {}).get("id"),
         "one_liner": (ir.get("figure") or {}).get("one_liner"),
         "n_elements": len(rows), "lines": rows, "elements": meta},
        ensure_ascii=False, indent=1), encoding="utf-8")
    if not quiet:
        print("[写了] %s" % md_p)
        print("[写了] %s" % js_p)
    n = len(rows)
    if n < 5:
        print("[warn] 清单只有 %d 行（作者要的是 5–10 行）—— 这么少，"
              "要么 IR 漏元素，要么这张图确实简单，请自己核一眼。" % n)
    elif n > 10:
        print("[warn] 清单有 %d 行，超过 10 行 —— 作者要的是 5–10 行："
              "请把同族的合并（如「核子簇 ×2」写成一行），或确认这张图真的这么多物体。" % n)
    return 0


def cmd_record(ir_path, outdir, reply, by, add):
    by_n = _text(by).strip().lower()
    if not reply:
        print("[FAIL] --record 必须带 --reply（客户原话）")
        return 2
    if by_n not in CLIENT_BY and by_n not in MANUAL_BY:
        print("[FAIL] --by=%r 不是客户。只认 %s（客户明确说「你定」才用 manual）。"
              % (by, "/".join(sorted(CLIENT_BY))))
        return 2
    d, md_p, js_p, ack_p = paths_for(ir_path, outdir)
    if not md_p.exists():
        print("!! 还没编译过清单（%s 不存在）—— 先跑一次不带 --record 的，别补票。" % md_p)
        return 2
    rec = {"ir": str(ir_path), "reply": _text(reply), "by": by_n,
           "extra": [_text(x) for x in (add or []) if _text(x)],
           "source": "element_list.py --record"}
    ack_p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    kind = "客户回执" if by_n in CLIENT_BY else "人工裁定（客户说「你定」）"
    print("[ok] %s已落盘 -> %s" % (kind, ack_p))
    print("     原话：%s" % rec["reply"])
    for x in rec["extra"]:
        print("     加项：%s" % x)
    return 0


def cmd_check(ir_path, outdir):
    d, md_p, js_p, ack_p = paths_for(ir_path, outdir)
    if not md_p.exists():
        print("[FAIL] 还没编译元素清单（%s 不存在）—— 出草图前必须先把它贴给客户。" % md_p)
        return 2
    if not ack_p.exists():
        print("[FAIL] 没有客户回执（%s 不存在）—— 清单给客户看过、他点头了才许出草图"
              "（作者 2026-10-15）。" % ack_p)
        return 2
    try:
        rec = json.loads(ack_p.read_text(encoding="utf-8"))
    except Exception as e:
        print("[FAIL] 回执读不出来：%r" % e)
        return 2
    by = _text(rec.get("by")).lower()
    if by not in CLIENT_BY and by not in MANUAL_BY:
        print("[FAIL] 回执的 --by=%r 不是客户（同一张表：%s）" % (by, "/".join(sorted(CLIENT_BY))))
        return 2
    print("[ok] 元素清单已过目：by=%s ｜ 原话=%s" % (by, rec.get("reply")))
    for x in rec.get("extra") or []:
        print("    加项：%s" % x)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="IR -> 中文元素清单（5–10 行）+ 客户回执 + 闸门（出草图前必须过）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ir", required=True, help="IR yaml")
    ap.add_argument("--outdir", default=None, help="产物目录（缺省 = IR 同目录）")
    ap.add_argument("--with-physics", action="store_true", help="顺带把 hard_physics 列出来一起过目")
    ap.add_argument("--quiet", action="store_true", help="只写文件，不打印清单")
    ap.add_argument("--record", action="store_true", help="落客户回执")
    ap.add_argument("--reply", default="", help="客户原话")
    ap.add_argument("--by", default="", help="client/customer/author/user/客户/作者/用户/甲方")
    ap.add_argument("--add", action="append", default=[], help="客户加的项（可多次）")
    ap.add_argument("--check", action="store_true", help="闸门自查：没回执则非零退出")
    a = ap.parse_args()
    if not Path(a.ir).exists():
        sys.exit("找不到 IR：%s" % a.ir)
    if a.check:
        return cmd_check(a.ir, a.outdir)
    if a.record:
        return cmd_record(a.ir, a.outdir, a.reply, a.by, a.add)
    return cmd_build(a.ir, a.outdir, a.with_physics, a.quiet)


if __name__ == "__main__":
    sys.exit(main())
