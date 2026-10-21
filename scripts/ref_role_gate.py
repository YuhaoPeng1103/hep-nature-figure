#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ref_role_gate -- 参考图「角色声明」闸门 + 标签泄漏闸门（作者 2026-10-13 要求）

作者原话：
    「可是风格图只是风格，生图模型总喜欢完全照抄怎么办，有的时候风格图就是我要的物理，
      可以照抄，有的时候风格图不是我要的物理，完全不能照抄」

为什么不能靠提示词里的一句「不要照抄」：
    skill 自己的实测（SKILL.md:613-623，同一张风格图、同一骨架）：
        A 档 一句话 + --ref        -> 与参考图相似度 0.36（4/4 复刻参考图）
        B 档 +106 字符输出硬约束   -> 0.043
        C 档 +物理增量             -> <=0.015
    也就是「抄多少」只跟**简报有多不完备**有关。
    而且负面句会反噬（SKILL.md:655-657：写「不是花生」那三张真画成花生）。
    实测复现（fig_upc_3d/sense_afix）：A2 写了「参考图只给风格、不要照抄它的物体与布局」
    仍然没干净；A3 加上**标签白名单**才干净。

所以本闸门的判据不是「像不像」，而是「**角色有没有被声明、代价有没有被付**」：
    出图前（--check；ref_guard.py --run 会自动调）
        R0  角色必须被声明：--ref-role style-only | style+content —— 没声明 = 硬伤。
            （照抄到底允不允许，必须有人签字，不能靠提示词自己决定。）
        R1  style-only：简报必须**超配**参考图 —— 要求
            (a) 元素枚举 >= 4（逐个点名要画的物体/关系）
            (b) 标签白名单 >= 3（「图上只许出现这些标签：…」）
            缺任一 = 硬伤。这就是实测里把 0.36 打到 0.03 的那个拐点。
        R2  style+content：这张图同时是「内容」，必须满足其一，否则硬伤 ——
            (a) 它也在 --content-ref 里；或
            (b) 简报里明确「照它的物体与布局画 / 复刻参考图」。
            （render 档还必须有客户回执，那一条由 ref_guard 的 choice_gate 兜。）
        R3  用了风格书、简报里却写「不要照抄 / 不是内容模板」这类**负面对照** -> 软警
            （实测负面句反噬；改成正面描述。）
    出图后（--post）
        R4  标签泄漏（硬伤）：识别图上的**整词**；凡 >=4 个字母、逐字置信度都 >= 0.62、
            且不在白名单里 -> 硬伤「图上有简报没允许的标签 X」。
            这一条抓的就是实测里真漏出来的那类错：collective_flow v40 render_s1201
            自己冒出 overlap / spectators。
        R5  版式相关度（**只作读数 + 软警**，不是硬判据）：出图与参考图的墨迹整体相关 r。
            只在 style-only 时提示：r 高 = 疑似连构图一起抄了。
            （作者 2026-10-12 已明确「不需要任何反抄写判据」，所以这一条不做硬判；
             本闸门的硬判据只有 R0–R2 与 R4。）

用法
    # 出图前（ref_guard.py --run 会自动调）
    python scripts\\ref_role_gate.py --check --stage sketch --ref-role style-only \\
        --ref <风格图.png> --brief <brief.md> [--ir <IR>] [--labels "a,b,x,y,z"]

    # 出图后
    python scripts\\ref_role_gate.py --post --png <出图.png> [--ref <风格图.png>] \\
        --brief <brief.md> [--ref-role style-only] [--labels ...] [--json r.json] [--annot a.png]

标定（2026-10-13 实测；改过这里就要重跑）
    出图前
        PASS  --ref-role style-only + fig_upc_3d/sense/brief_B.md
        PASS  --ref-role style-only + fig_upc_3d/sense/brief_A.md（A 档：<=80 字，R1/R2 不判）
        PASS  （无 --ref）—— 本闸门不适用
        FAIL  有 --ref 但没给 --ref-role（R0）
        FAIL  style-only + 无标签白名单（R1） / 无面板序列（R1） / 无不要图例标题（R1）
        FAIL  style+content 但既不在 --content-ref、简报也没说照它画（R2）
    出图后（--post）
        FAIL  collective_flow/gen/v40/render_test/render_s1201.png  -> Overlaρ / speCtatos
        FAIL  collective_flow/gen/v40/render_test/render_s1202.png  -> Overap
              （in-plane 被误读成 npane / npi8ne —— 已按“近似白名单词”降为读数，不再误杀）
        PASS  fig_upc_3d/sense/C2/sketch_s33.png 、sense/C/chosen.png
        PASS  fig_upc_3d/sense_noref/C/sketch_s81..s83.png 、B/sketch_s71.png
        PASS  fig_upc_3d/sense_noref/A/sketch_s61.png （深底图：额外发 R4_NO_TEXT_FOUND“没判”警告）
    近似度阈值 0.58（difflib ratio）的标定：真泄漏全 <=0.40（overlap 0.36 / spectators 0.29），
    白名单词的误读全 >=0.62（npane vs inplane 0.83 / npi8ne 0.62）。
    实测说明：字形识别在**小字**（中位字高 15 px）上会把字母误读（speCtatos、Overlaρ）
    —— 所以 R4 的硬判据只管“整词均值 >=0.62 且不在白名单”；
    报告里把所有认出的词全列出，人 5 秒可复核。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import string
import sys
from difflib import SequenceMatcher

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROLE_STYLE = "style-only"
ROLE_BOTH = "style+content"
ROLES = (ROLE_STYLE, ROLE_BOTH)

WHITELIST_HEADS = ("只许出现", "标签白名单", "只许写", "只许标", "只标这些", "只写这些")
COPY_HINTS = ("照它", "照他的", "按参考图", "照参考图", "复刻参考图", "照它的",
              "模仿参考图的构图", "参考图的构图", "沿用参考图")
NEG_HINTS = ("不要照抄", "不是内容模板", "别照抄", "不要复制参考", "不要模仿参考",
             "不要照搬", "不要复制它", "不是内容参考")
BULLET = re.compile(r"^\s*(?:[\u00b7\u2022\u25cf\-*]|\d+\s*[).\u3001\uff0e])\s*\S")
GREEK = "\u0370-\u03ff"
SUPER = "\u2070-\u209f"   # 上/下标（⁺ ⁻ ² …）：不保留的话 e⁺ 与 e⁻ 会被 norm 成同一个 "e"

MIN_WORD_LEN = 4
CHAR_MIN = 0.62      # 整词均值下限
CHAR_FLOOR = 0.45    # 单字下限
N_TEMPLATE = 40


# ── 路径/文本小工具 ─────────────────────────────────────────────────────────
def norm(tok: str) -> str:
    return re.sub(r"[^0-9a-z" + GREEK + SUPER + r"]+", "", (tok or "").lower())


def read_text(p):
    if not p:
        return ""
    try:
        return io.open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def resolve(p, base=None):
    q = str(p).strip().strip('"')
    if os.path.isabs(q):
        return os.path.normpath(q)
    for b in [base, os.getcwd()]:
        if b:
            c = os.path.normpath(os.path.join(b, q))
            if os.path.exists(c):
                return c
    return os.path.normpath(os.path.join(base or os.getcwd(), q))


# ── 从简报里读「元素枚举」与「标签白名单」 ──────────────────────────────────
def count_elements(text: str) -> int:
    n_form = text.count("\u3010\u5f62\u6001")            # 【形态：scene3d】
    n_bul = sum(1 for ln in text.splitlines() if BULLET.match(ln))
    return max(n_form, n_bul)


PANEL_HINTS = ("面板 a", "面板 b", "面板 c", "面板 d", "从左到右", "单面板",
               "不分 a/b", "不分ab", "分区")
NODECOR_HINTS = ("不要标题", "不要图例", "不要说明文字", "不要边框",
                 "无标题", "无图例")


def has_panel_seq(text: str) -> bool:
    return any(h in text for h in PANEL_HINTS)


def has_no_decor(text: str) -> bool:
    return any(h in text for h in NODECOR_HINTS)


def parse_labels(text: str):
    """从简报里解析标签白名单（best-effort；--labels 才是权威）。"""
    toks = []
    for ln in text.splitlines():
        # ★ 必须从「白名单那几个字」**之后**找冒号：单行简报（v4.26 的 B/D 就是一行）
        #   前面通常已经有别的冒号（“3D 期刊示意图：…”），按全文第一个冒号切会切错段，
        #   于是把整句当标签、全部超长被丢 → 合规简报被误判成「没有白名单」。
        _hit = next((h for h in WHITELIST_HEADS if h in ln), None)
        if _hit:
            _tail = ln[ln.index(_hit) + len(_hit):]
            seg = re.split(r"[\uff1a:]", _tail, 1)
            body = seg[1] if len(seg) > 1 else _tail
            # 白名单句子到「。」/「；」为止 —— 否则同一行后面的「本图不要 QGP 火球」
            # 会把 QGP 也解析成「允许的标签」（norm() 会丢掉纯中文，唯独留下拉丁词）。
            body = re.split(r"[\uff1b;\u3002]", body)[0]
            body = body.replace("\u8fd9\u4e9b\u6807\u7b7e", "")
            for p in re.split(r"[\uff0c,\u3001\s]+", body):
                p = p.strip().strip("\u3002.\uff1b;\"'\u201c\u201d\u300c\u300d")
                if p and len(p) <= 40:
                    toks.append(p)
        if "\u9010\u5b57\u7167\u5199" in ln or "\u56fe\u4e2d**\u6587\u5b57**" in ln or "\u56fe\u4e2d\u6587\u5b57" in ln:
            for m in re.findall(r"[\u201c\"]([^\u201d\"]{3,})[\u201d\"]", ln):
                if m.count(",") >= 1 and "\u4e0d\u8981" not in m:
                    for p in re.split(r"[\uff0c,]+", m):
                        p = p.strip()
                        if p and len(p) <= 40:
                            toks.append(p)
    seen, out = set(), []
    for t in toks:
        k = norm(t)
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


# 字形过程里常把希腊字误认成拉丁字的双胞（实测：overlap 的末尾 p 被认成 ρ）
GREEK_FIX = str.maketrans({"ρ": "p", "ν": "v", "τ": "t", "α": "a", "ο": "o",
                           "ε": "e", "κ": "k", "χ": "x", "υ": "u", "ι": "i",
                           "γ": "y", "ζ": "z", "β": "b", "μ": "u", "σ": "o"})


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return 9
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[lb]


def label_allowed(word: str, labels):
    w = norm(word)
    if not w:
        return True
    for lb in labels:
        n = norm(lb)
        if not n:
            continue
        if w == n or (len(n) >= 2 and n in w) or (len(w) >= 2 and w in n):
            return True
        # 模糊兼容：一个字误读不能把白名单里的合法标签变成泄漏。
        if len(n) >= 4 and len(w) >= 4 and _lev(w, n) <= 1:
            return True
    return False


# ── 无 OCR 字形识别（自足实现，不 import axis_gate，免得连带它的 stdout 包装）──
def _font_files():
    cands = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/georgia.ttf",
             "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/verdana.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]
    return [p for p in cands if os.path.exists(p)]


def _templates(chars, N=N_TEMPLATE, max_fonts=4, sizes=(28, 34, 40)):
    from PIL import Image, ImageDraw, ImageFont
    templ = {}
    for fp in _font_files()[:max_fonts]:
        for size in sizes:
            try:
                f = ImageFont.truetype(fp, size)
            except Exception:
                continue
            for c in chars:
                img = Image.new("L", (size * 2, size * 2), 255)
                try:
                    ImageDraw.Draw(img).text((size // 2, size // 2), c, font=f, fill=0)
                except Exception:
                    continue
                a = np.asarray(img) < 128
                ys, xs = np.nonzero(a)
                if len(xs) == 0:
                    continue
                a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                h, w = a.shape
                im2 = Image.fromarray((~a * 255).astype(np.uint8))
                s = N / float(max(h, w))
                im2 = im2.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))),
                                 Image.LANCZOS)
                cat = np.asarray(im2) < 128
                out = np.zeros((N, N), bool)
                oh, ow = cat.shape
                out[(N - oh) // 2:(N - oh) // 2 + oh, (N - ow) // 2:(N - ow) // 2 + ow] = cat
                templ.setdefault(c, []).append(out)
    return templ


def _norm_patch(patch):
    from PIL import Image
    h, w = patch.shape
    im2 = Image.fromarray((~patch * 255).astype(np.uint8))
    s = N_TEMPLATE / float(max(h, w))
    im2 = im2.resize((max(1, int(round(w * s))), max(1, int(round(h * s)))), Image.LANCZOS)
    cat = np.asarray(im2) < 128
    out = np.zeros((N_TEMPLATE, N_TEMPLATE), bool)
    oh, ow = cat.shape
    out[(N_TEMPLATE - oh) // 2:(N_TEMPLATE - oh) // 2 + oh,
        (N_TEMPLATE - ow) // 2:(N_TEMPLATE - ow) // 2 + ow] = cat
    return out


def _glyph(patch, templ):
    """返回 (char, score, margin, top3)。按**大小写无关**分组比 margin ——
    l/I、v/V、o/O 这类只有大小写差别的字形不该互相否决。
    总是取最高分的字符（不返 None）—— “认不出”用整词均值来判，
    否则一个 '?' 就把整个真正的泄漏词抹掉了。"""
    out = _norm_patch(patch)
    by = {}
    for c, ts in templ.items():
        sc = max(float((out & t).sum()) / max(1.0, float((out | t).sum())) for t in ts)
        k = c.lower()
        if sc > by.get(k, (0.0, c))[0]:
            by[k] = (sc, c)
    ranked = sorted(by.values(), reverse=True)
    s1, c1 = ranked[0]
    s2 = ranked[1][0] if len(ranked) > 1 else 0.0
    return c1, s1, s1 - s2, [(round(s, 3), c) for s, c in ranked[:3]]


def read_words(path, charset=None, lum_thr=130, min_h=8, max_frac_h=0.14,
               max_frac_w=0.07, min_area=25, ring_min=170):
    """连通域 -> 行/词聚类 -> 逐字模板匹配。返回 (words, debug)。"""
    from PIL import Image
    from scipy import ndimage
    charset = charset or (list(string.ascii_letters) + list(string.digits)
                          + list("\u03b3\u03b8\u03c6\u03c8\u03c3\u03c1\u03c4+-"))
    templ = _templates(charset)
    im = Image.open(path).convert("RGB")
    A = np.asarray(im, np.int16)
    lum = 0.299 * A[..., 0] + 0.587 * A[..., 1] + 0.114 * A[..., 2]
    mask = lum < lum_thr
    H, W = mask.shape
    lab, n = ndimage.label(mask)
    objs = ndimage.find_objects(lab)
    comps = []
    for i, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        h, w = y1 - y0, x1 - x0
        if not (min_h <= h <= max_frac_h * H):
            continue
        if not (2 <= w <= max_frac_w * W):
            continue
        if not (0.12 <= w / float(h) <= 3.0):
            continue
        if ndimage.sum(mask[sl], lab[sl], i) < min_area:
            continue
        # 字形必须坐在**浅色背景**上：环带中位亮度要高（把深底海报 / 核表面的碎面滤掉）
        pad_x, pad_y = max(3, w // 2), max(3, h // 2)
        ry0, ry1 = max(0, y0 - pad_y), min(H, y1 + pad_y)
        rx0, rx1 = max(0, x0 - pad_x), min(W, x1 + pad_x)
        ring = lum[ry0:ry1, rx0:rx1].copy()
        ring[y0 - ry0:y1 - ry0, x0 - rx0:x1 - rx0] = 255
        if ring.size == 0 or float(np.median(ring)) < ring_min:
            continue
        comps.append([x0, y0, x1, y1])
    if not comps:
        return [], {"ncomp": 0}
    med_h = float(np.median([c[3] - c[1] for c in comps]))
    lines = []
    for c in sorted(comps, key=lambda c: (c[1], c[0])):
        for L in lines:
            ov = min(L["y1"], c[3]) - max(L["y0"], c[1])
            if ov > 0.5 * min(L["y1"] - L["y0"], c[3] - c[1]):
                L["c"].append(c)
                L["y0"] = min(L["y0"], c[1])
                L["y1"] = max(L["y1"], c[3])
                break
        else:
            lines.append({"y0": c[1], "y1": c[3], "c": [c]})
    words = []
    for L in lines:
        cs = sorted(L["c"], key=lambda c: c[0])
        cur, grp = list(cs[0]), [cs[0]]
        for c in cs[1:]:
            if c[0] - cur[2] <= max(12.0, 0.75 * med_h):
                cur[2] = max(cur[2], c[2])
                cur[3] = max(cur[3], c[3])
                cur[1] = min(cur[1], c[1])
                grp.append(c)
            else:
                words.append((list(cur), grp))
                cur, grp = list(c), [c]
        words.append((list(cur), grp))
    out = []
    for (x0, y0, x1, y1), grp in words:
        chars, scores, boxes, tops = [], [], [], []
        for gx0, gy0, gx1, gy1 in grp:
            c, s, mg, top = _glyph(mask[gy0:gy1, gx0:gx1], templ)
            chars.append(c)
            scores.append(round(s, 3))
            tops.append(top)
            boxes.append([gx0, gy0, gx1, gy1])
        out.append({"word": "".join(chars), "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "n": len(grp), "scores": scores, "tops": tops,
                    "mean": round(float(np.mean(scores)), 3),
                    "min": round(float(np.min(scores)), 3), "boxes": boxes})
    return out, {"ncomp": len(comps), "med_h": med_h, "nwords": len(out)}


# ── 版式相关度（只作读数 / 软警） ───────────────────────────────────────────
def ink_corr(out_png, ref_png, size=(320, 176)):
    from PIL import Image
    def ink(p):
        im = Image.open(p).convert("L").resize(size, Image.BILINEAR)
        a = np.asarray(im, np.float32)
        return 255.0 - a
    a, b = ink(out_png), ink(ref_png)
    a = a - a.mean()
    b = b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if d == 0:
        return 0.0
    return float((a * b).sum() / d)


# ── 出图前 ─────────────────────────────────────────────────────────────────
def check_pre(stage, role, refs, content, brief_path, text=None, labels=None, base=None):
    v, w = [], []
    text = text if text is not None else read_text(brief_path)
    if not refs:
        w.append(("--ref", "(无)", "NA", "\u672c\u6b21\u6ca1\u6709\u98ce\u683c\u53c2\u8003\u56fe \u2014\u2014 "
                                     "\u672c\u95f8\u95e8\u4e0d\u9002\u7528\uff08\u540c\u65f6 A \u6863\u4e5f\u4e0d\u9002\u7528\uff09"))
        return v, w
    # R0 角色必须被声明
    if role not in ROLES:
        v.append(("--ref-role", role or "(未给)", "R0_NO_ROLE",
                  "\u53c2\u8003\u56fe\u7684\u89d2\u8272\u6ca1\u88ab\u58f0\u660e\uff1a\u5fc5\u987b\u7ed9 "
                  "--ref-role style-only | style+content \u2014\u2014 "
                  "\u201c\u7167\u6284\u5230\u5e95\u5141\u4e0d\u5141\u8bb8\u201d\u5fc5\u987b\u6709\u4eba\u7b7e\u5b57\uff0c"
                  "\u4e0d\u80fd\u9760\u63d0\u793a\u8bcd\u91cc\u4e00\u53e5\u201c\u4e0d\u8981\u7167\u6284\u201d\u81ea\u5df1\u51b3\u5b9a"))
        return v, w
    n_el = count_elements(text)
    labels = list(labels or []) or parse_labels(text)
    a_tier = (stage == "sketch" and len(text.strip()) <= 80)
    if a_tier:
        w.append(("--brief", brief_path or "", "A_TIER",
                  "A 档（<=80 字符）：照抄参考图是 skill 认定的**正常形态**"
                  "（作者 2026-10-12：「A 档复刻参考图就复刻参考图呗」）"
                  "—— 本档只作诊断、不许进交付链（ladder L2），R1/R2 在这一档不判。"))
    elif role == ROLE_STYLE:
        # R1：style-only 必须付“超配”的代价。
        #   硬判据 = 实测支持的**输出硬约束**（标签白名单 + 面板序列 + 不要标题图例）
        #   —— SKILL.md:613-623：相似度 0.36 -> 0.043 只差这 106 字符。
        #   元素枚举只作**软警**（它的阈值没有实测支撑，硬判会误杀）。
        if len(labels) < 3:
            v.append(("--brief", brief_path or "(未给)", "R1_NO_WHITELIST",
                      "style-only 下简报里没有标签白名单（解出 %d 个，要求 >=3）"
                      "—— “图上只许出现这些标签：…” 是把拄线画清楚的那一句"
                      "（实测：加白名单前后从“照抄 + 标签乱”变“干净”）" % len(labels)))
        else:
            w.append(("--brief", brief_path or "", "OK",
                      "标签白名单 %d 个：%s" % (len(labels), ", ".join(labels[:12]))))
        if not has_panel_seq(text):
            v.append(("--brief", brief_path or "(未给)", "R1_NO_PANEL_SEQ",
                      "style-only 下简报没有**面板序列**（“面板 a/b/c”、"
                      "“从左到右”、“单面板 / 不分 a,b 分区”这类）"
                      "—— 输出硬约束的另一半，缺了就是把构图交给参考图了"))
        if not has_no_decor(text):
            v.append(("--brief", brief_path or "(未给)", "R1_NO_OUTPUT_CONSTRAINT",
                      "style-only 下简报没写“不要标题 / 图例 / 说明文字 / 边框”"
                      "—— 就是这句把自带的海报标题与图例项赶掉的"))
        if n_el < 4:
            w.append(("--brief", brief_path or "", "R1_THIN_ENUM",
                      "简报只点名了 %d 个元素（建议 >=4）—— 简报越欠定，"
                      "模型就越拿参考图去填（软警：只作读数，不硬判）" % n_el))
        else:
            w.append(("--brief", brief_path or "", "OK", "元素枚举 %d 个" % n_el))
    else:
        # R2 style+content：这张图同时是「内容」——必须说出来
        ok_ct = any(os.path.normcase(resolve(p, base)) in
                    {os.path.normcase(resolve(q, base)) for q in (content or [])} for p in refs)
        ok_br = any(h in text for h in COPY_HINTS)
        if not (ok_ct or ok_br):
            v.append(("--brief", brief_path or "(未给)", "R2_NOT_DECLARED_AS_CONTENT",
                      "style+content 但既不在 --content-ref 里、简报也没写"
                      "“照它的物体与布局画”—— 既然它同时是内容，"
                      "就得把这件事说出来（建议：A 档照抄 -> 客户选一张 -> "
                      "那张就是已过闸口的草图 -> render 用 --content-ref 送它）"))
        if ok_ct:
            w.append(("--ref", ", ".join(refs), "OK", "它也在 --content-ref 里（合法）"))
        if ok_br:
            w.append(("--brief", brief_path or "", "OK", "简报里已声明“照它画”"))
        if stage == "render":
            w.append(("--ref-role", role, "NOTE",
                      "render 档还需客户回执（ref_guard 的 choice_gate 会查）"))
    # R3 负面对照 -> 软警
    neg = [h for h in NEG_HINTS if h in text]
    if neg:
        w.append(("--brief", brief_path or "", "R3_NEGATIVE_WORDING",
                  "\u7b80\u62a5\u91cc\u5199\u4e86\u8d1f\u9762\u5bf9\u7167\u201c%s\u201d\u2014\u2014 "
                  "\u5b9e\u6d4b\u8d1f\u9762\u53e5\u4f1a\u53cd\u566c\uff08\u5199\u201c\u4e0d\u662f\u82b1\u751f\u201d\u90a3\u4e09\u5f20"
                  "\u771f\u753b\u6210\u82b1\u751f\uff09\uff1b\u5efa\u8bae\u6539\u6210**\u6b63\u9762\u63cf\u8ff0**"
                  "\u8981\u753b\u6210\u4ec0\u4e48" % "\u3001".join(neg)))
    return v, w


# ── 出图后 ─────────────────────────────────────────────────────────────────
def check_post(png, refs=None, brief_path=None, role=None, labels=None, annot=None, base=None):
    v, w, rd = [], [], {}
    if not png or not os.path.exists(resolve(png, base)):
        return [("--png", png or "(未给)", "R4_NO_PNG", "\u6ca1\u7ed9\u53ef\u8bfb\u7684\u51fa\u56fe\u4f4d\u56fe")], [], {}
    text = read_text(brief_path)
    labels = list(labels or []) or parse_labels(text)
    words, dbg = read_words(resolve(png, base))
    rd["ncomp"] = dbg.get("ncomp", 0)
    rd["med_h"] = round(dbg.get("med_h", 0) or 0, 1)
    rd["labels"] = labels
    rd["words"] = [{"t": x["word"], "score": x["mean"], "n": x["n"], "n_ok": x["n"],
                    "x": int((x["x0"] + x["x1"]) / 2), "y": int((x["y0"] + x["y1"]) / 2),
                    "box": [int(x["x0"]), int(x["y0"]), int(x["x1"]), int(x["y1"])]}
                   for x in words]
    leaks, reading = [], []
    if not labels:
        w.append(("--brief", brief_path or "", "R4_NO_WHITELIST",
                  "简报里没解析到标签白名单、也没给 --labels —— "
                  "R4 无法判，跳过（建议：给 --labels，或在简报里写"
                  "「图上只许出现这些标签：…」）"))
    n_judged = 0
    for x in words:
        wd = x["word"]
        core = re.sub(r"[^0-9A-Za-z" + GREEK + r"]", "", wd).translate(GREEK_FIX)
        if (not labels or len(core) < MIN_WORD_LEN or x["min"] < CHAR_FLOOR
                or x["mean"] < CHAR_MIN or not core.isascii()):
            reading.append("%s(%.2f)" % (wd, x["mean"]))
            continue
        n_judged += 1
        if label_allowed(core, labels):
            continue
        # 近似白名单词：大概率是把合法标签**误读**了，降为读数。
        # 阈值 0.58 是标定出来的：真泄漏全 <=0.40（overlap 0.36 / spectators 0.29），
        # 白名单词的误读全 >=0.62（npane vs inplane 0.83 / npi8ne 0.62）。
        near = [lb for lb in labels
                if len(norm(lb)) >= 4 and len(core) >= 4
                and (SequenceMatcher(None, core, norm(lb)).ratio() >= 0.58
                     or _lev(core, norm(lb)) <= 2)]
        if near:
            reading.append("%s(%.2f~%s)" % (wd, x["mean"], near[0]))
            continue
        leaks.append(x)
    for x in leaks:
        v.append(("--png", png, "R4_LABEL_LEAK",
                  "\u56fe\u4e0a\u6709\u7b80\u62a5\u6ca1\u5141\u8bb8\u7684\u6807\u7b7e\u201c%s\u201d"
                  "\uff08\u6574\u8bcd\u5747\u503c %.2f\uff0c\u4f4d\u7f6e %d,%d\uff09\u2014\u2014 "
                  "\u5c31\u662f\u201c\u81ea\u5df1\u52a0\u8bcd\u201d\u90a3\u7c7b\u7167\u6284\u75d5\u8ff9"
                  "（\u5b9e\u6d4b\uff1a\u4e0a\u4e00\u8f6e\u81ea\u5df1\u5199\u4e86 overlap / spectators\uff09"
                  % (x["word"], x["mean"], int((x["x0"] + x["x1"]) / 2), int((x["y0"] + x["y1"]) / 2))))
    rd["n_judged"] = n_judged
    if n_judged == 0:
        w.append(("--png", png, "R4_NO_TEXT_FOUND",
                  "\u4e00\u4e2a\u53ef\u5224\u7684\u6574\u8bcd\u4e5f\u6ca1\u8ba4\u51fa\u6765\uff08\u6df1\u5e95\u56fe / \u5b57\u592a\u5c0f / "
                  "\u90fd\u662f\u5355\u5b57\u7b26\uff09\u2014\u2014 \u672c\u95f8\u95e8\u8fd9\u5f20**\u6ca1\u5224**\uff0c\u8bf7\u4eba\u773c\u590d\u6838"))
    rd["leaks"] = [x["word"] for x in leaks]
    rd["reading"] = reading
    # R5 版式相关度（读数 + 软警，仅 style-only）
    if refs:
        try:
            r = ink_corr(resolve(png, base), resolve(refs[0], base))
            rd["ink_r"] = round(r, 3)
            if role == ROLE_STYLE and r > 0.45:
                w.append(("--png", png, "R5_LAYOUT_CORR",
                          "\u4e0e\u53c2\u8003\u56fe\u7684\u58a8\u8ff9\u76f8\u5173 r=%.3f > 0.45 \u2014\u2014 "
                          "\u7591\u4f3c\u8fde\u6784\u56fe\u4e00\u8d77\u6284\u4e86\uff08\u4ec5\u8bfb\u6570/\u8f6f\u8b66\uff0c"
                          "\u4e0d\u662f\u786c\u5224\u636e\uff09" % r))
        except Exception as e:
            w.append(("--png", png, "R5_SKIP", "\u7248\u5f0f\u76f8\u5173\u5ea6\u7b97\u4e0d\u4e86\uff1a%r" % (e,)))
    if annot:
        try:
            draw_annot(resolve(png, base), resolve(annot, base), leaks, words)
            w.append(("--annot", annot, "OK", "\u6807\u6ce8\u56fe\u5df2\u51fa"))
        except Exception as e:
            w.append(("--annot", annot, "SKIP", "ann ot \u5931\u8d25\uff1a%r" % (e,)))
    return v, w, rd


def draw_annot(png, outp, leaks, words):
    from PIL import Image, ImageDraw
    im = Image.open(png).convert("RGB")
    d = ImageDraw.Draw(im)
    for x in words:
        col = (220, 30, 30) if x in leaks else (60, 130, 220)
        d.rectangle([x["x0"] - 4, x["y0"] - 4, x["x1"] + 4, x["y1"] + 4], outline=col, width=4)
    im.save(outp)


def render_report(title, roles, v, w, rd):
    out = ["=" * 74, title, "=" * 74]
    for k, val in roles:
        out.append("  %-16s %s" % (k, val))
    if rd:
        out.append("  \u8bfb\u6570            \u8fde\u901a\u57df %s / \u4e2d\u4f4d\u5b57\u9ad8 %s / \u8ba4\u51fa %d \u8bcd"
                   % (rd.get("ncomp"), rd.get("med_h"), len(rd.get("words", []))))
        if rd.get("labels"):
            out.append("  \u767d\u540d\u5355          %s" % ", ".join(rd["labels"][:16]))
        if "ink_r" in rd:
            out.append("  版式相关 r      %s" % rd["ink_r"])
        if rd.get("words"):
            out.append("  \u8ba4\u51fa\u7684\u8bcd      %s" % ", ".join(
                "%s(%.2f)" % (x["t"], x["score"]) for x in rd["words"][:26]))
    out.append("")
    for role_, p_, k_, y_ in w:
        out.append("  [%s] %-22s %s" % ("warn", k_, y_))
    if w:
        out.append("")
    for role_, p_, k_, y_ in v:
        out.append("  [FAIL] %-22s %s" % (k_, y_))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(add_help=True,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="\u53c2\u8003\u56fe\u89d2\u8272\u58f0\u660e + \u6807\u7b7e\u6cc4\u6f0f\u95f8\u95e8\uff08\u89c1\u6587\u4ef6\u5934\uff09")
    ap.add_argument("--check", action="store_true", help="\u51fa\u56fe\u524d\uff1a\u89d2\u8272\u58f0\u660e + \u524d\u63d0\u6761\u4ef6")
    ap.add_argument("--post", action="store_true", help="\u51fa\u56fe\u540e\uff1a\u6807\u7b7e\u6cc4\u6f0f + \u7248\u5f0f\u8bfb\u6570")
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch")
    ap.add_argument("--ref-role", default=None, help="style-only | style+content")
    ap.add_argument("--ref", action="append", default=[], help="\u98ce\u683c\u53c2\u8003\u56fe")
    ap.add_argument("--content-ref", action="append", default=[], help="\u6784\u56fe\u4f9d\u636e")
    ap.add_argument("--brief", default=None, help="\u7b80\u62a5\uff1a\u7528\u6765\u8bfb\u5143\u7d20\u679a\u4e3e / \u4e0d\u524d\u540d\u5355 / \u8d1f\u9762\u53e5")
    ap.add_argument("--ir", default=None, help="IR\uff08\u9884\u7559\uff09")
    ap.add_argument("--labels", default=None, help="\u6807\u7b7e\u767d\u540d\u5355\uff08\u9017\u53f7\u5206\u9694\uff09\uff1a\u6743\u5a01\uff0c\u76d6\u8fc7\u4ece\u7b80\u62a5\u81ea\u52a8\u89e3\u6790")
    ap.add_argument("--png", default=None, help="\u51fa\u56fe\u4f4d\u56fe\uff08--post\uff09")
    ap.add_argument("--annot", default=None, help="\u6807\u6ce8\u56fe\u8f93\u51fa\u8def\u5f84")
    ap.add_argument("--base", default=None, help="\u76f8\u5bf9\u8def\u5f84\u89e3\u6790\u57fa\u51c6")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    base = a.base or os.getcwd()
    labels = [t for t in re.split(r"[,\uff0c]", a.labels or "") if t.strip()] if a.labels else None

    if a.post:
        v, w, rd = check_post(a.png, a.ref, a.brief, a.ref_role, labels, a.annot, base)
        print(render_report("ref_role_gate -- \u51fa\u56fe\u540e\uff1a\u6807\u7b7e\u6cc4\u6f0f + \u7248\u5f0f\u8bfb\u6570", 
                            [("stage", a.stage), ("ref-role", a.ref_role or "(\u672a\u58f0\u660e)"),
                             ("png", a.png or "(\u672a\u7ed9)")], v, w, rd))
        if a.json:
            Path_w = io.open(a.json, "w", encoding="utf-8")
            Path_w.write(json.dumps({"mode": "post", "png": a.png, "ref_role": a.ref_role,
                                     "violations": [{"kind": k, "why": y} for _, _, k, y in v],
                                     "warnings": [{"kind": k, "why": y} for _, _, k, y in w],
                                     "readings": rd, "ok": not v}, ensure_ascii=False, indent=2))
            Path_w.close()
        if v:
            print("\n\u7ed3\u8bba\uff1a\u53c2\u8003\u56fe\u89d2\u8272\u95f8\u95e8\u672a\u8fc7 \u2014\u2014 \u51fa\u56fe\u4e0d\u5408\u683c\u3002")
            return 1
        print("\n\u7ed3\u8bba\uff1a\u53c2\u8003\u56fe\u89d2\u8272\u95f8\u95e8\u901a\u8fc7\u3002")
        return 0

    v, w = check_pre(a.stage, a.ref_role, a.ref, a.content_ref, a.brief, labels=labels, base=base)
    print(render_report("ref_role_gate -- \u51fa\u56fe\u524d\uff1a\u53c2\u8003\u56fe\u89d2\u8272\u58f0\u660e",
                        [("stage", a.stage), ("ref-role", a.ref_role or "(\u672a\u58f0\u660e)"),
                         ("--ref", ", ".join(a.ref) or "(\u65e0)"),
                         ("brief", a.brief or "(\u672a\u7ed9)")], v, w, {}))
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(
            {"mode": "check", "stage": a.stage, "ref_role": a.ref_role, "refs": a.ref,
             "violations": [{"kind": k, "why": y} for _, _, k, y in v],
             "warnings": [{"kind": k, "why": y} for _, _, k, y in w],
             "ok": not v}, ensure_ascii=False, indent=2))
    if v:
        print("\n\u7ed3\u8bba\uff1a\u89d2\u8272\u6ca1\u58f0\u660e\u6e05\u695a / \u4ee3\u4ef7\u6ca1\u4ed8 \u2014\u2014 \u4e0d\u8bb8\u8c03 API\u3002")
        return 1
    print("\n\u7ed3\u8bba\uff1a\u53c2\u8003\u56fe\u89d2\u8272\u95f8\u95e8\u901a\u8fc7\u3002")
    return 0


if __name__ == "__main__":
    sys.exit(main())
