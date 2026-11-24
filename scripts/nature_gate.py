#!/usr/bin/env python3
"""Check compiled SVG/PNG/PDF against the Nature schematic profile."""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "assets" / "spec-profiles" / "nature-2026.json"
PT_TO_MM = 25.4 / 72.0


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_number(value):
    if value is None:
        return None
    m = re.search(r"[-+]?[0-9]*\.?[0-9]+", str(value))
    return float(m.group(0)) if m else None


def parse_hex(color):
    c = color.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return tuple(int(x * 2, 16) for x in c[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
    return None


def color_family(color: str) -> str:
    rgb = parse_hex(color)
    if rgb is None:
        return "named-or-invalid"
    if max(rgb) - min(rgb) < 14:
        return "neutral"
    r, g, b = (x / 255.0 for x in rgb)
    h, _, _ = colorsys.rgb_to_hsv(r, g, b)
    deg = h * 360
    if deg < 15 or deg >= 345:
        return "red"
    if deg < 45:
        return "orange"
    if deg < 65:
        return "amber"
    if deg < 165:
        return "green"
    if deg < 210:
        return "cyan"
    if deg < 265:
        return "blue"
    if deg < 300:
        return "violet"
    return "magenta"


def main():
    ap = argparse.ArgumentParser(description="Nature profile gate")
    ap.add_argument("svg")
    ap.add_argument("--spec")
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--manifest")
    ap.add_argument("--safe-mode", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    errors, warnings, readings = [], [], {}
    root = ET.parse(a.svg).getroot()
    if local_name(root.tag) != "svg":
        raise SystemExit("not an SVG document")
    width_text, height_text = root.get("width", ""), root.get("height", "")
    width = parse_number(width_text)
    height = parse_number(height_text)
    if width is None or height is None or "mm" not in width_text or "mm" not in height_text:
        errors.append("SVG width/height must be explicit millimetres")
    elif width not in profile["canvas"]["widths_mm"]:
        errors.append(f"canvas width {width:g} mm is not {profile['canvas']['widths_mm']}")
    if height is not None and height > profile["canvas"]["max_height_mm"]:
        errors.append(f"canvas height {height:g} mm exceeds {profile['canvas']['max_height_mm']}")
    readings["canvas_mm"] = [width, height]

    vb = [float(x) for x in re.split(r"[\s,]+", root.get("viewBox", "").strip())]
    if len(vb) != 4:
        errors.append("missing/invalid viewBox")
        vb = [0, 0, width or 1, height or 1]
    mm_per_unit_x = (width or vb[2]) / vb[2]

    for node in root.iter():
        name = local_name(node.tag)
        if name in {"script", "foreignObject"}:
            errors.append(f"forbidden <{name}>")
        if name == "image":
            msg = "embedded raster <image>"
            (errors if a.safe_mode else warnings).append(msg)
        for key, value in node.attrib.items():
            low = key.casefold()
            key_name = local_name(key).casefold()
            if low.startswith("on") or "javascript:" in str(value).casefold():
                errors.append(f"unsafe attribute/value: {key}")
            if key_name in {"href", "xlink:href"} and not str(value).startswith("#"):
                errors.append(f"external reference: {value}")
        if name == "g" and str(node.get("data-ai-generated", "")).casefold() == "true" and a.safe_mode:
            errors.append(f"AI-origin group in safe mode: {node.get('data-element-id', '?')}")

    fonts = profile["typography"]["allowed_families"]
    font_sizes = []
    for node in root.iter():
        if local_name(node.tag) != "text":
            continue
        family = node.get("font-family") or node.get("style", "")
        if family and not any(f in family for f in fonts):
            errors.append(f"font family outside profile: {family}")
        size_pt = node.get("data-font-size-pt")
        if size_pt is not None:
            try:
                pt = float(size_pt)
                font_sizes.append(pt)
                if pt < profile["typography"]["font_size_pt_min"]:
                    errors.append(f"text {node.get('data-text-id', '?')} font {pt:g} pt below profile")
                if pt > profile["typography"]["font_size_pt_max"]:
                    warnings.append(f"text {node.get('data-text-id', '?')} font {pt:g} pt above profile")
            except ValueError:
                errors.append("invalid data-font-size-pt")
    readings["font_size_pt"] = {
        "count": len(font_sizes),
        "min": min(font_sizes) if font_sizes else None,
        "max": max(font_sizes) if font_sizes else None,
    }

    line_widths = []
    for node in root.iter():
        if not node.get("data-connection-id"):
            continue
        raw = node.get("stroke-width")
        value = parse_number(raw)
        if value is None:
            errors.append(f"connection {node.get('data-connection-id')} lacks stroke-width")
            continue
        pt = value * mm_per_unit_x / PT_TO_MM
        line_widths.append(pt)
        if pt < profile["lines"]["min_pt"]:
            errors.append(f"connection line {pt:.2f} pt below profile")
        if pt > profile["lines"]["max_pt"]:
            errors.append(f"connection line {pt:.2f} pt above profile")
    readings["line_width_pt"] = {
        "count": len(line_widths),
        "min": min(line_widths) if line_widths else None,
        "max": max(line_widths) if line_widths else None,
    }

    families = set()
    for node in root.iter():
        for key in ("fill", "stroke", "stop-color"):
            color = node.get(key)
            if not color or color in {"none", "transparent"} or color.startswith("url("):
                continue
            family = color_family(color)
            if family == "named-or-invalid":
                errors.append(f"non-hex colour outside controlled palette: {color}")
            else:
                families.add(family)
    allowed = set(profile["palette"]["allowed_families"])
    bad = families - allowed
    if bad:
        errors.append(f"palette hue families outside profile: {sorted(bad)}")
    chromatic = families - {"neutral"}
    if len(chromatic) > profile["palette"]["max_chromatic_families"]:
        warnings.append(f"{len(chromatic)} chromatic hue families exceeds profile guidance")
    readings["palette_families"] = sorted(families)

    if a.png:
        try:
            from PIL import Image
            with Image.open(a.png) as im:
                dpi = profile["raster"]["min_combination_dpi"]
                expected = round((width or 183) / 25.4 * dpi)
                readings["png"] = {"size": list(im.size), "expected_width_600dpi": expected}
                if im.width < expected * 0.98:
                    errors.append(f"PNG width {im.width}px below 600 dpi target {expected}px")
        except Exception as exc:
            errors.append(f"PNG check failed: {exc}")
    if a.pdf and not Path(a.pdf).exists():
        errors.append("PDF output is missing")

    report = {
        "schema": "hep-nature-figure/nature-gate-v1",
        "profile": profile["profile_id"],
        "safe_mode": bool(a.safe_mode),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "readings": readings,
    }
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    if a.manifest:
        mp = Path(a.manifest)
        if mp.exists():
            manifest = json.loads(mp.read_text(encoding="utf-8"))
            manifest["nature_gate"] = report
            mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    print("=" * 72)
    print(f"nature_gate -- {PROFILE.name} ({'safe' if a.safe_mode else 'standard'})")
    print("=" * 72)
    print(f"  canvas       {width} x {height} mm")
    print(f"  fonts        {readings['font_size_pt']}")
    print(f"  lines        {readings['line_width_pt']}")
    print(f"  palette      {', '.join(sorted(families)) or '-'}")
    for warning in warnings:
        print(f"  warn  {warning}")
    if errors:
        print(f"  RESULT FAIL ({len(errors)})")
        for error in errors:
            print(f"    - {error}")
        return 1
    print("  RESULT PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
