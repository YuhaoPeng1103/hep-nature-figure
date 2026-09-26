#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sketch_to_vector —— 把【草图位图】矢量化成「人能直接改」的 SVG 草图
=========================================================================

## 它在流程里的位置

    生图 ──▶ 草图位图 ──★本脚本★──▶ 草图 SVG（人可改）──▶ 成品位图 ──▶ 成品 SVG
                                     ↑
                     路径 2/3 都要求草图是**矢量的**：
                     人要能在 Illustrator 里直接拖、删、改，而不是对着 PNG 干瞪眼。

## 和 raster_to_vector_semantic.py 的分工

| | `sketch_to_vector.py`（本脚本） | `raster_to_vector_semantic.py` |
|---|---|---|
| 服务对象 | **草图**（中间稿，会被人改） | **成品**（要交付、要物理命名） |
| 要不要写表 | **不用** —— 全自动 | 要写 `panels.py` + `words.txt` |
| 图层命名 | `part-01`…（按自动切分） | 物理名字（`photon-A`…） |
| 何时用 | 草图一出来就矢量化，先给人看 | 最终交付那一步 |

> ⚠️ 草图**不需要**物理命名表 —— 表是给最终图准备的。草图阶段靠自动切分，
> 每个连通域就是一个独立子层，人在 Illustrator 里重命名即可。
> 想省事的话，直接复制草图的图层名，改成品图时再补物理名。

## 用法

    python3 scripts/sketch_to_vector.py gen/sketch_s1.png -o gen/sketch_s1.svg

    # 想让草图里的字也是真 <text>（Windows 上自动调系统 OCR）
    python3 scripts/sketch_to_vector.py gen/sketch_s1.png -o gen/sketch_s1.svg --ocr

    # 已经自己写好了词表
    python3 scripts/sketch_to_vector.py gen/sketch_s1.png -o gen/sketch_s1.svg --words w.txt

    # 更忠实（更慢更大）
    python3 scripts/sketch_to_vector.py gen/sketch_s1.png -o gen/sketch_s1.svg --R 8 --K 8
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

# 自动生成的版式表：一个面板铺满画布；元素名由 element_of 动态给。
_TEMPLATE = '''# -*- coding: utf-8 -*-
"""自动生成（sketch_to_vector.py）—— 只服务于「把草图矢量化成人可改的 SVG」。

草图没有物理命名表：每个自动切分出来的连通域就是一个独立可选子层
（part-01、part-02…），人在 Illustrator 里重命名即可。
"""
import numpy as np

W_CANVAS, H_CANVAS = {W}, {H}

CELLS = [("p", "p", "graphics", (0, 0, W_CANVAS, H_CANVAS), "bitmap sketch (auto-split)")]


def order():
    seen, o = set(), []
    for cid, *_ in CELLS:
        if cid not in seen:
            seen.add(cid); o.append(cid)
    return o


def meta():
    m = {{}}
    for cid, pan, role, rect, desc in CELLS:
        m.setdefault(cid, dict(panel=pan, role=role, desc=desc, rects=[]))["rects"].append(rect)
    return m


def cell_index(H, W):
    idx = np.full((H, W), -1, np.int32)
    for i, (cid, pan, role, (x0, y0, x1, y1), d) in enumerate(CELLS):
        idx[y0:y1, x0:x1] = i
    return idx


# 顺序 = 图层输出顺序；只有 background 需要排在前面，其余由 groupvec 按像素量排
ELEMENTS = {{"p": [("background", "Panel background", [(0, 0, W_CANVAS, H_CANVAS)], None)]}}
SPLIT = {{}}
MANUAL = []
FIX = {{}}
DROP = set()
ROTATED = []

_N = [0]


def pixel_pred(a, spec):
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    kind, thr = spec
    return lum < thr if kind == "dark" else lum >= thr


def element_of(cid, bbox, rgb):
    """★ 这里不按颜色命名图层（人会改它），只把「白底」和「形体」分开。"""
    x0, y0, x1, y1 = bbox
    area = (x1 - x0) * (y1 - y0)
    if min(rgb) >= 246 and area >= 0.25 * W_CANVAS * H_CANVAS:
        return ("background", "Panel background (white)")
    _N[0] += 1
    return ("part-%02d" % _N[0],
            "auto part %02d  bbox=%d,%d,%d,%d  rgb=%d,%d,%d"
            % (_N[0], x0, y0, x1, y1, rgb[0], rgb[1], rgb[2]))
'''


def make_panels(path: pathlib.Path, W: int, H: int):
    path.write_text(_TEMPLATE.format(W=W, H=H), encoding="utf-8")
    return path


def try_ocr(image: pathlib.Path, out_words: pathlib.Path):
    """Windows.Media.Ocr 出词表（skill 自带脚本，2× 放大后识别）。

    ★ 失败时**把原因打出来**：这里曾经是 `except: return None`，
      结果脚本的 `-Out` 参数一直没声明（PowerShell 报 ambiguous）而
      使用者只看到“没有词表”，反复加 --ocr 也无济于事。
    """
    ps1 = HERE / "raster_vector" / "ocr_words.ps1"
    if not ps1.exists():
        print("  ! OCR 跳过：找不到 %s" % ps1)
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", str(ps1), "-Image", str(image),
                            "-Out", str(out_words)],
                           capture_output=True, text=True, errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        print("  ! OCR 超时（180s）")
        return None
    except (OSError, subprocess.SubprocessError) as e:
        print("  ! OCR 无法运行：%s" % e)
        return None
    if out_words.exists() and out_words.stat().st_size > 0:
        return out_words
    print("  ! OCR 没出词表（returncode=%s）" % r.returncode)
    for ln in (r.stderr or "").strip().splitlines()[-4:]:
        print("    " + ln.strip())
    return None


def main():
    ap = argparse.ArgumentParser(
        description="草图位图 → 人可改的 SVG 草图（不需要写 panels.py）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--words", default="", help="词表；不给可加 --ocr 自动出")
    ap.add_argument("--ocr", action="store_true", help="用系统 OCR 自动出词表（Windows）")
    ap.add_argument("--W", type=int, default=None, help="工作分辨率宽（默认=源图宽）")
    ap.add_argument("--trim", type=int, default=0,
                    help="先裁掉四周 N px 再矢量化（生图模型常在四周画一条贴边细外框）")
    ap.add_argument("--R", type=float, default=12.0, help="四叉树色差阈值（小=更准更大）")
    ap.add_argument("--K", type=int, default=7, help="最粗边长 2^K")
    ap.add_argument("--q", type=int, default=16,
                    help="每通道颜色量化级数（默认 16；0=关）。"
                         "草图边缘的抗锯齿会切出巨量碎路径，量化后才能给人改。"
                         "实测（同一张草图）：0->30412 条/MAE 0.376；"
                         "6->873/3.210；10->1255/1.273；**16->2111/1.102（>8 误差 0.31% 与不量化持平）**")
    a = ap.parse_args()

    src = pathlib.Path(a.image).resolve()
    if not src.exists():
        sys.exit("找不到 %s" % src)
    from PIL import Image
    SW, SH = Image.open(src).size
    W = a.W or SW
    out = pathlib.Path(a.out).resolve() if a.out else src.with_suffix(".svg")

    panels = make_panels(out.parent / ("_sketch_panels_%s.py" % src.stem), W, SH * W // SW)
    use_src = src
    if a.trim:
        from PIL import Image as _Im
        im = _Im.open(src).convert("RGB")
        w0, h0 = im.size
        im = im.crop((a.trim, a.trim, w0 - a.trim, h0 - a.trim))
        use_src = out.parent / ("_sketch_trim_%s.png" % src.stem)
        im.save(use_src)
        print("已裁掉四周 %d px -> %dx%d" % (a.trim, im.size[0], im.size[1]))

    words = a.words
    if not words and a.ocr:
        got = try_ocr(src, out.parent / ("_sketch_words_%s.txt" % src.stem))
        if got:
            words = str(got)
            print("OCR 词表: %s" % got)
        else:
            print("  → --ocr 没成功（原因见上）：本次按无名牌文字处理")
    if not words:
        if a.ocr:
            print("（没拿到词表 → 文字会留在色块里。"
                  "可以自己写一份 --words，或查上面的 OCR 报错）")
        else:
            print("（没有词表 → 文字会留在色块里。"
                  "要真 <text> 就加 --ocr，或自己写 --words）")

    cmd = [sys.executable, str(HERE / "raster_to_vector_semantic.py"), str(use_src),
           "-o", str(out), "--panels", str(panels),
           "--W", str(W), "--R", str(a.R), "--K", str(a.K), "--q", str(a.q),
           "--legend", str(out.with_name(out.stem + "_layers.md")),
           "--manifest", str(out.with_name(out.stem + ".json")),
           "--check"]
    if words:
        cmd += ["--words", words]
    else:
        cmd += ["--no-text"]
    print("→ %s" % " ".join(cmd[1:]))
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
