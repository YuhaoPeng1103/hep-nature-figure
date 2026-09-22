# raster_vector —— 位图 → 语义分层的全矢量 SVG

> 与「像素描摹」的根本差别：**先理解，再临摹**。
> 描摹不认识字、不认识语义、把渐变压成色阶；本包把文字做成真 `<text>`，
> 把图形按**物理元素**分组，并且误差可量化（MAE / PSNR，能过验收数字）。

## 流水线

```
源位图 ──┬─ 文字：OCR 词表 ── labels.py ── 与成品同渲染器(cairo)逐词对齐 ── 真 <text>
         ├─ 图形：quadtree 平色块 ── 严格不相交的矩形
         ├─ 元素：elements.py 自动切形状 + panels.py 的 ELEMENTS 给名字
         └─ 组装：groupvec.py ── SVG + 图层清单(.json/.md) + 自检图
```

产出图层树（Illustrator 图层面板 / Inkscape 子图层都能按名字点选）：

```
figure
└─ c1                       data-role="schematic"   ← 面板
   ├─ c1-medium-tube        data-label="Hydrodynamic expansion (medium tube)"  ← 物理元素
   │  ├─ c1-medium-tube-ltorange   data-family=...    ← 颜色族
   │  │  └─ <path data-color="#fcf0de" data-px="..."/>
   │  └─ …
   ├─ c1-nucleus-deformed / c1-nucleus-spectator / c1-core-sphere
   ├─ c1-slice-ellipse / c1-jets / c1-momentum-arrow / c1-connector-arrow
   ├─ c1-background
   └─ c1-text               ← 可编辑的真 <text>（font-family 单值，见下）
```

## 必须先准备的两样东西

| 输入 | 说明 | 怎么来 |
|---|---|---|
| `--words words.txt` | `x y w h text`，Tab 分隔，**源图 2 倍图**坐标 | `ocr_words.ps1`（Windows.Media.Ocr）。没有就 `--no-text` |
| `--panels panels.py` | 这张图的 `CELLS`（面板框）/ `ELEMENTS`（元素框+颜色条件）/ `SPLIT` | 照 `panels.py`（T3-01 示例）改 |

**这两张表是每张图各不相同的** —— 自动切分只负责"形状"，
"这块叫什么物理名字"必须人来写。这也是它有别于纯自动描摹的地方。

## 实测指标（T3-01 Jia2026 Fig.1，1200×1133）

| 指标 | 值 |
|---|---|
| 整图 MAE / PSNR | **1.48** / **26.5 dB** |
| 非文字区（纯矢量色块）MAE / >32 | **0.227** / **0.00%** |
| `<path>` / `<text>` / `<image>` | 37930 / 54 / **0** |
| 图层 | 12 面板 / **50 物理元素** / 54 真文字 |
| 体积 | 4.7 MB（R=16）；R=32 更小(4.1MB)但 MAE 升到 1.65 |

对照组：旧的像素描摹 + PIL 大字降采样对齐那版，文字区 MAE 11.26 → 现在 12.04
（数字变差是因为**旧版用 PIL 当代理做验收，系统性偏乐观**；换 cairo 同一渲染器后，
单词级实测 3/4 更优：Transverse 0.1125→0.0459、Longitudinal 0.1413→0.0925）。

## 参数

| 参数 | 默认 | 作用 |
|---|---|---|
| `--W` | 1200 | 工作分辨率宽度。**词表坐标系跟着它走** |
| `--R` | 16 | 四叉树色差阈值。小=更准更大 |
| `--K` | 7 | 最粗边长 2^K=128px |
| `--erase` | 开 | 擦掉原字笔画（因为文字会用真 `<text>` 重写） |
| `--no-text` | 关 | 不做文字层（不需要 OCR，但过不了投稿门禁） |
| `--legend` / `--manifest` | — | 输出可读 / 机读图层清单 |
| `--elmap` | — | 元素划分自检图（人眼确认名字有没有贴对物体） |
| `--check` | 关 | cairosvg 回渲染 + 逐像素自检 |

## 三条必须遵守的工程约定（都是踩过的坑）

1. **矩形只能"列相邻且同色"才合并**（`quadtree`）—— 否则矩形互相重叠，
   出图顺序一变整张图就错。实测重叠 66.8% 时逆序 MAE 12.47 vs 自然序 0.25。
2. **矩形按面板边界切开**（`groupvec.runs_cells`）—— 否则后画的面板会盖住
   前一个面板的文字（实测「Head-on col」整个消失）。
3. **`font-family` 只写单值**（`fonts.py`）—— `"Arial, Helvetica, sans-serif"`
   这种列表 cairo 解析不了，静默退回 sans-serif，宽度差 11.5%，文字全错位。
   量字宽的字体必须和 SVG 里写的族名一致。

## 已知边界

- **渐变**是色阶台阶，不是 vector gradient mesh。要更平滑只能调小 `--R`（路径数涨）。
- **公式**（⟨V₂(η₁)V₂*(η₂)⟩_Sph 这类）字体里没有对应衬线字形，残差天然偏大；
  在 `labels.py` 里用 `_{}` / `^{}` 写上下标，或改用 STIX/DejaVu Serif。
- **元素边界**来自自动切分，个别细线（曲面上的引线、喷流锥）可能跟着父物体走；
  用 `panels.SPLIT` 按颜色/画框再切。
- 只适合"色块 + 硬边"类图（示意/三维渲染示意图）。照片、有机纹理不适合。

## 验收

```bash
python3 scripts/raster_to_vector_semantic.py fig.png -o fig.svg --words words.txt \
        --panels my_panels.py --legend fig_layers.md --check
python3 scripts/check_delivery.py fig.pdf --svg fig.svg
```
