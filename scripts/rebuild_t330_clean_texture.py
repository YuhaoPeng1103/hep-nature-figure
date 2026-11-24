#!/usr/bin/env python3
"""Build a QGP-only fidelity texture with grid/field context removed."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from element_texture_vectorize import smooth_mesh_texture  # noqa: E402

LIB = ROOT / "assets" / "element-library"
INDEX = LIB / "index.json"
METRICS = LIB / "source-derived" / "texture_metrics.json"
ASSET_ID = "article_t330_qgp_fireball"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    asset = next(item for item in doc["assets"] if item["id"] == ASSET_ID)
    generation = asset["generation"]
    edit = LIB / generation["edit_file"]
    clean_source = edit.with_suffix(".clean.png")
    texture = LIB / generation["texture_file"]
    cairosvg.svg2png(
        url=str(edit),
        write_to=str(clean_source),
        output_width=550,
        output_height=450,
        background_color=None,
    )
    stats, metrics = smooth_mesh_texture(
        clean_source, texture, ASSET_ID, max_width=900
    )
    generation.update({
        "texture_method": "smooth-mesh",
        "texture_origin": "article_vector_smooth_texture",
        "texture_parameters": stats,
        "texture_metrics": metrics,
        "texture_input_file": clean_source.relative_to(LIB).as_posix(),
        "texture_input_sha256": sha256(clean_source),
        "texture_sha256": sha256(texture),
        "context_removed": [
            "perspective background grid",
            "purple electromagnetic field lines",
            "external black radiation arrows",
        ],
    })
    asset["review"]["texture_measurement_note"] = (
        f"smooth-mesh against QGP-only native reference "
        f"MAE={metrics['mae']:.3f}, >32={metrics['gt32']*100:.2f}%"
    )
    INDEX.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = json.loads(METRICS.read_text(encoding="utf-8"))
    report.setdefault("elements", {})[ASSET_ID] = {
        **metrics, "method": "smooth-mesh"
    }
    values = list(report["elements"].values())
    report["count"] = len(values)
    report["median_mae"] = round(
        sorted(v["mae"] for v in values)[len(values) // 2], 4
    )
    report["max_mae"] = max(v["mae"] for v in values)
    report["updated"] = "2026-11-23"
    METRICS.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(clean_source)
    print(texture)
    print(metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
