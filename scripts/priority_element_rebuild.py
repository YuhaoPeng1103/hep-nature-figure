#!/usr/bin/env python3
"""Triage and rebuild object crops from the high-priority figure queue.

This is an auditable first pass, not an automatic promotion tool. Every object
gets a transparent cutout and either a native smooth-path SVG candidate or a
manual-review reason. Nothing here enters index.json automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "assets" / "element-library" / "corpus-review"
SOURCE = REVIEW / "candidate_figures.jsonl"
OUT = ROOT / "assets" / "element-library" / "priority-review"
ARTIFACTS = OUT / "objects"
OBJECTS = OUT / "objects.jsonl"
REPORT = OUT / "report.json"
INDEX_HTML = OUT / "index.html"
SHEETS = OUT / "sheets"
TODAY = "2026-11-23"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def put_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def pad_box(box: list[int], width: int, height: int, fraction=0.08) -> list[int]:
    x0, y0, x1, y1 = [int(v) for v in box]
    px = max(4, round((x1 - x0) * fraction))
    py = max(4, round((y1 - y0) * fraction))
    return [max(0, x0 - px), max(0, y0 - py),
            min(width, x1 + px), min(height, y1 + py)]


def smooth_closed_path(points) -> str:
    """Convert a closed polygon to a smooth Catmull-Rom cubic path."""
    import numpy as np

    pts = np.asarray(points, dtype=float)
    if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-6:
        pts = pts[:-1]
    if len(pts) < 3:
        return ""
    commands = [f"M{pts[0,0]:.2f},{pts[0,1]:.2f}"]
    count = len(pts)
    for index in range(count):
        p0 = pts[(index - 1) % count]
        p1 = pts[index]
        p2 = pts[(index + 1) % count]
        p3 = pts[(index + 2) % count]
        c1 = p1 + (p2 - p0) / 6.0
        c2 = p2 - (p3 - p1) / 6.0
        commands.append(
            f"C{c1[0]:.2f},{c1[1]:.2f} "
            f"{c2[0]:.2f},{c2[1]:.2f} "
            f"{p2[0]:.2f},{p2[1]:.2f}"
        )
    commands.append("Z")
    return "".join(commands)


def _rgb_hex(color) -> str:
    return "#" + "".join(f"{max(0, min(255, round(float(v)))):02x}" for v in color[:3])


def _components(mask):
    import cv2

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        (mask > 0).astype("uint8"), connectivity=8
    )
    rows = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area:
            rows.append((area, label, stats[label]))
    rows.sort(reverse=True, key=lambda item: item[0])
    return labels, rows


def analyze_alpha(alpha) -> dict:
    import cv2
    import numpy as np

    mask = (alpha > 20).astype("uint8")
    labels, components = _components(mask)
    total = int(mask.sum())
    if not components:
        return {
            "foreground_fraction": 0.0,
            "components": 0,
            "largest_component_fraction": 0.0,
            "small_components": 0,
        }
    largest = components[0][0]
    small = sum(1 for area, _label, _stats in components if area < total * 0.015)
    contours, _ = cv2.findContours(
        (labels == components[0][1]).astype("uint8"),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    contour = max(contours, key=cv2.contourArea) if contours else None
    perimeter = cv2.arcLength(contour, True) if contour is not None else 0.0
    area = cv2.contourArea(contour) if contour is not None else 0.0
    circularity = 4 * math.pi * area / (perimeter * perimeter) if perimeter else 0.0
    hull = cv2.convexHull(contour) if contour is not None else None
    hull_area = cv2.contourArea(hull) if hull is not None else 0.0
    solidity = area / hull_area if hull_area else 0.0
    outline_contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    holes = 0
    if hierarchy is not None:
        holes = sum(1 for item in hierarchy[0] if int(item[3]) >= 0)
    x, y, w, h = cv2.boundingRect(contour) if contour is not None else (0, 0, 0, 0)
    return {
        "width": int(mask.shape[1]),
        "height": int(mask.shape[0]),
        "foreground_fraction": round(total / mask.size, 6),
        "components": len(components),
        "largest_component_fraction": round(largest / total, 6),
        "small_components": small,
        "bbox_fraction": round(area / mask.size, 6),
        "fill_ratio": round(area / max(1, w * h), 6),
        "circularity": round(circularity, 6),
        "solidity": round(solidity, 6),
        "holes": holes,
        "aspect_ratio": round(w / max(1, h), 6),
    }


def color_metrics(rgba) -> dict:
    import cv2
    import numpy as np

    arr = np.asarray(rgba)
    keep = arr[:, :, 3] > 32
    if not keep.any():
        return {"saturation_mean": 0.0, "colored_fraction": 0.0}
    hsv = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1][keep].astype(np.float32) / 255.0
    return {
        "saturation_mean": round(float(saturation.mean()), 6),
        "colored_fraction": round(float((saturation > 0.14).mean()), 6),
        "white_foreground_fraction": round(
            float((
                (arr[:, :, :3] > 245).all(axis=2) & keep
            ).sum() / max(1, keep.sum())),
            6,
        ),
    }


def native_svg_from_rgba(rgba, asset_id: str) -> tuple[str, dict]:
    import cv2
    import numpy as np
    from PIL import Image

    arr = np.asarray(rgba)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]
    mask = (alpha > 20).astype("uint8")
    if not mask.any():
        raise ValueError("empty foreground")
    labels, components = _components(mask)
    h, w = mask.shape
    foreground = rgb[mask > 0].astype(np.float32)
    unique = max(1, len(np.unique(foreground.astype(np.uint8), axis=0)))
    k = max(1, min(4, int(math.sqrt(unique)), len(foreground) // 24))
    if k <= 1:
        centers = np.array([foreground.mean(axis=0)])
        assignments = np.zeros(len(foreground), dtype=np.int32)
    else:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
        compactness, assign, centers = cv2.kmeans(
            foreground, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS
        )
        assignments = assign.ravel()
    pixels = np.zeros((int(mask.sum()), 2), dtype=np.int32)
    pixels[:, 0] = np.nonzero(mask)[1]
    pixels[:, 1] = np.nonzero(mask)[0]
    layers = []
    cluster_rows = []
    for cluster in range(k):
        cluster_mask = np.zeros_like(mask, dtype=np.uint8)
        selected = pixels[assignments == cluster]
        if len(selected):
            cluster_mask[selected[:, 1], selected[:, 0]] = 255
        cluster_rows.append((len(selected), cluster, cluster_mask))
    # Paint minor edge colours first and the dominant body colour last. k-means
    # label order is otherwise unstable and can cover the object with a pale
    # anti-alias cluster.
    for _count, cluster, cluster_mask in sorted(cluster_rows):
        cluster_mask = cv2.morphologyEx(
            cluster_mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        contours, _ = cv2.findContours(
            cluster_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
        )
        color = _rgb_hex(centers[cluster])
        min_area = max(8, mask.size * 0.00025)
        for contour in contours:
            if cv2.contourArea(contour) < min_area:
                continue
            perimeter = cv2.arcLength(contour, True)
            epsilon = max(0.4, perimeter * 0.004)
            polygon = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
            path = smooth_closed_path(polygon)
            if path:
                layers.append(
                    f'<path d="{path}" fill="{color}" fill-opacity="0.98"/>'
                )
    if not layers:
        raise ValueError("no vector contour survived")
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" data-element-asset="{html.escape(asset_id)}" '
        'data-origin="article_vector_candidate">'
        f'<g id="{html.escape(asset_id)}" data-element="{html.escape(asset_id)}" '
        'data-role="review-candidate">'
        + "".join(layers)
        + "</g></svg>\n"
    )
    return svg, {
        "paths": len(layers),
        "color_layers": k,
        "largest_component_pixels": components[0][0],
    }


def transparent_and_metrics(src: Path, padded_box: list[int]):
    import sys as _sys

    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in _sys.path:
        _sys.path.insert(0, script_dir)
    from source_element_extract import transparent_crop
    import numpy as np

    crop, absolute = transparent_crop(src, padded_box, None)
    metrics = analyze_alpha(np.asarray(crop)[:, :, 3])
    metrics.update(color_metrics(crop))
    return crop, absolute, metrics


def propose_components(path: Path, max_objects: int = 20) -> list[dict]:
    """Propose separate foreground components without the coarse panel closing."""
    import cv2
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        scale = min(1.0, 1400 / max(width, height))
        work = rgb.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        ) if scale < 1.0 else rgb
        pixels = np.asarray(work)
    border = np.concatenate([
        pixels[:8].reshape(-1, 3),
        pixels[-8:].reshape(-1, 3),
        pixels[:, :8].reshape(-1, 3),
        pixels[:, -8:].reshape(-1, 3),
    ])
    background = np.median(border, axis=0)
    distance = np.max(np.abs(pixels.astype(np.float32) - background), axis=2)
    mask = (distance > 16).astype(np.uint8)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    canvas_area = mask.shape[0] * mask.shape[1]
    proposals = []
    for label in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[label]]
        if area < canvas_area * 0.00035 or area > canvas_area * 0.55:
            continue
        if w < 12 or h < 12:
            continue
        pad = max(3, round(max(w, h) * 0.045))
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(mask.shape[1], x + w + pad)
        y1 = min(mask.shape[0], y + h + pad)
        proposals.append({
            "source_box_analysis_px": [x0, y0, x1, y1],
            "source_box_px": [
                round(x0 / scale), round(y0 / scale),
                min(width, round(x1 / scale)), min(height, round(y1 / scale)),
            ],
            "component_area_fraction": round(area / canvas_area, 6),
        })
    proposals.sort(key=lambda row: row["component_area_fraction"], reverse=True)
    selected = []
    for proposal in proposals:
        bx0, by0, bx1, by1 = proposal["source_box_px"]
        redundant = False
        for old in selected:
            ox0, oy0, ox1, oy1 = old["source_box_px"]
            inter_w = max(0, min(bx1, ox1) - max(bx0, ox0))
            inter_h = max(0, min(by1, oy1) - max(by0, oy0))
            inter = inter_w * inter_h
            area = max(1, (bx1 - bx0) * (by1 - by0))
            if inter / area > 0.92:
                redundant = True
                break
        if not redundant:
            selected.append(proposal)
        if len(selected) >= max_objects:
            break
    return selected


def render_preview(svg: str, dest: Path) -> tuple[int, int] | None:
    try:
        import cairosvg
        from PIL import Image
        import io
    except ImportError:
        return None
    png = cairosvg.svg2png(bytestring=svg.encode("utf-8"), background_color="white")
    with Image.open(io.BytesIO(png)) as image:
        image.convert("RGB").save(dest.with_suffix(".png"))
        return image.size


def process_object(figure: dict, index: int, obj: dict) -> dict:
    from PIL import Image

    figure_id = figure["figure_id"]
    key = obj.get("_record_key") or f"object-{index:02d}"
    object_id = f"{figure_id}-{key}"
    source = ROOT / figure["local_file"]
    with Image.open(source) as image:
        width, height = image.size
    box = pad_box(
        obj.get("box_source_px") or obj["source_box_px"], width, height
    )
    crop, absolute, metrics = transparent_and_metrics(source, box)
    dest = ARTIFACTS / figure_id / f"object-{index:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    source_crop = dest / "source.png"
    if not source_crop.exists():
        with Image.open(source) as image:
            image.convert("RGB").crop(tuple(box)).save(source_crop)
    transparent = dest / "transparent.png"
    crop.save(transparent)

    reasons = []
    if crop.width < 24 or crop.height < 24:
        reasons.append("object-too-small")
    if metrics["foreground_fraction"] < 0.015:
        reasons.append("foreground-too-sparse")
    if metrics["foreground_fraction"] > 0.96:
        reasons.append("background-removal-failed")
    if metrics["foreground_fraction"] > 0.68 or metrics["bbox_fraction"] > 0.58:
        reasons.append("compound-panel-too-large")
    if metrics["components"] > 1 or metrics["largest_component_fraction"] < 0.55:
        reasons.append("multiple-disconnected-objects")
    if metrics["small_components"] > 2:
        reasons.append("possible-text-or-small-symbols")
    if metrics["aspect_ratio"] > 6 or metrics["aspect_ratio"] < 1 / 6:
        reasons.append("line-or-caption-strip")
    if metrics["solidity"] < 0.55:
        reasons.append("sparse-line-art")
    if metrics["fill_ratio"] < 0.30:
        reasons.append("glyph-or-thin-line")
    if metrics["holes"] > 0:
        reasons.append("contains-type-or-internal-labels")
    if metrics["white_foreground_fraction"] > 0.08:
        reasons.append("embedded-light-text-or-symbols")
    if (
        metrics["saturation_mean"] < 0.12
        and (
            metrics["circularity"] < 0.55
            or min(metrics["width"], metrics["height"]) < 40
        )
    ):
        reasons.append("monochrome-text-or-line")
    status = "review-candidate" if not reasons else "needs-manual-separation"
    vector_rel = ""
    vector_error = ""
    vector_stats = {}
    if status == "review-candidate":
        try:
            svg, vector_stats = native_svg_from_rgba(crop, object_id)
            vector = dest / "native_candidate.svg"
            vector.write_text(svg, encoding="utf-8")
            render_preview(svg, dest / "native_preview")
            vector_rel = vector.relative_to(ROOT).as_posix()
        except Exception as exc:
            vector_error = str(exc)
            status = "needs-manual-redraw"
    return {
        "object_id": object_id,
        "figure_id": figure_id,
        "doi": figure.get("doi"),
        "title": figure.get("title"),
        "caption": figure.get("caption"),
        "license": figure.get("license"),
        "license_source_url": figure.get("license_source_url"),
        "source_figure": figure["local_file"],
        "source_sha256": figure.get("local_sha256"),
        "source_box_px": absolute,
        "source_crop": source_crop.relative_to(ROOT).as_posix(),
        "transparent_crop": transparent.relative_to(ROOT).as_posix(),
        "transparent_sha256": sha256(transparent),
        "native_candidate": vector_rel,
        "native_candidate_sha256": sha256(dest / "native_candidate.svg")
        if vector_rel else "",
        "vector_stats": vector_stats,
        "vector_error": vector_error,
        "metrics": metrics,
        "audit_reasons": reasons,
        "status": status,
        "active_library": False,
    }


def build_html(rows: list[dict]) -> str:
    table = []
    for row in rows:
        image = Path(os.path.relpath(ROOT / row["transparent_crop"], OUT)).as_posix()
        preview = ""
        if row.get("native_candidate"):
            link = Path(
                os.path.relpath(ROOT / row["native_candidate"], OUT)
            ).as_posix()
            preview = (
                f'<a href="{html.escape(link)}">SVG candidate</a>'
            )
        table.append(
            "<tr>"
            f'<td><img src="{html.escape(image)}" alt=""></td>'
            f'<td><code>{html.escape(row["object_id"])}</code><br>'
            f'{html.escape(row["status"])}<br>{preview}<br>'
            f'<small>{html.escape(str(row.get("caption") or "")[:500])}</small></td>'
            "</tr>"
        )
    markup = f"""<!doctype html><meta charset="utf-8">
<title>High-priority object rebuild</title>
<style>body{{font:14px/1.45 system-ui,sans-serif;margin:20px;background:#f4f6f8}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #ccd4dc;padding:10px;vertical-align:top}}
img{{max-width:360px;max-height:260px;object-fit:contain;background:white}}</style>
<h1>High-priority object rebuild</h1>
<p>All rows are review-only. No object is active in index.json.</p>
<table>{"".join(table)}</table>"""
    INDEX_HTML.write_text(markup, encoding="utf-8")
    return INDEX_HTML.relative_to(ROOT).as_posix()


def build_review_sheets(rows: list[dict], per_sheet: int = 12) -> list[str]:
    from PIL import Image, ImageDraw

    selected = [row for row in rows if row.get("native_candidate")]
    SHEETS.mkdir(parents=True, exist_ok=True)
    outputs = []
    cols = 3
    cell_w, cell_h = 420, 250
    for start in range(0, len(selected), per_sheet):
        batch = selected[start:start + per_sheet]
        sheet = Image.new("RGB", (cols * cell_w, math.ceil(len(batch) / cols) * cell_h), "white")
        draw = ImageDraw.Draw(sheet)
        for offset, row in enumerate(batch):
            x = (offset % cols) * cell_w
            y = (offset // cols) * cell_h
            with Image.open(ROOT / row["transparent_crop"]) as source:
                rgba = source.convert("RGBA")
                white = Image.new("RGBA", rgba.size, "white")
                white.alpha_composite(rgba)
                left = white.convert("RGB")
                left.thumbnail((190, 190), Image.Resampling.LANCZOS)
            preview_path = (ROOT / row["native_candidate"]).with_name("native_preview.png")
            with Image.open(preview_path) as preview:
                right = preview.convert("RGB")
                right.thumbnail((190, 190), Image.Resampling.LANCZOS)
            sheet.paste(left, (x + 8 + (190 - left.width) // 2, y + 10))
            sheet.paste(right, (x + 214 + (190 - right.width) // 2, y + 10))
            draw.text((x + 8, y + 205), row["object_id"][:62], fill="#17212b")
            draw.text((x + 8, y + 222), f"cutout | native candidate | score {row['metrics']['largest_component_fraction']:.2f}", fill="#506070")
        dest = SHEETS / f"native-candidates-{start // per_sheet + 1:03d}.jpg"
        sheet.save(dest, quality=90)
        outputs.append(dest.relative_to(ROOT).as_posix())
    return outputs


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit and vectorize high-priority objects")
    ap.add_argument("--limit-figures", type=int, default=0)
    ap.add_argument("--max-objects", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--object-source",
        choices=["recorded", "resegment", "both"],
        default="both",
    )
    args = ap.parse_args()
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit("priority rebuild needs OpenCV, numpy and Pillow") from exc
    figures = [
        row for row in load_jsonl(SOURCE)
        if row.get("review_priority") == "high"
    ]
    if args.limit_figures:
        figures = figures[:args.limit_figures]
    jobs = []
    for figure in figures:
        recorded = [
            {**obj, "_record_key": f"object-{index:02d}"}
            for index, obj in enumerate(figure.get("object_candidates") or [], 1)
        ]
        resegmented = []
        if args.object_source in {"resegment", "both"}:
            source = ROOT / figure["local_file"]
            resegmented = [
                {**obj, "_record_key": f"reseg-{index:02d}"}
                for index, obj in enumerate(propose_components(source), 1)
            ]
        objects = (
            recorded
            if args.object_source == "recorded"
            else resegmented
            if args.object_source == "resegment"
            else recorded + resegmented
        )
        for index, obj in enumerate(objects, 1):
            jobs.append((figure, index, obj))
            if args.max_objects and len(jobs) >= args.max_objects:
                break
        if args.max_objects and len(jobs) >= args.max_objects:
            break
    if args.dry_run:
        print(json.dumps({
            "high_priority_figures": len(figures),
            "object_jobs": len(jobs),
        }, ensure_ascii=False, indent=2))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    existing = {
        row["object_id"]: row
        for row in load_jsonl(OBJECTS)
    }
    processed = failures = 0
    rows = []
    for pos, (figure, index, obj) in enumerate(jobs, 1):
        key = obj.get("_record_key") or f"object-{index:02d}"
        object_id = f"{figure['figure_id']}-{key}"
        if object_id in existing and not args.force:
            rows.append(existing[object_id])
            continue
        try:
            row = process_object(figure, index, obj)
            existing[object_id] = row
            rows.append(row)
            processed += 1
        except Exception as exc:
            failures += 1
            print(f"WARN {object_id}: {exc}", file=sys.stderr, flush=True)
            continue
        if pos % 25 == 0 or pos == len(jobs):
            put_jsonl(OBJECTS, sorted(existing.values(), key=lambda r: r["object_id"]))
            print(f"[{pos}/{len(jobs)}] {figure['figure_id']}", flush=True)
    final_rows = sorted(existing.values(), key=lambda r: r["object_id"])
    put_jsonl(OBJECTS, final_rows)
    review_html = build_html(final_rows)
    sheets = build_review_sheets(final_rows)
    counts = Counter(row["status"] for row in final_rows)
    report = {
        "schema_version": "1.0",
        "updated": TODAY,
        "high_priority_figures": len(figures),
        "objects_considered": len(jobs),
        "objects_recorded": len(final_rows),
        "processed_this_run": processed,
        "failures_this_run": failures,
        "status_counts": dict(sorted(counts.items())),
        "review_html": review_html,
        "review_sheets": sheets,
        "promotion_policy": "review-only; native candidates require object review before ingestion",
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
