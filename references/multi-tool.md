# 多工具联合：一张图，多个后端

> **核心主张**：一张图不该只用一种工具。
> 各部分交给各自最擅长的工具，在拼版层合成。
>
> 实测范例：`scripts/demo_combined.py` → 产出 `combined.pdf` / `.eps`

---

## 交付格式：SVG 和 PDF/EPS **都要出**，用途不同

这是容易搞混的一点，说清楚：

| 格式 | 用途 | 为什么 |
|---|---|---|
| **SVG** | **工作稿**——给人精修 | `<g inkscape:label>` 保留**图层结构**，Inkscape/Illustrator 打开后每个部件可单独选中。文本格式，可 diff、可版本管理 |
| **PDF** | **交付稿**——投给期刊 | Nature 官方首选。字体内嵌、打印就绪。**但 PDF 没有图层概念**，只有绘制顺序，在 Inkscape 里打开会丢层级 |
| **EPS** | 备份交付 | Nature 也接受。`pdftops -eps` 生成 |
| **AI** | 有 Illustrator 时 | 从 SVG/PDF 另存为 .ai |

> ⚠️ **不要只出 PDF**：那样人精修时就没有图层了。
> ⚠️ **不要只出 SVG**：那不是 Nature 明确列出的格式。

**Nature 官方原话**（查证过）：
> "For line art, graphs, charts and schematics we prefer
> **Adobe Illustrator (AI), Encapsulated PostScript (EPS), or PDF**"

官方**没提 SVG**。SVG 是我们的**工作格式**，不是投稿格式。

---

## 哪些部分该交给哪个工具

| 图的内容 | 工具 | 为什么是它 |
|---|---|---|
| 数据面板（谱、曲线、误差带） | `matplotlib` / `ROOT` | 真矢量，数值精确 |
| 3D 曲面 | `matplotlib` | 真矢量（**Mathematica 会栅格化，别用**） |
| 卡通/示意图（渐变、发光） | `svg_lib` + `shapely` | 渐变的精确控制；shapely 做布尔与轮廓 |
| **公式与数学排版** | **TikZ / LaTeX** | 分式、上下标、期望值括号、贝塞尔函数——SVG 手写极痛苦且排版差 |
| 真 3D（几何即内容） | `Blender` | 探测器几何、CAD |
| 数学密集的整图 | `Ipe` / `Asymptote` | LaTeX 原生 |
| 合成 | `PyMuPDF` | `show_pdf_page` 保矢量 |
| 交付转换 | `pdftops` | PDF → EPS |
| **人工精修** | `Inkscape` / `Illustrator` | **唯一必须人的一步** |

---

## 实测范例：碰撞几何 + 公式

`scripts/demo_combined.py` 产出的图：

```
panel a  碰撞几何示意  ← svg_lib（反应平面、火球、ϕ 角、Ψ_RP）
panel b  物理公式      ← TikZ（v_n、R(Ψ_n)、CME 电荷分离）
合成                  ← PyMuPDF
```

**验证结果**：
```
页面 180×78 mm
矢量指令 17 条 | 嵌入位图 0 个      ← 全矢量
XObject 6 个                       ← 两面板各自嵌入
文字可提取 228 字符                 ← 公式是真文字，不是轮廓
combined.pdf 42 KB | combined.eps 368 KB
```

**"公式可提取"是关键**：TikZ 输出的是**真文字**，美术团队能重新排版。
若用 SVG 手写公式再转轮廓，这条就废了。

---

## 实现要点

### 1. 拼版用 `show_pdf_page`，不要用图片

```python
import fitz
doc = fitz.open()
page = doc.new_page(width=PW, height=PH)
src = fitz.open("panel.pdf")
page.show_pdf_page(fitz.Rect(x0, y0, x1, y1), src, 0)   # 矢量嵌入
```

### 2. 交付前验证

```bash
python3 scripts/check_delivery.py combined.pdf
#  → get_images()==0 ？  有没有被栅格化
#  → 文字能提取吗？      公式/标注是否还在
#  → XObject 数           面板是否都嵌进去了
```

⚠️ **复合图不能只用 `get_drawings()` 计数**——面板是 XObject，不遍历。
判据是「0 嵌入位图 + XObject>0 + 文字可提取」。

### 3. LaTeX 宏包依赖

实测踩坑：`newtxtext` / `newtxmath` 未安装会导致编译失败。
**用之前先验证宏包可用**，缺了要么装、要么换基础宏包：

```bash
kpsewhich newtxtext.sty     # 有输出 = 可用
sudo apt install texlive-fonts-extra   # 装
```

---

## 缺工具怎么办

**不要降级、不要糊弄。** 跑 `scripts/check_tools.py` 看缺什么 → 告诉用户装什么 → 装好调用它。

> 缺工具 = 去装，不是绕开。
