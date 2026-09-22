> # 📌 本分支 = 版本 B2（最新）：生图 + 成品位图
>
> 两次生图：先出「更好的草图」检查，再出成品位图，然后临摹成矢量。**观感最好，但可复现最差。**
>
> 另外两个版本在别的分支：
> | 分支 | 路线 | 特点 |
> |---|---|---|
> | `main`（= 本分支） | **B2**：生图 + 成品位图 | 观感最好，但两次生图、可复现最差 |
> | `route-a` | **A**：模型直接写 SVG | 约束最紧、可复现最好，**默认推荐** |
> | `route-b1` | **B1**：生图当草图 | 质感和可控的折中 |
>
> ```bash
> git clone -b <分支名> https://github.com/YuhaoPeng1103/hep-nature-figure.git
> ```

---

# hep-nature-figure

**高能核物理期刊级配图 Skill** — 从参考图或手绘草图，产出**可编辑的矢量配图**。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 这个 skill 解决什么问题

做科研配图的痛点不是"不会画"，是**花太多时间画**；而且 AI 直接画往往
**"花里胡哨但物理表达不准确"**。

本 skill 的做法：**在动手之前，先把"这张图在物理上表达什么"写成结构化的 IR**，
画完再用**可判定的门禁**验收。

---

## ★ 分工：谁画、谁约束、谁验收

**画图交给模型，本 skill 负责约束、验收、返修。**

| 环节 | 谁做 | 为什么 |
|---|---|---|
| **画** | **模型** | 有视觉先验，能做出代码拼不出的质感 |
| **约束** | **IR + `geometry_constraints`** | 防"好看但物理错"——模型单干最爱犯 |
| **验收** | **三道门禁** | **模型看不见自己的输出**，这里能量 |
| **返修** | **`repair_brief.py` → 模型改** | 光说"文字重叠"模型只能猜；返修单给归一化坐标 + 具体改多少 |

> **不要试图用代码把图"画好看"** —— 那条路性价比极低。
> 代码该干的是**把模型的输出卡对**。

### 实测证据（外部 A/B）

同一张草图、同一个模型，只差"用不用本 skill"：

| | 不调用 skill | 调用 skill |
|---|---|---|
| 观感 | 一样漂亮 | **一样漂亮** |
| 几何约束 6 项 | **过 2 项** | **过 6 项** |

不调 skill 那版的具体违规：加了 IR 禁止的装饰元素、喷注端点出界、
胶子辐射画在了两条喷注上（应只有淬火那条）、两喷注夹角 173°（应 180°）、
**表面偏置丢了**（|v−C|/R = 0.85，应有 0.72 —— 而这是整张图的物理）。

---

## 完整流程

```
输入（参考图 / 草图 / 描述）
   ↓
① 写 IR —— 物理层 + 元素 + 构图 + geometry_constraints
   ↓
② 选路线产生内容
   A  模型直接写 SVG         B1 生图当草图 → 检查 → 绘画         B2 B1 + 成品位图
   ↓
③ ★ 确定性重组（三条路在这里汇合），两种粒度：
   对象级：模型看懂 → 写 Scene Graph → scene_render.py 重组 → SVG
   像素级：位图 → raster_to_vector_semantic.py（自动切分定形状 + 人写元素表命名）→ SVG
   两者的同一份输入两次跑 → 逐字节相同的 SVG
   ↓
④ 三道门禁 + 返修单 → 交付（SVG 工作稿 + PDF 交付稿）
```

**为什么要有第 ③ 环**：「位图 → 矢量」这一步，像素描摹**没有理解**
（文字碎成色块、渐变退化成色阶），而让模型直接重画**不忠实、不确定**
（漂移、自己发明）。所以拆开：**人/模型负责看懂，代码负责重组。**

**两种粒度各管一摊**：图能拆成图元（圆/圆柱/箭头/轴）就用 Scene Graph，
渐变是**真** `<gradient>`；图是渲染质感（光照/体积/有机纹理）就用
`raster_to_vector_semantic.py`，忠实度最高但渐变换成色阶台阶。见下节。

---

## 三条路线，怎么选

|  | **A：模型写 SVG** | **B1：生图当草图** | **B2：B1 + 成品位图** |
|---|---|---|---|
| 流程 | IR → 模型直接写 SVG → 门禁 | IR → 生图简报 → 草图 → 检查 → 绘画 | B1 + 成品位图 → 先理解再临摹 |
| 观感 | 教科书插画 | 中 | **最好** |
| 可复现 | 较好 | 中 | **最差**（两次生图） |
| 物理把关 | IR 全程 | 生图后要核 | 两道闸口 |
| 成本 | 低 | 中 | 高 |

- **默认走 A**：约束最紧、可复现最好
- **要质感走 B1**：`ir_to_genbrief.py --stage sketch` → 生图 → `check_sketch.py`
- **B2 只在 B1 明显不够时上**：多一次生图，也多一次漂移机会
  （临摹那步本身是确定性的，漂移只来自生图）

> ⚠️ **可复现性尚未验证**：同 prompt 两次输出是否一致，决定这条路能否做**交付**
> 而不只是**出稿**。这是当前最大的未解问题。

---

## 位图 → 矢量（临摹）

两条临摹路，**按图的类型选**：

| | `raster_to_vector.py`（逐像素描摹） | **`raster_to_vector_semantic.py`（先理解再临摹）** |
|---|---|---|
| 文字 | 模型写 `--text-spec` → 擦掉重写 | **真 `<text>`**（OCR 词表 + 逐词对齐 + 擦原笔画） |
| 图层 | 按**颜色**分，`--groups` 可归组 | 按**物理元素**分（fireball / nucleons / jets / surface …） |
| 渐变 | 退化成色阶台阶 | 色阶台阶，但**误差可量化可调**（`--R`） |
| 验收 | 要自己量 | MAE / PSNR / `--check` 回渲染 |
| 复现 | 逐字节相同 | **逐字节相同**（已实测三次） |
| 依赖 | cv2 / skimage | numpy / scipy / Pillow / cairosvg / cairocffi / fontTools |

实测（T3-01 Jia2026 Fig.1，1200×1133，4.7 MB）：

| 指标 | 值 |
|---|---|
| 非文字区（纯矢量色块）MAE / >32 色阶像素 | **0.227** / **0.00%** |
| 整图 MAE / PSNR | 1.48 / 26.5 dB |
| `<path>` / `<text>` / `<image>` | 37930 / 54 / **0** |
| 图层 | 12 面板 / **50 物理元素** |

```bash
# ① 出词表（Windows.Media.Ocr，自动 2× 放大）
powershell -File scripts/raster_vector/ocr_words.ps1 -Image fig.png -Out words.txt
# ② 照着 scripts/raster_vector/panels.py 改出这张图的 CELLS / ELEMENTS / SPLIT
# ③ 组装 + 自检
python3 scripts/raster_to_vector_semantic.py fig.png -o fig.svg --words words.txt \
        --panels my_panels.py --legend fig_layers.md --elmap fig_el.png --check
```

> ★ **要人写两张每图各不相同的表**：`words.txt`（OCR 词表）和 `panels.py`
> （面板框 + 物理元素框 + 颜色条件）。自动切分只负责"形状对不对"，
> **"这块叫什么物理名字"必须人来写** —— 这是它比纯描摹贵的地方，也是它准的地方。

> ⚠️ **做不出真渐变网格**。原图的连续渐变在矢量里只能是色阶台阶
> （调小 `--R` 变细，代价是路径数/体积）或真 `<gradient>`（要求图能拆成图元）。
> 只适合「色块 + 硬边」类图（示意 / 三维渲染示意图）；照片、有机纹理不适合。

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
pip install -r requirements.txt
# 或手动：
pip install numpy pillow cairosvg pymupdf matplotlib scipy shapely \
            pyyaml opencv-python
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
│   ├── raster_to_vector.py      位图 → 矢量（临摹主路径）：逐像素 + 混合文字 + --groups
│   ├── raster_to_vector_semantic.py  ★ 位图 → 语义分层的全矢量 SVG（先理解再临摹）
│   ├── raster_vector/           上面那条的库（quadtree/labels/elements/panels/groupvec）
│   ├── compare_ref.py           参考图与成图并排对比
│   ├── style_bench.py           风格度量与基准比对
│   ├── auto_converge.py         自动收敛循环（量→定位→修正→复测）
│   ├── assemble_panels.py       复合图拼版（保矢量）
│   ├── extract_figures.py       从论文 PDF 自动切图
│   └── demo_combined.py         多工具联合示范
└── assets/
    ├── t3-exemplars/            参考图库（含 2 张 CC-BY 图 + 版权说明）
    └── ir/                      3 套 IR 标准答案
```

---

## 五条硬纪律

写在 `SKILL.md` 里，是踩坑换来的：

0. **不要把版权受限的图打包发布**
   建参考图库前先看许可：CC-BY 可再分发（需署名），
   CC-BY-NC / 版权保留只能内部用。
   *踩坑*：本仓库最初打包了 8 张参考图，推之前查证才发现
   5 张来自 Springer Nature 综述和 Nature 非 OA 文章，已改为只留 CC-BY。

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

> 其中「精确复现位置」这一条，`raster_to_vector_semantic.py` 对**平色块图**已经做到
> （非文字区 MAE 0.227、>32 色阶像素 0.00%）。它做不到的是**连续渐变的平滑**
> —— 矢量里只能是色阶台阶，或真 `<gradient>`（后者要求图能拆成图元）。

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
