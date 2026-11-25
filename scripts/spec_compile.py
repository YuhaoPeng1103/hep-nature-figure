#!/usr/bin/env python3
"""Compile a confirmed element-level figure spec into SVG/PDF/PNG.

This is the production compiler for the v5.1 element library:
spec -> confirmation -> asset resolution -> deterministic SVG assembly ->
Nature profile gate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from element_library import asset_map, is_safe_asset, load_index, svg_security_errors  # noqa: E402
from spec_confirm import canonical_hash, cmd_check, load_spec, receipt_path, summary  # noqa: E402

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
PT_TO_MM = 25.4 / 72.0
ANCHORS = {"center", "left", "right", "top", "bottom"}


def q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def length_mm(value, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().lower()
    m = re.fullmatch(r"([0-9.]+)\s*(mm|cm|in|pt|px)?", text)
    if not m:
        raise ValueError(f"{field} must be a number with optional mm/cm/in/pt: {value!r}")
    amount = float(m.group(1))
    unit = m.group(2) or "mm"
    return amount * {"mm": 1, "cm": 10, "in": 25.4, "pt": PT_TO_MM, "px": 0.264583}[unit]


def ids_unique(spec: dict) -> list[str]:
    errors = []
    seen = set()
    for key in ("elements", "texts", "connections", "relationships", "hard_physics"):
        for row in spec.get(key) or []:
            eid = str(row.get("id") or "")
            if not eid:
                errors.append(f"{key}: entry without id")
            elif eid in seen:
                errors.append(f"duplicate id: {eid}")
            seen.add(eid)
    return errors


def validate_spec(spec: dict, safe_mode: bool,
                  source_derived_only: bool = False) -> tuple[list[str], dict]:
    errors = ids_unique(spec)
    warnings = []
    fig = spec.get("figure") or {}
    if not str(fig.get("physics_claim") or "").strip():
        errors.append("figure.physics_claim is required")
    canvas = fig.get("canvas") or {}
    try:
        width = length_mm(canvas.get("width_mm"), "figure.canvas.width_mm")
        height = length_mm(canvas.get("height_mm"), "figure.canvas.height_mm")
    except ValueError as exc:
        errors.append(str(exc))
        width, height = 1.0, 1.0
    if width <= 0 or height <= 0:
        errors.append("canvas dimensions must be positive")
    target = str(fig.get("target_journal") or fig.get("target") or "Nature")
    if target.casefold() == "nature":
        if abs(width - 89) > 0.5 and abs(width - 183) > 0.5:
            errors.append("Nature canvas width must be 89 mm (single) or 183 mm (double)")
        if height > 247:
            errors.append("Nature canvas height exceeds 247 mm")
    style = spec.get("style") or {}
    if style.get("mode") != "render3d":
        errors.append("style.mode must be render3d")
    if not str(style.get("classification") or "").strip():
        errors.append("style.classification is required")
    if not str(style.get("evidence") or "").strip():
        errors.append("style.evidence is required")
    comp = spec.get("composition") or {}
    proj = comp.get("projection") or {}
    if not proj.get("type"):
        errors.append("composition.projection.type is required")
    if "perspect" in str(proj.get("type", "")).casefold():
        errors.append("perspective projection is not allowed")
    coord = comp.get("coordinates") or comp.get("坐标约定") or {}
    if (coord.get("handedness") or coord.get("手性")) not in {"right", "右手"}:
        errors.append("composition.coordinates.handedness must be right/右手")
    beam = coord.get("beam_axis") or coord.get("束流轴")
    if not beam:
        errors.append("composition.coordinates.beam_axis is required (use 'none' if absent)")

    elements = spec.get("elements") or []
    if not elements:
        errors.append("elements is empty")
    library = asset_map()
    three_d_count = 0
    for e in elements:
        eid = e.get("id", "?")
        asset = resolve_element_asset(e, library)
        if not asset:
            requested = (
                f"{e.get('asset_family')}/{e.get('asset_variant')}"
                if e.get("asset_family") else e.get("asset")
            )
            errors.append(f"{eid}: unresolved element asset {requested!r}")
            continue
        if safe_mode and not is_safe_asset(asset):
            errors.append(f"{eid}: asset {asset['id']} is AI/non-safe and is excluded by safe mode")
        if source_derived_only and not str(asset.get("generation", {}).get("origin", "")).startswith("article_"):
            errors.append(f"{eid}: asset {asset['id']} is a system primitive, not source-derived")
        for option in e.get("variant_options") or []:
            candidate = next(
                (a for a in library.values()
                 if a.get("family") == e.get("asset_family")
                 and (a["id"] == option or a.get("variant") == option)),
                None,
            )
            if not candidate:
                errors.append(
                    f"{eid}: variant option {option!r} is not in family "
                    f"{e.get('asset_family')!r}")
        if asset.get("dimensionality") in {"3d", "mixed"}:
            three_d_count += 1
        if not str(e.get("physics_role") or "").strip():
            errors.append(f"{eid}: physics_role is required")
        try:
            length_mm(e.get("x_mm"), f"{eid}.x_mm")
            length_mm(e.get("y_mm"), f"{eid}.y_mm")
            length_mm(e.get("width_mm"), f"{eid}.width_mm")
            length_mm(e.get("height_mm"), f"{eid}.height_mm")
        except ValueError as exc:
            errors.append(str(exc))
        if str(e.get("fit", "contain")).casefold() not in {"contain", "stretch"}:
            errors.append(f"{eid}: fit must be contain or stretch")
    if three_d_count == 0:
        errors.append("at least one 3D/mixed vector element is required")

    hard = spec.get("hard_physics") or []
    if not hard:
        errors.append("hard_physics is empty")
    for hp in hard:
        if not str(hp.get("claim") or "").strip():
            errors.append(f"{hp.get('id', '?')}: hard physics claim is empty")
        if not str(hp.get("measure") or "").strip():
            errors.append(f"{hp.get('id', '?')}: hard physics needs a measurable criterion")
        if hp.get("verification") not in {"machine", "human"}:
            errors.append(f"{hp.get('id', '?')}: verification must be machine or human")

    known_ids = {e.get("id") for e in elements}
    for rel in spec.get("relationships") or []:
        for key in ("subject", "object"):
            if rel.get(key) not in known_ids:
                errors.append(f"{rel.get('id', '?')}: {key} references unknown element {rel.get(key)!r}")
        if not rel.get("type"):
            errors.append(f"{rel.get('id', '?')}: relationship type is required")

    for text in spec.get("texts") or []:
        if not str(text.get("value", text.get("text", ""))).strip():
            errors.append(f"{text.get('id', '?')}: text value is empty")
        try:
            length_mm(text.get("x_mm"), f"{text.get('id')}.x_mm")
            length_mm(text.get("y_mm"), f"{text.get('id')}.y_mm")
            size = float(text.get("font_size_pt", 7))
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
            size = 7
        if size < 5:
            errors.append(f"{text.get('id', '?')}: font size {size} pt is below Nature 5 pt")
        if size > 12:
            warnings.append(f"{text.get('id', '?')}: font size {size} pt is outside the 5-12 pt profile")

    for con in spec.get("connections") or []:
        ctype = con.get("type")
        if ctype not in {"line", "arrow", "double_arrow", "elbow", "freeform"}:
            errors.append(f"{con.get('id', '?')}: unsupported connection type {ctype!r}")
        if ctype != "freeform":
            for key in ("from", "to"):
                ref = con.get(key)
                ref_id = ref.get("element") if isinstance(ref, dict) else ref
                if ref_id and ref_id not in known_ids:
                    errors.append(f"{con.get('id', '?')}: {key} references unknown element {ref_id!r}")
        if ctype == "freeform" and len(con.get("points") or []) < 2:
            errors.append(f"{con.get('id', '?')}: freeform needs at least two points")

    metrics = {
        "figure_id": fig.get("id") or "figure",
        "canvas_mm": [width, height],
        "target": target,
        "elements": len(elements),
        "three_d_elements": three_d_count,
        "texts": len(spec.get("texts") or []),
        "connections": len(spec.get("connections") or []),
        "hard_physics": len(hard),
        "safe_mode": safe_mode,
        "source_derived_only": source_derived_only,
    }
    return errors, metrics


def evaluate_physics(spec: dict) -> tuple[list[str], list[dict]]:
    """Execute the supported machine checks and retain human-review items."""
    errors = []
    results = []
    elements = {e["id"]: e for e in spec.get("elements") or []}
    for hp in spec.get("hard_physics") or []:
        hid = hp.get("id", "?")
        verification = hp.get("verification")
        if verification == "human":
            results.append({"id": hid, "status": "human-review", "note": hp.get("note", "")})
            continue
        check = hp.get("check") or {}
        ctype = check.get("type")
        try:
            origin = element_center(elements[check["origin"]])
            a = element_center(elements[check["a"]])
            b = element_center(elements[check["b"]])
        except KeyError as exc:
            errors.append(f"{hid}: machine check references unknown element {exc}")
            continue
        va = (a[0] - origin[0], a[1] - origin[1])
        vb = (b[0] - origin[0], b[1] - origin[1])
        la = math.hypot(*va)
        lb = math.hypot(*vb)
        if la == 0 or lb == 0:
            errors.append(f"{hid}: zero-length physical vector")
            continue
        dot = (va[0] * vb[0] + va[1] * vb[1]) / (la * lb)
        if ctype == "opposite_rays":
            ok = dot < float(check.get("max_cos", 0.0))
            results.append({"id": hid, "status": "pass" if ok else "fail",
                            "type": ctype, "cosine": round(dot, 6)})
            if not ok:
                errors.append(f"{hid}: rays are not opposite (cos={dot:.3f})")
        elif ctype == "angle_between_rays":
            angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
            lo = float(check.get("min_deg", 0))
            hi = float(check.get("max_deg", 180))
            ok = lo <= angle <= hi
            results.append({"id": hid, "status": "pass" if ok else "fail",
                            "type": ctype, "angle_deg": round(angle, 3)})
            if not ok:
                errors.append(f"{hid}: angle {angle:.1f} deg outside [{lo:g}, {hi:g}]")
        elif ctype == "distance_ratio":
            da = math.dist(origin, a)
            db = math.dist(origin, b)
            ratio = da / db if db else float("inf")
            minimum = float(check.get("min_ratio", 1.0))
            ok = ratio >= minimum
            results.append({"id": hid, "status": "pass" if ok else "fail",
                            "type": ctype, "ratio": round(ratio, 6)})
            if not ok:
                errors.append(f"{hid}: distance ratio {ratio:.3f} < {minimum:g}")
        else:
            errors.append(f"{hid}: unsupported machine check type {ctype!r}")
    return errors, results


def evaluate_layout(spec: dict) -> tuple[list[str], list[dict]]:
    """Check the declared composition regions and alignment assumptions."""
    layout = (spec.get("composition") or {}).get("layout") or {}
    if not layout:
        return [], []
    errors = []
    results = []
    elements = {e["id"]: e for e in spec.get("elements") or []}
    for region in layout.get("regions") or []:
        rid = region.get("id", "?")
        x_range = region.get("x_range_mm") or []
        y_range = region.get("y_range_mm") or []
        missing = [eid for eid in region.get("objects") or [] if eid not in elements]
        if missing:
            errors.append(f"layout {rid}: unknown elements {missing}")
            continue
        if len(x_range) != 2 or len(y_range) != 2:
            errors.append(f"layout {rid}: ranges must contain two numbers")
            continue
        outside = []
        for eid in region.get("objects") or []:
            x, y = element_center(elements[eid])
            if not (float(x_range[0]) <= x <= float(x_range[1])
                    and float(y_range[0]) <= y <= float(y_range[1])):
                outside.append(eid)
        if outside:
            errors.append(f"layout {rid}: outside declared region {outside}")
        else:
            results.append({"id": rid, "status": "pass"})

    alignment = layout.get("alignment") or {}
    if alignment.get("incoming_axis") == "horizontal":
        ids = alignment.get("incoming_objects") or []
        if len(ids) >= 2 and all(eid in elements for eid in ids[:2]):
            a = element_center(elements[ids[0]])
            b = element_center(elements[ids[1]])
            if abs(a[1] - b[1]) > 1.0:
                errors.append("layout alignment: incoming objects are not horizontal")
            else:
                results.append({"id": "incoming-horizontal", "status": "pass"})
    centre_id = alignment.get("incoming_symmetry_about")
    ids = alignment.get("incoming_objects") or []
    if centre_id in elements and len(ids) >= 2 and all(eid in elements for eid in ids[:2]):
        centre = element_center(elements[centre_id])
        a = element_center(elements[ids[0]])
        b = element_center(elements[ids[1]])
        if abs((a[0] - centre[0]) + (b[0] - centre[0])) > 1.5 \
                or abs((a[1] - centre[1]) + (b[1] - centre[1])) > 1.5:
            errors.append("layout alignment: incoming objects are not symmetric about medium")
        else:
            results.append({"id": "incoming-symmetric", "status": "pass"})
    if alignment.get("jets") == "back_to_back_about_vertex":
        origin_id = alignment.get("jet_origin")
        ids = alignment.get("jet_objects") or []
        if origin_id in elements and len(ids) >= 2 and all(eid in elements for eid in ids[:2]):
            origin = element_center(elements[origin_id])
            a = element_center(elements[ids[0]])
            b = element_center(elements[ids[1]])
            va = (a[0] - origin[0], a[1] - origin[1])
            vb = (b[0] - origin[0], b[1] - origin[1])
            na = math.hypot(*va)
            nb = math.hypot(*vb)
            if na == 0 or nb == 0:
                errors.append("layout alignment: zero-length jet direction")
            else:
                angle = math.degrees(math.acos(max(
                    -1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / (na * nb))
                )))
                if not 150 <= angle <= 210:
                    errors.append(
                        f"layout alignment: jets are not back-to-back ({angle:.1f} deg)"
                    )
                else:
                    results.append({"id": "jets-back-to-back", "status": "pass"})
    if alignment.get("labels") == "outside_object_bbox":
        boxes = []
        for element in elements.values():
            x, y = element_center(element)
            w = length_mm(element["width_mm"], "width_mm")
            h = length_mm(element["height_mm"], "height_mm")
            boxes.append((element["id"], x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        for text in spec.get("texts") or []:
            tx = length_mm(text["x_mm"], "x_mm")
            ty = length_mm(text["y_mm"], "y_mm")
            inside = [
                eid for eid, x0, y0, x1, y1 in boxes
                if x0 <= tx <= x1 and y0 <= ty <= y1
            ]
            if inside:
                errors.append(
                    f"layout labels: {text.get('id')} overlaps physical elements {inside}"
                )
        if not any(str(error).startswith("layout labels") for error in errors):
            results.append({"id": "labels-outside-objects", "status": "pass"})
    return errors, results


def _namespace_markup(root, prefix: str) -> None:
    mapping = {}
    for node in root.iter():
        old = node.get("id")
        if old:
            new = f"{prefix}{old}"
            mapping[old] = new
            node.set("id", new)
    if not mapping:
        return
    local_reference = re.compile(r"(?<=#)([A-Za-z_][A-Za-z0-9_.:-]*)")
    for node in root.iter():
        for key, value in list(node.attrib.items()):
            node.set(
                key,
                local_reference.sub(
                    lambda match: mapping.get(match.group(1), match.group(1)),
                    str(value),
                ),
            )


def load_asset_svg(path: Path, prefix: str):
    problems = svg_security_errors(path)
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    root = ET.parse(path).getroot()
    view_box = root.get("viewBox")
    if not view_box:
        wm = re.match(r"[0-9.]+", root.get("width", ""))
        hm = re.match(r"[0-9.]+", root.get("height", ""))
        if not wm or not hm:
            raise ValueError("asset SVG lacks both viewBox and numeric width/height")
        view_box = f"0 0 {wm.group(0)} {hm.group(0)}"
        root.set("viewBox", view_box)
    vb = [float(x) for x in re.split(r"[\s,]+", view_box)]
    _namespace_markup(root, prefix)
    defs = []
    body = []
    for child in list(root):
        name = local_name(child.tag)
        if name == "defs":
            defs.extend(list(child))
        elif name not in {"title", "desc", "metadata"}:
            body.append(child)
    defs_xml = "".join(ET.tostring(x, encoding="unicode") for x in defs)
    body_xml = "".join(ET.tostring(x, encoding="unicode") for x in body)
    return vb, defs_xml, body_xml


def element_center(element: dict) -> tuple[float, float]:
    return length_mm(element["x_mm"], "x_mm"), length_mm(element["y_mm"], "y_mm")


def resolve_element_asset(element: dict, library: dict) -> dict | None:
    """Resolve a fixed asset ID or a semantic family+variant slot."""
    family = element.get("asset_family")
    variant = element.get("asset_variant")
    if family:
        candidates = [a for a in library.values() if a.get("family") == family]
        if variant:
            candidates = [
                a for a in candidates
                if a["id"] == variant or a.get("variant") == variant
            ]
        return candidates[0] if len(candidates) == 1 else None
    aid = element.get("asset")
    return library.get(aid) if aid else None


def anchor_point(element: dict, anchor: str, library: dict) -> tuple[float, float]:
    x, y = element_center(element)
    w = length_mm(element["width_mm"], "width_mm")
    h = length_mm(element["height_mm"], "height_mm")
    anchor = anchor or "center"
    if anchor not in ANCHORS:
        raise ValueError(f"{element.get('id')}: unknown anchor {anchor}")
    return {
        "center": (x, y),
        "left": (x - w / 2, y),
        "right": (x + w / 2, y),
        "top": (x, y - h / 2),
        "bottom": (x, y + h / 2),
    }[anchor]


def resolve_endpoint(ref, elements: dict, offset, field: str) -> tuple[float, float]:
    if isinstance(ref, str):
        ref = {"element": ref}
    if not isinstance(ref, dict):
        raise ValueError(f"{field}: expected element id or anchor object")
    eid = ref.get("element")
    if eid not in elements:
        raise ValueError(f"{field}: unknown element {eid}")
    px, py = anchor_point(elements[eid], ref.get("anchor", "center"), {})
    dx, dy = offset or [0, 0]
    return px + float(dx), py + float(dy)


def layout_guide_markup(spec: dict) -> tuple[str, str]:
    """Render non-physical alignment guides declared by the IR."""
    layout = (spec.get("composition") or {}).get("layout") or {}
    guides = layout.get("guides") or {}
    if not guides:
        return "", ""
    defs = []
    body = []
    for index, panel in enumerate(guides.get("panels") or [], 1):
        rect = [float(v) for v in panel.get("rect_mm") or []]
        if len(rect) != 4:
            raise ValueError("layout.guides.panels[].rect_mm needs x,y,width,height")
        body.append(
            f'<g id="guide-panel-{index}" data-panel="{index}">'
            f'<rect x="{rect[0]:.4f}" y="{rect[1]:.4f}" width="{rect[2]:.4f}" '
            f'height="{rect[3]:.4f}" rx="{float(panel.get("radius_mm", 1.5)):.4f}" '
            f'fill="{esc(panel.get("fill", "#fbfcfd"))}" '
            f'stroke="{esc(panel.get("stroke", "#c8d1da"))}" '
            f'stroke-width="{float(panel.get("stroke_width_mm", .3)):.4f}"/>'
            "</g>"
        )
    plane = guides.get("reaction_plane")
    if plane:
        points = [
            (float(point[0]), float(point[1]))
            for point in plane.get("points_mm") or []
        ]
        if len(points) != 4:
            raise ValueError("layout.guides.reaction_plane.points_mm needs four points")
        p00, p10, p11, p01 = points
        polygon = " ".join(f"{x:.4f},{y:.4f}" for x, y in points)
        body.append(
            f'<polygon id="guide-reaction-plane" points="{polygon}" '
            f'fill="{esc(plane.get("fill", "#e7ebef"))}" '
            f'fill-opacity="{float(plane.get("opacity", .18)):g}" '
            f'stroke="{esc(plane.get("stroke", "#aab3bd"))}" stroke-width=".35"/>'
        )
        columns, rows = [int(v) for v in plane.get("grid", [6, 5])]
        for column in range(1, max(1, columns)):
            t = column / columns
            a = (p00[0] * (1 - t) + p10[0] * t, p00[1] * (1 - t) + p10[1] * t)
            b = (p01[0] * (1 - t) + p11[0] * t, p01[1] * (1 - t) + p11[1] * t)
            body.append(
                f'<path d="M{a[0]:.4f} {a[1]:.4f} L{b[0]:.4f} {b[1]:.4f}" '
                'fill="none" stroke="#aab3bd" stroke-width=".22" opacity=".55"/>'
            )
        for row in range(1, max(1, rows)):
            t = row / rows
            a = (p00[0] * (1 - t) + p01[0] * t, p00[1] * (1 - t) + p01[1] * t)
            b = (p10[0] * (1 - t) + p11[0] * t, p10[1] * (1 - t) + p11[1] * t)
            body.append(
                f'<path d="M{a[0]:.4f} {a[1]:.4f} L{b[0]:.4f} {b[1]:.4f}" '
                'fill="none" stroke="#aab3bd" stroke-width=".22" opacity=".55"/>'
            )
    beam = guides.get("beamline")
    if beam:
        start = beam.get("from_mm") or [12, 55]
        end = beam.get("to_mm") or [110, 55]
        marker_attrs = ""
        if beam.get("arrowheads"):
            marker = "guide-beam-arrow"
            defs.append(
                f'<marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" '
                'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
                '<path d="M0 0 L10 5 L0 10 Z" fill="#768391"/></marker>'
            )
            marker_attrs = (
                f' marker-start="url(#{marker})" marker-end="url(#{marker})"'
            )
        body.append(
            f'<path id="guide-beamline" d="M{float(start[0]):.4f} {float(start[1]):.4f} '
            f'L{float(end[0]):.4f} {float(end[1]):.4f}" fill="none" '
            f'stroke="#768391" stroke-width=".45" stroke-dasharray="2 2"'
            f'{marker_attrs}/>'
        )
    triad = guides.get("axis_triad")
    if triad:
        origin = triad.get("origin_mm") or [162, 90]
        length = float(triad.get("length_mm", 12))
        font_pt = float(triad.get("font_size_pt", 6))
        size_mm = font_pt * PT_TO_MM
        axes = (spec.get("composition") or {}).get("projection", {}).get("axes_deg") or {}
        colors = {"x": "#d46b42", "y": "#3178c6", "z": "#309566"}
        for axis in ("x", "y", "z"):
            angle = math.radians(float(axes.get(axis, {"x": -17, "y": -90, "z": 24}[axis])))
            x1 = float(origin[0]) + length * math.cos(angle)
            y1 = float(origin[1]) + length * math.sin(angle)
            marker = f"guide-axis-marker-{axis}"
            defs.append(
                f'<marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" '
                'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
                f'<path d="M0 0 L10 5 L0 10 Z" fill="{colors[axis]}"/></marker>'
            )
            body.append(
                f'<path id="guide-axis-{axis}" d="M{float(origin[0]):.4f} '
                f'{float(origin[1]):.4f} L{x1:.4f} {y1:.4f}" fill="none" '
                f'stroke="{colors[axis]}" stroke-width=".55" '
                f'marker-end="url(#{marker})"/>'
                f'<text id="guide-label-{axis}" data-text-id="guide-label-{axis}" '
                f'data-element="guide-label-{axis}" data-element-kind="text" '
                f'data-font-size-pt="{font_pt:g}" x="{x1 + 1.4:.4f}" '
                f'y="{y1 - 1.0:.4f}" font-family="DejaVu Sans" '
                f'font-size="{size_mm:.4f}" text-anchor="middle" '
                f'fill="{colors[axis]}">{axis}</text>'
            )
    if not body:
        return "".join(defs), ""
    return "".join(defs), (
        '<g id="layout-guides" data-layer="layout-guides">'
        + "".join(body)
        + "</g>"
    )


def render_spec(spec: dict, safe_mode: bool) -> tuple[str, dict]:
    fig = spec["figure"]
    canvas = fig["canvas"]
    width = length_mm(canvas["width_mm"], "width_mm")
    height = length_mm(canvas["height_mm"], "height_mm")
    library = asset_map()
    defs = []
    body_elements = []
    element_lookup = {e["id"]: e for e in spec["elements"]}
    provenance = []
    for index, element in enumerate(sorted(spec["elements"], key=lambda e: e.get("z", 0))):
        asset = resolve_element_asset(element, library)
        if asset is None:
            raise ValueError(f"{element['id']}: unresolved asset")
        generation = asset.get("generation") or {}
        render_mode = str(element.get("render_mode") or "edit").casefold()
        if render_mode not in {"texture", "edit"}:
            raise ValueError(f"{element['id']}: render_mode must be texture or edit")
        if render_mode == "texture" and not generation.get("texture_file"):
            raise ValueError(
                f"{element['id']}: texture was requested but asset "
                f"{asset['id']} has no texture_file"
            )
        render_rel = (
            generation.get("edit_file") or asset["file"]
            if render_mode == "edit"
            else generation["texture_file"]
        )
        render_origin = str(generation.get("origin") or "software")
        if render_mode == "edit" and render_origin.startswith("article_vector_"):
            render_origin = str(
                generation.get("native_origin") or "article_vector_native"
            )
        path = ROOT / "assets" / "element-library" / render_rel
        if not path.exists():
            raise ValueError(f"{element['id']}: render file missing: {render_rel}")
        render_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        prefix = f"asset{index}_{re.sub(r'[^A-Za-z0-9_-]', '_', element['id'])}_"
        vb, d, b = load_asset_svg(path, prefix)
        defs.append(d)
        x, y = element_center(element)
        w = length_mm(element["width_mm"], "width_mm")
        h = length_mm(element["height_mm"], "height_mm")
        source_w = vb[2] - vb[0]
        source_h = vb[3] - vb[1]
        fit = str(element.get("fit", "contain")).casefold()
        if fit == "stretch":
            sx = w / source_w
            sy = h / source_h
            offset_x = offset_y = 0.0
        else:
            scale = min(w / source_w, h / source_h)
            sx = sy = scale
            offset_x = (w - source_w * scale) / 2.0
            offset_y = (h - source_h * scale) / 2.0
        rot = float(element.get("rotation_deg", 0) or 0)
        opacity = float(element.get("opacity", 1) or 1)
        transform = (
            f"translate({x:.4f} {y:.4f}) rotate({rot:.4f}) "
            f"translate({-w/2:.4f} {-h/2:.4f}) "
            f"translate({offset_x:.4f} {offset_y:.4f}) "
            f"scale({sx:.6f} {sy:.6f}) "
            f"translate({-vb[0]:.4f} {-vb[1]:.4f})"
        )
        body_elements.append(
            f'<g id="el-{esc(element["id"])}" data-element="{esc(element["id"])}" '
            f'data-element-id="{esc(element["id"])}" data-element-kind="asset" '
            f'data-asset-id="{esc(asset["id"])}" '
            f'data-origin="{esc(render_origin)}" '
            f'data-render-mode="{render_mode}" '
            f'data-ai-generated="{str(bool(generation.get("ai_generated"))).lower()}" '
            f'opacity="{opacity:g}" transform="{transform}">{b}</g>'
        )
        provenance.append({
            "element_id": element["id"],
            "asset_id": asset["id"],
            "asset_family": asset.get("family"),
            "asset_variant": asset.get("variant"),
            "asset_file": render_rel,
            "render_mode": render_mode,
            "requested_render_mode": str(element.get("render_mode") or "edit").casefold(),
            "fit": fit,
            "asset_sha256": render_sha,
            "origin": render_origin,
            "ai_generated": bool(generation.get("ai_generated")),
            "contains_ai_pixels": bool(generation.get("contains_ai_pixels")),
            "license": asset["license"]["spdx"],
            "license_source_url": asset["license"].get("source_url", ""),
            "attribution": asset["license"].get("attribution", ""),
            "source_asset_id": generation.get("source_asset_id", ""),
            "source_sha256": generation.get("source_sha256", ""),
            "submission_safe": is_safe_asset(asset),
        })

    marker_defs = []
    connection_markup = []
    for idx, con in enumerate(spec.get("connections") or []):
        cid = con.get("id") or f"C{idx+1}"
        ctype = con.get("type")
        color = con.get("color", "#29323c")
        width_pt = float(con.get("line_width_pt", 0.75))
        width_mm = width_pt * PT_TO_MM
        dash = f' stroke-dasharray="{esc(con["dash"])}"' if con.get("dash") else ""
        if ctype == "freeform":
            pts = [(float(p[0]), float(p[1])) for p in con["points"]]
        else:
            start = resolve_endpoint(con.get("from"), element_lookup,
                                     con.get("from_offset_mm"), f"{cid}.from")
            end = resolve_endpoint(con.get("to"), element_lookup,
                                   con.get("to_offset_mm"), f"{cid}.to")
            if ctype == "elbow":
                bend = con.get("bend", "h_v")
                mid = (end[0], start[1]) if bend == "h_v" else (start[0], end[1])
                pts = [start, mid, end]
            else:
                pts = [start, end]
        d = "M " + " L ".join(f"{x:.4f} {y:.4f}" for x, y in pts)
        attrs = []
        if ctype in {"arrow", "double_arrow"}:
            mk = f"arrow-{idx}"
            marker_defs.append(
                f'<marker id="{mk}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                f'<path d="M0 0 L10 5 L0 10 Z" fill="{esc(color)}"/></marker>'
            )
            attrs.append(f'marker-end="url(#{mk})"')
            if ctype == "double_arrow":
                attrs.append(f'marker-start="url(#{mk})"')
        connection_markup.append(
            f'<path id="conn-{esc(cid)}" data-connection-id="{esc(cid)}" '
            f'data-element="{esc(cid)}" data-element-kind="connection" '
            f'd="{d}" fill="none" stroke="{esc(color)}" stroke-width="{width_mm:.4f}" '
            f'stroke-linecap="round" stroke-linejoin="round"{dash} '
            + " ".join(attrs) + "/>"
        )

    text_markup = []
    for text in spec.get("texts") or []:
        size_pt = float(text.get("font_size_pt", 7))
        size_mm = size_pt * PT_TO_MM
        x = length_mm(text["x_mm"], "x_mm")
        y = length_mm(text["y_mm"], "y_mm")
        family = text.get("font_family", "DejaVu Sans")
        weight = ' font-weight="bold"' if text.get("bold") else ""
        anchor = text.get("anchor", "middle")
        value = text.get("value", text.get("text", ""))
        text_markup.append(
            f'<text id="txt-{esc(text["id"])}" data-text-id="{esc(text["id"])}" '
            f'data-element="{esc(text["id"])}" data-element-kind="text" '
            f'data-font-size-pt="{size_pt:g}" x="{x:.4f}" y="{y:.4f}" '
            f'font-family="{esc(family)}" font-size="{size_mm:.4f}" '
            f'text-anchor="{esc(anchor)}" fill="{esc(text.get("color", "#111111"))}"'
            f'{weight}>{esc(value)}</text>'
        )

    guide_defs, guides_markup = layout_guide_markup(spec)
    metadata = {
        "schema": "hep-nature-figure/spec-compile-v1",
        "figure_id": fig.get("id") or "figure",
        "spec_sha256": canonical_hash(spec),
        "safe_mode": safe_mode,
        "assets": provenance,
        "relations": spec.get("relationships") or [],
        "hard_physics": spec.get("hard_physics") or [],
        "layout": (spec.get("composition") or {}).get("layout") or {},
    }
    background = (spec.get("style") or {}).get("background", "#ffffff")
    title = fig.get("title") or fig.get("id") or "HEP schematic"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" width="{width:g}mm" height="{height:g}mm" '
        f'viewBox="0 0 {width:g} {height:g}" role="img" aria-labelledby="fig-title">\n'
        f"<title id=\"fig-title\">{esc(title)}</title>\n"
        f'<metadata id="provenance">{esc(json.dumps(metadata, ensure_ascii=False, sort_keys=True))}</metadata>\n'
        f"<defs>{''.join(defs)}{''.join(marker_defs)}{guide_defs}</defs>\n"
        f'<rect id="background" x="0" y="0" width="{width:g}" height="{height:g}" fill="{esc(background)}"/>\n'
        f"{guides_markup}\n"
        f'<g id="elements" data-layer="physical-elements">\n{chr(10).join(body_elements)}\n</g>\n'
        f'<g id="connections" data-layer="physical-connections">\n{chr(10).join(connection_markup)}\n</g>\n'
        f'<g id="text" data-layer="text"><g id="labels">{chr(10).join(text_markup)}</g></g>\n'
        "</svg>\n"
    )
    return svg, metadata


def render_outputs(svg_text: str, outdir: Path, stem: str, width_mm: float) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    svg_path = outdir / f"{stem}.svg"
    png_path = outdir / f"{stem}.png"
    pdf_path = outdir / f"{stem}.pdf"
    svg_path.write_text(svg_text, encoding="utf-8")
    try:
        import cairosvg
    except ImportError as exc:
        raise SystemExit("SVG output written, but cairosvg is required for PDF/PNG") from exc
    width_px = round(width_mm / 25.4 * 600)
    cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=width_px)
    try:
        cairosvg.svg2pdf(url=str(svg_path), write_to=str(pdf_path))
    except MemoryError:
        # Some Windows Cairo builds report a spurious OOM even for a plain SVG.
        # PyMuPDF still imports this vector scene without rasterising it.
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        document = fitz.open(stream=svg_text.encode("utf-8"), filetype="svg")
        try:
            pdf_path.write_bytes(document.convert_to_pdf())
        finally:
            document.close()
    return {"svg": str(svg_path), "png": str(png_path), "pdf": str(pdf_path)}


def main():
    ap = argparse.ArgumentParser(description="Compile confirmed spec to Nature-ready figure")
    ap.add_argument("spec")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--stem", default="figure")
    ap.add_argument("--receipt")
    ap.add_argument("--safe-mode", action="store_true",
                    help="reject AI-origin and raster-derived elements")
    ap.add_argument("--source-derived-only", action="store_true",
                    help="reject software-authored primitives and use article-derived elements only")
    ap.add_argument("--experiment", action="store_true",
                    help="allow an unconfirmed spec; manifest marks the run experimental")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--final", action="store_true",
                    help="require a matching client visual-review receipt")
    ap.add_argument("--review-receipt")
    ap.add_argument("--no-nature-gate", action="store_true")
    ap.add_argument("--skip-postchecks", action="store_true")
    a = ap.parse_args()
    spec_path = Path(a.spec).expanduser().resolve()
    spec = load_spec(spec_path)
    errors, metrics = validate_spec(spec, a.safe_mode, a.source_derived_only)
    if errors:
        print("FAIL: spec is not compilable")
        for error in errors:
            print(f"  - {error}")
        return 1
    rec = receipt_path(spec_path, a.receipt)
    confirmation = "experimental"
    if not a.experiment:
        rc = cmd_check(spec_path, rec)
        if rc:
            return rc
        confirmation = "confirmed"
    else:
        print("WARN: experimental compile; no client confirmation is claimed")
    physics_errors, physics_results = evaluate_physics(spec)
    layout_errors, layout_results = evaluate_layout(spec)
    if physics_errors:
        print("FAIL: machine-readable hard physics checks failed")
        for error in physics_errors:
            print(f"  - {error}")
        return 1
    if layout_errors:
        print("FAIL: IR layout checks failed")
        for error in layout_errors:
            print(f"  - {error}")
        return 1
    if a.check_only:
        print(json.dumps({"ok": True, "confirmation": confirmation,
                          "physics_checks": physics_results,
                          "layout_checks": layout_results, **metrics},
                         ensure_ascii=False, indent=2))
        return 0
    svg_text, metadata = render_spec(spec, a.safe_mode)
    outdir = Path(a.outdir).expanduser().resolve()
    outputs = render_outputs(svg_text, outdir, a.stem, metrics["canvas_mm"][0])
    visual_status = "preview"
    if a.final:
        reviewer = Path(__file__).resolve().parent / "visual_review.py"
        cmd = [sys.executable, str(reviewer), "--spec", str(spec_path),
               "--svg", outputs["svg"], "--png", outputs["png"], "--pdf", outputs["pdf"]]
        if a.review_receipt:
            cmd += ["--receipt", a.review_receipt]
        r = subprocess.run(cmd)
        if r.returncode:
            print("Preview outputs were written. Record visual review, then rerun with --final.")
            return r.returncode
        visual_status = "approved"
    manifest = {
        "schema": "hep-nature-figure/spec-compile-v1",
        "spec": str(spec_path),
        "spec_sha256": canonical_hash(spec),
        "confirmation": confirmation,
        "safe_mode": bool(a.safe_mode),
        "source_derived_only": bool(a.source_derived_only),
        "visual_review": visual_status,
        "metrics": metrics,
        "physics_checks": physics_results,
        "layout_checks": layout_results,
        "outputs": outputs,
        "provenance": metadata["assets"],
    }
    manifest_path = outdir / f"{a.stem}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    if not a.no_nature_gate:
        gate = Path(__file__).resolve().parent / "nature_gate.py"
        cmd = [sys.executable, str(gate), str(outputs["svg"]), "--spec", str(spec_path),
               "--png", outputs["png"], "--pdf", outputs["pdf"], "--manifest", str(manifest_path)]
        if a.safe_mode:
            cmd.append("--safe-mode")
        r = subprocess.run(cmd)
        if r.returncode:
            return r.returncode
        # nature_gate appends its report to the manifest on disk.
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    postchecks = {}
    if not a.skip_postchecks:
        checks = [
            ("svg_structure", [
                sys.executable, str(Path(__file__).parent / "check_direct_svg.py"),
                outputs["svg"], "--require", *[e["id"] for e in spec["elements"]],
                "--min-text", str(len(spec.get("texts") or [])),
            ]),
            ("render", [sys.executable, str(Path(__file__).parent / "check_render.py"),
                        outputs["png"]]),
            ("3d", [sys.executable, str(Path(__file__).parent / "check_3d_generic.py"),
                    outputs["png"], "--expect-plane", "no"]),
            ("delivery", [sys.executable, str(Path(__file__).parent / "check_delivery.py"),
                          outputs["pdf"]]),
        ]
        for name, cmd in checks:
            r = subprocess.run(cmd)
            postchecks[name] = r.returncode
            if r.returncode:
                manifest["postchecks"] = postchecks
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
                return r.returncode
        manifest["postchecks"] = postchecks
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps({"confirmation": confirmation, **outputs,
                      "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
