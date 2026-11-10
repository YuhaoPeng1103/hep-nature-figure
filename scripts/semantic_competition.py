#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolve ambiguous same-colour boundaries without changing protected cores."""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage


def load_names(text: str) -> list[str]:
    path = Path(text)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
    return [item.strip() for item in text.split(",") if item.strip()]


def _component_count(mask: np.ndarray) -> int:
    return int(ndimage.label(mask, structure=np.ones((3, 3)))[1])


def preserves_protected_core(candidate: np.ndarray, protected: np.ndarray,
                             label: int) -> bool:
    """Each protected component stays owned and does not split."""
    components, count = ndimage.label(protected, structure=np.ones((3, 3)))
    for index in range(1, count + 1):
        comp = components == index
        if not comp.any():
            continue
        owned = candidate == label
        if not np.all(owned[comp]):
            return False
        inside = owned & ndimage.binary_dilation(comp, iterations=2)
        if _component_count(inside & comp) > 1:
            return False
    return True


def _neighbour_pairs(lab: np.ndarray) -> list[tuple[int, int]]:
    pairs = set()
    for a, b in ((lab[:, :-1], lab[:, 1:]), (lab[:-1], lab[1:])):
        ok = (a >= 0) & (b >= 0) & (a != b)
        for x, y in zip(a[ok].ravel(), b[ok].ravel()):
            pairs.add((min(int(x), int(y)), max(int(x), int(y))))
    return sorted(pairs)


def _robust_model(lab_img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    core = ndimage.binary_erosion(mask, iterations=2)
    points = lab_img[core] if core.any() else lab_img[mask]
    return np.median(points, axis=0)


def resolve_conflicts(src: np.ndarray, lab: np.ndarray, names: list[str],
                      ir_elements: list[dict], pairs: list[dict],
                      band: int = 4, max_area_change: float = 0.15
                      ) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Return an independently reviewable label map and confidence map."""
    from skimage.segmentation import random_walker

    rgb = np.asarray(src, dtype=np.uint8)
    base = np.asarray(lab, dtype=np.int32)
    lab_img = cv2.cvtColor(rgb, cv2.COLOR_RGB2Lab).astype(np.float32)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(gx, gy)
    strong = grad >= max(8.0, float(np.percentile(grad, 90)))
    edge_dist = ndimage.distance_transform_edt(~strong)

    result = base.copy()
    confidence = np.ones(base.shape, dtype=np.float32)
    records: list[dict] = []
    pair_index = {(str(p.get("a", "")), str(p.get("b", ""))): p for p in pairs}
    by_name = {name: idx for idx, name in enumerate(names)}

    candidate_pairs = []
    for ka, kb in _neighbour_pairs(base):
        names_ab = (names[ka], names[kb])
        if names_ab in pair_index:
            candidate_pairs.append((ka, kb, pair_index[names_ab]))
        elif (names_ab[1], names_ab[0]) in pair_index:
            candidate_pairs.append((ka, kb, pair_index[(names_ab[1], names_ab[0])]))

    for ka, kb, _audit in candidate_pairs:
        ma, mb = result == ka, result == kb
        if not ma.any() or not mb.any():
            continue
        core_iters = max(2, min(8, band - 2))
        cores = {
            ka: ndimage.binary_erosion(ma, iterations=core_iters),
            kb: ndimage.binary_erosion(mb, iterations=core_iters),
        }
        near_a = ndimage.binary_dilation(ma, iterations=band)
        near_b = ndimage.binary_dilation(mb, iterations=band)
        roi = (ma & near_b) | (mb & near_a)
        if not roi.any():
            continue
        known = np.zeros(base.shape, dtype=np.int8)
        known[cores[ka]] = 1
        known[cores[kb]] = 2
        if not (known == 1).any() or not (known == 2).any():
            continue
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="The probability range is outside")
                prob = random_walker(lab_img, known, beta=120, mode="cg_j",
                                     return_full_prob=True, channel_axis=-1,
                                     tol=1e-2, prob_tol=1e-2)
            prob = np.clip(prob, 0.0, 1.0)
            proposal = np.where(prob[1] > prob[0], kb, ka).astype(np.int32)
        except Exception as exc:
            records.append({"a": names[ka], "b": names[kb], "status": "rejected",
                            "reason": "solver_failed: %s" % exc})
            continue

        changed = roi & (proposal != base)
        boundary = roi & (
            (ndimage.binary_dilation(proposal == ka, iterations=1)
             & ndimage.binary_dilation(proposal == kb, iterations=1)))
        edge_support = (float((edge_dist[boundary] <= 1.5).mean())
                        if boundary.any() else 0.0)
        trial = result.copy()
        trial[roi] = proposal[roi]
        area_ok = all(
            abs(int((trial == k).sum()) - int((base == k).sum()))
            <= max_area_change * max(1, int((base == k).sum()))
            for k in (ka, kb)
        )
        topology_ok = (preserves_protected_core(trial, cores[ka], ka)
                       and preserves_protected_core(trial, cores[kb], kb))
        local_conf = np.abs(prob[1] - prob[0]).astype(np.float32)
        confidence[roi] = np.minimum(confidence[roi], local_conf[roi])
        accepted = bool(changed.any() and edge_support >= 0.45
                        and area_ok and topology_ok)
        if accepted:
            result = trial
            status, reason = "accepted", "edge_supported"
        else:
            reason = (
                "no_changed_pixels" if not changed.any() else
                "weak_edge" if edge_support < 0.45 else
                "area_change" if not area_ok else
                "topology"
            )
            status = "rejected"
            confidence[roi] = np.minimum(confidence[roi], 0.49)
        records.append({
            "a": names[ka], "b": names[kb], "status": status, "reason": reason,
            "changed_px": int(changed.sum()), "edge_support": round(edge_support, 4),
            "area_change_ok": bool(area_ok), "topology_ok": bool(topology_ok),
        })

    return result, np.clip(confidence, 0.0, 1.0), records


def main() -> int:
    ap = argparse.ArgumentParser(description="resolve same-colour semantic boundaries")
    ap.add_argument("--src", required=True)
    ap.add_argument("--elmap", required=True)
    ap.add_argument("--names", required=True, help="comma list or names file")
    ap.add_argument("--audit-json", default="", help="optional conflict report")
    ap.add_argument("--ir", default="")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--stem", default="semantic")
    ap.add_argument("--band", type=int, default=4)
    ap.add_argument("--max-area-change", type=float, default=0.15)
    a = ap.parse_args()

    src = np.asarray(Image.open(a.src).convert("RGB"), dtype=np.uint8)
    lab = np.load(a.elmap)
    names = load_names(a.names)
    pairs = []
    if a.audit_json:
        report = json.loads(Path(a.audit_json).read_text(encoding="utf-8"))
        pairs = report.get("boundary_pairs") or []
    ir_elements = []
    if a.ir:
        import yaml
        data = yaml.safe_load(Path(a.ir).read_text(encoding="utf-8"))
        ir_elements = data.get("elements") or []
    out, confidence, rows = resolve_conflicts(
        src, lab, names, ir_elements, pairs, a.band, a.max_area_change)
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    np.save(outdir / (a.stem + "_competed.npy"), out)
    np.save(outdir / (a.stem + "_confidence.npy"), confidence)
    (outdir / (a.stem + "_names.txt")).write_text(",".join(names), encoding="utf-8")
    report = {
        "schema": "hep-nature-figure/competition-v1",
        "source": str(Path(a.src).resolve()),
        "elmap": str(Path(a.elmap).resolve()),
        "names": names,
        "unresolved_high_risk": sum(1 for r in rows if r["status"] == "rejected"),
        "pairs": rows,
    }
    (outdir / (a.stem + "_competition.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    base = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY)
    canvas = np.repeat(base[..., None], 3, axis=2)
    canvas = np.clip(canvas * 0.35 + 255 * 0.65, 0, 255).astype(np.uint8)
    changed = out != lab
    canvas[changed] = (230, 40, 40)
    Image.fromarray(canvas).save(outdir / (a.stem + "_competition.png"))
    for rec in rows:
        print("%-18s | %-18s %-8s %-14s changed=%d edge=%.2f"
              % (rec["a"], rec["b"], rec["status"], rec["reason"],
                 rec["changed_px"], rec.get("edge_support", 0.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
