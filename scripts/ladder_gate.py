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
    L2  A 档 = 一句话：简报 <= 80 字符，**默认不带风格参考图**（作者 2026-10-13：
        「把 A 档不放参考图作为默认」）；带了 --ref 只作软警。A 档产物**只作诊断**，
        不许进交付链（--stage render 时构图依据来自 A 档的 outdir → 硬伤）。
    L3  B 档必须有三样：① **风格参考图**（A 档默认没有，风格从 B 档引入 ——
        作者 2026-10-13「B 档还是有参考图」）；② 面板序列；③ 输出硬约束
        （标签白名单 / 不要图例标题说明文字）。
    L4  每一轮 C 必须带「上一轮错在哪 → 改成什么」那一节，且 <= 3000 字符（增量，不是规格书）；
        简报还得是累积稿（上一轮简报的内容在里面）。
    L6  出成品位图之前，阶梯必须至少有 A、B、C 三段。
    L7  **风格参考图必须贯穿整条阶梯**：B/C 档的 `--ref` 必须与 A 档一致
        （作者 2026-10-07：「BC档和A档完全不一样啊，BC档是辅助A档物理错误的」）——
        B/C 是 A 的续（只补面板序列 / 输出硬约束 / 物理修正），中途换风格图 = 另起一张。
    L8  **慢慢增加提示词**（作者 2026-10-07：「你这B档提示词一下子加太多提示词
        导致图片一下就很难看了」）：草图档每上一档，简报相对上一档最多增加
        MAX_STEP_GROWTH（250）字符 —— 一次只加一条新约束。实测 v43：A 档 31 字符
        直接跳到 B 档 767 字符，出图的观感与 A 档完全不是一张图。
        render 档豁免（它的简报是 IR 编译稿 + 错误清单，见 §0.6）。
    L9  **B/C 档每一轮都要把「修改前的图」当 --content-ref 交进去**（作者 2026-10-13：
        「A 档出图后，BC 档每次修改都要给修改前的图，这样方便模型理解什么修改，
        什么保留」）：B/C 档（stage=sketch）必须给至少一条 --content-ref，
        且它要落在**本阶梯账本已登记的 rung 目录**里（= 上一轮的图）。
        只给文字说「改这个、别的别动」不够 —— 模型看不到上一版，就会把上一版
        已经画对的东西一起重画（实测：A 档的 QGP 火球是从风格图继承来的，
        B/C 档看不到上一版、只好自己重画，同一张图的 QGP 在两档之间换了形状）。
        不给 = 硬伤（--waive "理由" 可放行，理由照抄进交付说明）。
    L10 **C 档必须严格在上一张图上改**（作者 2026-10-13：「只有 C 档时严格在上一张
        图片上改」）：只改下面列出的那几条，其余连形状 / 质感 / 配色 / 光源 / 视角 /
        位置都不许变 —— 不许重画、不许换材质、不许加也不许删（命中 >= 2 个严格措辞）。
        为什么标出来：C 档不写"严格"，B 档刚改对的东西会被整张重画一遍
        （实测：C 档把 B 档的火球质感重画成了光滑球）。
        ★ **B 档不判这条**（作者 2026-10-13：「B 不就一轮吗，怎么还有挑着保留这一说」）：
        B 只跑一轮，简报就是「A 的内容 + 面板序列 + 输出硬约束」= v4.12 的 B 档；
        "该保留什么"由 L9 把上一张图交给它、模型自己看着办，不写成硬措辞。
    L11 **C 档改「形状 / 几何」时不许改「材质 / 质感」**（作者 2026-10-14：
        「对 C 档修改物理几何的地方不修改材质……我建议说'不要修改材质'」）：
        形状 / 几何是**物理**（该改），材质 / 质感是**观感**（不该顺手换）。C 档增量块
        只要命中形状 / 几何类词（形状 / 几何 / 压扁 / 尺寸 / 位置 / 朝向…），简报里
        就必须写明**材质保持不变**，否则硬伤。★ 写法是「材质保持不变（以给的那张图 ——
        上一版的材质为准）」，**不要替模型指定具体材质**（作者 2026-10-14：「不要写材质
        保持光滑啊，应该是材质保持不变」）；点名了具体材质只出软警。实测：C 档只让把圆球
        压成扁球，模型把上一版的光滑球面一起重画成了粗糙石块（keep_gate 漂移 0.881）。
    L12 **B 档必须写明「保留上一档（A）画得好的元素，可在其基础上更美观」**（作者
        2026-10-14：「B 保留 A 好看的元素，比如如果 A 画的核子好看就保留核子，甚至可以
        在此基础上更美观」）：B 是 A 的续 —— A 画对的形状 / 物体 / 布局要留着、只在此基础上
        做得更好看，不许推倒重画。缺这句 = 硬伤。★ 与 L10 不冲突：L10 只判 **C 档**的
        「严格…不许变」措辞；B 档不判严格措辞，但判这条「继承优点」。

## 用法

    # 出图前查（ref_guard.py --run 会自动调）
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md --ref <风格图> \
            --content-ref <fig>/gen/A/sketch_s1.png      # L9：这一档必须给「修改前的图」
    # 出图后登记（ref_guard.py --run 成功退出后自动调）
    python3 scripts/ladder_gate.py --record --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md
    # 单独查账本
    python3 scripts/ladder_gate.py --gen-dir <fig>/gen --stage render

`--waive "理由"` 可放行（理由会被打印出来，交付说明里必须照抄）。

自检（L11 / L12 标定；改了判据就跑一次）：

    python3 scripts/ladder_gate.py --selftest
"""

import argparse
import json
import os
import sys
from pathlib import Path

MAX_A_CHARS = 80
MAX_B_CHARS = 1500
MAX_INC_CHARS = 3000
MAX_STEP_GROWTH = 250

PANEL_MARKERS = ("面板", "从左到右", "a/b/c", "a b c", "三个面板", "两个面板", "四面板")
NO_DECOR_MARKERS = ("不要图例", "不要标题", "不要说明文字", "不成段", "不图例", "不色卡",
                    "不章节编号", "不要边框")
WHITELIST_MARKERS = ("只许出现这些标签", "只允许出现这些标签", "只许写这些标签",
                     "标签白名单", "图上只允许出现", "只许出现", "白名单")
FAIL_MARKERS = ("错", "改成", "上一轮", "这一轮必须改对", "没做对", "改成什么")
INC_SEPS = ("上一轮画错", "上一轮真画错", "上一版画错", "上一轮（", "上一轮(", "════", "====")

# L10：C 档"严格在上一张图上改"（★ B 档不判 —— B 只跑一轮，见文件头 L10）
STRICT_KEEP_MARKERS = ("严格", "原样保留", "不许重画", "不许换", "不许换材质", "不许删",
                       "不许加", "不许变", "完全一致", "一模一样", "只改下面")

# L11：C 档改「形状 / 几何」时不许改「材质 / 质感」（作者 2026-10-14）
#   形状 / 几何 = 物理（该改）；材质 / 质感 = 观感（不该顺手换）。两者分开判。
MATERIAL_KEEP_MARKERS = ("不要修改材质", "不修改材质", "不要改材质", "不改材质",
                         "不要修改质感", "不修改质感", "不要换材质", "不许换材质",
                         "不换材质", "材质保持不变", "材质保持", "材质不变", "质感不变",
                         "材质/质感保持", "材质、质感保持", "材质与质感保持", "材质和质感保持",
                         "材质 / 质感 / 配色", "材质一律保持", "材质原样", "质感原样",
                         "只改形状", "只改几何", "不改质感", "材质照着上一版")
GEOM_CHANGE_MARKERS = ("形状", "几何", "压扁", "拉长", "尺寸", "位置", "朝向", "长短",
                       "高瘦", "扁球", "改成", "角度", "间距", "重叠", "变大", "变小",
                       "轮廓", "剖面")

# L12：B 档必须写明「保留上一档（A）画得好的元素，可在其基础上更美观」（作者 2026-10-14）
B_INHERIT_MARKERS = ("保留上一档", "保留上一版", "保留上一张", "保留 A 档", "保留A档",
                     "保留 A 版", "保留A版", "上一档好看", "上一版好看", "保留好看",
                     "保留画得好", "保留满意", "保留其中好", "保留好的", "保留好的元素",
                     "好的元素保留", "好看的元素保留", "好看的部分保留", "继承上一档",
                     "继承上一版", "延续上一档", "延续上一版", "在此基础上更美观",
                     "在此基础上再美观", "在此基础上做得更好看")

# 简报里**替模型指定材质**的词（写「材质保持光滑」这类是错的）—— 只出软警。
MATERIAL_WORD_HINTS = ("光滑", "粗糙", "哑光", "磨砂", "金属", "镜面", "高光", "磨砂感")


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
    seeds, refs, content_refs, stages = [], [], [], set()
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
    return {"seeds": seeds, "refs": refs, "content_refs": content_refs,
            "stages": sorted(x for x in stages if x)}


def extract_increment(text):
    """取「上一轮错在哪 -> 改成什么」那一节（C 档的增量）。"""
    best = -1
    for s in INC_SEPS:
        i = text.rfind(s)
        if i > best:
            best = i
    return text[best:].strip() if best >= 0 else ""


def _squash(s):
    """去掉空白与常见分隔符再比，避免「材质 / 质感」这类空格把标记切碎。"""
    for ch in (" ", "\u3000", "\t", "/", "、", "，", ",", "与", "和", "＋", "+", "·"):
        s = s.replace(ch, "")
    return s


def has_material_keep(text):
    """简报里有没有写明「不要修改材质 / 质感（保持上一版）」。"""
    if not text:
        return False
    t = _squash(text)
    if any(_squash(k) in t for k in MATERIAL_KEEP_MARKERS):
        return True
    has_mat = ("材质" in t) or ("质感" in t)
    has_keep = any(k in t for k in ("保持", "不变", "不改", "不要改", "不许改", "别动",
                                    "照旧", "沿用", "原样"))
    return has_mat and has_keep


def has_inherit_clause(text):
    """B 档有没有写明「保留上一档画得好的元素，可在其基础上更美观」。"""
    if not text:
        return False
    t = _squash(text)
    if any(_squash(k) in t for k in B_INHERIT_MARKERS):
        return True
    has_keep = any(k in t for k in ("保留", "继承", "延续", "不推倒", "沿用"))
    has_good = any(k in t for k in ("上一档", "上一版", "上一张", "A档", "A版", "好看",
                                    "优点", "满意", "好的", "画得好", "更好看", "更美观"))
    return has_keep and has_good


def material_prescribe_hint(text):
    """简报是不是在**替模型指定材质**（「材质保持光滑」这类）。

    正确写法是「材质保持不变（以给的那张图为准）」—— 不点名具体材质。命中返回该词。
    """
    if not text:
        return None
    for w in MATERIAL_WORD_HINTS:
        i = text.find(w)
        while i >= 0:
            near = text[max(0, i - 24): i + 24]
            if ("材质" in near) or ("质感" in near):
                return w
            i = text.find(w, i + 1)
    return None


def brief_shape(rung, text, refs, prev_text):
    v, w = [], []
    n = len(text.strip())
    if rung == "A":
        if n > MAX_A_CHARS:
            v.append("L2 A 档必须是一句话（<= %d 字符），这份简报 %d 字符 —— A 档是用来"
                     "看模型对这个题材的先验的，不是交付稿；要加约束请走 B 档。" % (MAX_A_CHARS, n))
        if refs:
            w.append("L2 A 档**默认不带风格参考图**（作者 2026-10-13「把 A 档不放参考图作为默认」）"
                     "—— A 档是看模型对这个题材的先验、只作诊断，风格由 B 档引入。"
                     "这一轮带了 --ref %s，确认是有意的。" % (refs,))
    elif rung == "B":
        if n < 40:
            v.append("L3 B 档太短（%d 字符）：B = A + 面板序列 + 输出硬约束。" % n)
        if n > MAX_B_CHARS:
            v.append("L3 B 档太长（%d 字符 > %d）：这一档只加面板序列与输出硬约束，"
                     "物理增量留给 C 档。" % (n, MAX_B_CHARS))
        if not refs:
            v.append("L3 B 档必须带**风格参考图**（--ref）：A 档默认不带参考图，风格是从 B 档"
                     "开始引入的（作者 2026-10-13「B 档还是有参考图」）。")
        if not any(k in text for k in PANEL_MARKERS):
            w.append("L3 B 档还没有【面板序列】（「面板 a/b/c」「从左到右」这类）—— "
                     "L8 允许分几步加，但**进 render 前必须补齐**（由 L3b 在 render 档把关）。")
        if not any(k in text for k in WHITELIST_MARKERS + NO_DECOR_MARKERS):
            w.append("L3 B 档还没有【输出硬约束】（标签白名单 / 不要图例标题说明文字）—— "
                     "L8 允许分几步加，但进 render 前必须补齐。")
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


def order_checks(led):
    rungs = led.get("rungs") or []
    names = [r.get("rung") for r in rungs]
    want = [rung_name(i) for i in range(len(names))]
    if names != want:
        return ["L1 阶梯跳档：账本里是 %s，必须是 %s（A → B → C…）。" % (names, want)]
    return []


def precheck(gen_dir, brief_path, outdir, refs, stage, content_refs=None):
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
    # L7 风格参考图必须贯穿整条阶梯（作者 2026-10-07）。
    #     ★ 2026-10-13：A 档默认不带参考图，所以锚点取**阶梯里第一个带 refs 的 rung**
    #     （现在一般是 B 档），不再写死 rungs[0]（那会让这条规则失效）。
    if rungs:
        anchor = None
        for _r in rungs:
            if _r.get("refs"):
                anchor = _r
                break
        now_refs = sorted(os.path.basename(x) for x in (refs or []))
        if anchor is not None:
            a_refs = sorted(os.path.basename(x) for x in (anchor.get("refs") or []))
            if now_refs and a_refs != now_refs:
                v.append("L7 风格参考图与本条阶梯的 %s 档不一致：%s 档用 %s，这一轮用 %s —— "
                         "B/C 档是同一张风格书的续，中途换风格图 = 另起一张。"
                         % (anchor.get("rung"), anchor.get("rung"), a_refs, now_refs))
    # L8 慢慢加提示词：每上一档只加一条新约束（作者 2026-10-07）
    if stage == "sketch" and prev is not None:
        grow = len(text.strip()) - (prev.get("brief_chars") or 0)
        if grow > MAX_STEP_GROWTH:
            v.append("L8 这一档比上一档一次多写了 %d 字符（上限 %d）—— 「慢慢增加提示词」："
                     "每上一档只加一条新约束，一次加太多会把上一档的观感整个换掉"
                     "（实测 v43：A 档 31 字符 → B 档 767 字符，B/C 出图跟 A 完全不一样）。"
                     % (grow, MAX_STEP_GROWTH))
    # L9 B/C 档每一轮都要把「修改前的图」交进去（作者 2026-10-13）
    if stage == "sketch" and rung in ("B", "C") and rungs:
        hit_any, hit_prev, prev_od = False, False, None
        if prev and prev.get("outdir"):
            prev_od = os.path.abspath(prev["outdir"])
        for x in (content_refs or []):
            if not x:
                continue
            cp = os.path.abspath(x)
            for r in rungs:
                od = r.get("outdir")
                if not od:
                    continue
                od_a = os.path.abspath(od)
                if cp == od_a or cp.startswith(od_a + os.sep):
                    hit_any = True
                    if prev_od and od_a == prev_od:
                        hit_prev = True
        if not hit_any:
            v.append("L9 %s 档必须把**上一档的图**当 --content-ref 交进去（作者 2026-10-13："
                     "「BC 档每次修改都要给修改前的图，方便模型理解什么修改、什么保留」）—— "
                     "这一轮没给任何落在本阶梯**已登记 rung 目录**里的 --content-ref。"
                     "做法：--content-ref %s"
                     % (rung, prev_od or "<gen>/<上一档>/sketch_sN.png"))
        elif not hit_prev:
            w.append("L9 给的 --content-ref 不在**紧邻的上一档**目录里 —— "
                     "确认给的是「修改前」那一版，不是更早的版本。")
    # L10 C 档必须严格在上一张图上改（作者 2026-10-13）；B 档不判（B 只跑一轮）
    if stage == "sketch" and rung == "C":
        _hits = [k for k in STRICT_KEEP_MARKERS if k in (text or "")]
        if text and len(_hits) < 2:
            v.append("L10 C 档必须写清它是**严格在上一张图上改**（作者 2026-10-13："
                     "「只有 C 档时严格在上一张图片上改」）—— 只改下面列出的那几条，"
                     "其余连形状 / 质感 / 配色 / 光源 / 视角 / 位置都不许变，不许重画、"
                     "不许换材质、不许加也不许删。现在只命中 %s。" % (_hits or "0 个严格措辞"))
    # L11 C 档改「形状 / 几何」时不许改「材质 / 质感」（作者 2026-10-14）
    if stage == "sketch" and rung == "C" and text:
        inc = extract_increment(text)
        _geo = [k for k in GEOM_CHANGE_MARKERS if k in inc]
        if _geo and not has_material_keep(text):
            v.append("L11 C 档要改【形状 / 几何】（命中 %s），但简报里没写明**不要修改材质 / "
                     "质感**（作者 2026-10-14：「对 C 档修改物理几何的地方不修改材质……"
                     "我建议说'不要修改材质'」）—— 形状 / 几何是物理（该改），材质 / 质感是"
                     "观感（不该顺手换），两者要分开。做法：在增量块里加一句「不要修改材质"
                     "」—— 准确写法是「**材质保持不变**（以给的那张图 —— 上一版的材质为准，"
                     "不要改）」。★ 不要替模型指定具体材质（写「材质保持光滑」这类是错的）。"
                     "实测：C 档只让把圆球压成扁球，模型却把上一版的光滑球面一起重画成了粗糙石块"
                     "（keep_gate 质感漂移 0.881）。"
                     % (_geo[:3],))
        elif not _geo:
            w.append("L11 这一轮 C 档没看出要改形状 / 几何；确认不动材质 —— 建议仍写一句"
                     "「材质保持不变（以给的那张图为准）」，免得模型顺手换材质"
                     "（形状是物理，材质是观感）。")
        _mh = material_prescribe_hint(text)
        if _mh:
            w.append("L11 简报里点名了具体材质「%s」—— 应该写「材质保持不变」（以给的那张图的"
                     "材质为准），**不要替模型指定材质**（作者 2026-10-14：「不要写材质保持光滑啊，"
                     "应该是材质保持不变」）。" % _mh)
    # L12 B 档必须写明「保留上一档（A）画得好的元素，可在其基础上更美观」（作者 2026-10-14）
    if stage == "sketch" and rung == "B" and text and not has_inherit_clause(text):
        v.append("L12 B 档必须写明**保留上一档（A）画得好的元素**，甚至在其基础上更美观"
                 "（作者 2026-10-14：「B 保留 A 好看的元素，比如如果 A 画的核子好看就保留核子，"
                 "甚至可以在此基础上更美观」）—— B 是 A 的续，不是另起一张。做法：加一句"
                 "「上一档画得好的部分（形状 / 物体 / 布局 / 配色）保留，并在此基础上做得更好看；"
                 "除下面要改的，其余原样保留」。")
    bv, bw = brief_shape(rung, text, refs, prev_text)
    v += bv
    w += bw
    if stage == "render":
        names = [r.get("rung") for r in rungs]
        if not ("A" in names and "B" in names and "C" in names):
            v.append("L6 出成品位图之前阶梯必须至少有 A、B、C 三段（现在只有 %s）。" % names)
        # L3b render 档：累积草图简报里三样必须齐全（L3 在 B 档已降级为软警，
        # 允许分几步慢慢加，但出成品位图前必须补齐）。
        # 只看 sketch 段的累积简报（render 段简报是 IR 编译稿，不算「草图阶梯」）
        if rungs:
            _sk = [r for r in rungs if r.get("stage", "sketch") == "sketch"]
            last = (_sk or rungs)[-1]
            lb = last.get("brief")
            lt = ""
            if lb:
                lp = Path(lb)
                lt = _read(lp if lp.is_absolute() else Path(gen_dir) / lb)
            miss = []
            if not any(k in lt for k in PANEL_MARKERS):
                miss.append("面板序列")
            if not any(k in lt for k in WHITELIST_MARKERS + NO_DECOR_MARKERS):
                miss.append("输出硬约束（标签白名单 / 不要图例标题说明文字）")
            if miss:
                v.append("L3b 出成品位图前，累积草图简报（第 %s 段 %s）还缺：%s —— "
                         "L3 允许 B 档分步加，但 render 前必须补齐。"
                         % (last.get("rung"), os.path.basename(lb or ""), "、".join(miss)))
        if outdir:
            od = os.path.abspath(outdir)
            for r in rungs:
                if r.get("rung") == "A" and r.get("outdir") and os.path.abspath(r["outdir"]) == od:
                    v.append("L2 构图依据来自 A 档（%s）—— A 档只作诊断，不许进交付链。" % od)
    return rung, v, w, idx


def do_record(gen_dir, brief_path, outdir, refs, add=None, stage="sketch", content_refs=None):
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
    # 出图记录里的 `refs` 会把 --content-ref 一起算进去；登记"风格参考"时必须剔掉它，
    # 否则 L7（风格图贯穿整条阶梯）会把上一轮的图当成风格图比，误判。
    _all = (calls or {}).get("refs") or list(refs or [])
    _cr = (calls or {}).get("content_refs") or list(content_refs or [])
    _crn = {os.path.normcase(os.path.abspath(x)) for x in _cr if x}
    _style = [x for x in _all if os.path.normcase(os.path.abspath(x)) not in _crn]
    entry = {
        "rung": rung,
        "stage": stage,
        "brief": (os.path.relpath(Path(brief_path).resolve(), Path(gen_dir)).replace("\\", "/")
                  if brief_path else None),
        "brief_chars": len(text.strip()),
        "outdir": str(Path(outdir).resolve()) if outdir else None,
        "refs": _style or _all,
        "content_refs": _cr,
        "seeds": (calls or {}).get("seeds") or [],
        "inc_chars": len(inc),
        "add": rel_add,
    }
    rungs.append(entry)
    led["rungs"] = rungs
    led["gen_dir"] = str(Path(gen_dir).resolve())
    p = save_ledger(gen_dir, led)
    return entry, p


def selftest():
    """L11 / L12 标定（作者 2026-10-14）：造最小账本 + 简报，直接调 precheck 看判据对不对。

        python ladder_gate.py --selftest

    返回 0 = 全部符合期望；1 = 有不符合（改了 L11 / L12 判据就跑一次）。
    """
    import tempfile
    g = Path(tempfile.mkdtemp(prefix="ladder_selftest_"))
    style = "_selftest_style.png"          # 只比 basename，不需要真文件
    a_dir, b_dir = str(g / "A"), str(g / "B")
    b_core = ("画成 3D 科研示意图；面板序列：从左到右 a/b/c；"
              "图上只许出现这些标签：beam。")
    inc = ("\n════ 上一轮画错的地方（这一轮必须改对）════\n"
           "严格在上一张图上改：其余原样保留，不许重画/删/加。\n"
           "[HP3] 每核沿水平束流压扁成高瘦扁球，改成高瘦扁球，不是圆球。\n")
    mat = "核的材质、质感、配色一律保持上一版，不要修改材质。\n"
    (g / "a.md").write_text("一句话。", encoding="utf-8")
    (g / "b_no.md").write_text(b_core, encoding="utf-8")
    (g / "b_ok.md").write_text(b_core + "上一档画得好的元素保留、并在此基础上更美观。",
                               encoding="utf-8")
    (g / "c_geo.md").write_text(b_core + inc, encoding="utf-8")
    (g / "c_ok.md").write_text(b_core + inc + mat, encoding="utf-8")
    (g / "c_smooth.md").write_text(
        b_core + inc + "核的材质保持光滑，不要改。", encoding="utf-8")

    def rung(nm, od, refs, bc):
        return {"rung": nm, "stage": "sketch", "brief": None, "brief_chars": bc,
                "outdir": od, "refs": refs, "content_refs": [], "seeds": [1]}

    ab = [rung("A", a_dir, [], 10), rung("B", b_dir, [style], len(b_core))]

    def run(ledger, brief, od, refs, cr):
        (g / "ladder.json").write_text(json.dumps(
            {"version": 1, "gen_dir": str(g), "rungs": ledger}, ensure_ascii=False),
            encoding="utf-8")
        _r, v, w, _i = precheck(str(g), brief, od, refs, "sketch", cr)
        return v, w

    cases = [
        ("L12  B 档缺「保留上一档好的元素」", ab[:1], "b_no.md", "Bt1", True, False),
        ("L12  B 档写了继承句", ab[:1], "b_ok.md", "Bt2", False, False),
        ("L11  C 档改几何、没写材质", ab, "c_geo.md", "Ct1", True, False),
        ("L11  C 档写「材质保持不变」", ab, "c_ok.md", "Ct2", False, False),
        ("L11  C 档写「材质保持光滑」（该软警）", ab, "c_smooth.md", "Ct3", False, True),
    ]
    bad = 0
    print("=" * 70)
    print("ladder_gate 自检 —— L11 / L12 标定（作者 2026-10-14）")
    print("=" * 70)
    for nm, ledger, brief, od, want_fail, want_warn in cases:
        v, w = run(ledger, str(g / brief), str(g / od), [style],
                   [os.path.join(a_dir if od.startswith("Bt") else b_dir, "x.png")])
        hit = any(x.startswith(("L11", "L12")) for x in v)
        warned = any("点名了具体材质" in x for x in w)
        ok = (hit == want_fail) and (warned == want_warn)
        bad += 0 if ok else 1
        print("%-40s 期望 %-4s%s 实得 %-4s%s  %s"
              % (nm, "FAIL" if want_fail else "PASS", " +软警" if want_warn else "",
                 "FAIL" if hit else "PASS", " +软警" if warned else "",
                 "\u2713" if ok else "\u2717 不符"))
        if not ok:
            for x in v + w:
                print("      | %s" % x)
    print("-" * 70)
    print("全部符合期望" if not bad else "有 %d 项不符" % bad)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(
        description="提示词阶梯闸门 A → B → C（见文件头）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gen-dir", default=None, help="账本目录（缺省由 --outdir 往上找）")
    ap.add_argument("--outdir", default=None, help="这一轮出图的目录")
    ap.add_argument("--brief", default=None, help="这一轮的简报 .md")
    ap.add_argument("--add", default=None, help="C 档：上一轮的错误清单 .md（登记时可给）")
    ap.add_argument("--ref", action="append", default=[], help="这一轮的风格参考图")
    ap.add_argument("--content-ref", action="append", default=[],
                    help="这一轮的构图依据；B/C 档必须给上一轮的图（L9）")
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch")
    ap.add_argument("--record", action="store_true", help="出图成功后登记这一段")
    ap.add_argument("--waive", default=None, help="确实要放行时的理由（会打印出来）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="跑 L11 / L12 标定（造最小账本 + 简报，直接判），不碰真账本")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    gen_dir = find_gen_dir(a.outdir or ".", a.gen_dir)
    print("=" * 70)
    print("ladder_gate —— 提示词阶梯闸门（A → B → C）")
    print("=" * 70)
    print("账本 : %s" % ledger_path(gen_dir))

    if a.record:
        entry, p = do_record(gen_dir, a.brief, a.outdir, a.ref, a.add, a.stage, a.content_ref)
        n = len(load_ledger(gen_dir)["rungs"])
        print("已登记第 %d 段：%s 档 | 简报 %d 字符 | 增量 %d 字符"
              % (n, entry["rung"], entry["brief_chars"], entry["inc_chars"]))
        print("账本 -> %s" % p)
        return 0

    rung, v, w, idx = precheck(gen_dir, a.brief, a.outdir, a.ref, a.stage, a.content_ref)
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
            print("  阶梯：A（一句话，默认不带参考图，只作诊断）→ "
                  "B（+ 风格图 + 面板序列 + 输出硬约束）→ "
                  "C（**严格在上一张图上改**，只补上一轮真画错的）")
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
