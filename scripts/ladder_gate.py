#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ladder_gate —— 提示词阶梯闸门（A → B → C → D，作者 2026-10-06 / 2026-10-14）
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

    L1  顺序不许跳档：前四段必须是 A、B、C、D，之后都是 D（重复修正档）。
    L2  A 档 = 一句话：简报 <= 80 字符，**默认不带风格参考图**（作者 2026-10-13：
        「把 A 档不放参考图作为默认」）；带了 --ref 只作软警。A 档产物**只作诊断**，
        不许进交付链（--stage render 时构图依据来自 A 档的 outdir → 硬伤）。
    L3  B 档必须有三样：① **风格参考图**（A 档默认没有，风格从 B 档引入 ——
        作者 2026-10-13「B 档还是有参考图」）；② 面板序列；③ 输出硬约束
        （标签白名单 / 不要图例标题说明文字）。
        ★ **B 档不给构图依据**（不给 --content-ref）：作者 2026-10-14「B 档输入取消输入
        A 档的图，只有参考图」——「把 A 的好元素搬进 B」是新的 **C 档**干的事（见 L9/L12）。
    L4  每一轮 **D 档**必须带「上一轮错在哪 → 改成什么」那一节，且 <= 3000 字符（增量，
        不是规格书）；简报还得是累积稿（上一轮简报的内容在里面）。
    L6  出成品位图之前，阶梯必须至少有 A、B、C、D 四段。
    L7  **风格参考图必须贯穿整条阶梯**：B/C/D 档的 `--ref` 必须与 B 档一致
        （作者 2026-10-07：「BC档和A档完全不一样啊，BC档是辅助A档物理错误的」）——
        B/C/D 是同一条阶梯的续，中途换风格图 = 另起一张。
    L8  **慢慢增加提示词**（作者 2026-10-07：「你这B档提示词一下子加太多提示词
        导致图片一下就很难看了」）：草图档每上一档，简报相对上一档最多增加
        MAX_STEP_GROWTH（250）字符 —— 一次只加一条新约束。实测 v43：A 档 31 字符
        直接跳到 B 档 767 字符，出图的观感与 A 档完全不是一张图。
        render 档豁免（它的简报是 IR 编译稿 + 错误清单，见 §0.6）。
    L9  **每一档都要给「修改前的图」，但按档位给不同的图**（作者 2026-10-13 / 2026-10-14）：
          · **B 档**：不给 —— B 的输入只有风格图（L3）。
          · **C 档（元素替换档，新）**：必须给**两条** --content-ref ——
            一条落在 **A 档**目录（拿它的好元素），一条落在 **B 档**目录（要被替换的那一版）。
          · **D 档（物理修正档，= 原 C 档）**：必须给一条落在 **C 档**目录的 --content-ref。
        只给文字说「改这个、别的别动」不够 —— 模型看不到上一版，就会把上一版
        已经画对的东西一起重画（实测：A 档的 QGP 火球是从风格图继承来的，
        B 档看不到上一版、只好自己重画，同一张图的 QGP 在两档之间换了形状）。
        不给 = 硬伤（--waive "理由" 可放行，理由照抄进交付说明）。
    L10 **D 档必须严格在上一张图上改**（作者 2026-10-13：「只有 C 档时严格在上一张
        图片上改」）：只改下面列出的那几条，其余连形状 / 质感 / 配色 / 光源 / 视角 /
        位置都不许变 —— 不许重画、不许换材质、不许加也不许删（命中 >= 2 个严格措辞）。
        为什么标出来：不写"严格"，上一档刚改对的东西会被整张重画一遍
        （实测：把上一档的火球质感重画成了光滑球）。
        ★ **A/B/C 档不判这条**（作者 2026-10-13：「B 不就一轮吗，怎么还有挑着保留这一说」）：
        B 只跑一轮（简报 = A 的一句话内容 + 面板序列 + 输出硬约束）、C 是元素替换档；
        真正的「严格只改这几处、其余一模一样」只有 D 档。
    L11 **D 档改「形状 / 几何」时不许改「材质 / 质感」**（作者 2026-10-14：
        「对 C 档修改物理几何的地方不修改材质……我建议说'不要修改材质'」）：
        形状 / 几何是**物理**（该改），材质 / 质感是**观感**（不该顺手换）。增量块
        只要命中形状 / 几何类词（形状 / 几何 / 压扁 / 尺寸 / 位置 / 朝向…），简报里
        就必须写明**材质保持不变**，否则硬伤。★ 写法是「材质保持不变（以给的那张图 ——
        上一版的材质为准）」，**不要替模型指定具体材质**（作者 2026-10-14：「不要写材质
        保持光滑啊，应该是材质保持不变」）；点名了具体材质只出软警。实测：D 档只让把圆球
        压成扁球，模型把上一版的光滑球面一起重画成了粗糙石块（keep_gate 漂移 0.881）。
    L12 **C 档（元素替换档）必须写明「把 A 档画得好的元素搬进来、替换 B 档里对应画得差的
        那个东西」**（作者 2026-10-14：「在 B 档和 C 档之间加一个档次作为新的 C 档，
        将 A 档的优秀元素替换 B 档中相应的东西」）：C = A 的好元素 × B 的版式。必须是
        **元素级替换**（核子球团、火球介质这类具体对象），不是整张重画；A 画得好的部分
        要留着，B 里对应的那个东西才被换掉。缺这句 = 硬伤。
        ★ 与 L10 不冲突：L10 只管 D 档的「严格…不许变」措辞。
    L13 **位图（render）档必须在上一张草图的基础上改，不许推倒重画**（作者 2026-10-14：
        「D 档输出的草图到位图的阶段一定要在前面的图基础上修改，修改物理错误和使相应的
        元素变得更优秀，绝对不要将原来优秀的元素换掉」）：render 档必须 ① 给一条落在
        最后一个草图档目录里的 --content-ref；② 简报写明「在上一张图的基础上改：只改
        下面列出的物理错误，把对应的元素做得更优秀，**不要换掉已经画对的元素**」。
        缺一 = 硬伤。

## 用法

    # 出图前查（ref_guard.py --run 会自动调）
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/A --brief <fig>/gen/A_brief.md
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md \
            --ref <风格图>                              # L3：B 只给风格图，不给 --content-ref
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/C --brief <fig>/gen/C_brief.md \
            --ref <风格图> --content-ref <fig>/gen/A/sketch_s1.png \
            --content-ref <fig>/gen/B/sketch_s2.png     # L9：C 同时给 A 和 B 的图
    python3 scripts/ladder_gate.py --stage sketch --outdir <fig>/gen/D --brief <fig>/gen/D_brief.md \
            --ref <风格图> --content-ref <fig>/gen/C/sketch_s3.png   # L9：D 给 C 的图
    # 出图后登记（ref_guard.py --run 成功退出后自动调）
    python3 scripts/ladder_gate.py --record --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md
    # 单独查账本
    python3 scripts/ladder_gate.py --gen-dir <fig>/gen --stage render

`--waive "理由"` 可放行（理由会被打印出来，交付说明里必须照抄）。

自检（L9 / L12 / L13 标定；改了判据就跑一次）：

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

# L14：用了整幅风格参考图，必须写「参考图自带、本图不要」黑名单（v4.25）
LEAK_HEADERS = ("【参考图自带、本图不要】", "【参考图自带，本图不要】", "参考图自带、本图不要", "参考图自带，本图不要", "风格图自带、本图不要", "风格图自带，本图不要")

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

# L12：C 档 = **元素替换档** —— 必须写明把 A 档画得好的元素搬进来、替换 B 档里对应的那一个
#      （作者 2026-10-14：「在 B 档和 C 档之间加一个档次作为新的 C 档，将 A 档的优秀元素
#      替换 B 档中相应的东西」）
A_SWAP_MARKERS = ("把A档", "把A", "用A档", "用A的", "取A档", "搬进来", "搬到", "搬入", "搬过去",
                  "移植", "挪过来", "替换B", "替换掉B", "替换B档", "替换过来", "替换进去",
                  "换掉B", "B里对应", "对应的那处", "对应的那一个", "对应的东西", "以A档为准",
                  "以A为准", "A档更好", "A的核子", "A画得好", "A好看的", "继承A", "沿用A",
                  "A档的元素", "A的元素", "把上一档", "把上一版", "上一档的核子", "上一版的核子")

# L13：render 档（草图 → 位图）必须写明「在上一张图的基础上改」+ 「不要换掉画对的元素」
#      （作者 2026-10-14：「D 档输出的草图到位图的阶段一定要在前面的图基础上修改，修改物理
#      错误和使相应的元素变得更优秀，绝对不要将原来优秀的元素换掉」）
RENDER_BASE_MARKERS = ("在上一张图", "在上一版", "在上一轮", "在前一张图", "在上一幅图",
                       "以上一张图为", "以上一版为", "基于上一张", "沿用上一张", "接着上一张",
                       "在上一张草图", "在当前这张图", "在这张图的基础上", "在选定的草图",
                       "在选定草图", "以上一张草图为", "的基础上改", "基础上修改", "基础上改",
                       "基础上润色", "基础上精修", "在本图的基础上", "在本草图的基础上")
RENDER_KEEP_MARKERS = ("不要换掉", "别换掉", "不许换掉", "不要替换掉", "不许替换掉",
                       "不要重画", "不许重画", "保留画对的", "不要丢掉", "不许丢掉",
                       "不要删掉", "不要删除", "不许删除", "原样保留", "其余保持", "其余不变",
                       "保留原本", "保留已经画对", "保留上一张画对", "不要动画对", "别动画对")

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
    """A → B → C → D；D 档之后还是 D（作者 2026-10-14 加 C 档、原 C 改 D）。"""
    return "ABCD"[idx] if idx < 4 else "D"


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


def has_swap_clause(text):
    """C 档有没有写明「把上一档（A）画得好的元素搬进来、替换 B 里对应的那一个」。"""
    if not text:
        return False
    t = _squash(text)
    if any(_squash(k) in t for k in A_SWAP_MARKERS):
        return True
    has_take = any(k in t for k in ("搬", "拿", "取", "用", "继承", "沿用", "以"))
    has_a = any(k in t for k in ("A档", "A版", "上一档", "上一版", "上一张", "上一轮"))
    has_put = any(k in t for k in ("替换", "换掉", "替", "换", "对应"))
    return has_take and has_a and has_put


def has_render_keep(text):
    """L13：位图简报有没有同时写「在上一张图的基础上改」与「不要换掉画对的元素」。"""
    if not text:
        return False, [], []
    base = [k for k in RENDER_BASE_MARKERS if k in text]
    keep = [k for k in RENDER_KEEP_MARKERS if k in text]
    return bool(base and keep), base, keep


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
    """按档位判简报的「形状」（长度 / 必须有哪些段）。判据编号见文件头。"""
    v, w = [], []
    n = len(text.strip())
    if rung == "A":
        if n > MAX_A_CHARS:
            v.append("L2 A 档必须是一句话（<= %d 字符），这份简报 %d 字符 —— A 档是用来"
                     "看模型对这个题材的先验的，不是交付稿；要加约束请走 B 档。"
                     % (MAX_A_CHARS, n))
        if refs:
            w.append("L2 A 档**默认不带风格参考图**（作者 2026-10-13「把 A 档不放参考图作为默认」）"
                     "—— A 档是看模型对这个题材的先验、只作诊断，风格由 B 档引入。"
                     "这一轮带了 --ref %s，确认是有意的。" % (refs,))
    elif rung == "B":
        if n < 40:
            v.append("L3 B 档太短（%d 字符）：B = A 的文字 + 面板序列 + 输出硬约束。" % n)
        if n > MAX_B_CHARS:
            v.append("L3 B 档太长（%d 字符 > %d）：这一档只加面板序列与输出硬约束，"
                     "物理增量留给 D 档。" % (n, MAX_B_CHARS))
        if not refs:
            v.append("L3 B 档必须带**风格参考图**（--ref）：A 档默认不带参考图，风格是从 B 档"
                     "开始引入的（作者 2026-10-13「B 档还是有参考图」）。")
        if not any(k in text for k in PANEL_MARKERS):
            w.append("L3 B 档还没有【面板序列】（「面板 a/b/c」「从左到右」这类）—— "
                     "L8 允许分几步加，但**进 render 前必须补齐**（由 L3b 在 render 档把关）。")
        if not any(k in text for k in WHITELIST_MARKERS + NO_DECOR_MARKERS):
            w.append("L3 B 档还没有【输出硬约束】（标签白名单 / 不要图例标题说明文字）—— "
                     "L8 允许分几步加，但进 render 前必须补齐。")
        w.append("L3 提醒：B 档**不给 --content-ref**（作者 2026-10-14：「B 档输入取消输入 "
                 "A 档的图，只有参考图」）—— 不把 A 的图交给模型，A 的好元素由 C 档搬进来。")
    elif rung == "C":
        if n < 40:
            v.append("L12 C 档太短（%d 字符）：C = B 的简报（累积稿）+「把 A 档画得好的元素"
                     "搬进来、替换 B 里对应的那一处」那一段。" % n)
        if prev_text and prev_text.strip() and prev_text.strip() not in text:
            w.append("L12 这一轮简报不是累积稿（上一轮简报的内容不在里面）——"
                     "确认是有意重写，还是漏了。")
    else:
        inc = extract_increment(text)
        if not inc:
            v.append("L4 D 档缺【上一轮真画错的清单】：简报里要有"
                     "「上一轮画错的地方 → 这一轮必须改对」那一节。")
        else:
            if len(inc) > MAX_INC_CHARS:
                v.append("L4 增量那一节太长（%d 字符 > %d）：D 档只补上一轮真画错的那几条，"
                         "不是再发一次规格书。" % (len(inc), MAX_INC_CHARS))
            if not any(k in inc for k in FAIL_MARKERS):
                v.append("L4 增量那一节看不出「错在哪 → 改成什么」。")
        if prev_text and prev_text.strip() and prev_text.strip() not in text:
            w.append("L4 这一轮简报不是累积稿（上一轮简报的内容不在里面）——"
                     "确认是有意重写，还是漏了。")
    if refs and rung in ("B", "C", "D"):
        if not any(k in text for k in LEAK_HEADERS):
            if rung == "D":
                v.append("L14 D 档用了整幅风格参考图，但简报没有【参考图自带、本图不要】黑名单："
                         "风格图里的物理对象（如 QGP 火球 + 放射箭头）会被‘其余原样保留’保住；"
                         "必须逐条点名，不能只写自己注意到的那几条。")
            else:
                w.append("L14 用了整幅风格参考图，建议加【参考图自带、本图不要】黑名单："
                         "逐条点名风格图里的物理对象，免得被当风格抄进来。")
    return v, w


def order_checks(led):
    rungs = led.get("rungs") or []
    names = [r.get("rung") for r in rungs]
    want = [rung_name(i) for i in range(len(names))]
    if names != want:
        return ["L1 阶梯跳档：账本里是 %s，必须是 %s（A → B → C → D…）。" % (names, want)]
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
                         "B/C/D 档是同一张风格书的续，中途换风格图 = 另起一张。"
                         % (anchor.get("rung"), anchor.get("rung"), a_refs, now_refs))
    # L8 慢慢加提示词：每上一档只加一条新约束（作者 2026-10-07）
    if stage == "sketch" and prev is not None:
        grow = len(text.strip()) - (prev.get("brief_chars") or 0)
        if grow > MAX_STEP_GROWTH:
            v.append("L8 这一档比上一档一次多写了 %d 字符（上限 %d）—— 「慢慢增加提示词」："
                     "每上一档只加一条新约束，一次加太多会把上一档的观感整个换掉"
                     "（实测 v43：A 档 31 字符 → B 档 767 字符，B/C/D 出图跟 A 完全不一样）。"
                     % (grow, MAX_STEP_GROWTH))
    # ── L9 每一档「给不给上一张图」（作者 2026-10-13 / 2026-10-14）──
    #    B 档：**不给** --content-ref（B 的输入只有风格图，A 的图不进 B）
    #    C 档：给两条 —— A 档的图（要搬进来的好元素）+ B 档的图（要被替换的那一版）
    #    D 档：给一条 —— 紧邻上一档（C）的图
    if stage == "sketch" and rungs:
        def _which_rung(x):
            cp = os.path.abspath(x)
            for r in rungs:
                od = r.get("outdir")
                if not od:
                    continue
                od_a = os.path.abspath(od)
                if cp == od_a or cp.startswith(od_a + os.sep):
                    return r.get("rung")
            return None

        def _dir_of(nm):
            for r in rungs:
                if r.get("rung") == nm and r.get("outdir"):
                    return r["outdir"]
            return None

        hits = [(x, _which_rung(x)) for x in (content_refs or []) if x]
        prev_od = os.path.abspath(prev["outdir"]) if (prev and prev.get("outdir")) else None
        if rung == "B":
            inside = [x for x, nm in hits if nm]
            if inside:
                v.append("L9 B 档**不许给构图依据（--content-ref）**（作者 2026-10-14：「B 档输入"
                         "取消输入 A 档的图，只有参考图」）—— 这一轮给了 %s。B 的输入只有风格"
                         "参考图；A 档的好元素是留给 **C 档**搬进来的（L12）。" % inside)
            elif hits:
                w.append("L9 B 档带了 --content-ref（%s）—— B 的输入应当只有风格参考图，"
                         "确认这是有意的。" % [x for x, _ in hits])
        elif rung == "C":
            got_a = [x for x, nm in hits if nm == "A"]
            got_b = [x for x, nm in hits if nm == "B"]
            if not got_a:
                v.append("L9 C 档必须把**上一档（A）的图**当 --content-ref 交进去（作者 2026-10-14："
                         "C 档「将 A 档的优秀元素替换 B 档中相应的东西」）—— 不把 A 的图交上去，"
                         "模型没法知道要搬哪几个好元素。做法：--content-ref %s"
                         % (_dir_of("A") or "<gen>/A/sketch_sN.png"))
            if not got_b:
                v.append("L9 C 档必须把**要被替换的那一版（B 的图）**当 --content-ref 交进去 —— "
                         "做法：--content-ref %s" % (_dir_of("B") or "<gen>/B/sketch_sN.png"))
            if len(got_a) > 1 or len(got_b) > 1:
                w.append("L9 C 档同一档给了多张图（A 档 %d 张 / B 档 %d 张）—— 确认是要同时看多张。"
                         % (len(got_a), len(got_b)))
        elif rung == "D":
            hit_prev = any(nm and prev and nm == prev.get("rung") for _x, nm in hits)
            if not hits:
                v.append("L9 D 档必须把**修改前的那张图（上一档 C）**当 --content-ref 交进去"
                         "（作者 2026-10-13：「每次修改都要给修改前的图，方便模型理解什么修改、"
                         "什么保留」）—— 这一轮没给任何落在本阶梯**已登记 rung 目录**里的 "
                         "--content-ref。做法：--content-ref %s"
                         % (prev_od or "<gen>/<上一档>/sketch_sN.png"))
            elif not hit_prev:
                w.append("L9 给的 --content-ref 不在**紧邻的上一档**目录里 —— "
                         "确认给的是「修改前」那一版，不是更早的版本。")
    # L10 D 档必须严格在上一张图上改（作者 2026-10-13）；A/B/C 档不判（C 是元素替换）
    if stage == "sketch" and rung == "D":
        _hits = [k for k in STRICT_KEEP_MARKERS if k in (text or "")]
        if text and len(_hits) < 2:
            v.append("L10 D 档必须写清它是**严格在上一张图上改**（作者 2026-10-13："
                     "「只有 C 档时严格在上一张图片上改」—— 那一档现在叫 D 档）—— 只改下面"
                     "列出的那几条，其余连形状 / 质感 / 配色 / 光源 / 视角 / 位置都不许变，"
                     "不许重画、不许换材质、不许加也不许删。现在只命中 %s。"
                     % (_hits or "0 个严格措辞"))
    # L11 D 档改「形状 / 几何」时不许改「材质 / 质感」（作者 2026-10-14）
    if stage == "sketch" and rung == "D" and text:
        inc = extract_increment(text)
        _geo = [k for k in GEOM_CHANGE_MARKERS if k in inc]
        if _geo and not has_material_keep(text):
            v.append("L11 D 档要改【形状 / 几何】（命中 %s），但简报里没写明**不要修改材质 / "
                     "质感**（作者 2026-10-14：「对 C 档修改物理几何的地方不修改材质……"
                     "我建议说'不要修改材质'」）—— 形状 / 几何是物理（该改），材质 / 质感是"
                     "观感（不该顺手换），两者要分开。做法：在增量块里加一句「不要修改材质」"
                     "—— 准确写法是「**材质保持不变**（以给的那张图 —— 上一版的材质为准，不要改）」。"
                     "★ 不要替模型指定具体材质（写「材质保持光滑」这类是错的）。"
                     "实测：只让把圆球压成扁球，模型却把上一版的光滑球面一起重画成了粗糙石块"
                     "（keep_gate 质感漂移 0.881）。" % (_geo[:3],))
        elif not _geo:
            w.append("L11 这一轮 D 档没看出要改形状 / 几何；确认不动材质 —— 建议仍写一句"
                     "「材质保持不变（以给的那张图为准）」，免得模型顺手换材质"
                     "（形状是物理，材质是观感）。")
        _mh = material_prescribe_hint(text)
        if _mh:
            w.append("L11 简报里点名了具体材质「%s」—— 应该写「材质保持不变」（以给的那张图的"
                     "材质为准），**不要替模型指定材质**（作者 2026-10-14：「不要写材质保持光滑啊，"
                     "应该是材质保持不变」）。" % _mh)
    # L12 C 档 = 元素替换档：必须写明「把 A 档画得好的元素搬进来、替换 B 里对应的那一个」
    if stage == "sketch" and rung == "C" and text and not has_swap_clause(text):
        v.append("L12 C 档必须写明**把上一档（A）画得好的元素搬进来、替换 B 档里对应的那一个**"
                 "（作者 2026-10-14：「在 B 档和 C 档之间加一个档次作为新的 C 档，将 A 档的"
                 "优秀元素替换 B 档中相应的东西」）—— C = A 的好元素 × B 的版式。做法：在简报里"
                 "写一段「把 A 档画得好的 <元素>（核子 / 火球 / 配色…）搬进来，替换 B 档里对应的"
                 "<东西>；A 画得好的部分要留着，B 里对应的那一处换掉」。")
    # L13 草图 → 位图：必须在「上一张草图」的基础上改（作者 2026-10-14）
    if stage == "render":
        last_sk = None
        for r in rungs:
            if r.get("stage", "sketch") == "sketch":
                last_sk = r
        sk_hits = []
        if last_sk and last_sk.get("outdir"):
            od_a = os.path.abspath(last_sk["outdir"])
            for x in (content_refs or []):
                if x and (os.path.abspath(x) == od_a or os.path.abspath(x).startswith(od_a + os.sep)):
                    sk_hits.append(x)
        if not (content_refs or []):
            v.append("L13 出位图必须把**上一张草图**当 --content-ref 交进去（作者 2026-10-14："
                     "「D 档输出的草图到位图的阶段一定要在前面的图基础上修改」）—— 这一轮没给。"
                     "做法：--content-ref %s"
                     % ((os.path.join(last_sk["outdir"], "sketch_sN.png")
                         if (last_sk and last_sk.get("outdir")) else "<gen>/<最后一档>/sketch_sN.png")))
        elif not sk_hits:
            v.append("L13 给的 --content-ref 不在**最后一个草图档**的目录里 —— 位图要在"
                     "「上一张草图」的基础上改，别拿更早版本。")
        _okk, _b, _k = has_render_keep(text or "")
        if not _okk:
            v.append("L13 位图简报必须**同时**写明两件事（作者 2026-10-14）：「在上一张图的基础上"
                     "改」+「不要换掉原来画对的元素」。作者原话：「修改物理错误和使相应的元素变得"
                     "更优秀，绝对不要将原来优秀的元素换掉」—— 现在【基础上改】命中 %s、"
                     "【别换掉】命中 %s。" % (_b or "0 个", _k or "0 个"))
    bv, bw = brief_shape(rung, text, refs, prev_text)
    v += bv
    w += bw
    if stage == "render":
        names = [r.get("rung") for r in rungs]
        if not all(x in names for x in ("A", "B", "C", "D")):
            v.append("L6 出成品位图之前阶梯必须至少有 A、B、C、D 四段（现在只有 %s）。" % names)
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
    """L9 / L12 / L13 标定（作者 2026-10-14）：造最小账本 + 简报，直接调 precheck 看判据对不对。

        python ladder_gate.py --selftest

    返回 0 = 全部符合期望；1 = 有不符合（改了 L9 / L12 / L13 判据就跑一次）。
    """
    import tempfile
    g = Path(tempfile.mkdtemp(prefix="ladder_selftest_"))
    style = "_selftest_style.png"          # 只比 basename，不需要真文件
    a_dir, b_dir, c_dir, d_dir = (str(g / x) for x in "ABCD")
    b_core_noleak = ("画成 3D 科研示意图；面板序列：从左到右 a/b/c；"
                     "图上只许出现这些标签：beam。")
    leak = "【参考图自带、本图不要】参考图里的 QGP 火球和放射箭头，本图不要；"
    b_core = ("画成 3D 科研示意图；面板序列：从左到右 a/b/c；"
              + leak + "图上只许出现这些标签：beam。")
    swap = ("把上一档（A）画得好的核子搬进来，替换 B 档里对应的那两个球；"
            "A 画得好的部分留着。\n")
    inc = ("\n════ 上一轮画错的地方（这一轮必须改对）════\n"
           "严格在上一张图上改：其余原样保留，不许重画/删/加。\n"
           "[HP3] 每核沿水平束流压扁成高瘦扁球，改成高瘦扁球，不是圆球。\n")
    mat = "核的材质、质感、配色一律保持上一版，不要修改材质。\n"
    rend_ok = ("在本图（上一张草图）的基础上改：只改下面列出的物理错误，把对应元素做得更好，"
               "不要换掉原来画对的元素，其余原样保留。\n")
    (g / "a.md").write_text("一句话。", encoding="utf-8")
    (g / "c_ok.md").write_text(b_core + swap, encoding="utf-8")
    (g / "c_no.md").write_text(b_core, encoding="utf-8")
    (g / "d_geo.md").write_text(b_core + inc, encoding="utf-8")
    (g / "d_ok.md").write_text(b_core + inc + mat, encoding="utf-8")
    (g / "d_smooth.md").write_text(b_core + inc + "核的材质保持光滑，不要改。", encoding="utf-8")
    (g / "d_noleak.md").write_text(b_core_noleak + inc + mat, encoding="utf-8")
    (g / "r_ok.md").write_text(rend_ok, encoding="utf-8")
    (g / "r_no.md").write_text("按 IR 画这张图，把物理错误改对。", encoding="utf-8")

    def rung(nm, od, refs, bc):
        return {"rung": nm, "stage": "sketch", "brief": None, "brief_chars": bc,
                "outdir": od, "refs": refs, "content_refs": [], "seeds": [1]}

    ab = [rung("A", a_dir, [], 10), rung("B", b_dir, [style], len(b_core))]
    abc = ab + [rung("C", c_dir, [style], len(b_core) + len(swap))]
    abcd = abc + [rung("D", d_dir, [style], len(b_core) + len(inc) + len(mat))]
    ap_ = os.path.join(a_dir, "x.png")
    bp_ = os.path.join(b_dir, "x.png")
    dp_ = os.path.join(d_dir, "x.png")

    def run(ledger, brief, od, refs, cr, stage):
        (g / "ladder.json").write_text(json.dumps(
            {"version": 1, "gen_dir": str(g), "rungs": ledger}, ensure_ascii=False),
            encoding="utf-8")
        return precheck(str(g), brief, od, refs, stage, cr)

    #   (名称, 账本, 简报, outdir 标记, content-ref, stage, 盯哪几条, 期望硬伤, 期望软警)
    a_only = ab[:1]
    cases = [
        ("L12  C 档没写「搬 A 的好元素」", ab, "c_no.md", "Ct1", [ap_, bp_], "sketch",
         ("L12",), True, False),
        ("L12  C 档写了搬 A 的元素", ab, "c_ok.md", "Ct2", [ap_, bp_], "sketch",
         ("L12",), False, False),
        ("L9   C 档没给 A 的图", ab, "c_ok.md", "Ct3", [bp_], "sketch",
         ("L9",), True, False),
        ("L9   B 档给了 A 的图（不许）", a_only, "c_ok.md", "Bt1", [ap_], "sketch",
         ("L9",), True, False),
        ("L10/L11  D 档改几何、没写材质", abcd, "d_geo.md", "Dt1", [dp_], "sketch",
         ("L10", "L11"), True, False),
        ("L10/L11  D 档写「材质保持不变」", abcd, "d_ok.md", "Dt2", [dp_], "sketch",
         ("L10", "L11"), False, False),
        ("L14  D 档缺泄漏黑名单", abcd, "d_noleak.md", "Dt4", [dp_], "sketch",
         ("L14",), True, False),
        ("L11  D 档写「材质保持光滑」（该软警）", abcd, "d_smooth.md", "Dt3", [dp_], "sketch",
         ("L10", "L11"), False, True),
        ("L13  render 简报没写「基础上改/别换掉」", abcd, "r_no.md", "Rt1", [dp_], "render",
         ("L13",), True, False),
        ("L13  render 简报写全 + 给了上一张草图", abcd, "r_ok.md", "Rt2", [dp_], "render",
         ("L13",), False, False),
        ("L13  render 没给任何 --content-ref", abcd, "r_ok.md", "Rt3", [], "render",
         ("L13",), True, False),
    ]
    bad = 0
    print("=" * 74)
    print("ladder_gate 自检 —— L9 / L12 / L13 标定（作者 2026-10-14）")
    print("=" * 74)
    for nm, ledger, brief, od, cr, stage, pres, want_fail, want_warn in cases:
        _r, v, w, _i = run(ledger, str(g / brief), str(g / od), [style], cr, stage)
        hit = any(x.startswith(pres) for x in v)
        warned = any("点名了具体材质" in x for x in w)
        ok = (hit == want_fail) and (warned == want_warn)
        bad += 0 if ok else 1
        print("%-36s 期望 %-4s%s 实得 %-4s%s  %s"
              % (nm, "FAIL" if want_fail else "PASS", " +软警" if want_warn else "",
                 "FAIL" if hit else "PASS", " +软警" if warned else "",
                 "\u2713" if ok else "\u2717 不符"))
        if not ok:
            for x in v + w:
                print("      | %s" % x)
    print("-" * 74)
    print("全部符合期望" if not bad else "有 %d 项不符" % bad)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(
        description="提示词阶梯闸门 A → B → C → D（见文件头）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gen-dir", default=None, help="账本目录（缺省由 --outdir 往上找）")
    ap.add_argument("--outdir", default=None, help="这一轮出图的目录")
    ap.add_argument("--brief", default=None, help="这一轮的简报 .md")
    ap.add_argument("--add", default=None, help="D 档：上一轮的错误清单 .md（登记时可给）")
    ap.add_argument("--ref", action="append", default=[], help="这一轮的风格参考图")
    ap.add_argument("--content-ref", action="append", default=[],
                    help="这一轮的构图依据；给几张按档位定（L9：B 不给 / C 给 A+B / D 给上一档）")
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch")
    ap.add_argument("--record", action="store_true", help="出图成功后登记这一段")
    ap.add_argument("--waive", default=None, help="确实要放行时的理由（会打印出来）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--selftest", action="store_true",
                    help="跑 L9 / L12 / L13 标定（造最小账本 + 简报，直接判），不碰真账本")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    gen_dir = find_gen_dir(a.outdir or ".", a.gen_dir)
    print("=" * 70)
    print("ladder_gate —— 提示词阶梯闸门（A → B → C → D）")
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
                  "B（+ 风格图 + 面板序列 + 输出硬约束；**不给 A 的图**）→ "
                  "C（把 A 档画得好的元素搬进来、替换 B 里对应的）→ "
                  "D（**严格在上一张图上改**，只补上一轮真画错的）")
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
