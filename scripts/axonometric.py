# -*- coding: utf-8 -*-
"""axonometric -- a REAL orthographic camera for 2D drawings, plus a verifier.

The thing that makes a drawn "3D" scene read as 3D is that its three axis
directions on the page must come from ONE orthographic camera.  Write

    screen(w) = ( w.r , -w.u )            [canvas mm, +y = down]

with r, u the camera's right/up vectors.  Then (r, u, b=r x u) is an
orthonormal frame and the drawing is real.  If you instead pick the three axis
screen directions by hand (the usual "one axis at 45 degrees" recipe) you get an
OBLIQUE drawing: |r| != 1, |u| != 1, r.u != 0, and the foreshortenings disagree
with each other.  The eye reads that as flat.  `--check` prints exactly those
three numbers.

Usage
    python3 scripts/axonometric.py --check --az 144.74 --el 45
    python3 scripts/axonometric.py --check --az 144.74 --el 45 --roll 118   # 指定 roll
    python3 scripts/axonometric.py --check --az 144.74 --el 45 --level-axis z

★ 两套角度约定，别混（v4.0）：
    本工具按**数学惯例**：屏幕 +y 向上，顺时针为正 → atan2(dy_up, dx)。
    IR 的 `composition.projection.轴方向_deg` 按**简报约定**：屏幕 y **向下**，
    0° = 向右、90° = 向下、向上写负数。
    换算一步：**规范角 = −工具角**。`--check` 会把两套都打出来 ——
    填 IR 请抄「→ IR」那一列。填错的代价：y 被画成竖直向下（图倒挂），而且照样过闸门
    （`projection_gate.py` 的 P1 只查"有没有落在 0/±90 附近"，y 本来就被允许竖直）。
"""
from __future__ import annotations
from __future__ import annotations

import argparse
import math

import numpy as np


def basis(az_deg: float, el_deg: float, roll_deg: float = 0.0):
    """Orthonormal camera frame. b points from the scene towards the viewer."""
    az, el, roll = map(math.radians, (az_deg, el_deg, roll_deg))
    b = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(b @ up)) > 0.999:
        up = np.array([0.0, 1.0, 0.0])
    r0 = np.cross(up, b); r0 /= np.linalg.norm(r0)
    u0 = np.cross(b, r0)
    r = r0 * math.cos(roll) + u0 * math.sin(roll)
    u = -r0 * math.sin(roll) + u0 * math.cos(roll)
    return r, u, b


def roll_that_levels(az_deg: float, el_deg: float, axis=(1.0, 0.0, 0.0), up=True):
    """Roll such that the given world axis comes out HORIZONTAL on the page."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    b = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
    up_w = np.array([0.0, 0.0, 1.0])
    if abs(float(b @ up_w)) > 0.999:
        up_w = np.array([0.0, 1.0, 0.0])
    r0 = np.cross(up_w, b); r0 /= np.linalg.norm(r0)
    u0 = np.cross(b, r0)
    a = np.array(axis, dtype=float)
    a = a if up else -a
    return math.degrees(math.atan2(float(a @ u0), float(a @ r0)))


def project(v, r, u):
    v = np.asarray(v, dtype=float)
    return np.array([float(v @ r), -float(v @ u)])


def axis_table(az_deg: float, el_deg: float, level_x: bool = True, roll=None,
               level_axis=(1.0, 0.0, 0.0)):
    if roll is None:
        roll = roll_that_levels(az_deg, el_deg, axis=level_axis) if level_x else 0.0
    r, u, b = basis(az_deg, el_deg, roll)
    rows = []
    for name, v in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1))):
        sp = project(v, r, u)
        rows.append((name, float(sp[0]), float(sp[1]),
                     math.degrees(math.atan2(-sp[1], sp[0])), float(np.linalg.norm(sp))))
    return roll, rows, (r, u, b)


def _spec_ang(a_tool: float) -> float:
    """工具角（+y 向上，顺时针为正） -> 规范角（+y 向下）。"""
    a = -a_tool
    a = (a + 180.0) % 360.0 - 180.0
    return a


def check(az_deg, el_deg, level_x=True, roll=None, level_axis=(1.0, 0.0, 0.0)):
    if roll is None:
        roll, _rows, _fr = axis_table(az_deg, el_deg, level_x, level_axis=level_axis)
    _roll, rows, (r, u, b) = axis_table(az_deg, el_deg, level_x, roll=roll)
    print("=" * 74)
    print("axonometric check  az=%.2f deg  el=%.2f deg  roll=%.3f deg" % (az_deg, el_deg, roll))
    print("=" * 74)
    print("  camera frame  |r|=%.6f  |u|=%.6f  r.u=%+.6f  (need 1, 1, 0)"
          % (np.linalg.norm(r), np.linalg.norm(u), float(r @ u)))
    print("  axis   screen dx   screen dy   angle(+y up, tool)   ->  IR 角(+y down)   drawn length")
    for nm, sx, sy, ang, ln in rows:
        print("    %s    %+8.4f    %+8.4f       %+8.2f deg            %+8.2f deg        %.4f"
              % (nm, sx, sy, ang, _spec_ang(ang), ln))
    ok = (abs(np.linalg.norm(r) - 1) < 1e-9 and abs(np.linalg.norm(u) - 1) < 1e-9
          and abs(float(r @ u)) < 1e-9)
    print("  => %s" % ("VALID orthographic camera (a real 3D view)"
                       if ok else "INVALID: not a projection"))
    # ── 顺手按 projection_gate.py 的 P1/P2 过一遍（画之前就能知道会不会被闸门拦）──
    spec = {nm: _spec_ang(ang) for nm, _sx, _sy, ang, _ln in rows}
    fmin = min(ln for _n, _sx, _sy, _a, ln in rows)
    bad = []
    for nm in ("x", "z"):
        d = spec[nm]
        if min(abs(d % 180), abs(d % 180 - 90), abs(d % 180 - 180)) <= 4.0:
            bad.append("%s=%+.1f deg 落在画面的水平/垂直方向" % (nm, d))
    dirs = sorted(v % 180.0 for v in spec.values())
    gaps = [dirs[1] - dirs[0], dirs[2] - dirs[1], 180 - (dirs[2] - dirs[0])]
    if min(gaps) < 8:
        bad.append("两条轴几乎同向（最小夹角 %.1f deg）" % min(gaps))
    print()
    print("  P1/P2 自检（projection_gate.py 的口径，规范角）:")
    if fmin >= 0.88:
        bad.append("最小前缩 %.2f >= 0.88（法线轴没前缩）" % fmin)
    print("    最小前缩 %.3f  (P2 要 < 0.88)   %s" % (fmin, "ok" if fmin < 0.88 else "FAIL"))
    if bad:
        for x in bad:
            print("    FAIL  " + x)
        print("    ↑ 这样写进 IR 会被 projection_gate.py 拦（或出来必然扁平），换个 roll / 相机")
    else:
        print("    ok  —— 三轴方向可以直接抄进 IR 的 轴方向_deg")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--az", type=float, default=144.74)
    ap.add_argument("--el", type=float, default=45.0)
    ap.add_argument("--no-level", action="store_true")
    ap.add_argument("--roll", type=float, default=None,
                    help="显式 roll（度）。不给则按 --level-axis 把那根轴摆成水平")
    ap.add_argument("--level-axis", default="x", choices=("x", "y", "z", "none"),
                    help="把哪根轴摆成水平（默认 x；none = roll 0）")
    a = ap.parse_args()
    if a.check:
        ax = {"x": (1., 0., 0.), "y": (0., 1., 0.), "z": (0., 0., 1.)}.get(a.level_axis)
        check(a.az, a.el, (a.level_axis != "none") and not a.no_level,
              roll=a.roll, level_axis=ax)
    else:
        for az, el, nm in ((45.0, 35.264, "isometric (2:1 sides)"),
                           (144.74, 45.0, "z at 45 deg down-right, x horizontal"),
                           (135.0, 30.0, "shallower dimetric")):
            roll, rows, (r, u, b) = axis_table(az, el)
            print("%-38s roll=%7.2f" % (nm, roll), end="   ")
            print("  ".join("%s:(dx%+.2f dy%+.2f len%.2f ang%+.1f)"
                            % (n, sx, sy, ln, ang) for n, sx, sy, ang, ln in rows))
