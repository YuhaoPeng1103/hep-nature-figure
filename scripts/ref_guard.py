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

  警告（不算硬伤，但会打印）：把作者手绘稿放进 --ref —— 手绘稿是**构图依据**，
  规范是只放 --content-ref；--ref 只收风格书。

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
import io
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
            v.append(("--ref", p, r, "★ 自家草图也不许当风格参考（它是构图依据，走 --content-ref）；--ref 只收风格书"))
        elif r == AUTHOR_IN:
            w.append(("--ref", p, r, "作者手绘稿是**构图依据**，"
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


# ── v4.1 新增：IR 契约（必须 3D + 必须声明坐标约定） ──────────────────────
FLAT_ALLOWED = {"render3d"}          # 只认这一档；其余一律要 --allow-flat 理由


def ir_contract(ir_path):
    """返回 (violations, warnings)。作者 2026-10-04：「三轴物理不能错，而且一定要是 3D」。"""
    v, w = [], []
    try:
        import yaml
        doc = yaml.safe_load(io.open(ir_path, encoding="utf-8").read())
    except Exception as e:
        return [("--ir", ir_path, "IR_UNREADABLE", "IR 读不了：%r" % (e,))], []
    if not isinstance(doc, dict):
        return [("--ir", ir_path, "IR_NOT_MAPPING", "IR 不是 mapping")], []
    style = doc.get("style") or {}
    mode = style.get("mode") if isinstance(style, dict) else None
    conv = style.get("conventions") if isinstance(style, dict) else None
    if isinstance(conv, list):
        text = " ".join(str(x) for x in conv)
    else:
        text = "" if conv is None else str(conv)
    if mode not in FLAT_ALLOWED:
        v.append(("--ir", ir_path, "NOT_3D",
                  "style.mode = %r，不是 render3d —— 3D 明暗风是硬规则（AGENTS.md 第 0 节）"
                  % (mode,)))
    else:
        w.append(("--ir", ir_path, "OK", "style.mode = render3d"))
    kws = ("明暗", "高光", "阴影", "透视", "体积", "limb", "shading", "shadow", "渐变")
    if not any(k in text for k in kws):
        w.append(("--ir", ir_path, "NO_3D_LANGUAGE",
                  "style.conventions 里没写三维材质语言（明暗/高光/阴影/透视/渐变）"))
    import re as _re
    inplane = normal = None
    src = "未找到坐标约定"
    comp = doc.get("composition") or {}
    if isinstance(comp, dict):
        for key in ("坐标约定", "coordinate_convention", "convention"):
            blk = comp.get(key)
            if isinstance(blk, dict):
                ip = blk.get("面内") or blk.get("in_plane") or blk.get("plane")
                nm_ = blk.get("法线") or blk.get("normal")
                if ip and nm_:
                    if isinstance(ip, str):
                        ip = [x for x in _re.split(r"[\s,、/\u2013-]+", ip) if x]
                    inplane = [str(x).lower() for x in ip]
                    normal = str(nm_).lower()
                    src = "composition.%s" % key
                    break
    if inplane is None:
        for el in (doc.get("elements") or []):
            if not isinstance(el, dict):
                continue
            pr = el.get("params") or {}
            if not isinstance(pr, dict):
                continue
            ip = pr.get("张成轴") or pr.get("plane_axes")
            nm_ = pr.get("法线轴") or pr.get("normal_axis")
            if ip and nm_:
                if isinstance(ip, str):
                    ip = [x for x in _re.split(r"[\s,、/\u2013-]+", ip) if x]
                inplane = [str(x).lower() for x in ip]
                normal = str(nm_).lower()
                src = "elements[%s].params.张成轴/法线轴" % el.get("id")
                break
    if inplane and normal:
        w.append(("--ir", ir_path, "OK", "坐标约定已声明：面内=%s 法线=%s（%s）" % (inplane, normal, src)))
    else:
        v.append(("--ir", ir_path, "NO_CONVENTION",
                  "IR 没声明坐标约定（%s）—— 加 composition.坐标约定：{面内:[?,?], 法线:?}；"
                  "交付说明必须照抄这一行" % src))
    return v, w


def post_checks(a):
    """出图后：3D 闸门 + 三轴物理闸门。返回进程退出码。"""
    rc = 0
    here = os.path.dirname(os.path.abspath(__file__))
    if a.post_3d:
        cmd = [sys.executable, os.path.join(here, "check_3d_generic.py"), a.post_3d]
        if a.ir:
            cmd += ["--ir", a.ir]
        if a.expect_plane:
            cmd += ["--expect-plane", a.expect_plane]
        sys.stdout.flush()
        print("\n===== 出图后 3D 闸门 =====")
        sys.stdout.flush()
        if subprocess.call(cmd) != 0:
            rc = 1
    if a.axis_svg or a.axis_png:
        cmd = [sys.executable, os.path.join(here, "axis_gate.py")]
        if a.axis_svg:
            cmd += ["--svg", a.axis_svg]
        if a.axis_png:
            cmd += ["--png", a.axis_png]
        if a.ir:
            cmd += ["--ir", a.ir]
        sys.stdout.flush()
        print("\n===== 出图后 三轴物理闸门 =====")
        sys.stdout.flush()
        if subprocess.call(cmd) != 0:
            rc = 1
    return rc


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
    ap.add_argument("--allow-flat", default=None,
                    help="确实要出扁平稿时的理由（写进交付说明）；不给则 style.mode != render3d 判硬伤")
    ap.add_argument("--post", action="store_true",
                    help="出图后跑 3D 闸门 + 三轴闸门（配合 --post-3d / --axis-svg / --axis-png）")
    ap.add_argument("--post-3d", default=None, help="成品位图，交给 check_3d_generic.py")
    ap.add_argument("--axis-svg", default=None, help="交付/重建后的 SVG，交给 axis_gate.py")
    ap.add_argument("--axis-png", default=None, help="与 SVG 同尺寸的位图（无 OCR 轴名识别）")
    ap.add_argument("--expect-plane", choices=("auto", "yes", "no"), default=None,
                    help="传给 check_3d_generic.py：这张图该不该有板面")
    ap.add_argument("--ladder-gen-dir", default=None,
                    help="ABC 阶梯账本目录（缺省由 --outdir 往上找 ladder.json）")
    ap.add_argument("--ladder-waive", default=None,
                    help="确实要放行阶梯闸门（A→B→C）时的理由；会打印出来，交付说明必须照抄")
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

    # --post 且没给 --stage / --run：只跑出图后闸门，不重复跑参考图角色检查
    if a.post and not a.run and not a.stage:
        return post_checks(a)

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

    # ── v4.1：IR 契约（必须 3D + 必须声明坐标约定） ──
    if ir:
        try:
            civ, ciw = ir_contract(ir)
        except Exception as e:
            civ, ciw = [("--ir", ir, "IR_CONTRACT_ERR", repr(e))], []
        for r_, p_, k_, y_ in ciw:
            print("[%s] IR 契约 %-24s %s" % ("ok  " if k_ == "OK" else "warn", k_, y_))
        for r_, p_, k_, y_ in civ:
            if k_ == "NOT_3D" and a.allow_flat:
                print("[warn] IR 契约 %-24s %s（--allow-flat \"%s\"）" % (k_, y_, a.allow_flat))
                w = w + [(r_, p_, k_, y_)]
            else:
                print("[FAIL] IR 契约 %-24s %s" % (k_, y_))
                v = v + [(r_, p_, k_, y_)]

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


    # ── v4.6：提示词阶梯闸门 A -> B -> C（作者 2026-10-06：「严格按 ABC 档来」） ──
    ladder = Path(__file__).resolve().parent / "ladder_gate.py"
    lad_out, lad_brief = None, None
    if argv:
        for _i, _t in enumerate(argv):
            if _t == "--outdir" and _i + 1 < len(argv):
                lad_out = argv[_i + 1]
            if _t == "--brief" and _i + 1 < len(argv):
                lad_brief = argv[_i + 1]
    if (lad_out or a.ladder_gen_dir) and not a.ladder_waive:
        if not ladder.exists():
            print("[warn] 找不到 ladder_gate.py —— 提示词阶梯闸门没跑成")
        else:
            cmd = [sys.executable, str(ladder), "--stage", stage or "sketch"]
            if lad_out:
                cmd += ["--outdir", lad_out]
            if lad_brief:
                cmd += ["--brief", lad_brief]
            if a.ladder_gen_dir:
                cmd += ["--gen-dir", a.ladder_gen_dir]
            for _r in (style or []):
                cmd += ["--ref", _r]
            _r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            sys.stdout.write(_r.stdout or "")
            if _r.returncode != 0:
                v = v + [("--outdir", lad_out or "", "LADDER",
                          "提示词阶梯 A->B->C 不合规；见上面 ladder_gate 的报告"
                          "（--ladder-waive \"理由\" 可放行）")]
    elif (lad_out or a.ladder_gen_dir) and a.ladder_waive:
        print("[warn] 提示词阶梯闸门已用 --ladder-waive \"%s\" 放行" % a.ladder_waive)

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
        rc = subprocess.call([sys.executable, gf] + list(argv))
        if rc != 0:
            return rc
        if (lad_out or a.ladder_gen_dir) and not a.ladder_waive and ladder.exists():
            cmd = [sys.executable, str(ladder), "--record"]
            cmd += ["--stage", stage or "sketch"]
            if lad_out:
                cmd += ["--outdir", lad_out]
            if lad_brief:
                cmd += ["--brief", lad_brief]
            if a.ladder_gen_dir:
                cmd += ["--gen-dir", a.ladder_gen_dir]
            _r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            sys.stdout.write(_r.stdout or "")
            if _r.returncode != 0:
                print("[warn] 阶梯账本登记失败 —— 下一轮会被 L1「跳档」拦住")
        return post_checks(a) if a.post else 0
    if a.post:
        return post_checks(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
