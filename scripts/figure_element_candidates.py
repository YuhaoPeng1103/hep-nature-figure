#!/usr/bin/env python3
"""Build a resumable review index for all legally harvested article figures.

The tool never promotes a whole article panel into the element library. It
deduplicates the source corpus, ranks figure-level schematic likelihood, and
creates candidate object crops for human review. Accepted crops still go
through the normal mask, redraw, provenance, and visual gates.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "assets" / "element-library" / "source-corpus"
PUBLISHER = CORPUS / "publisher" / "figures.jsonl"
SOURCE_INDEXES = [CORPUS / "figures.jsonl", PUBLISHER]
REVIEW = ROOT / "assets" / "element-library" / "corpus-review"
RECORDS = REVIEW / "candidate_figures.jsonl"
CROPS = REVIEW / "crops"
SHEETS = REVIEW / "sheets"
SCHEMATIC_RE = re.compile(
    r"(?i)schematic|illustration|cartoon|depiction|conceptual|"
    r"geometry|geometric|workflow|spacetime|space-time|"
    r"detector (?:layout|cutaway)|3d rendering|energy-loss scenario|"
    r"model (?:picture|sketch)|diagram"
)
STRONG_SCHEM_RE = re.compile(
    r"(?i)schematic|illustration|cartoon|depiction|conceptual|3d rendering"
)
PLOT_RE = re.compile(
    r"(?i)\b(?:axes|axis|distribution|spectrum|cross section|"
    r"as a function of|error bars|heat map|histogram|scatter plot)\b"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def resolve_local(row: dict) -> Path | None:
    value = str(row.get("local_file") or "")
    if not value:
        return None
    path = ROOT / value
    return path if path.is_file() else None


def hep_figure(row: dict) -> bool:
    try:
        from article_element_harvester import hep_article_relevant
    except Exception:
        return True
    return hep_article_relevant(
        str(row.get("title") or ""),
        f"{row.get('caption', '')} {row.get('journal', '')}",
    )


def caption_score(caption: str) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0
    if STRONG_SCHEM_RE.search(caption):
        score += 4.0
        reasons.append("caption-explicit-schematic")
    elif SCHEMATIC_RE.search(caption):
        score += 2.5
        reasons.append("caption-diagram-term")
    if PLOT_RE.search(caption):
        score -= 1.0
        reasons.append("caption-plot-term")
    return score, reasons


def image_measure(path: Path):
    import cv2
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        scale = min(1.0, 1400 / max(rgb.size))
        if scale < 1.0:
            rgb = rgb.resize(
                (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
                Image.Resampling.LANCZOS,
            )
        pixels = np.asarray(rgb)
    small = cv2.resize(pixels, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    quant = (small // 32).astype(np.uint8)
    unique_ratio = len(np.unique(quant.reshape(-1, 3), axis=0)) / max(
        1, small.shape[0] * small.shape[1]
    )
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    saturation = float(hsv[:, :, 1].mean() / 255)
    white_fraction = float(
        ((small[:, :, 0] > 245) & (small[:, :, 1] > 245) & (small[:, :, 2] > 245)).mean()
    )
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    edge_density = float((edges > 0).mean())
    local_mean = cv2.blur(gray.astype(np.float32), (3, 3))
    local_sq = cv2.blur((gray.astype(np.float32) ** 2), (3, 3))
    local_std = np.sqrt(np.maximum(local_sq - local_mean ** 2, 0))
    flat_fraction = float((local_std < 2.0).mean())
    return {
        "width": int(pixels.shape[1]),
        "height": int(pixels.shape[0]),
        "unique_color_ratio": round(unique_ratio, 6),
        "saturation_mean": round(saturation, 6),
        "white_fraction": round(white_fraction, 6),
        "edge_density": round(edge_density, 6),
        "flat_fraction": round(flat_fraction, 6),
    }, scale


def image_score(readings: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    if readings["flat_fraction"] >= 0.35:
        score += 2.0
        reasons.append("large-flat-regions")
    if readings["edge_density"] <= 0.075:
        score += 1.2
        reasons.append("sparse-outlines")
    if readings["white_fraction"] >= 0.35:
        score += 1.0
        reasons.append("light-background")
    if readings["saturation_mean"] >= 0.18:
        score += 0.8
        reasons.append("semantic-color")
    if readings["edge_density"] >= 0.18:
        score -= 1.5
        reasons.append("photo-or-dense-plot")
    return score, reasons


def object_boxes(path: Path, analysis_scale: float) -> list[dict]:
    """Conservative component proposals; these remain review-only."""
    import cv2
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        original_width, original_height = rgb.size
        scale = min(analysis_scale, 1000 / max(rgb.size), 1.0)
        work = rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.Resampling.LANCZOS,
        )
        pixels = np.asarray(work)
    border = np.concatenate([
        pixels[:8].reshape(-1, 3),
        pixels[-8:].reshape(-1, 3),
        pixels[:, :8].reshape(-1, 3),
        pixels[:, -8:].reshape(-1, 3),
    ])
    background = np.median(border, axis=0)
    distance = np.max(np.abs(pixels.astype(np.float32) - background), axis=2)
    mask = (distance > 12).astype(np.uint8) * 255
    radius = max(2, min(work.size) // 100)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)
    )
    merged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    canvas_area = work.width * work.height
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < canvas_area * 0.003 or area > canvas_area * 0.85:
            continue
        pad = max(2, round(max(w, h) * 0.04))
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(work.width, x + w + pad)
        y1 = min(work.height, y + h + pad)
        candidates.append({
            "box_analysis_px": [x0, y0, x1, y1],
            "box_source_px": [
                round(x0 / scale),
                round(y0 / scale),
                min(original_width, round(x1 / scale)),
                min(original_height, round(y1 / scale)),
            ],
            "area_fraction": round(area / canvas_area, 6),
        })
    candidates.sort(key=lambda row: row["area_fraction"], reverse=True)
    return candidates[:12]


def write_crops(path: Path, figure_id: str, boxes: list[dict]) -> list[dict]:
    from PIL import Image

    outputs = []
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        for index, candidate in enumerate(boxes, 1):
            x0, y0, x1, y1 = candidate["box_source_px"]
            crop = rgb.crop((x0, y0, x1, y1))
            dest = CROPS / figure_id / f"object-{index:02d}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            crop.save(dest, format="PNG")
            outputs.append({
                **candidate,
                "local_file": dest.relative_to(ROOT).as_posix(),
                "status": "review-only",
            })
    return outputs


def build_contact_sheets(records: list[dict], per_sheet: int = 16) -> list[str]:
    from PIL import Image, ImageDraw

    selected = [
        row for row in records
        if row.get("review_priority") in {"high", "medium"}
    ]
    SHEETS.mkdir(parents=True, exist_ok=True)
    outputs = []
    cell_w, cell_h = 300, 250
    cols = 4
    for start in range(0, len(selected), per_sheet):
        batch = selected[start:start + per_sheet]
        rows = math.ceil(len(batch) / cols)
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
        draw = ImageDraw.Draw(sheet)
        for offset, row in enumerate(batch):
            source = ROOT / row["local_file"]
            with Image.open(source) as image:
                tile = image.convert("RGB")
                tile.thumbnail((cell_w - 16, cell_h - 48), Image.Resampling.LANCZOS)
            x = (offset % cols) * cell_w
            y = (offset // cols) * cell_h
            sheet.paste(tile, (x + 8, y + 8))
            draw.text((x + 8, y + cell_h - 36), row["figure_id"][:42], fill="#17212b")
            draw.text(
                (x + 8, y + cell_h - 20),
                f"{row['review_priority']} | score={row['schematic_score']:.1f}",
                fill="#506070",
            )
        dest = SHEETS / f"review-{start // per_sheet + 1:03d}.jpg"
        sheet.save(dest, quality=88)
        outputs.append(dest.relative_to(ROOT).as_posix())
    return outputs


def build_review_html(records: list[dict]) -> str:
    rows = []
    for row in records:
        image = Path(os.path.relpath(ROOT / row["local_file"], REVIEW)).as_posix()
        caption = html.escape(str(row.get("caption") or "")[:600])
        rows.append(
            "<tr>"
            f'<td><a href="{html.escape(image)}"><img src="{html.escape(image)}" '
            f'alt="{html.escape(row["figure_id"])}"></a></td>'
            f'<td><code>{html.escape(row["figure_id"])}</code><br>'
            f'{row["review_priority"]} / {row["schematic_score"]:.1f}<br>'
            f'{html.escape(str(row.get("title") or ""))}<br>'
            f'<small>{caption}</small></td>'
            "</tr>"
        )
    body = "\n".join(rows)
    markup = f"""<!doctype html>
<meta charset="utf-8">
<title>HEP figure element review</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;margin:20px;background:#f4f6f8;color:#15202b}}
table{{border-collapse:collapse;width:100%}}
td{{vertical-align:top;border-bottom:1px solid #ccd4dc;padding:10px}}
img{{max-width:420px;max-height:300px;object-fit:contain;background:white}}
code{{font-size:12px}}
</style>
<h1>HEP figure element review</h1>
<p>Automatic crops are review-only. No candidate is active until object review
and native SVG redraw.</p>
<table>{body}</table>
"""
    dest = REVIEW / "index.html"
    dest.write_text(markup, encoding="utf-8")
    return dest.relative_to(ROOT).as_posix()


def main() -> int:
    ap = argparse.ArgumentParser(description="Index article figures for element review")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-figures", type=int, default=0)
    ap.add_argument("--min-score", type=float, default=2.0)
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()
    try:
        import cv2  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit("candidate indexing needs OpenCV and Pillow") from exc

    old = {row["figure_id"]: row for row in load_jsonl(RECORDS)}
    seen_hashes = set()
    records = []
    sources = duplicates = rejected = 0
    for source_index in SOURCE_INDEXES:
        for row in load_jsonl(source_index):
            path = resolve_local(row)
            if not path or row.get("status", "").startswith("metadata-only"):
                continue
            sources += 1
            content_hash = sha256(path)
            if content_hash in seen_hashes:
                duplicates += 1
                continue
            if not hep_figure(row):
                rejected += 1
                continue
            seen_hashes.add(content_hash)
            if not args.force and row["figure_id"] in old:
                old_row = old[row["figure_id"]]
                if old_row.get("local_sha256") == content_hash:
                    records.append(old_row)
                    continue
            readings, scale = image_measure(path)
            cap_score, cap_reasons = caption_score(
                f"{row.get('caption', '')} {row.get('title', '')}"
            )
            vis_score, vis_reasons = image_score(readings)
            score = round(cap_score + vis_score, 3)
            priority = "high" if score >= 5 else "medium" if score >= args.min_score else "low"
            boxes = []
            crops = []
            if priority != "low" and not args.no_crops:
                boxes = object_boxes(path, scale)
                crops = write_crops(path, row["figure_id"], boxes)
            records.append({
                **row,
                "local_sha256": content_hash,
                "visual_metrics": readings,
                "schematic_score": score,
                "review_priority": priority,
                "score_reasons": cap_reasons + vis_reasons,
                "object_candidates": crops,
                "element_status": "needs-human-object-review",
            })

    records.sort(
        key=lambda row: (
            row.get("review_priority") == "high",
            row.get("schematic_score", 0),
            row["figure_id"],
        ),
        reverse=True,
    )
    if args.max_figures:
        records = records[:args.max_figures]
    put_jsonl(RECORDS, records)
    sheets = build_contact_sheets(records)
    review_html = build_review_html(records)
    report = {
        "schema_version": "1.0",
        "updated": "2026-11-22",
        "source_records": sources,
        "unique_hep_records": len(records),
        "duplicate_images": duplicates,
        "rejected_non_hep": rejected,
        "high": sum(row["review_priority"] == "high" for row in records),
        "medium": sum(row["review_priority"] == "medium" for row in records),
        "low": sum(row["review_priority"] == "low" for row in records),
        "object_candidates": sum(len(row["object_candidates"]) for row in records),
        "contact_sheets": sheets,
        "review_html": review_html,
        "promotion_policy": (
            "Whole figures and automatic crops remain review-only. "
            "No crop enters index.json without object review and native SVG rebuild."
        ),
    }
    (REVIEW / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
