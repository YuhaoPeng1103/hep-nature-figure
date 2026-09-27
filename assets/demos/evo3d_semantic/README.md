# 形变核 → 火球：**3D 渲染档**重出 + 语义临摹（跑通的完整算例 #4）

和算例 #3（`../evo_semantic/`）**同一份 IR、同一张手绘草图、同一个风格参考
T3-02**，唯一变的是 `ir_to_genbrief.py --style-mode`。这一例专门证明
**「参考图 = 风格书」**那句话：参考图给的是**渲染方式**（3D 渲染），
不是内容模板。

## 这一例修的是什么（v2.6.7）

算例 #3 的简报是**旧的**：`ir_to_genbrief.py` 把风格**写死成扁平矢量**，
还无条件禁止 3D —— 而 IR 的 `style` 段明写「半写实插画 / 3D 椭球 /
球面明暗 + 网格线 / 火球橙→红渐变」。IR 与简报**直接打架**，模型照简报走，
于是火球被画成一个**纯色圆盘**（见 CHANGELOG v2.6.7 的根因表）。

现在 `--style-mode auto` 会读 IR 的 `style` 段（关键词判据）判出 `render3d`，
简报第四节改成「3D 渲染的期刊插画风」，禁止项也改成
「**允许** 3D 渲染的立体感 …… 只禁照片级材质 / 噪点 / 景深」。

## 文件

| 文件 | 作用 |
|---|---|
| `brief_sketch.md` / `brief_render.md` | 两步生图的约束简报（`--style-mode` 生效后；render 档 = `render3d`） |
| `src_render.png` | 选中并裁过外框的**成品位图**，1663×927（qwen-image-3.0，seed 31） |
| `words_s31.txt` | OCR 词表 5 条（**源图 2x 坐标**；已合并 `deformed nucleus` / `QGP fireball`） |
| `panels_evo2.py` | 版式/元素表：1 面板 + 9 元素 + 3 组 SPLIT（框全部按新位图**重新量过**） |
| `evo2_edit.svg` | ★ **可编辑版**交付：686 `<path>` / **5 `<text>`** / 0 `<image>`，3.07 MB —— 真 `<radialGradient>`（火球）+ 真 `<linearGradient>`（参与区透镜）+ 明暗层 |
| `evo2_edit_layers.md` | 可编辑版图层清单 |
| `evo2_layers.md` | 忠实版图层清单 |
| `cmp_bitmap_vs_svg.png` | 上＝成品位图，下＝交付矢量（`evo2_edit.svg`）回渲染 |

IR 在 `assets/ir/sketch7_deformed_to_fireball.ir.yaml`（同一份，没改）。

## 实测数字

| 交付 | 结构 | `<path>` | `<text>` | `<image>` | 体积 | MAE |
|---|---|---|---|---|---|---|
| `evo2.svg` 忠实版（**未入库**，4.58 MB） | 逐色临摹 | 33158 | **5** | 0 | 4.58 MB | **0.666** |
| `evo2_edit.svg` 可编辑版 | `--shade auto:32:1` | **686** | **5** | 0 | 3.07 MB | 0.994 |
| 对照 `--shade auto:16:1` | 明度档 16 | 441 | 5 | 0 | 2.49 MB | 2.237（火球外圈肉眼可见色环） |

忠实版太大没入库；一条命令即可重现（`--shade` 那行去掉就是忠实版）：

```bash
S=<skill>/scripts
python3 $S/raster_to_vector_semantic.py src_render.png -o evo2.svg \
    --words words_s31.txt --panels panels_evo2.py \
    --W 1663 --R 5 --K 7 --q 0 --legend evo2_layers.md --check

python3 $S/raster_to_vector_semantic.py src_render.png -o evo2_edit.svg \
    --words words_s31.txt --panels panels_evo2.py \
    --W 1663 --R 5 --K 7 --q 0 --shade auto:32:1 \
    --legend evo2_edit_layers.md --check
```

门禁：`check_delivery.py` 两份**全部通过**（嵌入位图 0 个、可提取文字 60 字符、
最小字号 9.8 pt）；`audit_composition.py` 判「局部构图无问题」。

## ★ 逐标签选字体（这一例顺带修掉的真 bug）

位图里的标签是生图模型画的，**字体每张图都可能不同**。矢量化以前只拿主字体
（Arial）硬套，`labels.align` 的墨迹高度验收（`dh <= dh_lim`）就过不了，
标签**退回成色块轮廓** —— 「文字必须可编辑」直接失守：5 条标签只成了 2 条 `<text>`。

| 字体 | deformed nucleus | collision | QGP fireball |
|---|---|---|---|
| Arial | dh=6 ✗ | dh=5 ✗（限 5.22） | dh=10 dw=9 ✗ |
| **Tahoma** | dh=5 ✓ | dh=3 ✓ | dh=3 dw=0 ✓ |

现在 `labels.fam_candidates` 会按 Arial → Tahoma → Verdana → Calibri → Segoe UI →
DejaVu 依次试，取第一个过验收的（默认字体就过时行为不变）；族名一律**从字体
文件读**，不靠文件名猜。实测：**5 条全成 `<text>`**（其中 3 条换成了 Tahoma），
SVG 里 `font-family` 同时出现 Arial 与 Tahoma。

## 闸口②（成品位图，`measure_stages.py` 出数字）

```
阶段横向中心: ['169', '584', '1034', '1486']   箭头1/2/3 全部向右
阶段2 连通域=1   阶段3 交叠=99 px   阶段4 内部连通域=1
各阶段平均饱和度: ['0.013', '0.006', '0.061', '0.765']
1_阶段x递增=是  2_箭头全向右=是  3_阶段2椭圆相互重叠=是  4_阶段3部分重叠=是
5_阶段4核子相互重叠=是  6_冷热分明=是  7_标签对齐=是
```
