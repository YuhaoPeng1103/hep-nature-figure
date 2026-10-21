#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preview -- 把要「给模型看」的图压成 1800px / JPEG q90 的预览，原图不动。

作者 2026-10-21 约定：
  · 生产图保持 2336*1280（描摹、axis_gate、keep_gate 都要全尺寸）；
  · 模型只看长边 <=1800 的 JPEG q90（20 张约 5-8MB，远低于 DeepSeek 48MiB 请求体）；
  · 4up / 长条拼图也先缩到 1800px 再看；全尺寸只喂脚本。

用法：
    python scripts/preview.py <文件或目录...> [--max 1800] [--quality 90]
                            [--outdir DIR] [--json]

默认输出到这些输入的最小公共目录下的 `_preview/`，文件名带一级目录前缀避免
A/B/C/D 同名冲突，例如 `A__sketch_s7101.jpg`。打印每张的尺寸与体积。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in IMG_EXT and "_preview" not in f.parts:
                    out.append(f)
        elif p.is_file():
            out.append(p)
        else:
            print(f"[skip] not found: {p}", file=sys.stderr)
    return out


def common_root(files: list[Path]) -> Path:
    if len(files) == 1:
        return files[0].parent
    return Path(os.path.commonpath([str(f.parent) for f in files]))


def main() -> int:
    ap = argparse.ArgumentParser(description="make <=1800px JPEG previews for model viewing")
    ap.add_argument("paths", nargs="+", help="image files or directories")
    ap.add_argument("--max", type=int, default=1800, help="max long side px (default 1800)")
    ap.add_argument("--quality", type=int, default=90, help="JPEG quality (default 90)")
    ap.add_argument("--outdir", default=None, help="output dir (default <common>/_preview)")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is required: pip install pillow", file=sys.stderr)
        return 2

    files = collect(args.paths)
    if not files:
        print("no images found", file=sys.stderr)
        return 1

    root = common_root(files)
    outdir = Path(args.outdir) if args.outdir else root / "_preview"
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    total = 0
    for src in files:
        try:
            im = Image.open(src)
            im.load()
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {src}: {exc}", file=sys.stderr)
            continue

        w, h = im.size
        scale = min(1.0, args.max / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")

        parent = src.parent.name or "root"
        stem = src.stem
        dst = outdir / f"{parent}__{stem}.jpg"
        im.save(dst, "JPEG", quality=args.quality, optimize=True, progressive=True)
        size = dst.stat().st_size
        total += size
        rows.append({
            "src": str(src.resolve()),
            "preview": str(dst.resolve()),
            "src_size": [w, h],
            "size": list(im.size),
            "bytes": size,
        })

    if args.json:
        print(json.dumps({"outdir": str(outdir.resolve()), "total_bytes": total, "items": rows},
                         ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print(f"{r['preview']}  {r['size'][0]}x{r['size'][1]}  {r['bytes']/1024:.0f} KB")
        print(f"-- {len(rows)} previews, {total/1048576:.2f} MB total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
