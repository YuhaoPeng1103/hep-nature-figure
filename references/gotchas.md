# SVG 光影路线技术验证报告

**日期**：2026-09-18
**目的**：验证项目最高风险假设——纯 Python 生成的 SVG 能否做出 Jia Fig.1 那种
「渐变阴影 + 半透明发光 + 3D 形体」的期刊级示意图。
**结论**：✅ **可行**。且踩出 7 个必须提前知道的坑，全部有解。

验证代码：`svg_shading_demo.py` ｜ 输出：`svg_demo/`（含 PNG、SVG、HTML）

---

## 一、验证结果

三个场景全部通过：

| 场景 | 技法 | 结果 |
|---|---|---|
| 渐变阴影圆柱 | `linearGradient` 柱面明暗 + 高光条 + 椭圆端面 + 贝塞尔波形轮廓 | ✅ 达到 Jia Fig.1b 观感 |
| 半透明发光火球 | `radialGradient` 三层叠加（外晕/本体/内核高光）+ 半透明介质椭球 | ✅ 达到 Jia Fig.1c 观感 |
| 3D 曲面 | 手写斜投影 + 逐格填色（HSV 色相映射）+ 画家算法排序 | ✅ 可行（但 matplotlib 更省事） |

**关键**：全程只用 Python 标准库拼字符串，**零第三方依赖**——保证在 ChatGPT
沙箱里必然可跑。

---

## 二、七个坑（按踩到的顺序）

### 坑 1：PyMuPDF 不能渲染 SVG 渐变

**现象**：`url(#grad)` 填充全部渲染成纯黑，形状/描边/文字正常。
**最小复现**：一个带 `linearGradient` 的 `<rect>`，PyMuPDF 取中心像素 = `(0,0,0)`。

**结论**：MuPDF 的 SVG 渲染器不支持渐变。**不是 SVG 写错了。**

```python
# ❌ 不要用
import fitz; fitz.open("x.svg")[0].get_pixmap()
# ✅ 用 cairosvg
import cairosvg; cairosvg.svg2png(url="x.svg", write_to="x.png")
```

> 幸运的是 PyMuPDF 渲染**它的强项是 PDF**，本项目的 PDF 审计工具（碰撞/对齐检测）
> 仍然可用。只是别拿它渲 SVG。

### 坑 2：cairosvg 不做字体回退

`font-family="Helvetica, Arial, SimHei, sans-serif"` → **只认第一个**，找不到就
静默回退到 DejaVu，缺字也不会报错，直接丢。

**规则**：`font-family` 只写一个**确实存在且覆盖所需字符**的字体。

```python
FONT_CJK   = "SimHei"       # 中英混排（SimHei 拉丁字形一般，但够用）
FONT_LATIN = "DejaVu Sans"  # 纯英文期刊图，接近 Helvetica，希腊字母齐全
```

### 坑 3：没有单一字体同时具备「中文」和「Unicode 下标」

实测（`fc-list :lang=zh` 共 14 个中文字体）：

| 字体 | 中文 | `ε₂` 的 ₂ |
|---|---|---|
| DejaVu Sans（默认） | ❌ 豆腐块 | ✅ |
| SimHei / 微软雅黑 / Droid Sans Fallback | ✅ | ❌ 豆腐块 |
| FandolHei / NSimSun | ✅ | ❌ |
| Noto Sans CJK SC / 文泉驿 | 未安装 → 回退 DejaVu | — |

**规则**：按字符集分字体。**期刊图是纯英文**，用 `DejaVu Sans` + Unicode 下标
（₂₃₁）最省事，不要用 tspan。

### 坑 4：`baseline-shift` 被忽略

```svg
<!-- ❌ 下标不掉下去，等同无效 -->
<tspan baseline-shift="sub">2</tspan>
```

### 坑 5：`font-size="70%"` 百分比解析错误

**现象**：tspan 里的字被渲染成巨大黑块。
**规则**：tspan 内必须用**绝对字号**（如 `font-size="9.1"`），不能用百分比。

### 坑 6：`text-anchor="middle"` + `<tspan>` 锚点算错

**现象**：居中文本里含 tspan 时，锚点计算把后续文字串到别处
（实测出现 `η)Triangularity: ε` 这种错位）。

**规则**：
- 居中标签 + 下标 → 用字体自带的 Unicode 下标字符（见坑 3），**别用 tspan**
- 必须用 tspan 时 → 只用 `text-anchor="start"` 并手动给 x

### 坑 7（正面）：cairosvg 可以直接输出矢量 PDF

```python
cairosvg.svg2pdf(url="fig.svg", write_to="fig.pdf")
```

实测输出：75 条矢量绘制指令，字体被子集化内嵌（`AWSMGL+TeXGyreHeros-Regular`）。
**矢量的、文字可编辑、可投稿——这就是最终交付路径。**

⚠️ 注意：用 `SimHei` 等中文 TTF 时字体会被**转成轮廓或子集内嵌**，
投稿前需确认目标期刊是否接受。**期刊图建议纯英文 + DejaVu/Helvetica。**

---

## 三、固化的工具函数

```python
def sub(s, rest="", base=13.0):
    """下标。仅用于 text-anchor='start'；居中文案请改用 Unicode 下标字符。"""
    dy = base * 0.28
    return (f'<tspan dy="{dy:.1f}" font-size="{base*0.7:.1f}">{s}</tspan>'
            f'<tspan dy="{-dy:.1f}">{rest}</tspan>')
```

```python
def wavy_cylinder(cx, cy, w, h, amp, waves, phase, squash=0.18):
    """带波形起伏的 3D 圆柱。squash 是椭圆端面的扁平度——这是 3D 感的关键：
    纯正椭圆端面让平面图形立刻有透视。"""
```

```python
def fireball(cx, cy, r):
    """三层叠加：外晕(softer模糊) / 本体(radialGradient) / 内核高光。"""
```

---

## 四、对项目的影响

1. **T3（3D 示意图 + 光影）风险解除** —— 这是项目最大的未知数，现已证明可做。
2. **技术栈确定**：Python 标准库拼 SVG → cairosvg 出 PNG/PDF。零依赖，
   ChatGPT 沙箱和本地都能跑。
3. **需要给 ChatGPT 的 Instructions 写死字体规则** —— 否则它会默认写
   `font-family="Arial, sans-serif"` 然后中文全丢、渐变全黑，且**不报错**。
   这是最危险的失败模式：静默错误。
4. **建议加一道自动校验**：生成 SVG 后，检查渲染结果的非白像素分布，
   或至少检查「应出现文字的位置是否真的有墨」——防止字体丢失静默通过。

---

## 五、还没验证的

| 项 | 风险 | 何时验证 |
|---|---|---|
| ChatGPT 沙箱里是否有 cairosvg | **高**——若没有，只能下载 SVG 本地渲染 | 能力探针 |
| ChatGPT 能否输出可下载的 .svg/.pdf | 高 | 能力探针 |
| 复杂 SVG（数百图层）的渲染性能 | 低 | T3 实战时 |
| 3D 曲面用 matplotlib 还是手写 SVG | 低 | T2 实战时定 |

> 前三项用 `nature-figure-拆解与借鉴方案.md` §7 的能力探针 prompt 一次性测掉。
