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

### ★ 台阶边界 -> 亚像素等值线：`--spline`（v4.23，纯 CPU）

临摹层的几何是**可见像素轮廓**，边缘天然是 1 px 台阶。`svg_spline.py` 把「单连通大形体」
的轮廓换成光滑曲线，**只改边界、不动明暗**（明暗仍是临摹层的四分块）。

```bash
# 交给 raster_to_vector_semantic 一步做完（默认关）
python3 scripts/raster_to_vector_semantic.py fig.png -o fig.svg --no-text --spline
# 或对已有成品做后处理
python3 scripts/svg_spline.py --svg in.svg --png src.png --elmap elmap.npy --el-names "S1,N1,N2" -o out.svg [--method subpixel|vtracer]
```

- **默认 `--method subpixel`**：掩膜高斯软化（σ=1.4）→ `find_contours(0.5)` 取**亚像素**
  闭合轮廓 → 周期三次样条 → 按弧长每 8 px 一段转成 `C` 段。
  等值线落在**抗锯齿过渡带的 50% 中点**，也就是真实可见边缘上。
- `--method vtracer` 保留：对**二值**掩膜拟合，边界落在台阶**外沿**，面积系统性偏大
  （N1 +1.04%、N2 +0.75%），实测比等值线**更差** —— 只作为对照。
- 四道写盘前闸门：多连通不做、回渲染 IoU ≥ 0.95、**代价 = 段数 × 该组 path 数 ≤ 2e6**、
  图层组必须唯一（多面板同名元素明确跳过）。
- UPC 实测（1664×909，边界带 = 两核轮廓内外各 3 px / 7849 px）：

  | 版本 | 边界来源 | MAE | >32 | 边界带 MAE |
  |---|---|---:|---:|---:|
  | v4.21m | 1 px 台阶 | 1.279 | 1.12% | 16.607 |
  | v4.22 | vtracer 二值样条 | 1.287 | 1.12% | 18.094 |
  | **v4.23** | 亚像素等值线 | **1.275** | **1.10%** | **15.733** |

  ★ 判据（写在这里防止再犯）：**看「元素自身 MAE」，不看全图 MAE**。全图被大片平背景稀释 ——
  实测把细条元素 A1/P1/T1/B1 也套等值线，全图 MAE 1.274→1.248「变好」，但元素自身
  A1 6.40→6.84、T1 7.10→10.30 全都变差（只是裁掉了 1 px 描边外溢）—— 那是刷指标，不是改进。
  用 `svg_repro_check.py --elmap ... --el-names ...` 逐元素拆账。
  ★ 教训：**「更光滑」不等于「更准」**。vtracer 那一版我只看 8×
  放大觉得顺眼就宣布"更好"，实际边界带误差从 16.6 涨到 18.1。做这类判断必须报
  **边界带 MAE**（全图 MAE 被大片平背景稀释，看不出边界变差）。
- ★ 坑：vtracer 把图形**居中到原点**，真实位置在 `<path transform="translate(tx,ty)">` 里。
  只取 `d`、丢掉 transform，路径会整体错位并把画布涂满（实测 MAE 11.6、核整块消失）。
- ★ 坑：cairosvg 把 clip 路径**摊进每一条被裁的 path**。板 S1（512 段 × 8504 path）
  会让 PDF 从 2.68 MB 涨到几百 MB、渲染 >12 min，而它对 MAE 的贡献是 0.000 ——
  所以 `--max-cost` 会把它挡掉，这是有依据的取舍。

### ★ 复现度不能只看「像不像」：`svg_repro_check.py`（v4.21）

```bash
python3 scripts/svg_repro_check.py --svg fig.svg --png fig.png \
        [--elmap seg/elmap.npy --el-names A,B,...] [--json r.json] [--diff d.png]
```

四个读数一起看：`MAE`（会被大片平背景稀释）、`>8%`、`>32%`、`PSNR`；
给了 `--elmap` 就逐元素拆账 —— 总量变差时能直接看出是哪个元素变差。

同一张图实测（喷注淬火 1664×928，cairosvg 同分辨率回渲染）：

| 版本 | MAE | >32 |
|---|---|---|
| 旧成品 | 3.07 | 2.67% |
| 旧临摹（按颜色分层，96k path） | 2.32 | 1.57% |
| v4.21（语义分层 + 实测底色 + 0.25 接缝） | **1.64** | **0.33%** |

★ **两处隐藏的系统性误差**（不做这个读数就永远发现不了）：

1. 画布底色原来写死 `#ffffff`，生图模型的底其实是 `#fdfcfd` —— 没归进任何元素的背景像素
   整片偏 2~3 个色阶，MAE 白送 1.7。现在按位图量：边框环取初值 → 全图「离初值 ≤4 的低饱和
   像素」再求中位（第二遍是为了避开模型自带的暗角，四角比中间暗 3~5 级）。
2. 同色接缝描边（`SEAM`）让每块色块四周各外扩 sw/2 px；元素边界两侧颜色差大时
   （QGP 橙 vs 板灰）这半像素就是系统性偏色。实测 1.00 → MAE 2.39 / 0.50 → 1.87 /
   0.25 → 1.64 / 0 → 1.45；4× 放大下 0.25 已能盖住 1 设备像素的接缝（PDF 无纱窗），
   所以这张图用 `SEAM = {"*": 0.25}`。**细碎色块很多的图仍要 1.0**（那是堵 PDF 纱窗的
   标定值），这是按图标定的参数，不是全局最优。

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

### 4. 出图入口与 A→B→C→D 阶梯（v4.15）

- **A 档**：一句话（≤80 字符），**默认不带 `--ref`**；只作诊断，**不进交付链**。
- **出草图前**：把 IR 的**元素清单**（中文 5–10 行）贴给客户过目 / 加项，**客户点头才开跑**（v4.19）。
- **B 档**：A 的文字 + 面板序列 + 输出硬约束；**必须带 `--ref` 风格书**；**不给上一档的图**（L9）；不写“保留”措辞（B 只跑一轮）。
- **C 档 = 元素替换档**：必须给 **A、B 两张图**；简报必须写“把 A 档画得好的元素搬进来、替换 B 里对应的那一处”（L12）。
- **D 档 = 物理修正档**：必须给**紧邻上一档的图**；严格在上一张图上改，只补上一轮真画错的，**其余形状 / 质感 / 配色 / 视角都不许变**（L10/L11）。B 档不判 L10。
- **D 档的“错”必须来自上一轮 `check_sketch` 人工项里所有答“否”的硬物理，不是只写自己注意到的那两条**（v4.25）。写 D 简报前先逐条过 HP1–HP6；漏一条，模型就会按“其余原样保留”把它保住。实测 UPC：D 档只写 beam/b，黄色 QGP 椭圆被完整保留；D2 点名删除后才消失。
- **用了整幅风格参考图，就必须写泄漏黑名单**（v4.25）：B/C/D 简报里必须有 `【参考图自带、本图不要】` 一节，逐条点名风格图里的物理对象（如“参考图自带的黄色椭圆 QGP 火球 + 放射箭头，本图不要”）。只写“不要 QGP”不够——要点名它的形状/位置，否则模型会把它当风格抄进来。`ladder_gate.py` 的 **L14** 会硬判 D 档缺这一节。
- **整幅风格图带错误物理时，允许用同一本风格书抽出的“材质卡”当 `--ref`**（v4.25）：材质卡只保留材质/光照/渲染语言；L7 会报“风格图不一致”，用 `--ladder-waive "ref_is_material_card_from_same_stylebook"` 放行，理由写进交付说明。
- **L9**：B 给图 = 硬伤；C 缺 A 或 B = 硬伤；D 缺上一档 = 硬伤。**L7**：阶梯里第一个带 `refs` 的 rung 是风格锚点。
- 机械闸门：`ref_guard.py --run -- ...`（先查后调，查不过不烧 API 钱）；账本 `ladder.json`；`ladder_gate.py --selftest` 标定 L9/L12/L13。
- **3D 感是首要判据**；草图管“基础物理”（三轴一一对应、方向关系、b 横向错开），位图管“IR 齐全度 + 精修”。
- **选择权在客户**：`make_picker.py` → 客户点选 → `choice_gate.py --record --by client`；没有回执不许出成品位图。

---


## 路线 B：图像生成（速查；完整命令链见 `references/generate-flow.md`）

> **动手出图之前，先读 `references/generate-flow.md`。** 默认走这条路；本节只是 7 步骨架与硬约束，每一步的命令、参数、实测读数在下沉文件里。

1. **IR → 简报**：`ir_to_genbrief.py --stage sketch`。默认先走 `brief_lite.py --tier 0`（一句话 + 面板序列 + 输出硬约束），看图后 `--tier 1 --add 上一轮画错.md` 只补错的那几条（= 上一轮 `check_sketch` 人工项里所有答“否”的硬物理，不是只写注意到的）；完整规格书留给 A 类复现。
2. **出草图**：`gen_figure.py --stage sketch --ref <风格书> --seeds ...`；产物 `sketch_sN.png` + `calls.jsonl`。模型稳定画 1–2 px 外框，**别求它去掉**，用 `trim_border.py` 确定性地裁（两层外框加 `--bg 0.975`）。
3. **草图矢量化**：`sketch_to_vector.py ... --ocr`；每形体一个子层，人可直接改。
4. **闸口①**：`check_sketch.py --ir ...`。过闸后 `sketch_handoff.py` 交候选 → `make_picker.py` → `choice_gate.py` 收回执；客户改完用 `sketch_ingest.py` 灌回，**强制重过闸口①**。
5. **出成品位图**：`ir_to_genbrief.py --stage render` → `gen_figure.py --stage render --content-ref <构图依据> --ref <风格书>`。普通 render 的构图依据是选中的草图；**C 档给 A、B 两张，D 档给紧邻上一档一张**（L9）。草图**原样送**（`auto -> full`）；只有草图本身是扁平稿才加 `--content-ref-mode layout`。别把草图塞进 `--ref`。简报必须写「在上一张图的基础上改，别换掉画对的」；D 档只改列出的物理错误（L10/L13）；列之前先逐条过 HP1–HP6，并把上一轮 `check_sketch` 里答“否”的项全部写进增量清单。
   - `--ref` 只收风格书（`assets/t3-exemplars/`、`_T3精选/`）；`--content-ref` 只收手绘输入或本阶梯已登记的 rung；`assets/demos/**` 任何阶段不许当参考；同一张图不许同时占两个角色。
6. **闸口②**：`check_sketch.py --sketch <草图>` 再跑一次；再 `gate3d_rank.py --require-all`、`axis_gate.py`、`check_3d_generic.py`。
7. **位图 → 矢量**：固定三步 —— ① 客户确认的位图；② `raster_to_vector_semantic.py` 逐像素**临摹**（`<g data-element>` 语义层）；③ `trace_rebuild.py` **从临摹层重建**。**几何只来自临摹层**，禁止再走“颜色阈值 ∩ 包围盒”重抠（v37 教训）。
   - 默认交付 **③-B 光滑档**（`shade_smooth.py`）+ **③-A 对象档**；要“点一下 = 一个物理结构”加 `pick_layer.py`。
   - 文字必须真 `<text>`；边界用 `svg_spline.py --method subpixel`（默认，亚像素等值线），`vtracer` 只作对照。
   - 判好坏看**元素自身 MAE**，不看全图 MAE；cairosvg 不画 `<mask>`，验 MAE 用 Edge/Chrome。

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

> 停在"元素清单全中 + 物理无误"。**不追像素级复刻**——那会陷入无限调参。

---

## 按需参考（不要一次全读）

| 什么时候读 | 文件 |
|---|---|
| **判定任务 / 图型、写 IR、选后端、跑验证、走 A→B→C→D** | **`references/routing.md`** ★ |
| **走路线 B、出草图 / 位图、位图→矢量七步** | **`references/generate-flow.md`** ★ |
| 查完整脚本表 / 某个脚本干什么 | `references/scripts.md` |
| 写 IR 的字段细节 | `references/ir-spec.md` |
| **画 T3 示意图之前 / 图出来觉得"扁"** | **`references/3d-checklist.md`** ★ |
| 画 SVG、查图元、查技法 | `references/svg-cookbook.md` |
| 决定用哪个后端、为什么 | `references/tool-selection.md` |
| 风格量化、闭环修正 | `references/style-bench.md` |
| 遇到渲染异常 / 静默失败 | `references/gotchas.md` |
| **一张图要用多种工具** | `references/multi-tool.md` |
| **位图 → 矢量的四档 / amodal 补全 / 拾取层 / 光滑判据** | **`references/bitmap-to-vector.md`** ★ |
| 硬物理 vs 画法偏好的完整规则 | `references/physics-vs-style.md` |

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


## 脚本（索引；完整表见 `references/scripts.md`）

最常用的一条链：
`ir_to_genbrief.py` / `brief_lite.py` → `gen_figure.py` → `trim_border.py` → `check_sketch.py` → `sketch_to_vector.py` / `sketch_handoff.py` / `choice_gate.py` → `gate3d_rank.py` → `axis_gate.py` → `raster_to_vector_semantic.py` → `trace_rebuild.py` → `svg_spline.py` → `check_delivery.py`

- 生成与闸门：`gen_figure.py`、`ref_guard.py`、`ladder_gate.py`、`choice_gate.py`、`check_sketch.py`、`gate3d_rank.py`、`axis_gate.py`、`check_3d_generic.py`、`check_delivery.py`
- 位图 → 矢量：`raster_to_vector_semantic.py`、`trace_rebuild.py`、`svg_spline.py`、`shade_smooth.py`、`pick_layer.py`
- 诊断与返修：`check_render.py`、`compare_ref.py`、`style_bench.py`、`repair_brief.py`、`audit_composition.py`
- 其余（IR、拼版、复现、工具探测）见 `references/scripts.md`。
