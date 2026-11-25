# 硬规则（自包含版，v5.1）

> 这份文件 = 工作区 `AGENTS.md` 的**可移植版本**。规则属于 skill，不属于某一个工作区：
> 换一台机器、开一个新对话、在一个空目录里开工，只要按这里的命令走，闸门就在。
> 工作区的 `AGENTS.md` 只是它的副本；两者冲突时**取更严的那条**。
>
> 一句话版本：**规则不靠记性，靠闸门。** 每条硬规则下面都写了「怎么机械执行」。

## 0. 唯一入口：`ref_guard.py`（先查后调）

```bash
python scripts/ref_guard.py --run --stage sketch \
    --brief <brief.md> --tier <A|B|C|D|E> --ir <IR> \
    --ref <风格书> --content-ref <构图依据> \
    -- --brief <brief.md> --stage sketch --ref <风格书> --content-ref <构图依据> \
       --seeds 1,2 --outdir <dir> --size 1664*909
```

`ref_guard` 在**调 API 之前**依次跑：

| 顺序 | 闸门 | 失败码 | 规则出处 |
|---|---|---|---|
| 1 | 参考图角色（`--ref` 只收风格书、`--content-ref` 只收手绘/上一档） | `SELF_OUTPUT` / `DEMO_REF` / `SAME_FILE` | §2 |
| 2 | IR 契约（`style.mode=render3d`、坐标约定、投影、手性、束流轴） | `NOT_3D` / `NO_PROJECTION` / `LEFT_HANDED` / `NO_BEAM_AXIS` | §3 |
| 3 | IR 版式没被写死 | `LAYOUT_LOCKED` | §4 |
| 4 | IR 元素清单给客户过目并点头 | `NO_ELEMENT_ACK` | §5 |
| 5 | 客户挑了草图（render 档） | `NO_CLIENT_CHOICE` | §6 |
| 6 | 提示词阶梯 L1–L14 | `LADDER` | §7 |
| 7 | **IR 生效范围 S1–S5（B 档不许出现 IR 的元素）** | `IR_SCOPE` | §7.1 |

`--post` 再跑出图后闸门：

```bash
python scripts/ref_guard.py --post --post-3d <成品.png> \
    --axis-svg <交付.svg> --axis-png <同尺寸.png> --ir <IR> [--expect-plane yes|no]
```

> 直调 `scripts/gen_figure.py` 会被令牌机制拦住（它要求 `HEP_GUARD_PASSED`，只有
> `ref_guard --run` 会发）。所以**不要绕**，绕了也跑不起来。

---

## 1. 取图与请求体预算（R0，2026-10-21）

- 生产图保持全尺寸（常见 `2336*1280`）；描摹、`axis_gate.py`、`keep_gate.py`、矢量重建**只用全尺寸**。
- 模型（对话）只看**长边 ≤1800 的 JPEG q90**：
  ```bash
  python scripts/preview.py <文件或目录...>        # 默认写 _preview/，打印尺寸与合计体积
  ```
- 4up / 长条拼图也**先缩到 1800px 再看**；全尺寸只喂脚本。
- **单会话预览 ≤ 40 张**；到量就开新会话，只带「当前选定 + 待改清单」，不要搬整段历史。
- 依据：请求体上限按**整段历史**算（DeepSeek Responses 48 MiB），每看过一张图，之后每一轮都要重新 base64 发送。
  实测旧会话 20 次 `view_image` 累计 49.68 MB → `413 Payload Too Large`。**与仓库体积无关。**

## 2. 参考图的角色（R1）

- `--ref`（风格参考）**只许**取风格书：`assets/t3-exemplars/`、
  `assets/schematic-library/redistributable/` 或工作区 `_T3精选/`。
- 新素材库只把 CC0 / CC BY 图放进 `redistributable/`；metadata-only 记录不得当 `--ref`。
- `--content-ref`（构图依据）：草图阶段只许作者手绘输入（`sketches_in/`、`hand_sketch*.png`）；
  render 阶段只许**本阶梯已登记 rung 目录里**的图（`gen/A/sketch_s1.png`、`gen/B/chosen.png`）。
- 任何阶段都不许：自家成品（`out/**`、`render_*.png`、`chosen*.png`、`*.svg`、`*.pdf`、`*@4000.png`）、
  `assets/demos/**`（成品示例，不是风格书）。
- **同一张图不许同时出现在 `--ref` 和 `--content-ref`**。
- 闸门：`scripts/ref_guard.py`（`SELF_OUTPUT` / `DEMO_REF` / `SAME_FILE`）。
  历史对账：`scripts/audit_refs.py`（扫所有 `calls.jsonl`）。

## 3. 所有配图一律 3D 明暗风（R2）

- `style.mode` 必须是 `render3d`；成品必须是**有体积、有明暗的 3D 渲染插画**，不是扁平矢量。
- 扁平只允许两类面板，且要写进交付说明：① 承载定量数据（谱/曲线/误差带/场图/极坐标）；
  ② 纯抽象（演化色条、晶格示意、流程条）。同一张图里的物理示意图面板仍必须 3D。
- 闸门：`ref_guard` 的 IR 契约（`NOT_3D`，`--allow-flat "理由"` 才放行）；
  出图后 `check_3d_generic.py`（`3D0–3D3`）；批量排序 `gate3d_rank.py`。

## 4. 三轴物理（R3）

- `X1` 坐标约定必须声明；`X2` 轴名多重集 == 声明；`X3` **同一轴名的两端必须落在同一根轴杆上**；
  `X4` 三轴两两夹角 > 15°；`X5` 不许第四个单字母轴名。
- `X7` 右手系必须书面声明，且图上轴杆方向与 IR 的 `轴方向_deg` 一致（容差 20°）；
  `X8` 投影必须是正交/轴测（不许透视），给了前缩就要几何自洽；`X9` 束流轴一般是 z。
- 闸门：
  ```bash
  python scripts/axis_gate.py --svg <交付.svg> --png <同尺寸.png> --ir <IR> [--annot <标注.png>]
  python scripts/axis_gate.py --png <草图_clean.png> --ir <IR>     # 草图档：X3b/X4 降级为读数
  ```
- 标定：`axis_gate.py --selftest` 15 条。

## 5. 出草图前：IR 元素清单先给客户过目（R4）

```bash
python scripts/element_list.py --ir <IR> [--with-physics]      # ① 贴给客户看
python scripts/element_list.py --ir <IR> --ack --by client --reply "原话"   # ② 客户点头
python scripts/element_list.py --ir <IR> --check               # ③ 自查
```
`--by` 只认 `client/customer/author/user/客户/作者/用户/甲方`；写 `agent/auto/codex` 一律失败。

## 6. 选择权在客户手里（R5）

```bash
python scripts/make_picker.py --handoff <dir> --tag <TAG>        # pick.html + pick_sheet.png
python scripts/choice_gate.py --handoff <dir> --record --code <TAG>-cand_NN \
       --reply "客户原话" --by client                            # 回执
```
没有客户回执 = 不许出成品位图（`ref_guard` 在 render 档硬拦，`NO_CLIENT_CHOICE`）。

## 7. 两条提示词阶梯（R6）

新账本首轮收到作者草图才走 A→E：A 是手稿加一句话；B 复用原句、不带图；C 才加风格书、面板序列及输出硬约束；D 以 C 为底稿，对照本账本 A/B/C 各一张逐元素取舍；E 仅用紧邻上一稿修物理。正式位图基于作者选中的最后一张 E 草图。无草图及旧账本沿用以下 A→D。

有手稿路线的 A/B 共用原句只写领域、题材和必要的物理关系，不得指定形状或颜色（L2）。D 可选更好的画法；E 仅在形状违反硬物理时修正，并写 `[HPn]` 或可量证据。

- **A**：一句话（≤80 字符），**默认不带 `--ref`**；只作诊断，不进交付链。
- **B**：A 的文字 + 面板序列 + 输出硬约束；**必须带 `--ref`**；**不给上一档的图**；不写“保留”措辞。
- **C** = 元素替换档：必须给 **A、B 两张图**；简报写“搬 A 的好元素替换 B 的对应处”。
- **D** = 物理修正档：必须给**紧邻上一档的图**；只改列出的物理错误，其余连形状/质感/配色/视角都不许变。
- 用了整幅风格图，就必须写 `【参考图自带、本图不要】` 泄漏黑名单（L14）。
- 闸门：`scripts/ladder_gate.py`（L1–L14；`--selftest` 跑标定），账本 `gen/ladder.json`。

### 7.1 IR 的生效范围

下列 B/C/D 是无草图档位。有作者草图时，风格档移至 C，禁止提前引入 IR 的形体和材质；D 以三张候选图取舍元素，无需为了通过闸门而虚构物理错误；E 逐条复查硬物理。

> 作者 2026-10-14：「B 档输入取消输入 A 档的图，只有参考图」；
> 2026-10-21：「B 档没有 IR 进去，IR 第一次起作用应该是在 D 档起到删除错误物理改成正确物理的作用」。

- **B 档简报里不许出现 IR 的元素**：只许 A 的文字 + 面板序列 + 标签白名单 / 不要图例这类输出硬约束。
  板 / 网格 / 玻璃 / 薄板 / 竖立 / 斜置 / 半透明 / 冷灰 / 接触阴影 … 这些是 IR 的 elements 与材质，
  **第一次可以出现是在 C 档**。
- C 档只许用 IR 去改 **A 档真画错的东西**：每条改动要带 `[HPn]` 或可量证据（量、实测、夹角、比值、坐标…）。
- D 档才逐条过 HP1–HP6（上一轮 `check_sketch` 里所有答“否”的硬物理）。
- **IR 的版式 / 材质偏好不构成物理要求** —— 物理对的排法有很多种。
- 闸门：`scripts/ir_scope_gate.py`（`S0–S5`），已接进 `ref_guard`（`IR_SCOPE` 硬伤）。
  ```bash
  python scripts/ir_scope_gate.py --tier B --brief <brief.md> --ir <IR> [--show-vocab]
  ```
- 标定（2026-10-21）：
  | 输入 | 结果 |
  |---|---|
  | `fig_upc_v427_u15/brief_B.md`（含“竖立半透明网格板”） | **FAIL**：`竖立` / `网格` / `半透明` |
  | `fig_upc_v426_u15/brief_B.md`（含“斜置浅灰网格薄板”） | **FAIL**：`斜置` / `网格` / `薄板` |
  | 同 IR 的干净 B（只有场景 + 标签白名单） | **PASS** |
  | A 档一句话 | **PASS** |

> 为什么要这条：v427 的 A 档只写“两个核子堆成的重核”，B 档自己加了“竖立半透明网格板”，
> C/D 的“原样保留”把它冻结成竖玻璃板 + 冷灰石材质；而 v426 的 B 也带了“斜置网格薄板”，
> 只是风格锚点恰好同族所以没被看出来。**这是系统性 bug，不是一次失误。**

## 8. 草图管“对不对”，位图管“全不全、精不精”（R7）

- 草图阶段必须管（答“否”就重出）：三轴与轴杆一一对应、同一轴名只出现一次、方向关系
  （L ⊥ 反应平面、自旋沿 L、b 是横向错开、面内 vs 面外大小、杏仁长轴朝向）、不编造数值与公式。
- 草图阶段**不管**：IR 元素齐全度、面板形状精细度、配色质感；`3D1/3D2` 只当读数。
- 草图产物是**两份**：`sketch_sN_clean.png` + `sketch_sN.svg`（`sketch_to_vector.py`）。
- 闸门：`check_sketch.py --ir ...`；交接 `sketch_handoff.py` / `sketch_ingest.py`。

## 9. 位图简报 = IR 全量 + 上一版错误清单（R8）

```bash
python scripts/ir_to_genbrief.py <IR> --stage render --style-mode render3d -o <dir>/brief_render.md
# 再追加一节：
# ════ 构图依据（草图）已知画错的地方 —— 这一步必须改对，不许照抄 ════
# 1. <错在哪> → <改成什么>          （每条带 [HPn]）
# 2. 图上只许出现这些标签：…        （一个都不许多）
```

- 构图参考**原样送**（`auto -> full`，技能 v4.7 起不降级）；草图本身是扁平稿才用 `--content-ref-mode layout`。
- 逐条对照错误清单复检：没改对的 + 新冒出来的标签，写成下一轮清单。

## 10. 硬物理 vs 画法 vs 美观（R9）

**否决权单向：物理可以否决美观；美观不能否决物理；美观可以否决“画法偏好”。**

- 第 1 层 · 硬物理（唯一有否决权）：写进 IR 的 `hard_physics:`，每条必须给 `measure`（怎么量）。
  **给不出 measure 的，说明它是画法，不是物理。**
- 第 2 层 · 画法偏好：降级为建议，放进标题含「建议 / 外观 / 可选」的块。
- 第 3 层 · 配色 / 材质 / 质感 / 光源：交给生图模型，闸门不判。
- 闸门：`ir_scope_gate.py` 的 S3/S4；`ref_guard` 的 IR 契约要求 `hard_physics` 非空。

## 11. 最终 SVG：原生几何与独立透明纹理两版（R10）

已有作者指定的成品图、只要重绘 SVG 时，从对象拆解直接开始，跳过生图、草图阶梯和逐像素临摹。需要创作新图时，草图、作者选择和成品位图门禁照旧，最后按对象重绘 SVG。 见 [直接重绘 SVG](direct-svg-redraw.md)。按对象直接重绘：量参考图的比例与锚点 → 列对象和前后关系 → 画出完整形体（包括可合理补画的遮挡部分） → 用真渐变、独立阴影和原生文字塑形 → 回渲染、隐藏/移动一个对象核对。SVG 不嵌位图；每个物体是可单独编辑的命名组。

`scripts/check_direct_svg.py` 可检查结构并渲染隐藏指定组的试编辑图；被挡形体是否完整需目检。只有作者明确要像素级保真、对照旧算法或维护旧稿时，才走临摹备用。纯代码渐变重绘按 [连续渐变 SVG](continuous-gradient-svg.md) 直接回渲染 4 倍局部，并试移或隐藏关键对象。有目标位图时，两版还须通过 [原尺寸保真门禁](svg-fidelity.md)。

**双版要求（2026-11-19）**：默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。 见 [双 SVG 流程](dual-svg.md)。`check_svg_pair.py` 验证共同对象/文字及试编辑只改变指定 transform/display，完整遮挡和前景颜色仍需目检。

## 12. 元素级矢量素材库（R11）

```bash
python scripts/element_library.py validate
python scripts/element_library.py list --safe-only
```

- `assets/element-library/` 存透明原生 SVG，不存整图截图；
- 每个元素必须声明 licence、attribution、SHA-256、physics_roles、dimensionality；
- `generation.origin` 区分 software / human / AI raster / AI vector；
- AI 补充必须走 `ingest-ai`，记录模型、prompt hash、审核人和来源；
- 整图检索层 `schematic-library/` 仍按 CC0/CC BY 与 metadata-only 分层。

## 12.1 元素 spec 与投稿安全模式（R12）

```bash
python scripts/spec_confirm.py figure.spec.yaml --record --by client --reply "原话"
python scripts/spec_compile.py figure.spec.yaml --outdir out --stem figure --safe-mode
python scripts/visual_review.py --spec figure.spec.yaml --svg out/figure.svg \
  --png out/figure.png --pdf out/figure.pdf --record --by client --reply "原话"
python scripts/spec_compile.py figure.spec.yaml --outdir out --stem figure --safe-mode --final
```

- confirmation hash 覆盖元素、文字、连接、画布、关系与硬物理；改 spec 后必须重新确认；
- `--safe-mode` 排除 `ai_raster`、`ai_generated_vector`、`data-ai-generated=true` 与 `<image>`；
- `--source-derived-only` 进一步只允许 `article_vector_native/trace`，排除所有 `software` 补位图元；
- `nature_gate.py` 检查 89/183 mm 宽度、5–12 pt 字号、0.25–3 pt 线宽、语义色族和 600 dpi；
- `--final` 要求视觉回执与当前 SVG/PNG/PDF 哈希一致；
- 输出 SVG + PDF + 600 dpi PNG + manifest；manifest 记录每个元素的 licence 与 AI provenance。

## 13. 交付强制项（每张图都要出）

1. 作者给定的参考图，或客户确认的成品位图（若需生成位图）；
2. 原生几何 `<stem>_edit.svg` + 独立透明 `<stem>_texture.svg`，各自 PNG、所用源码；
3. `参考图 | SVG 回渲染` 对照与试编辑结果；临摹备用才交旧三联图；
4. 闸门读数：`坐标约定：束流=? 碰撞参数 b=? 反应平面=? 法线=?`；
   `3D 闸门读数：板面 ?% / 接触阴影 ?% / 高光偏离 ? 半轴`；
5. 已知偏差 + 没改对的地方（逐条）。

## 14. 新工作区怎么起步

```bash
python scripts/init_workspace.py --dir <新工作区>
```
它会在目标目录写一份 `AGENTS.md`（本文件的入口版）+ `tools/` 下的转发脚本（指向 skill 的
`scripts/`），这样新对话即使读不到这份 `references/hard_rules.md`，也会先看到 `AGENTS.md` 并照做。

## 15. 与工作区 `AGENTS.md` 的关系

- 本文件是**上游**；工作区那份是**副本/补充**（可以写具体图种、具体标定样本）。
- 冲突时取**更严**；工作区放宽一条，必须在交付说明里写明理由，并给出对应的 `--waive`。
