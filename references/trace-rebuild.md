# 矢量成品的三步：先临摹 → 再从临摹层重建（v4.0）

> **配套**：`scripts/trace_rebuild.py`（第三步）· `scripts/raster_to_vector_semantic.py`（第二步）
> · `references/svg-cookbook.md`（矢量怎么画）· `references/3d-checklist.md`（3D 怎么立起来）
> **来源**：2026-10-03 ~ 10-04 集体流示意图 v35 → v37 → v38 一整轮返工，全部有实测数字。

---

## 0. 为什么要有这条线

「位图 → 矢量」以前有两条路：**重画**（照位图重画一遍矢量）与**混合临摹**（逐像素描摹）。
两条都踩过同一个坑：**几何是重新抠的**，于是成品与位图对不上 —— 而对不上的地方，
读者一眼就看得出（"你这矢量图和位图完全不一样"）。

v4.0 把这条线定成**固定三步**，核心是第 ③ 步**只从临摹层的语义图层取几何**：

```
① 客户选定/确认的位图           out/figure_v38_src.png
        ↓
② 逐像素临摹（带语义图层）      raster_to_vector_semantic.py
   → SVG，每个物理元素一个 <g data-element="...">
        ↓
③ 从临摹层重建                  trace_rebuild.py
   → 最终矢量成品（含真渐变）
```

---

## 1. 为什么"几何必须从临摹层取"，而不是重新做颜色阈值

实测的两种失败（都出在 v37，来自"颜色谓词 ∩ 包围盒"这条老路）：

| 现象 | 根因 |
|---|---|
| `a-nucleus-far` 的底边被**切平** | 手写的包围盒 `(575,35,810,255)` 比真 bbox `(586,46,800,306)` 矮，底边被裁掉 |
| "板下淡出"成了一条**卷曲细带** | 那片区域不是单连通的，`findContours` 在非单连通掩膜上描出来就是一条飘带 |

改成**只从 `<g data-element>` 的掩膜取几何**之后：

| 版本 | 几何来源 | 三个体积的 MAE |
|---|---|---|
| v35 | 颜色阈值 | 2.49 |
| v37 | 颜色阈值 ∩ 包围盒 | 5.28 |
| **v38** | **`<g data-element>` 掩膜** | **1.95** |

**回归自检基线**：`trace_rebuild.py` 在 v38 的输入上重跑，三个体积的像素数
**30044 / 25884 / 28268** 应逐一复现，整图 **MAE = 1.946**。换了代码先跑这条回归。

---

## 2. 每个体积元素被重做成三件东西

| # | 产出 | 干什么 |
|---|---|---|
| **(a)** | **`clipPath`** | 该元素在临摹图里的**精确可见轮廓** —— 含被其它元素**遮挡后**的形状（这是"临摹"相对"重画"最大的优势：位图里的遮挡关系是免费的） |
| **(b)** | **真渐变网格** | 每 `BAND` 像素一条 `linearGradient`（`NSTOP` 个 stop），颜色场从原图拟合：先把掩膜按 `ERODE` 内缩、再按 `SIGMA` 平滑，纵向再做一次高斯平滑消掉带间噪声 |
| **(c)** | **线稿逐像素保留** | 网格解释不了的描边 / 切割线 / **穿过球面的格线**，原样照抄临摹图里的碎矩形（`RECT` 正则认得的那种 `M..h..v..h-z`） |

判"哪些碎矩形要留"用的是**残差**：`dev = |模型 − 原图|`、`ink_px = 掩膜 & ((dev > DEV_KEEP) | (拟合底色比原图亮过 INK_DARK))` ——
也就是"渐变铺不出来的那部分像素"，那些位置的线稿一律留下。

其余元素（薄板、三轴、文字、箭头、虚线、别的面板）**整段照抄**临摹图，不重建。

---

## 3. 用法

```bash
python3 scripts/trace_rebuild.py \
    --trace out/figure_v17.svg \      # ② 的产物（带 <g data-element=...>）
    --src   gen/trace_src.png   \      # ① 的位图（要跟 --trace 同尺寸同内容）
    --stem  figure_v38          \      # 输出名
    --elements a-nucleus-near,a-nucleus-far,a-fireball-a
# 尺寸默认从 <trace>.svg 的 width/height 读；也可显式 --size 1500x630
```

产出 `<outdir>/<stem>.svg / .png`（默认宽 2600）`/ @4000.png`，并打印
**逐元素读数**（`px / bands / inkrects / inkpx / shade_resid`）与**整图 MAE**。

### 输入要求（不满足就别跑）

- `--src` 与 `--trace` 必须**同尺寸、同内容**（`--trace` 就是 `--src` 的临摹结果）；
- `--trace` 里的体积元素必须各自包在**一个带 `id` 的 `<g>`** 里，且该 `<g>` 内部的
  形状是 `RECT` 那种**碎矩形 path**（`raster_to_vector_semantic.py` 的输出即如此）；
- 被 `--elements` 点名的元素**至少 200 px**，否则跳过（在报告里写成 `px=0 … resid=-1`）。

### 读懂那行报告

```
a-nucleus-far        px= 25884 bands= 21 inkrects= 1180 inkpx=  9213  shade_resid=1.83
  px          该元素在临摹图里的可见像素数（= 它的可见面积）
  bands       铺了几条 linearGradient（纵向 BAND 数）
  inkrects    保留了多少条碎矩形（线稿层）
  inkpx       这些碎矩形覆盖的像素数
  shade_resid 渐变拟合在"非线稿区"的平均残差（越小越好；大 = 这块颜色场太复杂，网格没铺住）
```

---

## 4. 失败模式（按踩到的顺序）

| 症状 | 塌在哪 | 怎么修 |
|---|---|---|
| 成品与位图"完全不一样" | 几何不是从临摹层取的（走了颜色阈值/包围盒） | 确认 `--trace` 是**语义临摹**的产物，且 `--elements` 点的就是那些 `<g id>` |
| 形体边缘发毛 / 有锯齿 | `silhouette_d` 的 `eps` 太小 | 调大 `--eps`（默认 0.7）；或看 `--win` 平滑轮数 |
| 球上的格线丢了 | 线稿层判据太严 | 调小 `--dev`（`DEV_KEEP`）或调小 `--ink-dark` |
| 颜色带条状（banding） | `BAND` 太大 / 纵向平滑不够 | 调小 `--band`；纵向 `gaussian_filter1d(P, 1.5, axis=0)` 的 1.5 可加大 |
| 整图 MAE 正常但某一块糊 | 那块 `shade_resid` 高 | 那块要么单独点进 `--elements` 重建，要么承认它是"颜色场太复杂"、整段照抄 |

---

## 5. 这一步之后还要过什么

`trace_rebuild.py` 的产物**不自动等于可交付**：

1. 五道门禁（`check_render` / `audit_composition` / `check_delivery` / `delivery_gate` /
   `projection_gate`），相关时加 `verify_scene` / `ref_leak_check` / `pdf_roundtrip`；
2. `bitmap_conformance.py`（v3.2）：成品 vs **所选位图**的架构几何对账 ——
   这条正是"重画"与"临摹"两条路的共同底线；
3. `check_render_mode.py` + **成品 × 风格参考的并排图**（机器判不了 3D，就让人 5 秒内能判）；
4. SVG 底线：最底层白 `<rect>`；纯矢量、0 嵌入位图；
   **禁** `feGaussianBlur` / `feDropShadow` —— 立体感靠**叠渐变**模拟。
