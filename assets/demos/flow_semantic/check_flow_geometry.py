# -*- coding: utf-8 -*-
"""Measure the geometry that the IR declares, from the rendered bitmap.

Checks:
  1. initial / final fireball bbox aspect ratio (init h/w>=1.4, final w/h>=2.0)
  2. angle between the two fireballs' fitted major axes (90 +- 15 deg)
  3. radial starburst anisotropy r(phi): in-plane vs out-of-plane (>=1.8)
  4. orange connected component cross span (gradient arrows): horiz/vert (>=1.8)
"""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def warm_mask(a, hue_max=None):
    """Warm (orange/yellow) pixels.  hue_max separates the fireball
    (red-orange rim, hue<29) from the yellow-orange gradient arrows."""
    r = a[..., 0].astype(np.float64) / 255.0
    g = a[..., 1].astype(np.float64) / 255.0
    b = a[..., 2].astype(np.float64) / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, ((g - b) / d) % 6.0,
                   np.where(mx == g, (b - r) / d + 2.0, (r - g) / d + 4.0)) * 60.0
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    m = (sat > 0.35) & (a[..., 0] > 110) & (a[..., 0].astype(np.int16) >
                                            a[..., 1].astype(np.int16) + 18)
    if hue_max is not None:
        m = m & (hue < hue_max) & (hue > 0.0)
    return m


def disk(rad):
    y, x = np.mgrid[-rad:rad + 1, -rad:rad + 1]
    return (x * x + y * y) <= rad * rad


def biggest(m):
    lab, n = ndi.label(m, np.ones((3, 3), int))
    if n == 0:
        return None
    sizes = ndi.sum(m, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


def bbox(m):
    ys, xs = np.nonzero(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def ellipse_axes(m):
    ys, xs = np.nonzero(m)
    x = xs - xs.mean()
    y = ys - ys.mean()
    cxx = (x * x).mean()
    cyy = (y * y).mean()
    cxy = (x * y).mean()
    w, v = np.linalg.eigh(np.array([[cxx, cxy], [cxy, cyy]]))
    order = np.argsort(w)[::-1]
    w = w[order]
    v = v[:, order]
    major = 4.0 * np.sqrt(w[0])
    minor = 4.0 * np.sqrt(w[1])
    ang = np.degrees(np.arctan2(v[0, 1], v[0, 0])) % 180.0
    return major, minor, ang


def main(path):
    a = np.asarray(Image.open(path).convert("RGB"))
    H, W = a.shape[:2]
    wm = warm_mask(a, hue_max=29.0)
    half = W // 2
    print("=" * 70)
    print("geometry measured from %s  (%dx%d)" % (path, W, H))
    print("=" * 70)
    rad = max(6, int(round(W * 0.005)))
    kern = disk(rad)
    res = {}
    for tag, sl in (("initial(left)", (slice(None), slice(0, half))),
                    ("final(right)", (slice(None), slice(half, W)))):
        sub = np.zeros_like(wm)
        sub[sl] = wm[sl]
        blob = biggest(sub)
        if blob is None:
            print("  %s : no fireball blob found" % tag)
            continue
        x0, y0, x1, y1 = bbox(blob)
        cross_w, cross_h = x1 - x0, y1 - y0
        core = ndi.binary_opening(blob, kern)
        if core.sum() < 50:
            core = blob
        cx0, cy0, cx1, cy1 = bbox(core)
        fw = (cx1 - cx0) + 2 * rad
        fh = (cy1 - cy0) + 2 * rad
        maj, mnr, ang = ellipse_axes(core)
        maj = maj + 2 * rad
        mnr = mnr + 2 * rad
        res[tag] = dict(ang=ang, maj=maj, mnr=mnr, roi=sub, fb=blob,
                        fw=fw, fh=fh,
                        cx=(cx0 + cx1) / 2.0, cy=(cy0 + cy1) / 2.0)
        which = "h/w" if fw < fh else "w/h"
        val = (fh / fw) if fw < fh else (fw / fh)
        print("  %-13s fireball (thin arrows removed): w=%d px  h=%d px  ->  %s = %.2f"
              % (tag, fw, fh, which, val))
        print("                fitted ellipse: major %.0f / minor %.0f = %.2f, major axis %.0f deg"
              % (maj, mnr, maj / max(mnr, 1.0), ang))
        print("                orange blob cross span (incl. gradient arrows): %d x %d -> h/v = %.2f"
              % (cross_w, cross_h, cross_w / max(cross_h, 1)))
    if len(res) == 2:
        d = abs(res["initial(left)"]["ang"] - res["final(right)"]["ang"])
        d = min(d, 180.0 - d)
        ok = 75.0 <= d <= 105.0
        print("  -> angle between fireball major axes = %.0f deg   %s (want 90+-15)"
              % (d, "OK" if ok else "FAIL"))
    # ---- gradient arrows (left panel): horizontal vs vertical length ----
    # 沿过火球中心的一行 / 一列扫暖色像素：水平那行的跨度 = 火球宽 + 左右两支箭头；
    # 竖直那列的跨度 = 火球高 + 上下两支箭头。竖直箭头在 x=中心，不会污染行的跨度。
    ini = res.get("initial(left)")
    if ini:
        aw = warm_mask(a)
        cx, cy = int(ini["cx"]), int(ini["cy"])
        band_y = slice(max(cy - 12, 0), cy + 13)
        band_x = slice(max(cx - 12, 0), cx + 13)
        rows = np.nonzero(aw[band_y, :half].any(0))[0]
        cols = np.nonzero(aw[:H, band_x].any(1))[0]
        if rows.size and cols.size:
            hspan = int(rows.max() - rows.min())
            vspan = int(cols.max() - cols.min())
            hlen = (hspan - ini["fw"]) / 2.0
            vlen = (vspan - ini["fh"]) / 2.0
            r = hlen / max(vlen, 1e-9)
            print("  gradient arrows: horizontal %.0f px / vertical %.0f px = %.2f  %s"
                  % (hlen, vlen, r, "OK" if r >= 1.4 else "FAIL (want >=1.4)"))
    rg = res.get("final(right)")
    if rg:
        lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
        dark = lum < 110
        yy, xx = np.mgrid[0:H, 0:W]
        dxx = xx - rg["cx"]
        dyy = yy - rg["cy"]
        rad_px = np.hypot(dxx, dyy)
        lim = 0.55 * max(rg["maj"], rg["mnr"])
        sel = (rad_px < lim) & dark & (xx >= half) & rg["roi"]
        ang = np.degrees(np.arctan2(-dyy, dxx)) % 180.0
        if sel.sum() > 100:
            prof = []
            for lo in range(0, 180, 5):
                m = sel & (ang >= lo) & (ang < lo + 5)
                prof.append(rad_px[m].max() if m.sum() >= 8 else np.nan)
            prof = np.array(prof, float)
            inpl = np.nanmean(np.concatenate([prof[0:4], prof[-4:]]))
            outp = np.nanmean(prof[16:21])
            ratio = inpl / max(outp, 1e-9)
            print("  radial starburst: in-plane %.0f px / out-of-plane %.0f px = %.2f  %s"
                  % (inpl, outp, ratio, "OK" if ratio >= 1.4 else "FAIL (want >=1.4)"))
        else:
            print("  radial starburst: too few dark pixels to measure")
    # dump the mask used, for visual sanity check
    try:
        out = np.zeros((H, W, 3), np.uint8)
        out[wm] = (255, 255, 255)
        Image.fromarray(out).save("gen/_mask_checked.png")
        print("  (mask dumped to gen/_mask_checked.png)")
    except Exception as exc:
        print("  mask dump failed: %s" % exc)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gen/chosen.png")
