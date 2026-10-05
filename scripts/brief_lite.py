#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brief_lite.py —— 极简档简报编译器（v4.2）

作者 2026-10-05 的原话：
  「你给的提示词别那么复杂，从简单到复杂，比如最开始就给他一个草图和风格图，
    一句话说明一下需求，物理不对的地方第二次添加一些物理约束生成」

所以出图不再一上来就灌 7.5k 字符的规格书，改成三轮递增：

  第 0 轮  --tier 0   一句话 + 画布/面板序列 + 输出硬约束        （约 400 字符）
  第 1 轮  --tier 1   上面那些 + 五条 3D 空间线索 + 每面板一句形态（约 1.2k 字符）
  第 N 轮  --tier 1 --add gen/roundN_fail.md
                      只把上一轮**真的画错**的物理点追加进去（错了才加，对了不加）

用法：
  python scripts/brief_lite.py <ir.yaml> --tier 0 --size 2048*704 -o gen/brief_lite0.md
  python scripts/brief_lite.py <ir.yaml> --tier 1 --add gen/round0_fail.md -o gen/brief_lite1.md
  python scripts/brief_lite.py <ir.yaml> --tier 0            # 不给 -o 就打到 stdout

写出后照常喂给 gen_figure.py（--brief），闸门不用改：

  python scripts/gen_figure.py --brief gen/brief_lite0.md --stage sketch \
      --ref assets/t3-exemplars/T3-30.png --seeds 401,402 --size 2048*704 --outdir gen

一句话的来源：优先 IR 的 figure.one_liner（推荐自己写一句），
没有就退回 figure.physics_claim 的前 N 句（--sents，默认 1）。

★ 为什么不自动把失败约束全塞进来：作者要的是「物理不对的地方第二次添加」——
  增量由人判断（看上一轮的图 + 闸门报告），这个脚本只负责把增量拼进简报，不负责猜。
★ 参考图的角色不变（AGENTS.md 0.1）：--ref 只给风格书，--content-ref 只给作者手绘草图
  （render 阶段才允许给上一轮已过闸口①的草图）。极简档不改变这条。
"""

import argparse
import io
import os
import re
import sys

ALLOWED = "a b c d、QGP、Glasma、hadrons、e+、e-、γ、τ、T_c、x、y、z"

DEPTH = [
    "每个面板画一张【斜置的透视网格板】（反应平面）当空间基准：平行四边形，两条边分别朝画面"
    "右下方与右上方延伸，网格线比板底色深一档。",
    "物体【坐在板上】：接触处必须有【接触阴影】（板面在那儿变暗），或顺运动方向留一道"
    "暖色反光拖尾。没有接触阴影 = 贴纸。",
    "火球是【半透明的发光体积】：白热核 + 径向温度梯度 + 外发光，且板的网格线能透过它看见。",
    "核与旁观碎片画成【核子球团】：一堆有明暗的小球堆成的团，不是一坨光滑团块。",
    "坐标三轴画成【有透视的实体轴】：z 沿束流、x 沿碰撞参数（都在板面内，各沿板的一条边），"
    "y 是板的法线（朝观察者）。",
]

PANEL_RE = re.compile(r"^面板\s*([a-zA-Z])\s*[—\-–－:：]+\s*(.+)$")


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
        m = PANEL_RE.match(_flat(el.get("name")).replace("——", "——"))
        if m:
            out.append((m.group(1).lower(), m.group(2).strip(), el))
    return out


def panels_line(doc):
    return " → ".join("%s %s" % (k, name) for k, name, _ in panel_matches(doc))


def panel_lines(doc):
    out = []
    for key, name, el in panel_matches(doc):
        role = _sents(el.get("physics_role"), 1)
        prim = _flat(el.get("primitive"))
        tail = "（形态：%s）" % prim if prim else ""
        out.append("- %s %s：%s%s" % (key, name, role, tail))
    return out


def captions(doc):
    for el in (doc.get("elements") or []):
        if not isinstance(el, dict):
            continue
        t = el.get("text")
        if isinstance(t, str) and "approach" in t:
            return _flat(t)
    return ""


def parse_size(text):
    m = re.match(r"^(\d+)\s*[*x×]\s*(\d+)$", str(text).strip())
    if not m:
        sys.exit("--size 要写成 W*H（如 2048*704），实得 %r" % text)
    return int(m.group(1)), int(m.group(2))


def build(doc, tier, wh, added=None, sents=1):
    w, h = wh
    ol = one_liner(doc, sents)
    pl = panels_line(doc)
    cap = captions(doc)
    L = []
    L.append("【任务】" + ol)
    L.append("")
    L.append("画成 **3D 渲染风格的期刊插画**（有体积、有明暗），不是扁平矢量；纯白底、不要边框。")
    L.append("画布 %d×%d（宽高比 %.2f）；四个等宽面板从左到右是同一条时间轴：%s。" % (w, h, w / h, pl))
    if tier >= 1:
        L.append("")
        L.append("★★★ 必须是【一个三维场景】，不是白底上摆的一堆贴纸。下面五条比好看更重要：")
        for i, d in enumerate(DEPTH, 1):
            L.append("  %d. %s" % (i, d))
        L.append("")
        L.append("各面板形态：")
        L.extend(panel_lines(doc))
        L.append("全图共用一个光源（方位 128° / 仰角 38°），不要每个物体各自打光。")
    L.append("")
    L.append("【输出硬约束】图上只许出现这些字符：%s。此外一个字都不要写 ——"
             "不成段、不图例、不色卡、不章节编号、不说明段落。" % ALLOWED)
    if cap:
        L.append("面板说明逐字照写（大小写/上下标都对，不要翻译）：%s" % cap)
    L.append("本说明是画图指令，不是要画的内容；不要把指令本身画成文档 / 海报 / 幻灯片。")
    if added:
        L.append("")
        L.append("════ 上一轮画错的地方（这一轮必须改对）════")
        L.append(str(added).strip())
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description="极简档简报编译器（从简单到复杂）")
    ap.add_argument("ir", help="IR 的 .yaml")
    ap.add_argument("--tier", type=int, choices=(0, 1), default=0,
                    help="0=一句话档；1=加五条 3D 线索与各面板形态")
    ap.add_argument("--size", default="2048*704", help="画布 W*H")
    ap.add_argument("--sents", type=int, default=1,
                    help="figure 里没写 one_liner 时，退回 physics_claim 的前 N 句")
    ap.add_argument("--add", action="append", default=[],
                    help="追加的增量约束文件（上一轮画错的点），可多次给")
    ap.add_argument("-o", "--out", default=None, help="输出 .md；不给就打到 stdout")
    a = ap.parse_args()

    doc = read_ir(a.ir)
    added = ""
    for p in a.add:
        if not os.path.exists(p):
            sys.exit("找不到增量约束文件：%s" % p)
        with io.open(p, encoding="utf-8") as f:
            added += ("\n" if added else "") + f.read().strip()
    text = build(doc, a.tier, parse_size(a.size), added, a.sents)

    if a.out:
        d = os.path.dirname(os.path.abspath(a.out))
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s" % a.out)
    else:
        sys.stdout.write(text)
    print("tier=%d  字符数=%d  面板=%s  增量约束=%d 个文件"
          % (a.tier, len(text), panels_line(doc) or "（没识别到）", len(a.add)))


if __name__ == "__main__":
    main()
