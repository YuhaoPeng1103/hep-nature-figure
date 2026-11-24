# 变更记录

## v5.1 — 2026-11-25

**在 v4.31 的原生几何与连续渐变重绘基础上，新增元素级 HEP 矢量素材库、作者确认 IR、确定性 SVG 编译器和投稿安全模式。**

- 新增 `assets/element-library/`：181 个透明 SVG 元素变体，其中 74 个文章来源元素各有可无限缩放的原生 `_edit.svg` 和用于保真审计的 `_texture.svg`。107 个代码生成 system-primitives 继续单独标记。
- 核子族扩到 30 种，其中 16 种为文章来源；新增 11 个来自形变核/碰撞几何图的红色质子、蓝色中子和核碎片核子照明变体，同一槽位可直接替换。
- 新增 24 个 2020–2026 年论文元素：ALICE 部分子介质与多色部分子对、STAR 径迹探测器、涡旋环/涡旋嵌套、事件拓扑与发射锥；全部保留源 DOI、许可、源 SHA、crop box 与后处理说明。
- 新增 `source_element_extract.py`：按授权源图、人工 bbox/椭圆/多边形掩膜去白底并用 `vtracer` 矢量化；记录源 DOI、许可、源 SHA、高清源图、缩放比例、crop box 与加工方法。
- 新增 `article_element_harvester.py`：发现高能核物理论文，按 PMC OA S3 元数据选择可再分发的 CC BY 版本，下载原始媒体与可选 PDF；失败文章不进“完成”集合，可用 `--retry-failed` 重试。
- PMC/JATS 图件改为按 graphic URL 去重；标题分类收紧，排除“heavy ion radiation / spin polarization / water-jet”等跨领域同词误收；永久许可失败与临时下载失败分开缓存。
- 新增 `publisher_figure_harvester.py`：先核对 APS/PR landing page 的 CC BY 声明和题注第三方权利提示，再从 PDF 以 300 dpi 重建图区；题注缺失或含 permission/reprinted 等提示时只保留 metadata。arXiv PDF adapter 同样要求论文页明确 CC BY。首轮严格筛选得到 574 篇候选，处理 524 篇，保留 4,568 条图件记录，其中 3,557 张已下载高分辨率图区、1,011 条因题注无法核验只留 metadata。
- 新增 `figure_element_candidates.py`：对全部合法本地图做哈希去重、HEP 相关性过滤、题注/视觉示意图排序、审查 HTML/拼图和 review-only 对象 crop；自动 crop 不直接进入 active element index。首轮把 4,695 条本地图件归并为 3,578 张唯一 HEP 图，生成 8,531 个对象候选和 199 张审查拼图。
- 新增 `priority_element_rebuild.py`：对 408 张高优先级图逐对象去背景、审核并生成保守的原生 SVG candidate。首轮联合记录框与重新连通域分区，处理 3,599 个对象 proposal；3,595 个因多物体、文字、坐标或线图风险进入人工拆分，4 个生成平滑纯矢量 candidate；全部保持 `review-only`，不自动进入 active index。
- 新增 canonical 纯文章来源单幅 3D QGP-jet `qgp-jet-paper-3d.spec.yaml`：Pb 核来自 Nature STAR 核形状图，QGP 火球来自 arXiv:2512.00739 图重建，喷注和辐射语言取自 PRL 125, 122301；共享同一斜二测相机、反应平面和硬散射顶点。旧的软件图元样例只保留为编译回归对照。
- 核实 T3-30 QGP 素材来源为 CC BY 的 arXiv:2512.00739 论文图；去除上下文后的 native/texture 双版进入 canonical 3D QGP-jet。
- 修正 T3-30 的语义切分：透视网格、紫色电磁场线和外部黑箭头不再烘进 QGP 元素；QGP 元素只保留火球体积、橙色谱线、部分子和螺旋。干净的 native/texture 两版均重新生成，纹理对干净 native 参考 `MAE 0.851 / >32 0.12%`。
- 新增 `rebuild_article_vectors.py` 与 `element_texture_vectorize.py`：原生重建处理几何和材质，纹理版用平滑曲线、连续渐变网格生成可选的无位图保真对照；`index.json` 始终指向可无限缩放的 `_edit.svg`，纹理重跑不会把默认入口改回跟踪稿。
- 修复透明裁切矢量化把 alpha=0 处的隐藏 RGB 当成可见颜色、从而在圆外漏出彩色晕圈的缺陷；光滑网格改用真实 alpha 轮廓，并保留透明背景。完整 T3-30 crop 上曾达到 `MAE 0.495 / >32 0.22%`；拆分掉网格与场线后，干净 QGP 元素对 clean native 参考为 `MAE 0.851 / >32 0.12%`。
- `element_texture_vectorize.py` 新增 `smooth-gradient-mesh` 后端：二维连续渐变 + 细残差网格；不再把柔光压成 VTracer 平色阶。文章来源元素逐项以误差是否下降为替换条件，整图继续保持纯矢量、可编辑文字和 600 dpi 输出。
- 新增 `assets/element-library/source-corpus/`：保留筛选出的开放获取论文、图注、PMC 版本、CC BY 许可、7 张已收候选图及高分辨率源图的来源链；订阅制与非 CC BY 内容仍只存元数据。
- 新增 `element_variants.py`：固定同一元素的 `x_mm/y_mm/width_mm/height_mm`，逐一预览不同素材变体，生成 `pick.html`/拼图，记录客户选择并回写 `asset_variant`。
- 新增 `spec_confirm.py`：把完整 spec 的元素、文字、连接、关系、画布与硬物理哈希绑定到作者回执；改动 spec 后自动失效。
- 新增 `spec_compile.py`：从元素库确定性组装 SVG，代码生成箭头/连接/文字和 mm 布局，导出 SVG、PDF、600 dpi PNG 与 provenance manifest。
- 新增 `visual_review.py`：把作者看最终预览的原话与 spec/SVG/PDF/PNG 哈希绑定；`spec_compile.py --final` 只有复核一致才进入最终导出。
- `spec_compile.py` 在本机 Cairo PDF 后端报告内存错误时回退到 PyMuPDF 矢量 PDF 转换，避免已正确生成的 SVG 被渲染器环境阻断；PNG 仍由 CairoSVG 生成。
- 新增 `nature_gate.py` 和 `assets/spec-profiles/nature-2026.json`：检查 89/183 mm、5–12 pt、0.25–3 pt、语义色族、字体和 600 dpi。
- `--safe-mode` 排除 AI raster、AI generated vector、`data-ai-generated=true` 与嵌入位图；AI 元素可用 `element_library.py ingest-ai` 记录并入库。
- 新增元素级示例 `assets/demos/element-spec/` 和规范 `references/element-spec-pipeline.md`。
- 新增 `assets/schematic-library/`：统一按物理主题、图型、3D 风格、来源和许可检索。
- 现有规模：63 条图件/出处记录，其中 20 张本地 CC BY 图可直接用于 `--ref`；43 条订阅制、默认 arXiv 许可或 NC/ND 记录只保留来源与访问入口。
- 新增 16 个主题的候选发现：Nature 系列、Physical Review 系列、Science 系列、Reviews of Modern Physics、JHEP、EPJC、PLB、Nuclear Physics A 等共得到 5,245 篇 DOI 去重候选；OpenAlex 负责跨库种子，Crossref 分页扩展 APS、Nature 与核心 HEP 期刊，并剔除词面假阳性与重复记录。
- 新增 `scripts/schematic_library.py`：目录校验、语义词检索、`--for-ref` 白名单、OpenAlex/Crossref 发现、Europe PMC/NCBI 全文回退和 CC BY 图件采集。
- `ref_guard.py` 把 `assets/schematic-library/redistributable/` 纳入合法风格书；metadata-only 图不能进入 `--ref`。
- `choice_gate.py`、`ir_layout_guard.py`、`ref_guard.py` 补上 Windows 管道 UTF-8 初始化，修复回归测试中输出乱码和闸门误报。
- 新增 `catalog.schema.json`、`taxonomy.json`、`queries.json`、许可说明和素材库 README。
- “全部”按可复现的查询覆盖和计数对账实现，不声称已经穷尽期刊创刊以来所有插图。

## v4.31 — 2026-11-25

### 纯代码重绘复杂连续渐变

- 纯代码、对象级编辑与连续渐变同时出现时，先建完整几何与遮挡，再按材质拟合原生渐变。低像素差用于诊断返修位置。纯代码路线采用连续色场，避免像素网格和平涂色块。
- 新增 [连续渐变制作与验收](references/continuous-gradient-svg.md)。记录透明光晕、渐变边界的矢量求交，以及同尺寸、放大和实际试编辑的检查方法。
- `compare_ref.py` 新增原尺寸报告，可分别查看整幅、指定面板和前景 RGB MAE。`check_svg_pair.py` 支持声明嵌套对象的显隐或变换，并可报告对齐后的 RGBA 渲染偏差。启用 RGBA 探针时，整数平移默认执行逐像素检查。
- 新工作区可通过 `tools/compare_ref.py` 调用分区诊断，转发脚本自动从技能目录加载同目录依赖。

## v4.30 — 2026-11-19

### 默认同时交付两版 SVG

- 保留原生几何重绘 `_edit.svg`，新增独立透明纹理 `_texture.svg`；两版同时输出，不仅改名，也不以旧像素稿或背景依赖修正层代替。
- 新增 `references/dual-svg.md`：前景/alpha 反混合、被挡底层与旧阴影的补全、独立纹理、真实文字、无模式切换拖动验证及能力边界。
- 新增 `assets/examples/dual-svg/` 的实际双版入口、几何/透明构建器和验证源码；命令接外部参考图与输出目录，不硬编码用户 Temp 路径。
- 新增 `check_svg_pair.py`，同步工作区模板和 AGENTS.md。示例带特定喷注场景约束，不是任意图一键转分层。


### 原生几何直接重绘（2026-11-18）

- R10 与工作区模板改为「参考图 → 完整对象 → 原生 SVG → 实际试编辑」。已有目标成品的纯重绘任务跳过生图。旧临摹和重建工具保留为像素级保真、算法对照和维护旧稿的备用。
- 新增 `references/direct-svg-redraw.md`、两张喷注图的可运行源码和 `check_direct_svg.py`。结构与真实试编辑一起验收。

## v4.29 — 2026-11-18

- 有作者草图的 A→E 路线中，A/B 共用的一句话不指定形状或颜色。L2 拦截常见形状、颜色词及色号；E 只有在形状违反可核查的硬物理时才修正。无草图路线不变。

## v4.28 — 2026-11-18

- 新阶梯首轮以 `--content-ref` 收到作者草图时走 A→E。A 只给草图和一句话，B 复用同一句话且不传任何图，C 首次引入风格书，D 以 C 为底稿、对照 A/B/C 逐元素取舍，E 只修上一稿的物理错误。
- `ladder.json` 固定本轮路线。无草图的新任务和已经开始的旧账本仍走 A→D。有草图路线出位图前必须完成 E，正式出图继续要求作者选稿回执。
- `ref_guard.py` 和 `ir_scope_gate.py` 按账本核对档位；`--ladder-outdir` 支持只预检外部生图后端。Dry run 不登记出图。

## v4.27 — 2026-11-11

**位图→矢量改为可审计的语义发布链；同色边界有独立竞争结果，三类产物职责不再混在一个 SVG 中。**

- `semantic_conflicts.py`：新增 `conflicts-v1` 报告，审计同色、弱边缘和 z-order 冲突。
- `semantic_competition.py`：边界带确定性竞争；保护物体核心、限制面积变化、拒绝拓扑断连；输出 competed elmap、置信度、报告和叠加图。
- `semantic_release.py`：统一生成 `edit-master`、`visual-master`、`visual-pick` 与 `release-v1` manifest；记录源文件、冲突报告和产物哈希。
- `release_gate.py`：校验哈希、语义 ID、嵌入位图、真文字和拾取目标；渲染器缺失时报 `unavailable`，不冒充通过。
- `edit_to_visual.py`：从修改后的 edit master 重新渲染语义掩膜、派生 trace、visual master 和 pick；支持改色、平移、缩放和适度形变，明确拒绝空掩膜、ID 漂移和不支持的输入。
- 推荐流程：`semantic_conflicts` → `semantic_competition` → 用 competed elmap 临摹 → `semantic_release` → `release_gate`。
- 投稿用 visual master；修改形状/基色用 edit master 后重建；点击整物体由 pick layer 完成。
- 完全遮挡、amodal 补全与统一“既可像素复现又可任意编辑”的表示不在当前范围。

## v4.26 — 2026-10-21

**B 档把 IR 的形体/材质写进了简报，整条阶梯从 B 起被锁死；规则从 `AGENTS.md` 搬进 skill 并变成硬闸门。**

作者原话：「B 档没有 IR 进去，IR 第一次起作用应该是在 D 档起到删除错误物理改成正确物理的作用」；
「`AGENTS.md` 里的内容也要让 skill 实现吧，否则这个 skill 根本用不了」。

### 事故（系统性 bug，不是一次失误）

UPC 单面板（`fig_upc_v427_u15/`）：A 档只写“两个核子堆成的重核”，**B 档自己加了
“竖立半透明网格板（不是地面）”**。C/D 的默认句“其余原样保留”把它冻结，成品变成
**竖立玻璃板 + 冷灰石头质感**；而更早的 v426 的 B 也写了“斜置浅灰网格薄板”，只是那轮
风格锚点（T3-38）恰好同族，所以肉眼没看出来。

### 改了什么

| 项 | 内容 |
|---|---|
| `scripts/ir_scope_gate.py` **S1 ④**（新增） | A/B 档简报里出现 IR 元素的**形体/材质词**（竖立/斜置/平放/横放/网格/薄板/玻璃/半透明/倒角/刻线/侧壁/接触阴影/冷灰/青色边缘）= 硬伤 `S1_IR_PROP_IN_BRIEF`。元素名重合仍只作软警 |
| `scripts/ref_guard.py`（接线） | 新增 `--brief` / `--tier`。**每次 sketch 出图前自动跑 `ir_scope_gate`**，非零退出 = `IR_SCOPE` 硬伤，不烧 API。档位推断：`--tier` → `--outdir` 的 rung 目录 → `brief_[ABCD].md` → `ladder.json` 的下一档 → 都推不出时**保守按 B 判**（C/D 要显式写） |
| `references/hard_rules.md`（新增） | 工作区 `AGENTS.md` 的**可移植上游版**：R0 取图预算、R1 参考图角色、R2 3D、R3 三轴、R4 元素清单、R5 客户拍板、R6 阶梯、R6.1 IR 生效范围、R7 草图/位图分界、R8 位图简报、R9 否决权、R10 临摹→重建、交付项。每条给命令与标定 |
| `scripts/init_workspace.py`（新增） | 一条命令把规则落到新工作区：写 `AGENTS.md` + `tools/*.py` 转发脚本（脚本只有 skill 这一份，永远跟 skill 升级） |
| `scripts/preview.py`（新增到 skill） | 长边 ≤1800 的 JPEG q90 预览 + 合计体积；生产图保持全尺寸，全尺寸只喂脚本 |
| `scripts/ref_role_gate.py`（从工作区搬进来） | 参考图**角色声明**（style-only 必须付三样代价：标签白名单 / 面板序列 / 不要标题图例）+ 出图后**标签泄漏**。`ref_guard` 新增 `--ref-role` / `--labels` / `--no-ref-role-check`，缺省 style-only 并自动调 |
| `scripts/render_brief_gate.py`（从工作区搬进来） | 位图简报四块（必须原样保留 / 必须改对 / 必须补上 / 标签白名单）+ 「不许简化/不许重画」；`ref_guard --stage render` 自动调 |
| `SKILL.md` | 新增「硬规则（v4.26：已内置，不依赖工作区 AGENTS.md）」总表（规则 → 闸门 → 失败码）；B 档条目写明“不许出现 IR 元素”；明确 IR 生效范围（B 无 IR / C 只改 A 真画错的 / D 逐条过 HP1–HP6）；新增「5. 取图与请求体预算」 |

### 顺带修的两个真 bug（都是把闸门跑起来才发现的）

1. **单行简报解析错位**：`parse_labels()` 按**全文第一个冒号**切白名单。B/D 简报通常是一行，
   前面已有“3D 期刊示意图：…”，于是切到错误段 → 合规简报被判 `R1_NO_WHITELIST`（误杀）。
   改成从「只许出现 / 标签白名单」**之后**找冒号。
2. **上标被 norm 吃掉**：`norm()` 只保留 `0-9a-z` + 希腊字母，`e⁺` 与 `e⁻` 都归一成 `e` →
   白名单少一个、出图后可能误报标签泄漏。加入 U+2070–U+209F。

### 标定

`ir_scope_gate.py --tier B`：

| 输入 | 结果 |
|---|---|
| `fig_upc_v427_u15/brief_B.md`（竖立半透明网格板） | **FAIL**：`竖立` / `网格` / `半透明` |
| `fig_upc_v426_u15/brief_B.md`（斜置浅灰网格薄板） | **FAIL**：`斜置` / `网格` / `薄板` |
| 同 IR 的干净 B（只有场景 + 标签白名单） | **PASS** |
| `fig_upc_v427_u15/brief_A.md` | **PASS** |

`ref_guard.py --stage sketch --brief <v427 B> --ir <IR>` → **`IR_SCOPE` 硬伤，rc=1**
（`ref_guard` 是唯一入口，直调 `gen_figure.py` 会被 `HEP_GUARD_PASSED` 拦住）。

### 没改的

- 位图档（render）不归 `ir_scope_gate` 管：按 §0.6 就是 **IR 全量 + 上一版错误清单**。
- `brief_lite.py --tier 1` 的 `DEPTH_CORE` 首条仍是“斜置的网格板”（tier 1 ≈ D 档底稿）；
  按 B 档用它会被 S1 判硬伤 —— 这是刻意的，不是误杀。

---

## v4.25 — 2026-10-21

**D 档漏删错误物理：错在简报只写了"注意到的两条"，不在模型。**

作者原话：「D 不就是用来删除错误物理的吗，你刚刚怎么没有删除」。

### 事故

UPC 单面板示意图（`fig_upc_v424/`）D 档简报只列了两条增量（beam 反向、`b` 改双向箭头），
没把 B 档沿风格图带进来的**黄色 QGP 椭圆 + 放射箭头**写进"上一轮画错"清单。
D 档的默认句是"其余严格原样保留"，于是模型把 QGP 当已画对的东西保住了 —— HP2 失败。
D2 简报点名"删除黄色椭圆 QGP 与长放射箭头"后才消失。

### 改了什么

| 项 | 内容 |
|---|---|
| `ladder_gate.py` **L14**（新增） | B/C/D 只要给了 `--ref`，简报必须有 `【参考图自带、本图不要】` 一节，逐条点名风格图里**本图不要**的物理对象。**D 档缺 = 硬伤**，B/C 缺 = 软警 |
| `SKILL.md` §4 | D 档的"错"必须是上一轮 `check_sketch` 人工项里**所有答"否"**的硬物理（HP1–HP6 逐条过），不是只写自己注意到的 |
| `SKILL.md` §4 | 用整幅风格参考图必须写泄漏黑名单；只写"不要 QGP"不够，要点名形状/位置 |
| `SKILL.md` §4 | 整幅风格图带错误物理时，允许用同一本风格书抽出的**材质卡**当 `--ref`，`--ladder-waive "ref_is_material_card_from_same_stylebook"` 放行，理由写进交付说明 |
| `references/generate-flow.md` | 同步上述三条（步骤 1 / 步骤 5 措辞改成"全量错清单"） |
| `scripts/gen_figure.py` | Windows 上 `urllib` 的 TLS 握手失败时自动改用 `curl.exe` 兜底（生成与下载两处）；本机实测不兜底就调不通生图接口 |

### 标定

`python tools/ladder_gate.py --selftest` → **11 条全过**（新增 `L14 D 档缺泄漏黑名单` 一条）。
工作区 `tools/ladder_gate.py` 与 skill `scripts/ladder_gate.py` **md5 一致**（`969548b8…`）。

---

## v4.24 — 2026-10-20

**文档瘦身：`SKILL.md` 从 121.8 KB / 1,603 行降到 41.7 KB / 653 行（粗估约 33k → 11k tokens）；`CHANGELOG.md` 从 234.5 KB / 3,802 行降到 8.1 KB / 145 行。**

作者原话：「现在的 skill 是不是多余文件太多了，容易占满上下文」—— 文件数本身不占上下文，真正占的是入口文件。

### 改了什么

| 文件 | 之前 | 之后 |
|---|---:|---:|
| `SKILL.md` | 121.8 KB / 1,603 行 | **41.7 KB / 653 行** |
| `CHANGELOG.md` | 234.5 KB / 3,802 行 | **8.1 KB / 145 行**（只留 v4.24–v4.22） |
| `references/routing.md` | — | **新增**（路由协议全文） |
| `references/generate-flow.md` | — | **新增**（路线 B 全流程） |
| `references/scripts.md` | — | **新增**（完整脚本表） |
| `docs/changelog/CHANGELOG_v1.0-v4.21.md` | — | **新增**（v1.0–v4.21 + 踩过的坑） |

### 硬规则一条没丢

- A→B→C→D 阶梯、`L9`（B 不给图 / C 给 A+B / D 给上一档）、`L10`（D 严格在上一张图上改）、`L12`（C 搬 A 的好元素）、`L13`（render 在上一张图基础上改）全部保留在 `SKILL.md`。
- 三轴物理（右手系 / 不许透视 / z=束流轴）、`render3d`、`geometry_constraints`、客户选择权（`choice_gate`）、位图→矢量三步（几何只来自临摹层）全部保留。
- 下沉文件只放表格、命令、实测依据；主文件留判据 + 指针。

# 变更记录

## v4.23 — 2026-10-20

**边界改成「亚像素等值线」—— v4.22 的 vtracer 样条其实是**退步**，这一版两项同时拿到**

作者原话：「真的已经是目前机器上最好的了？」—— 不是，测完就不是了。

### 1. 先承认 v4.22 的错

`--quant/--grow/--corner` 八个组合全扫过（q6/q8 × grow2/3 × corner60/90）：
MAE 1.285–1.287、边界带 MAE 17.76–18.14，**没有一个组合优于台阶版**（1.279 / 16.61）。
也就是说 v4.22 在「更光滑」和「更贴源图」之间做了交换，而我当时把它写成了"更好"。

根因：**vtracer 拟合的是二值掩膜**，边界落在 1 px 台阶的**外沿**，整块面积系统性偏大
（实测 N1 +1.04%、N2 +0.75%，IoU 0.9893 / 0.9923）。

### 2. 新方法（默认）：模糊 -> 0.5 等值线 -> 闭合三次 Bézier

```python
f   = gaussian_filter(mask, 1.4)
c   = measure.find_contours(f, 0.5)        # 亚像素，落在抗锯齿过渡带的中点
tck = splprep([x, y], s=0, per=True, k=3)
# 按弧长每 --step 8 px 取一段，切线做 Hermite -> Bezier
```

等值线落在**真实可见边缘**上，所以既更准又同样光滑。段数自适应（弧长 / step，夹在 64–512）。

### 3. UPC 实测（1664×909；边界带 = 两核轮廓内外各 3 px，7849 px）

| 版本 | 边界来源 | MAE | >8 | >32 | PSNR | 边界带 MAE |
|---|---|---:|---:|---:|---:|---:|
| v4.21m | 1 px 台阶 | 1.279 | 3.65% | 1.12% | 31.07 | 16.607 |
| v4.22 | vtracer 二值样条 | 1.287 | 3.65% | 1.12% | 30.96 | 18.094 |
| **v4.23** | 亚像素等值线 | **1.275** | **3.63%** | **1.10%** | 31.04 | **15.733** |

- N1 90 段 / N2 86 段；SVG 5.59 MB、29730 path / 8 text / 0 image；PDF **2.68 MB / 10 s**。
- `axis_gate` **PASS**、`gate3d_rank` **PASS**（0.0256）。
- 参数扫描：σ ∈ {1.0,1.4,1.8}、段数 ∈ {64,96,160} —— σ1.4 + 96 段最优，
  但按 `--step 8` 自适应（90/86 段）与 96 段差 0.0002，故默认用自适应。

### 4. 仍然不做的事（有依据，不是偷懒）

板 S1：512 段 × 8504 path，代价 4.4e6 超闸门；实测它做曲线对全图 MAE 的贡献
**0.000**，却会让 PDF 涨到几百 MB。→ 台阶保留。

### 5. 收尾：文字层对位校准 + 一条被否决的刷指标路线

- **文字层校准（采用）**：对每个 `<text>` 做坐标下降（dx/dy/font-size/letter-spacing），
  目标是与源图文字墨迹的 IoU。e⁻ 0.531→0.768、e⁺ 0.571→0.648、y 0.761→0.799、b 0.729→0.778。
  全图 MAE 1.275 → **1.274**。
- **细条元素也走曲线（否决）**：A1/P1/T1/B1 是多连通细笔，套等值线后全图 MAE 1.274 → **1.248**、
  >32 1.10% → 1.02%，看起来是进步；但**元素自身**误差变大（A1 6.40→6.84、T1 7.10→10.30）。
  全图变好只是因为裁掉了 1 px 描边外溢 —— **这是刷指标，不是改进**，已否决。
- ★ 新判据写进 SKILL：**判断边界/细部改得好不好，看「元素自身 MAE」，不看全图 MAE**
  （全图被大片平背景稀释；`svg_repro_check --elmap` 可以直接拆账）。

### 6. 定稿读数（`fig_upc_3d/out/upc_3d_v423.*`，1664×909）

| 项 | 数值 |
|---|---|
| 回渲染 | MAE **1.274** / >8 3.63% / >32 **1.10%** / PSNR **31.05 dB** / 边界带 **15.733** |
| SVG | 5.59 MB，29730 `<path>` / 8 `<text>` / 0 `<image>` |
| PDF | 2.68 MB（10 s） |
| `axis_gate` / `gate3d_rank` | **PASS** / **PASS**（0.0256） |

### 7. 一句话

台阶、vtracer、等值线三条都测过，**等值线唯一同时赢在 MAE / >32 / 边界带**；
但这不是"全局最优"，只是"这台机器、这条流水线上，用现有信息能做到的最好"。
仍未解决的：板 S1 保持 1 px 台阶（代价闸门，MAE 贡献 0.000）；`γ` 与 `γγ→e⁺e⁻` 仍是描边矢量而非可编辑 `<text>`。

## v4.22 — 2026-10-20

**边界从 1 px 台阶换成光滑样条（纯 CPU，vtracer）**

作者原话：「那就继续做呗，我不是说了要给我这个机器能达到的最好结果的方案吗。」

### 1. 新工具 `scripts/svg_spline.py` + `raster_to_vector_semantic.py --spline`

只改**大形体的可见像素轮廓**：掩膜 -> 裁 bbox -> vtracer(binary/spline) -> 一条闭合 Bézier，
写成 `<clipPath>` 挂到该元素组上；再在掩膜内外各留一条补色带（外 2 px、内 4 px，
颜色取**最近的元素自身像素**），保证样条相对像素台阶鼓出/缩进的半像素不露白边。

- 三个写盘前的闸门：`IoU >= 0.95`（样条回渲染 vs 掩膜）、最大连通块 >= 90%（多连通不做）、
  **代价 = 段数 x 该组 path 数 <= 2e6**。
- 定位图层组改成按 `data-element="<EID>"`；同名出现多次（多面板）明确跳过，不猜。

### 2. ★ 三个真 bug（都修了，标定值留在这里）

1. **vtracer 的输出原点不是 bbox 左上角**：它把图形居中到原点，真实位置写在
   `<path transform="translate(tx,ty)">` 里。第一版只取 `d`、丢掉 transform →
   每个元素被裁到左上角，`MAE 11.609 / >32 6.46% / PSNR 17.16`，核整块消失、板出大白洞。
2. **补色带画在被裁的同一层**：环天然在掩膜外，会被自己的 clipPath 裁掉 → 白边仍在。
   现在环与原始内容同层、但排在 `<title>` 之后（最底层），靠 clip 边界收口。
3. **S1（板）的样条会让 PDF 爆炸**：cairosvg 把 clip 路径写进**每一条被裁的 path**，
   1002 段 x 8504 path -> **PDF 563 MB、渲染 >12 min**（去掉 clip 只要 2.88 MB / 15 s）。
   而它对回渲染 MAE 的贡献是 **0.000（1.287 vs 1.287）**。→ 加 `--max-cost 2e6` 自动跳过。

### 3. UPC 实测（`fig_upc_3d/out/upc_3d_v421m_spline.*`，1664x909）

| 项 | v4.21m（台阶） | v4.22（样条） |
|---|---|---|
| `<path>` / `<text>` / `<image>` | 27703 / 8 / 0 | **29730 / 8 / 0** |
| SVG / PDF | 5.27 / 1.53 MB | **5.59 / 2.32 MB** |
| 回渲染 MAE | **1.279** | 1.287 |
| >8 / >32 | 3.54% / 1.07% | 3.65% / 1.12% |
| PSNR | 31.20 dB | 30.96 dB |
| `axis_gate` / `gate3d_rank` | PASS / 0.0267 | **PASS / 0.0268** |

样条只上在两个核：N1（63 段，IoU **0.9893**）、N2（41 段，IoU **0.9923**）。
MAE 升 0.008 是**预期代价**（台阶贴网格、样条拉圆边界），换曲面无锯齿 ——
8x 对比 `out/_boundary_cmp_v2.png`，三联 `out/_triptych_spline.png`。

### 4. 端到端 A/B（同一条流水线，只差开关）

`--no-text --spline` 2.787 vs 不开关 2.783 —— 开关本身不引入回归。

> 旧版本（v1.0–v4.21）与「踩过的坑」已归档到 [`docs/changelog/CHANGELOG_v1.0-v4.21.md`](docs/changelog/CHANGELOG_v1.0-v4.21.md)。
> 主文件只保留最近三版，避免一次读入整份 3,800 行历史。
