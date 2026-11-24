#!/usr/bin/env python3
"""Create smooth, scalable transparent vector texture companions.

Each article-derived element keeps its native editable SVG and gets a paired
texture SVG for pixel-fidelity review. The native edit SVG remains the default
rendering path for infinite-scale publication output.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

LIB = Path(__file__).resolve().parents[1] / "assets" / "element-library"
INDEX = LIB / "index.json"
METRICS = LIB / "source-derived" / "texture_metrics.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composite_white(image):
    from PIL import Image
    im = image.convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return bg.convert("RGB")


def metrics(src: Path, svg: Path) -> dict:
    import cairosvg
    import numpy as np
    from PIL import Image
    reference = composite_white(Image.open(src))
    rendered = Image.open(io.BytesIO(cairosvg.svg2png(
        bytestring=svg.read_bytes(),
        output_width=reference.width,
        output_height=reference.height,
        background_color="white",
    ))).convert("RGB")
    a = np.asarray(reference, dtype=np.int16)
    b = np.asarray(rendered, dtype=np.int16)
    d = np.abs(a - b)
    channel_max = d.max(axis=2)
    mse = float(np.mean(d.astype(np.float64) ** 2))
    return {
        "mae": round(float(d.mean()), 4),
        "gt8": round(float((channel_max > 8).mean()), 6),
        "gt32": round(float((channel_max > 32).mean()), 6),
        "psnr": round(99.0 if mse == 0 else 20 * math.log10(255 / math.sqrt(mse)), 3),
    }


def shade_texture(src: Path, dst: Path, asset_id: str,
                  max_width: int = 900) -> tuple[dict, dict]:
    """Build a smooth, editable gradient scene from the exact alpha silhouette."""
    import numpy as np
    from PIL import Image

    image = Image.open(src).convert("RGBA")
    width, height = image.size
    with tempfile.TemporaryDirectory(prefix="hep_element_shade_") as td:
        work = Path(td)
        scale = min(1.0, max_width / width)
        work_image = image
        if scale < 1.0:
            work_image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        work_source = work / "source.png"
        work_image.save(work_source)
        work_width, work_height = work_image.size
        alpha = np.asarray(work_image)[:, :, 3]
        np.save(work / "elmap.npy", (alpha > 8).astype(np.uint16))
        (work / "panels.py").write_text(
            "# -*- coding: utf-8 -*-\n"
            f"CELLS=[(\"body\",\"\",\"body\",(0,0,{work_width},{work_height}),\"body\")]\n"
            "ALL=lambda c: True\n"
            f"ELEMENTS={{\"body\":[(\"body\",\"body\",[(0,0,{work_width},{work_height})],ALL)]}}\n"
            "SPLIT={}\n"
            "def order(): return [\"body\"]\n"
            "def meta(): return {\"body\":{\"panel\":\"\",\"role\":\"body\","
            f"\"desc\":\"body\",\"rects\":[(0,0,{work_width},{work_height})]}}}}\n"
            "def cell_index(H,W):\n"
            " import numpy as np\n"
            " return np.zeros((H,W),np.int32)\n"
            "def element_of(cid,bbox,rgb): return (\"body\",\"body\")\n",
            encoding="utf-8",
        )
        generated = work / "texture.svg"
        command = [
            sys.executable,
            str(LIB.parents[1] / "scripts" / "raster_to_vector_semantic.py"),
            str(work_source),
            "-o", str(generated),
            "--panels", str(work / "panels.py"),
            "--elmap-in", str(work / "elmap.npy"),
            "--el-names", "background,body",
            "--W", "0",
            "--R", "4",
            "--K", "8",
            "--no-text",
            "--shade", "2:64",
        ]
        result = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
        if result.returncode != 0 or not generated.exists():
            raise RuntimeError(
                f"raster_to_vector_semantic failed for {asset_id}: "
                f"{(result.stdout + result.stderr)[-2000:]}"
            )
        ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", ns)
        ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")
        tree = ET.parse(generated)
        root = tree.getroot()
        body_found = False
        for parent in root.iter():
            for child in list(parent):
                if child.get("id") == "canvas-background":
                    parent.remove(child)
                elif child.get("data-element") == "background":
                    parent.remove(child)
                elif child.get("data-element") == "body":
                    body_found = True
        if not body_found:
            raise RuntimeError(f"shade output has no body group for {asset_id}")
        root.set("data-element-asset", asset_id)
        root.set("data-origin", "article_vector_smooth_texture")
        root.set("data-texture-backend", "shade")
        tree.write(dst, encoding="utf-8", xml_declaration=True)

    result = metrics(src, dst)
    root = ET.parse(dst).getroot()
    paths = sum(1 for node in root.iter() if node.tag == f"{{{ns}}}path")
    gradients = sum(
        1 for node in root.iter()
        if node.tag in {f"{{{ns}}}linearGradient", f"{{{ns}}}radialGradient"}
    )
    return ({
        "paths": paths,
        "gradients": gradients,
        "source_pixels": width * height,
        "work_scale": round(scale, 6),
    }, result)


def vtracer_texture(src: Path, dst: Path, asset_id: str,
                    max_width: int = 900) -> tuple[dict, dict]:
    """Smooth spline candidate for compact, high-frequency element crops."""
    import vtracer
    from PIL import Image

    image = Image.open(src).convert("RGBA")
    width, height = image.size
    scale = min(1.0, max_width / width)
    with tempfile.TemporaryDirectory(prefix="hep_element_vtrace_") as td:
        work = Path(td)
        work_image = image
        if scale < 1.0:
            work_image = image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        work_source = work / "source.png"
        work_image.save(work_source)
        generated = work / "texture.svg"
        vtracer.convert_image_to_svg_py(
            str(work_source), str(generated),
            colormode="color", hierarchical="stacked", mode="spline",
            filter_speckle=0, color_precision=8, layer_difference=1,
            corner_threshold=72, length_threshold=1.5,
            max_iterations=14, splice_threshold=40, path_precision=3,
        )
        ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", ns)
        tree = ET.parse(generated)
        root = tree.getroot()
        for parent in root.iter():
            for child in list(parent):
                if child.tag.rsplit("}", 1)[-1] in {"image", "script", "foreignObject"}:
                    parent.remove(child)
        group = ET.Element(f"{{{ns}}}g", {"id": asset_id, "data-element": asset_id})
        for child in list(root):
            if child.tag.rsplit("}", 1)[-1] in {"title", "desc"}:
                continue
            root.remove(child)
            group.append(child)
        root.append(group)
        root.set("data-element-asset", asset_id)
        root.set("data-origin", "article_vector_smooth_texture")
        root.set("data-texture-backend", "vtracer-spline")
        if not root.get("viewBox"):
            root.set(
                "viewBox",
                f"0 0 {root.get('width', work_image.width)} "
                f"{root.get('height', work_image.height)}",
            )
        tree.write(dst, encoding="utf-8", xml_declaration=True)
    return ({
        "paths": sum(1 for node in ET.parse(dst).getroot().iter()
                     if node.tag.endswith("path")),
        "work_scale": round(scale, 6),
    }, metrics(src, dst))


def alpha_mask_svg(image, width: int, height: int) -> str:
    """Exact alpha silhouette used only as geometry for the smooth mesh."""
    import cv2
    import numpy as np

    alpha = np.asarray(image.getchannel("A"))
    mask = np.ascontiguousarray((alpha > 0).astype(np.uint8))
    contours, _ = cv2.findContours(
        mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE
    )
    parts = []
    for contour in contours:
        if cv2.contourArea(contour) < 4:
            continue
        points = cv2.approxPolyDP(contour, 0.45, True)[:, 0, :]
        if len(points) >= 3:
            parts.append(
                "M" + " L".join(f"{int(x)} {int(y)}" for x, y in points) + " Z"
            )
    path = " ".join(parts)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        '<g id="body" data-element="body">'
        f'<path d="{path}" fill="#000"/></g></svg>\n'
    )


def clean_white_matte(image):
    """Recover transparency from a crop that was keyed out only by an outer shape.

    Several publisher crops have a valid silhouette but keep opaque white
    canvas, labels or axes inside it. On a white page those pixels are
    invisible; on a tinted panel they become obvious white rectangles.
    """
    import cv2
    import numpy as np
    from PIL import Image

    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rgb = rgba[:, :, :3]
    source_alpha = rgba[:, :, 3] / 255.0
    # White-background matte: white has zero coverage, black has unit coverage.
    coverage = np.clip((255.0 - rgb.min(axis=2)) / 255.0, 0.0, 1.0)
    alpha = np.clip(source_alpha * coverage, 0.0, 1.0)
    safe = np.maximum(alpha[:, :, None], 1.0 / 255.0)
    foreground = np.clip(255.0 + (rgb - 255.0) / safe, 0.0, 255.0)

    mask = (alpha > 1.0 / 255.0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count > 1:
        largest = max(int(stats[index, cv2.CC_STAT_AREA])
                      for index in range(1, count))
        minimum = max(24, int(round(largest * 0.005)))
        keep = np.zeros(count, dtype=bool)
        for index in range(1, count):
            keep[index] = stats[index, cv2.CC_STAT_AREA] >= minimum
        alpha[~keep[labels]] = 0.0

    cleaned = np.empty_like(rgba)
    cleaned[:, :, :3] = foreground
    cleaned[:, :, 3] = np.rint(alpha * 255.0)
    cleaned[cleaned[:, :, 3] == 0] = 0
    return Image.fromarray(cleaned.astype(np.uint8), "RGBA")


def smooth_mesh_texture(src: Path, dst: Path, asset_id: str,
                        max_width: int = 900) -> tuple[dict, dict]:
    """Build a continuous two-dimensional gradient mesh from exact alpha geometry."""
    from PIL import Image

    image = Image.open(src).convert("RGBA")
    width, height = image.size
    scale = min(1.0, max_width / max(width, height))
    work_image = clean_white_matte(image)
    if scale < 1.0:
        work_image = work_image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
    work_width, work_height = work_image.size
    longest = max(work_width, work_height)
    cell = 1 if longest <= 180 else 2 if longest <= 700 else 3 if longest <= 1100 else 4
    detail_cell = 1 if longest <= 700 else 2
    with tempfile.TemporaryDirectory(prefix="hep_element_mesh_") as td:
        work = Path(td)
        trace = work / "alpha_trace.svg"
        trace.write_text(
            alpha_mask_svg(work_image, work_width, work_height),
            encoding="utf-8",
        )
        work_source = work / "source.png"
        work_image.save(work_source)
        generated = work / f"{asset_id}_mesh.svg"
        command = [
            sys.executable,
            str(LIB.parents[1] / "scripts" / "shade_smooth.py"),
            "--src", str(work_source),
            "--trace", str(trace),
            "--stem", asset_id,
            "--outdir", str(work),
            "--size", f"{work_width}x{work_height}",
            "--cell", f"default={cell}",
            "--dc", str(detail_cell),
            "--tile", "48",
            "--thr", "2",
            "--mind", "1",
            "--feather", "1.5",
            "--no-text",
            "--transparent-background",
            "--bake-clips",
        ]
        result = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=1800,
        )
        if result.returncode != 0 or not generated.exists():
            raise RuntimeError(
                f"smooth mesh failed for {asset_id}: "
                f"{(result.stdout + result.stderr)[-2000:]}"
            )
        ns = "http://www.w3.org/2000/svg"
        ET.register_namespace("", ns)
        tree = ET.parse(generated)
        root = tree.getroot()
        root.set("width", str(work_width))
        root.set("height", str(work_height))
        root.set("viewBox", f"0 0 {work_width} {work_height}")
        root.set("data-element-asset", asset_id)
        root.set("data-origin", "article_vector_smooth_texture")
        root.set("data-texture-backend", "smooth-gradient-mesh")
        root.set("data-alpha-geometry", "exact-rgba-silhouette")
        tree.write(dst, encoding="utf-8", xml_declaration=True)

    root = ET.parse(dst).getroot()
    paths = sum(1 for node in root.iter() if node.tag.endswith("path"))
    gradients = sum(
        1 for node in root.iter() if node.tag.endswith("linearGradient")
    )
    return ({
        "paths": paths,
        "gradients": gradients,
        "cell_px": cell,
        "detail_cell_px": detail_cell,
        "source_pixels": width * height,
        "work_scale": round(scale, 6),
    }, metrics(src, dst))


def ensure_edit_path(asset: dict) -> Path:
    gen = asset.setdefault("generation", {})
    current = LIB / asset["file"]
    existing = gen.get("edit_file")
    if existing and (LIB / existing).exists():
        return LIB / existing
    edit = current.with_name(current.stem + "_edit.svg")
    if current.exists() and current.resolve() != edit.resolve():
        current.replace(edit)
    gen["edit_file"] = edit.relative_to(LIB).as_posix()
    return edit


def normalize_texture_svg(path: Path, method: str) -> None:
    if not path.exists():
        return
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ET.parse(path)
    root = tree.getroot()
    root.set("data-origin", "article_vector_smooth_texture")
    root.set(
        "data-texture-backend",
        "shade" if method == "shade"
        else "vtracer-spline" if method == "vtracer"
        else "smooth-gradient-mesh",
    )
    tree.write(path, encoding="utf-8", xml_declaration=True)


def vectorize_job(crop: Path, texture: Path, asset_id: str,
                  max_width: int) -> tuple[dict, dict, str]:
    from PIL import Image
    width, height = Image.open(crop).size
    candidates = []
    shade = texture.with_name(texture.stem + ".shade.svg")
    try:
        stats, metric = shade_texture(crop, shade, asset_id, max_width=max_width)
        candidates.append((metric["mae"], shade, stats, metric, "shade"))
    except Exception:
        shade.unlink(missing_ok=True)
    if width * height <= 500_000:
        vtrace = texture.with_name(texture.stem + ".vtracer.svg")
        try:
            stats, metric = vtracer_texture(crop, vtrace, asset_id, max_width=max_width)
            candidates.append((metric["mae"], vtrace, stats, metric, "vtracer"))
        except Exception:
            vtrace.unlink(missing_ok=True)
    smooth = texture.with_name(texture.stem + ".mesh.svg")
    try:
        stats, metric = smooth_mesh_texture(
            crop, smooth, asset_id, max_width=max_width
        )
        candidates.append((metric["mae"], smooth, stats, metric, "smooth-mesh"))
    except Exception:
        smooth.unlink(missing_ok=True)
    if not candidates:
        raise RuntimeError(f"both vector backends failed for {asset_id}")
    _mae, winner, stats, metric, method = min(candidates, key=lambda row: row[0])
    if texture.exists():
        texture.unlink()
    winner.replace(texture)
    for _mae2, candidate, _stats, _metric, _method in candidates:
        candidate.unlink(missing_ok=True)
    return stats, metric, method


def main() -> int:
    ap = argparse.ArgumentParser(description="Build low-error vector texture companions")
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-width", type=int, default=900,
                    help="working width; 900 px covers 38 mm at about 600 dpi")
    ap.add_argument("--area-max", type=int, default=0,
                    help="refresh only crops at or below this source-pixel count")
    a = ap.parse_args()
    try:
        import cairosvg  # noqa: F401
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        raise SystemExit("texture vectorization needs cairosvg, numpy and Pillow") from exc

    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    wanted = set(a.ids)
    targets = [
        asset for asset in doc["assets"]
        if (not wanted or asset["id"] in wanted)
        and str((asset.get("generation") or {}).get("origin", "")).startswith("article_vector_")
        and (asset.get("generation") or {}).get("crop_file")
    ]
    if a.check:
        print("\n".join(asset["id"] for asset in targets))
        return 0

    results = {}
    pending = []
    for asset in targets:
        gen = asset.setdefault("generation", {})
        crop = LIB / gen["crop_file"]
        if not crop.exists():
            print(f"WARN {asset['id']}: missing crop {crop}", file=sys.stderr)
            continue
        edit = ensure_edit_path(asset)
        texture = edit.with_name(edit.stem.removesuffix("_edit") + "_texture.svg")
        if a.area_max:
            with Image.open(crop) as source_image:
                if source_image.width * source_image.height > a.area_max:
                    if gen.get("texture_metrics"):
                                results[asset["id"]] = {
                                    **gen["texture_metrics"],
                                    "method": gen.get("texture_method"),
                                }
                    continue
        if texture.exists() and not a.force and gen.get("texture_metrics"):
            normalize_texture_svg(texture, str(gen.get("texture_method") or ""))
            gen["texture_origin"] = "article_vector_smooth_texture"
            gen["texture_sha256"] = sha256(texture)
            results[asset["id"]] = {
                **gen["texture_metrics"],
                "method": gen.get("texture_method"),
            }
            continue
        pending.append((asset, crop, edit, texture))

    failures = {}
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(8, a.workers))
    ) as pool:
        futures = {
            pool.submit(
                vectorize_job, crop, texture, asset["id"], a.max_width
            ): (asset, edit, texture)
            for asset, crop, edit, texture in pending
        }
        for future in concurrent.futures.as_completed(futures):
            asset, edit, texture = futures[future]
            completed += 1
            gen = asset.setdefault("generation", {})
            try:
                encode_stats, result, texture_method = future.result()
            except Exception as exc:
                failures[asset["id"]] = str(exc)
                print(f"WARN {asset['id']}: {exc}", file=sys.stderr, flush=True)
                continue
            edit_sha = sha256(edit)
            texture_sha = sha256(texture)
            gen.update({
                # `origin` describes the default/public path. A texture companion
                # must never make index.json point back to the traced fidelity copy.
                "origin": gen.get("origin") or "article_vector_native",
                "native_origin": "article_vector_native",
                "edit_file": edit.relative_to(LIB).as_posix(),
                "texture_file": texture.relative_to(LIB).as_posix(),
                "texture_origin": "article_vector_smooth_texture",
                "texture_method": texture_method,
                "texture_parameters": encode_stats,
                "texture_metrics": result,
                "texture_crop_sha256": sha256(crop),
                "edit_sha256": edit_sha,
                "texture_sha256": texture_sha,
                "ai_generated": False,
                "contains_ai_pixels": False,
            })
            asset["file"] = edit.relative_to(LIB).as_posix()
            asset["sha256"] = edit_sha
            vb_match = re.search(
                r'viewBox="([^"]+)"',
                edit.read_text(encoding="utf-8"),
            )
            if vb_match:
                asset["viewBox"] = [
                    float(x) for x in re.split(r"[\s,]+", vb_match.group(1))
                ]
                asset["anchor"] = [
                    asset["viewBox"][0] + asset["viewBox"][2] / 2,
                    asset["viewBox"][1] + asset["viewBox"][3] / 2,
                ]
            review = asset.setdefault("review", {})
            review["texture_metrics_status"] = "measured"
            review["texture_measured_at"] = "2026-11-23"
            review["texture_measurement_note"] = (
                f"{texture_method} MAE={result['mae']:.3f}, "
                f">32={result['gt32']*100:.2f}%"
            )
            results[asset["id"]] = {**result, "method": texture_method}
            print(
                f"[{completed}/{len(pending)}] {asset['id']}: "
                f"MAE={result['mae']:.3f}, >8={result['gt8']*100:.2f}%, "
                f">32={result['gt32']*100:.2f}%, paths={encode_stats['paths']}, "
                f"backend={texture_method}, "
                f"scale={encode_stats['work_scale']:.3f}",
                flush=True,
            )

    doc["updated"] = "2026-11-22"
    # Normalize the public entry point even when all textures were already
    # present and this run only refreshed metadata or selected a subset.
    for asset in doc["assets"]:
        gen = asset.get("generation") or {}
        if not str(gen.get("origin", "")).startswith("article_vector_"):
            continue
        edit_rel = gen.get("edit_file")
        if not edit_rel:
            continue
        edit = LIB / edit_rel
        if not edit.exists():
            continue
        asset["file"] = edit_rel
        asset["sha256"] = sha256(edit)
        if gen.get("texture_file"):
            gen["texture_origin"] = "article_vector_smooth_texture"
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    previous_metrics = {}
    if METRICS.exists():
        try:
            previous_metrics = json.loads(
                METRICS.read_text(encoding="utf-8")
            ).get("elements", {})
        except (OSError, ValueError, AttributeError):
            previous_metrics = {}
    all_metrics = {**previous_metrics, **results}
    METRICS.write_text(json.dumps({
        "schema_version": "1.0",
        "updated": "2026-11-22",
        "count": len(all_metrics),
        "median_mae": round(
            sorted(v["mae"] for v in all_metrics.values())
            [len(all_metrics) // 2], 4
        ) if all_metrics else None,
        "max_mae": max(
            (v["mae"] for v in all_metrics.values()), default=None
        ),
        "elements": all_metrics,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metric_lines = [
        "# Smooth scalable texture pixel-error report",
        "",
        "| Element | MAE | >8 | >32 | PSNR |",
        "|---|---:|---:|---:|---:|",
    ]
    for asset_id, value in sorted(all_metrics.items()):
        metric_lines.append(
            f"| `{asset_id}` | {value['mae']:.4f} | "
            f"{value['gt8']*100:.2f}% | {value['gt32']*100:.2f}% | "
            f"{value['psnr']:.2f} dB |"
        )
    metric_lines.append("")
    METRICS.with_suffix(".md").write_text(
        "\n".join(metric_lines), encoding="utf-8"
    )
    notice = [
        "# Source-derived element notices",
        "",
        "All article-derived elements have paired `_texture.svg` and `_edit.svg`",
        "files. The edit version is the default infinitely scalable SVG; the",
        "texture version is an optional smooth-path fidelity reference and is",
        "never selected by `index.json.file`.",
        "",
        "| Element | Source asset | Crop px | Texture MAE | >32 |",
        "|---|---|---|---:|---:|",
    ]
    for asset in doc["assets"]:
        gen = asset.get("generation") or {}
        if not gen.get("texture_file"):
            continue
        m = gen.get("texture_metrics") or {}
        notice.append(
            f"| `{asset['id']}` | `{gen.get('source_asset_id', '')}` | "
            f"`{gen.get('source_bbox_px', '')}` | {m.get('mae', '')} | "
            f"{m.get('gt32', '')} |"
        )
    notice.append("")
    (LIB / "source-derived" / "NOTICE.md").write_text(
        "\n".join(notice), encoding="utf-8"
    )
    print(f"texture vectors: {len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
