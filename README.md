# hep-nature-figure

**高能核物理期刊级配图 Skill** — 从参考图或手绘草图，产出**可编辑的矢量配图**。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 这个 skill 解决什么问题

做科研配图的痛点不是"不会画"，是**花太多时间画**，而且 AI 直接画往往
**"花里胡哨但物理表达不准确"**。

这个 skill 的做法是：**在动手之前，先把"这张图在物理上表达什么"写成结构化的 IR**
（中间表示），再交给合适的工具执行，最后用可判定的断言验收。

```
参考图 / 手绘草图
      ↓
  ① IR（物理内容 + 元素清单 + 构图 + 风格分类 + 后端选择）
      ↓
  ② 按图选后端：svg_lib / matplotlib / TikZ / Blender / ROOT …
      ↓
  ③ 执行 → ④ 验证（渲染静默失败、风格偏离、投稿合规）
      ↓
  SVG（工作稿，人精修用） + PDF/EPS（交付稿，投稿用）
```

**核心主张**：一张图不该只用一种工具。各部分交给各自最擅长的，在拼版层合成。

---

## 安装

### Claude Code

```bash
git clone https://github.com/YuhaoPeng1103/hep-nature-figure.git \
  ~/.claude/skills/hep-nature-figure
```

或建软链：

```bash
ln -s /path/to/hep-nature-figure ~/.claude/skills/hep-nature-figure
```

装好后用 `/hep-nature-figure` 或在对话里描述任务即可触发。

### 其他平台

`SKILL.md` + `references/` 的内容是**平台无关的方法论**，可移植到
ChatGPT（Instructions + Knowledge 文件）、Cursor、Codex 等。

---

## 环境要求

**核心（必需）**：

```bash
pip install matplotlib numpy scipy pillow cairosvg pymupdf shapely
```

**按需**（不同图型需要不同工具）：

| 工具 | 用于 | 安装 |
|---|---|---|
| Inkscape | 人工精修矢量 | `sudo apt install inkscape` |
| LaTeX (pdflatex) | 公式、TikZ | `sudo apt install texlive-latex-recommended texlive-pictures` |
| Blender | 真 3D 几何 | https://www.blender.org/download/ |
| ROOT | `.root` 文件、领域惯例图 | https://root.cern/install/ |
| Asymptote | 程序化矢量图 | `sudo apt install asymptote` |
| Ipe | 公式密集的整图 | `sudo apt install ipe` |

**先用脚本探测本机有什么、缺什么该装什么**：

```bash
python3 scripts/check_tools.py
```

输出示例：

```
✅ 已可用（5）   Python+matplotlib · cairosvg · PyMuPDF · LaTeX · ROOT
❌ 缺失（6）     Inkscape · Ipe · Asymptote · Blender · Mathematica · Illustrator
                 ↑ 每项都给出对应平台的安装命令
```

> **缺工具 = 去装，不是绕开。** 这是这个 skill 的一条硬纪律。

---

## 快速开始

```bash
# 1. 看本机有什么工具
python3 scripts/check_tools.py

# 2. 从论文 PDF 切参考图
python3 scripts/extract_figures.py paper.pdf -o refs/

# 3. 写 IR（参考 references/ir-spec.md 的格式）
#    —— 这一步不可跳过，是物理正确性的保证

# 4. 按 IR 实现，渲染
#    图元库在 scripts/svg_lib.py

# 5. 迭代：与参考图并排对比
python3 scripts/compare_ref.py 参考图.png 我的图.png -o cmp.png

# 6. 交付前检查
python3 scripts/check_delivery.py fig.pdf fig.eps
```

### 多工具联合示例

```bash
python3 scripts/demo_combined.py
# 卡通示意(svg_lib) + 物理公式(TikZ) + 合成(PyMuPDF) → PDF + EPS
```

---

## 目录结构

```
.
├── SKILL.md                     路由器：判任务 → 写 IR → 选后端 → 执行 → 验证
├── references/
│   ├── ir-spec.md               六层 IR 规范（物理/元素/构图/风格/执行/验收）
│   ├── svg-cookbook.md          SVG 技法 + 7 个渲染陷阱
│   ├── tool-selection.md        按图选工具（内容轴 × 风格轴）
│   ├── multi-tool.md            多工具联合 + 交付格式
│   ├── style-bench.md           风格量化与 4 个测量陷阱
│   └── gotchas.md               渲染静默失败详解
├── scripts/
│   ├── svg_lib.py               SVG 图元库（火球/圆柱/核子/壳/环/坐标轴/图层）
│   ├── geom.py                  shapely 布尔运算 → SVG path（外轮廓、有机团块）
│   ├── check_tools.py           工具能力探测 + 装机指引
│   ├── check_render.py          渲染静默失败检测（渐变失效/字体丢失都不报错）
│   ├── check_delivery.py        投稿检查（矢量？文字可编辑？字号达标？）
│   ├── compare_ref.py           参考图与成图并排对比
│   ├── style_bench.py           风格度量与基准比对
│   ├── auto_converge.py         自动收敛循环（量→定位→修正→复测）
│   ├── assemble_panels.py       复合图拼版（保矢量）
│   ├── extract_figures.py       从论文 PDF 自动切图
│   └── demo_combined.py         多工具联合示范
└── assets/
    ├── t3-exemplars/            8 张 T3 参考图（3D 示意图 + 光影）
    └── ir/                      3 套 IR 标准答案
```

---

## 四条硬纪律

写在 `SKILL.md` 里，是踩坑换来的：

1. **几何量必须【量】，禁止【看】**
   数量、角度、比例、坐标必须写脚本扫像素得出。
   *踩坑*：目测 T3-03 的径向线得出"48 条"，脚本一扫是 **40 条**。

2. **绘制顺序就是 z 序**
   后画的盖住先画的，画反了元素会**凭空消失且不报错**。

3. **风格指标是【诊断工具】，不是【优化目标】**
   指标告诉你往哪看，不告诉你调到多少。
   *踩坑*：按指标"整体降饱和+加深描边"，把不该压暗的平面也压暗，
   3 项指标反而恶化、视觉更差。
   正确流程：**量 → 判断 → 把指标对应的像素可视化、找到具体原因 → 只改那一处 → 复测 → 看图**。

4. **物理正确性无法自动验证**
   复现任务有参考图当 ground truth；创作任务**必须人看**。
   **不要说"自动达到 Nature 级"**——能说的是"把偏离量化、让失败可见"。

---

## 关于参考图的版权

`assets/t3-exemplars/` **只包含 CC-BY 开放获取的图**（STAR, Nature 2024），
其余参考图因版权原因**未随仓库分发** —— 详见
[`assets/t3-exemplars/NOTICE.md`](assets/t3-exemplars/NOTICE.md)，
里面有每张图的出处和获取方式。

自己建库：

```bash
python3 scripts/extract_figures.py 你的论文.pdf -o refs/
```

> **不要把版权受限的论文配图打包发布。** 这是使用本 skill 时容易踩的坑。

## 诚实的边界

这个 skill **不是**"一键出 Nature 级图"。

| 能做 | 不能做 |
|---|---|
| 从图/草图提取结构化 IR | 精确复现每个元素的位置 |
| 按图型选后端并调用 | 复现有机/程序化生成的形状 |
| 输出分层干净、可精修的矢量 | 达到"并排看不出差别" |
| 量化偏离、自动收敛到参数最优 | 突破参数空间能表达的上限 |
| 保证投稿合规（矢量、字号、可编辑） | 替代人的审美判断 |

**它提高下限、让失败可见，不替代人。** 最终质量判定仍需人看图。

按 Nature 官方美术指南，本来就没有"一步到位的成品"：各面板在各自软件做，
最后在矢量编辑器里合成，美术团队还可能重画。所以"能直接用"的准确含义是
**「输出的稿子在 Inkscape/Illustrator 里打开，不用重画、只需调整」**。

---

## 参考

- [Nature 美术指南](https://www.nature.com/nprot/for-authors/protocols) —
  线稿/示意图首选 AI / EPS / PDF，必须可编辑矢量
- [Nature 配图模板](https://research-figure-guide.nature.com/resources/templates/)

---

## License

MIT
