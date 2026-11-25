---
name: hep-nature-figure
metadata:
  version: "5.3.1"
description: >-
  Produce publication-quality high-energy nuclear physics figures: 3D schematics with
  lighting, collision/QGP illustrations, multi-panel composites, and reproductions of
  existing journal figures. Use for 科研配图、论文示意图、高能核物理配图、Nature 级配图、
  碰撞示意图、QGP 示意图、复现论文图、手绘草图转配图、参考图重绘成可编辑 SVG、3D 示意图 with shading.
  Existing image to SVG uses code-first object redraw. Journal diagrams with a settled
  layout use confirmed element specs and licensed vector assets. Data panels use code;
  image generation is for open-ended visual exploration.
---

# HEP Nature Figure — Router

## 先按交付物选路线

| 请求 | 入口 |
|---|---|
| 给了目标图，要 SVG、低像素差、放大清楚或能试移对象 | **纯代码按对象重绘**。读 [直接重绘](references/direct-svg-redraw.md)，用目标图量几何和明暗；交付前运行 [双版审查](references/svg-fidelity.md#双版交付审查)。草图阶梯和生图都不属于该路线。 |
| 给了足以确定构图的手绘草图或明确对象关系，要期刊示意图 | **元素级生产链**。先确认 [结构化 spec](references/element-spec-pipeline.md)，再用授权矢量素材按位装配。 |
| 要探索新构图或新画风 | 按需走 [草图探索](references/routing.md)。 |
| 有数据要绘图 | 用 matplotlib；混合面板按各自路线绘制后拼版。 |

## 分工：谁画、谁约束、谁验收

**先选路线，再由该路线的脚本回渲染和验收。**

| 环节 | 谁做 | 为什么 |
|---|---|---|
| **画** | **按对象重绘 SVG**；探索新图时可先生成参考位图 | 模型读图、定形体和叠放；手写 SVG 或写逐图脚本实现几何与光影 |
| **约束** | **IR + geometry_constraints** | 防"好看但物理错"。模型单干时最爱犯这个 |
| **验收** | **三道门禁** | 模型看不见自己的输出，这里能量（见下「三道门禁是谁」） |
| **拍板** | **作者本人** | 元素装配按 spec 和图面回执；探索稿由作者选定草图再出成品位图；指定成品重绘沿用已有目标图 |
| **返修** | **`repair_brief.py` → 模型改** | 光说"文字重叠"模型只能猜；返修单给**归一化坐标 + 具体错开量** |

**最终 SVG 默认双版交付：原生几何版 + 独立透明纹理版。** 先读 [直接重绘](references/direct-svg-redraw.md)，再读 [双版流程](references/dual-svg.md)。默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。

**V5.3 结构化 SVG 重绘**：先量轮廓和锚点，再画完整可移动的原生几何、按对象拟合连续材质。球缘、喷注锥口、环纹和文字逐个校准。用 `review_redraw.py` 将两版保真、关键轮廓、4 倍局部及显隐和移动合并验收。首轮回渲染发现轴杆、箭头或线圈偏位，回到几何修改。见 [连续渐变流程](references/continuous-gradient-svg.md)。

### 元素级生产链（v5.1）

新创作优先把图写成**可执行元素 spec（IR）**：元素、文字、连接、相对关系、画布毫米尺寸和硬物理约束。作者先确认完整 spec，再由代码从元素库精确装配。

```bash
python scripts/spec_confirm.py figure.spec.yaml --show
python scripts/spec_confirm.py figure.spec.yaml --record --by client --reply "原话"
python scripts/element_variants.py preview --spec figure.spec.yaml \
  --element participant_nucleon --safe-only --outdir variants/nucleon
python scripts/spec_compile.py figure.spec.yaml --outdir out --stem figure --safe-mode
python scripts/visual_review.py --spec figure.spec.yaml --svg out/figure.svg \
  --png out/figure.png --pdf out/figure.pdf --record --by client --reply "原话"
python scripts/spec_compile.py figure.spec.yaml --outdir out --stem figure --safe-mode --final
```

- 元素库：`assets/element-library/`，每个 SVG 带授权、哈希、物理角色和 AI/软件来源；文章来源元素的 `file` 必须是 `_edit.svg`；
- 无限缩放：`_edit.svg` 用圆/路径/真渐变/原生文字；`_texture.svg` 只是可选平滑跟踪对照，不作为默认入口，也不把逐像素色块冒充重建质量；
- 语料扩展：PMC OA 之外可用 `publisher_figure_harvester.py`（当前 APS/PR CC BY）和 `figure_element_candidates.py` 建立可恢复的全图审查队列；自动 crop 在人工对象审查和原生重绘前不得入库；
- 高优先级重建：`priority_element_rebuild.py` 对 `high` 图逐对象去背景、做保守单对象审核并生成平滑 SVG candidate；含文字、坐标轴、连线的复合区域必须进入人工拆分，不得整块晋升为元素；
- 缺元素：`element_library.py ingest-ai` 登记 AI 补充素材；
- 投稿安全模式：`--safe-mode` 排除 AI 像素、AI 生成矢量和嵌入位图；
- Nature 门禁：`nature_gate.py` 检查 89/183 mm、字号、线宽、语义色板和 600 dpi；
- `--final` 要求视觉回执与本次 SVG/PDF/PNG 哈希一致；
- 修改 spec 后重新确认并编译。

详见 [元素级生产链](references/element-spec-pipeline.md)。已有作者成品、只需可编辑 SVG 时仍走直接重绘。

### 草图探索链（仅用于探索路线）

**三条职责，各管一段：**

```
IR 管物理  ｜  按需生图探索风格  ｜  SVG 按对象重绘
```

```
输入：参考图 / 手绘草图 / 文字描述
        ↓
① 写 IR —— 物理内容 + geometry_constraints（**只干这一件事**）
        ↓
② IR → 生图简报（ir_to_genbrief.py）→ 生图（gen_figure.py --ref 风格参考图）
   先出【草图】，草图也要【矢量化输出】（sketch_to_vector.py）让人能直接改
        ↓
   ★ 闸口①  check_sketch.py 草图 —— 几何约束逐条对账，答完才往下走
        ↓
   ★★ 交接点（v3.0）sketch_handoff.py —— 候选 + 可编辑 SVG 交给作者挑/改
      作者点一下 → make_picker.py 出 pick.html → choice_gate.py 收回执（★ v3.1）
      作者改完 → sketch_ingest.py 灌回（重过闸口①）
        ↓
③ 出【成品位图】（gen_figure.py --stage render，同样带 --ref）
        ↓
   ★ 闸口②  check_sketch.py 成品位图 —— **同一个脚本再跑一次**
        （以前只跑闸口①，闸口②是漏的）
        ↓
④ 同时制作两版 SVG：原生几何重绘 → 遮挡补全、前景反混合 → 独立透明纹理版
        回渲染，隐藏或移动关键对象核对被挡几何
        ↓
⑤ 三道门禁 + 返修单 → 交付
```

### ★ 三道门禁是谁、各拦什么

"三道门禁"以前全文只出现过名字、**从没定义过**（2026-09-26 补）。实际是三个脚本，
各拦一类"模型看不见自己"的错：

| 门禁 | 脚本 | 拦什么 | 何时跑 |
|---|---|---|---|
| **① 渲染** | `check_render.py` | **静默失败**：渐变退化成纯黑、字体缺失变豆腐块、元素根本没画出来 —— 渲染器不报错，只能靠它抓 | 每次出图稿 |
| **② 风格** | `delivery_gate.py` | 离目标风格超限（按类内离散度分级判定，**不是**"调到某个数"） | A 类复现必跑 |
| **③ 投稿** | `check_delivery.py` | 不是真矢量 / 文字被转成轮廓 / 字号 <5pt / 位图有效 dpi <300 / 整页被位图盖住 | 交付前 |

**另有第四个（后来加的，也按阻断算）**：`audit_composition.py` —— **局部构图**
（文字互压、线穿文字、出界贴边、留白失衡）。全局指标可能全过，但这类问题必须修。

**第五个（v3.3 加）：`projection_gate.py` —— T3 图的【投影 + 空间关系】闸口。**
它拦的是那个**致命组合**：*主平面正对读者（x 水平 / y 竖直）+ 法线轴画成有长度* ——
这两件事同时要，几何上不可能，图必然扁平。
判据 P0–P3（轴方向 / 前缩 / 不许透视）+ G1–G2（穿透 / 遮挡）。

> ★ 它量的是 **IR 的声明，不是渲染出来的图**。为什么：两个"量图"的探针都被校准否掉了
> —— 塑形覆盖率会把**扁的**判成更立体；边线方向直方图在 T3-30 真图上只有 6.0%，
> 和生图模型的 5.7–9.3% 分不开（它量的是边缘锐利度）。而**声明层的自相矛盾是可判定的**，
> 出图之前就能抓。详见 `references/3d-checklist.md`。

```bash
python3 scripts/projection_gate.py ir/xxx.ir.yaml          # 画之前跑
python3 scripts/projection_gate.py ir/*.ir.yaml --strict    # 警告也算失败
```

**第六个（v4.0 加）：`check_3d.py` —— 在栅格上量「**这张图读起来是实体、还是贴纸**」。**
五道门禁**全都看不见**这个失败（扁的 v7 与 3D 的 v7 一样能全过；风格门禁的白名单里
没有任何一条量的是**渲染方式**）。所以它直接在像素上量四条硬判据：
**C1 接触阴影**（形体必须把它站的那块板压暗）/ **C2 面内内容确实被投影**（面内一串等间隔
元素在屏幕上的间隔必须不匀）/ **C3 参考圆被压扁**（同一个面里的「各向同性」参考必须是扁的，
否则 C2 的不匀读起来像随手压扁）/ **C4 明暗带法线场**（高光偏心 + 边缘比中半径暗）。
★ 它是**面向版式标定的**：判据通用，但搜索窗口（画布毫米 / 受检形体窗口 / 颜色谓词）要按你的
版式改；找不到受检形体会报 **C0 失败**，不会静默放行。

```bash
python3 scripts/check_3d.py out/figure_3d.png         # 0 = 四条全过
python3 scripts/check_render_mode.py out/figure_3d.svg # 交付前：真有渐变吗 + 有没有并排图
```

**第七个（v4.1 加）：`axis_gate.py` —— 三轴物理闸门。**

实测（UPC）生图模型把**同一根 x 轴的两端标成了两个名字**（一端 `x`、一端 `y`）→
读者会把反应平面读错。五道门禁**一条也不看**轴名与轴杆的对应关系，所以单加一道：

- `X1` 坐标约定必须被声明（IR 的 `composition.坐标约定{面内,法线}` 或 `elements[].params.张成轴/法线轴`）；
- `X2` SVG 文字层的轴名多重集 == 声明；`X5` 不许出现第四个单字母轴名；
- `X3` **同一轴名的两次标注必须落在同一根轴杆的两端**（抓上面那个 bug 的判据）；
- `X4` 三轴方向两两相差 > 15°；
- `X0` SVG 与位图的轴名多重集一致（默认软警，位图也是交付件时加 `--strict-x0` 变硬伤）；
- `X6` 板面与三轴是否同一投影 —— **只作读数 + 软警**（板边方向检测在 UPC 上不稳，当硬判据会误杀好图）。
- **`X7` 右手定则（v4.15 加，作者 2026-10-14：「xyz 之间满足右手定则」）**：
  ① IR 必须**书面声明右手系**（`composition.坐标约定.手性: 右手`；声明「左手」= 硬伤；没声明默认
  只出软警，`--strict-handedness` 才硬判）；② **图上三根轴杆的方向必须与 IR 声明的 `轴方向_deg`
  一一对上**（每根 ≤ `--axis-tol`，默认 20°）。
  ★ 为什么 ② 才是可核对的形式：**手性在平行投影里本身不可观测** —— 把一张轴测图镜像过去还是
  合法的轴测图，光看图判不出左右手；能查的是「画出来的那套三轴 == 声明的那套（声明写着右手系）」。
- **`X8` 投影类型（v4.15 加：「斜二测、正等测」）**：`composition.projection.类型` 必须声明，
  且不许是「透视 / perspective」（硬伤）；给了 `轴方向_deg` + `前缩` 时再硬判几何自洽 ——
  · **正交 / 轴测**（正等测 / 等轴测 / 正交相机）：`Σ f²·e^{2iθ} ≈ 0`（≤0.05，轴测正投影的充要条件）；
  · **斜二测 / 斜投影**：存在一对面内轴（屏幕夹角 ≈ 90°、前缩相等且最大），第三根（法线 / 深度轴）
  前缩更小、与最近的面内轴夹角落在 15°–75°。
  缺声明 = 硬伤（`--allow-missing-projection` 降级为软警）。
- **`X9` 束流方向（v4.15 加，作者 2026-10-14：「z 轴一般是束流方向」）**：IR 必须能读出束流轴
  （`composition.坐标约定.束流轴: z`，或文本里「z=束流方向 / 沿束流轴 z」）—— 读不出 = 硬伤
  （`--allow-missing-beam` 降级）；**不是 z 时必须给 `束流轴理由:`**；本图**确实没有束流**的写
  `束流轴: 无`。图上读数：最长的一根轴杆应当是束流轴（`X9b`，软警）。
- 标定：`axis_gate.py --selftest`（X7 / X8 / X9 共 15 条，写临时 IR）；真图回归见脚本文件头
  （`fig_upc_3d/out/upc_3d.svg` PASS、`fig_upc_3d/trace/upc_trace_prelabel.svg` FAIL）。

★ `--png` 传**与 SVG 同尺寸**的那张位图：闸门会对它做**无 OCR 字形识别**（连通域 + 模板匹配，
x/y/z 实测可信度 0.75–0.89），于是**位图阶段**就能抓到模型的错标，不必等矢量重建完。

```bash
python3 scripts/axis_gate.py --svg out/fig.svg --png gen/chosen.png --ir ir/fig.ir.yaml \
        --json rep.json --annot annot.png
```

**第八个（v4.1 加）：`check_3d_generic.py` —— 图种无关的 3D 闸门（不用硬编码窗）。**

`check_3d.py` 判据通用但**搜索窗按版式标定**，换图就得改窗。这一道把窗去掉：主体与板面
都由像素自己找，只留四条直接量像素的判据 —— `3D0` 主体存在；`3D1` 最大浅灰面连通块
>= 3% 画布；`3D2` 板面上有**接触阴影**（板内比中位亮度暗 6% 的像素 >= 8% 板面，
且至少一块 >= 0.08% 画布）；`3D3` 主体最亮点**偏离几何中心 > 0.08 半轴**（高光偏移 = 有法线场）。
IR 声明没有板面（或 `--expect-plane no`）时 `3D1/3D2` 自动降级为读数。

★ 已知限制：`3D1/3D2` 只认「浅灰」板面；板面用深色/彩色表达的图会被误判 →
用 `--expect-plane no` 只查 3D3（体积明暗）。换图先看读数再定。

```bash
python3 scripts/check_3d_generic.py out/fig.png --ir ir/fig.ir.yaml --annot annot3d.png
python3 scripts/gates_selftest.py      # 两道新闸门的回归标定表（缺样本自动跳过）
```

**把这两道挂进出图流水线（`ref_guard.py`，v4.1）**：出图**前**多一道 **IR 契约**
（`style.mode` 不是 `render3d` 即硬伤，除非 `--allow-flat "理由"` 且写进交付说明；
并且 IR 必须声明坐标约定）；出图**后** `--post` 依次跑上面两道，任一不过 = 非零退出。

```bash
python3 scripts/ref_guard.py --run --post \
    --post-3d <成品位图.png> --axis-svg <交付.svg> --axis-png <同尺寸位图.png> \
    --brief <简报.md> --stage render --ir <IR> --ref <风格书> --content-ref <草图> ...
```

跑完把报告交给 `repair_brief.py` 变成**返修单**（归一化坐标 + 具体改法），
再让模型去改 —— 这是"模型画、skill 验收"分工的关键一环。

> ⚠️ 门禁挡不住物理。物理只由两个 `check_sketch.py` 闸口 + `axis_gate.py`（轴名 ↔ 轴杆、板面 ↔ 三轴）+ 人看图把关（纪律 4）。

### ★ ④ 双版 SVG（默认同时交付）

默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。 具体透明分离和验收见 [双版 SVG](references/dual-svg.md)。不得仅改文件名冒充两版，不得将像素稿或背景依赖修正层当纹理版。隐藏几何参考不等于自动驱动显示纹理，能力边界须说明。

读 [直接重绘 SVG](references/direct-svg-redraw.md)。按对象直接重绘：量参考图的比例与锚点 → 列对象和前后关系 → 画出完整形体（包括可合理补画的遮挡部分） → 用真渐变、独立阴影和原生文字塑形 → 回渲染、隐藏/移动一个对象核对。SVG 不嵌位图；每个物体是可单独编辑的命名组。

交可编辑 SVG、回渲染的 PNG、所用绘制源码与「参考图 | SVG 回渲染」对照，记录一次试编辑结果。正式投稿继续按已有条件导出 PDF 并过相应门禁。 `check_direct_svg.py` 检查结构，并可输出一次隐藏对象后的回渲染；要看图确认露出的网格、喷注等是否完整。

已确认位图基准时，两版均通过 [位图保真门禁](references/svg-fidelity.md)，并保存 [4 倍局部对照](references/continuous-gradient-svg.md) 和实际试编辑。旧算法见 [临摹备用](references/bitmap-to-vector.md)，用于算法对照和维护已有临摹稿。草图快速交接沿用 `sketch_to_vector.py`。

### ★ 物理检查要在【最终矢量】上做

**位图对 ≠ 重画出来的对。** 实测（`sketch2nature_demo/`）：同一模型从位图重画时，
几何约束 **6 项只过 2 项**（喷注夹角 173° 应 180°、表面偏置 0.85 应 0.72）。

所以 IR 的 `geometry_constraints` 得在**重画之后再过一遍**。

### `scene_render.py` 的定位（别当新概念）

它是 **"IR 直接渲染成 SVG" 的可选后端**，不是什么新的一层。
**它只在"要批量扫描参数 / 要代码直渲"时有用** ——
自由创作和复现都用不到它。

> 走过的弯路：一度把它包装成"Scene Graph 层"，说成 A/B 共用的枢纽。
> **它和可执行 IR 是同一个东西**（只是多了 layers/text/formula 三个字段），
> 包装成新层是噪声。

### 三条路线怎么选

|  | **路线 1：直接代码出图** | **路线 2：生图草图 → 代码完善** | **路线 3：生图草图 → 成品位图 → 重绘 SVG** |
|---|---|---|---|
| 中间产物 | 无 | 草图 PNG + **草图 SVG** | 草图 PNG + **草图 SVG** + 成品位图 |
| 谁保证物理 | 代码（`geometry_constraints` 直接可算） | 闸口① | 闸口① + 闸口② |
| 主要用途 | 复现已确定几何、布局或批量参数 | 比较或人工编辑备选构图 | 探索材质表现并交付精修位图 |
| 成本 | 低 | 中 | 高 |

- **从文字或手稿探索新图**按需走路线 2 / 3；已有指定成品且要可编辑 SVG，直接重绘。
- **要批量扫参数 / 要代码直渲** → 路线 1（`scene_render.py` IR 直渲，或 `svg_lib` 手写）
- **要人插手改草图** → 路线 2（草图矢量化后交给人在 Illustrator 里改，再代码完善）

> 路线 2 和 3 的**前两段完全一样**（IR → 简报 → 生图 → 矢量化草图 → 闸口①）。
> 区别只在第三段：2 是代码/模型接着完善草图，3 是再多跑一张成品位图。

### ★ 生图那一步的三条硬规矩

1. **API key 由使用者自己提供** —— `gen_figure.py` 读环境变量 `DASHSCOPE_API_KEY`，
   脚本里**不存任何 key**。别人装了 skill 就用他自己的 key（没 key 也能 `--dry-run` 自检）。
2. **必须给风格参考图**（`--ref`，可多张）—— 参考图 = Nature **风格书**。
   只给文字简报，出来的图一定很"通用"。`_T3精选` 这类本地图直接传就行；
   要公开发布时用 `assets/t3-exemplars/` 或 `assets/schematic-library/redistributable/`
   里的 CC BY 4.0 图（先跑 `schematic_library.py search --for-ref`）。
   ★ 给的是**风格**（配色/线条/材质/光影/**渲染方式**），**不是内容模板** ——
   本图内容可以和参考图**完全不同**；参考图里没有的物理对象照 IR 画出来就行，
   不要因为"参考图里没有"就不画。**「期刊矢量插画风」≠「扁平 2D」**：
   T3-02 那条线本身就是 3D 渲染的矢量插画（见「参考图 = 风格书」一节）。
3. **两个产物都要落盘 + 记调用记录** —— 草图、成品位图都要输出出来
   （草图还要矢量化成 SVG），`gen/` 里同时写 `calls.jsonl`（model/seed/size/refs/
   prompt 指纹/输出文件），复现和核对计费都靠它。


## 这个 skill 的核心

**把「物理意图」和「这张图怎么画」强制拆开，并在动手前写成 IR。**

价值不在于"AI 会画图"，而在于**让物理正确成为流程里的强制约束**，而不是靠人盯着。
老师原话的失败模式是"花里胡哨但物理表达不准确"——IR 就是防这个的。

**关键性质**：IR 与后端无关。同一份 IR 可交给 SVG / matplotlib / Blender / Illustrator。
**后端按图选，不预设。**

---


## 硬规则（v5.1：已内置，不依赖工作区 `AGENTS.md`）

> v5.1 增加许可分级示意图库：`assets/schematic-library/`。找参考图先运行
> `python scripts/schematic_library.py search --topic <topic> --for-ref`；只有 CC0 / CC BY
> 本地图可进 `--ref`。完整版 + 每条标定：**`references/hard_rules.md`**。工作区的 `AGENTS.md` 只是副本/补充；
> 两者冲突时**取更严的那条**。
> 新工作区落地：`python scripts/init_workspace.py --dir <ws>` —— 写 `AGENTS.md`
> + `tools/` 转发脚本（`python tools/ref_guard.py` 照样可用，脚本只有 skill 这一份）。

规则不靠记性，靠闸门。下表是「规则 → 闸门 → 失败码」，全部由 `scripts/ref_guard.py`
在调 API 之前串起来（直调 `gen_figure.py` 会被令牌拦住）：

| # | 硬规则 | 闸门 | 失败码 |
|---|---|---|---|
| R0 | 取图预算：生产图全尺寸、模型只看 ≤1800px q90、单会话 ≤40 张 | `preview.py`（约定，非闸门） | — |
| R1 | `--ref` 只收风格书；`--content-ref` 只收手绘 / 本阶梯已登记 rung；同一图不许兼两角色 | `ref_guard.py` | `SELF_OUTPUT` / `DEMO_REF` / `SAME_FILE` |
| R2 | 一律 `render3d`；扁平只许出现在定量数据面板与纯抽象内容 | `ref_guard` IR 契约 + `check_3d_generic.py` | `NOT_3D` / `3D0–3D3` |
| R3 | 三轴：X1–X5 轴名与轴杆一一对应、X7 右手系、X8 投影、X9 束流轴=z | `axis_gate.py` | `X1–X9` |
| R4 | 出草图前 IR 元素清单给客户过目并点头 | `element_list.py --check` | `NO_ELEMENT_ACK` |
| R5 | 出成品前客户挑草图、`--by client` 回执 | `choice_gate.py` | `NO_CLIENT_CHOICE` |
| R6 | 走生图探索时，无作者草图 A→D，有作者草图 A→E。账本固定路线，元素替换与物理修正按所属路线取图 | `ladder_gate.py` | `L1–L14` |
| **R6.1** | **B 档没有 IR：B 简报不许出现板/网格/玻璃/薄板/竖立/斜置/半透明/冷灰等 IR 形体与材质词** | **`ir_scope_gate.py`（已接进 `ref_guard`）** | **`IR_SCOPE` / `S1_IR_PROP_IN_BRIEF`** |
| R7 | 草图管“对不对”，位图管“全不全、精不精” | `check_sketch.py` | 人工逐条答“否”就重出 |
| R8 | 位图简报 = IR 全量 + 上一版错误清单；构图参考原样送 | `render_brief_gate.py` + 复检 | — |
| R9 | 物理否决美观；美观否决画法；硬物理每条必须给 `measure` | `ir_scope_gate.py` S3/S4 + IR 契约 | `NO_HARD_PHYSICS` |
| R10 | 双版 SVG 共享对象、文字与画布，补全遮挡并试移关键对象。有位图基准时检查原尺寸、细结构和 4 倍局部 | `review_redraw.py`（有位图基准）和回渲染目检 | — |
| R11 | 元素素材必须带授权、署名、哈希、物理角色与 AI/软件来源；AI 资产显式标记 | `element_library.py validate` | — |
| R12 | 完整 spec 必须由客户确认；投稿安全模式排除 AI 资产与嵌入位图 | `spec_confirm.py` + `nature_gate.py` | `NO_SPEC_CONFIRMATION` / `AI_ASSET_IN_SAFE_MODE` |

**R6.1 是 v4.26 新增的硬闸门**（作者 2026-10-21：「B 档没有 IR 进去」）。
它拦的是一次实测过的系统性 bug：A 档只写“两个核子堆成的重核”，B 档自己加了
“竖立半透明网格板”，C/D 的“原样保留”把它冻结成竖玻璃板 + 冷灰石材质；
而更早那版的 B 也带了“斜置浅灰网格薄板”，只是风格锚点恰好同族所以没人看出来。
有账本时档位与路线由账本推断，显式 `--tier` 必须与之相符；脱离账本单查时可由简报文件名推断。

---


## 路由协议（速查；完整版见 `references/routing.md`）

> **动手判定任务 / 写 IR / 选后端 / 跑验证 / 走 A→B→C→D 之前，先读 `references/routing.md`。**
> 本节只是硬判据速查；表格、命令、实测依据全在下沉文件里。

### 0. 先判任务，再判图型

| 任务 | 输入 | 走法 |
|---|---|---|
| **A 复现** | 参考图 | 本 skill 主干，逐条对账 |
| **B 创作** | 手绘草图 / 文字 | 本 skill 主干 |
| **C 数据图** | 数据 + 坐标轴 | matplotlib，本 skill 只加样式约束 |
| **D 复合** | 上述组合 | 分面板做，`assemble_panels.py` 拼版 |

| 图型 | 特征 | 主后端 |
|---|---|---|
| **T1** | 2D 定量（谱 / 曲线 / 误差带） | matplotlib |
| **T2** | 3D 曲面 | matplotlib（**不要 Mathematica**，实测会栅格化） |
| **T3** | 3D 示意图 + 光影 | **SVG 手绘（本 skill 主战场）** |

### 1. 写 IR（强制，不可跳过）

- 读 `references/ir-spec.md`。模型**永远看不到 IR**，只看到 `ir_to_genbrief.py` 编译出的简报；编译器丢字段 = IR 白写。改 IR / 模板后跑 `ir_brief_audit.py`。
- 三个必填：`figure.physics_claim`；每个元素的 `physics_role`（不许写“装饰”）；`style.classification` + `evidence`。
- **画序 = z 序**：背景 → 后壳 → 前表面 → 表面线 → 前景。
- 物理空间关系必须写成可计算的 `geometry_constraints`，分两节：`约束`（机器判不了，闸口逐条问人）与 `机器`（闸口自己量，如 Lorentz 收缩方向、弦长比）。
- `style.mode: render3d`；坐标约定必须声明：**右手系**、投影类型（正交 / 轴测 / 斜二测，**不许透视**）、**束流轴一般是 z**（无束流写“无”）。
- 硬物理与画法分开：`hard_physics` 每条必须给 `measure`；给不出 measure 的降为 `style_preferences`，可被更美观的画法替换；**美观不能否决物理**。

### 2. 选后端与交付

| 图型 | 首选 | 备选 |
|---|---|---|
| 数据图 | matplotlib | ROOT |
| 3D 曲面 | matplotlib | Asymptote |
| 3D 示意图 | `svg_lib` 生成 → Inkscape 精修 | Illustrator |
| 真 3D 几何 | Blender | — |
| 公式密集 | TikZ / Ipe | Asymptote |
| 复合拼版 | `assemble_panels.py` | Inkscape |

- 交付 **SVG + PDF/EPS 都要出**：SVG 是工作稿（保留图层），PDF 是投稿稿；不要只出 PDF，也不要只出 SVG。
- 缺工具 = 去装（`check_tools.py` 给命令），**不许降级凑合**。

### 3. 验证（不可跳过）

1. `check_render.py` —— 抓渐变失效 / 字体丢失 / 元素没画出来。
2. `compare_ref.py` —— **所有任务必做**的并排图，让人 5 秒内判“像不像参考图的渲染方式”。
3. `style_bench.py` —— A 类任务量风格偏离；它只诊断，不是优化目标。
4. `repair_brief.py` —— 门禁报告 → 归一化坐标 + 具体改法的返修单。
5. `axis_gate.py` / `check_3d_generic.py` / `gate3d_rank.py` / `check_delivery.py` —— 三轴、3D、交付硬闸门。
6. **最后必须人看图**；物理正确性无法自动验证（纪律 4）。

### 4. 出图入口与两条阶梯（v4.29）

**已选择生图探索并有作者草图时走 A→E**：在新账本首轮把手稿放入 `--content-ref`，A 用手稿 + ≤80 字符的一句话，B 用完全相同的一句话、不传任何图，C 加风格书 + 面板序列 + 输出硬约束、不传构图图，D 给本账本 A/B/C 各一张、逐元素挑选，在 C 底稿上替换对应处，E 拿紧邻上一稿只改物理。风格书从 C 沿用到位图。最后一张合格 E 草图仍交作者选择后再正式出位图。详见 [routing](references/routing.md)。

**A/B 共用的一句话不得预设形状或颜色（L2）**。例如「画一张高能核物理中的三维喷注淬火期刊示意图，展示背对背喷注」，省去「暖色椭球 QGP」「蓝色喷注」等画法。D 可以选用物理成立、画得更好的形状；仅当它确实违反硬物理并有 `[HPn]` 或可量证据，才在 E 局部改形状，保留原有材质。不把偏离手稿外形或默认椭球本身判作物理错误。

**无作者草图及已开始的旧账本仍按以下 A→D 规则。**

- **A 档**：一句话（≤80 字符），**默认不带 `--ref`**；只作诊断，**不进交付链**。
- **出草图前**：把 IR 的**元素清单**（中文 5–10 行）贴给客户过目 / 加项，**客户点头才开跑**（v4.19）。
- **B 档**：A 的文字 + 面板序列 + 输出硬约束；**必须带 `--ref` 风格书**；**不给上一档的图**（L9）；不写“保留”措辞（B 只跑一轮）。
- **B 档简报里不许出现 IR 的元素**（v4.26，硬闸门）：只许写 A 的文字 + 面板序列 + 标签白名单 / 不要图例这类输出硬约束；**不许写板 / 网格 / 玻璃 / 薄板 / 竖立 / 斜置 / 半透明 / 冷灰等形体与材质词**。它们属于 IR 的 elements，第一次可以出现是在 C 档。`ir_scope_gate.py --tier B` 会把这类词判硬伤（`S1_IR_PROP_IN_BRIEF`）。实测 v427：A 只说“两个核子堆成的重核”，B 自己加了“竖立半透明网格板（不是地面）”，整条阶梯从 B 起就被竖板与灰石材质锁死。
- **C 档 = 元素替换档**：必须给 **A、B 两张图**；简报必须写“把 A 档画得好的元素搬进来、替换 B 里对应的那一处”（L12）。
- **D 档 = 物理修正档**：必须给**紧邻上一档的图**；严格在上一张图上改，只补上一轮真画错的，**其余形状 / 质感 / 配色 / 视角都不许变**（L10/L11）。B 档不判 L10。
- **D 档的“错”必须来自上一轮 `check_sketch` 人工项里所有答“否”的硬物理，不是只写自己注意到的那两条**（v4.25）。写 D 简报前先逐条过 HP1–HP6；漏一条，模型就会按“其余原样保留”把它保住。实测 UPC：D 档只写 beam/b，黄色 QGP 椭圆被完整保留；D2 点名删除后才消失。
- **IR 的生效范围**（v4.26 明确）：B 档没有 IR；C 档只许用 IR 去“改 A 档真画错的东西”（`ir_scope_gate.py` 的 S3 要求每条带 `[HPn]` 或可量的证据）；D 档才逐条过 HP1–HP6。**IR 的版式 / 材质偏好不构成物理要求** —— 物理对的排法有很多种。
- **用了整幅风格参考图，就必须写泄漏黑名单**（v4.25）：B/C/D 简报里必须有 `【参考图自带、本图不要】` 一节，逐条点名风格图里的物理对象（如“参考图自带的黄色椭圆 QGP 火球 + 放射箭头，本图不要”）。只写“不要 QGP”不够——要点名它的形状/位置，否则模型会把它当风格抄进来。`ladder_gate.py` 的 **L14** 会硬判 D 档缺这一节。
- **整幅风格图带错误物理时，允许用同一本风格书抽出的“材质卡”当 `--ref`**（v4.25）：材质卡只保留材质/光照/渲染语言；L7 会报“风格图不一致”，用 `--ladder-waive "ref_is_material_card_from_same_stylebook"` 放行，理由写进交付说明。
- **L9**：B 给图 = 硬伤；C 缺 A 或 B = 硬伤；D 缺上一档 = 硬伤。**L7**：阶梯里第一个带 `refs` 的 rung 是风格锚点。
- 机械闸门：`ref_guard.py --run -- ...`（先查后调，查不过不烧 API 钱）；账本 `ladder.json`；`ladder_gate.py --selftest` 标定 L9/L12/L13。
- **3D 感是首要判据**；草图管“基础物理”（三轴一一对应、方向关系、b 横向错开），位图管“IR 齐全度 + 精修”。
- **选择权在客户**：`make_picker.py` → 客户点选 → `choice_gate.py --record --by client`；没有回执不许出成品位图。

### 5. 取图与请求体预算（v4.26）

- **生产图保持全尺寸**（如 2336×1280）；描摹、`axis_gate.py`、`keep_gate.py`、矢量重建只用全尺寸文件。
- **模型（对话）只看长边 ≤1800 的 JPEG q90**：`python scripts/preview.py <文件或目录...>`，默认输出到 `_preview/`，并打印每张尺寸与合计体积。
- **4up / 长条拼图也先缩到 1800px 再看**；全尺寸只喂脚本。
- **单会话预览 ≤ 40 张**（约 8–12 MB base64）；到量就开新会话，把“当前选定 + 待改清单”带过去，不要搬整段历史。
- 依据：请求体上限（DeepSeek Responses 为 48 MiB）按**整段历史**算，看过的每张图每轮都会重新 base64 发送。实测旧会话 20 次 `view_image` 累计 49.68 MB 触发 413 —— **与 skill 仓库体积无关**。

---


## 路线 B：图像生成（速查；完整命令链见 `references/generate-flow.md`）

> **动手出图之前，先读 `references/generate-flow.md`。** 需生成并精修新位图时走这条路；已有目标图的直接重绘从第 7 步开始。本节是 7 步骨架与硬约束，每一步的命令、参数、实测读数在下沉文件里。

1. **IR → 简报**：`ir_to_genbrief.py --stage sketch`。默认先走 `brief_lite.py --tier 0`（一句话 + 面板序列 + 输出硬约束），看图后 `--tier 1 --add 上一轮画错.md` 只补错的那几条（= 上一轮 `check_sketch` 人工项里所有答“否”的硬物理，不是只写注意到的）；完整规格书留给 A 类复现。
2. **出草图**：`gen_figure.py --stage sketch --ref <风格书> --seeds ...`；产物 `sketch_sN.png` + `calls.jsonl`。模型稳定画 1–2 px 外框，**别求它去掉**，用 `trim_border.py` 确定性地裁（两层外框加 `--bg 0.975`）。
3. **草图矢量化**：`sketch_to_vector.py ... --ocr`；每形体一个子层，人可直接改。
4. **闸口①**：`check_sketch.py --ir ...`。过闸后 `sketch_handoff.py` 交候选 → `make_picker.py` → `choice_gate.py` 收回执；客户改完用 `sketch_ingest.py` 灌回，**强制重过闸口①**。
5. **出成品位图**：`ir_to_genbrief.py --stage render` → `ref_guard.py --run -- ... --stage render --content-ref <作者选中的末档草图> --ref <风格书>`。末档是 D（无手稿）或 E（有手稿）；草图**原样送**（`auto -> full`），只有草图本身扁平时才考虑 `--content-ref-mode layout`。简报写「在上一张图的基础上改，别换掉画对的」，对照硬物理逐条列出仍需修正或补齐的内容。
   - `--ref` 只收风格书（`assets/t3-exemplars/`、`assets/schematic-library/redistributable/`、`_T3精选/`）；`--content-ref` 只收手绘输入或本阶梯已登记的 rung；`assets/demos/**` 任何阶段不许当参考；同一张图不许同时占两个角色。
6. **闸口②**：`check_sketch.py --sketch <草图>` 再跑一次；再 `gate3d_rank.py --require-all`、`axis_gate.py`、`check_3d_generic.py`。
7. **双版 SVG**：默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。 按 [重绘](references/direct-svg-redraw.md) 和 [双版流程](references/dual-svg.md) 制作，纹理版另做不切换纹理的拖动/隐藏试验。
   - 临摹备用仍可用 `semantic_conflicts.py` / `semantic_competition.py` 审计边界，再以 `semantic_release.py` 发布、`release_gate.py` 校验；旧 edit master 的修改用 `edit_to_visual.py` 重建。它们不替代默认双版流程，不负责补全遮挡。

---

## 否决权分层：硬物理 / 画法 / 美观（2026-10-11，作者定）

> 「IR 是物理正确的东西，用来检查生图模型的物理正确性，但有时候也会有不美观的地方，
>  那我该怎么办呢……其实 IR 里的那个杏仁状的 QGP 就很难看。」

**否决权只能单向：物理可以否决美观；美观不能否决物理；美观可以否决「画法偏好」。**

- **第 1 层 · 硬物理**（唯一有否决权）—— 判据只有一条：**能不能在图上量出来 / 证伪**。
  写进 IR 的 `hard_physics:`，**每条必须给 `measure`**。
- **第 2 层 · 画法偏好**（降级为建议）—— 不涉及任何可量化关系的东西。写进
  `style_preferences:`，**可被更美观的画法替换**，替换后只要第 1 层不破就行。
- **第 3 层 · 美观 / 质感** —— 生图模型最擅长，**别去规定**。

三条操作规则：

1. **「以生图模型的图为准」有前提** —— 只在它不违反第 1 层时才以它为准。生图模型在"关系"上
   经常打架（同一个 `x` 标到两根不同的杆上、`b` 不落在核芯上、面内箭头比面外短），必须改。
2. **「能更美观就增加」有边界** —— 增加的只能是第 2 层的视觉元素，**不许顺手删骨架**。
3. **默认是"不变"，改动要举证**（第 1 层不更差 + 观感更好）。

反例（实测）：A 档到 C 档为了满足 `style.conventions` 的「单幅、不要插图框」，
把作者参考图里 `−b/2` / `b/2` 的碰撞几何插图整块删掉 —— 写 IR 的人把自己的口味
升级成了"物理要求"，而当时的闸门一条也拦不住。

完整规则、IR 例子与闸门见 `references/physics-vs-style.md`。

## 五条硬纪律

### 纪律 0：不要把版权受限的图打包发布

建立参考图库时，**先看许可**：

| 许可 | 能否再分发 |
|---|---|
| CC-BY | ✅ 可以，需署名 |
| CC-BY-NC / 版权保留 | ❌ 内部研究可用，**不要发布** |
| arXiv | 看具体论文的许可声明 |

*踩坑*：本仓库最初打包了 8 张参考图，其中 5 张来自
Springer Nature 综述和 Nature 非 OA 文章 —— 推到公开仓库前查证才发现，
已改为「只留 CC-BY + 其余只给出处」。


### 纪律 1：几何量必须【量】，禁止【看】

**数量、角度、比例、坐标** —— 这些必须写脚本扫像素得出，不许目测。

来源：盲测实测。我目测 T3-03 的径向线得出"48 条"，脚本一扫是 **40 条**。
AI 盲测时自己写了扫描脚本，数对了；我目测，数错了。

```python
# 例：数径向线条数
# 在半径 r 的圆上扫一圈，统计蓝色像素的簇数
```

**哪些必须量**：元素个数、圆/多边形边数、角度与夹角、缩放比例、
相对坐标、颜色值、线宽。
★ **最容易漏的一个：`panels.py` 里 `ELEMENTS` 的每个框。** 换一张位图，元素位置
全变；框沿用上一张的坐标 → IoU 全为 0 → 走兜底规则把元素**判给邻居**。实测：三个
箭头的框抄了上一张的 `y 405..463`（新图在 `y 351..400`），三个箭头全被判给相邻阶段，
`stage1-nucleus` 的包围盒被拉到 `x 62..1319` —— 图层面板直接没法用。**每张图都要用
连通域 / 颜色掩膜把框重量一遍**（可用 `--elmap` 出的元素划分自检图核对）。


**哪些可以看**：风格分类、物理角色、叠放顺序、视觉层次。

### 纪律 2：绘制顺序就是 z 序

后画的盖住先画的。画反了元素会**凭空消失且不报错**。
顺序：背景 → 外轮廓/后壳 → 前表面 → 表面上的线 → 前景物体。

### 纪律 3：风格指标是【诊断工具】，不是【优化目标】

`style_bench` 告诉你**往哪看**，不告诉你**调到多少**。
踩过的坑：按指标"整体降饱和+加深描边"，结果把不该压暗的平面也压暗，
**3 项指标反而恶化、视觉更差**。

正确流程：
```
量 → 判断 → ★把指标对应的像素可视化、找到具体原因★ → 只改那一处 → 复测 → 看图
```
**第 3 步是关键。** 直接从指标跳到调参数必然伤及无辜。

### 纪律 4：物理正确性无法自动验证

- 复现任务：有参考图当 ground truth，可对照检查
- 创作任务：**没有 ground truth，必须人看**

**不要说"自动达到 Nature 级"。** 能说的是：
"把偏离量化、让失败可见、验证修正是否收敛"，最终判定仍需人。

---

## 自动收敛循环（复现任务用）

复现一张图手工要 7 轮以上——那不叫"省时间"。用 `auto_converge.py` 自动化：

```bash
python3 scripts/auto_converge.py --ref 参考图.png \
    --script repro_T3-03_param.py --max-iter 24
```

**使用前必须先测敏感度**，别凭直觉写映射表：

```bash
# 每个参数取区间两端各渲一次，量各指标的响应幅度
# 幅度 >0.15 才算有效杠杆；<0.10 的指标要标为"无杠杆"
```

踩过的坑（都写在 `auto_converge.py` 的注释里）：
1. **映射表凭直觉写 → 5 条只对 1 条**。必须先测敏感度。
2. **sign 的语义是「修正方向」不是「相关方向」**。写反了会"指标越高越加"，南辕北辙还看不出来。
3. **没有回溯 → loss 单调恶化**。变差必须回退 + 步长减半。
4. **参数撞界会冻死循环**。撞界要跳到下一个可调指标。
5. **敏感度是在基准点测的**，其他参数移动后可能失效 → 循环会卡在某个指标上反复小幅试探。这是坐标下降的固有局限。

### 天花板由参数空间决定，不是由搜索算法决定

实测：`whitespace` 原本**所有参数对它的敏感度都 <0.10**，卡在 +34% 不动。
加了 `face_tone`（前表面亮度）后敏感度到 **0.57**，直接降到 −7%。

**指标调不动时，先怀疑参数空间不够，别怀疑算法。**

## 交付前自检

**机器可判**（AI 自己核对并给证据）：
- ☐ 元素清单逐条对上，无遗漏无多余
- ☐ 渲染无静默失败（渐变非纯黑、文字无豆腐块）
- ☐ 导出矢量；单面板 `get_images()==0`；复合图看 `get_xobjects()>0`
  （`check_delivery.py` 现在**阻断**：整页被位图覆盖、有效 dpi <300、位图之外无矢量轮廓）
- ☐ 文字可提取（不是被转成轮廓）
- ☐ 面板标号由拼版层加，面板内部不重复画

**人工判**：
- ☐ 物理表达准确
- ☐ 与参考图的结构/物理内容一致（A 类）
- ☐ 视觉达到可投稿水平

> 有目标图的 SVG，完成原尺寸保真、关键结构、4 倍和试编辑核查后再交付。以 spec 创作的新图按物理约束和图面回执封版。

---

## 按需参考（不要一次全读）

| 什么时候读 | 文件 |
|---|---|
| **判定任务 / 图型、写 IR、选后端、跑验证、走 A→B→C→D** | **`references/routing.md`** ★ |
| **新对话 / 新工作区：硬规则在哪、每条由哪个闸门执行** | **`references/hard_rules.md`** ★ |
| **把规则落到一个新目录（写 AGENTS.md + `tools/` 转发脚本）** | `scripts/init_workspace.py --dir <ws>` |
| **走路线 B、出草图 / 位图、位图→矢量七步** | **`references/generate-flow.md`** ★ |
| **元素级 spec、作者确认、矢量装配、Nature 规范和安全模式** | **`references/element-spec-pipeline.md`** ★ |
| 查完整脚本表 / 某个脚本干什么 | `references/scripts.md` |
| 写 IR 的字段细节 | `references/ir-spec.md` |
| **画 T3 示意图之前 / 图出来觉得"扁"** | **`references/3d-checklist.md`** ★ |
| 画 SVG、查图元、查技法 | `references/svg-cookbook.md` |
| 决定用哪个后端、为什么 | `references/tool-selection.md` |
| 风格量化、闭环修正 | `references/style-bench.md` |
| 遇到渲染异常 / 静默失败 | `references/gotchas.md` |
| **一张图要用多种工具** | `references/multi-tool.md` |
| **最终 SVG：对象拆解、补画遮挡、3D 光影、试编辑及示例** | **`references/direct-svg-redraw.md`** ★ |
| **双版交付：反混合、遮挡补全、独立纹理与拖动验收** | **`references/dual-svg.md`** ★ |
| **连续渐变 SVG：纯代码、渲染兼容与局部保真** | **`references/continuous-gradient-svg.md`** ★ |
| 临摹备用：amodal 补全、拾取层、光滑档 | `references/bitmap-to-vector.md` |
| 硬物理 vs 画法偏好的完整规则 | `references/physics-vs-style.md` |

## 资产

- `assets/t3-exemplars/` —— **17 张 CC BY 4.0 参考图**（逐张署名见 `NOTICE.md`）
- `assets/schematic-library/` —— **5.1 许可分级素材库**：20 张本地可分发图、43 条 metadata-only 记录、16 个主题的 5,245 篇 DOI 去重候选论文；先看 `README.md`
- `assets/element-library/` —— **181 个元素级 SVG 变体**：74 个文章来源素材均以可无限缩放的原生 `_edit.svg` 为默认，附可选平滑 `_texture.svg` 审计对照；107 个 `software` system-primitives；核子族 30 种，其中 16 种为文章来源
- `assets/spec-profiles/nature-2026.json` —— 尺寸、字体、线宽、色板、DPI 和安全模式口径
- `assets/demos/element-spec/` —— 元素级 IR → SVG/PDF/PNG 的完整可运行示例
- `assets/ir/` —— **三套** IR 标准答案（**不要提前给被测 AI 看**）

  - B1_T3-03 / B2_T3-05：手写，已按盲测验证结果修正
  - B3_T3-07：**盲测产出**（25 个元素，比手写版完整得多，含几何反解）

> **建立标准答案的方法**：不要自己手写就完事。
> 实测：手写版在辐条数（48 vs 实测 40）、黑圈内是否可见、
> 两幅是否相同等处都错了；盲测 AI 自己写扫描脚本，全对。
> **正确做法是——先手写一版，再让一个没见过它的 AI 独立提取，
> 逐条验证后合并。** 差异处往往就是手写版出错的地方。

- `assets/demos/jet_quenching/` —— **喷注淬火 线路③ 全流程**（IR / 简报 / 草图 / 位图 / 元素表 /
  交付 SVG+PDF / 对照图 + 实测数字），v2.7.2 —— 想照抄一个「机器闸口抓出几何写反」的完整算例看这里


## 脚本（索引；完整表见 `references/scripts.md`）

最常用的一条链：
`ir_to_genbrief.py` / `brief_lite.py` → `gen_figure.py` → `trim_border.py` → `check_sketch.py` → `sketch_to_vector.py` / `sketch_handoff.py` / `choice_gate.py` → `gate3d_rank.py` → `axis_gate.py` → 两版 SVG（几何/透明纹理）→ `check_direct_svg.py`（两版）+ `check_svg_pair.py`（试编辑）→ `check_delivery.py`

- 生成与闸门：`gen_figure.py`、`ref_guard.py`、`ladder_gate.py`、`ir_scope_gate.py`、`ir_layout_guard.py`、`keep_gate.py`、`element_list.py`、`choice_gate.py`、`check_sketch.py`、`gate3d_rank.py`、`axis_gate.py`、`check_3d_generic.py`、`check_delivery.py`、`preview.py`、`init_workspace.py`
- 素材库：`schematic_library.py`（统计 / 校验 / 语义词检索 / OpenAlex 候选发现 / Europe PMC CC BY 采集）
- 元素生产链：`article_element_harvester.py`、`publisher_figure_harvester.py`、`figure_element_candidates.py`、`build_element_library.py`、`element_library.py`、`spec_confirm.py`、`spec_compile.py`、`visual_review.py`、`nature_gate.py`
- 双版 SVG：`review_redraw.py`（参考图与两版交付）、`check_direct_svg.py`（单版结构）、`check_svg_pair.py`（对象与编辑诊断）。临摹备用：`raster_to_vector_semantic.py`、`trace_rebuild.py`、`svg_spline.py`、`shade_smooth.py`、`pick_layer.py`。
- 临摹备用的语义发布：`semantic_conflicts.py`、`semantic_competition.py`、`semantic_release.py`、`release_gate.py`、`edit_to_visual.py`。
- 诊断与返修：`check_render.py`、`compare_ref.py`、`style_bench.py`、`repair_brief.py`、`audit_composition.py`
- 其余（IR、拼版、复现、工具探测）见 `references/scripts.md`。
