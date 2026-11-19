# 直接重绘可编辑 SVG（原生几何版）

**默认：参考图 → 对象和遮挡关系 → 原生 SVG → 回渲染和试编辑。** 作者已给定成品图并要求重绘 SVG 时，直接从第一步开始；不重新生图、跑草图阶梯或制作临摹中间稿。若任务本来要创作并生成成品位图，先走已有草图、作者选择、位图精修和物理检查，再把已确认的位图作为参考。

1. **量构图，列对象。** 先看参考图，登记画布比例、面板框、物体特征点、共同顶点、轴方向和文字锚点；按「对象 ID / 几何参数 / 谁在前谁在后 / 被挡处怎么延伸 / 材质 / 标签」记简表。复杂图按面板建局部坐标。核对 IR 的硬物理；给定的参考图与物理或数据冲突时明说，不能默默把它抄错或改掉。
2. **先画整体几何，再做光影。** 逐件写 SVG 或为这张图写 `draw.py` 输出 SVG。球用圆/椭圆或投影生成的核子簇，火球用一条可编辑的闭合 Bézier，管体用连续侧壁和端帽，反应平面用一块完整四边形与贯穿网格。箭头/辐射用独立路径。先定边界、端点和图层叠放，再加真 `linearGradient` / `radialGradient`、半透明彩色路径、独立阴影。颜色不是图层。复杂光纹可以用固定种子的矢量涡旋、光斑和弯曲丝带近似，别把像素色块堆当纹理。
3. **补画遮挡后仍应存在的部分。** 用可见两端、整体形体及物理关系延伸底层：网格穿过火球下方，轴线或喷注保留连续路径，核子簇、火球、辐射各有独立几何。正常遮挡靠 SVG 叠放实现，别从底层挖出前景的洞。内部纹理可以用自身轮廓的 `clipPath`，尽量与轮廓共享一份源路径；不能用邻居的可见像素掩膜裁断整个物体。实在不能从参考推知的部分，记为示意补全。合成/相关曲面能按机理或参数近似；没有数据就不声称还原数值。
4. **组织源文件。** `<g id="…" data-element="…">` 一组一个能独立选择、移动和改色的物体，需要时加 Inkscape 命名层。阴影、纹理和外部标签按编辑需求分层。文字用 `<text>` / `<tspan>`，检查公式、上下标、字体。本步出 `<stem>_edit.svg`，再按双版流程输出 `<stem>_texture.svg`；两版都交源码与 PNG；正式投稿仍按该任务导出 PDF 并过既有门禁。SVG 按参考比例设 viewBox；工作区若要求 2336×1280 PNG，等比导出并补白。原图只作参考，交付 SVG 不嵌它。
5. **回渲染，再做一次真编辑。** 看「参考图 | SVG 回渲染」对照：核对位置、叠层、质感、标签和物理。再隐藏或移走至少一个关键重叠物体，实际重渲染，确认应该露出的网格/喷注等仍完整、另一侧的对象未被拖走。若对象从未重叠，移动或改色一个对象，核对邻居不变。最后把画面恢复原状，留下核对结果。结构检查能抓缺层、断引用、嵌位图；它不能代替观察遮挡或判断物理。

## 同时输出独立透明纹理版

默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。 本页的几何方法保留；完成后按 [双 SVG 制作与验收](dual-svg.md) 分离透明颜色和补全被挡部分。不能用关闭修正或自动换稿来通过拖动测试。

## 可执行示例

[`assets/examples/direct-svg/jet_fireball.py`](../assets/examples/direct-svg/jet_fireball.py) 是火球图的实际绘制源码。查看 `qgp-outline`、纹理剪裁、两束完整喷注、软渐变和辐射细丝。[`assets/examples/direct-svg/jet_plane.py`](../assets/examples/direct-svg/jet_plane.py) 是反应平面图的源码：完整网格、独立阴影、渐变核子、喷注、辐射弧和坐标轴。示例目录放的是绘制代码，只为阅读和复跑，并非生图风格参考。把脚本复制到输出目录再运行；依赖 `cairosvg`，火球示例还用 Pillow。

从 skill 根目录执行（以下假设示例生成的文件在当前目录；可传实际路径）：

```bash
python scripts/check_direct_svg.py jet_fireball_edit.svg --require qgp-medium escaping-jet quenched-jet radiation labels --hide qgp-medium --hidden-png fireball_hidden.png
python scripts/check_direct_svg.py jet_plane_edit.svg --require reaction-plane cast-shadows qgp escaping-jet quenched-jet --hide qgp cast-shadows plasma-partons --hidden-png grid_revealed.png
python scripts/preview.py fireball_hidden.png grid_revealed.png
```

这两组试编辑应当分别露出完整的两束蓝色喷注，以及原本在 QGP 下方的贯穿网格。示例用 CairoSVG 可重渲染；如遇渐变、剪裁、字体等渲染器差异，以交付软件的导出和目检为准。避免用滤镜做需要原生矢量的发光；透明边缘可叠数层不同宽度、低透明度的描边。遇到 CairoSVG 忽略 `<use opacity>`，把透明度放到外层普通 `<g>`。

## 何时用旧路

只有作者指定像素级复刻、要求跑旧算法对照，或已有临摹资产需要维护时，才走 [临摹备用流程](bitmap-to-vector.md)。它能复现可见颜色，不能靠可见像素自动得到被遮住的几何；即使用拾取层包住碎路径，也不能替代几何试编辑。像素误差在保真任务可作辅助或专项判据；直接重绘以结构、物理、外观和可编辑性验收。作者草图的快速矢量交接仍可用 `sketch_to_vector.py`，不等于最终 SVG。
