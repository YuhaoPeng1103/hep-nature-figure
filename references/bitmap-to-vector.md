# 位图 → 矢量：四档固定流程、判据、被废弃的方法（v4.10 / ③-B 装配器 v4.11）

> **配套脚本**：`scripts/raster_to_vector_semantic.py`（② 临摹）· `scripts/trace_rebuild.py`（③-A 对象档）
> · `scripts/shade_smooth.py`（③-B 光滑档装配器）
> · `scripts/pick_layer.py`（④ 拾取层）· `scripts/pick_verify.py`（④ 验收）· `scripts/smooth_metric.py`（光滑判据）
> **配套文档**：`references/trace-rebuild.md`（v4.0 的三步原文）· `references/svg-cookbook.md`（矢量怎么画）
> · `references/3d-checklist.md`（3D 怎么立起来）· `references/gotchas.md`
> **来源**：2026-10-11 ~ 10-12「喷注淬火 JET-QUENCH-3D」第 7 ~ 12 轮返工。**下面每个数字都是实测的，没有估算。**

---

## 0. 一句话

**几何只来自第 ② 步的临摹层。** 第 ③ 步只做三件事：按元素**拟合**、按声明**补全**、把线稿**贴回**。
第 ④ 步再叠一层不可见的「每个物理结构一条闭合路径」，让**点一下 = 一个物理结构**。

```
① 位图（客户选定，唯一权威的外观）
      ↓  raster_to_vector_semantic.py
② 临摹（逐像素 + 语义图层：每个物理元素一个 <g data-element="...">）
      ↓  trace_rebuild.py（对象档）/ 逐行渐变网格（光滑档）
③ 重建（每个元素 = clipPath + 真渐变 + 线稿贴回）
      ↓  pick_layer.py（+ amodal 补全产出的 _sil.json）
④ 拾取层（每结构一条 fill-opacity="0" pointer-events="all" 的闭合路径）
```

---

## 1. 四档：什么时候用哪个

| 档 | 做什么 | 产物 | 什么时候用 | 验收 |
|---|---|---|---|---|
| **① 位图** | 生图模型出图、客户选定 | `gen/chosen.png` | 总是 | 闸口②（物理对） |
| **② 临摹** | 逐像素 + 语义分层 | `<stem>_trace.svg` | **总是**（③ 的几何只能从这里来） | 回渲染 MAE |
| **③-A 对象档** | 把每个元素重做成「可改形状/改色」 | `<stem>_obj.svg`（几百条 path） | 客户要改几何 / 配色时 | **逐元素**看，不看整幅 MAE |
| **③-B 光滑档** | 逐行自适应渐变网格（`shade_smooth.py`） | `<stem>_mesh.svg`（几万条 path） | **默认交付**：放大不糊 | `smooth_metric.py` |
| **④ 拾取层** | 每结构一条不可见闭合路径 | `<stem>_mesh_pick.svg` | 要「点一下 = 一个物理结构」 | `pick_verify.py` |

> ★ **③-A 与 ③-B 是两个档，不是同一个文件**：`_mesh.svg` 保真 + 光滑但难改形状；
> `_obj.svg` 能改形状但天生不平滑。**两个都交**，说明书里写清哪个干什么。

---

## 2. ② 临摹：几何的唯一来源（为什么不能重新抠）

老路是「颜色谓词 ∩ 包围盒」，实测的两种翻车：

| 现象 | 根因 |
|---|---|
| `a-nucleus-far` 的底边被**切平** | 手写的框 `(575,35,810,255)` 比真 bbox `(586,46,800,306)` 矮，底边被裁掉 |
| 「板下淡出」成了一条**卷曲细带** | 那片区域不是单连通的，`findContours` 在非单连通掩膜上描出来就是一条飘带 |

改成**只从 `<g data-element>` 的掩膜取几何**之后，三个体积的 MAE：

| 版本 | 几何来源 | MAE |
|---|---|---|
| v35 | 颜色阈值 | 2.49 |
| v37 | 颜色阈值 ∩ 包围盒 | 5.28 |
| **v38** | **`<g data-element>` 掩膜** | **1.95** |

**回归自检基线**：`trace_rebuild.py` 在 v38 的输入上重跑，三个体积的像素数
**30044 / 25884 / 28268** 应逐一复现，整图 **MAE = 1.946**。换代码先跑这条。

### 产物规格（③ 只认这个）

- 每个物理元素包在**一个带 `id` 的 `<g>`** 里，`data-element="<物理名>"`；
- `<g>` 内部的形状是 `RECT` 式**碎矩形** path（`M..h..v..h-z`）—— 这是 `raster_to_vector_semantic.py` 的输出格式；
- 一个元素内部可以有**很多条**碎矩形（一个元素几百条是正常的）。

---

## 3. ③-A 对象档：每个元素重做成三件东西

| # | 产出 | 干什么 |
|---|---|---|
| **(a)** | `clipPath` | 该元素在临摹图里的**精确可见轮廓** —— 含**被其它元素遮挡后**的形状（"临摹"相对"重画"最大的优势：位图里的遮挡关系免费） |
| **(b)** | 真渐变 | 颜色场从原图拟合；掩膜先按内缩量腐蚀、再按 σ 平滑，纵向再做一次高斯平滑消掉带间噪声 |
| **(c)** | 线稿逐像素保留 | 网格解释不了的描边 / 切割线 / **穿过球面的格线**，原样照抄 |

判"哪些碎矩形要留"用**残差**：`dev = |模型 − 原图|`，渐变铺不出来的那部分像素，线稿一律留下。
其余元素（板、三轴、文字、箭头、虚线、别的面板）**整段照抄**临摹图。

### ★ 「整幅 MAE」不是判据（实测反例）

| 运行 | 梯度预算 | 对象数 | 整幅 MAE | 代价 |
|---|---|---|---|---|
| obj3 | 8 层 / 16 stop | 10 | 6.418 | 正常 |
| obj4 | **12 层 / 24 stop** | 10 | **5.984**（更低！） | ★ 把**三轴吃成了渐变**：z 轴没有箭头、x 轴只剩短桩 |
| **obj5（采用）** | 12 层 / 16 stop | 10 | 6.418 | 三轴正常 |

⇒ **"整幅 MAE 更低"不等于"更好"**。必须逐元素看（靠 `--iso` 那种逐元素出图）。

---

## 4. ③-B 光滑档（默认交付）：逐行自适应渐变网格（`scripts/shade_smooth.py`）

- 每个元素一条 `clipPath`（几何仍来自 ②）；
- 网格 = 每 `BAND` 像素一条 `linearGradient`（`NSTOP` 个 stop）+ 纵向 `mask`；
- **不引 SVG 滤镜**（`feGaussianBlur` / `feDropShadow` 都不许）—— 引了 PDF 就不是纯矢量、文字也提不出来。

### 判据：`smooth_metric.py`（"放大会不会看出台阶"是可测的）

只在**位图本身就是平滑**的像素上量（相邻步长 ≤ 3，且行、列两个方向都满足），再内缩 7 px；
量 A 与 B 的**相邻像素最大通道差**。实测（喷注淬火 1× 位图，火球面 40662 px）：

| 输入 | mean \|d\| | p99 | **>8 占比** | max |
|---|---|---|---|---|
| 位图自己（对照，测的是它自己的相邻步长） | 1.21 | 3 | 0.000 | 3 |
| **本 skill 光滑档** | **1.19** | **3** | **0.000** | 4 |
| VTracer 0.6.15（默认参数） | 43.67 | 84 | **0.990** | 88 |

**`shade_smooth.py` 回归基线**（喷注淬火 `chosen_x2.png` + `jet_q_trace.svg`，3328×1818，
同一把尺子、同一火球 ROI，64560 px）：本脚本 **mean 1.16 / p99 3 / >8 0.000**，
已交付的 `jet_q_mesh.svg` **1.16 / 3 / 0.000**，位图自己 **1.19 / 3 / 0.000** —— 三者等价。
（本脚本成品 20.3 MB，交付件 34.6 MB。）

⇒ 光滑档在这块区域上与**位图自己的读数无法区分**（1.19 vs 1.21）；VTracer 把柔渐变压成了平色块。
（VTracer 的绝对值随它的旋钮变：`color_precision` / `layer_difference` 调细后会好看很多 ——
**要对照就同一区域、同一批参数比**，别跨配置比数字。）

### ★★ 环境事实：**cairosvg 不画 `<mask>`**

光滑档带 `mask`。用 cairosvg 渲染会**把旁衬层整块丢掉**，于是"成品 vs 位图"的 MAE 全错。
渲染这条线**必须用 Edge / Chrome**（headless 截图），PDF 用 Edge 打印 → 再光栅化。
看到"明明写了却像没生效"时，先怀疑渲染器，不要怀疑 SVG。

---

## 5. ④ 拾取层：「点一下 = 一个物理结构」

### 为什么需要

③ 的成品内部是**几百到几万条 `<path>`**（碎矩形 / 逐行渐变带）。一次点击命中的是**那一条 path**，
不是物理对象 —— 于是"点一下球，选中的是一段渐变带"。

### 做法（`scripts/pick_layer.py`）

- 在 `<svg>` 最后面加 `<g id="pick">`，里面每个物理结构一条**闭合路径**，
  `fill-opacity="0" pointer-events="all"`：**什么都不画，但接管点击**；
- ★ **一次点击由最后画的那条路径决定** ⇒ 顺序必须 = 图里的**真实遮挡**（back → front）。
  `pick_verify.py` 的探针表就是拿来验这件事的；
- ★ **子物体**：`--sub` 传 `{"element": {"paths": [...]}}`（如两个 Pb 核里逐核子一条路径）。
  子路径画在**父级之后** ⇒ 点球选球、点没被切开的区域选核。位图把背排的球画在一起、没给边界时，
  **父级就是兜底**，保证不存在"点不到"的地方。

### 验收（`scripts/pick_verify.py`，三张表）

```
element          pick px  layer px covered  extra   empty   unc smooth unc text
plate            2160131   1168017 0.892    0.518   0.004   0.61      0.39
nucleus-A         138243    192221 0.608    0.155   0.039   0.18      0.82
fireball          659903    475576 1.000    0.279   0.000   0.12      0.88
axes                9487      9430 0.960    0.046   0.046   0.00      1.00
```

- `covered` = 这个结构的可见像素里有多少能点到它自己；
- `extra` = 拾取区里是**补出来的**（被遮住）那一份；
- `empty` = 点在"图里什么都没有"的地方（越低越好）；
- `unc smooth / text` = 没被覆盖的那部分层，到底是**落影/柔边**还是**纹理/格线** ——
  **这一列才是判"该不该再补"的依据**。例：`nucleus-A` 的 `covered` 只有 0.608，
  但那 39% 里 82% 是**纹理**（核投在板上的影子 + 板的暗边带被临摹层算进了核），**不是漏球**。
- 探针表：每个元素取「可见体」「被遮住处」各一点，实测**位图上是甚么 vs 点一下选中甚么**；
  `probes that do NOT do what is claimed = 0` 才算过。有意为之的例外写进 `--expect`。

---

## 6. amodal 补全：声明式策略（本法的关键一步）

**为什么必须补**：位图只画了**可见**的部分。"点一下 = 一个物理结构"要求选中的是**完整**的物体。
补全 = 把被遮住 / 被抗锯齿吃掉的那一块按**声明的策略**补回来。

策略**只能按 IR 角色声明**（不许用数值判据自动挑，见 §7），每条都要有实测读数：

| 策略 | 用在什么 | 怎么算 | 实测读数 |
|---|---|---|---|
| `none` | 碎笔画（喷注条 / 星芒 / 三轴） | 不补，就是可见轮廓 | —— |
| `hull` | 一个凸体积（热芯 / 束流箭头） | 最大连通域的凸包 | 束流箭头 25658 → 43449 px（补回被球挡住的那一截） |
| `union_close` | **QGP 火球** | 50% 覆盖颜色门 → `open(12)` → `close(20)` → ∪层 → `fill_holes` → `hull` | **659736 px**（位图化 658519，**0.998**） |
| `ballfield` | **Pb 核（球簇）** | 带通纹理超水平集（**不做凸包**）→ `open(41)` → `close(31)` → `fill_holes` → 与层重叠最大的连通域；再**逐核子 watershed** | 核 A **19** 条（16 单球 + 3 合并块）/ 核 B **18** 条；拾取区 138243 / 125234 px |
| `edgequad` | 板（一个平面） | 在位图上**量** 4 条边（沿 4 个方向扫边界跑长）→ 求交得 4 个角 | 远角 `(2045.7, 228.5)`；补回 992441 px |
| `cyan` | 青色逃逸喷注 | 颜色门 → `fill`（**不 hull**：要保住箭头的凹口） | 40207 → 40432 px |
| `skip` | 残差类（辉光 + 弧线 + 抗锯齿边） | 不是结构，不进拾取层 | —— |

### ★ 带通纹理（`ballfield` 的核心，为什么必须带通）

判"哪里是球簇"不能直接用窗口 sd：核投在板上的**落影** sd 实测 **7.8**，`sd>5` 会把影子一起吞进来
（多 23 kpx，ymax 1326 vs 球堆 1193）。**先减掉大尺度亮度起伏再做局部 sd**（带通）就分开了：

| 区域 | 带通后的读数 |
|---|---|
| 球堆 | 中位 **15.3**（p10/p50/p90 = 6.1 / 15.9 / 29.8） |
| 核 A / 核 B 的落影 | **2.2 / 1.3** |
| 空板 | **0.7** |

### ★ 逐核子切分

`watershed(亮度, markers)`，markers = 亮度高光峰（`maximum_filter` + 距离变换门）。
旋钮实测扫描：`sep 0.85r + gate 0.35r` → 核 A/B 各 **21** 个种子；`sep 1.05r + gate 0.50r` → 19/17（会漏背排球）。
**背排的球是位图自己就画在一起的**（没给边界），合并块由**父级兜底**，不是 bug。

---

## 7. 被废弃的方法（留痕：它们是**错的**，不是"不够好"）

| 判据 / 方法 | 结论 |
|---|---|
| **颜色阈值 ∩ 包围盒**重抠几何 | 底边被切平 / 细带飘带（§2 实测） |
| `fill = visible / hull >= 0.55` 判"够不够凸" | **错**：把「被遮挡形成的洞」算成「非凸」，于是把整块**板**和 `nucleus-A` 一起误拒 |
| `hull & ~mask & ~others` 自动挑补全方式 | 板 0.103 / 核B 0.101 偏高 —— 追下去发现**层的 hull 本身就是错的**（核B 的 hull 把右侧空白月牙包了进来）⇒ **本图上任何"自动挑补全方式"的数值判据都不可用**，只能声明 + 逐条实测 |
| 21 px 窗口 `sd > 5` 找球簇 | **被落影骗过**（落影 sd 7.8）⇒ 必须**带通**（§6） |
| 任何形式的**凸包**用于球堆 | 一定跨过整堆 ⇒ 把 Pb 箭头头和一片空板圈进来（xmin 449 vs 球的 531） |
| 椭圆「读图」补全核（目测圆心/半径） | 盖住整个核、漏 37% 层 ⇒ 点球选中核 |
| `hull(layer)` 补全火球 | 内凹缺口，且 3 个方向上比可见橙边**小 4–30 px** |
| 火球补全**不做 `close`** | 橙色门被灰色喷注条切成 2 块 + 掐点 ⇒ 交付路径只剩 **328419 / 521801 px** |
| **整幅 MAE** 当选型判据 | obj4 反例：MAE 更低，但把三轴吃成了渐变（§3） |
| 用 `cairosvg` 渲染带 `mask` 的成品 | 旁衬层整块丢（§4） |

---

## 8. 与开源 / 商业工具的差别（数出来的，不是印象）

| | 语义从哪来 | 有没有**补全** | 有没有真渐变 | 能不能"点一下 = 一个物体" |
|---|---|---|---|---|
| VTracer / potrace | **无**（颜色量化 + 轮廓拟合） | 无 | 无（只能平色块） | ❌（0 个 `data-element`） |
| Vectorizer.AI | **无**（"shape" = 几何图元，"layer" = **按颜色**分层） | 无 | —— | ❌（按颜色，不按物体） |
| AmodalSVG / LayerSVG / SAMVG | VLM / SAM 从像素**推断** | 有 | 有 | ✅ |
| **本 skill** | **IR 里人工声明的物理角色** + 逐条实测 | 有（声明式策略，§6） | 有 | ✅ |

⇒ 「语义分割」这个动作在前两行**根本没有**，在第三、四行**都有**，区别在**语义的来源**：
它们是模型推断，我们是**可审计的声明**。

---

## 9. 逐字可跑（以喷注淬火图为例）

```bash
# ① 位图（客户选定）
#     fig_jet_3d/gen/chosen_x2.png   3328x1818

# ② 临摹（几何的唯一来源）
python scripts/raster_to_vector_semantic.py fig_jet_3d/gen/chosen_x2.png \
       -o fig_jet_3d/build/jet_q_trace.svg

# ③-A 对象档（可改形状）
python build/objfit3.py --klayers 12 --nstops 16 \
       --sil build/mesh/_sil.json --out out/jet_q_obj.svg

# ③-B 光滑档（默认交付）—— 逐行渐变网格 + 纵向 mask，一条命令（几何仍只从临摹层来）
python scripts/shade_smooth.py --src gen/chosen_x2.png \
       --trace <第②步的临摹.svg> --stem jet_q --outdir out --size 3328x1818
#     回渲染用 Edge / Chrome（带 <mask>，cairosvg 会丢旁衬层）；判据见 smooth_metric.py

# ④ 拾取层 + 验收
python scripts/pick_layer.py out/jet_q_mesh.svg \
       --sil build/mesh/_sil.json --sub build/mesh/_nuc_balls.json \
       -o out/jet_q_mesh_pick.svg
python scripts/pick_verify.py --sil build/mesh/_sil.json --vis build/mesh/_vis_trace.npz \
       --ref gen/chosen_x2.png --size 3328x1818 --outdir out --stem jet_q \
       --expect '{"fireball-core":"fireball"}' \
       --nuc-balls build/mesh/_nuc_balls.json --json build/_pick_coverage.json

# 光滑判据
python scripts/smooth_metric.py gen/chosen_x2.png out/jet_q_mesh_render.png \
       --mask build/mesh/_vis_trace.npz:fireball

# 闸门（缺一不可）
python scripts/axis_gate.py --svg out/jet_q_obj.svg --png gen/chosen.png --ir ir/*.ir.yaml
python scripts/check_3d_generic.py gen/chosen.png --ir ir/*.ir.yaml
python scripts/check_render_mode.py out/jet_q_obj.svg
```

★ **`_sil.json` 是 ③ 与 ④ 之间的接口**：`{"element": "<path d>", ...}`，顺序 = back → front。
子物体另出一份 `_nuc_balls.json`。这两份文件就是「按物理结构」的全部秘密。

---

## 10. 交付强制项（这一条线专属）

1. **`smooth_metric.py` 读数**（交付说明书里照抄）：成品 vs 位图在**平滑像素**上的 mean / p99 / >8 占比。
2. **拾取层看不见的证明**：成品与带拾取层的成品**各渲染一次、比 MD5**（必须 Edge/Chrome）——
   必须**逐字节相同**。
3. **`pick_verify.py` 三张表**：覆盖表 / 探针表 / 子物体表；`probes that do NOT do what is claimed = 0`。
4. **`位图 | 临摹 | 重建` 三联图**：让"重建是不是还像位图"5 秒内可判。
5. 与风格参考的**并排对比图**（`scripts/compare_ref.py`，技能第 5 步原文要求）。
6. 交付说明书里写清：哪一档是默认交付、哪一档可改形状、哪些元素是 `none`（不补）以及为什么。
