#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brief_lite.py —— 极简档简报编译器（v4.2）

作者 2026-10-05 的原话：
  「你给的提示词别那么复杂，从简单到复杂，比如最开始就给他一个草图和风格图，
    一句话说明一下需求，物理不对的地方第二次添加一些物理约束生成」

所以出图不再一上来就灌几 k 字符的规格书，改成逐轮递增：

  第 0 轮  --tier 0   一句话 + 画布/面板序列 + 输出硬约束        （约 400-600 字符）
  第 1 轮  --tier 1   上面那些 + 五条 3D 空间线索 + 每面板一句形态（约 1.5k 字符）
  第 N 轮  --tier 1 --add gen/roundN_fail.md
                      只把上一轮**真的画错**的物理点追加进去（错了才加，对了不加）

用法：
  python scripts/brief_lite.py <ir.yaml> --tier 0 --size 1664*909 -o gen/lite0.md
  python scripts/brief_lite.py <ir.yaml> --tier 1 --add gen/round0_fail.md -o gen/lite1.md
  python scripts/brief_lite.py <ir.yaml> --tier 0            # 不给 -o 就打到 stdout

写出后照常喂给 gen_figure.py（--brief），闸门不用改。

一句话的来源：优先 IR 的 figure.one_liner（推荐自己写一句），
没有就退回 figure.physics_claim 的前 N 句（--sents，默认 1）。
允许出现的标签：优先取 IR 里"文字标注"那个元素的 text；没有就用内置的通用短表。

★ 为什么不自动把失败约束全塞进来：作者要的是「物理不对的地方第二次添加」——
  增量由人判断（看上一轮的图 + 闸门报告），这个脚本只负责把增量拼进简报，不负责猜。
★ 参考图的角色不变（AGENTS.md 0.1）：--ref 只给风格书，--content-ref 只给作者手绘草图
  （render 阶段才允许给上一轮已过闸口①的草图）。极简档不改变这条。
★ v4.14 起编译出的简报固定带两句（作者 2026-10-14）：
  ① 有 --add（C 档）时自动加「只改物理 / 几何，材质保持不变（以给的那张图为准）」—— 形状是
     物理、材质是观感（`ladder_gate` 的 L11 会查，漏写即硬伤；点名具体材质只出软警）；
  ② tier >= 1 时自动加「上一版画得好的部分保留、只在此基础上改得更好看」。
★ v4.15 起四档阶梯（A → B → C → D，见 ladder_gate.py）。这个编译器负责的是草图简报：
  · `--tier 0` ≈ **B 档**（一句话 + 画布/面板序列 + 输出硬约束，+ --ref 风格图，不给 --content-ref）；
  · `--tier 1` ≈ **D 档**的底稿（再叠五条 3D 空间线索 + 各面板形态）；
  · `--swap-from-a "核子=核子球团"` ≈ **C 档**（把 A 档画得好的元素搬进来、替换 B 档里对应的
    那一处；`ladder_gate` 的 L12 会查这一句）。C 档要同时给 A 与 B 两张 --content-ref（L9）。
  · `--add <上一轮画错.md>` ≈ **D 档**的增量（+ 材质保持不变那句，L11/L4）。
"""

import argparse
import io
import os
import re
import sys

ALLOWED_DEFAULT = "a b c d、QGP、Glasma、hadrons、e+、e-、γ、τ、T_c、x、y、z（按本图 IR 的元素命名）"

DEPTH_CORE = [
    "每个面板画一张【斜置的网格板】当空间基准：它是一块有厚度的平行四边形，两条边分别朝画面"
    "右下方与右上方延伸；板面上那两组网格线的方向，就是这张板的两个【面内轴】方向。",
    "物体【坐在板上】：接触处必须有一圈【接触阴影】（板面在那儿变暗）；"
    "没有接触阴影 = 贴纸。",
    "坐标三轴画成【有透视的实体轴】：三根轴方向彼此不同、并且与板面对得上 —— 板面内的两根轴"
    "要【严格贴着板面里的两组网格线】，竖直的那根是板的法线。轴名写在对应轴头上，"
    "一个面板只画一组三轴，绝不允许出现重复的轴名或悬空的轴名。",
    "全图共用【一个光源】：所有球的高光落在同一个方位，所有接触阴影朝同一个方向。",
]

DEPTH_HEP_FIREBALL = (
    "火球是【半透明的发光体积】：白热核 + 径向温度梯度 + 外发光，且板的网格线能透过它看见。"
)
DEPTH_HEP_NUCLEON = (
    "核与旁观碎片画成【核子球团】：一堆有明暗的小球堆成的团，不是一坨光滑团块。"
)


def depth_lines(doc):
    blob = str(doc)
    out = list(DEPTH_CORE)
    if any(k in blob for k in ("火球", "QGP", "qgp", "Glasma", "glasma", "夸克胶子", "高温")):
        out.append(DEPTH_HEP_FIREBALL)
    if any(k in blob for k in ("核子", "旁观", "碎片")):
        out.append(DEPTH_HEP_NUCLEON)
    return out

PANEL_RE = re.compile(r"^面板\s*([a-zA-Z])\s*(?:[—\-–－:：、,，]\s*)?(?:的)?\s*(.+)$")


def read_ir(path):
    try:
        import yaml
    except ImportError:
        sys.exit("需要 PyYAML：pip install pyyaml")
    with io.open(path, encoding="utf-8") as f:
        return yaml.safe_load(f.read())


def _flat(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sents(text, n=1):
    flat = _flat(text)
    if not flat:
        return ""
    parts = [p for p in re.split(r"(?<=[。！？；;])", flat) if p]
    return "".join(parts[:n]) if parts else flat


def one_liner(doc, sents=1):
    fig = doc.get("figure") or {}
    for key in ("one_liner", "一句话"):
        if fig.get(key):
            return _flat(fig[key])
    return _sents(fig.get("physics_claim"), sents)


def panel_matches(doc):
    out = []
    for el in (doc.get("elements") or []):
        if not isinstance(el, dict):
            continue
        m = PANEL_RE.match(_flat(el.get("name")))
        if m:
            out.append((m.group(1).lower(), m.group(2).strip(), el))
    return out


def panels_line(doc):
    m = panel_matches(doc)
    seen = {}
    for k, name, _el in m:
        seen.setdefault(k, name)
    if len(seen) >= 2:
        return " → ".join("%s %s" % (k, seen[k]) for k in sorted(seen))
    claims = (doc.get("figure") or {}).get("panel_claim")
    if isinstance(claims, dict) and claims:
        out = []
        for k in sorted(claims):
            txt = re.sub(r"[（(].*?[）)]", "", _sents(claims[k], 1))
            out.append("%s %s" % (k, txt[:26]))
        return " → ".join(out)
    return " → ".join("%s %s" % (k, name) for k, name, _ in m)


def panel_lines(doc):
    out = []
    for key, name, el in panel_matches(doc):
        role = _sents(el.get("physics_role"), 1)
        prim = _flat(el.get("primitive"))
        tail = "（形态：%s）" % prim if prim else ""
        out.append("- %s %s：%s%s" % (key, name, role, tail))
    if out:
        return out
    # 退回 figure.panel_claim：没有"面板 x"命名的元素时也能给出每面板一句形态
    claims = (doc.get("figure") or {}).get("panel_claim")
    if isinstance(claims, dict):
        for k in sorted(claims):
            body = re.sub(r"[（(].*?[）)]", "", _sents(claims[k], 2)).strip()
            out.append("- 面板 %s：%s" % (k, body))
    return out


def _text_elements(doc):
    out = []
    for el in (doc.get("elements") or []):
        if isinstance(el, dict) and el.get("text"):
            out.append(el)
    return out


def captions(doc):
    for el in _text_elements(doc):
        t = str(el.get("text"))
        if "approach" in t:
            return _flat(t)
    return ""


def labels(doc):
    """允许出现在图上的标签：取"文字标注 / 命名"那个元素；把 "z (beam)" 这种括号说明去掉。"""
    for el in _text_elements(doc):
        nm = _flat(el.get("name"))
        if any(k in nm for k in ("文字标注", "标签", "label", "legends")):
            toks = []
            for raw in re.split(r"[,，、;；]+", str(el.get("text"))):
                tok = re.sub(r"\s*[（(].*?[)）]\s*$", "", raw.strip())
                if tok:
                    toks.append(tok)
            if toks:
                return "  ".join(toks)
    # 退路二：IR 顶层 texts:（panel_letters / labels_a / labels_b …）
    blk = doc.get("texts")
    if isinstance(blk, dict):
        toks = []
        for k, v in blk.items():
            if any(bad in str(k).lower() for bad in ("convention", "说明")):
                continue
            vals = v if isinstance(v, list) else [v]
            for item in vals:
                tok = _flat(item)
                if tok and tok not in toks:
                    toks.append(tok)
        if toks:
            return "  ".join(toks)
    return ALLOWED_DEFAULT


def parse_size(text):
    m = re.match(r"^(\d+)\s*[*x×]\s*(\d+)$", str(text).strip())
    if not m:
        sys.exit("--size 要写成 W*H（如 1664*909），实得 %r" % text)
    return int(m.group(1)), int(m.group(2))


def build(doc, tier, wh, added=None, sents=1, swap_from_a=None):
    w, h = wh
    fig = doc.get("figure") or {}
    ol = one_liner(doc, sents)
    pl = panels_line(doc)
    n_panels = fig.get("panels_count")
    cap = captions(doc)
    lab = labels(doc)
    L = []
    L.append("【任务】" + ol)
    L.append("")
    L.append("画成 **3D 渲染风格的期刊插画**（有体积、有明暗），不是扁平矢量；纯白底、不要边框。")
    if pl:
        L.append("画布 %d×%d（宽高比 %.2f）；%s 个等宽面板从左到右是同一条时间轴：%s。"
                 % (w, h, w / h, n_panels or len(panel_matches(doc)) or 1, pl))
    else:
        L.append("画布 %d×%d（宽高比 %.2f）；单幅示意图，不分面板。" % (w, h, w / h))
    if tier >= 1:
        L.append("")
        _depth = depth_lines(doc)
        L.append("★★★ 必须是【一个三维场景】，不是白底上摆的一堆贴纸。下面 %d 条比好看更重要："
                 % len(_depth))
        for i, d in enumerate(_depth, 1):
            L.append("  %d. %s" % (i, d))
        if panel_lines(doc):
            L.append("")
            L.append("各面板形态：")
            L.extend(panel_lines(doc))
    L.append("")
    L.append("【输出硬约束】图上只许出现这些标签：%s。此外一个字都不要写 ——"
             "不成段、不图例、不色卡、不章节编号、不说明段落。" % lab)
    if cap:
        L.append("面板说明逐字照写（大小写/上下标都对，不要翻译）：%s" % cap)
    L.append("本说明是画图指令，不是要画的内容；不要把指令本身画成文档 / 海报 / 幻灯片。")
    if tier >= 1:
        # ★ 作者 2026-10-13：IR 只在 C 档起作用，且只改 A 档真画错的。
        #   光源方位这类是「画法/质感」（§0.7 第 2/3 层），不能当硬约束，
        #   所以放进「外观建议」块（tools/ir_scope_gate.py S1/S4 只允许它在这里）。
        L.append("")
        L.append("════ 外观建议（可以改得更漂亮，物理不许因此破）════")
        L.append("- 全图可以共用一个光源（方位 128° / 仰角 38°），"
                 "让所有高光与接触阴影朝同一个方向。")
        L.append("- 上一版（已给的 --content-ref 那张图）里**画得好的部分保留** —— 物体的形状 /"
                 "布局 / 配色 —— 只在此基础上改得更好看，不要把已经画对的东西推倒重画。")
    if swap_from_a:
        # ★ v4.15（作者 2026-10-14）：新的 C 档 = 元素替换档 —— 把 A 档画得好的东西搬进来，
        #   替换 B 档里对应的那一处。ladder_gate 的 L12 查这一句（缺了就是硬伤）。
        L.append("")
        L.append("════ 把上一档（A）画得好的元素搬进来（C 档：元素替换，作者 2026-10-14）════")
        for _x in swap_from_a:
            L.append("- 把 A 档画得好的【%s】搬进来，**替换 B 档里对应的那一处**" % _x)
        L.append("- 只做**元素级替换**：A 画得好的部分要留着（形状 / 质感 / 配色照 A），"
                 "B 里对应的那个东西才被换掉；其余照 B 档，不要整张重画。")
        L.append("- 元素是物理（该换对），材质是观感：**材质保持不变** —— 以给的那张图为准，"
                 "不要替模型指定具体材质。")
    if added:
        L.append("")
        L.append("════ 上一轮画错的地方（这一轮必须改对）════")
        L.append(str(added).strip())
        L.append("")
        L.append("★ 这一轮**只改上面列出的物理 / 几何**：物体的**材质保持不变** —— 以给的 "
                 "--content-ref 那张图（上一版）的材质为准，**材质 / 质感 / 配色 / 光源一律照它"
                 "不变**（形状 / 几何是物理，该改；材质是观感，不要动）。")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="极简档简报编译器（从简单到复杂）")
    ap.add_argument("ir", help="IR 的 .yaml")
    ap.add_argument("--tier", type=int, choices=(0, 1), default=0,
                    help="0=一句话档；1=加五条 3D 线索与各面板形态")
    ap.add_argument("--size", default="1664*909", help="画布 W*H")
    ap.add_argument("--sents", type=int, default=1,
                    help="figure 里没写 one_liner 时，退回 physics_claim 的前 N 句")
    ap.add_argument("--add", action="append", default=[],
                    help="追加的增量约束文件（上一轮画错的点），可多次给")
    ap.add_argument("--swap-from-a", action="append", default=[],
                    help="C 档：把 A 档画得好的 <元素> 搬进来、替换 B 档里对应的那一处（可多次给）")
    ap.add_argument("-o", "--out", default=None, help="输出 .md；不给就打到 stdout")
    a = ap.parse_args()

    doc = read_ir(a.ir)
    added = ""
    for p in a.add:
        if not os.path.exists(p):
            sys.exit("找不到增量约束文件：%s" % p)
        with io.open(p, encoding="utf-8") as f:
            added += ("\n" if added else "") + f.read().strip()
    text = build(doc, a.tier, parse_size(a.size), added, a.sents, a.swap_from_a)

    if a.out:
        d = os.path.dirname(os.path.abspath(a.out))
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s" % a.out)
    else:
        sys.stdout.write(text)
    print("tier=%d  字符数=%d  面板=%s  标签=%s  增量约束=%d 个文件"
          % (a.tier, len(text), panels_line(doc) or "（单幅）", labels(doc)[:60], len(a.add)))


if __name__ == "__main__":
    main()
