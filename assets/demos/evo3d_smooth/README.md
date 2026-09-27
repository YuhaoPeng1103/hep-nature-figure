# evo3d_smooth —— 位图 → 矢量：把「色彩光滑」做到与源图同档

**任务**：把扩散模型出的「形变核 → 量子涨落 → 碰撞 → QGP 火球」四阶段示意图
临摹成全矢量 SVG（文字为真 `<text>`，图形按**物理元素**分层，不按颜色分层）。

**回答的两个追问**：
1. 「临摹出来的 SVG 色彩可不可以像 `fig.svg` 一样色彩光滑？」
2. 「fireball 画好了一些，但是 3D 渲染感又没了」

## 结果

| 指标 | 值 |
|---|---|
| `<path>` | 15,516 |
| `<text>`（可编辑、PDF 里可提取） | 4 |
| `<image>` | 0 |
| 回渲染 MAE（全图） | 0.587 |
| 回渲染 MAE（非文字区） | 0.141 |
| 相邻色阶步进 中位 / p90 / p95 / p99 | 0 / 0 / 2 / 20 |
| 源位图 同指标 | 0 / 1 / 2 / 23 |
| 体积 | SVG 3.59 MB ／ PDF 1.59 MB |
| 门禁 | `check_delivery` ✅ 纯矢量 + 文字可编辑；`audit_composition` ✅ 无重叠/出界 |

图层树（`figure_layers.md` 里有完整表）：`p-background` / `p-stage1-nucleus` /
`p-stage2-fluctuations` / `p-stage3-nucleus-A` / `p-stage3-nucleus-B` /
`p-stage4-fireball` / `p-stage4-nucleons` / `p-stage3-overlap` /
`p-arrow-1..3` / `p-text`。

- 整图对照：`cmp_bitmap_vs_svg.png`（上=位图，下=临摹矢量）
- 火球特写（本次交付，对）：`cmp_fireball_perpixel_OK.png`
- 火球特写（真渐变那条路，错）：`cmp_fireball_truegradient_BAD.png`

## 关键实测：真 `<radialGradient>` 在这张火球上差 31 倍

同一张位图、同一个火球元素，只换「怎么画」：

| 画法 | 火球区域 MAE |
|---|---|
| 逐像素色块（本次交付） | **0.455** |
| 一条真 aradial `<radialGradient>` body | **14.324** |

原因不是参数没调好，是**几何不对**：位图的最亮核心**偏离球心**（发光中心在球心
左上），而一条椭圆径向渐变的等色线是**同心**的 —— 拟合残差看着还小（5.54），
**渲染出来**却是整圈错位的亮/暗环（`cmp_fireball_truegradient_BAD.png` 右图那圈
奶白色环 + 硬边亮斑就是它）。

★ 教训：`gradfit.fit` 的残差会把这种偏移当离群点丢掉（迭代 keep-mask 只保
"模型解释得了"的像素），所以 **残差小 ≠ 画出来像**。判据必须是**回渲染后的区域 MAE**。

→ 位图到矢量要**先量再选路**：等色线真同心（球心高光）的元素走真渐变（本图的
形变核就走通了，见图层表里的 `+ 基色x2 + 明度层`）；等色线偏移/有内部结构的
（本图火球）走逐像素。两条路的取舍**不能凭感觉**。

## 复现

```bash
# 临摹（工作分辨率 = 源图 1:1；--q 0 不量化是「光滑」的前提）
python3 scripts/raster_to_vector_semantic.py src_render.png -o figure.svg \
    --words words_s51.txt --panels panels_evo3.py \
    --W 1664 --R 5 --q 0 --legend figure_layers.md --check

# PDF：包一层 HTML 走 Edge headless（cairosvg 出这张会 CAIRO_STATUS_NO_MEMORY）
#   @page { size: 183mm 101.8mm; margin: 0 }  + SVG 内联进 <body>
python3 scripts/check_delivery.py figure.pdf --svg figure.svg
python3 scripts/audit_composition.py figure.pdf
```

## 踩过的两个坑（`panels_evo3.py` 的注释里有对应说明）

1. **元素框必须每张图重新量**。三个箭头的框是从上一张位图抄的（y 405..463），
   这张位图的箭头在 y 351..400 → 三个箭头**全被 IoU 判给了相邻阶段**
   （实测 2887 / 2796 / 2571 px 分别落进 `stage2` / `stage3-nucleus-A` /
   `stage1-nucleus`）。改框后三个箭头各自独立成层。
2. **火球里的 4 个核子球要单独切出来**，否则它们会被当成"渐变拟合不了的残差"
   混在火球层里，改不了色。本图用 `gradresid`（按 gradfit 残差找落脚区），
   见 `panels_evo3.py` 的 `pixel_pred`。
