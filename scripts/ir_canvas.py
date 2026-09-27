#!/usr/bin/env python3
"""
ir_canvas —— IR 画布的**唯一读取口**
======================================================================

★ 为什么需要它（2026-09-27 实测）

`references/ir-spec.md` 把画布写在 **composition.canvas**：

    composition:
      canvas: {ratio: "约 1.36（横）", 用途: "单栏或双栏图"}

但 `ir_to_genbrief.py` / `check_sketch.py` 读的是 `figure.canvas`（旧写法）。
仓库里 9 份 IR 有 **6 份**按规范写 → 它们的画布被**静默丢弃**：

    sketch5_upc.ir.yaml 声明 composition.canvas.ratio = "约 2.1（横）"
      → 简报写出默认的 1400×560（宽高比 2.50）
      → gen_figure 又按 --size 默认请求 1664×928（1.79）
    同一张图三个比例，模型照哪个都可能错。

更糟的是 `ir_brief_audit.py` 的哨兵把 canvas 塞在 `figure.canvas` 下，
所以这个丢失**体检不出来** —— 它照样报「IR → 简报 无损 ✅」。

**规则：画布一律用本模块读，别再直接 `get("canvas")`。**
"""
import re

_LAYERS = ("composition", "figure")     # 规范位置在前；figure 是旧写法，兜底


def canvas_node(ir):
    """返回 (canvas_dict, 来源说明)。规范位置 `composition.canvas` 优先。"""
    for layer in _LAYERS:
        node = ((ir or {}).get(layer) or {}).get("canvas")
        if isinstance(node, dict) and node:
            return node, "%s.canvas" % layer
    return {}, "(无)"


def parse_ratio(text):
    """从『约 2.1（横）』『约 1.32（横版，833 x 633 px）』这类自由文本取宽高比。

    优先认显式像素『833 x 633』；否则取第一个数字当比值。取不到返回 None。
    """
    s = str(text)
    m = re.search(r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)", s)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a > 0 and b > 0:
            return a / b
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        r = float(m.group(1))
        if 0.05 <= r <= 20:
            return r
    return None


def pixel_size(ir):
    """IR 明确给了像素尺寸才返回 (W, H)；否则 None。

    ★ 只有这里返回的值才可以直接当 API 的 `--size` 用 ——
      API 只收一份**离散**的尺寸清单，按比例算出来的 1664×792 会被拒。
    """
    node, _ = canvas_node(ir)
    w, h = node.get("w"), node.get("h")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
        return int(w), int(h)
    return None


def declared_ratio(ir):
    """IR 声明的宽高比（数字）；没有就 None。像素尺寸也能推出比例。"""
    px = pixel_size(ir)
    if px:
        return px[0] / px[1]
    node, _ = canvas_node(ir)
    if node.get("ratio") is not None:
        return parse_ratio(node["ratio"])
    return None


def canvas_for_brief(ir, default=(1664, 928)):
    """简报里『画布』那一行该写什么 → (W, H, 说明)。

    ★ 只用于**文字描述**：告诉模型画布长什么样。
      不要拿它当 API 的 `--size`（见 pixel_size 的说明）。
    """
    px = pixel_size(ir)
    if px:
        return px[0], px[1], "IR 的像素尺寸"
    node, _ = canvas_node(ir)
    r = declared_ratio(ir)
    if r:
        long_side = max(default)
        if r >= 1:
            return long_side, int(round(long_side / r)), "IR 声明的比例 %.2f" % r
        return int(round(long_side * r)), long_side, "IR 声明的比例 %.2f" % r
    if node.get("ratio") is not None:
        # ★ 有 ratio 却解析不出数字 = IR 写法有问题。以前这里静默退回默认画布，
        #   模型照默认比例画、IR 的归一化坐标全失效，而且没人知道。
        return (default[0], default[1],
                "默认（★ IR 的 ratio 认不出数字：%s）" % str(node["ratio"])[:40])
    return default[0], default[1], "默认（IR 没写画布）"


def ratio_deviation(ir, size_wh):
    """IR 声明的比例 vs 实际请求尺寸的比例，返回相对偏差；判不了返回 None。"""
    want = declared_ratio(ir)
    if not want or not size_wh or size_wh[1] <= 0:
        return None
    got = size_wh[0] / size_wh[1]
    return abs(got - want) / want


def parse_size(text):
    """把 `1664*928` / `1664x928` / `1664×928` 解析成 (W, H)。"""
    m = re.match(r"^\s*(\d+)\s*[x×*]\s*(\d+)\s*$", str(text))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))
