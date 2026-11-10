#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit semantic label boundaries before vector reconstruction.

This does not invent a new segmentation model.  It makes the unresolved cases
explicit with three measurable checks:

  colour competition  - do the two class colour models disagree enough?
  edge support        - is the proposed boundary backed by an image edge?
  z order             - can declared element overlaps be reconciled with the IR?

Outputs a JSON report and a conflict overlay.  ``--strict`` treats high-risk
boundaries as a failed audit.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage


def load_names(text: str) -> list[str]:
    p = Path(text)
    if p.exists():
        text = p.read_text(encoding="utf-8").strip()
    return [x.strip() for x in text.split(",") if x.strip()]


def ir_z_map(path: str) -> tuple[dict[str, float], list[dict]]:
    if not path:
        return {}, []
    import yaml
    data = yaml.safe_load(io.open(path, encoding="utf-8"))
    elements = data.get("elements") or []
    zmap = {}
    for elem in elements:
        eid = str(elem.get("id", "")).strip()
        if eid:
            zmap[eid] = float(elem.get("z", 0))
    return zmap, elements


def resolve_ir_name(name: str, elements: list[dict]) -> str:
    for elem in elements:
        eid = str(elem.get("id", ""))
        ename = str(elem.get("name", ""))
        if name == eid or (eid and eid in name):
            return eid
        if ename and (ename in name or name in ename):
            return eid
    return ""


def unpack_mask(value: np.ndarray, width: int, height: int) -> np.ndarray:
    if value.dtype == np.bool_ and value.shape == (height, width):
        return value
    if value.size == width * height:
        return value.reshape(height, width).astype(bool)
    raw = np.unpackbits(np.asarray(value, dtype=np.uint8))[:width * height]
    return raw.reshape(height, width).astype(bool)


def neighbour_pairs(lab: np.ndarray) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        if dy == 0:
            a = lab[:, :-dx]
            b = lab[:, dx:]
        elif dx > 0:
            a = lab[:-dy, :-dx]
            b = lab[dy:, dx:]
        elif dx == 0:
            a = lab[:-dy, :]
            b = lab[dy:, :]
        else:
            a = lab[:-dy, -dx:]
            b = lab[dy:, :dx]
        ok = (a >= 0) & (b >= 0) & (a != b)
        for x, y in zip(a[ok].ravel(), b[ok].ravel()):
            pair = (min(int(x), int(y)), max(int(x), int(y)))
            counts[pair] = counts.get(pair, 0) + 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description="audit same-colour, edge, and z-order ambiguity")
    ap.add_argument("--src", required=True, help="source bitmap")
    ap.add_argument("--elmap", required=True, help="integer label map .npy")
    ap.add_argument("--names", required=True, help="comma list or el_names_z.txt")
    ap.add_argument("--ir", default="", help="optional IR for z-order checks")
    ap.add_argument("--vis-npz", default="",
                    help="optional per-element visible masks with packed bit arrays")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--stem", default="semantic")
    ap.add_argument("--band", type=int, default=3)
    ap.add_argument("--same-delta", type=float, default=18.0)
    ap.add_argument("--colour-margin", type=float, default=3.0)
    ap.add_argument("--edge-band", type=float, default=1.5,
                    help="a boundary is supported when its distance to a strong edge is <= this")
    ap.add_argument("--overlap-min", type=int, default=8)
    ap.add_argument("--json", default="")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    src = np.asarray(Image.open(a.src).convert("RGB"), dtype=np.uint8)
    lab = np.load(a.elmap)
    names = load_names(a.names)
    if lab.shape[:2] != src.shape[:2]:
        raise SystemExit("elmap %s != source %s" % (lab.shape[:2], src.shape[:2]))
    if int(lab.max(initial=-1)) >= len(names):
        raise SystemExit("elmap has label %s but only %d names" % (lab.max(), len(names)))

    rgb = src.astype(np.float32) / 255.0
    lab_img = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab)
    gray = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    strong = grad >= max(8.0, float(np.percentile(grad, 90)))
    edge_dist = ndimage.distance_transform_edt(~strong)

    models = {}
    for k, name in enumerate(names):
        mask = lab == k
        core = ndimage.binary_erosion(mask, iterations=2)
        pts = lab_img[core if core.sum() >= 16 else mask]
        if len(pts):
            models[k] = np.median(pts, axis=0)

    pair_counts = neighbour_pairs(lab)
    rows = []
    conflict_pixels = {
        "same_colour": np.zeros(lab.shape, bool),
        "weak_edge": np.zeros(lab.shape, bool),
        "colour_competition": np.zeros(lab.shape, bool),
        "z_overlap": np.zeros(lab.shape, bool),
    }
    for (ka, kb), n_border in sorted(pair_counts.items(), key=lambda x: -x[1]):
        if ka not in models or kb not in models:
            continue
        ma, mb = lab == ka, lab == kb
        band = ((ma & ndimage.binary_dilation(mb, iterations=a.band))
                | (mb & ndimage.binary_dilation(ma, iterations=a.band)))
        if not band.any():
            continue
        da = np.linalg.norm(lab_img - models[ka], axis=2)
        db = np.linalg.norm(lab_img - models[kb], axis=2)
        competes = ((ma & (db + a.colour_margin < da))
                    | (mb & (da + a.colour_margin < db))) & band
        edge_ok = band & (edge_dist <= a.edge_band)
        weak = band & ~edge_ok
        colour_delta = float(np.linalg.norm(models[ka] - models[kb]))
        comp_frac = float(competes.sum()) / max(1, int(band.sum()))
        edge_frac = float(edge_ok.sum()) / max(1, int(band.sum()))
        same = colour_delta <= a.same_delta
        score = (1.0 if same else 0.0) * 0.45 + comp_frac * 0.35 + (1.0 - edge_frac) * 0.20
        severe = (same and comp_frac >= 0.20 and edge_frac < 0.65) or score >= 0.70
        severity = "high" if severe else ("medium" if score >= 0.45 else "low")
        rows.append(dict(
            a=names[ka], b=names[kb], border_px=n_border,
            band_px=int(band.sum()), colour_delta=round(colour_delta, 2),
            same_colour=bool(same), colour_competition=round(comp_frac, 4),
            edge_supported=round(edge_frac, 4), risk=round(score, 4), severity=severity,
            action=(
                "manual confirmation required"
                if severe else
                "review if the objects are physically distinct"
                if same else
                "no colour conflict"
            ),
        ))
        if same:
            conflict_pixels["same_colour"] |= band
        conflict_pixels["weak_edge"] |= weak
        conflict_pixels["colour_competition"] |= competes

    overlap_rows = []
    if a.vis_npz:
        zmap, ir_elements = ir_z_map(a.ir)
        vis = np.load(a.vis_npz, allow_pickle=True)
        masks = {}
        for key in vis.files:
            name = str(key)
            eid = resolve_ir_name(name, ir_elements)
            if eid or not ir_elements:
                masks[name] = unpack_mask(vis[key], lab.shape[1], lab.shape[0])
        keys = list(masks)
        for i, na in enumerate(keys):
            for nb in keys[i + 1:]:
                ov = masks[na] & masks[nb]
                n = int(ov.sum())
                if n < a.overlap_min:
                    continue
                ia = resolve_ir_name(na, ir_elements)
                ib = resolve_ir_name(nb, ir_elements)
                za = zmap.get(ia)
                zb = zmap.get(ib)
                expected = None if za is None or zb is None else (ia if za >= zb else ib)
                overlap_rows.append(dict(a=na, b=nb, overlap_px=n,
                                         z_a=za, z_b=zb, expected_front=expected))
                conflict_pixels["z_overlap"] |= ov

    high = [r for r in rows if r["severity"] == "high"]
    report = dict(
        schema="hep-nature-figure/conflicts-v1",
        source=str(Path(a.src).resolve()),
        elmap=str(Path(a.elmap).resolve()),
        names=names,
        config=dict(band=a.band, same_delta=a.same_delta,
                    colour_margin=a.colour_margin, edge_band=a.edge_band),
        boundary_pairs=rows,
        overlaps=overlap_rows,
        high_risk_pairs=high,
        interpretation=(
            "same_colour/weak_edge identify where colour or contour evidence cannot decide "
            "ownership; expected_front from IR is a constraint, not visible pixel evidence"
        ),
    )
    jpath = Path(a.json) if a.json else outdir / (a.stem + "_conflicts.json")
    jpath.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    canvas = np.repeat(gray[..., None], 3, axis=2)
    canvas = (canvas * 0.35 + 255 * 0.65).astype(np.uint8)
    colors = {
        "same_colour": (230, 40, 40),
        "weak_edge": (245, 170, 30),
        "colour_competition": (180, 50, 220),
        "z_overlap": (30, 190, 220),
    }
    for key, color in colors.items():
        m = conflict_pixels[key]
        canvas[m] = (0.25 * canvas[m] + 0.75 * np.asarray(color)).astype(np.uint8)
    ipath = outdir / (a.stem + "_conflicts.png")
    Image.fromarray(canvas).save(ipath)

    print("boundary pairs: %d, high risk: %d" % (len(rows), len(high)))
    for r in rows[:20]:
        print("  %-18s | %-18s %-6s dColour=%6.2f compete=%.2f edge=%.2f risk=%.2f"
              % (r["a"], r["b"], r["severity"], r["colour_delta"],
                 r["colour_competition"], r["edge_supported"], r["risk"]))
    if overlap_rows:
        print("declared overlaps: %d (see %s)" % (len(overlap_rows), jpath))
    print("wrote %s\nwrote %s" % (jpath, ipath))
    if a.strict and high:
        print("STRICT: unresolved high-risk semantic boundaries remain")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
