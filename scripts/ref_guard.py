#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ref_guard -- 出图的「参考图角色」硬闸门（作者 2026-09-29 要求；v3.1 起随 skill 发布，脚本在 scripts/）

作者原话：
    「出草图时不给自家成品当参考，skill 库里的只是风格参考图」

为什么必须变成机器判据（实测，2026-09-29）：
    collective_flow/gen/v3/calls.jsonl 里 sketch seed 31-34 记录的是
        refs         = out/collective_flow_v2.png     <- 自家成品当「风格参考」
        content_refs = out/collective_flow_v2.png     <- 同一张又当「构图参考」
    也就是模型照着**我自己上一版**描，不是照着库里的风格图。
    再加上 IR 把版式写死，于是「同一物理每次草图都一样」「看着像库里那张」。

两条角色规则
--------------------------------------------------------------------------------
  --ref        （风格参考）只许取：skill 的 assets/t3-exemplars/、本工作区 _T3精选/
  --content-ref（构图依据）sketch 阶段：只许作者手绘输入（.../sketches_in/、hand_sketch*.png）
                          render 阶段：只许本图上一步**已过闸口①**的草图

  任何阶段都不许：
    · 本工作区的成品（*/out/**、render_*.png、chosen*.png、*.svg、*.pdf、*@4000.png）
    · skill 的 assets/demos/**（那是**成品示例图**，不是风格书）
    · 同一张图同时出现在 --ref 和 --content-ref（v3 的 bug 就是这个形状）

  警告（不算硬伤，但会打印）：把作者手绘稿放进 --ref —— 规范是只放 --content-ref，
  否则它会绕过 layout-only 降级、把平涂风格原样送进去。

用法
--------------------------------------------------------------------------------
出图前必须先跑，非零退出就不许调 API：

    python scripts/ref_guard.py --stage sketch --ir <IR> --ref <风格图> [--ref ...]

★ 想彻底免掉「忘了跑」这件事，用 --run 包一层，它会先查再调（推荐）：

    python scripts/ref_guard.py --run -- <gen_figure.py 的原参数...>

    --run 会从后面的参数里读 --stage/--ref/--content-ref/--ir，查过之后原样交给
    skill 的 scripts/gen_figure.py 执行；查不过就不执行。
--------------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ── 角色 ────────────────────────────────────────────────────────────────────
STYLE_LIB = "STYLE_LIB"        # 风格书：skill t3-exemplars / 本工作区 _T3精选
DEMO_FIG = "DEMO_FIG"          # skill assets/demos/**：成品示例图（永远不许当参考）
OWN_FINAL = "OWN_FINAL"        # 本工作区成品：out/**、render_*、chosen*、svg/pdf...
OWN_SKETCH = "OWN_SKETCH"      # 本工作区草图：**/sketch_*.png、*_clean.png
AUTHOR_IN = "AUTHOR_IN"        # 作者手绘输入：**/sketches_in/**、hand_sketch*.png ...
SKILL_ASSET = "SKILL_ASSET"    # skill 的其它 assets
SKILL_OTHER = "SKILL_OTHER"    # skill 的其它文件
UNKNOWN = "UNKNOWN"

ALLOWED = {
    "sketch": {"style": {STYLE_LIB, AUTHOR_IN}, "content": {AUTHOR_IN}},
    "render": {"style": {STYLE_LIB, AUTHOR_IN}, "content": {OWN_SKETCH, AUTHOR_IN}},
}

ROLE_CN = {
    STYLE_LIB: "风格书（库内风格参考，允许）",
    DEMO_FIG: "skill 的成品示例图 assets/demos/**（任何阶段都不许）",
    OWN_FINAL: "本工作区成品（不许当草图参考）",
    OWN_SKETCH: "本工作区草图",
    AUTHOR_IN: "作者手绘输入",
    SKILL_ASSET: "skill 的其它 assets",
    SKILL_OTHER: "skill 的其它文件",
    UNKNOWN: "认不出来的路径",
}

_FIN_FINAL = re.compile(r"^(render|alt_render|chosen|layout_chosen|src_render|redraw|sketch_gallery|sheet|panel)", re.I)
_FIN_OWN = re.compile(r"(out|output)[\\/]", re.I)
_AUTHOR_DIR = re.compile(r"[\\/](sketches_in|inputs|refs_in|drafts_in)[\\/]", re.I)
_AUTHOR_NAME = re.compile(r"(hand[_\- ]?sketch|sketch[_\- ]?hand|hand[_\- ]?draft|hand[_\- ]?draw)", re.I)
_AUTHOR_ANY = re.compile(r"^hand[_\-].*\.(png|jpe?g|webp|bmp|tif?f)$", re.I)
_SKETCH = re.compile(r"(^|[\\/])sketch[^\\/]*\.png$|_clean\.png$", re.I)
_SHEET = re.compile(r"(_cmp_ref|_sbs|_sheet|_4up|_gallery|_cmp|@4000)", re.I)


def resolve(path: str, base: str | None = None) -> str:
    q = str(path).strip().strip('"')
    if os.path.isabs(q):
        return os.path.normpath(q)
    for b in [base, os.getcwd()]:
        if b:
            c = os.path.normpath(os.path.join(b, q))
            if os.path.exists(c):
                return c
    return os.path.normpath(os.path.join(base or os.getcwd(), q))


def classify(path: str, ws: str | None = None) -> str:
    """把一条路径判成上面那些角色。只用路径，不读文件内容。"""
    p = str(path).strip().strip('"').replace("\\", "/")
    low = p.lower()
    ws = (ws or os.getcwd()).replace("\\", "/").lower().rstrip("/")
    name = low.rsplit("/", 1)[-1]

    if "/hep-nature-figure/" in low:
        tail = low.split("/hep-nature-figure/", 1)[1]
        if tail.startswith("assets/demos/"):
            return DEMO_FIG
        if tail.startswith("assets/t3-exemplars/") or tail.startswith("assets/style"):
            return STYLE_LIB
        if tail.startswith("assets/"):
            return SKILL_ASSET
        return SKILL_OTHER

    if "/_t3" in low or low.startswith("_t3"):
        return STYLE_LIB

    # 作者手绘输入（必须排在「自家草图/成品」之前）
    if _AUTHOR_DIR.search(p) or _AUTHOR_NAME.search(name) or _AUTHOR_ANY.match(name):
        return AUTHOR_IN

    if _FIN_OWN.search(p) or low.endswith((".svg", ".pdf", ".html")):
        return OWN_FINAL
    if _SHEET.search(name):
        return OWN_FINAL
    if name.endswith(".png") and _FIN_FINAL.match(name):
        return OWN_FINAL
    if _SKETCH.search(p):
        return OWN_SKETCH
    return UNKNOWN


def check(stage: str, style, content, ws: str | None = None, base: str | None = None):
    """返回 (violations, warnings)；violation = (role, path, kind, why)"""
    v, w = [], []
    if stage not in ALLOWED:
        return [("--stage", stage, "BAD_STAGE", "stage 只能是 sketch / render")], []
    rules = ALLOWED[stage]
    for p in style or []:
        r = classify(p, ws)
        if r == DEMO_FIG:
            v.append(("--ref", p, r, "skill 的 assets/demos/** 是**成品示例图**，不是风格书；"
                                     "任何阶段都不许当参考 —— 否则出来就是那张 demo 的重绘"))
        elif r == OWN_FINAL:
            v.append(("--ref", p, r, "★ 不许拿自家成品当风格参考（作者 2026-09-29）。"
                                     "风格参考只许取 skill 的 t3-exemplars/ 或 _T3精选/"))
        elif r == OWN_SKETCH:
            v.append(("--ref", p, r, "★ 自家草图也不许当风格参考（会把平涂风格原样带进去）；--ref 只收风格书"))
        elif r == AUTHOR_IN:
            w.append(("--ref", p, r, "作者手绘稿放进 --ref 会绕过 layout-only 降级；"
                                     "规范是只放 --content-ref，--ref 只放风格书"))
        elif r not in rules["style"]:
            v.append(("--ref", p, r, "风格参考的角色不对：只许 %s" % "/".join(sorted(rules["style"]))))
    for p in content or []:
        r = classify(p, ws)
        if r == DEMO_FIG:
            v.append(("--content-ref", p, r, "skill 的 demo 成品图不许当构图依据"))
        elif stage == "sketch" and r in (OWN_FINAL, OWN_SKETCH):
            v.append(("--content-ref", p, r,
                      "★★ 出草图时不许拿自家成品/自家草图当参考（作者 2026-09-29）—— "
                      "这正是「同一物理每次 IR 出的草图长一样」的根因之一：模型会照着我上一版描"))
        elif stage == "render" and r == OWN_FINAL:
            v.append(("--content-ref", p, r,
                      "render 的构图依据只能是**上一步已过闸口①的草图**，不是成品图"))
        elif r not in rules["content"]:
            v.append(("--content-ref", p, r, "构图依据的角色不对：只许 %s" % "/".join(sorted(rules["content"]))))
    # 同一张图两个角色
    try:
        s = {os.path.normcase(resolve(p, base)) for p in (style or [])}
        c = {os.path.normcase(resolve(p, base)) for p in (content or [])}
        for x in sorted(s & c):
            v.append(("both", x, "SAME_FILE", "同一张图同时当 --ref 和 --content-ref —— v3 的 bug 就是这个形状"))
    except Exception:
        pass
    # 路径不存在（可能只是相对路径没写全，所以只警告）
    for role, seq in (("--ref", style or []), ("--content-ref", content or [])):
        for p in seq:
            if not os.path.exists(resolve(p, base)):
                w.append((role, p, "MISSING", "按当前工作目录/记录目录都找不到这个文件（历史记录里常见）"))
    return v, w


def render_report(stage, style, content, violations, warnings, ws, base=None):
    out = ["=" * 74,
           "ref_guard -- 参考图角色检查（stage=%s）" % stage,
           "=" * 74]
    for role, seq in (("风格参考 --ref", style or []), ("构图依据 --content-ref", content or [])):
        if not seq:
            out.append("  %-20s （无）" % role)
        for p in seq:
            r = classify(p, ws)
            out.append("  %-20s %s" % (role, p))
            out.append("  %-20s   -> %s（%s）" % ("", r, ROLE_CN.get(r, r)))
    out.append("")
    for role, p, kind, why in warnings:
        out.append("  ⚠️ [%s] %s" % (role, p))
        out.append("      %s" % why)
    if warnings:
        out.append("")
    if violations:
        out.append("  结果：❌ 不许出图（%d 条）" % len(violations))
        for role, p, kind, why in violations:
            out.append("    · [%s] %s" % (role, p))
            out.append("        %s" % why)
        out.append("")
        out.append("  规则：--ref 只收风格书；sketch 的 --content-ref 只收作者手绘输入；")
        out.append("        render 的 --content-ref 只收上一步已过闸口①的草图。")
    else:
        out.append("  结果：✅ 通过")
    out.append("")
    return "\n".join(out)


def parse_from_argv(argv):
    stage, style, content, ir, extra = None, [], [], None, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stage" and i + 1 < len(argv):
            stage = argv[i + 1]; i += 2; continue
        if a in ("--ref", "--style-ref") and i + 1 < len(argv):
            style.append(argv[i + 1]); i += 2; continue
        if a == "--content-ref" and i + 1 < len(argv):
            content.append(argv[i + 1]); i += 2; continue
        if a == "--ir" and i + 1 < len(argv):
            ir = argv[i + 1]; i += 2; continue
        if a in ("--choice", "--handoff") and i + 1 < len(argv):
            extra[a] = argv[i + 1]; i += 2; continue
        i += 1
    return stage, style, content, ir, extra


def find_gen_figure():
    skill = os.environ.get("HEP_SKILL")
    cands = [skill] if skill else []
    # 本脚本自己所在的仓库根排最前：脚本装进 skill 的 scripts/ 之后，
    # 不设 HEP_SKILL 也能找到同目录的 gen_figure.py（换机器、换用户都能用）
    cands += [os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
              os.path.expanduser("~/.codex/skills/hep-nature-figure"),
              os.path.join(os.environ.get("CODEX_HOME", ""), "skills", "hep-nature-figure")]
    for c in cands:
        if c and os.path.exists(os.path.join(c, "scripts", "gen_figure.py")):
            return os.path.join(c, "scripts", "gen_figure.py")
    return None


def main():
    ap = argparse.ArgumentParser(add_help=True,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="出图前的参考图角色硬闸门（见文件头）")
    ap.add_argument("--stage", choices=("sketch", "render"))
    ap.add_argument("--ref", action="append", default=[], help="风格参考（只许风格书）")
    ap.add_argument("--content-ref", action="append", default=[], help="构图依据")
    ap.add_argument("--ir", default=None, help="IR；给了就同时查「版式有没有被写死」")
    ap.add_argument("--ws", default=None, help="工作区根（默认当前目录）")
    ap.add_argument("--base", default=None, help="相对路径的解析基准（默认当前目录）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--no-ir-check", action="store_true", help="跳过 IR 版式检查")
    ap.add_argument("--choice", default=None, help="客户挑草图的回执 choice.json")
    ap.add_argument("--handoff", default=None, help="handoff 目录（自动找 <dir>/choice.json）")
    ap.add_argument("--no-choice-check", action="store_true",
                    help="跳过「客户有没有挑过草图」的检查（只在确有理由时才用）")
    ap.add_argument("--run", action="store_true",
                    help="查过后直接执行 skill 的 gen_figure.py（参数放在 -- 之后）")
    a, rest = ap.parse_known_args()

    ws = os.path.abspath(a.ws or os.getcwd())
    base = os.path.abspath(a.base or os.getcwd())
    stage, style, content, ir = a.stage, list(a.ref), list(a.content_ref), a.ir
    argv = None
    if a.run:
        argv = rest[rest.index("--") + 1:] if "--" in rest else rest
        s2, r2, c2, i2, x2 = parse_from_argv(argv)
        stage = stage or s2
        style = style or r2
        content = content or c2
        ir = ir or i2
        a.choice = a.choice or x2.get("--choice")
        a.handoff = a.handoff or x2.get("--handoff")

    v, w = check(stage or "sketch", style, content, ws, base)
    sys.stdout.write(render_report(stage or "sketch", style, content, v, w, ws, base))

    if ir and not a.no_ir_check:
        g = Path(__file__).resolve().parent / "ir_layout_guard.py"
        if g.exists():
            r = subprocess.run([sys.executable, str(g), ir, "--stage", stage or "sketch"],
                               capture_output=True, text=True, encoding="utf-8")
            sys.stdout.write(r.stdout or "")
            if r.returncode != 0:
                v = v + [("--ir", ir, "LAYOUT_LOCKED", "IR 把版式写死了，见上面 ir_layout_guard 的报告")]

    # ── render 之前必须有**客户**挑草图的回执 ──
    if (stage or "sketch") == "render" and not a.no_choice_check:
        cg = Path(__file__).resolve().parent / "choice_gate.py"
        if cg.exists():
            cmd = [sys.executable, str(cg)]
            if a.choice:
                cmd += ["--choice", a.choice]
            elif a.handoff:
                cmd += ["--handoff", a.handoff]
            else:
                cmd += ["--choice", ""]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            sys.stdout.write(r.stdout or "")
            if r.returncode != 0:
                v = v + [("--choice", a.choice or a.handoff or "(未给)", "NO_CLIENT_CHOICE",
                          "没有**客户**挑草图的回执 —— 不许出成品位图（作者 2026-09-29）")]
            else:
                w = w + [("--choice", a.choice or a.handoff or "", "OK", "已有客户回执")]

    if a.json:
        Path(a.json).write_text(json.dumps(
            {"stage": stage, "refs": style, "content_refs": content, "ir": ir,
             "roles": [{"path": p, "role": classify(p, ws)} for p in style + content],
             "violations": [{"role": r, "path": p, "kind": k, "why": y} for r, p, k, y in v],
             "warnings": [{"role": r, "path": p, "kind": k, "why": y} for r, p, k, y in w],
             "ok": not v}, ensure_ascii=False, indent=2), encoding="utf-8")

    if v:
        print("\n结论：不许出图。先把参考图的角色改对，再调 API。")
        return 1

    if a.run:
        gf = find_gen_figure()
        if not gf:
            print("找不到 skill 的 scripts/gen_figure.py（设 HEP_SKILL 环境变量）")
            return 2
        print("ref_guard 通过 -> 执行 %s %s" % (gf, " ".join(argv)))
        return subprocess.call([sys.executable, gf] + list(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())