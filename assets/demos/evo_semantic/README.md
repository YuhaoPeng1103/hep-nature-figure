# 形变核 → 火球（四阶段演化链）：手绘草图 -> 期刊图（跑通的完整算例 #3）

非中心/形变重离子碰撞的**四阶段演化链**示意图（单面板）。走 SKILL.md 的**默认路线③**：

**IR -> 约束简报 -> 草图（矢量化输出）-> 闸口① -> 成品位图（草图 + 风格双参考）
-> 闸口② -> 语义临摹成矢量 -> 三道门禁**

比 1/2 号算例多出来的那件事：**「真 `<gradient>` 到底帮不帮忙」第一次被量出来了 ——
不帮**。下面那张 A/B 表是本算例最重要的产出，`sweep.py` 可以一键复跑
（见 `CHANGELOG.md` v2.6.5）。

## 物理内容

- 阶段 1：**形变**核（长椭球不是球）+ 核内 3 个游离核子小球。
- 阶段 2：**量子涨落** = 同一个核在**不同取向**上的叠加 -> 三个相互重叠的椭圆。
- 阶段 3：两核**部分重叠**相撞，重叠区（参与者核物质）= 偏暖的竖直透镜。
- 阶段 4：**QGP 火球**（橙红径向辉光）+ 火球内 4 个相互重叠的核子球。
- 三个阶段箭头全部向右；冷（灰白，饱和 0.03~0.07）/ 热（橙红，饱和 0.84）用饱和度分开。

## 文件

| 文件 | 作用 |
|---|---|
| `brief_sketch.md` / `brief_render.md` | 两步生图的约束简报（`ir_to_genbrief.py` 从 IR 生成） |
| `sketch_s7.svg` | **草图的矢量化输出**（2075 `<path>` / 7 `<text>` / 0 `<image>`，1.13 MB） |
| `src_render.png` | 选中并裁过外框的成品位图，1662x925（qwen-image-3.0，seed 31） |
| `words_render31.txt` | 手工词表 5 条（**源图 2x 坐标**） |
| `panels_evo.py` | 版式/元素表：1 面板 + 9 元素 + 3 组 SPLIT（`GRADIENTS` 已实测置空） |
| `sweep_panels.py` / `sweep_cases.json` / `sweep.py` | A/B 实验台：真渐变开/关 × 调色板粗细 |
| `cmp_preview.png` | 上＝成品位图，下＝交付矢量回渲染 |
| `measure_stages.py` | 四阶段几何/颜色量测（闸口人答题出数字用） |
| `evo_edit.svg` | ★ **可编辑版**：541 `<path>`（含真 `<radialGradient>`/`<linearGradient>`），1.84 MB —— 每个物理元素 = 1 条 body（基色/真渐变）+ 少量黑/白明暗层，**能整体改一个物理色块** |
| `evo_edit_layers.md` | 可编辑版图层清单（元素行会标 `+ 基色xN + 明度层` 或 `+ 真X渐变 body + 明度层`） |
| `cmp_edit_pdf.png` | 可编辑版 PDF 回渲染 vs 成品位图 |
| `eval_svg.py` | 拿同一套指标（MAE/贴边比/path/体积）批量给 SVG 打分 |

IR 在 `assets/ir/sketch7_deformed_to_fireball.ir.yaml`。

## 命令

```bash
S=scripts
# (1) 生图（key 用你自己的：$DASHSCOPE_API_KEY；qwen-image-* 才支持 --ref）
python3 $S/gen_figure.py --brief brief_sketch.md --stage sketch \
    --content-ref hand_sketch_controlled.png --ref _T3精选/T3-02_....png \
    --seeds 5,7,9 --outdir gen/
python3 $S/sketch_to_vector.py gen/sketch_s7.png -o gen/sketch_s7.svg --ocr   # 草图矢量化（人可改）
python3 $S/trim_border.py gen/sketch_s7.png -o gen/sketch_s7_clean.png
python3 $S/check_sketch.py gen/sketch_s7_clean.png --ir assets/ir/sketch7_....ir.yaml   # 闸口①
python3 $S/gen_figure.py --brief brief_render.md --stage render \
    --content-ref gen/sketch_s7_clean.png --ref _T3精选/T3-02_....png \
    --seeds 22,31 --outdir gen/
python3 $S/trim_border.py gen/render_s31.png -o gen/render_s31_clean.png --bg 0.975  # 浅灰外框
python3 $S/check_sketch.py gen/render_s31_clean.png --ir assets/ir/sketch7_....ir.yaml  # 闸口②

# (2) 语义临摹（本算例交付参数：--q 0 不量化 + --R 5）
python3 $S/raster_to_vector_semantic.py src_render.png -o evo.svg \
    --words words_render31.txt --panels panels_evo.py \
    --W 1662 --R 5 --K 7 --q 0 --legend evo_layers.md --check

# (3) 出 PDF（cairosvg 对大 SVG 会 OOM，用 Edge）@page = 183x102 mm
msedge.exe --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf=$PWD/evo.pdf "file://$PWD/evo.wrap.html"

# (4) 门禁
python3 $S/check_delivery.py evo.pdf --svg evo.svg
python3 $S/audit_composition.py evo.pdf
python3 $S/pdf_roundtrip.py evo.pdf --src src_render.png -c cmp_pdf.png

# (5) A/B 实验台（真渐变到底帮不帮忙）
python3 $S/../assets/demos/evo_semantic/sweep.py --src src_render.png \
    --words words_render31.txt --panels sweep_panels.py \
    --cases sweep_cases.json --outdir gen/
```

## 实测

```
闸口①（草图）  宽高比 1.80 vs IR 1.79 ✅ | 9 格有内容 ✅ | 人答 7/7
闸口②（成品）  宽高比 1.80 vs IR 1.79 ✅ | 9 格有内容 ✅ | 人答 7/7
  阶段横向中心 167/583/1037/1493 | 3 箭头全向右 | 阶段3 交叠 83px | 饱和度 0.034/0.029/0.072/0.838
参考图照抄自检（calls.jsonl 的 ref_sim，判据 0.85）
  sketch s5/s7/s9 = 0.134/0.086/0.109 | render s22/s31 = 0.091/0.087 -> 全部 ok
临摹自检  整幅 MAE 0.626 | >8 0.74% | >32 0.45% | PSNR 29.73 dB
          31005 <path> | 5 <text> | 0 <image> | 3.99 MB
PDF 回渲染 MAE 1.297 (MAEmax 1.535) | >8 3.71% | >32 0.87% | PSNR 28.27 dB
交付门禁  evo.pdf 183x102 mm | 矢量指令 31006 | 嵌入位图 0 | 可提取文字 60 字符 | 最小字号 9.8 pt -> 通过
构图审计  文字-文字重叠 0 | 线条穿文字 0 | 出界贴边 0 | 留白 0-of-9 -> 通过
```

## ★ 真 `<gradient>` 帮不帮忙：不帮（本算例的核心结论）

| 用例 | R | --q | 真渐变 | MAE | MAEmax | >8% | 贴边比 | path | 体积 |
|---|---|---|---|---|---|---|---|---|---|
| **C（交付）** | 5 | **0** | 全关 | **0.626** | 0.698 | **0.74%** | 0.62 | 31005 | 3.99 MB |
| B | 5 | 32 | 全关 | 0.880 | 1.048 | 0.75% | 1.02 | 2552 | 1.80 MB |
| E | 5 | 32 | 只火球 | 0.886 | 1.084 | 1.07% | 1.12 | 2552 | 1.79 MB |
| A | 5 | 32 | 全开 | 1.016 | 1.213 | 2.00% | 1.39 | 2552 | 1.78 MB |
| D（第一版） | 10 | 16 | 全开 | 1.195 | 1.508 | 2.11% | 1.48 | 934 | 1.22 MB |

- `MAE` = 通道平均差（同 `--check` 定义）；`MAEmax` = 最大通道差（更严）。
- `贴边比` = 源图本来就平滑处，复现图 |梯度| ÷ 源图同处 |梯度|。>1 = 比源图更花。
- 机理：渐变形状画**模型色**（残差 5.9~8.6 级），留下的台阶块画**原图色**，
  交界处多一圈硬边；模型误差是低频的 -> 球面成片"斑块"。
  **人眼对平色区里的低频偏差比细碎噪声敏感得多** —— 所以"更平滑的模型"反而更难看。
- 根因是**调色板量化**（q=16 每通道跳 17 级）。`--q 0` 不量化 + R=5 时四叉树自己
  就把渐变追平了（贴边比 0.62×源图），`<gradient>` 多余。代价是 31005 path / 3.99 MB。
- `gradfit.py` 这条能力保留：只在**必须**用粗调色板（`--q <= 16`）救地板色阶时，
  才在 `panels.py` 里按元素打开 `GRADIENTS`。

## 12 个物理元素（图层树 panel -> element -> path）

`background` / `stage1-nucleus` / `stage1-nucleons` / `stage2-fluctuations` /
`stage3-nucleus-A` / `stage3-nucleus-B` / `stage3-overlap` / `stage4-fireball` /
`stage4-nucleons` / `arrow-1` / `arrow-2` / `arrow-3`。

后 3 个（核子/透镜）**只写在 `SPLIT`**：它们整块嵌在"兄弟"元素框内部，而 `element_of`
按连通域 bbox 算 IoU，穿过小框的**本体网格细线**（bbox 又长又扁）会被抢走（实测 3~4 条）。

## 这张图踩到 / 修掉的问题（详见 CHANGELOG v2.6.5）

1. **IR 里把三个箭头的 x 写成列表** -> `f"{x:.2f}"` 抛 TypeError，**整个简报生成崩掉**
   （`ir_to_genbrief.py`：新增 `_fmt_num()`，列表排成 `[0.17, 0.39, 0.66]`；
   `composition.layout` 是列表时也逐条排版）。
2. **单个 seed 网络抖动打断整批**（seed 7 撞 TimeoutError -> traceback 退出，
   seed 9 根本没跑、已出的 seed 5 也没进 `calls.jsonl`）-> 逐 seed 失败重试 1 次、
   两次都败记 `ok=False` 继续（`gen_figure.py`）。
3. **外框是两层**（1px 深线 + 1px 浅灰线 lum 244~249），默认 `BG=0.94` 只认深线 ->
   `trim_border.py` 新增 `--bg`（浅灰框用 0.975）。
4. **cairosvg 忽略径向渐变的 `gradientTransform`** —— 200x200 对照图里
   `matrix(.005 0 0 .01 100 100)` 与不带 transform 渲染**逐像素相同**（渐变中心没动、
   整块填成最外档颜色）-> `gradfit.py` 的 aradial 改成 `<g transform>` 包形状 +
   局部坐标系的圆 radialGradient。
5. **浅色球面的网格线只比底色暗 30~50 级** -> 「块心 + 颜色容差」丢台阶块会把网格线
   一起丢（断成虚线）-> 丢块判据改成**逐像素**「整块 ≥97% 在 dropmask 内」+
   **细条（min(w,h)<3）一律不丢**。
6. **`--elmap` 把 `_elem_table.txt` 落在 cwd** -> 改成跟着 `out_png` 走
   （否则会覆盖别的图的同名文件）。

## 可编辑版 `evo_edit.svg`（v2.6.6）：为什么需要它

逐像素临摹的产物**结构上必然**是「一种颜色一条 `<path>`」。数交付版 `evo.svg` 的元素内部：

| 元素 | `<path>` | 不同 fill |
|---|---|---|
| `stage1-nucleus` | 5162 | 5162 |
| `stage4-fireball` | 6696 | 6696 |
| `stage3-overlap` | 1613 | 1613 |

path 数 = 颜色数 —— **一条同色都并不到一起**。图层按物理元素分了 ✅，但元素内部是
颜色集合：改色只能一条条改，`Select > Same > Fill Color` 也救不了（跨元素同灰/白会一起变）。
`--q 32` 只把 6696 降到 693，结构没变。

`--shade`（`scripts/raster_vector/shade.py`）把元素重写成
「1 条基色块 / 1 条真渐变 body + 若干条 `fill-opacity` 明暗层」。明暗层是黑/白、
**不含颜色**，所以改基色块的 fill 时整个元素的明暗关系自动跟着走。

| 交付 | 结构 | `<path>` | 体积 | MAE | >8% | 贴边比 | PDF 回渲染 MAE |
|---|---|---|---|---|---|---|---|
| `evo.svg` 忠实版 | 逐色临摹 | 31005 | 3.99 MB | **0.626** | 0.74% | 0.62 | 1.297 |
| `evo_edit.svg` 可编辑版 | 基色/真渐变 + 明暗层 | **541** | 1.84 MB | 0.919 | 2.59% | 0.60 | 1.287 |

逐元素：`stage1-nucleus` 5162→34、`stage2-fluctuations` 10884→31、
`stage3-nucleus-A` 4395→35、`stage3-nucleus-B` 2185→22、
`stage4-fireball` 6696→28（真 `radialGradient`）、`stage4-nucleons` 4338→16、
`stage3-overlap` 1613→19（真 `linearGradient`）、`arrow-1/2/3` →26/31/31。

★ **径向渐变必须走真渐变 body**：用「平涂基色 + N 档明度层」近似时，每一档会沿等半径
连成一个**环** —— 16 档实测火球球面上是肉眼可见的同心色环（就是最忌的"色阶退化"）。
模型选型用**渐变本身的残差**（不是"渐变+明度层"的残差：后者按色块中心的预测色补，
大色块横跨 ramp 时块内均值 ≠ 块心预测值，补出来是一块块斑，实测形变核上出现明显方块）。

参数取舍（都实测）：`auto:16:1` 541 path / MAE 0.919；`auto:128:1` 2086 / 0.820；
`auto:16:0`（关真渐变）541 但火球出色环。

```bash
python3 $S/raster_to_vector_semantic.py src_render.png -o evo_edit.svg \
    --words words_render31.txt --panels panels_evo.py \
    --W 1662 --R 5 --K 7 --q 0 --legend evo_edit_layers.md --check
# 或直接给参数：--shade auto:16:1   （k:levels:grad；SHADING 也写在 panels_evo.py 里）
```

## 已知偏差（不掩饰）

1. 阶段 1 的标签「deformed nucleus」**是补的** —— 原手绘草图没有文字标签。
2. 草图底部英文说明不是图的一部分，未画入；也没加 (a)(b) 面板字母。
3. 文字是重排的 Arial，字形不可能逐像素重合（`>8` 的 0.74% 基本都在文字与描边上）。
4. 元素框 / SPLIT 判据是**这一张位图**量出来的，换 seed 换构图要重量。