# UPC 示意图：生图 → 语义临摹（跑通的完整算例）

超边缘重离子碰撞（ultra-peripheral collision, UPC）侧视示意图，走的是
SKILL.md 的主线：**IR 管物理 / 生图管风格 / 临摹管矢量化**。

物理内容：两个洛伦兹压扁的核（A 蓝、B 橙）分居两条平行虚线束流轴上，
不重叠、相向运动；碰撞参数 b；各自的准实光子（波浪线，无箭头）汇聚到
一个顶点，顶点发出背对背的 e⁺ / e⁻。

## 文件

| 文件 | 作用 |
|---|---|
| `prompt_upc.txt` / `negative_upc.txt` | 生图提示词。坐标是**显式写死**的（"上虚线在 30% 高度、核在左起 25%"），模型画错时改这里 |
| `src_upc.png` | 生图产物，1664×928（qwen-image-3.0，seed 22） |
| `words_upc.txt` | OCR 词表（**源图 2× 坐标**，`groupvec` 会自动 ×sc×0.5 还原） |
| `panels_upc.py` | 这张图的版式/元素表：1 个面板 + 15 个物理元素 + 颜色判据 |
| `cmp_preview.png` | 三条路线并排：生图位图 / 临摹矢量回渲染 / 直写 SVG |

## 命令

```bash
# ① 生图（需要有能出图的模型；本仓库用 DashScope 的 qwen-image-3.0）
python gen_qwen.py --model qwen-image-3.0 --size 1664*928 \
       --seeds 11,12,13,21,22,23 --prompt prompt_upc.txt
# ② 语义临摹
python scripts/raster_to_vector_semantic.py src_upc.png -o upc_traced.svg \
       --words words_upc.txt --panels panels_upc.py \
       --W 1664 --R 10 --K 7 --legend upc_layers.md --check
# ③ 门禁（PDF 用 render_util.to_pdf 出，183 mm 双栏）
python scripts/check_delivery.py upc.pdf --svg upc_traced.svg
python scripts/audit_composition.py upc.pdf
```

## 实测（W=1664, R=10, K=7）

```
MAE 0.486 | >8 0.31% | >32 0.23% | PSNR 31.44 dB
<path> 22655 | <text> 10 | <image> 0
check_delivery  : ✅ 矢量对象 22656 | 嵌入位图 0 | 最小字号 8.7 pt
audit_composition: ① 0 ② 0 ③ 0 ④ 0/9 → ✅
```

对照：同一条主线在 4 格手绘草图上（平色块 + 硬边）W=2160 得 MAE 0.230
（见 CHANGELOG v2.4）；T3-01 那种**三维渲染级**的封面图 W=1200 只有
MAE 0.293 但路径 43024 条、5.6 MB —— 平色块示意图的性价比明显更高。

## 15 个物理元素

`background` / `axis-A` / `axis-B`（两条虚线束流轴）/ `field-A` / `field-B`
（洛伦兹压扁的库仑场同心环）/ `photon-A` / `photon-B`（准实光子波浪线）/
`nucleus-A` / `nucleus-B` / `arrow-v-A` / `arrow-v-B` / `arrow-b` /
`vertex`（γγ 顶点星芒）/ `arrow-e-plus` / `arrow-e-minus`

## 这张图踩到 / 修掉的两个坑

1. **虚线束流轴会掉进 `background`** —— 虚线是几百段 <150px 的小连通域，
   `elements.discover` 的 `minpx` 闸门把它们当噪声丢掉。解法是在
   `panels_upc.py` 里用 `SPLIT` 按 **框 + 亮度** 把它们捞回成独立图层
   （`pixel_pred` 支持 `("darkbox", [框...], thr)`）。框是**量出来的**：
   实测 y=250..251 有 780/831 个暗像素、y=644..645 有 778/876 个。
2. **元素吞背景** —— 见 CHANGELOG v2.5 的 `elements.py` 修复。
   修前 `photon-A` 元素 97.7% 是背景，修后 30%（且这 30% 是它自己的
   抗锯齿边缘）。修前/修后 MAE 完全相同（0.486），只影响可编辑性。
