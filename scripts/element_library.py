#!/usr/bin/env python3
"""Validate, search, and safely ingest vector elements.

The library API is intentionally stricter than a generic SVG folder:
  * every asset has a licence and generation provenance;
  * AI-origin assets are explicitly marked;
  * submission-safe mode admits only software/human vectors with no AI pixels;
  * embedded rasters, scripts, external references, and event handlers fail.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "element-library"
INDEX = LIB / "index.json"
GENERATED = LIB / "generated"
TODAY = "2026-11-22"
ALLOWED_LICENSES = {"MIT", "CC0-1.0", "CC-BY-4.0"}
SAFE_ORIGINS = {
    "software", "human_vector", "ai_assisted_redraw",
    "article_vector_native", "article_vector_trace",
}


def load_index() -> dict:
    if not INDEX.exists():
        raise SystemExit("element-library/index.json is missing")
    return json.loads(INDEX.read_text(encoding="utf-8"))


def save_index(doc: dict) -> None:
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def svg_security_errors(path: Path) -> list[str]:
    errors = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"invalid XML: {exc}"]
    if local_name(root.tag) != "svg":
        errors.append("root element is not <svg>")
    for node in root.iter():
        name = local_name(node.tag)
        if name in {"image", "script", "foreignObject"}:
            errors.append(f"forbidden <{name}>")
        for key, value in node.attrib.items():
            low_key = key.casefold()
            key_name = local_name(key).casefold()
            if low_key.startswith("on"):
                errors.append(f"forbidden event attribute {key}")
            if key_name in {"href", "xlink:href"} and not str(value).startswith("#"):
                errors.append(f"external reference in {key}")
            if "javascript:" in str(value).casefold():
                errors.append("javascript URL")
    if not root.get("viewBox"):
        width = root.get("width", "")
        height = root.get("height", "")
        if not width or not height:
            errors.append("missing viewBox/width/height")
    return errors


def is_safe_asset(asset: dict) -> bool:
    gen = asset.get("generation") or {}
    lic = asset.get("license") or {}
    review = asset.get("review") or {}
    return (
        str(gen.get("origin", "")) in SAFE_ORIGINS
        and not gen.get("ai_generated", True)
        and not gen.get("contains_ai_pixels", True)
        and bool(lic.get("redistributable"))
        and review.get("status") in {"verified", "reviewed", "manual-reviewed"}
        and bool(review.get("reviewed_by"))
    )


def cmd_validate(_args):
    doc = load_index()
    errors = []
    seen = set()
    for asset in doc.get("assets", []):
        aid = asset.get("id", "")
        if not aid:
            errors.append("asset with empty id")
            continue
        if aid in seen:
            errors.append(f"{aid}: duplicate id")
        seen.add(aid)
        for key in ("file", "license", "generation", "review", "sha256",
                    "physics_roles", "category", "viewBox", "family", "variant"):
            if key not in asset:
                errors.append(f"{aid}: missing {key}")
        if errors and errors[-1].startswith(f"{aid}: missing"):
            continue
        path = LIB / asset["file"]
        if not path.exists():
            errors.append(f"{aid}: missing file {path}")
            continue
        if sha256(path) != asset["sha256"]:
            errors.append(f"{aid}: sha256 mismatch")
        lic = asset["license"]
        if lic.get("spdx") not in ALLOWED_LICENSES:
            errors.append(f"{aid}: unmanaged licence {lic.get('spdx')}")
        if not lic.get("redistributable"):
            errors.append(f"{aid}: non-redistributable asset in library")
        if not str(lic.get("attribution") or "").strip():
            errors.append(f"{aid}: missing attribution")
        gen = asset["generation"]
        if "origin" not in gen or "ai_generated" not in gen:
            errors.append(f"{aid}: incomplete generation provenance")
        if str(gen.get("origin", "")).startswith("ai_"):
            if not str(gen.get("model") or "").strip():
                errors.append(f"{aid}: AI asset must record the model")
            if gen.get("origin") in {"ai_raster", "ai_generated_vector"} and not gen.get("prompt_sha256"):
                errors.append(f"{aid}: AI asset must record a prompt-file hash")
        if gen.get("origin") == "article_vector_trace":
            for key in ("source_asset_id", "source_local_file", "source_sha256",
                        "source_bbox_px", "crop_file", "crop_sha256"):
                if not gen.get(key):
                    errors.append(f"{aid}: article-derived asset missing {key}")
            if not lic.get("source_url"):
                errors.append(f"{aid}: article-derived asset missing source URL")
            crop_rel = gen.get("crop_file")
            if crop_rel:
                crop = LIB / crop_rel
                if not crop.exists():
                    errors.append(f"{aid}: missing source crop {crop_rel}")
                elif gen.get("crop_sha256") and sha256(crop) != gen["crop_sha256"]:
                    errors.append(f"{aid}: crop sha256 mismatch")
        if str(gen.get("origin", "")).startswith("article_vector_"):
            edit_rel = gen.get("edit_file")
            texture_rel = gen.get("texture_file")
            if not edit_rel:
                errors.append(f"{aid}: article-derived asset missing edit_file")
            elif asset["file"] != edit_rel:
                errors.append(
                    f"{aid}: default file must be editable native SVG, not {asset['file']}"
                )
            if not texture_rel:
                errors.append(f"{aid}: article-derived asset missing texture_file")
            for label, rel in (("edit", edit_rel), ("texture", texture_rel)):
                if not rel:
                    continue
                paired = LIB / rel
                if not paired.exists():
                    errors.append(f"{aid}: missing paired {label} file {rel}")
                    continue
                expected_hash = gen.get(f"{label}_sha256")
                if expected_hash and sha256(paired) != expected_hash:
                    errors.append(f"{aid}: paired {label} sha256 mismatch")
                for problem in svg_security_errors(paired):
                    errors.append(f"{aid} {label}: {problem}")
        review = asset["review"]
        if not review.get("reviewed_by") or not review.get("reviewed_at"):
            errors.append(f"{aid}: missing element review record")
        if not asset.get("physics_roles"):
            errors.append(f"{aid}: missing physics_roles")
        if len(asset.get("viewBox") or []) != 4:
            errors.append(f"{aid}: viewBox must have four numbers")
        for problem in svg_security_errors(path):
            errors.append(f"{aid}: {problem}")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"PASS: {len(doc.get('assets', []))} vector elements")
    return 0


def _match(asset: dict, args) -> bool:
    terms = (args.q or "").casefold().split()
    blob = " ".join([
        asset.get("id", ""), asset.get("name_zh", ""), asset.get("category", ""),
        *asset.get("aliases", []), *asset.get("tags", []),
        *asset.get("physics_roles", []),
    ]).casefold()
    if terms and not all(term in blob for term in terms):
        return False
    if args.tag and not set(args.tag).issubset(set(asset.get("tags", []))):
        return False
    if args.family and asset.get("family") != args.family:
        return False
    if args.category and asset.get("category") != args.category:
        return False
    if getattr(args, "origin", None):
        origin = (asset.get("generation") or {}).get("origin")
        if args.origin.endswith("*"):
            if not str(origin or "").startswith(args.origin[:-1]):
                return False
        elif origin != args.origin:
            return False
    if args.safe_only and not is_safe_asset(asset):
        return False
    return True


def cmd_list(args):
    doc = load_index()
    found = [a for a in doc["assets"] if _match(a, args)]
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    for a in found[:args.limit]:
        safe = "SAFE" if is_safe_asset(a) else "AI"
        print(f"- {a['id']} | family={a.get('family', '-')} | variant={a.get('variant', '-')} "
              f"| {a['category']} | {a['dimensionality']} | {safe}")
        print(f"  {a['name_zh']} | {', '.join(a['physics_roles'][:3])}")
        if (a.get("generation") or {}).get("source_quality_note"):
            print(f"  quality: {a['generation']['source_quality_note']}")
        print(f"  {a['file']}")
    return 0


def cmd_show(args):
    doc = load_index()
    asset = next((a for a in doc["assets"] if a["id"] == args.id), None)
    if not asset:
        raise SystemExit(f"unknown element asset: {args.id}")
    print(json.dumps(asset, ensure_ascii=False, indent=2))
    return 0


def cmd_sheet(args):
    try:
        import cairosvg
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("contact sheets require cairosvg and Pillow") from exc
    doc = load_index()
    found = [a for a in doc["assets"] if _match(a, args)]
    if not found:
        raise SystemExit("no matching assets")
    cols = max(1, args.cols)
    cell_w, cell_h = 220, 210
    rows = math.ceil(len(found) / cols)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, asset in enumerate(found):
        path = LIB / asset["file"]
        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=150,
                               output_height=150, background_color="white")
        tile = Image.open(io.BytesIO(png)).convert("RGB")
        x = (idx % cols) * cell_w
        y = (idx // cols) * cell_h
        sheet.paste(tile, (x + 35, y + 12))
        label = asset["id"].replace("_", " ")
        draw.text((x + 8, y + 172), label[:34], fill="#17212b")
        draw.text((x + 8, y + 188), asset.get("variant", "")[:34], fill="#607080")
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"wrote {len(found)} assets -> {out}")
    return 0


def _sanitize_svg(src: Path, dst: Path, asset_id: str) -> tuple[float, float, float, float]:
    root = ET.parse(src).getroot()
    for parent in root.iter():
        for child in list(parent):
            if local_name(child.tag) in {"image", "script", "foreignObject"}:
                parent.remove(child)
    for node in root.iter():
        for key in list(node.attrib):
            if key.casefold().startswith("on"):
                del node.attrib[key]
            elif local_name(key).casefold() in {"href", "xlink:href"} and not str(node.attrib[key]).startswith("#"):
                del node.attrib[key]
    vb = root.get("viewBox")
    if vb:
        parts = [float(x) for x in re.split(r"[\s,]+", vb.strip())]
        if len(parts) != 4:
            raise ValueError("invalid viewBox")
    else:
        width = re.match(r"[0-9.]+", root.get("width", "100"))
        height = re.match(r"[0-9.]+", root.get("height", "100"))
        if not width or not height:
            raise ValueError("SVG has neither viewBox nor numeric width/height")
        parts = [0.0, 0.0, float(width.group(0)), float(height.group(0))]
        root.set("viewBox", " ".join(f"{x:g}" for x in parts))
    root.set("width", f"{parts[2]:g}")
    root.set("height", f"{parts[3]:g}")
    root.set("data-element-asset", asset_id)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(dst, encoding="utf-8", xml_declaration=True)
    return tuple(parts)


def _png_to_svg(src: Path, dst: Path) -> None:
    try:
        from PIL import Image
        import vtracer
    except ImportError as exc:
        raise SystemExit("PNG ingestion needs Pillow and vtracer") from exc
    im = Image.open(src).convert("RGBA")
    alpha = im.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        raise SystemExit("input PNG is fully transparent")
    im = im.crop(bbox)
    cleaned = dst.with_suffix(".source.png")
    cleaned.parent.mkdir(parents=True, exist_ok=True)
    im.save(cleaned)
    try:
        vtracer.convert_image_to_svg_py(
            str(cleaned), str(dst), colormode="color", hierarchical="stacked",
            mode="spline", filter_speckle=3,
            color_precision=8, layer_difference=6,
            corner_threshold=80, length_threshold=3.0,
            max_iterations=10, splice_threshold=45,
            path_precision=3,
        )
    except Exception as exc:
        raise SystemExit(f"vtracer failed: {exc}") from exc


def cmd_ingest_ai(args):
    if args.origin in SAFE_ORIGINS and args.origin != "ai_assisted_redraw":
        raise SystemExit("ingest-ai requires an AI origin")
    if not args.reviewer:
        raise SystemExit("--reviewer is required")
    if args.origin == "ai_assisted_redraw" and args.source.suffix.lower() != ".svg":
        raise SystemExit("ai_assisted_redraw must already be a vector SVG")
    if args.origin in {"ai_raster", "ai_generated_vector"} and not args.prompt_file:
        raise SystemExit("AI-origin assets require --prompt-file for provenance")
    doc = load_index()
    existing = next((a for a in doc["assets"] if a["id"] == args.id), None)
    if existing and not args.replace:
        raise SystemExit(f"{args.id} already exists; use --replace")
    GENERATED.mkdir(parents=True, exist_ok=True)
    dst = GENERATED / f"{args.id}.svg"
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"source not found: {source}")
    if source.suffix.lower() == ".png":
        _png_to_svg(source, dst)
    elif source.suffix.lower() == ".svg":
        shutil.copyfile(source, dst)
    else:
        raise SystemExit("source must be .png or .svg")
    vb = _sanitize_svg(dst, dst, args.id)
    problems = svg_security_errors(dst)
    if problems:
        raise SystemExit("ingested SVG failed security checks: " + "; ".join(problems))
    prompt_sha = sha256(Path(args.prompt_file).expanduser().resolve()) if args.prompt_file else None
    contains_ai_pixels = args.origin in {"ai_raster", "ai_generated_vector"}
    asset = {
        "id": args.id,
        "version": "1.0.0",
        "family": args.family or args.id,
        "variant": args.variant or "custom",
        "variant_description": args.variant_description or "custom supplied vector",
        "name_zh": args.name_zh,
        "aliases": args.alias or [args.id.replace("_", " ")],
        "category": args.category,
        "tags": args.tag or ["ai", args.category],
        "physics_roles": args.physics_role or [args.name_zh],
        "file": dst.relative_to(LIB).as_posix(),
        "viewBox": list(vb),
        "anchor": [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2],
        "dimensionality": args.dimensionality,
        "license": {
            "spdx": args.license,
            "redistributable": True,
            "attribution": args.attribution or f"AI-assisted asset supplied by {args.reviewer}",
        },
        "generation": {
            "origin": args.origin,
            "ai_generated": False if args.origin == "ai_assisted_redraw" else True,
            "contains_ai_pixels": contains_ai_pixels,
            "tool": args.tool,
            "model": args.model,
            "prompt_sha256": prompt_sha,
            "source_uri": args.source_uri,
        },
        "review": {
            "status": "reviewed",
            "reviewed_by": args.reviewer,
            "reviewed_at": TODAY,
            "note": args.review_note or "",
        },
        "sha256": sha256(dst),
    }
    assets = [a for a in doc["assets"] if a["id"] != args.id]
    assets.append(asset)
    doc["assets"] = sorted(assets, key=lambda a: a["id"])
    doc["updated"] = TODAY
    save_index(doc)
    print(f"registered {args.id} ({args.origin}, safe={is_safe_asset(asset)})")
    return 0


def asset_map(doc: dict | None = None) -> dict:
    doc = doc or load_index()
    return {a["id"]: a for a in doc["assets"]}


def build_parser():
    ap = argparse.ArgumentParser(description="HEP element-level vector library")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("validate")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("list")
    p.add_argument("--q", default="")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--category")
    p.add_argument("--family")
    p.add_argument("--origin")
    p.add_argument("--safe-only", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("show")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("sheet")
    p.add_argument("--out", required=True)
    p.add_argument("--q", default="")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--category")
    p.add_argument("--family")
    p.add_argument("--origin")
    p.add_argument("--safe-only", action="store_true")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(func=cmd_sheet, json=False)
    p = sub.add_parser("ingest-ai")
    p.add_argument("--id", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--name-zh", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--family")
    p.add_argument("--variant")
    p.add_argument("--variant-description")
    p.add_argument("--license", required=True, choices=sorted(ALLOWED_LICENSES))
    p.add_argument("--origin", required=True,
                   choices=["ai_raster", "ai_generated_vector", "ai_assisted_redraw"])
    p.add_argument("--tool", default="unknown image generator")
    p.add_argument("--model", default="")
    p.add_argument("--prompt-file")
    p.add_argument("--source-uri", default="")
    p.add_argument("--attribution", default="")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--review-note", default="")
    p.add_argument("--dimensionality", choices=["3d", "mixed", "flat"], default="3d")
    p.add_argument("--alias", action="append", default=[])
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--physics-role", action="append", default=[])
    p.add_argument("--replace", action="store_true")
    p.set_defaults(func=cmd_ingest_ai)
    return ap


def main():
    args = build_parser().parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
