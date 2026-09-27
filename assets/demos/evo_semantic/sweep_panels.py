# -*- coding: utf-8 -*-
"""sweep_panels.py -- A/B 实验台用的版式表包装。

panels_evo.py 是**交付**用的表（GRADIENTS 已实测置空，见其中注释）。
本文件是**实验台**用的表：默认把「真渐变」按下面这张实测参数表全开，
用环境变量 EXP_JSON 逐元素覆盖，用来量化「真 <gradient> 到底帮不帮忙」：

    EXP_JSON = {"stage1-nucleus": {"nstops": 16, ...}}   # 覆盖该元素
    EXP_JSON = {"stage1-nucleus": null}                  # 该元素不做真渐变
    EXP_JSON = {"k1": null, "k2": null, ...}             # 全关（sweep.py 的 kill=["*"]）
结果见 README.md 的 A/B 表。
"""
import os, sys, json
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
import panels_evo as _P
from panels_evo import *  # noqa: F401,F403

# 2026-09-27 实测出来的「真渐变」参数（--q 16 下逐元素试出来的那一版）
GRAD_DEFAULT = {
    "stage1-nucleus":      dict(nstops=16, tol=24, minpx=1500),
    "stage2-fluctuations": dict(nstops=16, tol=20, minpx=1500),
    "stage3-nucleus-A":    dict(nstops=16, tol=24, minpx=1500),
    "stage3-nucleus-B":    dict(nstops=16, tol=24, minpx=1500),
    "stage3-overlap":      dict(nstops=10, tol=18, minpx=800),
    "stage4-fireball":     dict(nstops=16, tol=26, minpx=1500),
    "stage4-nucleons":     dict(nstops=12, tol=18, minpx=1500),
}
GRADIENTS = {k: dict(v) for k, v in GRAD_DEFAULT.items()}
_j = os.environ.get("EXP_JSON", "")
if _j:
    for _k, _v in json.loads(_j).items():
        if _v is None:
            GRADIENTS.pop(_k, None)
        else:
            GRADIENTS[_k] = _v