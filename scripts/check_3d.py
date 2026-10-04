# -*- coding: utf-8 -*-
# ★ 版式标定说明（入库时加的）：下面 C1–C4 的**判据**与版式无关，但三处**搜索窗口**
#   是按「一个中心有星芒的暖色圆盘（火球）+ 一圈方位分布」这个版式标定的：
#     · W_MM, H_MM —— 画布毫米尺寸；
#     · WHEEL       —— 受检形体的搜索窗（x0, x1, y0, y1，毫米）；
#     · orange      —— 受检形体的颜色谓词（暖色 R 通道占优）。
#   换版式**必须先改这三处**（改成你这个版式的窗口/颜色），否则会报
#   「no orange body found」而判 C0 失败 —— 它**失败得响**，不会静默放行。
"""check_3d.py -- gate #6: does the raster read as a SOLID, or as a sticker?

    python3 scripts/check_3d.py collective_flow/out/collective_flow_v8.png

WHY A SEPARATE GATE.  The five Skill gates cannot see this failure at all: the
flat v7 candidate (collective_flow/out/collective_flow.png) and the 3D v7
bitmap both pass them, and the style gate's whitelist has no metric that
measures *rendering mode* -- colour_richness / gradient_ratio are marked
untrustworthy by the Skill itself, and the ink metrics turn out to measure
detail density plus type area, not shading.  So the four cues below are
measured directly on the pixels instead.

FOUR HARD CRITERIA (each one is a thing a flat vector drawing cannot have):

  C1  CONTACT.  The body must darken the slab it stands on.  A radial ramp
      cannot do this: it stops at the silhouette.
                                   v7: 1.2% darker (noise)     -> FAIL
  C2  IN-PLANE CONTENT IS PROJECTED.  The 20 azimuths are laid out in the wheel
      plane, so their screen spacing is uneven.  A printed starburst is
      perfectly even.
                                   v7: 18.00 +- 0.24 deg        -> FAIL
  C3  ONE COHERENT PLANE.  The isotropic reference is drawn IN the wheel plane,
      so it is squashed, not round -- that is what makes the foreshortening in
      C2 read as perspective rather than as an arbitrary squash of the data.
                                   v7: 1.000 (round)            -> FAIL
  C4  VOLUME SHADING.  The brightest point is OFF-CENTRE and the rim is darker
      than the mid-radius, i.e. the shading carries a normal field and not just
      a "hot centre" glow.  (v7 already satisfies this one; it is kept because a
      gate that only reproduces the v7 diagnosis is not a checklist.)

The design anchors below are canvas-millimetre SEARCH WINDOWS only.  Every
number that is asserted is measured off the raster inside them.
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

W_MM, H_MM = 183.0, 100.0
LIGHT = np.array([-0.62, -0.78])       # unit vector pointing TO the key light
DARK = -LIGHT                           # the side the wall must stick out on

WHEEL = (118.0, 170.0, 34.0, 68.0)      # x0, x1, y0, y1 -- momentum scene only
BODY_BOTTOM_PAD = 1.20                  # mm: first row under the body
BODY_BOTTOM_BAND = 1.80                 # mm: depth of the contact-shadow strip

TH_C1_SHADOW = 0.985                    # strip under the body / clear slab
TH_C2_STEP_SD = 0.80                    # deg
TH_C3_REF_ASPECT = 1.060                # squashed reference circle
TH_C4_OFFCENTRE = 0.08                  # brightest point, mm from the centre
TH_C4_LIMB = 0.05                       # rim darker than mid-radius, luminance
MAX_RUN_GAP = 3                         # deg: one bin of a spoke may drop out

report: list[str] = []
fails: list[str] = []
n_check = [0]


def say(s: str = "") -> None:
    report.append(s)


def check(ok: bool, label: str, detail: str) -> None:
    n_check[0] += 1
    say("  [%s] %-58s %s" % ("ok  " if ok else "FAIL", label, detail))
    if not ok:
        fails.append("%s (%s)" % (label, detail))


def title(s: str) -> None:
    say()
    say(s)
    say("-" * 78)


def main(path: Path) -> int:
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float64)
    hpx, wpx = a.shape[:2]
    s = wpx / W_MM                        # px per mm
    lum = (0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]) / 255.0
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    say("check_3d  %s  (%d x %d px, %.2f px/mm, %.1f x %.1f mm)"
        % (path.name, wpx, hpx, s, wpx / s, hpx / s))

    # ---------------------------------------------------------- the body ---
    win = np.zeros_like(lum, dtype=bool)
    x0, x1, y0, y1 = WHEEL
    win[int(y0 * s):int(y1 * s), int(x0 * s):int(x1 * s)] = True
    # Warm AND saturated: the soft outer glow (#ffb648 at ~50% over paper) has
    # r-b ~ 91 but r-g ~ 36, so it must not count as body -- otherwise the mask
    # is a symmetric halo and C1 can never see the wall.
    orange = (r > 140) & (r - b > 80) & (r - g > 55) & win
    ys, xs = np.nonzero(orange)
    if len(xs) < 500:
        say("  ! no orange body found in the momentum window %s" % (WHEEL,))
        fails.append("C0 body not found")
        return finish()
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    cx, cy = 0.5 * (bx0 + bx1), 0.5 * (by0 + by1)
    A, B = 0.5 * (bx1 - bx0), 0.5 * (by1 - by0)
    say("  body bbox %.2f..%.2f x %.2f..%.2f mm  -> centre (%.2f, %.2f), "
        "semi-axes %.2f x %.2f mm"
        % (bx0 / s, bx1 / s, by0 / s, by1 / s, cx / s, cy / s, A / s, B / s))

    def reach(direction) -> float:
        """Furthest distance along `direction` at which the body still exists,
        allowing the ink spokes to punch holes through it."""
        d = direction / math.hypot(*direction)
        last = 0.0
        for r_mm in np.arange(0.0, 0.55 * W_MM, 0.10):
            p = np.array([cx, cy]) + d * r_mm * s
            px, py = int(round(p[0])), int(round(p[1]))
            rad = max(1, int(round(0.45 * s)))
            if (orange[py - rad:py + rad + 1, px - rad:px + rad + 1].any()):
                last = r_mm
        return last

    title("C1  the body is a solid: it darkens the slab it stands on")
    band_y0, band_y1 = by1 + BODY_BOTTOM_PAD * s, by1 + (BODY_BOTTOM_PAD
                                                         + BODY_BOTTOM_BAND) * s
    iy0, iy1 = int(band_y0), int(band_y1)
    ixs = slice(int(cx - 0.70 * A), int(cx + 0.70 * A))
    ctl, ctr = [], []
    for lo, hi in ((1.45, 1.75),):
        for sgn in (-1.0, 1.0):
            ca = int(cx + sgn * lo * A)
            cb = int(cx + sgn * hi * A)
            ctl.append(lum[iy0:iy1, min(ca, cb):max(ca, cb)])
        ctr.append(lum[iy0:iy1, ixs])
    under = np.concatenate([t.ravel() for t in ctr])
    clear = np.concatenate([t.ravel() for t in ctl])
    sg = under.mean() / max(clear.mean(), 1e-9)
    say("  slab under the body %.4f, clear slab at the same height %.4f  "
        "(band %.2f..%.2f mm)" % (under.mean(), clear.mean(),
                                  band_y0 / s, band_y1 / s))
    check(sg <= TH_C1_SHADOW,
          "the body darkens the slab it stands on (contact shadow)",
          "ratio %.4f (need <= %.3f, i.e. %.2f%% darker)"
          % (sg, TH_C1_SHADOW, 100.0 * (1.0 - TH_C1_SHADOW)))
    say("  (silhouette along -LIGHT %.2f mm, toward the light %.2f mm -- the "
        "wall of a 3D body)" % (reach(DARK), reach(LIGHT)))

    title("C2  the content lies IN the wheel plane, so its screen spacing is uneven")
    # INK is the only COOL dark thing on the sheet (b >= r); the side wall is a
    # very dark WARM brown (r-b ~ 90) and must not be mistaken for a spoke, or
    # the wall's own annulus fills every angle and the runs never separate.
    ink = (lum < 0.45) & (b >= r) & win
    yy, xx = np.nonzero(ink)
    ux = (xx - cx) / A
    uy = (yy - cy) / B
    u = np.sqrt(ux ** 2 + uy ** 2)
    # Measured where the spokes are SEPARATE.  Every radial fan merges near
    # the origin -- the tails converge there -- and once the body has real
    # thickness the bbox centre is no longer the wheel centre, so the old
    # 0.10 cut stopped excluding the origin marker as well.  0.60 of the
    # bbox semi-axes is outside the merged core and inside every tip
    # (SPOKE_F1 = 0.96), so all twenty are still resolved: it is a stricter
    # and better-conditioned place to read the spacing, not a looser one.
    keep = (u > 0.60) & (u <= 1.02)
    xx, yy, u = xx[keep], yy[keep], u[keep]
    ang = np.degrees(np.arctan2(yy - cy, xx - cx)) % 360.0
    nb = 360
    cnt = np.bincount((ang / (360.0 / nb)).astype(int) % nb, minlength=nb)
    on = cnt > 0
    runs, i = [], 0
    idx = np.nonzero(on)[0]
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] - idx[j] <= MAX_RUN_GAP + 1:
            j += 1
        seg = np.arange(idx[i], idx[j] + 1)
        runs.append(float(np.average(seg, weights=cnt[seg])))
        i = j + 1
    if len(runs) > 1 and ((runs[0] + 360.0 - runs[-1]) % 360.0) <= MAX_RUN_GAP + 1:
        runs[0] = (runs[0] + runs[-1] - 360.0) / 2.0      # the 0/360 seam
        runs.pop()
    say("  %d dark pixels in the wheel, %d angular runs found (expect %d spokes)"
        % (len(xx), len(runs), 20))
    if len(runs) == 20:
        st = np.array(sorted((math.degrees(math.atan2(math.sin(math.radians(
            (runs[(k + 1) % 20] - runs[k]) % 360)),
            math.cos(math.radians((runs[(k + 1) % 20] - runs[k]) % 360))))
            for k in range(20))))
        say("  spoke-to-spoke screen step %.2f .. %.2f deg, sd %.2f deg"
            % (st.min(), st.max(), st.std()))
        check(st.std() >= TH_C2_STEP_SD,
              "the spokes are foreshortened unevenly (projected, not printed)",
              "sd %.2f deg (need >= %.2f; a flat starburst is ~0.2)"
              % (st.std(), TH_C2_STEP_SD))
    else:
        check(False, "the spokes are foreshortened unevenly (projected, not printed)",
              "could not resolve 20 spokes (%d runs)" % len(runs))

    title("C3  the isotropic reference shares the wheel plane (it is squashed)")
    # ... and the shared dashed reaction plane runs straight through this window,
    # so anything within 3 mm of it is discarded before the ring is fitted.
    # A cool neutral: the guide is #8b95a0 and its antialiased skirt keeps
    # b > g > r.  The body's warm outer glow (253,236,209) has b < g, so this
    # also keeps the glow out of the fit.
    grey = ((b > g) & (g >= r) & (r > 90) & (r < 215) & win)
    grey[np.abs(np.arange(hpx, dtype=float) - cy) < 3.0 * s, :] = False
    # Rows within 5 mm of the reaction plane are dropped: that is where the
    # shared dashed plane runs, where the two reaction-plane labels sit, and
    # where the ring is hidden behind the body anyway.  What is left is the
    # ring's top and bottom arcs -- exactly the part that carries the squash.
    grey[np.abs(np.arange(hpx, dtype=float) - cy) < 5.0 * s, :] = False
    yy, xx = np.nonzero(grey)
    body = orange.copy()
    for dxy in ((-2, 0), (2, 0), (0, -2), (0, 2), (0, 0)):
        body |= np.roll(np.roll(orange, dxy[1], axis=0), dxy[0], axis=1)
    sel = ~body[yy, xx]
    xx, yy = xx[sel], yy[sel]
    if len(xx) < 200:
        say("  ! no grey reference ring found outside the body")
        fails.append("C4 reference ring not found")
    else:
        # A plain bbox is useless here (one antialiased glyph pixel stretches it
        # by centimetres) and a free 5-parameter conic is ill-conditioned on two
        # arcs.  The ring IS concentric with the body by construction, so pin the
        # centre there and solve A u^2 + C v^2 = 1 -- three unknowns collapse to
        # two, and the vertical semi-axis comes out exact (v7: 13.56 against a
        # drawn 13.555).
        u = (xx - cx) / s
        v = (yy - cy) / s
        M = np.c_[u * u, v * v]
        coef, *_ = np.linalg.lstsq(M, np.ones(len(u)), rcond=None)
        ax = 1.0 / math.sqrt(abs(coef[0]))
        ay = 1.0 / math.sqrt(abs(coef[1]))
        rms = float(np.sqrt(((M @ coef - 1.0) ** 2).mean()))
        say("  reference ring fit (centre pinned on the body): %.2f x %.2f mm, "
            "rms residual %.4f  [%d px]" % (ax, ay, rms, len(u)))
        check(max(ax, ay) / min(ax, ay) >= TH_C3_REF_ASPECT,
              "the isotropic reference is drawn in the same plane (squashed)",
              "semi-axis ratio %.3f (need >= %.3f)"
              % (max(ax, ay) / min(ax, ay), TH_C3_REF_ASPECT))

    title("C4  the shading carries a normal field (volume, not a hot centre)")
    oy, ox = np.nonzero(orange)
    ou = np.sqrt(((ox - cx) / A) ** 2 + ((oy - cy) / B) ** 2)
    inside = ou <= 0.97
    oy, ox, ou = oy[inside], ox[inside], ou[inside]
    iv = lum[oy, ox]
    b_i = np.argmax(iv)
    offc = math.hypot(ox[b_i] - cx, oy[b_i] - cy) / s
    say("  brightest body pixel %.3f at %.2f mm from the centre" % (iv[b_i], offc))
    check(offc >= TH_C4_OFFCENTRE,
          "the highlight sits off-centre (a normal field, not a centred ramp)",
          "%.2f mm (need >= %.2f)" % (offc, TH_C4_OFFCENTRE))
    mid = iv[(ou >= 0.45) & (ou <= 0.70)].mean()
    edge = iv[(ou >= 0.88)].mean()
    say("  mean luminance mid-radius %.4f, rim %.4f" % (mid, edge))
    check(mid - edge >= TH_C4_LIMB,
          "the rim is darker than the mid-radius (limb darkening)",
          "%.4f (need >= %.4f)" % (mid - edge, TH_C4_LIMB))

    return finish()


def finish() -> int:
    say()
    say("=" * 78)
    if fails:
        say("RESULT: %d of %d 3D checks FAILED" % (len(fails), n_check[0]))
        for f in fails:
            say("   ! " + f)
    else:
        say("RESULT: all %d 3D checks passed -- the raster reads as a solid."
            % n_check[0])
    print("\n".join(report))
    return 1 if fails else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(args[0])))
