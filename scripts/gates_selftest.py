#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gates_selftest -- 把 §0.4 两道闸门的标定表变成一条命令。

    python scripts/gates_selftest.py

改了 axis_gate.py / check_3d_generic.py 之后跑一次；任何一行与期望不符 = 非零退出。
"""
from __future__ import annotations

import glob
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def t3(pat):
    """\u5148\u627e\u5de5\u4f5c\u533a\u7684 _T3\u7cbe\u9009\uff0c\u518d\u627e skill \u81ea\u5e26\u7684 assets/t3-exemplars\u3002"""
    for d in ("_T3\u7cbe\u9009", os.path.join("assets", "t3-exemplars")):
        g = glob.glob(os.path.join(HERE, "..", d, pat))
        if g:
            return g[0]
    return None


def _exist(args):
    """args[1:] 里的路径参数只要有一个不存在就跳过（本仓库通常没有工作区样本）。"""
    for x in args[1:]:
        if "." in os.path.basename(x) and not x.startswith("--") and len(x) > 3:
            if not os.path.exists(os.path.join(HERE, "..", x)):
                return False
    return True


def cases():
    C = []
    C.append(("\u4e09\u8f74 \u4fee\u524d UPC\uff08\u540c\u4e00\u6839\u8f74\u4e24\u4e2a\u540d\u5b57\uff09", 1,
              ["axis_gate.py", "--svg", "fig_upc_3d/trace/upc_trace_prelabel.svg",
               "--png", "fig_upc_3d/gen/chosen.png", "--ir", "fig_upc_3d/ir/upc_3d.ir.yaml"]))
    C.append(("\u4e09\u8f74 \u4fee\u540e UPC", 0,
              ["axis_gate.py", "--svg", "fig_upc_3d/out/upc_3d.svg",
               "--png", "fig_upc_3d/gen/chosen.png", "--ir", "fig_upc_3d/ir/upc_3d.ir.yaml"]))
    irq = "fig_qgp_3d/ir/qgp_formation.ir.yaml"
    C.append(("3D  QGP s301\uff08\u7b2c1\u8f6e\u300c2D\u8d34\u7eb8\u300d\uff09", 1,
              ["check_3d_generic.py", "fig_qgp_3d/gen/sketch_s301_clean.png", "--ir", irq]))
    C.append(("3D  QGP s322", 0,
              ["check_3d_generic.py", "fig_qgp_3d/gen/sketch_s322_clean.png", "--ir", irq]))
    C.append(("3D  QGP s324\uff08\u7b2c2\u8f6e\uff09", 0,
              ["check_3d_generic.py", "fig_qgp_3d/gen/sketch_s324_clean.png", "--ir", irq]))
    C.append(("3D  UPC chosen", 0,
              ["check_3d_generic.py", "fig_upc_3d/gen/chosen.png",
               "--ir", "fig_upc_3d/ir/upc_3d.ir.yaml"]))
    C.append(("3D  figC_upc\uff08\u6241\u5e73\u7a3f\uff09", 1,
              ["check_3d_generic.py", "figures/out/figC_upc.png"]))
    C.append(("3D  \u96c6\u4f53\u6d41 chosen\uff08\u65e0\u5730\u9762\uff09", 0,
              ["check_3d_generic.py", "collective_flow/gen/chosen.png", "--expect-plane", "no"]))
    # \u98ce\u683c\u4e66\u91cc\u6709\u7684\u7528\u6df1\u8272/\u5f69\u8272\u677f\u9762\uff0c\u6d45\u7070\u677f\u9762\u5224\u636e\u4f1a\u6f0f\u5224 -> \u90a3\u51e0\u5f20\u53ea\u67e5\u4f53\u79ef\u660e\u6697\uff083D3\uff09
    for pat, nm, extra in (("T3-07*", "T3-07", []), ("T3-30*", "T3-30", []),
                           ("T3-01*", "T3-01", ["--expect-plane", "no"]),
                           ("T3-34*", "T3-34", ["--expect-plane", "no"])):
        p = t3(pat)
        if p:
            C.append(("3D  \u98ce\u683c\u4e66 %s" % nm, 0, ["check_3d_generic.py", p] + extra))
    return C


def main():
    bad = 0
    n_skip = 0
    for nm, want, args in cases():
        if not _exist(args):
            print("%-38s 跳过（本仓库没有该样本）" % nm)
            n_skip += 1
            continue
        cmd = [PY, os.path.join(HERE, args[0])] + args[1:]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=os.path.join(HERE, ".."))
        ok = (r.returncode == want)
        if not ok:
            bad += 1
        print("%-38s want rc=%d  got rc=%d   %s" % (nm, want, r.returncode,
                                                    "\u2713" if ok else "\u2717 \u4e0d\u7b26"))
        if not ok:
            tail = (r.stdout or "").strip().splitlines()[-6:]
            for line in tail:
                print("      | %s" % line)
    print("\n%s   (%d \u9879\uff0c\u4e0d\u7b26 %d)" % (
        "\u5168\u90e8\u7b26\u5408\u671f\u671b" if bad == 0 else "\u6709\u4e0d\u7b26\u671f\u671b", len(cases()), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
