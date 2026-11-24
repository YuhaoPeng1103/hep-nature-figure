#!/usr/bin/env python3
"""Preview and choose visual variants for one spec element slot."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import re
import sys
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from element_library import asset_map, is_safe_asset, load_index  # noqa: E402
from spec_compile import render_outputs, render_spec, validate_spec  # noqa: E402
from spec_confirm import load_spec  # noqa: E402

CLIENT_ROLES = {"client", "customer", "author", "user", "客户", "作者", "用户", "甲方"}


def spec_element(spec: dict, element_id: str) -> dict:
    element = next((e for e in spec.get("elements") or [] if e.get("id") == element_id), None)
    if not element:
        raise SystemExit(f"unknown element slot: {element_id}")
    return element


def options_for(element: dict, library: dict) -> tuple[str, list[dict]]:
    family = element.get("asset_family")
    if not family:
        selected = element.get("asset")
        asset = library.get(selected)
        if not asset:
            raise SystemExit(f"{element['id']}: fixed asset {selected!r} not found")
        family = asset.get("family")
    listed = element.get("variant_options")
    if listed:
        options = []
        for value in listed:
            matches = [
                a for a in library.values()
                if a.get("family") == family
                and (a["id"] == value or a.get("variant") == value)
            ]
            if len(matches) != 1:
                raise SystemExit(f"{element['id']}: cannot resolve variant {value!r}")
            options.append(matches[0])
    else:
        options = [a for a in library.values() if a.get("family") == family]
    return family, sorted(options, key=lambda a: a["id"])


def cmd_list(a):
    spec = load_spec(Path(a.spec).resolve())
    element = spec_element(spec, a.element)
    family, options = options_for(element, asset_map())
    if a.safe_only:
        options = [x for x in options if is_safe_asset(x)]
    if a.source_derived_only:
        options = [
            x for x in options
            if str(x.get("generation", {}).get("origin", "")).startswith("article_")
        ]
    print(f"{element['id']}: family={family}, options={len(options)}")
    current = element.get("asset_variant") or element.get("asset")
    for asset in options:
        mark = "*" if current in {asset["id"], asset.get("variant")} else " "
        print(f" {mark} {asset['id']:<42} {asset['name_zh']:<24} "
              f"origin={asset['generation']['origin']}")
    return 0


def cmd_preview(a):
    try:
        import cairosvg
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("variant preview needs cairosvg and Pillow") from exc
    spec_path = Path(a.spec).resolve()
    spec = load_spec(spec_path)
    element = spec_element(spec, a.element)
    family, options = options_for(element, asset_map())
    if a.safe_only:
        options = [x for x in options if is_safe_asset(x)]
    if a.source_derived_only:
        options = [
            x for x in options
            if str(x.get("generation", {}).get("origin", "")).startswith("article_")
        ]
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    for old in list(outdir.glob("cand_*.png")) + list(outdir.glob("cand_*.svg")):
        old.unlink(missing_ok=True)
    records = []
    tiles = []
    for idx, asset in enumerate(options, 1):
        cand = copy.deepcopy(spec)
        target = spec_element(cand, a.element)
        target.pop("asset", None)
        target["asset_family"] = family
        target["asset_variant"] = asset["id"]
        problems, _ = validate_spec(cand, a.safe_only, a.source_derived_only)
        if problems:
            raise SystemExit("candidate spec invalid: " + "; ".join(problems))
        svg, _ = render_spec(cand, a.safe_only)
        cid = f"cand_{idx:02d}"
        svg_path = outdir / f"{cid}.svg"
        png_path = outdir / f"{cid}.png"
        svg_path.write_text(svg, encoding="utf-8")
        width_px = round(spec["figure"]["canvas"]["width_mm"] / 25.4 * a.dpi)
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                         output_width=width_px)
        if not a.keep_svg:
            svg_path.unlink(missing_ok=True)
        records.append({
            "code": cid,
            "asset_id": asset["id"],
            "asset_variant": asset.get("variant"),
            "name_zh": asset["name_zh"],
            "origin": asset["generation"]["origin"],
            "safe": is_safe_asset(asset),
            "svg": str(svg_path) if a.keep_svg else None,
            "png": str(png_path),
        })
        with Image.open(png_path) as im:
            thumb = im.convert("RGB")
            thumb.thumbnail((360, 230))
            tiles.append((cid, asset, thumb.copy()))
    sheet_w, sheet_h = 760, math_ceil(len(tiles) / 2) * 300
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, (code, asset, thumb) in enumerate(tiles):
        x = (idx % 2) * 380
        y = (idx // 2) * 300
        sheet.paste(thumb, (x + 10, y + 8))
        draw.text((x + 12, y + 250), f"{code}  {asset['id']}", fill="#16212b")
        draw.text((x + 12, y + 268), f"{asset['name_zh']} | {asset['generation']['origin']}",
                  fill="#5b6874")
    sheet_path = outdir / "variant_sheet.png"
    sheet.save(sheet_path)
    data = {
        "schema": "hep-nature-figure/element-variants-v1",
        "spec": str(spec_path),
        "element_id": a.element,
        "family": family,
        "source_derived_only": bool(a.source_derived_only),
        "sheet": str(sheet_path),
        "candidates": records,
    }
    (outdir / "variants.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cards = []
    for r in records:
        cards.append(
            f'<article><img src="{html.escape(Path(r["png"]).name)}">'
            f'<h3>{html.escape(r["code"])} · {html.escape(r["asset_id"])}</h3>'
            f'<p>{html.escape(r["name_zh"])} · {html.escape(r["origin"])} · '
            f'safe={r["safe"]}</p></article>'
        )
    page = (
        "<!doctype html><meta charset='utf-8'><title>Element variants</title>"
        "<style>body{font:14px system-ui;background:#f5f7f8;margin:24px}"
        "main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}"
        "article{background:white;padding:12px;border-radius:10px}"
        "img{width:100%;height:auto;background:white}</style>"
        f"<h1>{html.escape(a.element)} · {html.escape(family)}</h1><main>{''.join(cards)}</main>"
    )
    (outdir / "pick.html").write_text(page, encoding="utf-8")
    print(json.dumps({"family": family, "options": len(records),
                      "sheet": str(sheet_path), "html": str(outdir / "pick.html")},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_record(a):
    spec_path = Path(a.spec).resolve()
    outdir = Path(a.outdir).resolve()
    data = json.loads((outdir / "variants.json").read_text(encoding="utf-8"))
    chosen = next((x for x in data["candidates"] if x["code"] == a.code), None)
    if not chosen:
        raise SystemExit(f"unknown candidate code: {a.code}")
    if a.by not in CLIENT_ROLES:
        raise SystemExit("--by must identify the client/author")
    if not a.reply.strip():
        raise SystemExit("--reply must preserve the client's original wording")
    doc = {
        **data,
        "selected": chosen,
        "selected_by": a.by,
        "reply": a.reply,
        "selected_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (outdir / "choice.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {a.code} -> {chosen['asset_id']}")
    return 0


def cmd_apply(a):
    spec_path = Path(a.spec).resolve()
    choice = json.loads(Path(a.choice).resolve().read_text(encoding="utf-8"))
    target_id = choice["element_id"]
    new_asset = choice["selected"]["asset_id"]
    lines = spec_path.read_text(encoding="utf-8").splitlines()
    start = None
    indent = None
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)-\s+id:\s*[\"']?([^\"']+)", line)
        if m and m.group(2).strip() == target_id:
            start = i
            indent = m.group(1)
            break
    if start is None:
        raise SystemExit(f"element {target_id} not found in YAML spec")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(rf"^{re.escape(indent)}-\s+id:", lines[j])
        if m:
            end = j
            break
    field_indent = indent + "  "
    found = False
    for j in range(start, end):
        if re.match(rf"^{re.escape(field_indent)}asset_variant:", lines[j]):
            lines[j] = f"{field_indent}asset_variant: {new_asset}"
            found = True
            break
    if not found:
        for j in range(start, end):
            if re.match(rf"^{re.escape(field_indent)}asset_family:", lines[j]):
                lines.insert(j + 1, f"{field_indent}asset_variant: {new_asset}")
                found = True
                break
    if not found:
        lines.insert(start + 1, f"{field_indent}asset_variant: {new_asset}")
    out = Path(a.out).resolve() if a.out else spec_path
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"applied {new_asset} to {target_id} -> {out}")
    print("Spec hash changed; rerun spec_confirm.py --record before final compile.")
    return 0


def math_ceil(v):
    return int(v) if int(v) == v else int(v) + 1


def build_parser():
    ap = argparse.ArgumentParser(description="Choose between visual variants in one element slot")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list")
    p.add_argument("--spec", required=True)
    p.add_argument("--element", required=True)
    p.add_argument("--safe-only", action="store_true")
    p.add_argument("--source-derived-only", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("preview")
    p.add_argument("--spec", required=True)
    p.add_argument("--element", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--safe-only", action="store_true")
    p.add_argument("--source-derived-only", action="store_true")
    p.add_argument("--dpi", type=int, default=180)
    p.add_argument("--keep-svg", action="store_true",
                   help="retain full candidate SVGs; default keeps only PNG previews")
    p.set_defaults(func=cmd_preview)
    p = sub.add_parser("record")
    p.add_argument("--spec", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--reply", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_record)
    p = sub.add_parser("apply")
    p.add_argument("--spec", required=True)
    p.add_argument("--choice", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_apply)
    return ap


def main():
    args = build_parser().parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
