---
name: hep-nature-figure
description: >-
  Produce publication-quality high-energy nuclear physics figures: 3D schematics with
  lighting, collision/QGP illustrations, multi-panel composites, and reproductions of
  existing journal figures. Use for 科研配图、论文示意图、高能核物理配图、Nature 级配图、
  碰撞示意图、QGP 示意图、复现论文图、手绘草图转配图、3D 示意图 with shading.
  Routes to the right backend per figure (SVG / matplotlib / Blender / image generation)
  instead of forcing one tool. Not for statistics-only work or interactive dashboards.
---

# HEP Nature Figure — Router

## 分工：谁画、谁约束、谁验收

**画图交给模型，本 skill 负责约束、验收、返修。**

| 环节 | 谁做 | 为什么 |
|---|---|---|
| **画** | **模型**（直接输出 SVG） | 模型有视觉先验，能做出代码拼不出的质感。实测：纯代码管线产出"干净的教科书插图"，达不到期刊观感；模型直接画明显更好 |
| **约束** | **IR + geometry_constraints** | 防"好看但物理错"。模型单干时最爱犯这个 |
| **验收** | **三道门禁** | 模型看不见自己的输出，这里能量（见下「三道门禁是谁」） |
| **拍板**（只一次） | **作者本人** | 闸口①之后、成品位图之前：机器只能排序，"哪张更像你要讲的物理"只有你知道。草图是全链最便宜的返工点（`sketch_handoff.py` / `sketch_ingest.py`）。**v3.1 起这条有闸门了**：`make_picker.py` 交出去、`choice_gate.py` 收回执 —— 没有**你本人**的回执就不许出成品位图 |
| **返修** | **`repair_brief.py` → 模型改** | 光说"文字重叠"模型只能猜；返修单给**归一化坐标 + 具体错开量** |

**结论：不要试图用代码把图"画好看"——那条路性价比极低。**
代码该干的是**把模型的输出卡对**。

### 架构（2026-09-26 定稿）

**三条职责，各管一段：**

```
IR 管物理  ｜  生图管风格  ｜  矢量那一步管矢量化
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
④ 位图 → 矢量。**两个终点，首选重画、备用混合临摹**（见下）
        ★ v4.0 固定三步：① 客户选定/确认的位图 ② 逐像素**临摹**（raster_to_vector_semantic.py，
        带 <g data-element> 语义图层）③ **从临摹层重建**（trace_rebuild.py）——
        几何一律从临摹层的掩膜取，**别再走颜色阈值**（v37 教训：包围盒把真 bbox 切平、
        「板下淡出」描成卷曲细带；改从 data-element 取几何后 MAE 2.49 / 5.28 → 1.95）
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

### ★ ④ 的两个终点：**重画（首选）** vs **混合临摹（备用）**

| | **重画（首选）** | **混合临摹（备用）** |
|---|---|---|
| 做法 | 看懂位图里**每个部分是什么**，逐个重画成 SVG；形体带真 `<gradient>`，保留色彩与阴影 | 逐像素描摹 + 文字擦掉重写真 `<text>` |
| 分层 | 按**结构/物理**（`nucleus-A` / `photon-A` / `vertex`…） | 同上，**不按颜色分层** |
| 可编辑性 | 最好（曲线是干净的形体） | 次之（路径碎，但是全矢量） |
| 忠实度 | 取决于重画水平 | **最高**（同分辨率下 MAE 可到 0.2–0.5） |
| 什么时候用 | 默认 | 重画不划算 / 要求"和位图一模一样"时 |

**两条都要求**：文字是真 `<text>`、图层按物理元素分（颜色只是 `<path>` 的属性）。

> ⚠️ 老版本这里只写了"③ 必须是混合临摹"，且 `ir_to_genbrief` 的另一处又说
> "看懂后**重画**、**不要照抄位图的几何**" —— 两句互相打架，AI 读到哪句走哪句。
> 2026-09-26 统一：**位图已经过闸口，就该照它画**；对不上 = 位图错了，回去重出。

### ★ 但纯像素描摹一定不行：文字会全变成轮廓（实测依据）

| | 纯像素描摹 | **擦掉重写（必须）** |
|---|---|---|
| 图形忠实度 | 高 | **高**（同样的像素描摹） |
| 文字 | **0 个 `<text>`** —— 全是轮廓，`check_delivery` 判不合规 | **真 `<text>`，可编辑** |

实测：同一张图，纯描摹 `<text>` 元素 **0 个**；给文字清单后 **3 个**。

```bash
# 模型看图后写出文字清单，再做混合临摹
python3 scripts/raster_to_vector.py fig.png -o fig.svg --text-spec texts.yaml
```

```yaml
texts:
  - {content: "escaping jet", x: 0.62, y: 0.10, size: 13, anchor: start}
```

### ★ 临摹的两种粒度：逐像素 vs 先理解

备用方案有两个实现，**按图的类型选**：

| | `raster_to_vector.py`（逐像素描摹） | `raster_to_vector_semantic.py`（先理解再临摹） |
|---|---|---|
| 文字 | 模型写 `--text-spec` → 擦掉重写 | **OCR 词表 + 逐词对齐**（字号/字距/位置自动估） |
| 图层 | `--groups`（模型给代表点） | `panels.py` 的 **ELEMENTS 表** → 面板/元素两层树（**颜色只是 `<path>` 的属性**） |
| 忠实度 | 高 | 非文字区 MAE **0.227**、>32 色阶像素 **0.00%** |
| 误差验收 | 要自己量 | **自带** MAE / PSNR / `--check` 回渲染 |
| 依赖 | cv2 / skimage | numpy / scipy / Pillow / cairosvg / cairocffi / fontTools |
| 适合 | 通用 | 色块 + 硬边的渲染示意图 |

**要「人能直接点选某个物理元素改它」→ 用 semantic 那条** —— 它出的是
panel → element 的**命名图层树**，`--legend` 给可读清单，
`--elmap` 出元素划分自检图（人眼确认名字有没有贴对物体）。

代价：**要人写两张每图各不相同的表** —— `words.txt`（OCR 词表）和
`panels.py`（面板框 + 物理元素框 + 颜色条件）。自动切分只定"形状"，
**"这块叫什么物理名字"必然要人来写**。这是它比纯描摹贵、也比纯描摹准的地方。

```bash
# ① 出词表（Windows.Media.Ocr，自动 2× 放大）
powershell -File scripts/raster_vector/ocr_words.ps1 -Image fig.png -Out words.txt
# ② 照 scripts/raster_vector/panels.py 改出这张图的 CELLS / ELEMENTS / SPLIT
# ③ 组装 + 自检
python3 scripts/raster_to_vector_semantic.py fig.png -o fig.svg --words words.txt \
        --panels my_panels.py --legend fig_layers.md --elmap fig_el.png --check
```

> ⚠️ 两条路都**做不出真渐变网格**。原图的连续渐变在矢量里只能是色阶台阶
> （调小 `--R` 变细，代价是路径数/体积）或真 `<gradient>`（要求图能拆成图元）。

★ **临摹稿过两道门禁时会踩两个假阳性（v2.5 已修，但你得知道它们存在）：** 位图临摹稿的
页面就是图本身，白底矩形总是顶到边 → `audit_composition` 会报「出界」（白上白被裁
不可见，现已不计）；渐变填充会被 MuPDF 当成嵌入位图 →
`check_delivery` 会报「72 dpi 位图」（现已改成扫 xref 认真 `/Subtype /Image`）。
完整算例（含实测数字）：`assets/demos/jet_quenching/`（**线路③ 全流程 + 路径不对称闸口**，v2.7.2）、`assets/demos/upc_semantic/`、`assets/demos/spin_semantic/`、`assets/demos/evo_semantic/`（质感）与 `assets/demos/evo3d_semantic/`（**3D 风格档**：同一份 IR，`--style-mode render3d`，火球从纯色圆盘变成内亮外暗的 3D 渐变）。

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

|  | **路线 1：直接代码出图** | **路线 2：生图草图 → 代码完善** | **路线 3：生图草图 → 成品位图 → 临摹** |
|---|---|---|---|
| 中间产物 | 无 | 草图 PNG + **草图 SVG** | 草图 PNG + **草图 SVG** + 成品位图 |
| 谁保证物理 | 代码（`geometry_constraints` 直接可算） | 闸口① | 闸口① + 闸口② |
| 观感 | 教科书插画 | 中 | **最好** |
| 成本 | 低 | 中 | 高 |

- **默认 = 路线 3**（生图草图 → 成品位图 → 重画/临摹成矢量）
- **要批量扫参数 / 要代码直渲** → 路线 1（`scene_render.py` IR 直渲，或 `svg_lib` 手写）
- **要人插手改草图** → 路线 2（草图矢量化后交给人在 Illustrator 里改，再代码完善）

> 路线 2 和 3 的**前两段完全一样**（IR → 简报 → 生图 → 矢量化草图 → 闸口①）。
> 区别只在第三段：2 是代码/模型接着完善草图，3 是再多跑一张成品位图。
> **默认走 3**，因为"质感"这件事生图模型比代码强得多；只有要代码直渲时才退回 1。

### ★ 生图那一步的三条硬规矩

1. **API key 由使用者自己提供** —— `gen_figure.py` 读环境变量 `DASHSCOPE_API_KEY`，
   脚本里**不存任何 key**。别人装了 skill 就用他自己的 key（没 key 也能 `--dry-run` 自检）。
2. **必须给风格参考图**（`--ref`，可多张）—— 参考图 = Nature **风格书**。
   只给文字简报，出来的图一定很"通用"。`_T3精选` 这类本地图直接传就行；
   要公开发布时用 `assets/t3-exemplars/` 里那 17 张 CC BY 4.0 的（见纪律 0 与 `NOTICE.md`）。
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

## 路由协议

### 0. 判定任务类型

| 类型 | 输入 | 判据 |
|---|---|---|
| **A 复现** | 参考图 | 要求与已有图结构一致 |
| **B 创作** | 手绘草图 / 文字描述 | 没有现成目标图 |
| **C 数据图** | 数据 + 坐标轴需求 | 有数值要表达 |
| **D 复合** | 上述的组合 | 一张图里既有示意又有数据 |

**A/B 走本 skill 主干；C 用 matplotlib，本 skill 只施加样式约束；D 走拼版。**

### 1. 判定图型

| 层级 | 特征 | 主后端 |
|---|---|---|
| **T1** | 2D 定量面板（谱、曲线、误差带） | matplotlib |
| **T2** | 3D 曲面（rainbow colormap + 网格） | matplotlib（**不是 Mathematica**，实测其 3D 会栅格化） |
| **T3** | 3D 示意图 + 光影（碰撞几何、QGP、探测器） | **SVG 手绘** ← 本 skill 主战场 |

### 2. 写 IR（**强制，不可跳过**）

读 `references/ir-spec.md`，按格式产出 IR。

**三个必填项，缺一不可**：
- `figure.physics_claim` —— 一句话说明这张图在物理上表达什么
- 每个元素的 `physics_role` —— 它在物理上代表什么（**不能写"装饰"**）
- `style.classification` + `evidence` —— 风格归类**并给判据**

**画序 = z 序**，从后往前写。SVG 没有深度，后画的盖住先画的。

**物理上必须成立的空间关系，要写成 `geometry_constraints`（可计算的数值）。**
只用"偏右上""靠近表面"这类词描述位置 → 实现时会画出"看着对但物理错"的图。
*实测*：喷注淬火图第一版的逃逸喷注穿过了大半个介质，因为 IR 只写了"顶点偏右上"。

★ **分两节写，别都写成待答问题**（v2.6.2 加）：

```yaml
geometry_constraints:
  约束:            # 机器判不了 → check_sketch 逐条变成**待你回答**的问题
    - 名: 两核相向运动
      量: "dot(A 的速度方向, B 的速度方向)"
      要求: "< 0"
  机器:            # 机器能判 → check_sketch **自己量**，不用人回答
    - 名: 两核沿束流方向压扁（Lorentz 收缩）
      量: "每个核的彩色像素块 bbox 的高/宽"
      束流方向: horizontal       # 从 composition.视角 抄
      阈值: 1.25                 # ≥ 才算"确实压扁了"；≈1 的圆是没画收缩
      要求: "> 1.25"
```

*实测（2026-09-26）*：`约束` 那四条全是**核与核之间**的关系，
**没有一条管单个形体的朝向** —— 于是两核的 Lorentz 收缩方向画反了
（沿水平束流运动却画成横扁）的位图，"四条全过"。形状朝向这类**能量出来的**
东西，必须写进 `机器` 让闸口去量，不要指望人每次都想起来看。

★ **几何必须自洽：写完先用机器闸口量一遍，再交给模型**（v2.7.2）：

「谁穿过介质更长」这种话，模型只会**照抄你给的端点** —— 而**顶点偏哪边，
哪边出射路径就短**。实测（喷注淬火）：IR 写「朝左下路径长」，但按 IR 自己给的端点算，
顶点偏左下 ⇒ 朝左下 **0.09 W** 就出射、朝右上 **0.30 W** —— **恰好反了**；
3/3 草图一致照抄。凡是「能量损失 ∝ 路径长度」这类**唯一结论**，必须写进 `机器`：

```yaml
geometry_constraints:
  机器:
    - 名: 喷注路径不对称（弦长比）   # 名里含「路径 / 弦长」→ 自动走这条闸口
      长路径色: gray                # gray = 低饱和那一侧（被淬火）；画反了报错
      阈值: 1.8                     # 长 / 短 ≥ 它才算成立
```

`check_sketch.py` 会自己：介质 → 最大高饱和色块 → **凸包** → 拟合椭圆；
两条锥轴 → 蓝锥（高饱和）/ 灰锥（低饱和）各自**最大连通域的 PCA 主轴**；
顶点 → 蓝锥沿自身轴向的**极小投影点**（锥尖）；弦长 → 顶点沿每条轴到椭圆的**解析解**。
★ **量测失效 ≠ 通过**：找不到介质 / 喷注时只打 ⚠️，**不算通过**。


> 同理：IR 的 `style.conventions`（"核必须画成高瘦椭圆"这类**形态约定**）
> 一定要落到简报上 —— v2.6.2 之前 `ir_to_genbrief.py` 把它整个丢掉了，
> 写在 IR 里等于没写。

> 跳过 IR 直接画 = "AI 随机画一张好看的图"，复现不了，物理也没保证。

### ★ 编译器不许丢字段：IR → 简报的「无损体检」（v2.6.10）

模型**永远看不到 IR** —— 它只收到 `ir_to_genbrief.py` 编译出来的简报。
所以**编译器丢掉的字段，等于你从来没写过**。这件事已经踩过三次：

| 版本 | 被丢 / 被写死的字段 | 后果 |
|---|---|---|
| v2.6.4 | `style.conventions` | IR 写「纵向压扁」，4/4 把两核画成横扁 |
| v2.6.7 | `style.palette` + 风格档写死成扁平 | IR 要 3D，简报反过来禁 3D → 火球=纯色圆盘 |
| v2.6.9 | `elements[].material` | IR 写「哑光 / 三层壳 / 组元颗粒」一个字没进 → 火球=光滑糖球 |
| **v2.6.10** | `composition.view`、`geometry_constraints.约束[].为什么`、`composition.元素布局 / 分区 / 叠放关系`、sketch 档的 `style.palette` | 视角、判据理由、锚点 / 相对尺寸 / 备注全丢 |

**改 IR 格式 / 改简报模板之后，先跑一遍体检**：

```bash
python3 scripts/ir_brief_audit.py            # sketch + render 两档
python3 scripts/ir_brief_audit.py --verbose  # 每行都打理由
```

它用**哨兵法**（给 IR 的每个叶子字段塞一个唯一串，编译成简报后查在不在），
**不靠读代码猜**。字段分四类：

- `carry` —— 两档都必须到。
- `carry-render` —— 只要求 render 档（sketch 刻意不带：那一步要扁平，带 3D 风格定位会打架）。
- `context` —— 到了，但简报里明说「仅供理解，不要画进图」。
- `skip` —— 刻意不带：`figure.title` / `execution.*` / `assertions.*` 这类给工具和人用的，
  画上去就是错。

有「必须到达」的字段没到 → 退出码 1（已挂进回归：`genbrief_lossless_render`）。

> 哨兵要**包一层分隔符**（`@@S_z@@`）—— 否则 `S_z` 是 `S_zone` 的前缀，
> 会被纯子串匹配误判成「z 到了」。

### 3. 选后端（按图选工具，不预设）

**先跑工具探测**——缺工具不是放弃的理由，是**告诉用户装什么**：

```bash
python3 scripts/check_tools.py            # 全量探测 + 装机指引
python3 scripts/check_tools.py --for 示意图  # 只看某类图
```

**两条独立轴共同决定后端**：

```
内容轴：示意图 / 定量图 / 复合
风格轴：矢量插画 / 半写实 / 照片级 / 手绘 / 扁平 / 数据可视化
```

#### 工具路由表（依据 Nature 官方美术指南 + 开源替代调研）

| 图型 | 首选 | 备选 | 说明 |
|---|---|---|---|
| 数据图（谱/曲线/误差带） | `matplotlib` | `ROOT` / Mathematica | 三者都真矢量 |
| 3D 曲面 | `matplotlib` | Asymptote | **不要用 Mathematica**——实测其 3D 会栅格化 |
| 示意图（矢量插画） | `svg_lib` 生成 | **Inkscape** 精修 | Inkscape = Illustrator 开源替代，**有 CLI 可被调用** |
| 需要路径布尔/复杂描边 | **Inkscape** | Illustrator | Inkscape 可命令行调用；Illustrator 只能人工 |
| 真 3D（几何即内容） | **Blender** | — | 探测器几何、CAD |
| 数学公式密集 | **Ipe** / **TikZ** | Asymptote | LaTeX 原生，公式直接嵌入 |
| 复合图拼版 | `assemble_panels.py` | Inkscape | 保持矢量 |
| 最终交付 | **可编辑矢量** | — | Nature **硬性要求**，便于美术团队重排版 |

#### Nature 官方要求（实测查证，不是猜的）

- 线稿/图表/示意图：**首选 Adobe Illustrator (.ai)、EPS、PDF**，须**从生成软件直接导出**
- Nature 提供 **Illustrator 模板**
- 典型流程：各面板在各自软件做 → **在矢量编辑器里合成**
- 照片/复杂插画：Photoshop 分层 PSD，或 ≥300 dpi 位图
- **必须可编辑矢量**——美术团队要重排版、换字体、调样式
- 字体：无衬线（Helvetica/Arial 优先），正文标注 5–7 pt

> **推论**：Illustrator 的核心作用不是"画"，是**合成 + 可编辑叠加层**。
> 所以 skill 的交付目标应该是「**结构正确 + 分层干净 + 可直接打开精修的矢量**」，
> 而不是「一步到位的成品」。

#### 交付格式：SVG 和 PDF/EPS **都要出**

| 格式 | 用途 | 为什么 |
|---|---|---|
| **SVG** | **工作稿**（给人精修） | `<g inkscape:label>` 保留**图层结构**，Inkscape/Illustrator 里每个部件可单独选中。文本格式，可 diff |
| **PDF** | **交付稿**（投稿） | Nature 官方首选，字体内嵌、打印就绪。**但没有图层概念**，人精修时会丢层级 |
| **EPS** | 备份交付 | Nature 也接受。`pdftops -eps` 生成 |

⚠️ **不要只出 PDF**（人精修没图层），**也不要只出 SVG**（不是 Nature 列出的格式）。

> Nature 官方原话：*"For line art, graphs, charts and schematics we prefer
> Adobe Illustrator (AI), Encapsulated PostScript (EPS), or PDF"* —— **没提 SVG**。
> SVG 是我们的**工作格式**，不是投稿格式。

交付前跑：
```bash
python3 scripts/check_delivery.py fig.pdf fig.eps
```
检查：0 嵌入位图？文字可提取？字号 ≥5pt？

**大 SVG 怎么出 PDF（实测）**：不要用 `cairosvg` ——
本算例 `upc_q16.svg`（2.67 MB / 5396 条 `<path>`）走
`cairosvg.svg2pdf` 直接 OOM。用浏览器打印（保矢量、不栅格化）：

```bash
# 包一层 HTML，@page 尺寸 = 成品物理尺寸（mm 换算成 pt）
#   @page { size: 518.7402pt 289.2974pt; margin: 0 }    # 183 × 102 mm 双栏
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" \
    --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf=fig.pdf file:///.../fig.wrap.html
```

`check_delivery.py` 的位图判据正是按这条路径校准的
（渐变会被 MuPDF 误报成嵌入位图，它按 xref 判别）。

#### 风格档案与阻断门禁（不写死风格）

**风格不写死**——目标可以是任意一张参考图，也可以是**类级风格档案**。

```bash
# 从目标图提取档案（存【数字】，不存图 —— 版权受限的图也能用）
python3 scripts/style_profile.py extract 参考图.png -o prof.json

# 从多张同风格的图提取【类级】档案（更稳）
python3 scripts/style_profile.py extract refs/*.png -o t3.json --name T3

# 阻断式门禁：判"离目标风格多远"
python3 scripts/delivery_gate.py fig.png --profile t3.json --pdf fig.pdf
python3 scripts/delivery_gate.py fig.png --target 参考图.png --ir ir/B1.yaml
```

**门禁的判据不是固定的**，而是**按类内离散度分级**（实测得出的原则）：

| 指标在类内 | 例（T3, n=22） | 门禁角色 |
|---|---|---|
| **一致**（相对IQR<0.15） | 留白 0.10 | **阻断** —— 超出类内区间就不许交付 |
| 分散（IQR 0.2–0.5） | 边密度 0.24 / 暗像素 0.45 | **仅提醒** |

> **原则：指标在类内一致，才配当阻断门。** 拿一个本身就在飘的指标去卡人，只会误导。

**判的是"在不在类内区间"，不是"在不在中位数上"**——因为图与图本来就不一样。

为什么存数字不存图：
1. 版权受限的论文配图不能随仓库分发，但**测量结果是事实**，可以
2. 对 skill 更**有用**——它需要知道"目标图的线宽/配色/密度是多少"，不需要那张图

内置档案见 `assets/style-profiles.json`（从本地参考库聚合）。

**★ 类要拆够细，否则档案会互相打架**（实测）：

T3 类的 22 张图，用一个档案卡不住 —— 聚类后发现里面是两种风格：

| 子类 | n | 饱和 | 边密度 | 暗像素 |
|---|---|---|---|---|
| `T3-schematic (illustration)` | 12 | 0.330 | 0.097 | 0.033 |
| `T3-schematic (lineart)` | 10 | 0.254 | 0.125 | 0.049 |

同一张 UPC 图：
- 撞**合并的** T3 档案 → 🚫 阻断（加权偏离 1.130）
- 撞**插画型**子类档案 → ✅ 通过（加权偏离 **0.640**）

**图没错，是目标错了。** 类分得太粗，中位数就成了一个谁都不像的"平均图"。

**实践**：建档案时先聚类看子类，再决定建几套档案。

#### 缺工具怎么办

**不要降级、不要糊弄。** 按顺序：

1. 跑 `check_tools.py` 确认缺什么
2. **告诉用户安装命令**（脚本已给出）
3. 装好后**调用它**，而不是用别的工具凑合

> 这条是硬纪律：**缺工具 = 去装，不是绕开。**
> 用户可能只是没装，不是不能用。

### 4. 执行

- **SVG**：`scripts/svg_lib.py` 提供图元（火球/圆柱/核子/壳/坐标轴…）
- **matplotlib**：`size_steps`、`pdf.fonttype=42`（文字可编辑）
- **公式 / 数学排版**：**TikZ**（`pdflatex`）。分式、上下标、贝塞尔函数——
  SVG 手写极痛苦且排版差。详见 `references/multi-tool.md`
- **拼版**：`scripts/assemble_panels.py`（PyMuPDF，保矢量）

> **一张图通常要多个工具。** 例：碰撞几何用 svg_lib、公式用 TikZ、
> 合成用 PyMuPDF——各部分交给各自最擅长的，在拼版层汇合。

### 5. 验证（**不可跳过**）

按顺序跑：

```bash
# 渲染静默失败检测（渐变失效/字体丢失都不报错，靠它抓）
python3 scripts/check_render.py fig.png --probe 0.5,0.10 --probe 0.3,0.7

# 与参考图并排对比（★ 所有任务必做，作者 2026-09-28 定）
#   为什么升成必做：交付门禁的可信指标里**没有**能区分「扁平」与「3D 明暗」的量
#   （能反映渲染方式的 color_richness / gradient_ratio 被标为不可信），
#   实测一张扁平示意图可以五道门禁全绿。机器判不了"像不像参考图的渲染方式"，
#   就只能让**人 5 秒内能判**。这条不许省。
python3 scripts/compare_ref.py 参考.png fig.png -o cmp.png

# 风格偏离量化（A 类任务必做）
python3 scripts/style_bench.py compare 参考.png fig.png
```

**然后跑返修单，把问题变成可执行的指令：**

```bash
# 门禁报告 → 给模型的返修单（归一化坐标 + 具体改法）
python3 scripts/repair_brief.py fig.svg --profile assets/style-profiles.json \
    --class "T3-schematic (illustration)"
```

**这个脚本是"模型画、skill 验收"这条分工的关键一环。**
门禁输出原来只给人看（"文字重叠: A × B"），模型拿到只能猜往哪挪。
返修单给的是：**哪一处、归一化坐标是多少、建议错开多少 pt、哪种改法**。

它比门禁多查一项：**行间过近**（门禁只管重叠，不管"快贴上"）。
实测踩到：收敛结果里两行文字只隔 0.9pt，视觉上已经贴住，门禁判 ✅。
返修单会区分"行内正常词距"和"行间过近"——前者不报，后者给具体下移量。

**然后必须人看图。** 见下面的纪律。

**几何量的复核**：IR 里凡是写了数量的（如"径向线 40 条"），
实现后都要写脚本从成图上量一遍，确认与 IR 一致。别靠看。

---

### ★★ 入口与责任分界（v4.5，2026-10-06 实测）

作者原话：「a 档是一句话加参考图，构图参考是可选项，看用户提不提供，
而且无论用户提供什么，3d 感是首要」。「草图不用这么强调 IR 正确，主要位图要正确」。
「草图不是完全不管物理啊，基本的三轴物理这样类似的要管」。

#### 1 入口固定 A 档：一句话 + 一张风格参考图

| 档 | 简报 | 字数（实测） | 实测结果 |
|---|---|---|---|
| A | 一句话 + `--ref` 风格图 | 31 | 4/4 复刻参考图或画成深色海报；与参考图相似度 **0.36** |
| B | A + 面板序列 + **输出硬约束**（标签白名单、不许标题/图例/说明文字） | 137 | 4/4 干净白底三面板；相似度 **≤0.043** |
| C | B + 物理增量（只补上一轮真画错的） | 574 | 物理到位；相似度 **≤0.015** |

- **构图参考（`--content-ref`）是可选项**：作者/客户给了手绘稿就用，不给就不传 ——
  没有它时构图完全由简报决定，这是 A 档的正常形态，不是缺陷。
- **B 档那两行「输出硬约束」才是拐点**：提示词只多 106 字符，相似度从 0.36 掉到 0.03，
  海报 / 图例 / 标题全部消失。A 档单独用不可行（它画的是参考图，不是你的物理）。
- 实测记录：`fig_spin/gen/pc/EXPERIMENT_prompt_length.md`、`collective_flow/gen/v40/EXPERIMENT_ABC.md`。


#### 1.1 阶梯是**机械闸门**，不是文档约定（v4.6）

作者原话：「你要确保后续别的用户使用都是严格按照 ABC 档来的啊」。
写进文档**拦不住** —— 实测一个会话连出 4 轮草图，简报从 4148 字符涨到 6437 字符，
**A 档一次都没跑过**，直接拿累计规格书起手。所以做成闸门 `scripts/ladder_gate.py`，
并挂进 `ref_guard.py`：**出图前自动查，不合规就不许调生图接口**（钱花在构图上之前先拦住）。

```bash
python scripts/ladder_gate.py --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md --ref <风格图>  # 查
python scripts/ladder_gate.py --record --outdir <fig>/gen/B --brief <fig>/gen/B_brief.md        # 成功后退图后登记
```

硬判据：`L1` 顺序 A→B→C 不许跳档；`L2` A 档 ≤ 80 字符 + 必须有风格图，**A 档产物不许进交付链**；
`L3` B 档的**目标**是①面板序列 ②输出硬约束 ③**反抄写**（「不要照抄参考图的内容」必须显式写）——
这三样**允许分几步慢慢加**（见 `L8`），B 档一次没写全只出**软警**；
但 `L3b` 会在 **render 档**核对：出成品位图之前，累积草图简报里这三样必须齐全，缺一即硬伤。
`L4` 每轮 C 只许带「上一轮错在哪 → 改成什么」那一节（≤ 3000 字符）；`L5` `ref_sim ≥ 0.60` 判照抄；
`L6` render 前必须有 A/B/C 三段；`L7` **风格参考图必须贯穿整条阶梯** —— B/C 档的 `--ref` 与 A 档不一致就判硬伤；
`L8` **慢慢增加提示词**（作者 2026-10-07：「你这B档提示词一下子加太多提示词导致图片一下就很难看了」）——
草图档每上一档，简报相对上一档**最多 +250 字符**（render 档豁免）。账本落在 `<gen-dir>/ladder.json`。
`--waive "理由"` / `ref_guard --ladder-waive "理由"` 可放行，理由必须照抄进交付说明。

★ **B/C 是 A 的续，不是另起一张**（作者 2026-10-07：「BC档和A档完全不一样啊，BC档是辅助A档物理错误的」）：同一张风格图贯穿 A→B→C，B 只补面板序列 + 输出硬约束，
C 只补上一轮真画错的物理。中途换风格图（实测 v42：A 用 `T3-02`、B/C 换成 `T3-07`）就成了一条假的阶梯 —— 现已由 `L7` 拦住。
实测（集体流）：A 档 31 字符 + 一张风格图 → 4/4 **复刻参考图或渲染成海报**
（v43 用 `T3-07`：4 张全部复刻黑底 `T3-07` 的介子极化面板 / Reaction Plane 网格 / Nuclear Fragments，
其中 2 张还画出中文大标题、图例框、自造数值 v2=0.05–0.15）；
★ **v43 的错法**：A 档 31 字符**一步跳到** B 档 767 字符（**违反 `L8`**），出图观感与 A 档完全不是一张
—— 正确做法是**每档只加一条新约束**，按「反抄写 → 面板序列 → 输出硬约束 → 标签白名单」的顺序
逐档 +≤250 字符；每档出图后只把**上一档真画错的物理**写进下一档，而且**只写「要画成什么」，
不写负面列举** —— 实测负面提示词无效：写「不是 8 字、不是花生」那三张反而真画成 8 字和花生，
改成正面描述（「一个水平椭圆，中心在极点，长轴≈1.8×短轴」）后 4/4 一次过。
★ **已知限制：`ref_sim` 测不到「黑底内容复刻」** —— v43 的 A 档把 `T3-07` 整版搬走，
`ref_sim` 反而是 **−0.21 ~ −0.59**（参考图白底、成图黑底，指标被全局色调带偏）。
所以 `L5` 只能当参考，真判「有没有照抄内容」要看**图上有没有参考图独有的文字/装置名**。
#### 2 3D 感是首要判据

挑图、改稿、交付都以「像不像有体积有明暗的 3D 渲染」为第一取舍。
批量入口 `scripts/gate3d_rank.py`（见下方脚本表）。
★ 排序用 `grad_frac - edge_frac - max(limb,0)`（三个量都不依赖版式）；
`offcentre` 只当读数 —— 它对板面没意义，实测会把带大渐变的 A 档海报排到干净图前面。
★ 已知过杀：`3D1`「浅灰面 >= 3% 画布」按「有明显板面」标定，没大板面的图会被集体误杀。

#### 3 责任分界：草图管「基础物理」，位图管「IR 齐全度」

- **草图阶段必须管、答「否」就重出**：`check_sketch.py` 要你逐条回答的那几条基础物理 ——
  三轴与轴杆一一对应 / 同一轴名只出现一次 / 轴名不悬空；方向关系（L ⊥ 反应平面、
  自旋沿 L 不沿运动方向、b 是横向错开、面内 vs 面外的相对大小）；不编造数值与公式。
  这几条错了构图再好看也不往下走 —— 它们会原样传进位图。
  ★ 这几条**不用靠人记**：草图位图直接过一遍三轴闸门（**只给 `--png`**，走无 OCR 字形识别）——
  ```bash
  python scripts/axis_gate.py --png <草图_clean.png> --ir <IR> --json <报告.json>
  # 或者挂进出图后那一段：python scripts/ref_guard.py --post --axis-png <草图_clean.png> --ir <IR>
  ```
  `X1`（IR 必须声明坐标约定）/ `X2`（三个互不相同的轴名、且 == 约定）/ `X5`（不许第四个轴名）
  是**硬判据**；`X3b/X4`（轴杆几何）在只给 `--png` 时**自动降级为读数 + 软警**
  （草图上的轴杆检测不稳，误杀不起 —— 矢量交付给 `--svg` 时这两条仍是硬判据）。
  实测（2026-10-06）：v40 的 4 张 C 档草图 —— `s1121` / `s1123` / `s1124` PASS、
  `sketch_s1122` FAIL（第三根轴标成 `beam`，没有 `x`）；fig_spin 里 `s1002` FAIL（缺 x / y 标注），
  `s1001` / `s1003` / `s1004` 与 `s971`–`s975` PASS。
  ★ 这一条**实测踩过一次误杀**：`sketch_s1121` 一开始被判「缺 x」，人眼看图 x 是在的 ——
  x 标签紧挨着箭头与 `beam` 被并成一个「词」，词级模板匹配失败就被丢掉了。
  现在 `png_labels()` 在**词级判不出来时按单个连通域再试一次**（`min_score + 0.08` 防误报），
  x 找回后 s1121 通过。
  ★ 图**有意不画轴字母**（只标 `beam`）时用 `--allow-missing-axis` 把 X2 的缺轴名降级为软警，
  理由必须写进交付说明 —— 不加这个开关时缺轴名就是硬伤。
- **★ 草图的产物是两份，别只交位图**（v4.5 重申，原本就在第 3 步里）：① 位图
  `gen/sketch_sN_clean.png`（过闸门、排序用）；② **可编辑矢量草图** `gen/sketch_sN.svg` ——
  `scripts/sketch_to_vector.py <clean.png> -o <stem>.svg`，每个连通域一个 `part-NN` 子层，
  默认 `--q 16`（量化到 ~2000 条路径才"给人改"得动；`--q 0` 忠实但碎成数万条）。
  交接时用 `scripts/sketch_handoff.py gen/sketch_s*_clean.png --ir <IR> --outdir handoff`，
  它一起给 `handoff/candidates.md` + `handoff/cand_NN.svg`（可编辑）+ 预览图；
  作者改完用 `scripts/sketch_ingest.py <改过的.svg> --ir <IR> -o gen/` 灌回、重过闸口①。
  ★ **A/B/C 阶梯不替代这一步** —— 阶梯只决定"简报写多长"，草图仍然是"位图 + 矢量"两份产物；
  只交位图 = 作者改不动，等于把最便宜的返工点丢了。
- **草图阶段不管、压到位图**：IR 的元素齐全度（缺板面 / 缺公式 / 缺细箭头 / 缺尺寸线）、
  面板形状的精细度、配色与质感。`3D1/3D2`（板面 / 接触阴影）在草图阶段只作读数。
- 一句话：**草图管「对不对」，不管「全不全、精不精」**。

#### 4 位图精修：简报 = IR 全量 + 上一版错误清单

实测（`collective_flow/gen/v40/render_test/EXPERIMENT_render_fix.md`）：只要简报里逐条写出
「上一版错在哪 → 要改成什么」，位图**确实会把草图里的物理错改对**（形状、配色、
补回草图缺的轴、补上 IR 要求而草图没有的公式），**但它会自己加词**
（冒出 `overlap` / `spectators` 这类 IR 里没有的标签）。

所以位图这一步固定这么走：

```bash
# 1) 简报 = IR 编译稿 + 手写错误清单（两个文件拼起来）
python scripts/ir_to_genbrief.py <IR> --stage render --style-mode render3d -o brief_render.md
#    再往文件后面追加一节：
#    ==== 构图依据（草图）已知画错的地方 —— 这一步必须改对，不许照拄 ====
#    1. <错在哪> -> <改成什么>（一条一行，只写真画错的）
#    2. 图上只许出现这些标签：…（一个都不许多）   <- 必须带这条
# 2) 出图：content-ref 原样送（auto -> full，v4.7 起不降级 —— 位图是对草图的润色）
python scripts/gen_figure.py --brief brief_render_fix.md --stage render \
       --ref <风格书> --content-ref <选中草图> --seeds a,b,c --size W*H --outdir gen/
# 3) 复检（缺一不可）
python scripts/gate3d_rank.py gen/render_s*.png --ir <IR> --require-all
python scripts/axis_gate.py --svg <交付.svg> --png <位图.png> --ir <IR>
#    再**逐条对照错误清单**：没改对的 + 新冒出来的标签 -> 写成下一轮清单，只补没修好的
```

★ 正式交付时 render 档仍要客户回执（`choice_gate.py`）；做实验可以 `--no-choice-check`，
  但必须在记录里写明「这是实验、不是交付」。
★ 这条路 = **路线 3**（草图 → 成品位图 → 矢量）。**要人改草图就走路线 2**：草图矢量化后
  交人在 Illustrator / Inkscape 里改 → `sketch_ingest.py` 灌回、重过闸口① → 再出位图。
  两条路的**前两段完全相同**（IR → 简报 → 生图 → 矢量化草图 → 闸口①），别把路线 2 丢了。

---

## 路线 B：图像生成 —— 可执行全流程（2026-09-26 重写）

适合**质感优先**的图。**默认走这条路。** 完整命令链：

```bash
# ── 0. 写 IR（强制，见「路由协议 2」）────────────────────────
#    IR 就是"完善后给模型的 prompt"，它约束生图质量。

# ── 1. IR → 约束简报 ──────────────────────────────────────
python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage sketch -o brief1.md
#
#    ★★ v4.2 起，**默认先走「极简首轮 + 增量补约束」**（作者 2026-10-05 要求）：
#       别一上来就灌几 k 字符的规格书；先给「一句话 + 面板序列」，物理错的地方下一轮再补，
#       一次只补**错的那几条**（对了的不重复写）。
#
#         python3 scripts/brief_lite.py ir/xxx.ir.yaml --tier 0 --size 2048*704 -o gen/lite0.md
#         #   → 出图（照第 2 步）
#         #   → 看图 + 闸门，把**画错**的点写进 gen/round0_fail.md（一段话，不是重发规格书）
#         python3 scripts/brief_lite.py ir/xxx.ir.yaml --tier 1 --size 2048*704 \
#             --add gen/round0_fail.md -o gen/lite1.md
#
#       tier 0 = 一句话 + 画布/面板序列 + 输出硬约束   （实测 QGP：548 字符，原规格书 7559）
#       tier 1 = tier 0 + 3D 空间线索 + 每面板一句形态（实测 QGP：1427 字符）
#         ★ v4.4：3D 线索 = 通用 4 条（板/接触阴影/三轴/光源）+ 火球、核子球团两条按 IR 关键字条件追加（实测：牛顿/法拉第 4 条、UPC 5 条、QGP 6 条）
#       一句话取 IR 的 figure.one_liner（推荐自己写一句），没有就退回首句 physics_claim。
#       为什么不做成"自动把失败约束全塞进去"：增量要人判断（看上一轮的图 + 闸门报告），
#       工具只负责把增量拼进简报。
#
#    ★ 实测（QGP，2026-10-05，qwen-image-3.0 mm，同两张风格参考）：
#       极简档的画面**更接近** Gemini 那类"好看"，但**物理并没有自动变对**——
#       tier 0 那轮照样把 z 轴与运动方向画反、核没被压扁；补了增量约束的 tier 1 才把
#       「薄饼方向 / 板面三轴 / 色场管取向」做对（3D 闸门：tier0 1/2 过，tier1 1/2 过，
#       但 tier1 通过那张的板面占比 4.9% vs tier0 的 0.40%）。
#       → "提示词短 = 画面好看" 与 "物理对" 是两件事，前者靠生图模型，后者只能靠增量约束 + 闸门。
#
#    ★ 完整规格书（本行下面这条）留给**复现论文图**这类必须逐条对账的 A 类任务。

# ── 2. 出草图（★ 必须带风格参考图；key 用你自己的）──────────
python3 scripts/gen_figure.py --brief brief1.md --stage sketch \
    --ref refs/T3-33.png --seeds 1,2,3 --outdir gen/
#   产物：gen/sketch_s1.png、gen/sketch_prompt.txt、gen/calls.jsonl
#   ★ 模型**稳定**在四周画 1~2px 外框：简报里写「不要外框」没用、
#     --negative 加 border/frame/picture frame 也没用（实测 5/5 全有框）
#     → 别求它，确定性裁掉；后面所有步骤都用 *_clean.png：
#   ★ 外框可能是**两层**（1px 深线 + 1px 浅灰线 lum 244~249）：默认阈值只认深线，
#     浅灰线会留下来变成多余细边 → 这种图加 --bg 0.975 再裁一次
#     （实测 2026-09-27：形变核→火球 算例，下 2px + 右 1px 就是这么裁掉的）。
python3 scripts/trim_border.py gen/sketch_s1.png -o gen/sketch_s1_clean.png

# ── 3. 草图矢量化输出（人可改）────────────────────────────
python3 scripts/sketch_to_vector.py gen/sketch_s1_clean.png -o gen/sketch_s1.svg --ocr
#   不用写 panels.py：草图靠自动切分，每个形体一个子层（part-01…）
#   ★ 默认 --q 16（每通道颜色量化级数）。草图边缘的抗锯齿会切出数万条碎路径，
#     量化后才能“给人改”。实测：0->30412 条/MAE 0.376；16->2111 条/MAE 1.102
#     （>8 色阶像素 0.31%，与不量化的 0.32% 持平，但路径少 14 倍）。要更精就 --q 0。

# ── 4. ★ 闸口①：草图过物理检查（不能跳）────────────────────
python3 scripts/check_sketch.py gen/sketch_s1_clean.png --ir ir/xxx.ir.yaml
#   ★ 一次出了多张备选？**一次全喂进去** + 落 json，再自动排序挑图
#     （人眼只审没有硬伤的 —— 实测 UPC：8 个 seed 只有 3 张合格）：
#     python3 scripts/check_sketch.py gen/sketch_s*_clean.png --ir ir/xxx.ir.yaml \
#         --json gen/check1.json
#     python3 scripts/pick_best.py gen/check1.json

# ── 4.5 ★★ 交接点（v3.0）：多张草图 → 让用户挑 / 让用户改 ──────
#   ★ 默认**停下来**。草图是全链最便宜的返工点，而 "哪张更像你要讲的物理" 只有作者知道；
#     pick_best 负责把没硬伤的排前面（机器能做的都做了），拍板是人做的事。
python3 scripts/sketch_handoff.py gen/sketch_s*_clean.png --ir ir/xxx.ir.yaml \
    --json gen/check1.json --outdir handoff
#   产物：handoff/candidates.md（表格 + 预览图 + 三种回音怎么回）、
#         handoff/cand_01.svg（可编辑，每形体一个 part-NN 子层）、cand_01_preview.png
#   → 把 candidates.md 给用户看，问清楚：① 用第几张？ ② 还是下载 SVG 自己改？
#   ★ v3.1：别再把「我贴了 candidates.md」当成「已经问过了」—— 要留下**回执**：
#     ① 生成客户能点的选择页（底栏给选择码，不用让客户在仓库里翻 markdown）：
#        python3 scripts/make_picker.py --handoff handoff --tag V5 \
#            --notes handoff/notes.json --title "集体流产生"
#        -> handoff/pick.html（双击可点）+ handoff/pick_sheet.png（贴聊天窗口用）
#     ② 客户回话后落回执（--by 只认客户侧的值；写 agent 一律判失败）：
#        python3 scripts/choice_gate.py --handoff handoff --record \
#            --code V5-cand_06 --reply "用第 6 张" --by client
#        -> handoff/choice.json（候选 / 位图 / 原话 / 时间戳）
#     ③ 第 5 步之前机械校验（ref_guard.py --run 会自动带上它）：
#        python3 scripts/choice_gate.py --handoff handoff    # 非零退出 = 不许出成品位图
#   [为什么不是「说一句就行」：一次真实任务里 handoff/ 材料齐全、candidates.md 也贴了，
#    但工作区**找不到任何回执**，最后是 agent 自己挑了一张往下走 —— 约定拦不住，
#    只有闸门拦得住。]
#   ★ 用户改完传回 → 灌回流程（**强制重过闸口①**，人改不豁免）：
#     python3 scripts/sketch_ingest.py handoff/cand_02_edited.svg --ir ir/xxx.ir.yaml \
#         --size 1664*928 -o gen/sketch_edited_clean.png
#     过了闸口才继续第 5 步，且第 5 步的 --content-ref 换成 gen/sketch_edited_clean.png
#   ★ 用户说"你定" → **也要留回执**（--by manual），否则闸门过不去：
#     python3 scripts/choice_gate.py --handoff handoff --record \
#         --code V5-cand_01 --reply "你定吧" --by manual
#     然后按 pick_best 的顺序取第一张往下走
#   ★ 拿不到回音就不要往下走：成品位图一次出图要花钱，草图返工几乎免费

# ── 5. 出成品位图（★ 草图 + 风格参考图都要带）──────────────
#   ★ 风格档在**简报编译这一步**定（`ir_to_genbrief.py --style-mode auto|flat|render3d`，
#     默认 auto，按 IR 的 style 段判；**gen_figure.py 没有这个参数**）：
#     IR 写 3D/半写实/体积/网格线 -> render3d（球面明暗+高光+真渐变）；
#     判不出 -> ref（跟随参考图）。参考图是风格书，不是内容模板。
python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage render -o brief2.md
python3 scripts/gen_figure.py --brief brief2.md --stage render \
    --content-ref gen/sketch_s1_clean.png --ref refs/T3-33.png --seeds 21,22 --outdir gen/
#   ★ 上一步选中的草图走 **--content-ref**（不是 --ref）：它是构图依据（已过闸口①）。
#     ⚠️ 别把草图写进 --ref —— 草图是**构图依据**，--ref 只收风格书；
#       角色写错时两个机制同时失效：草图不再当构图依据、
#       而 ref_leak_check 又只拿 style_refs 判「有没有抄参考图」→ 静默失败。
#     只传风格参考图 = 让模型重新猜一遍构图，构图会被改坏
#     （实测 2026-09-26：UPC 算例漏传草图，成品位图把核 B 画成了横扁，
#      与 IR 的 Lorentz 收缩方向相反）。
#   ★ 草图**原样送**（--content-ref-mode auto -> full，v4.7 起不再降级）：
#     位图这一步就是对草图的润色 —— 形体 / 材质 / 光照 / 文字都该原样带进去。
#     ★ 旧默认（v2.6.8–v4.6.3）是 render 档先降级成 layout-only（灰度模糊、只留布局）；
#     它只为**扁平**草图标定（形变核→火球：原样送 0.873 但火球=纯色橙盘；
#     降级后 0.904 且火球=3D 辉光+亮核）。草图自己已经 3D 时降级是纯损失 ——
#     2026-10-07 法拉第算例实测：降级图连 3D0 都过不了，构图保真反而没变好
#     （0.416/0.654 vs 原样 0.425/0.597），且三轴闸门 2/2 FAIL（模糊图承载不了
#     可读的 x/y/z 标签）。所以只有**扁平**草图才显式加 --content-ref-mode layout。
#   成品位图同样带外框 → 同样裁掉再进闸口/临摹（外框两层时加 --bg 0.975）：
python3 scripts/trim_border.py gen/render_s22.png -o gen/render_s22_clean.png --bg 0.975

# ── 6. ★ 闸口②：成品位图再过一次同一个闸口 ─────────────────
#   ★ 加 --sketch 给出**构图依据**：闸口会量「成品位图有没有沿用草图的构图」
#     （布局相关 r；低于 --fidelity-min 直接算硬伤）。锚点（形变核→火球）：
#     完全不带构图参考 0.696 = 构图跑掉；带草图 0.87–0.90。
python3 scripts/check_sketch.py gen/render_s22_clean.png --ir ir/xxx.ir.yaml \
    --sketch gen/sketch_s1_clean.png

# ── 7. 位图 → 矢量：首选重画，备用混合临摹 ──────────────────
#    首选：看懂每个部分后重画（形体带真 <gradient>，保留色彩+阴影）
#    备用（要"和位图一模一样"时）—— semantic 临摹，出的是**真 <text>** +
#    **按物理元素的命名图层树**（不是像素描摹）：OCR 词表逐词对齐后擦掉原字、
#    重写成可编辑 <text>；图形按 panels.py 的元素表归到 nucleus-A / photon-B …
#    实测（自旋图）非文字区 MAE 0.518、>8 色阶 0.01%，1946 条 <path>、0 个 <image>
#   ★ 参数怎么选（2026-09-27 实测）：--q 0（不量化）+ --R 5 是本 skill 目前最好的组合。
#     "色阶台阶"的根源是 --q 量化（q=16 时每通道跳 17 级），不是四叉树不够细：
#       形变核→火球 算例实测  --q 0 --R 5 -> MAE 0.626 / 贴边比 0.62
#                            --q 16 --R 10 -> MAE 1.195 / 贴边比 1.48（台阶肉眼可见）
#     代价：path 数 31005 vs 934、体积 3.99 MB vs 1.22 MB。要小体积再退回 --q 32。
#   ★ 路径数由 --q 决定，不是 --R（v2.7.2 实测，喷注淬火 1664×928）：
#     R=2 -> 103418 / R=3 -> 99021 / R=5 -> 86932 / R=8 -> 86525 条 path（R 几乎没用）；
#     --q 64 -> 34076 条 path / 7.08 MB / MAE 1.204（几乎无损）；
#     --q 32 ->  4631 条 path / 3.47 MB / MAE 1.369。
#     要「保真 + 体积」就调 --q；调 --R 基本白费。
#   ★ 逐标签选字体（2026-09-27）：位图里的标签是**生图模型画的，字体每张图都可能
#     不同**。矢量化以前只拿主字体（Arial）硬套，字面比例一变（实测 Tahoma 那类
#     窄高体）就过不了 labels.align 的墨迹高度验收 → 标签**退回成色块轮廓**，
#     "文字必须可编辑"直接失守。现在 `labels.fam_candidates` 会按
#     Arial → Tahoma → Verdana → Calibri → Segoe UI → DejaVu 依次试，取第一个过
#     验收的（默认字体就过时行为不变）。
#       实测（形变核→火球 3D 版，5 个标签）：只试 Arial -> 5 条里 2 条成 <text>；
#         逐标签选字体 -> **5 条全成 <text>**（其中 3 条换成 Tahoma）。
#     SVG 里写的是**实际量字宽用的那个字体族名**（从字体文件读，不靠猜）。
python3 scripts/raster_to_vector_semantic.py gen/render_s22_clean.png -o fig.svg \
        --words words.txt --panels my_panels.py --W 1662 --R 5 --K 7 --q 0 \
        --legend fig_layers.md --el_txt fig_el_table.txt --check
#    --legend 人读图层清单 / --el_txt 元素明细 / --check 回渲染自检（MAE/PSNR）
#   ★ 要「整体改一个物理色块」（而不是按色素一条条改）就加 --shade：
#     逐像素临摹结构上必然是「一种颜色一条 path」—— 实测形变核→火球：stage1-nucleus
#     5162 条 path = 5162 种 fill，fireball 6696 = 6696（同色都并不起来）。图层按物理
#     元素分了，但元素内部还是颜色集合，改色只能一条条改。
#     --shade 把元素重写成「1 条基色块 / 1 条真 <radialGradient>/<linearGradient> body
#     + 少量 fill:#000/#fff + fill-opacity 的明暗层（不含颜色，所以换基色时明暗自动跟着走）」。
#     实测（同一张图 --q 0 --R 5）：31005 条 path -> 541 条，MAE 0.626 -> 0.919，3.99 -> 1.84 MB。
#   ★★ 但 --shade 在**羽化边缘**上会碎（v2.7.2 实测，喷注淬火）：
#     半透明介质的羽化外缘会被切出**白裂纹**、内部出**大陆状斑块**
#     （k=4x32 / k=5x64 都试过，都不行）。真渐变 body 也不行：**介质掩膜不连通**
#     —— 喷注横穿把介质切开，最大连通块只占 52.5% → gradfit 直接放弃。
#     → **保真优先**：这类元素就用逐色临摹；SHADING 表留在 panels 里，
#       用环境变量 NO_SHADE=1 切换。判据仍是「该元素回渲染 MAE」，别凭感觉。
#     ★ 径向渐变（火球）必须走真渐变 body：用「平涂基色 + N 档明度层」近似，每档沿等半径
#       连成一个环，16 档时球面是肉眼可见的同心色环 —— 那就是最忌的"色阶退化"。
#     语法 --shade k:levels:grad（如 auto:16:1 / 3:128:1 / auto:16:0）
#     或写进 panels.py：SHADING = {"*": {"k": None, "levels": 16, "gradient": True}}
#   ★★ 真渐变 vs 逐像素：**先量再选路，别凭感觉**（2026-09-27 实测）
#     判据只有一个：**回渲染后该区域的 MAE**。不要用 gradfit 的拟合残差当判据 ——
#     它会把「等色线不同心」的像素当离群点丢掉，残差看着只有 5.5，画出来差 31 倍。
#       · 等色线真同心（球心高光 / 均匀辉光）→ 真 <radialGradient>：path 少、可整体改色
#       · 最亮核心**偏离几何中心**、或内部有结构（颗粒/丝带/多个球）→ 逐像素
#     实测（形变核→火球，同一元素、同一张位图，只换画法）：
#       逐像素     火球区 MAE 0.455
#       真 aradial 火球区 MAE 14.324（亮核偏心 → 同心等色线整圈错位成亮/暗环）
#     ★ aradial 现在**已支持**（body 写局部坐标 + <g transform>，绕开 cairosvg 不认
#       gradientTransform 的问题）。开法：SHADING 里写
#       {"gradient": True, "levels": 0, "flat": False, "drop_tol": 60, "nstops": 64}
#     ★ 元素掩膜最外 1~3px 是抗锯齿过渡像素：**拟合要腐蚀过、判「body 盖不到」要
#       膨胀过**。否则拟合中心被带偏（火球实测 dev 中位 21 → 6.3），且那圈过渡像素
#       会被逐条按原色画出来 = 一圈硬边。
#   ★★ PDF「纱窗」：逐像素临摹在 PDF 里会出现 1px 亮网格（火球区 MAE 13.4），
#      groupvec 默认给**不透明实色** path 加**同色描边**（stroke=fill, width=1.0）→ 2.79。
#      panels 里 SEAM={"*":1.0} 可覆盖 / {"*":0} 关掉；**别加到 fill-opacity 的明暗层**。
#      ★ MAE 自检要用**成品同款渲染器**（Edge 打印 PDF → PyMuPDF 光栅化）；
#        cairosvg 回渲染看不出这个问题（0.59 vs 2.43）。
python3 scripts/raster_to_vector_semantic.py gen/render_s22_clean.png -o fig_edit.svg \
        --words words.txt --panels my_panels.py --W 1662 --R 5 --K 7 --q 0 \
        --shade auto:16:1 --legend fig_edit_layers.md --check

# ── 8. 三道门禁 + 返修单 → 交付 ───────────────────────────
python3 scripts/check_render.py fig.png --probe 0.5,0.10
python3 scripts/check_delivery.py fig.pdf --svg fig.svg
python3 scripts/audit_composition.py fig.pdf
python3 scripts/repair_brief.py fig.svg --profile assets/style-profiles.json
```

### ★ 关键设计：位图的定位是「更好的草图」，但**它过了闸口就必须照它画**

草图阶段只求"构图清晰、元素齐全"，不追求质感 —— 质感由第 5 步负责。

到了第 7 步，**位图已经过了闸口②，物理是对的**，所以重画/临摹都应该**照它**。
对不上 = 位图错了，回去改简报重出，**不要**在矢量那步偷偷"修正"。

> ⚠️ 老版本这里写着"绘画那步要按 IR 的 geometry_constraints 正确执行、
> **不要照抄位图的几何**" —— 那是**闸口还没补上**时候的写法（怕把位图的物理错误抄进去）。
> 现在闸口②已经拦在位图前面，这句就反了，2026-09-26 改掉。
> ★ v4.5 补充：这一条要和「位图精修」合起来看 —— 位图**自己也会错**（实测：会加 IR 里没有的英文词、会把形状改走样），所以「照它画」之前必须先跑 `gate3d_rank.py --require-all` + `axis_gate.py` + 逐条对照错误清单；位图那一步不过闸，就回去改简报重出位图，而不是带着错往下走。

### ★★ 这条规则有闸门了（v3.2）：`scripts/bitmap_conformance.py`

「照它画」以前只是**约定** —— 2026-09-30 实测它就失守过一次：集体流图第 5 版把
**位图之前就存在**的 `build_figure_v3.py` 整份搬过来（文本相似度 **96.0%**），
只换内容层，底盘常量原样继承，板子倾角差了 **11.3 度**，而**五道门禁全绿**
—— 没有一道在量「成品和位图像不像」。

所以别靠"记得照它"，把两边各量一遍：

    python3 scripts/bitmap_conformance.py <所选位图> <成品.png|.svg>

比的是架构几何：面板数、每个面板的**上边界倾角 / 板左缘 x / 板左上角 y /
侧边界角**、宽高比。超阈值 → **非零退出，不许出成品**。实测标定：

    位图 vs v5（沿用旧底盘）→ 拒绝：上边界倾角 17.79 -> 6.45（差 -11.33 度）
    位图 vs v6（重做底盘）  → 仍拒绝：b/c 两块板的左缘 x 与左上角 y 差 3.3~8.3 mm
    位图 vs 它自己           → 通过（自检）

★ **量不出来 ≠ 通过**：拟合不可信或两边至少一侧量不出来的量列成「不可比」，
  不计失败；但可比总数 < 3 时判「无法比对」而不放行。
★ 有意与位图不同（位图物理错了、客户要求改）才加 `--allow-diff "理由"`，
  并在交付说明里写明。

### ★ 生图那一步（gen_figure.py）

| 事 | 怎么做 | 为什么 |
|---|---|---|
| **API key** | 读环境变量 `DASHSCOPE_API_KEY`，**脚本不存 key** | 别人装了 skill 得用**他自己的** key |
| **风格参考图** | `--ref 图1.png --ref 图2.png`（可多张）。**缺了直接报错** —— 要纯文生图才加 `--allow-no-ref` | 只给文字 → 出来一定很"通用"。参考图 = Nature 风格书。纪律交给记性就等于没有（v2.8 从"打一行警告就继续"改成硬错误）|
| **两个接口** | `qwen-image-*` → 图生图（**支持 --ref**）；`wanx*`/`wan*` → 纯文生图 | 要参考图只能用前者 |
| **image 字段** | 本地图 → **base64 data URI**（自动）；公网 URL 直接透传 | mm 端点**只收**公网 URL 或 base64，**不认 `oss://`** —— 实测提交报 400 `Image must be either a public URL or a Base64 encoded string`（v2.6.1 修）|
| **两个产物** | 草图 PNG + **草图 SVG** + 成品位图，全部落盘 | 用户要能拿到中间产物 |
| **裁外框** | 出图后跑 `scripts/trim_border.py in.png -o out_clean.png` | 模型**稳定**在四周画 1~2px 外框，简报与 `--negative` 都拦不住（实测 5/5）→ 确定性裁掉，别求模型 |
| **提示词扩展** | `--prompt-extend` / `--no-prompt-extend`（默认沿用接口行为：mm=True / t2i=False）| ★ **v4.0 实测推翻了 v2.8 的建议**：`prompt_extend=True` 会让服务端**重写提示词**，看起来会稀释简报 → 但**关掉它更糟**：`--no-prompt-extend` 把简报**原样**当提示词，模型于是把「这是一份说明文档」这个先验也画出来（图上出现大段中文、章节编号、色卡）。实测同一份简报 + 同一批参考图：**加 flag 12 张全中，走接口默认 4 张零漏字** → **草图档不要加这个 flag**。实际取值记进 `calls.jsonl` |
| **画布比例对账** | `--size` 与 IR 声明的比例不符时当场警告 | 同一张图两个比例，IR 的归一化坐标就废了（实测 sketch5_upc 声明 2.10、默认 `--size` 1.79，差 15%）|
| **调用留痕** | `gen/calls.jsonl` 记 model/seed/size/refs/prompt 指纹 + `prompt_extend` / `no_style_ref` / `ir_ratio_dev` | 出图后要能溯源、核对计费、回溯提示词有没有被服务端重写 |
| **单个 seed 抖动** | 失败**重试 2 次**（共 3 次尝试），仍失败记 `ok=False` 继续下一个 seed | 实测 2026-09-27：seed 7 撞 TimeoutError 让整批 traceback 退出 —— seed 9 根本没跑、已出的 seed 5 也没进 `calls.jsonl` |
| **限流退避** | 429 / Throttling / rate limit 判为限流 → 退避 5s、10s（普通故障 3s）| 限流时立刻重试只会再撞一次；批量出图（多 seed）最容易撞 |
| 没 key 时 | `--dry-run` 只写提示词和调用计划 | 自检不用花钱 |

> 实测（UPC 图，2026-09-26）：`wanx2.0-t2i-turbo` 对结构化示意图太弱
> （画不出顶点/箭头/e⁺e⁻），且不支持参考图；`qwen-image-3.0` 8 个 seed 出图，
> 只有 3 张同时满足"两条平行虚线 + 不重叠 + 相向运动 + 双光子汇聚 + e⁺e⁻ 背对背"。

### ★ 输出「变成参考图的内容」了怎么办（v2.6.4）

**现象**：出的图跟参考图几乎一模一样 —— 物体、布局、箭头方向、文字全是参考图的。

**根因**：`qwen-image-*` 是**图生图**。参考图的内容越接近目标，模型越倾向**直接抄**
（`prompt_extend` 会重写提示词 —— ★ 但**别急着关**：v4.0 实测 `--no-prompt-extend` 反而会让模型把简报本身当内容画，见〔生图那一步〕表格与 CHANGELOG v4.0 第 2 条）。参考图给 2 张会加重。
**这不是"提示词没写清"，是参考图选错了。**

按顺序排查（每一步都能用机器量）：

```bash
# 1. 先量：r >= 0.85 就是照抄；0.60~0.85 偏高
python3 scripts/ref_leak_check.py gen/render_s22.png \
    --ref refs/T3-33.png --content-ref gen/sketch_s9_clean.png
```

2. **换参考图** —— 优先「**内容不同、风格相同**」。实测（自旋算例）：

| 出图 vs 参考图 | 内容关系 | r |
|---|---|---|
| 成品位图 vs T3-33 | 都要"双核+碰撞参数"→ 同类 | **0.117**（健康；本图没被抄） |
| 草图 vs T3-33 | 同类 | 0.108 |
| 成品位图 vs T3-09（QGP 涡旋） | 不同内容、同风格 | 0.017 |
| 成品位图 vs **自己的草图** | 本来就该像 | 0.634 |
| 两张不同参考图互比 | 基线 | 0.125 |
| 同一张图互比（照抄上限） | 照抄 | **1.000** |

> 阈值 0.85 定得**高于** 0.634 —— 正常"继承草图构图"不会被误判成照抄。

3. **说清角色**：`--content-ref <上一步草图>`（构图依据，本来就该像，自动排在最前）
   + `--ref <风格参考>`（只给风格，不许抄）。不标角色时，文件名含 `sketch`/`草图`
   的会被自动认成构图参考。
4. **减张数**：2 张同类参考比 1 张更容易被抄；先降到 1 张风格参考试。
5. **简报里的反照抄硬约定**（`ir_to_genbrief.py` 从 v2.6.4 起自动写）：
   「参考图只给风格，物体/数量/布局/箭头方向/文字一律不得照搬，以本文为准」。

`gen_figure.py` 出图后**自动跑**这个自检，把 `ref_leak` / `ref_sim` 写进
`calls.jsonl`；不想要就 `--no-ref-check`。

> ⚠️ **测不到的**：只抄一部分（r 会掉到 0.3 左右）、以及"照搬构图但换配色"。
> 这两种要靠闸口①的构图逐条核对 + 人眼。别把 `ref_leak_check` 通过当成"没抄"的证明。

### ★ 参考图 = 风格书，不是内容模板（v2.6.7）

**要的是**：参考图提供**风格**（配色 / 线条 / 材质 / 光影 / **渲染方式**），
**不提供内容** —— 不要求布局、物体、箭头、文字跟参考图一样。
**「期刊矢量插画风」不等于「扁平 2D」**：`_T3精选` 里 T3-02 那条线本身就是
**3D 渲染**的矢量插画（核子球面明暗 + 高光 + 经纬网格线 + 火球橙→红多层渐变）。
参考图里**没有**的物理对象，按 IR 画出来就行，不要因为"参考图里没有"就不画。

**据此定风格档**（`ir_to_genbrief.py --style-mode`，默认 `auto`）：

| 档 | 简报第四节怎么写 | 什么时候用 |
|---|---|---|
| `flat` | 扁平矢量：平涂 + 细描边 | IR 明说要扁平（简单的流程图式示意图） |
| `render3d` | 3D 渲染插画：球面明暗 + 高光 + 柔和阴影 + **真 `<gradient>`** + 网格线 | IR 明说 3D / 半写实 / 体积 / 网格线（T3-02 那条线） |
| `ref` | **跟随参考图**：先看参考图是 2D 还是 3D，照它的渲染方式来 | `auto` 判不出时的默认 |

`auto` 的判据 = IR 的 `style` 段（`classification` / `evidence` / `conventions`）
关键词：含 `3D` / 体积 / 网格线 / 半写实 → `render3d`；含 扁平 / 平涂 → `flat`；
都没有 → `ref`。**只有 `sketch` 档永远保持扁平**（那是为了能自动切矢量图层，
**不是最终风格**）；成品位图档按上表走。

> ★ **默认档 = `render3d`（作者 2026-09-28 定）**：所有配图**一律** 3D 明暗风，
> IR 的 `style.mode` 一律写 `render3d`；扁平（`flat`）**只允许**出现在
> ①承载定量数据的面板（谱 / 曲线 / 误差带 / 场图 / 极坐标数据）
> ②纯抽象内容（演化序列色条、晶格示意、流程条），且必须在交付说明里写明理由。
> 即使是这两类，同一张图里的**物理示意图面板仍必须是 3D 的**。
> 依据：`_T3精选` 21 张里 18 张带 3D 明暗体积语言，剩下 3 张（T3-50/T3-59/T3-60）
> 主体是平面 —— 而那 3 张画的正是「演化序列 / 晶格 / 流程条」。
> 反例代价：一张扁平示意图把五道门禁全过了（见上「验证」一节）。

### ★ 反过来：该学的风格没学到怎么办（v2.6.7 / v2.6.8）

**现象**：出的图又干又平，火球是个**纯色圆盘**，完全没有参考图那种 3D 质感 ——
用了 diffusion model 却没用它的好处。

**根因一（v2.6.7 实测，形变核→火球 算例）：简报把风格写死了。**
IR 的 `style` 明写「半写实插画 / 3D 椭球 / 球面明暗 + 网格线 / 火球橙→红渐变」，
而 `ir_to_genbrief.py` 生成的简报却写着「目标是期刊矢量插画风，**不是 3D 渲染图**」
—— IR 与简报**直接打架**，模型照简报走，于是出纯色圆盘。

> ⚠️ 这和上面「抄成参考图」是**两个相反方向的病**：
> 一个嫌它太像参考图（内容被抄，查 `ref_leak_check` r 太高）；
> 一个嫌它不像参考图（风格没学到，查**简报里有没有禁止 3D**）。
> 别用同一套排查。

**根因二（v2.6.8 实测）：构图参考（`--content-ref`）把"扁平"当风格一起送进去了。**

上面那条修完，简报已经不禁 3D 了，可出图**还是**纯色圆盘 —— 因为
`--content-ref` 传的是**扁平草图**，而 qwen-image 是**图生图**：它会
把草图的**渲染风格**连同构图**一起**继承，风格参考被稀释掉。

| content-ref 怎么送的（形变核→火球，同一简报 / seed 53） | 与草图布局的列剖面相关 r | 出的火球 |
|---|---|---|
| 原样送（旧行为） | 0.873 | **纯色橙盘** |
| 不送 | 0.696 | 3D 辉光，但构图跑掉（三取向涨落画成三个球） |
| **降级成 layout-only** | **0.904** | 3D 辉光 + 亮核 |

修法：`gen_figure.py --content-ref-mode auto|layout|full`。
★ **v4.7 起默认 `auto` = 原样送（`full`）** —— 上表那个降级只对**扁平**草图成立，
所以它现在是 opt-in：只有草图本身是扁平稿时才显式 `--content-ref-mode layout`
（降级成「灰度 + 降采样再放大 + 轻微模糊」的只含布局的图，落盘 `layout_*.png`）。
草图已经 3D 时降级是纯损失（2026-10-07 法拉第算例：降级档三轴闸门 2/2 FAIL，
连可读的 x/y/z 标签都被磨掉）。送的是哪张记在 `calls.jsonl` 的 `content_ref_sent`。
★ 对**扁平**草图，这不是"拿构图换风格"：**两边同时变好**（0.873 → 0.904）。

排查顺序（按这个顺序，别跳）：
1. 打开简报看**第四节（风格）+ 第五节（禁止项）**：出现「不是 3D 渲染图」
   → 风格档错了（IR 要 3D 却给了 flat）。重出简报：
   ```bash
   python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage render \
       --style-mode render3d -o brief2.md     # 或 --style-mode auto，让 IR 自己判
   ```
2. 简报第四节现在会把 IR 的 `style.palette` / `line_widths` **原样带出来**；
   要是没有，就往 IR 的 `style` 段补配色和线宽（`render3d` 档尤其需要）。
3. **查 `calls.jsonl` 的 `content_ref_mode` / `content_ref_sent`**：先量**草图自己**是
   不是已经 3D（`scripts/gate3d_rank.py <草图>`）。草图**扁平**、而这一轮又送了
   **原样草图**（`full`）→ 加 `--content-ref-mode layout` 用**同一个 seed** 再跑一遍 ——
   这是最便宜的一刀，实测同时救回风格和构图。★ 草图已经 3D 时**不要**降级：
   降级会把形体与可读的轴标签一起磨掉（2026-10-07 法拉第算例，三轴闸门 2/2 FAIL）。
4. 到这里才对不上，才考虑换模型 / 加 seed。

### ★ 出的图「很 AI」/ 火球像颗光滑糖球（v2.6.9）

**现象**：形体、构图、配色都对，但一看就"很 AI"—— 发光体是一颗**光滑高光的球**，
内部空空如也。用户拿别的模型（网页版）出的同题材图一比，明显更有内容。

**根因（实测，形变核→火球 算例）：IR 的 `material:` 根本没进简报。**
`ir_to_genbrief.py` 的元素表以前只带 `primitive`（形态），`material`（材质）
**全文件 0 次出现**；而简报里却**硬编码**着一句
「火球/热区：内亮外暗的多层半透明渐变（亮核→橙→红）…边缘柔和但不模糊」——
不管 IR 写什么，模型都被按在一颗光滑高光球上。
再叠加禁止项「不要添加 IR 清单里没有的东西」，模型连内部结构都**不许**加。

> **光滑高光 + 均匀径向渐变 + 无内部结构 = 通用 CG 球 = 用户说的「AI 画风」。**

**修法**（v2.6.9）：

1. 元素表每条带 `【材质：…】`（和 `【形态：…】` 并列）—— IR 写了什么就送什么。
2. 删掉硬编码的火球描述，改成「**发光体 / 热区怎么画，以第一节各元素的【材质】为准**」。
3. 禁止项第 1 条改成禁**【独立物体/箭头/文字/装饰光晕】**；
   【材质】里写明的内部结构（分层 / 组元颗粒 / 场线 / 亮核 / 外壳 / 日冕）**必须画**。
4. 「颗粒/噪点」澄清为**胶片颗粒/噪点纹理** —— 示意性的细小符号不算。

**所以在这条路线上，发光体一定要在 IR 的 `material:` 里写清楚"里面有什么"**：

```yaml
material: >
  **哑光**（不要高光反射 / 塑料光泽 / 辉光外溢 bloom）。
  由内到外**分三层、边界要看得出来是三层**：① 亮黄白热核 ② 橙→红等离子体壳
  ③ 半透明橙红日冕（边缘羽化）。内部散布**组元颗粒**与**弯曲短丝线**（胶子场），
  随机分布、不排成规则网格。最里面是 4 个相互重叠的参与者核子球。
```

**实测数字**（qwen-image-3.0，同一份构图 / **同一个 seed 53**，只改 spec）：
火球盘内「内部高频能量」旧 spec **0.0103**（全部里最平滑 = 纯渐变球）
→ 新 spec **0.0265 / 0.0418**（seed 53 / 51），即 **2.6~4 倍**；
盘内最亮 1% 亮度与内部小暗团数同步上升。数字与对照图见
`assets/demos/evo3d_fireball_spec/`。

---

### `check_sketch.py` 为什么要分两类输出（`references/ir-spec.md` 有详述）

| 输出 | 谁判 | 例 |
|---|---|---|
| ■ 自动测到的 | 机器 | 内容边界/出界、重心偏移、留白分布、画布比例被改、风格量测 |
| ■ 必须逐条回答的 | **人/模型看图** | IR 的 `geometry_constraints` 逐条变成待答问题 |

**机器判不了物理。** 把"检查物理"从一句原则变成**必须填的动作**，
才拦得住"图像模型把喷注画反、把非中心碰撞画成同心"这类错。

### ★ 位图 → 矢量的三种实现（第 7 步到底用哪个）

| | **模型看图重画**（首选） | `raster_to_vector_semantic.py`（备用） | `raster_to_vector.py`（备用） |
|---|---|---|---|
| 原理 | 看懂"这是核/这是光子线/这是顶点"再重画 | 自动切分定形状 + 人写元素表命名 | 等高线 → 填色路径，**没有"理解"** |
| 文字 | 真 `<text>` | **OCR + 逐词对齐**，真 `<text>` | 模型写 `--text-spec` 后擦掉重写 |
| 渐变 | **真 `<gradient>`**（能保住色彩和阴影） | 细调色板/不量化时**肉眼看不到台阶**（实测贴边比 0.62×源图）；也能合成真 `<gradient>`（`panels.py` 的 `GRADIENTS`，见下） | 退化成色阶台阶 |
| 图层 | 按**结构/物理**（人手定） | 按**物理元素**（命名图层树，**不再夹颜色层**） | 按**颜色**分，`--groups` 可归组 |
| 依赖 | 无（模型干活） | `numpy scipy Pillow cairosvg cairocffi fontTools` | 还要 `cv2`/`skimage` |

选法：

- **默认 → 重画**。看懂了再画，曲线干净、渐变是真渐变、图层是物理的。
- **要"和位图一模一样" → semantic 临摹**。同分辨率 MAE 实测 0.2–0.5，代价是
  每条曲线碎成台阶，且每张图要手写 `words.txt` + `panels.py`。
- ★ **渐变不要急着上真 `<gradient>`**：细调色板（`--q 0` 或 `--q >= 32`）+ 细四叉树
  （`--R 5`）时，四叉树本身就把渐变追平了，加真渐变反而**更差** —— 渐变画的是"模型色"
  （残差 5~9 级），留下的台阶块画的是"原图色"，交界处多一圈硬边、球面出现成片斑块。
  实测（形变核→火球）：真渐变全开 MAE 1.016 / 贴边比 1.39 vs 全关 MAE 0.626 / 0.62。
  只有**必须用粗调色板**（`--q <= 16` 压体积）时才按元素打开 `GRADIENTS`
  （算法与实测见 `scripts/raster_vector/gradfit.py` + `CHANGELOG.md` v2.6.5）。
- ★ **临摹要「能整体改」就加 `--shade`**：临摹产物结构上必然是「一种颜色一条 path」
  （实测 5162 path = 5162 种 fill），元素内部是颜色集合、改不了一整块。`--shade` 把元素
  重写成「1 条基色块 / 1 条真渐变 body + 少量黑/白 fill-opacity 明暗层」，改一个 fill
  就整体换色。实测 31005 -> 541 条 path，MAE 0.626 -> 0.919。
  径向渐变必须用真渐变 body，否则出色环（见上一条）。
- ⚠️ **`--shade` 不是万能的**（v2.7.2）：**羽化边缘**（半透明介质外缘）会被切出白裂纹、
  内部出「大陆状」斑块；元素掩膜被别的元素横穿切成**不连通**时，真渐变 body 会被直接放弃
  （实测介质掩膜最大连通块仅 52.5%）。这类元素**保真优先走逐像素**，
  `SHADING` 留在 `panels.py` 里用 `NO_SHADE=1` 切换，选路判据是该元素回渲染 MAE。
- 图**本来就该拆成图元** → 别临摹，直接写 IR / 写 SVG，渐变是真渐变。
- ⚠️ **重画的忠实度天生低于临摹。** 这是选择和位图"像不像"的取舍，
  **不是**"矢量后质量就比位图差" —— 重画的上限在人的水平，不在格式。

> 依赖：semantic 那条只要 `numpy scipy Pillow cairosvg cairocffi fontTools`，
> **不需要 cv2/skimage**。`raster_to_vector.py` 才需要 `cv2`/`skimage`，
> 而 **ChatGPT 沙箱里两者都没有** —— 那条环境只能走重画。


### ★ 参考图 vs 画法规律：**能直接给图就别提炼**

`assets/t3-exemplars/` 里有 **17 张 CC BY 4.0 的 T3 参考图**
（STAR / ALICE / CMS / 开放获取的 arXiv 论文，逐张署名与加工说明见 `NOTICE.md`）。

| | 给参考图 | 给提炼的规律 |
|---|---|---|
| 效果 | **无损、最好**（模型 few-shot 能力强） | 有损压缩 |
| 内部/本地 | ✅ **直接用图** | 不需要 |
| **公开发布** | ❌ 版权 | ✅ 只剩这条路 |

**「风格档案（数字）」和「画法规律（文字）」本质是同一个东西：
参考图的【版权干净代理物】。** 它们不是方法论，是降级方案 ——
因为多数期刊图不能随仓库分发（本仓库只留了 2 张 CC-BY）。

**所以：内部用直接调图；公开版用那 2 张 CC-BY + 代理物。**

> 那些"规律"（核带网格线、火球有纹理、衬板给中间调、粗黑箭头、
> 先定全局光源）都是从 8 张 T3 精选看图看出来的 —— **是总结，不是源头。**

---

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

> 停在"元素清单全中 + 物理无误"。**不追像素级复刻**——那会陷入无限调参。

---

## 按需参考（不要一次全读）

| 什么时候读 | 文件 |
|---|---|
| 写 IR、判定风格与后端 | `references/ir-spec.md` |
| **画 T3 示意图之前 / 图出来觉得"扁"** | **`references/3d-checklist.md`** ★ |
| 画 SVG、查图元、查技法 | `references/svg-cookbook.md` |
| 决定用哪个后端、为什么 | `references/tool-selection.md` |
| 风格量化、闭环修正 | `references/style-bench.md` |
| 遇到渲染异常 / 静默失败 | `references/gotchas.md` |
| **一张图要用多种工具** | `references/multi-tool.md` |

## 资产

- `assets/t3-exemplars/` —— **17 张 CC BY 4.0 参考图**（逐张署名见 `NOTICE.md`）
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

## 脚本

| 脚本 | 用途 |
|---|---|
| `svg_lib.py` | SVG 图元库（火球/圆柱/核子/壳/环/坐标轴/场线…） |
| `check_render.py` | 渲染静默失败检测，四项检查 |
| `compare_ref.py` | 参考图与成图并排对比 |
| `style_bench.py` | 风格度量与基准比对（**是诊断工具，不是优化目标**） |
| `assemble_panels.py` | 复合图拼版，保矢量 |
| `extract_figures.py` | 从论文 PDF 自动切图 |
| `audit_composition.py` | **局部构图审计**：文字重叠/线穿文字/出界/留白分布 |
| `style_profile.py` | **提取风格档案**（存数字不存图，版权干净） |
| `brief_lite.py` | **极简档简报**：IR → 一句话(tier 0) / +3D 线索与面板形态(tier 1)；`--add` 追加上一轮画错的物理约束。★ v4.4：不再硬编码 HEP 语言（公式 4 条 + 火球/核子团按需），面板数取 `figure.panels_count`，面板名支持 `面板 a、名称` 并去重 |
| `delivery_gate.py` | **阻断式门禁**：离目标风格超限就不许交付 |
| `check_delivery.py` | **投稿前检查**：矢量？文字可编辑？字号达标？ |
| `demo_combined.py` | **多工具联合示范**：svg_lib(卡通) + TikZ(公式) + PyMuPDF(合成) |
| `check_tools.py` | **工具能力探测 + 装机指引**——按图选工具的第一步 |
| `auto_converge.py` | **自动收敛循环**：量→定位→修正→复测，把人从多轮手工调参里解放出来 |
| `repair_brief.py` | **★ 门禁报告 → 给模型的返修单**（归一化坐标 + 具体改法）。"模型画、skill 验收"分工的关键一环 |
| `cartoon_lib.py` | **卡通图元库**（20 图元 + 全局光照模型）。做"草图→卡通图"这条线时用 |
| `ir_to_scene.py` | **IR → 可运行构图骨架**，含 `--check` 校验（primitives/散文 params/签名不符） |
| `repro_T3-03_param.py` | 参数化复现脚本（供 auto_converge 驱动），可作模板 |
| `gen_figure.py` | **★ 第 ② 步：生图**：IR 简报 → 草图 / 成品位图。key 由使用者自备（环境变量），支持 `--ref` 风格参考图（可多张），产物 + `calls.jsonl` 全部落盘 |
| `pdf_roundtrip.py` | **排版后的 PDF 回渲染 vs 原成品位图**（超采样 + 亚像素对齐 + MAE）。**唯一能发现"PDF 那一步悄悄退化"的工具**：不做超采样+对齐会得到 5 倍假性误差（实测 0.626 -> 2.998） |
| `raster_vector/gradfit.py` | **真 `<gradient>` 拟合**（radial / aradial / linear 三模型取残差最小者）。★ 只在粗调色板下才需要 —— 细调色板下实测反而更差，见 CHANGELOG v2.6.5 |
| `sketch_to_vector.py` | **★ 草图矢量化**（人可改的 SVG 草图）：不用写 `panels.py`，自动切分每个形体一个子层 |
| `sketch_handoff.py` | **★★ 人机交接（交出去）**：多张草图 → `candidates.md`（表格 + 预览 + 三种回音）+ 可编辑 SVG + 预览图。排序复用 `pick_best` 的判据 |
| `sketch_ingest.py` | **★★ 人机交接（灌回来）**：人改完的 SVG/PNG → 规范化到目标画布 → **强制重跑闸口①**（不过就拒，给返修单）；`--no-gate` 逃生门会留大字 |
| `ref_guard.py` | **★ 参考图角色闸门（v3.1）**：`--ref` 只许风格书（`assets/t3-exemplars/`）；sketch 的 `--content-ref` 只许作者手绘输入；render 的只许**上一步已过闸口①的草图**；`assets/demos/**` 任何阶段不许；同一张图不许同时占两个角色。`--run --` 包一层 = **先查后调**，查不过就不执行（不烧 API 的钱） |
| `ladder_gate.py` | **★ 提示词阶梯闸门（v4.6）**：A→B→C 不许跳档；A 档 = 一句话(≤80 字符) + 风格图、**只作诊断不许进交付链**；B 档必须含面板序列 + 输出硬约束 + **反抄写**；每轮 C 只许带「上一轮错在哪→改成什么」(≤3000 字符)；`ref_sim ≥ 0.60` 判照抄；render 前必须有 A/B/C 三段。账本 `<gen-dir>/ladder.json`；`ref_guard.py --run` **出图前自动查、成功后退图后自动登记**，`--ladder-waive "理由"` 可放行 |
| `ir_layout_guard.py` | **★ IR 版式锁闸门（v3.1）**：IR 把整张版式写死（`composition.分区` / `元素布局`、`elements[].params` 的绝对毫米、`conventions` 里的逐面板脚本 / "exactly N panels in ONE ROW"）→ 同一份物理每次草图都一样。它把**简报真的编译出来再扫**（简报才是模型看到的东西），只查 IR 字面会漏掉被模板合成的那些 |
| `choice_gate.py` | **★★ 客户拍板闸门（v3.1）**：没有客户回执 `handoff/choice.json` 就**不许出成品位图**；`--by` 只认 `client/customer/author/user/客户/作者/用户/甲方`，写 `agent`/`auto`/`codex` 一律判失败（客户明确说"你定"才用 `manual`）。`ref_guard.py --run --stage render` 会自动带上它 |
| `make_picker.py` | **★★ 客户选择入口（v3.1）**：handoff 候选 → `pick.html`（客户双击、点一张、底栏给选择码）+ `pick_sheet.png`（贴聊天窗口的总览图）。每张配 `notes.json` 的一句话说明与闸口①读数，有硬伤的卡片点不动 |
| `trace_rebuild.py` | **★★ 矢量成品三步的第三步（v4.0）**：从**临摹层**（`<g data-element=...>` 的掩膜）重建体积元素 —— 每个体积重做成 `clipPath`（精确可见轮廓）+ **真渐变网格**（每 BAND 一条 `linearGradient`）+ **线稿逐像素保留**。几何一律从掩膜取，**不重新走颜色阈值**。回归基线：v38 输入 MAE **1.946**、三体积像素数逐一对上 |
| `axonometric.py` | **★ 正交相机 + 校验（v4.0）**：给 `(az, el, roll)` 算三轴的屏幕方向与前缩；`--check` 打印 `\|r\|`、`\|u\|`、`r·u` 判它是不是**合法投影**（手挑三轴方向 = 斜投影，`\|r\|≠1`、`r·u≠0`，眼睛读它就叫「扁」）。★ 它**向上为正**，填 IR 的 `轴方向_deg` 要取负 |
| `check_3d.py` | **★ 第六道闸门（v4.0）**：栅格上判「实体 vs 贴纸」，四条硬判据 C1 接触阴影 / C2 面内内容被投影 / C3 参考圆被压扁 / C4 明暗带法线场。★ 搜索窗口按版式标定，换版式先改；找不到受检形体报 C0 失败 |
| `gate3d_rank.py` | **★ 挑图第一入口（v4.5）**：把「3D 感」当第一判据的批量入口 —— 对一批候选跑 `check_3d_generic.py`，按**渲染风格分** `grad_frac - edge_frac - max(limb,0)` 排序（三个量都不依赖版式），闸门结论单独一列；`--require-all` 有不过的就非零退出（交付档用）。★ `offcentre` 只当读数：它对板面没意义，实测会把带大渐变的深色海报排到干净图前面 |
| `axis_gate.py` | **★ 第七道闸门（v4.1）**：三轴物理 —— 轴名多重集 == IR 声明的坐标约定；**同一轴名的两次标注必须落在同一根轴杆的两端**（抓「一根轴两个名字」）；三轴方向两两 > 15°；不许第四个轴名。`--png` 走**无 OCR 字形识别**，位图阶段就能抓错标；`--svg` 与 `--png` 都给会互相对账。`X6`（板面 ↔ 三轴同一投影）只作读数 + 软警。★ **只给 `--png`（草图档，v4.5）**：X1/X2/X5 仍是硬判据，X3b/X4（轴杆几何）自动降级为读数 + 软警 —— 草图轴杆检测不稳，误杀不起 |
| `check_3d_generic.py` | **★ 第八道闸门（v4.1）**：图种无关的 3D 闸门 —— **不用硬编码窗**，主体与板面由像素自己找。3D0 主体 / 3D1 浅灰板面 >= 3% 画布 / 3D2 接触阴影 / 3D3 高光偏离几何中心 > 0.08 半轴。IR 声明无板面时 3D1/3D2 降级。★ 只认浅灰板面，深色/彩色板面会漏判 → `--expect-plane no` 只查 3D3 |
| `gates_selftest.py` | **★ 两道新闸门的回归标定表（v4.1）**：一条命令跑完 FAIL/PASS 对照，缺样本自动跳过 |
| `check_render_mode.py` | **★ 交付前「是不是 3D 明暗风」自检（v4.0）**：①[硬] 矢量层真有 `<gradient>` 吗 ②[参考] `ink_colors`（量的是细节密度+文字量，**不是**明暗渲染）③[硬] 有没有出成品 × 风格参考的**并排图** |
| `audit_refs.py` | **★ 历史对账（v4.0）**：扫全工作区 `calls.jsonl` 逐条过 `ref_guard`。★ 记录里的 `refs` 是 content+style 的**并集**，先 `split_refs()` 拆回两列再判，否则每条合规 render 都会被误判成 SAME_FILE |
| `bitmap_conformance.py` | **★★ 位图一致性闸门（v3.2）**：把**所选位图**和**成品**各量一遍架构几何（面板数、每个面板的上边界倾角 / 板左缘 x / 板左上角 y / 侧边界角、宽高比），超阈值 = **非零退出**。查的是**结果**（成品有没有照位图画），不是「你有没有抄旧脚本」——那查不出来 |
| `raster_to_vector.py` | **位图 → 矢量（临摹备用路径）**：逐像素描摹 + 混合文字（`--text-spec`）+ 语义归组（`--groups`） |
| `raster_to_vector_semantic.py` | **位图 → 语义分层的全矢量**（先理解再临摹）：真 `<text>`、物理元素图层树、误差可量化。库在 `scripts/raster_vector/`，用法见其 `README.md` |
| `ir_brief_audit.py` | **★ IR → 简报的无损体检**（哨兵法：字段没进简报 = IR 白写）。改 IR 格式 / 简报模板后必跑，可挂 CI |
| `ir_canvas.py` | **内部：IR 画布的**唯一**读取口**（规范位置 `composition.canvas` 优先，旧写法 `figure.canvas` 兜底）。修的是：8 份 IR 有 6 份的画布被静默丢弃 —— 简报照默认 1400×560 走、`gen_figure` 又按 1664×928 出，同一张图三个比例；而旧探针塞在 `figure.canvas` 下，体检照样绿 |
| `pick_best.py` | **★ 候选排序**：吃 `check_sketch.py --json` 的报告，按「硬伤 → 比例偏差 → 软警 → 构图保真」排序，只把人眼留给没有硬伤的。实测（UPC）：8 个 seed 只有 3 张合格 —— 以前那 5 张废图也要人眼看一遍 |
| `_console.py` | **内部：控制台编码兜底**。把 stdout/stderr 切 UTF-8 —— 中文 Windows 上 stdout 一旦被管道/重定向（agent、CI、`> log.txt`）就是 gbk，报告里的 ✅/⚠️ 编不出来 → `UnicodeEncodeError` 把脚本打在打印中途。**不影响交互式手敲**，所以只在自动化里炸。拷脚本（扁平布局）时必须一起拷 |
