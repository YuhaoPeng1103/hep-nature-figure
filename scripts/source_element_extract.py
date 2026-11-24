#!/usr/bin/env python3
"""Extract transparent element SVGs from CC BY article figures.

This is the source-derived path. A human supplies the crop box and semantic
labels; the script removes the connected white background, traces the crop with
vtracer, and records source DOI, licence, SHA-256, crop box, and processing.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
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
LIB = ROOT / "assets" / "element-library"
INDEX = LIB / "index.json"
CATALOG = ROOT / "assets" / "schematic-library" / "catalog.json"
OUT = LIB / "source-derived"
TODAY = "2026-11-22"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def transparent_crop(src: Path, bbox: list[int], mask_spec: dict | None = None) -> tuple[object, tuple[int, int, int, int]]:
    import numpy as np
    from PIL import Image, ImageFilter
    im = Image.open(src).convert("RGBA")
    crop = im.crop(tuple(bbox))
    arr = np.asarray(crop)
    if arr.shape[2] == 4 and np.any(arr[:, :, 3] < 250):
        alpha = arr[:, :, 3]
    else:
        rgb = arr[:, :, :3].astype(np.int16)
        border = np.concatenate([
            rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :],
        ], axis=0)
        bg = np.median(border, axis=0)
        dist = np.sqrt(((rgb - bg) ** 2).sum(axis=2))
        candidate = dist < 18
        from scipy.ndimage import label
        labels, n = label(candidate)
        border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
        connected_bg = np.isin(labels, list(border_labels - {0}))
        alpha = np.where(connected_bg, 0, 255).astype(np.uint8)
        alpha_img = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(0.6))
        alpha = np.asarray(alpha_img)
    if mask_spec:
        keep = np.zeros(alpha.shape, dtype=bool)
        shapes = mask_spec.get("shapes", [mask_spec])
        for shape in shapes:
            sb = shape.get("bbox")
            if not sb:
                continue
            x0, y0, x1, y1 = (int(v) for v in sb)
            x0, y0 = x0 - bbox[0], y0 - bbox[1]
            x1, y1 = x1 - bbox[0], y1 - bbox[1]
            if shape.get("type", "ellipse") == "rectangle":
                keep[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
            else:
                cy = (y0 + y1) / 2
                cx = (x0 + x1) / 2
                ry = max(1, (y1 - y0) / 2)
                rx = max(1, (x1 - x0) / 2)
                yy, xx = np.ogrid[:alpha.shape[0], :alpha.shape[1]]
                keep |= (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) <= 1.0
        alpha = np.where(keep, alpha, 0).astype(np.uint8)
        color_filter = mask_spec.get("filter") or {}
        mode = color_filter.get("mode")
        if mode:
            rgb = arr[:, :, :3].astype(np.int16)
            high = rgb.max(axis=2)
            low = rgb.min(axis=2)
            if mode == "saturated_or_dark":
                selected = ((high - low) >= 35) | (high <= 105)
            elif mode == "red":
                selected = (
                    (rgb[:, :, 0] >= 145)
                    & (rgb[:, :, 1] <= 115)
                    & (rgb[:, :, 2] <= 115)
                )
            else:
                raise ValueError(f"unknown color filter mode: {mode}")
            alpha = np.where(selected, alpha, 0).astype(np.uint8)
    out = crop.copy()
    out.putalpha(Image.fromarray(alpha, mode="L"))
    abox = Image.fromarray(alpha, mode="L").getbbox()
    if not abox:
        raise ValueError("crop is empty after background removal")
    pad_x = max(2, round((abox[2] - abox[0]) * 0.03))
    pad_y = max(2, round((abox[3] - abox[1]) * 0.03))
    abox = (max(0, abox[0] - pad_x), max(0, abox[1] - pad_y),
            min(out.width, abox[2] + pad_x), min(out.height, abox[3] + pad_y))
    return out.crop(abox), (bbox[0] + abox[0], bbox[1] + abox[1],
                            bbox[0] + abox[2], bbox[1] + abox[3])


def sanitize_trace(path: Path, asset_id: str) -> list[float]:
    root = ET.parse(path).getroot()
    for parent in root.iter():
        for child in list(parent):
            if local_name(child.tag) in {"image", "script", "foreignObject"}:
                parent.remove(child)
    for node in root.iter():
        for key in list(node.attrib):
            kname = local_name(key).casefold()
            if key.casefold().startswith("on"):
                del node.attrib[key]
            elif kname == "href" and not str(node.attrib[key]).startswith("#"):
                del node.attrib[key]
    root.set("data-element-asset", asset_id)
    if not root.get("viewBox"):
        width = re.match(r"[0-9.]+", root.get("width", ""))
        height = re.match(r"[0-9.]+", root.get("height", ""))
        if not width or not height:
            raise ValueError("vtracer output lacks numeric width/height")
        root.set("viewBox", f"0 0 {float(width.group(0)):g} {float(height.group(0)):g}")
    vb = [float(x) for x in re.split(r"[\s,]+", root.get("viewBox").strip())]
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return vb


def source_meta(source_asset_id: str, manifest: dict | None = None) -> dict:
    doc = json.loads(CATALOG.read_text(encoding="utf-8"))
    item = next((e for e in doc["entries"] if e["asset_id"] == source_asset_id), None)
    if not item and manifest:
        item = (manifest.get("sources") or {}).get(source_asset_id)
    if not item:
        raise SystemExit(f"source asset {source_asset_id} not found in catalog or manifest")
    if not item["license"].get("redistributable"):
        raise SystemExit(f"source asset {source_asset_id} is not redistributable")
    return item


def main():
    ap = argparse.ArgumentParser(description="Extract element SVGs from licensed article figures")
    ap.add_argument("manifest", help="JSON manifest with sources/items")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="remove source-derived assets disabled or absent from the manifest")
    a = ap.parse_args()
    manifest_path = Path(a.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    existing = {x["id"]: x for x in doc.get("assets", [])}
    items = [x for x in manifest.get("items", []) if x.get("enabled", True)]
    active_ids = {x["id"] for x in items}
    if a.prune:
        for aid, asset in list(existing.items()):
            if not str((asset.get("generation") or {}).get("origin", "")).startswith("article_"):
                continue
            if aid in active_ids:
                continue
            for key in ("file", "crop_file"):
                rel = (asset.get("generation") or {}).get(key) or asset.get(key)
                if rel:
                    p = (LIB / rel).resolve()
                    if OUT.resolve() in p.parents and p.exists():
                        p.unlink()
            existing.pop(aid, None)
    try:
        from PIL import Image
        import vtracer
    except ImportError as exc:
        raise SystemExit("source extraction needs Pillow and vtracer") from exc

    created = 0
    for item in items:
        aid = item["id"]
        if aid in existing and not a.replace:
            print(f"skip existing {aid}")
            continue
        src_id = item["source_asset_id"]
        source = source_meta(src_id, manifest)
        quality_note = (manifest.get("source_quality_notes") or {}).get(src_id, "")
        base_image = ROOT / source["local_file"]
        override = (manifest.get("source_overrides") or {}).get(src_id)
        image = ROOT / override if override else base_image
        from PIL import Image as _Image
        base_size = _Image.open(base_image).size
        image_size = _Image.open(image).size
        sx = image_size[0] / base_size[0]
        sy = image_size[1] / base_size[1]

        def scale_box(box):
            return [
                round(box[0] * sx), round(box[1] * sy),
                round(box[2] * sx), round(box[3] * sy),
            ]

        source_bbox = scale_box(item["bbox"])
        coordinate_scale = float(
            item.get("coordinate_scale", source.get("coordinate_scale", 1.0))
        )
        if coordinate_scale != 1.0:
            source_bbox = [round(value * coordinate_scale) for value in source_bbox]
        mask_spec = item.get("mask")
        if mask_spec is None and item.get("family") == "quark":
            mask_spec = {"type": "ellipse", "bbox": source_bbox}
        elif mask_spec:
            mask_spec = json.loads(json.dumps(mask_spec))
            for shape in mask_spec.get("shapes", [mask_spec]):
                if shape.get("bbox"):
                    shape["bbox"] = [
                        round(value * coordinate_scale)
                        for value in scale_box(shape["bbox"])
                    ]
        crop, absolute_bbox = transparent_crop(image, source_bbox, mask_spec)
        category = item.get("category", "source-derived")
        family = item.get("family", aid)
        out = OUT / family / f"{aid}.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        crop_png = out.with_suffix(".source.png")
        crop.save(crop_png)
        vtracer.convert_image_to_svg_py(
            str(crop_png), str(out), colormode="color", hierarchical="stacked",
            mode="spline", filter_speckle=2,
            color_precision=8, layer_difference=6,
            corner_threshold=80, length_threshold=3.0,
            max_iterations=10, splice_threshold=45,
            path_precision=3,
        )
        vb = sanitize_trace(out, aid)
        asset = {
            "id": aid,
            "version": "1.0.0",
            "name_zh": item["name_zh"],
            "family": family,
            "variant": item.get("variant", aid),
            "variant_description": item.get(
                "variant_description",
                f"derived from {source['asset_id']} bbox {absolute_bbox}",
            ),
            "aliases": item.get("aliases", []),
            "category": category,
            "tags": item.get("tags", ["source-derived", "article-vector"]),
            "physics_roles": item.get("physics_roles", [item["name_zh"]]),
            "file": out.relative_to(LIB).as_posix(),
            "viewBox": vb,
            "anchor": [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2],
            "dimensionality": item.get("dimensionality", "mixed"),
            "license": {
                "spdx": source["license"]["spdx"],
                "redistributable": True,
                "attribution": source["license"].get("attribution") or source["title"],
                "source_url": (
                    f"https://doi.org/{source['paper']['doi']}"
                    if source["paper"].get("doi")
                    else f"https://arxiv.org/abs/{source['paper']['arxiv']}"
                    if source["paper"].get("arxiv")
                    else source["license"].get("source_url")
                ),
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
            },
            "generation": {
                "origin": "article_vector_trace",
                "ai_generated": False,
                "contains_ai_pixels": False,
                "tool": "source_element_extract.py + vtracer",
                "model": None,
                "source_asset_id": source["asset_id"],
                "source_sha256": source["sha256"],
                "source_local_file": source["local_file"],
                "source_image": image.relative_to(ROOT).as_posix(),
                "source_image_sha256": sha256(image),
                "source_scale": [round(sx, 6), round(sy, 6)],
                "source_quality_note": quality_note,
                "source_bbox_px": absolute_bbox,
                "crop_file": crop_png.relative_to(LIB).as_posix(),
                "crop_sha256": sha256(crop_png),
                "processing": item.get("processing", "white-background removal; spline tracing"),
            },
            "review": {
                "status": "manual-reviewed",
                "reviewed_by": item.get("reviewed_by", "repository-maintainers"),
                "reviewed_at": item.get("reviewed_at", TODAY),
                "note": item.get("review_note", ""),
            },
            "sha256": sha256(out),
        }
        existing[aid] = asset
        created += 1
        print(f"{aid}: bbox={absolute_bbox} viewBox={vb}")
    doc["assets"] = sorted(existing.values(), key=lambda x: x["id"])
    doc["updated"] = TODAY
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    notice = [
        "# Source-derived element notices",
        "",
        "Only CC BY article figures are represented. Each row records the exact",
        "source asset and crop box used for the transparent SVG derivative.",
        "",
        "| Element | Source asset | Crop px | Licence |",
        "|---|---|---|---|",
    ]
    for asset in doc["assets"]:
        gen = asset.get("generation") or {}
        if gen.get("origin") != "article_vector_trace":
            continue
        notice.append(
            f"| `{asset['id']}` | `{gen['source_asset_id']}` | "
            f"`{gen['source_bbox_px']}` | {asset['license']['spdx']} |"
        )
    notice += [
        "",
        "Source URLs and attributions are stored in each entry's `license` and",
        "`generation` fields. Background removal and vector tracing are modifications.",
        "",
    ]
    (OUT / "NOTICE.md").write_text("\n".join(notice), encoding="utf-8")
    print(f"source-derived assets written: {created}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
