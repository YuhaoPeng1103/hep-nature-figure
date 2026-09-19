# 变更记录

## v1.0 — 2026-09-19

首个版本。从零构建，全部结论来自实测。

### 核心方法
- **六层 IR**（物理 / 元素 / 构图 / 风格 / 执行 / 验收）+ **geometry_constraints 层**
- **按图选后端**：svg_lib / matplotlib / TikZ / Blender / ROOT / 多工具联合
- **两道门禁**：全局风格收敛 + 局部构图审计

### 关键的事实测结论（都写进了 SKILL.md 的硬纪律）
1. **几何量必须量，禁止看** —— 目测径向线 48 条，脚本实测 40 条
2. **绘制顺序就是 z 序** —— 画反了元素凭空消失且不报错
3. **风格指标是诊断工具，不是优化目标** —— 整体调会把不该动的地方也调坏
4. **物理正确性无法自动验证** —— 只能靠可判定的几何约束 + 人看
5. **不要把版权受限的图打包发布** —— 推之前逐张查许可

### 工具（18 个）
生成类：`svg_lib` `geom` `demo_combined` `demo_jet_quenching` `demo_timeline` `demo_upc_color`
验证类：`delivery_gate` `audit_composition` `audit_panels` `check_delivery` `check_render` `style_bench` `style_profile`
流程类：`check_tools` `auto_converge` `compare_ref` `assemble_panels` `extract_figures`

### 评测
- `evals/test_tools.py` —— 13 个机器可跑的回归测试，每个对应一个真实踩过的坑
- `evals/evals.json` —— 14 个行为评测 case，27 条可勾选断言

### 风格档案
T1 / T2 / T3 / T3-插画 / T3-线稿 / 未分类 —— **只存测量数字，不含原图**（版权干净）

---

## 踩过的坑（按发现顺序）

| # | 坑 | 教训 |
|---|---|---|
| 1 | PyMuPDF 渲染 SVG → 渐变全黑 | 必须用 cairosvg |
| 2 | cairosvg 不做字体回退 → 中文静默丢失 | font-family 只写一个存在的字体 |
| 3 | 无单字体兼有中文+Unicode 下标 | 按字符集分字体 |
| 4 | `baseline-shift` 被忽略 / 百分比字号解析错 | 用 dy + 绝对字号 |
| 5 | `text-anchor:middle` + tspan → 锚点算错 | 居中文案用 Unicode 下标 |
| 6 | 水平线的 linearGradient 退化 → 箭杆不渲染 | 细长线不能用渐变描边 |
| 7 | `markerUnits` 默认随线宽缩放 → 粗箭头长巨三角 | 改 userSpaceOnUse |
| 8 | 复合图的矢量验证不能用 `get_drawings()` 计数 | 面板是 XObject，看 `get_images()==0` |
| 9 | 指标对分辨率/出处敏感 | color_richness、gradient_ratio 不可跨来源比 |
| 10 | 拿 2-panel 参考图比 1-panel 复现图 | 比对前先确认同范围 |
| 11 | 归一化不对称（大图被降采样） | 归一到同一像素尺寸再测 |
| 12 | 门禁偏离度量选错分母 | 用区间边界，不用区间宽度 |
| 13 | 类没拆对 → "修一个坏一个" | T3 要分插画型/线稿型 |
| 14 | 全局指标测不到局部问题 | 必须加构图审计 |
