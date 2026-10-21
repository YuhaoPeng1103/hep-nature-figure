#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_workspace -- 在一个新工作区落地 skill 的硬规则（v4.26）

做两件事：
  1) 写 <ws>/AGENTS.md —— 硬规则的入口版（新对话一进来就能看到，不依赖用户手抄）；
  2) 写 <ws>/tools/*.py —— 转发到本 skill 的 scripts/，让 `python tools/ref_guard.py`
     这类命令在新工作区照样可用（脚本只有一份，永远跟着 skill 升级）。

用法：
    python scripts/init_workspace.py --dir <新工作区> [--force] [--no-tools]

不改已有文件（除非 --force）；已存在就跳过并打印原因。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

# 转发脚本：工作区里 `python tools/<name>.py` == `python <skill>/scripts/<name>.py`
SHIMS = [
    "ref_guard", "ir_scope_gate", "ir_layout_guard", "ladder_gate", "keep_gate",
    "axis_gate", "check_3d_generic", "gate3d_rank", "check_sketch", "check_delivery",
    "make_picker", "choice_gate", "element_list", "preview", "audit_refs",
    "sketch_handoff", "sketch_ingest", "sketch_to_vector", "trim_border",
    "ir_to_genbrief", "brief_lite", "raster_to_vector_semantic", "trace_rebuild",
    "gen_figure",
]

SHIM_TMPL = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""转发到 hep-nature-figure/scripts/{name}.py（由 init_workspace.py 生成）。

改这里没用 —— 真正的脚本在 skill 里；要改就去改 skill，然后 `git pull` 或重跑 init。
"""
import runpy
import sys
from pathlib import Path

TARGET = Path(r"{target}")
if not TARGET.exists():
    sys.exit("找不到 %s —— skill 路径变了？重跑 scripts/init_workspace.py" % TARGET)
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
'''

AGENTS = """# AGENTS.md —— 配图工作硬规则（由 hep-nature-figure v4.26 生成）

> 完整规则与标定：`{skill}/references/hard_rules.md`
> 本文件是入口版；两者冲突时**取更严的那条**。

## 0. 唯一入口：先查后调

```bash
python tools/ref_guard.py --run --stage sketch --brief <brief.md> --tier <A|B|C|D> --ir <IR> \\
    --ref <风格书> -- --brief <brief.md> --stage sketch --ref <风格书> \\
    --seeds 1,2 --outdir <dir> --size 1664*909
```

直调 `gen_figure.py` 会被令牌机制拦住。参考图角色、IR 契约、元素清单回执、客户选图回执、
提示词阶梯、**IR 生效范围（B 档不许出现 IR 的元素）** 都在 `ref_guard` 里；
`--post` 再跑 3D 与三轴闸门。

## 1. 取图预算（R0）

- 生产图全尺寸（如 `2336*1280`）；描摹 / `axis_gate.py` / `keep_gate.py` / 矢量重建只用全尺寸。
- 模型只看长边 **≤1800 的 JPEG q90**：`python tools/preview.py <文件...>`（写 `_preview/`）。
- 4up / 长条拼图也先缩 1800px 再看；**单会话预览 ≤ 40 张**。
- 413 的根因是**历史累积**（每张看过的图每轮都重新 base64），不是仓库体积。

## 2. 参考图角色（R1）

- `--ref` 只收风格书（`assets/t3-exemplars/`、本工作区 `_T3精选/`）。
- `--content-ref`：草图档只收手绘输入；render 档只收本阶梯已登记 rung 的图。
- 自家成品、`assets/demos/**` 任何阶段都不许当参考；同一张图不许兼两个角色。

## 3. 3D 明暗风（R2）

`style.mode` 必须是 `render3d`。扁平只允许出现在「定量数据面板」与「纯抽象内容」，
且要写进交付说明。草图阶段 `3D1/3D2` 只当读数，位图阶段才硬判。

## 4. 三轴物理（R3）

`X1–X5` + `X7 右手系` + `X8 投影` + `X9 束流轴=z`。同一轴名的两端必须落在同一根轴杆上。
```bash
python tools/axis_gate.py --svg <交付.svg> --png <同尺寸.png> --ir <IR>
python tools/axis_gate.py --png <草图_clean.png> --ir <IR>
```

## 5. 客户拍板（R4/R5）

- 出草图前：`element_list.py` 把 IR 元素清单贴给客户，`--ack --by client` 点头才开跑。
- 出成品前：`make_picker.py` → 客户点选 → `choice_gate.py --record --by client`。
- `--by` 写 `agent/auto/codex` 一律判失败。

## 6. A→B→C→D（R6）

- A：一句话（≤80 字符），默认不带 `--ref`，不进交付链。
- B：A 的文字 + 面板序列 + 输出硬约束；**必须带 `--ref`**；不给上一档的图。
- C：元素替换档，给 A、B 两张图。
- D：物理修正档，给紧邻上一档的图，只改列出的物理错误。
- 用了整幅风格图必须有 `【参考图自带、本图不要】` 泄漏黑名单。

### 6.1 IR 生效范围（v4.26 硬闸门）

**B 档没有 IR。** B 简报里不许出现板 / 网格 / 玻璃 / 薄板 / 竖立 / 斜置 / 半透明 / 冷灰
这类 IR 元素的形体与材质词（`ir_scope_gate.py` 的 `S1_IR_PROP_IN_BRIEF`，已接进 `ref_guard`）。
C 档只许用 IR 改 A 档真画错的（每条带 `[HPn]` 或可量证据）；D 档才逐条过 HP1–HP6。
IR 的版式 / 材质偏好**不构成物理要求**。

## 7. 草图 vs 位图（R7/R8）

- 草图管“对不对”（三轴一一对应、方向关系、b 横向错开），不管“全不全、精不精”。
- 草图产物两份：`sketch_sN_clean.png` + `sketch_sN.svg`。
- 位图简报 = IR 全量 + 上一版错误清单；构图参考原样送；逐条对照复检。

## 8. 否决权分层（R9）

**物理可以否决美观；美观不能否决物理；美观可以否决画法偏好。**
硬物理每条必须在 IR 的 `hard_physics` 里给出 `measure`；给不出 measure 的就是画法。

## 9. 位图 → 矢量（R10）

① 客户确认的位图 → ② `raster_to_vector_semantic.py` 逐像素临摹（`<g data-element>`）
→ ③ `trace_rebuild.py` 从临摹层重建。几何只来自临摹层，禁止再按颜色阈值抠轮廓。
交付贴 `位图 | 临摹 | 重建` 三联图。

## 10. 交付强制项

客户确认的位图 + 可编辑 SVG + 三联图 + 两行读数
（`坐标约定：…` / `3D 闸门读数：板面 ?% / 接触阴影 ?% / 高光偏离 ? 半轴`）+ 已知偏差清单。
"""


def main():
    ap = argparse.ArgumentParser(description="把 skill 的硬规则落到一个新工作区")
    ap.add_argument("--dir", required=True, help="目标工作区目录")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的 AGENTS.md / 转发脚本")
    ap.add_argument("--no-tools", action="store_true", help="只写 AGENTS.md，不生成 tools/ 转发脚本")
    a = ap.parse_args()

    ws = Path(a.dir).resolve()
    if not ws.exists():
        ws.mkdir(parents=True, exist_ok=True)

    written, skipped = [], []

    ag = ws / "AGENTS.md"
    if ag.exists() and not a.force:
        skipped.append(str(ag))
    else:
        ag.write_text(AGENTS.format(skill=SKILL.as_posix()), encoding="utf-8")
        written.append(str(ag))

    if not a.no_tools:
        td = ws / "tools"
        td.mkdir(exist_ok=True)
        for name in SHIMS:
            target = SKILL / "scripts" / (name + ".py")
            if not target.exists():
                continue
            dst = td / (name + ".py")
            if dst.exists() and not a.force:
                skipped.append(str(dst))
                continue
            dst.write_text(SHIM_TMPL.format(name=name, target=target.as_posix()),
                           encoding="utf-8")
            written.append(str(dst))

    print("skill = %s" % SKILL)
    print("写出 %d 个文件：" % len(written))
    for p in written:
        print("  + %s" % p)
    if skipped:
        print("跳过 %d 个已存在的文件（--force 覆盖）：" % len(skipped))
        for p in skipped[:8]:
            print("  = %s" % p)
        if len(skipped) > 8:
            print("  ... 还有 %d 个" % (len(skipped) - 8))
    return 0


if __name__ == "__main__":
    sys.exit(main())