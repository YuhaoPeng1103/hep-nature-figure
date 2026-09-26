# 自旋关联示意图：生图 -> 语义临摹（跑通的完整算例 #2）

非中心重离子碰撞下的**整体极化 / Λ-Λ̄ 自旋关联**示意图（双面板）。走 SKILL.md 的
**默认路线③**：

**IR -> 约束简报 -> 草图（矢量化输出）-> 闸口① -> 成品位图（草图 + 风格双参考）
-> 闸口② -> 语义临摹成矢量 -> 三道门禁**

比 1 号算例（`assets/demos/upc_semantic/`）复杂：两个面板、双参考图、
非中心碰撞 + 轨道角动量 L + 涡旋 w + 整体极化 + 弱衰变自分析。
这个算例暴露并修掉了 9 个真问题，见 `CHANGELOG.md` v2.6.3。

## 物理内容

- 面板 (a)：非中心碰撞 —— 两核上下错开、各在一条平行虚线束流轴上、相向运动（b ≠ 0）；
  参与核物质带巨大轨道角动量 **L**（垂直于反应平面、竖直向上）→ 以涡旋 w 传给 QGP
  火球 → 夸克/强子沿 L **整体极化**；两个超子（Λ 青 / Λ̄ 紫）自旋与 L 同向。
- 面板 (b)：`pair rest frame` —— 同一事件的 ΛΛ̄ 对自旋**背对背**（关联）；
  自旋靠**弱衰变自分析**读出：Λ -> p π-、Λ̄ -> p̄ π+，质子偏向自旋方向但有夹角 θ*。

## 文件

| 文件 | 作用 |
|---|---|
| `prompt_sketch.txt` / `prompt_render.txt` | 两步生图的简报（由 `ir_to_genbrief.py` 从 IR 生成，含形态约定） |
| `negative_spin.txt` | negative_prompt（**注意**：加 border/frame 也拦不住外框，见下） |
| `src_spin.png` | 选中并裁过外框的成品位图，1664x926（qwen-image-3.0，seed 22） |
| `words_spin22.txt` | OCR/手工词表 21 条（**源图 2x 坐标**） |
| `panels_spin.py` | 这张图的版式/元素表：2 面板 + 28 物理元素 + SPLIT 7 组 + EXTRA_ERASE 1 条 |
| `cmp_preview.png` | 上=源位图，下=临摹矢量回渲染 |

IR 在 `assets/ir/sketch6_spin_correlation.ir.yaml`。

## 命令

```bash
# (1) 生图（key 用你自己的；qwen-image-* 才支持 --ref）
python3 scripts/gen_figure.py --brief prompt_sketch.txt --stage sketch \
    --ref _T3精选/T3-09_STAR2017_3D碰撞余波_QGP涡旋+极化.png \
    --ref _T3精选/T3-33_Snellings2011_3D双椭圆核+碰撞参数.png \
    --seeds 5,7,9 --outdir gen/
python3 scripts/sketch_to_vector.py gen/sketch_s9.png -o gen/sketch_s9.svg --ocr   # 草图的矢量化输出（人可改）
python3 scripts/trim_border.py gen/sketch_s9.png -o gen/sketch_s9_clean.png        # 裁外框（必须）
python3 scripts/check_sketch.py gen/sketch_s9_clean.png --ir assets/ir/sketch6_spin_correlation.ir.yaml   # 闸口①
python3 scripts/gen_figure.py --brief prompt_render.txt --stage render \
    --ref gen/sketch_s9_clean.png --ref _T3精选/T3-33_Snellings2011_3D双椭圆核+碰撞参数.png \
    --seeds 22,31 --outdir gen/
python3 scripts/trim_border.py gen/render_s22.png -o gen/render_s22_clean.png
python3 scripts/check_sketch.py gen/render_s22_clean.png --ir assets/ir/sketch6_spin_correlation.ir.yaml  # 闸口②

# (2) 语义临摹
python3 scripts/raster_to_vector_semantic.py src_spin.png -o spin_q16.svg \
    --words words_spin22.txt --panels panels_spin.py \
    --W 1664 --R 10 --K 7 --q 16 --legend spin_layers.md --el_txt spin_el_table.txt --check

# (3) 门禁（PDF 用 Edge print-to-pdf，@page = 183x102 mm）
python3 scripts/check_delivery.py spin_q16.pdf --svg spin_q16.svg
python3 scripts/audit_composition.py spin_q16.pdf
```

## 实测（W=1664, R=10, K=7, q=16）

```
闸口①（草图 sketch_s9_clean） 核#1 109x576 高/宽 5.28 fill 0.77 | 核#2 96x440 高/宽 4.58 fill 0.77 -> 通过
闸口②（成品 render_s22_clean）核#1 109x571 高/宽 5.24 fill 0.77 | 核#2 114x481 高/宽 4.22 fill 0.77 -> 通过
临摹自检  整幅      MAE 1.351 | >8 1.07% | >32 0.62% | PSNR 26.85 dB
          非文字区  MAE 0.518 | >8 0.01% | >32 0.01%     <- 96.7% 画布
          文字区    MAE 25.573 | >8 31.87%                 <- 重排 Arial，已知残余
          1946 <path> | 21 <text> | 0 <image>
擦字      21 条标签残留 209px -> 0
交付门禁  spin_q16.pdf 183x102 mm | 矢量对象 1947 | 嵌入位图 0 | 可提取文字 79 字符 | 最小字号 8.6 pt -> 通过
构图审计  文字-文字重叠 0 | 线条穿文字 0 | 出界贴边 0 | 留白 0-of-9 -> 通过
```

## 28 个物理元素（图层树 panel -> element -> path）

`background` / `beam-axis-A` / `beam-axis-B`（两条平行虚线束流轴）/
`velocity-A` / `velocity-B` / `impact-parameter-b`（b 的双箭头）/
`hyperon-spin-A` / `hyperon-spin-B` / `vorticity-omega` / `L-angular-momentum` /
`nucleus-A` / `nucleus-B` / `fireball-QGP`（面板 a 共 13 个）；
`pair-A-arrows` / `pair-B-arrows` / `pair-A-vertex` / `pair-B-vertex` /
`pair-A-decay-pion` / `pair-B-decay-pion` / `pair-A-decay-proton` /
`pair-B-decay-antiproton` / `pair-A-spin` / `pair-B-spin` / `pair-A-momentum` /
`pair-B-momentum` / `pair-A-theta` / `pair-B-theta`（面板 b 共 15 个）；
外加两个 `text` 图层（21 个真 `<text>`）。

图层**只按物理元素分，不按颜色分** —— Illustrator 图层面板里按名字点选即可；
颜色挂在 `data-color` 上，只做体积优化（同色矩形并成一条 path）。

## 这张图踩到 / 修掉的坑（详见 CHANGELOG v2.6.3）

1. **模型稳定画外框** —— 简报和 negative 都拦不住（5/5 有框）→ `trim_border.py` 确定性裁掉。
2. **粗笔画擦字留残影** —— `ink_map` 加「比 41x41 中值背景暗 25」这条；Λ 残留 21.1% -> 0。
3. **颜色条件无条件 +0.22** —— 灰色碎片被表里靠前的元素抢走 → 改成返回加分 float。
4. **兜底只看距离** —— 整面板的 background 框吞掉 5 个散块 8000+px -> 改成 (距离, 框面积)。
5. **细线从整面板捞** —— `darkbox` 把核的暗色底尖挖走 7400px -> 只从 background 捞。
6. **OCR 漏掉多部件字形的零件** —— Λ̄ 的上划线擦不掉 -> 新增 `EXTRA_ERASE`（只擦不改字）。

## 已知偏差（不掩饰）

1. 选中的 `render_s22` 核**没画核子气纹理**（`render_s31` 有，但缺 `QGP` 标签、
   且与 UPC 算例视觉语言重复 -> 取标签齐全的 s22）。
2. 文字是重排的 Arial，字形不可能逐像素重合（文字区 >8 达 31.87%）。
3. 元素框是**这一张位图**量出来的，换 seed 换构图要重新量。
