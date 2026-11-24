# 双 SVG 交付：原生几何版与独立透明纹理版

**每张最终图默认同时生成两版 SVG；有作者指定交付范围时按作者要求。** 不能用同一文件改名冒充两版；也不能用过去的“像素修正层 + 编辑后停用修正”的中间试验冒充透明纹理版。两版来自同一份对象表、画布和标签清单。此处两个版本与草图的 A→E 档位无关。

| 文件 | 要保留什么 | 适合的编辑 | 不能承诺什么 |
|---|---|---|---|
| `<stem>_edit.svg` | 原来的完整原生几何、真渐变、独立阴影与真实文字 | 改轮廓、端点、配色、公式和对象关系 | 不承诺逐像素复刻原位图 |
| `<stem>_texture.svg` | 每个对象独立的前景颜色、alpha 和矢量纹理；背景与遮挡补完；真实文字 | 组的直接拖动、旋转和缩放，纹理随组变换 | 不承诺像素零差；改隐藏几何参考节点不自动重算显示纹理，须同步映射或重建 |

两版均保持纯矢量。纯代码重绘任务在两版中都用 [连续渐变](continuous-gradient-svg.md) 建立材质，细纹理版可增加对象内的柔边光斑、丝带或渐变深度。位图可用于测量、拟合与核对。隐藏部分按物理与可见形体合理重建，并注明。

## 1. 共同底稿

先按 [直接重绘流程](direct-svg-redraw.md) 建立对象表、叠放和完整几何。所有物理对象在两版中用相同的顶层 `id` / `data-element`，使用相同的 `viewBox` 与标签清单；背景底板可以单独作为 `background`。先做好原生几何版，再以它的轮廓、光影和物理关系重建纹理版。两版均保留 `<text>` / `<tspan>`。

## 2. 构建独立透明纹理

纯代码路线可以直接按对象生成颜色和 alpha。有合成参考图且需要匹配其半透明材质时，按下面的顺序分离前景。

1. **识别遮挡关系。** 核团、喷注、光晕、辐射、板面和文字不能按颜色混成一层。给每个对象登记自身轮廓、发光支持域、前后关系和完整覆盖范围。不要把模板的橙色阈值直接套给新题材。
2. **先补底层。** 对被前景覆盖的底层区域，延伸其原生几何、网格和光影。必要时把原来前景造成的阴影一起移除。示例是“完整椭球光照 + 可见区域低频色差场的延伸”，并在交界处羽化，避免留下旧喷注的影子或把白底拖进边缘。新图采用适合其材质和几何的方法，不要求全部用椭球。
3. **再反混合前景。** 按 back→front 的顺序，使用 `C = αF + (1−α)B` 与已重建的背景 B，约束求解前景 F 与 alpha。用原生光照、材质、边缘覆盖先验约束解，避免把原来的背景颜色烘进前景。不能仅把参考的已合成像素直接分组。模型不适用时逐区域调整，不能承诺自动恢复唯一的真实分层。
4. **补前景被挡区域。** 用完整锥体/球面/板面等的原生几何和材质补足不可见部分；不能让末端粒子簇从喷注上挖出洞。
5. **输出稳定图层。** 一个物理对象一个命名组；透明颜色和纹理放在这个对象内部，用真实 `fill-opacity` 或原生渐变，不含整幅参考图。示例将纹理写为 `data-role="intrinsic-RGBA-vector-texture"`。可以保留 `data-role="native-geometry"` 的参考控制组，但说明其是否实际驱动显示。后续普通 `transform` 不允许触发关纹理、换稿、重新归属背景或换材质。

## 3. 两版验收

- 原生几何版按原来的轮廓、光影、文字、3D/三轴物理与隐藏测试验收。
- 纹理版要看原位置、拖动后、隐藏底层后的预览；观察彩边、残留旧影、背景色污染与缺口。结构检查替代不了这个目检。
- 对纹理版实际只加 `transform="translate(dx dy)"`，其余对象内容、透明纹理、共享定义都保持不变；将对象单独导出透明 PNG，平移对齐后测 RGBA，记录渲染器与结果。结构通过后，边缘抗锯齿和整数舍入仍可造成微小渲染差异。再只设置一个底层对象 `display="none"`，确认前景保留自身颜色和完整形体。禁止用“自动停用修正”通过。
- 分别附两版与参考图的对照、PNG、所用源码与已知偏差。报告参考图原尺寸下的误差；整幅误差会被空白稀释，要同时看物体局部。不能因为参考原图已经通过检查，就跳过最终 SVG 的物理检查。
- 默认 PNG 按工作区要求等比导出（本工作区为 2336×1280）；像素差测试则用参考图/共同 SVG 的原尺寸。正式投稿仍导出需要的 PDF，并按既有门禁验收。

从 skill 根目录执行，ID 按本图替换：

```bash
python scripts/check_direct_svg.py out/figure_edit.svg
python scripts/check_direct_svg.py out/figure_texture.svg
python scripts/check_svg_pair.py --geometry out/figure_edit.svg --texture out/figure_texture.svg
python scripts/check_svg_pair.py --geometry out/figure_edit.svg --texture out/figure_texture.svg --edited out/drag.svg --changed quenched-jet quenched-fragments gluon-radiation --rgba-object quenched-jet
python scripts/check_svg_pair.py --geometry out/figure_edit.svg --texture out/figure_texture.svg --edited out/hide.svg --changed qgp-medium --kind display
```

`check_svg_pair.py` 比较顶层对象 ID、viewBox、真实文字和 SVG 引用，并核对试编辑只改变声明对象的 transform/display。显隐或变换可指向命名子组。RGBA 探针使用未被裁断的顶层对象，默认要求整数平移对齐后的逐像素相等。遇到渲染器量化差异，可加 `--rgba-report-only` 测原始及预乘 RGBA，结果作为诊断，仍需检查单对象与整张图。非整数移动、缩放和旋转用结构和外观验证。

## 4. 已跑通的喷注图示例

[双版入口](../assets/examples/dual-svg/make_jet_pair.py) 一次运行两种方法：
[原生椭球与锥体](../assets/examples/dual-svg/jet_geometry.py) →
[独立透明纹理](../assets/examples/dual-svg/jet_layers.py)。
[示例验证](../assets/examples/dual-svg/verify_jet_pair.py) 记录拖动 RGBA 与参考图误差。
原有 [火焰火球](../assets/examples/direct-svg/jet_fireball.py) 和 [反应平面](../assets/examples/direct-svg/jet_plane.py) 的原生重绘源码继续保留。

```bash
python assets/examples/dual-svg/make_jet_pair.py --reference path/to/reference.png --outdir out/jet_pair --stem jet
python assets/examples/dual-svg/verify_jet_pair.py --reference path/to/reference.png --outdir out/jet_pair --stem jet
```

这个示例对应 1522×848 的椭球 QGP、双喷注和粒子簇图，带有该图的坐标、支持域和材质约束。**它不是任意图片一键转分层的通用模型**；换图时先重新拆对象，重写其几何与分离配置，再同时生成两版。例子不自带参考图，调用时传作者提供的那张原图。依赖：`numpy scipy Pillow cairosvg`。示例代码不是生图风格参考。
