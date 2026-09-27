# 喷注淬火示意图：生图 -> 语义临摹（路线③ 全流程，v2.7.2）

高能重离子碰撞里的**喷注淬火 / 双喷注不对称**示意图（单面板，1664x928）。
走 SKILL.md 的**默认路线③**：

**IR -> 约束简报 -> 草图（矢量化输出）-> 闸口① -> 成品位图（草图 + 风格双参考）
-> 闸口② -> 语义临摹成矢量 -> 三道门禁**

这个算例的价值不在"画得好看"，而在**它抓出了一个 IR 自己写反的几何** ——
新加的机器闸口「喷注路径长度不对称（弦长比）」把它量出来了，见 `CHANGELOG.md` v2.7.2。

## 物理内容

硬散射在极早期产生一对**背对背**部分子（dijet），它们必须穿过 QGP 介质才能逃逸。

- **J1 未淬火喷注**（右上）：顶点本来就在介质偏右，它**穿过介质只有很短一段**就出射
  -> 明亮、准直、高 pT 强子多（6 颗亮球）。
- **J2 被淬火喷注**（左下）：要**几乎横穿整个介质**才出射，沿途通过**胶子轫致辐射**
  不断把能量沉积给介质 -> 出介质后变灰、变软、强子只剩 3 颗。
- 能量损失正比于**穿过介质的路径长度**，所以「顶点偏右」才是「左下长、右上短」的唯一画法。
  闸口①/② 量的就是这个比值（实测 **4.00x**，阈值 1.8）。

## 文件

| 文件 | 作用 |
|---|---|
| `jet_quenching.ir.yaml` | IR（含 `geometry_constraints.机器` 的路径不对称闸口） |
| `brief_sketch.md` / `brief_render.md` | 两步的约束简报（由 `ir_to_genbrief.py` 从 IR 编译） |
| `sketch_s21_clean.png` | 选中并裁过外框的草图（闸口① 通过） |
| `src_render.png` | 选中的成品位图，1662x926（seed 33，已 trim 1px 边框） |
| `words_s33.txt` | OCR 词表 6 条（2 行标签已合并、去掉误识的 "0"；**坐标是 2 倍图**） |
| `panels_jet.py` | 版式/元素表：9 个**物理**元素 + SPLIT + SHADING + SEAM |
| `jet_layers.md` / `jet_el_table.txt` | 图层清单 / 元素明细（人读） |
| `figure.svg` | **交付矢量**：34,076 `<path>` / **6 真 `<text>`** / `<image>` **0** |
| `figure.pdf` | 183 x 101.96 mm，纯矢量（Edge `--print-to-pdf`） |
| `cmp_bitmap_vs_svg.png` | 上 = 成品位图，下 = SVG->PDF 用 PyMuPDF 回渲染 |

## 命令

```bash
# (1) 草图（★ 必须带风格参考图；key 用你自己的，qwen-image-* 才支持 --ref）
python3 scripts/ir_to_genbrief.py jet_quenching.ir.yaml --stage sketch -o brief_sketch.md
python3 scripts/gen_figure.py --brief brief_sketch.md --stage sketch \
    --ref _T3精选/T3-02_STAR2024_ED1_核形变到火球_全流程3D.png --seeds 21,23,25 --outdir gen/
python3 scripts/sketch_to_vector.py gen/sketch_s21.png -o gen/sketch_s21.svg --ocr   # 草图的矢量化输出（人可改）
python3 scripts/trim_border.py gen/sketch_s21.png -o gen/sketch_s21_clean.png        # 裁外框（必须）
python3 scripts/check_sketch.py gen/sketch_s21_clean.png --ir jet_quenching.ir.yaml  # 闸口①

# (2) 成品位图（草图 = 构图依据，参考图 = 风格书，两个都要带）
python3 scripts/ir_to_genbrief.py jet_quenching.ir.yaml --stage render -o brief_render.md
python3 scripts/gen_figure.py --brief brief_render.md --stage render \
    --content-ref gen/sketch_s21_clean.png --ref _T3精选/T3-02_STAR2024_ED1_核形变到火球_全流程3D.png \
    --seeds 31,33 --outdir gen3a/
python3 scripts/trim_border.py gen3a/render_s33.png -o gen3a/render_s33_clean.png
python3 scripts/check_sketch.py gen3a/render_s33_clean.png --ir jet_quenching.ir.yaml  # 闸口②

# (3) 语义临摹（★ 路径数由 --q 决定，不是 --R）
python3 scripts/raster_to_vector_semantic.py gen3a/render_s33_clean.png -o figure.svg \
    --words words_s33.txt --panels panels_jet.py --W 1662 --R 5 --K 7 --q 64 \
    --legend jet_layers.md --el_txt jet_el_table.txt --check

# (4) 门禁（PDF 用 Edge print-to-pdf，@page = 183 x 101.96 mm）
python3 scripts/check_delivery.py figure.pdf --svg figure.svg
python3 scripts/audit_composition.py figure.pdf
```

## 这个算例量到的数字

| 项 | 实测 |
|---|---|
| 闸口①（草图 s21 / s23 / s25）弦长比 | 10.65 / 21.13 / 6.20 x（阈值 1.8） |
| 闸口②（成品 s33）弦长比 | **4.00 x**（蓝锥 91px / 灰锥 363px） |
| 介质高宽比 / 顶点位置 | 1.81 / (0.581, 0.414)，在介质内 |
| 交付 PDF 全图 MAE | **1.797**（介质区 2.459、蓝锥 2.962、灰锥 2.029、空白区 0.007） |
| 路径数 vs `--q` | R=2 -> 103,418 / R=3 -> 99,021 / R=5 -> 86,932 / R=8 -> 86,525（R 只降 16%）；**`--q 64` -> 34,076 / 7.08 MB / MAE 1.204**；`--q 32` -> 4,631 / 3.47 MB / MAE 1.369 |
| 门禁 | `check_delivery.py` 全过（纯矢量、0 嵌入位图、79 字符可提取文字、最小字号 9.2pt）；`audit_composition.py` 无问题 |
| `--shade` | 103,418 -> 611 path，但**羽化边缘被切出白裂纹**、介质掩膜不连通（最大块 52.5%）-> **不用**，保真优先走逐色临摹 |

## 想照着做的话，记住三条

1. **IR 的几何要自洽**：顶点偏哪边，哪边出射路径就短。写完先用闸口量一遍再交给模型 ——
   否则多张草图会「一致地」错（这个算例就是这么错的，3/3 张全反）。
2. **路径数由 `--q` 决定，不是 `--R`**。要「保真 + 体积」就调 `--q`。
3. **`--shade` 不是万能的**：羽化边缘 + 掩膜不连通的元素会碎，用 `NO_SHADE=1` 切回逐色临摹。
