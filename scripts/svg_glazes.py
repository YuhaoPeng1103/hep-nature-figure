"""Fit smooth SVG color glazes to one object's material field."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

import numpy as np


OFFSETS = np.array([0, .13, .26, .39, .52, .65, .78, .9, 1])
FALLOFF = np.exp(-4.5 * OFFSETS**2)
FALLOFF = (FALLOFF - FALLOFF[-1]) / (1 - FALLOFF[-1])
PEAK_ALPHA = .69


@dataclass(frozen=True)
class Scale:
    sigma: float
    spacing: int
    passes: int
    cutoff: float


@dataclass(frozen=True)
class Glaze:
    cx: float
    cy: float
    radius: float
    color: tuple[int, int, int]

    def svg(self, id, *, convex_outline=None):
        """Return (gradient, visible shape), clipping only crossing supports.

        The outline is a convex polygon in the same scene coordinates. For
        concave surfaces use the object's own SVG clip or a Boolean geometry
        backend that can preserve disjoint components and holes.
        """
        if not re.fullmatch(r"[A-Za-z_][\w.-]*", id):
            raise ValueError("invalid SVG gradient id")
        cx, cy, radius = self.cx, self.cy, self.radius
        contour = None
        if convex_outline is not None:
            import cv2

            outline = np.asarray(convex_outline, dtype=np.float32).reshape(-1, 2)
            if len(outline) < 3 or not cv2.isContourConvex(outline):
                raise ValueError("glaze outline must be convex")
            distance = cv2.pointPolygonTest(outline, (cx, cy), True)
            if distance <= -radius:
                return "", ""
            if distance < radius:
                count = max(48, math.ceil(math.tau * radius / 2))
                angle = np.arange(count) * math.tau / count
                disk = np.column_stack((cx + radius * np.cos(angle), cy + radius * np.sin(angle)))
                area, intersection = cv2.intersectConvexConvex(disk.astype(np.float32), outline)
                if intersection is None or area <= 0:
                    return "", ""
                contour = intersection.reshape(-1, 2)
        paint = "#{:02x}{:02x}{:02x}".format(*self.color)
        stops = "".join(
            f'<stop offset="{p:.2f}" stop-color="{paint}" stop-opacity="{PEAK_ALPHA * a:.4f}"/>'
            for p, a in zip(OFFSETS, FALLOFF)
        )
        gradient = (f'<radialGradient id="{id}" gradientUnits="userSpaceOnUse" '
                    f'cx="{cx:.3f}" cy="{cy:.3f}" r="{radius:.3f}">{stops}</radialGradient>')
        if contour is None:
            shape = f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{radius:.3f}" fill="url(#{id})"/>'
        else:
            path = "M" + "L".join(f"{x:.3f} {y:.3f}" for x, y in contour) + "Z"
            shape = f'<path d="{path}" fill="url(#{id})"/>'
        return gradient, shape


def fit_glazes(target, base, weight, scales, *, origin=(0, 0), seed=0):
    """Fit material RGB (0–255) with visibility weights (0–1).

    The scene author separates material from the composited image before
    calling. Pixels owned by foreground geometry get weight zero. The fit
    adds translucent radial gradients to the supplied complete material base.
    """
    target = np.asarray(target, dtype=np.float32)
    current = np.array(base, dtype=np.float32, copy=True)
    weight = np.asarray(weight, dtype=np.float32)
    if target.ndim != 3 or target.shape[2] != 3 or target.shape != current.shape or target.shape[:2] != weight.shape:
        raise ValueError("target, base, and weight must share one nonempty RGB material viewport")
    if (not target.size or not all(np.isfinite(field).all() for field in (target, current, weight))
            or weight.min() < 0 or weight.max() > 1):
        raise ValueError("expected finite RGB arrays and visibility weights from 0 to 1")

    rng = np.random.default_rng(seed)
    height, width = weight.shape
    ox, oy = origin
    glazes = []
    for scale in scales:
        if not math.isfinite(scale.sigma) or scale.sigma <= 0 or min(scale.spacing, scale.passes) < 1 or scale.cutoff < 0:
            raise ValueError("invalid glaze fit scale")
        radius = 3 * scale.sigma
        half = math.ceil(radius)
        index = np.arange(-half, half + 1)
        distance = np.hypot(index[:, None], index[None, :]) / radius
        kernel = (PEAK_ALPHA * np.interp(distance, OFFSETS, FALLOFF)).astype(np.float32)
        anchors = np.array([(x, y) for y in range(0, height, scale.spacing)
                            for x in range(0, width, scale.spacing)])
        step = max(1, scale.spacing // 4)
        for _ in range(scale.passes):
            for i in rng.permutation(len(anchors)):
                x, y = np.clip(anchors[i] + rng.integers(-step, step + 1, size=2), (0, 0), (width - 1, height - 1))
                left, right = max(0, x - half), min(width, x + half + 1)
                top, bottom = max(0, y - half), min(height, y + half + 1)
                region = np.s_[top:bottom, left:right]
                k = kernel[top - y + half:bottom - y + half, left - x + half:right - x + half]
                confidence = weight[region]
                influence = k * confidence
                normalization = (k * influence).sum()
                if normalization < 1:
                    continue
                apparent = current[region]
                residual = target[region] - apparent
                needed = np.einsum("ij,ijc->c", influence, residual)
                mass = influence.sum()
                if np.max(np.abs(needed)) < scale.cutoff * mass:
                    continue
                local = np.einsum("ij,ijc->c", k * influence, apparent)
                ink = np.clip(np.rint((local + needed) / normalization), 0, 255).astype(int)
                change = (ink - apparent) * k[..., None]
                improvement = (confidence[..., None] * change * (2 * residual - change)).sum()
                if improvement <= scale.cutoff**2 * mass:
                    continue
                apparent += change
                glazes.append(Glaze(float(ox + x + .5), float(oy + y + .5), radius, tuple(map(int, ink))))
    return glazes
