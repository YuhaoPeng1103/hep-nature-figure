#!/usr/bin/env python3
"""
repair_brief —— 把门禁报告翻译成【给模型的返修单】
=========================================================================
## 为什么需要它

这个 skill 的分工已经变了：

    画    → 模型（它有视觉先验，能画出代码难做的质感）
    约束  → 本 skill 的 IR（防止"好看但物理错"）
    验收  → 本 skill 的门禁（模型看不见自己的输出，这里能量）
    返修  → ★ 这一环原来是缺的

原来的门禁是**给人看的报告**："文字重叠: nucleus × scattering"。
人看得懂，但模型拿到这句话只能猜往哪挪。结果就是反复来回。

本脚本把门禁输出转成**可执行的返修单**：哪一处、在哪（PDF 点 + 归一化坐标）、
违反了什么、建议改多少。

## 用法

    # 直接给一张图（svg / pdf / png 都行）
    python3 repair_brief.py fig.svg
    python3 repair_brief.py fig.svg --profile assets/style-profiles.json --class "T3-schematic (illustration)"
    python3 repair_brief.py fig.svg --ir ir/xxx.ir.yaml --json

    # 输出是给模型看的纯文本；--json 出结构化版本
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fitz  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

# 复用的门禁
from audit_composition import (boxes, check_line_through_text,  # noqa: E402
                               check_out_of_bounds, check_text_text,
                               check_balance, MM)

MIN_GAP_PT = 4.0        # 文字之间至少留这么多（含行间与块间）
EDGE_MARGIN = 2.0       # 元素离页面边缘至少留这么多


# ══════════════════════════════════════════════════════════════
def to_pdf(fig: Path) -> tuple[Path, bool]:
    """svg → 临时 PDF（cairosvg）。返回 (pdf 路径, 是否为临时文件)。"""
    if fig.suffix.lower() == ".pdf":
        return fig, False
    if fig.suffix.lower() == ".svg":
        try:
            import cairosvg
        except ImportError:
            raise SystemExit("需要 cairosvg 才能从 SVG 转 PDF 做几何审计："
                             "pip install cairosvg")
        tmp = Path(tempfile.gettempdir()) / (fig.stem + "_brief.pdf")
        cairosvg.svg2pdf(url=str(fig), write_to=str(tmp))
        return tmp, True
    raise SystemExit(f"不支持的格式 {fig.suffix}：几何审计需要 svg 或 pdf")


def norm(rect, page_rect):
    """PDF 点 → 归一化 [0,1] 坐标，方便模型直接换算成画布比例。"""
    return (round((rect.x0 - page_rect.x0) / page_rect.width, 3),
            round((rect.y0 - page_rect.y0) / page_rect.height, 3),
            round((rect.x1 - page_rect.x0) / page_rect.width, 3),
            round((rect.y1 - page_rect.y0) / page_rect.height, 3))


def gap_between(a, b):
    """两个 bbox 的间隙（pt）。重叠返回负值；否则返回最近边距（同轴取最大）。"""
    r = a & b
    if not r.is_empty and r.get_area() > 0:
        return -r.get_area() ** 0.5
    dx = max(a.x0 - b.x1, b.x0 - a.x1)
    dy = max(a.y0 - b.y1, b.y0 - a.y1)
    return max(dx, dy)


# ══════════════════════════════════════════════════════════════
def analyze(fig: Path, profile=None, want_class=None, ir=None):
    pdf, is_tmp = to_pdf(fig)
    doc = fitz.open(pdf)
    page = doc[0]
    pr = page.rect
    texts, draws = boxes(page)
    page_area = pr.get_area()

    hard, soft = [], []      # hard = 必须修（阻断）；soft = 建议改

    # ── ① 文字互相重叠 ──
    for x, y, pct in check_text_text(texts, page_area):
        tb = next((t for t in texts if t["text"] == x), None)
        nb = next((t for t in texts if t["text"] == y), None)
        hard.append({
            "kind": "文字重叠", "who": f"{x} × {y}", "how_bad": f"重叠 {pct}%",
            "where": norm(tb["bbox"], pr) if tb else None,
            "fix": f"把「{x}」或「{y}」平移开，两者 bbox 不要相交；"
                   f"建议沿纵向错开至少 {(tb['size'] if tb else 12) * 1.4:.0f}pt",
        })

    # ── ② 图形压字（对比度判据）──
    for txt, contrast in check_line_through_text(page, texts):
        tb = next((t for t in texts if t["text"] == txt), None)
        hard.append({
            "kind": "文字被压", "who": txt,
            "how_bad": f"对比度只有 {contrast}（需 ≥0.35）",
            "where": norm(tb["bbox"], pr) if tb else None,
            "fix": f"「{txt}」压在了图形上。给它的 bbox 加一层白底描边"
                   f"（stroke white 3pt, paint-order=stroke）"
                   f"，或把它移到没有图形的区域",
        })

    # ── ③ 出界 / 贴边 ──
    for kind, dsc in check_out_of_bounds(texts, draws, pr, margin_pt=EDGE_MARGIN):
        if kind == "文字":
            tb = next((t for t in texts if t["text"] == dsc), None)
            hard.append({
                "kind": "出界", "who": dsc,
                "how_bad": "超出画布，会被裁掉",
                "where": norm(tb["bbox"], pr) if tb else None,
                "fix": f"把「{dsc}」整体移进画布内，四周留 ≥{EDGE_MARGIN}pt 余量；"
                       f"或缩小字号",
            })
        else:
            hard.append({
                "kind": "图形出界", "who": dsc,
                "how_bad": "超出画布边界，会被裁掉",
                "where": None,
                "fix": "把这个图形缩小或内移，使 bbox 落在画布内",
            })

    # ── ④ 文字间隙过小（门禁的盲区，这里补上）──
    #  ★ 实测：审计只管"重叠"，不管"快贴上"。收敛结果里
    #    「quenched jet」↔「Surface bias:」只隔 0.9pt，读起来就是贴住的。
    #    但同一张图里大部分 <6pt 的间隙是**行内正常词距**，所以判据要区分：
    #    只有**不同行**且间隙 < MIN_GAP_PT 才算问题。
    def same_line(a, b):
        """两个文字块的纵向重叠超过较矮者的 60% → 判为同一行。"""
        ov = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
        h = min(a.height, b.height)
        return h > 0 and ov / h > 0.6

    seen = set()
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            a, b = texts[i]["bbox"], texts[j]["bbox"]
            if same_line(a, b):
                continue                      # 行内词距，正常
            g = gap_between(a, b)
            if 0 <= g < MIN_GAP_PT:
                key = (texts[i]["text"], texts[j]["text"])
                if key in seen:
                    continue
                seen.add(key)
                soft.append({
                    "kind": "行间过近",
                    "who": f"{texts[i]['text']} ↔ {texts[j]['text']}",
                    "how_bad": f"间隙只有 {g:.1f}pt（建议 ≥{MIN_GAP_PT}pt）",
                    "where": norm(a, pr),
                    "fix": f"两行贴得太近，视觉上会读成一块。"
                           f"把下面那行下移 ≥{MIN_GAP_PT - g:.1f}pt",
                })

    # ── ⑤ 留白分布 ──
    frac, empty = check_balance(draws, texts, pr)
    if empty and frac >= 0.33:
        where = ", ".join(f"第{j+1}列第{i+1}行" for j, i in empty)
        soft.append({
            "kind": "留白失衡", "who": f"{len(empty)}/9 格全空",
            "how_bad": f"空块位置：{where}",
            "where": None,
            "fix": "内容挤在一侧。把整体元素重新分布，或加大留白小的一侧的"
                   "元素尺寸；也可整体缩小后居中",
        })

    # ── ⑥ 风格偏离（有档案/IR 时）──
    style_note = None
    if profile:
        style_note = style_deviation(fig, profile, want_class)

    doc.close()
    if is_tmp:
        try:
            pdf.unlink()
        except OSError:
            pass
    return hard, soft, style_note


def style_deviation(fig: Path, profile_path, want_class=None):
    """量风格偏离。用 style_bench 的度量 + 档案的区间判据。"""
    import json as _json
    from style_bench import measure, METRIC_ROBUST

    pdata = _json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if want_class:
        pdata = pdata.get(want_class, {})
    elif "style" not in pdata:
        pdata = pdata[list(pdata)[0]]
    st = pdata.get("style", pdata)

    if fig.suffix.lower() != ".png":
        # 量风格需要位图
        if fig.suffix.lower() == ".svg":
            import cairosvg
            tmp = Path(tempfile.gettempdir()) / (fig.stem + "_brief.png")
            cairosvg.svg2png(url=str(fig), write_to=str(tmp), output_width=1400)
            target = tmp
        else:
            return None
    else:
        target = fig

    m = measure(str(target))
    out = []
    for k in ("whitespace", "saturation", "edge_density", "dark_ratio"):
        ent = st.get(k)
        if not isinstance(ent, dict) or not METRIC_ROBUST.get(k, True):
            continue
        lo, hi, med = ent.get("p25"), ent.get("p75"), ent.get("median")
        v = m.get(k)
        if None in (lo, hi, v):
            continue
        if v > hi:
            over = (v - hi) / max(hi, 1e-9)
            direction = "偏高"
        elif v < lo:
            over = (lo - v) / max(lo, 1e-9)
            direction = "偏低"
        else:
            continue
        # 类内离散度：飘的指标只作提醒（与 delivery_gate 同一原则）
        rel_iqr = (hi - lo) / med if med else 9
        out.append({
            "metric": k, "value": round(v, 4),
            "range": [round(lo, 4), round(hi, 4)],
            "dev": round(over, 3), "dir": direction,
            "class_iqr": round(rel_iqr, 2),
            "blocking": rel_iqr < 0.15,     # 只有类内一致的指标才够格阻断
        })
    return out


def fmt(fig, hard, soft, style_note, as_json=False):
    if as_json:
        return json.dumps({"figure": str(fig), "must_fix": hard,
                           "should_fix": soft, "style": style_note},
                          ensure_ascii=False, indent=2)
    L = [f"【返修单】{Path(fig).name}", ""]
    if not hard and not soft:
        L.append("✅ 门禁全过，无需返修。")
    if hard:
        L.append(f"■ 必须修（{len(hard)} 处，不修不予交付）")
        for i, x in enumerate(hard, 1):
            L.append(f"{i}. 【{x['kind']}】{x['who']} —— {x['how_bad']}")
            if x.get("where"):
                w = x["where"]
                L.append(f"   位置（归一化 x0,y0,x1,y1）= {w}")
            L.append(f"   改法：{x['fix']}")
        L.append("")
    if soft:
        L.append(f"■ 建议改（{len(soft)} 处，不阻断但影响观感）")
        for i, x in enumerate(soft, 1):
            L.append(f"{i}. 【{x['kind']}】{x['who']} —— {x['how_bad']}")
            L.append(f"   改法：{x['fix']}")
        L.append("")
    if style_note:
        blocking = [s for s in style_note if s["blocking"]]
        advisory = [s for s in style_note if not s["blocking"]]
        if blocking:
            L.append(f"■ 风格偏离（阻断级，{len(blocking)} 项）")
            for s in blocking:
                L.append(f"   {s['metric']}: 当前 {s['value']}，"
                         f"目标区间 {s['range']}，{s['dir']} {s['dev']*100:.0f}%")
            L.append("")
        if advisory:
            L.append(f"■ 风格参考（类内分散，仅提醒，{len(advisory)} 项）")
            L.append("   ⚠️ 这些指标在类内本身就飘（IQR 见下），"
                     "偏离大不代表图差，别为了它们牺牲别的")
            for s in advisory:
                L.append(f"   {s['metric']}: 当前 {s['value']} vs "
                         f"区间 {s['range']}（{s['dir']} {s['dev']*100:.0f}%，"
                         f"类内 IQR {s['class_iqr']}）")
            L.append("")
    L.append("改完把文件发回来，重跑本脚本验收。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="把门禁报告翻译成给模型的返修单")
    ap.add_argument("figure", help="svg / pdf / png")
    ap.add_argument("--profile", help="风格档案（可选）")
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--ir", help="IR（可选，用于结构断言）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    fig = Path(a.figure)
    if not fig.exists():
        raise SystemExit(f"找不到 {fig}")

    hard, soft, style_note = analyze(fig, a.profile, a.want_class, a.ir)
    print(fmt(fig, hard, soft, style_note, a.json))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
