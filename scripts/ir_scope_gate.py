#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ir_scope_gate -- IR 生效范围闸门：**IR 只在 C 档起作用，且只改 A 档真画错的**（作者 2026-10-13 要求）

作者原话：
    「我还是觉得我的思路是对的，就是 IR 只在 C 档起作用，而且只修改 A 档错误的东西，
      如果物理正确不要求和 IR 一样，因为本来就有多种排版方式」

为什么需要它（结构漏洞，不是记性问题）：
    · PROMPT_LADDER.md 与 brief_lite.py 早就写了「A 档一句话 / B 档 + 面板序列 + 输出硬约束 /
      C 档 + 物理增量」，但**没有任何闸门查简报里的内容是从哪来的**。
    · 实测（2026-10-13）：fig_upc_3d/sense_noref/brief_C.md 名义上是「C 档 = B + 上一轮错误清单」，
      实际写成了 **IR 全量灌进去**（6 条物理场景 + HP1-HP6），于是
      「三轴画成画面空白角上一组紧凑小图标」「反应平面画成斜置的浅灰网格薄板」这种 IR 的
      **画法偏好**变成了硬要求 —— 一张物理正确、只是把三轴画在别处的图，会因为不符合 IR 排版被判废。
      作者要的恰恰相反：「物理正确不要求和 IR 一样，本来就有多种排版方式」。
    · 约定拦不住（§0.2 的教训），只有闸门拦得住。

判据（render 档不归本闸门管 —— 位图档按 §0.6 就是 IR 全量 + 错误清单）：
    S0  --tier 必须声明：A | B | C | D。
    S1  A/B 档：IR 的「规格书部件」不许进简报 —— 硬伤（标题含「建议/外观/可选」的块豁免）：
        ① 色号 #rrggbb；② IR style.conventions / style_preferences 的整条（归一化后 >= 12 字连续重合）；
        ③ 绝对版式词（z 序 / 从左到右 / 画面空白角 / 同一行 …）；
        ④ IR 元素的**形体 / 材质词**（竖立 / 斜置 / 网格 / 薄板 / 玻璃 / 半透明 / 冷灰 …）
           —— B 档 = A 的文字 + 面板序列 + 输出硬约束，IR 从 C 档才起作用（作者 2026-10-21）。
        A 档豁免：A 档简报本来就该 = IR 的 figure.one_liner（连续重合 >= 0.8 倍最短长度即认账）。
        元素名重合 -> 只作**软警读数**（B 档描述场景本来就会撞词）；
        但 ④ 那张形体/材质词表是**硬伤** —— 它们不是场景，是 IR 的版式与材质。
    S2  C 档必须含「上一轮错在哪 -> 改成什么」改正块（与 ladder_gate L4 同源）；
        输出硬约束（标签白名单 + 不要标题/图例）缺失 -> 软警。
    S3  C 档改正块**逐条**必须能追到证据，否则硬伤：
        带 [HPn] 出处 / 写了怎么量（量、实测、夹角、点积、比值、坐标、高:宽、数值比…）/
        可逐字对照的标签错（标签、白名单、写成、缺…）。
        与某条 HP 的 claim 有 >=3 字关键词重合但没标号 -> 软警「疑似 HPn，请直接标号」。
        ★ 追不到证据的条目 = 画法偏好，不是错 —— 只许进「外观建议」块。
    S4  C 档：IR 的**画法专属词**（3 字词片，只从 style.conventions / style_preferences 里取；
        §0.7 第 3 层的质感/材质不归 IR 管，不参与判定）
        不许出现在「必须」类条目里（>=2 个即硬伤，1 个软警）。
        放进标题含「建议 / 外观 / 可选」的块里永远通过 —— 那正是 physics-vs-style「第 2 层」的合法归宿。
    S5  **本闸门明确不判**的（打印出来，交付说明照抄）：
        不比对输出的版式 / 元素齐全度 / 配色 / 面板序列与 IR 是否一致；
        只按 hard_physics（能在图上量出来的）比对。这就是「物理正确就不要求和 IR 一样」。

用法：
    python tools/ir_scope_gate.py --tier C --brief <brief.md> --ir <IR> [--json <报告.json>] [--show-vocab]
    （ref_guard.py --run 给了 --tier 时会自动带上它）

标定（改过判据就重跑，2026-10-13 实测）：
    PASS  fig_upc_3d/sense_noref/brief_A.md  --tier A
    PASS  fig_upc_3d/sense_noref/brief_B.md  --tier B
    FAIL  fig_upc_3d/sense_noref/brief_C.md  --tier C
          ── S4_STYLE_AS_MUST x3：光子波浪线配色 / 板面遮挡明暗 / 三轴位置
             被写成硬要求；另有 S3_HP_HINT 软警 x1（两核相交那条没标 [HP1]）
    PASS  tools/_irscope_cal/brief_C_ok.md  --tier C
          ── 同样内容，把上面三条挪进「外观建议」块 + 逐条标 [HPn] 后通过
    FAIL  tools/_irscope_cal/brief_B_bad.md  --tier B
          ── S1：色号 x2 / z 序 / 从左到右 / 整条 style.preferences
    PASS  brief_lite.py --tier 0 产出            --tier B（仅 1 条软警：元素名撞词）
    PASS  brief_lite.py --tier 1 产出            --tier B
          ── 修过一处：「全图共用一个光源（方位 128°/仰角 38°）」与 IR
             style.conventions 撞整条，已从硬约束挪进「外观建议」块

已知局限（别当它万能）：
    · 只看**字面**（3 字片 + 正则），不看语义：光子「波浪形」这种**记法**
      也会被算成画法词（它的措辞来自 style_preferences）——
      处理：挪进「外观建议」块，或把措辞改成不带画法的说法。
    · 追证只认**字面证据**（[HPn] / 量词 / 标签词）：写得出但语义上不可量的
      条目仍会被放过 —— 这一层靠人复核（所以 S5 那份「不判清单」要贴进交付说明）。
    · 不给 --ir 时 S3/S4 不判（只剩 S1 的色号/版式词 + S2）。
    · 「外观建议」块是合法宿主，也就是说把东西全塞进建议块就能过闸门 ——
      那不是漏洞，是刻意的：闸门只保证「声明写清楚了这是建议还是必须」，美不美靠人看。

退出码：0 = 过；1 = 有硬伤（不许调 API）。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

LAYOUT_WORDS = ("z 序", "z序", "z-order", "从左到右", "从左至右", "从右到左",
                "画面空白角", "画面左下角", "画面右下角", "画面右上角", "画面左上角",
                "画面角落", "同一行", "exactly", "one row")

# S1 ④（作者 2026-10-21）：A/B 档不许出现 IR 元素的**形体 / 材质**词。
#   为什么：B 档的定义是「A 的文字 + 面板序列 + 输出硬约束」，IR 从 C 档才起作用。
#   实测 fig_upc_v427_u15：A 只说「两个核子堆成的重核」，B 却冒出
#   「竖立半透明网格板（不是地面）」—— 这句来自 IR 的 S1，B 档把板的朝向与材质
#   一起定死，C/D 的「原样保留」再把它冻到最后。v426 的 B 同样带了
#   「斜置浅灰网格薄板」，只是它与风格图 T3-38 同族，所以没被看出来。
#   只收「形体/材质」词，不收物理词（核 / 光子 / 轻子这些 A 里本来就有）。
PROP_WORDS = ("竖立", "斜置", "平放", "横放", "网格", "薄板", "玻璃", "半透明",
              "倒角", "刻线", "侧壁", "接触阴影", "冷灰", "青色边缘")

PUNCT = set(" \t\r\n\u3000【】「」『』（）()〔〕[]《》〈〉、，。；：！？,.;:!?“”‘’—–-~／/+*=_|\\\"'")

ITEM_RE = re.compile(r"^\s*(?:[-·*\u2022\u25aa]|\d+\s*[.、)]|\(\d+\))\s*")

EVID_WORD = ("量", "实测", "读数", "夹角", "点积", "比值", "坐标", "占画布", "像素",
             "高宽比", "长度比", "角度", "标签", "白名单", "写成", "错字", "拼写",
             "多出", "多了", "少了", "缺", "漏", "多余")
EVID_PAT = re.compile(r"HP\s*\d|高\s*[:：/]\s*宽|\d+\s*[:：]\s*\d+|[<>≥≤]\s*\d|约\s*\d")

SUGGEST_MARKERS = ("建议", "外观", "可选", "可以改得")
FIX_MARKERS = ("上一轮", "上一版", "画错", "改成", "修正", "错误清单", "错在哪", "真画错")
OUT_MARK_WHITE = ("只许出现这些标签", "只许出现这些字符串", "只许出现这些字符", "白名单")
OUT_MARK_NODECOR = ("不要图例", "不要标题", "不要说明文字", "不许图例", "不要边框")

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TOK_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z\-/]{2,}")
GENERIC = set(["不要", "不是", "可以", "必须", "一个", "所有", "图上", "这张", "要么", "如果",
               "只能", "直接", "需要", "表示", "用来", "这是", "单个", "两者", "本身", "一致"])

NOT_JUDGED = [
    "输出的版式 / 构图 / 元素摆放与 IR 是否一致 —— 不判（IR 只描述一种排法，物理对的排法有很多种）",
    "IR 的 elements 齐全度（少了板面 / 少了细箭头 / 少了尺寸线）在草图档 —— 不判（留给位图档）",
    "配色 / 材质 / 质感 / 光源与 IR palette 是否一致 —— 不判（skill 第 3 层，交给生图模型）",
    "面板序列 / 画布分区与 IR panels_count 是否一致 —— 不判",
    "判定只用 IR 的 hard_physics：每条必须能在图上量出来 / 证伪（measure）",
]


def norm(s):
    return "".join(ch for ch in str(s or "") if ch not in PUNCT).lower()


def lcs(a, b):
    """最长连续公共子串长度。"""
    a, b = str(a or ""), str(b or "")
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def toks(s):
    """中英混排切词：CJK 长串切成 3 字片（>=5 字时），英文取 >=3 字母的词。"""
    out = []
    for run in TOK_RE.findall(str(s or "")):
        if CJK_RE.match(run):
            if len(run) >= 5:
                out += [run[i:i + 3] for i in range(len(run) - 2)]
            else:
                out.append(run)
        else:
            out.append(run.lower())
    return out


FIRST_CHARS = "\u2550\u2500\u2014-=*#"


def _header(line):
    """认块标题：① 分隔线型（════ 标题 ════）；
    ② 不带项符、不超 30 字且含「建议/外观/可选/画错/改成」的短行（如「外观建议（可以改得更漂亮）」）。"""
    s = line.strip()
    if not s or len(s) > 40 or ITEM_RE.match(line):
        return None
    if s[0] in FIRST_CHARS and len(s) >= 4:
        return s.strip(FIRST_CHARS + " ").strip() or "(分隔线)"
    if len(s) <= 30 and any(m in s for m in SUGGEST_MARKERS + FIX_MARKERS):
        return s.rstrip("\uff1a: 。").strip()
    return None


def blocks(text):
    """按块标题切块；返回 [(title, [lines])]，第一块 title = (开头)。"""
    out = []
    title, body = "(开头)", []
    for ln in str(text or "").splitlines():
        h = _header(ln)
        if h:
            out.append((title, body))
            title, body = h, []
            continue
        body.append(ln)
    out.append((title, body))
    return out


def items(lines):
    return [ITEM_RE.sub("", ln).strip() for ln in lines if ITEM_RE.match(ln)]


def is_suggest(title):
    return any(m in str(title) for m in SUGGEST_MARKERS)


def is_fix(title):
    return any(m in str(title) for m in FIX_MARKERS)


def load_ir(path):
    import yaml
    with io.open(path, encoding="utf-8") as f:
        return yaml.safe_load(f.read())


def ir_view(doc):
    fig = doc.get("figure") or {}
    style = doc.get("style") or {}
    els = [e for e in (doc.get("elements") or []) if isinstance(e, dict)]
    hp = [h for h in (doc.get("hard_physics") or []) if isinstance(h, dict)]
    conv = [str(x) for x in (style.get("conventions") or [])]
    pref = [str(x) for x in (doc.get("style_preferences") or [])]
    mats = []
    for e in els:
        if e.get("material"):
            mats.append(str(e.get("material")))
        for v in ((e.get("params") or {}) if isinstance(e.get("params"), dict) else {}).values():
            if isinstance(v, str) and len(v) > 4:
                mats.append(v)
    for v in ((style.get("palette") or {}) if isinstance(style.get("palette"), dict) else {}).values():
        mats.append(str(v))
    phys = [fig.get("physics_claim"), fig.get("one_liner"), fig.get("panel_claim")]
    for e in els:
        phys.append(e.get("physics_role"))
    for h in hp:
        phys += [h.get("claim"), h.get("measure")]
    phys += list((doc.get("assertions") or {}).get("machine") or [])
    phys_text = norm(" ".join(str(x) for x in phys if x))
    style_toks = []
    for t in toks(" ".join(conv + pref)):
        if len(t) <= 2 and (t in GENERIC or (CJK_RE.match(t) and t in phys_text)):
            continue
        if norm(t) in phys_text and CJK_RE.match(t):
            continue
        if t not in style_toks:
            style_toks.append(t)
    prop_src = []
    for e in els:
        prop_src += [str(e.get("name") or ""), str(e.get("primitive") or ""),
                     str(e.get("material") or "")]
        p = e.get("params")
        if isinstance(p, dict):
            prop_src += [str(v) for v in p.values() if isinstance(v, str)]
    prop_text = norm(" ".join(prop_src))
    return {
        "one_liner": str(fig.get("one_liner") or fig.get("physics_claim") or ""),
        "conv": conv, "pref": pref,
        "element_names": [str(e.get("name")) for e in els if e.get("name")],
        "mats": mats, "hp": hp, "phys_text": phys_text, "style_toks": style_toks,
        "prop_text": prop_text,
    }


def hp_hint(item, hp_list):
    n = norm(item)
    for h in hp_list:
        for t in re.findall(r"[\u4e00-\u9fff]{3,}|[A-Za-z]{3,}", str(h.get("claim") or "")):
            if t.lower() in n:
                return str(h.get("id"))
    return None


def has_evidence(item):
    if EVID_PAT.search(item):
        return True
    return any(w in item for w in EVID_WORD)


def check(tier, text, view):
    hard, soft, reading = [], [], []
    if tier in ("A", "B"):
        # 建议块豁免：IR 的画法/外观内容，在**任何**档里都只许出现在「外观建议」块里（与 S4 同一条原则）。
        _bl = blocks(text)
        text = "\n".join(ln for _t, _b in _bl if not is_suggest(_t) for ln in _b)
        nb = norm(text)
        if tier == "A":
            no = norm(view["one_liner"]) if view else ""
            if no and lcs(nb, no) >= 0.8 * max(1, min(len(nb), len(no))):
                reading.append("A 档豁免：简报就是 IR 的 figure.one_liner（不算 IR 越权）")
                return hard, soft, reading
        for m in HEX_RE.finditer(text):
            hard.append(("S1_IR_HEX_IN_BRIEF", "A/B 档简报里出现色号 %s —— 色号是 IR 的规格书部件" % m.group(0)))
        for w in LAYOUT_WORDS:
            if w in text:
                hard.append(("S1_IR_LAYOUT_IN_BRIEF", "A/B 档简报里出现绝对版式词「%s」" % w))
        for w in PROP_WORDS:
            if w in text and w in view.get("prop_text", ""):
                hard.append(("S1_IR_PROP_IN_BRIEF",
                             "A/B 档简报里出现 IR 元素的形体/材质词「%s」—— B 档只许有 A 的文字 + "
                             "面板序列 + 输出硬约束；板 / 玻璃 / 网格这类形体留到 C 档再长出来" % w))
        for tag, lines in (("conventions", view["conv"]), ("preferences", view["pref"])):
            for ln in lines:
                nl = norm(ln)
                if len(nl) >= 12 and lcs(nl, nb) >= 12:
                    hard.append(("S1_IR_%s_IN_BRIEF" % tag.upper(),
                                 "A/B 档简报里出现 IR style.%s 的整条：%s" % (tag, ln[:40])))
        hit_names = [nm for nm in view["element_names"] if norm(nm) and norm(nm) in nb]
        if hit_names:
            soft.append(("S1_ELEMENT_NAME_OVERLAP",
                         "简报里出现 IR 元素名 %s —— 只作读数（B 档描述场景本来就会撞词）"
                         % "、".join(hit_names[:4])))
        return hard, soft, reading
    if tier == "render":
        return hard, soft, reading
    # ---- C / D 档（严格改档）----
    bl = blocks(text)
    fixblocks = [(t, b) for t, b in bl if is_fix(t)]
    if not fixblocks:
        hard.append(("S2_NO_FIX_BLOCK",
                     "%s 档没有「上一轮画错 -> 改成什么」这一节（IR 只许以这个形状进来）" % tier))
    if not any(m in text for m in OUT_MARK_WHITE):
        soft.append(("S2_NO_LABEL_WHITELIST", "%s 档没有标签白名单（上一档的东西要累积下来）" % tier))
    if not any(m in text for m in OUT_MARK_NODECOR):
        soft.append(("S2_NO_DECOR_BAN", "%s 档没有「不要标题/图例/说明文字」" % tier))
    for _t, body in fixblocks:
        for it in items(body):
            if not has_evidence(it):
                hint = hp_hint(it, view["hp"]) if view else None
                if hint:
                    soft.append(("S3_HP_HINT", "[%s] 疑似对应 %s，请直接标号：%s" % (hint, hint, it[:46])))
                else:
                    hard.append(("S3_UNTRACEABLE_FIX",
                                 "改正条目追不到证据（既没 [HPn] 也没写怎么量）= 画法偏好，不是错：%s" % it[:60]))
    toks_all = view["style_toks"] if view else []
    for title, body in bl:
        if is_suggest(title):
            continue
        for it in items(body):
            if any(m in it for m in OUT_MARK_WHITE + OUT_MARK_NODECOR):
                continue
            if any(m in it for m in ("【", "】")) and re.search(r"^\s*[\[\(]?HP", it):
                pass
            hits = [t for t in toks_all if t in norm(it)]
            if len(hits) >= 2:
                hard.append(("S4_STYLE_AS_MUST",
                             "「必须」类条目里出现 IR 画法专属词 %s —— 那是画法偏好，只许进「外观建议」块：%s"
                             % ("、".join(hits[:4]), it[:52])))
            elif len(hits) == 1:
                soft.append(("S4_STYLE_WORD_HINT",
                             "条目里有 1 个 IR 画法词「%s」，建议降级为建议：%s" % (hits[0], it[:46])))
    return hard, soft, reading


def main():
    ap = argparse.ArgumentParser(add_help=True,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="IR 生效范围闸门：IR 只在 C 档起作用，且只改 A 档真画错的（见文件头）")
    ap.add_argument("--tier", required=True, choices=("A", "B", "C", "D", "render"))
    ap.add_argument("--brief", required=True)
    ap.add_argument("--ir", default=None, help="IR；给了才能判 S1 的 conventions / S3 的 [HPn] / S4 的画法词")
    ap.add_argument("--json", default=None)
    ap.add_argument("--show-vocab", action="store_true", help="打印从 IR 抽出来的画法专属词，供人核对")
    ap.add_argument("--waive", default=None, help="确要放行时的理由；会被打印，交付说明必须照抄")
    a = ap.parse_args()

    text = io.open(a.brief, encoding="utf-8").read()
    if a.tier == "render":
        print("[ok  ] S0 档位 render —— 位图档按 §0.6 本来就是 IR 全量 + 错误清单，本闸门不判")
        return 0
    view = None
    if a.ir:
        try:
            view = ir_view(load_ir(a.ir))
        except Exception as e:
            print("[warn] IR 读不了（%r）—— S1/S3/S4 降级为部分判据" % e)
    else:
        print("[warn] 没给 --ir —— S1 只查色号/版式词，S3/S4 跳过")

    hard, soft, reading = check(a.tier, text, view or
                                {"one_liner": "", "conv": [], "pref": [], "element_names": [],
                                 "mats": [], "hp": [], "phys_text": "", "style_toks": []})

    print("=" * 72)
    print("ir_scope_gate  tier=%s  brief=%s  ir=%s" % (a.tier, a.brief, a.ir or "(未给)"))
    print("=" * 72)
    if a.show_vocab and view:
        print("IR 画法专属词（3 字片，只从 style.conventions / style_preferences 抽）:")
        print("  " + "  ".join(view["style_toks"]))
        print("IR 元素名: " + "  ".join(view["element_names"]))
    for x in reading:
        print("[ok  ] " + x)
    for code, y in soft:
        print("[warn] %-26s %s" % (code, y))
    for code, y in hard:
        print("[FAIL] %-26s %s" % (code, y))
    print("-" * 72)
    print("S5 本闸门明确不判（交付说明照抄）:")
    for x in NOT_JUDGED:
        print("   · " + x)
    print("-" * 72)
    if hard and a.waive:
        print("[waive] %d 条硬伤被放行，理由：%s（交付说明必须照抄这句）" % (len(hard), a.waive))
        hard = []
    print("结论：%s（硬伤 %d 条 / 软警 %d 条）" % ("FAIL 不许调 API" if hard else "PASS", len(hard), len(soft)))

    if a.json:
        rep = {"tier": a.tier, "brief": a.brief, "ir": a.ir,
               "pass": not hard,
               "hard": [{"code": c, "msg": m} for c, m in hard],
               "soft": [{"code": c, "msg": m} for c, m in soft],
               "reading": reading, "not_judged": NOT_JUDGED,
               "style_vocab": (view or {}).get("style_toks", [])}
        with io.open(a.json, "w", encoding="utf-8") as f:
            f.write(json.dumps(rep, ensure_ascii=False, indent=2))
        print("报告写到 %s" % a.json)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())