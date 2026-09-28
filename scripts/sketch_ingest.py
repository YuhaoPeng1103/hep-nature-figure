#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sketch_ingest —— 把【人改完的草图】灌回流程（v3.0 人机交接的另一半）
================================================================================

    用户改完 handoff/cand_02.svg ──★本脚本★──▶ gen/sketch_edited_clean.png
                                                      │
                                                      ▼
                            gen_figure.py --content-ref gen/sketch_edited_clean.png

## 三条纪律（都写死在代码里，不靠自觉）

1. **人改不豁免闸口**：默认**强制**重跑闸口①（`check_sketch.py`），几何断言不过就
   **拒绝往下走**并打出返修单。人眼比机器强的地方是"物理对不对、好不好看"，
   不是"比例准不准" —— 那一条机器量得比人准（纪律 1：量，不要看）。
2. **IR 仍是唯一权威**：人把 v2 的方向画反了、把火球压扁了，闸口会当场拒。
   真需要改物理 → 先改 IR，再改图（别让图偷偷变成新的"真相"）。
3. **文字仍是占位**：草图上别精修文字，正式文字在成品位图 → 矢量那一步才重写。

## 用法

    # 用户改完 SVG 传回（推荐路径）
    python3 scripts/sketch_ingest.py handoff/cand_02_edited.svg --ir ir/x.ir.yaml \
        --size 1664*928 -o gen/sketch_edited_clean.png

    # 用户是在纸上重画的 / 传的是 PNG
    python3 scripts/sketch_ingest.py 我的草图.png --ir ir/x.ir.yaml --size 1664*928

    # 四周有贴边细外框（打印/截图带来的一圈灰线）→ 先裁掉
    python3 scripts/sketch_ingest.py ... --trim 2

    # 明知画布比例被改过、就要拉伸到 IR 的画布
    python3 scripts/sketch_ingest.py ... --fit stretch

    # 只想栅格化、死活不过闸口（危险：跳过物理检查，日志里会留大字）
    python3 scripts/sketch_ingest.py ... --no-gate

退出码：0 = 过了闸口①，可以拿去出成品位图；1 = 被闸口拒（按打印的返修单改）。
"""
from __future__ import annotations

from _console import init_console

init_console()          # Windows：管道下 stdout 是 gbk，打印 ✅ 会崩

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def parse_size(s):
    if not s:
        return None
    t = s.lower().replace("x", "*")
    if "*" not in t:
        sys.exit("--size 要写 W*H（如 1664*928），实得 %r" % s)
    w, h = t.split("*", 1)
    return int(w), int(h)


def load_rgb(src):
    """SVG 走 cairosvg 栅格化；PNG/JPG 直接读。都转成 RGB 白底。"""
    from PIL import Image
    if src.suffix.lower() in (".svg", ".svgz"):
        try:
            import cairosvg
        except ImportError:
            sys.exit("回流 SVG 需要 cairosvg：pip install cairosvg\n"
                     "  （也可以让用户先自己导出 PNG 再传）")
        import io as _io
        # 先按高分辨率光栅化，再由 fit() 缩到目标尺寸 —— 直接按目标宽度光栅化
        # 会让细线在缩放比 >1 时发虚
        buf = cairosvg.svg2png(url=str(src), output_width=2048)
        return Image.open(_io.BytesIO(buf)).convert("RGB")
    from PIL import Image as _Im
    return _Im.open(src).convert("RGB")


def fit(im, W, H, mode="contain"):
    """贴到目标画布。contain = 等比缩放后居中（不拉伸，留白边）；stretch = 硬拉。"""
    from PIL import Image
    if mode == "stretch":
        return im.resize((W, H), Image.LANCZOS)
    r = min(W / im.width, H / im.height)
    nw, nh = max(1, round(im.width * r)), max(1, round(im.height * r))
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    canvas.paste(im.resize((nw, nh), Image.LANCZOS),
                 ((W - nw) // 2, (H - nh) // 2))
    return canvas


def main():
    ap = argparse.ArgumentParser(
        description="人改完的草图（SVG/PNG）→ 干净的草图位图，并强制重过闸口①",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("image", help="用户传回的草图：.svg（改过的候选）或 .png（重画的）")
    ap.add_argument("--ir", required=True, help="对应 IR（闸口①的断言从它来）")
    ap.add_argument("--size", default="1664*928", help="目标画布 W*H（默认 1664*928）")
    ap.add_argument("-o", "--out", default="gen/sketch_edited_clean.png")
    ap.add_argument("--fit", choices=("contain", "stretch"), default="contain",
                    help="比例不符时怎么办：contain=不拉伸居中（默认），stretch=硬拉")
    ap.add_argument("--trim", type=int, default=0, metavar="N",
                    help="先裁掉四周 N px（贴边细外框；走 trim_border.py --bg 0.975）")
    ap.add_argument("--no-gate", action="store_true",
                    help="★ 跳过闸口①（危险：跳过物理检查，除非用户明确要求）")
    a = ap.parse_args()

    src = pathlib.Path(a.image).resolve()
    if not src.exists():
        sys.exit("找不到 %s" % src)
    dst = pathlib.Path(a.out).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    W, H = parse_size(a.size)

    im = load_rgb(src)
    dw, dh = abs(im.width / im.height - W / H) / (W / H), None
    if dw > 0.02 and a.fit == "contain":
        print("⚠️ 你这张图的画布比例 %.4f 与目标 %.4f 差 %.1f%% —— 默认**不拉伸**，"
              % (im.width / im.height, W / H, dw * 100))
        print("   会居中留白边；闸口量的就是留白后的图，比例断言可能因此不过。")
        print("   要么把画布比例改回 IR 的（推荐），要么确认要改物理 → 先改 IR，"
              "或显式 --fit stretch。")
    im = fit(im, W, H, a.fit)
    im.save(dst)
    print("已写出 %s（%dx%d，%.0f KB）"
          % (dst, W, H, dst.stat().st_size / 1024))

    if a.trim:
        tb = HERE / "trim_border.py"
        r = subprocess.run([sys.executable, str(tb), str(dst), "-o", str(dst),
                            "--max", str(a.trim), "--bg", "0.975"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        print((r.stdout or "").strip() or (r.stderr or "").strip())

    if a.no_gate:
        print()
        print("=" * 66)
        print("★ 已跳过闸口①（--no-gate）：这张图**没有**经过几何断言检查。")
        print("  后续任何「物理对不对」的问题，责任在人，不在闸口。")
        return 0

    rep = dst.with_suffix(".check.json")
    r = subprocess.run([sys.executable, str(HERE / "check_sketch.py"), str(dst),
                        "--ir", a.ir, "--json", str(rep)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print()
    print("=" * 66)
    print("闸口①（在**你改完的这张图**上重跑）：")
    print((r.stdout or "").strip())

    ok = r.returncode == 0
    try:
        d = json.loads(rep.read_text(encoding="utf-8"))
        img = (d.get("images") or [{}])[0]
        hard, soft = img.get("hard") or [], img.get("soft") or []
    except Exception as e:
        print(" ⚠️ 读不到闸口报告（%s: %s）→ 按**未通过**处理" % (type(e).__name__, e))
        hard, soft, ok = ["闸口没跑出报告"], [], False

    print()
    if not ok:
        print("❌ 没过闸口① —— 先按上面的返修单改，别往下走（成品位图要花钱）。")
        if hard:
            print("   硬伤：%s" % "；".join(str(x) for x in hard))
        print("   改的还是那张 SVG：改完再灌一次，命令一样。")
        return 1
    print("✅ 过了闸口①（软警 %d 条）。下一步：拿它出成品位图 ——" % len(soft))
    print()
    print("   python3 scripts/gen_figure.py --brief brief2.md --stage render \\")
    print("       --content-ref %s --ref refs/<风格参考>.png --seeds 21,22 --outdir gen/"
          % dst.name)
    print()
    print("   （--content-ref 会在送模型前自动降级成 layout-only —— 手改的草图照样降级，"
          "别用 --ref 传它。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
