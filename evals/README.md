# 评测套件

两层，分别测不同的东西。

## ① 工具回归测试（机器可跑）

```bash
python3 evals/test_tools.py        # 13 个 case
python3 evals/test_tools.py -v     # 显示每个 case 防的是什么坑
```

**每个 case 对应一个真实踩过的坑。** 不加 pytest 依赖（要能在 ChatGPT 沙箱里跑）。

| case | 防什么 |
|---|---|
| `geom_opposite_velocity` | 两核箭头画反（渲染图看不出来） |
| `geom_back_to_back_final_state` | 末态同向，违反动量守恒 |
| `geom_no_overlap_upc` | UPC 画成普通碰撞 |
| `gate_deviation_metric` | 偏离度量选错分母 → 量级错误被当轻微偏离 |
| `gate_escalates_category_error` | 黑白图通过门禁 |
| `gate_uses_subclass_profile` | 拿合并类当目标 |
| `composition_catches_out_of_bounds` | 标签被裁但全局指标全绿 |
| `composition_catches_text_overlap` | 文字重叠 |
| `render_detects_gradient_failure` | 渐变变纯黑 |
| `render_detects_missing_element` | z 序画反导致元素消失 |
| `profile_stores_ranges_not_points` | 风格档案存单点而非区间 |
| `profile_metrics_are_robust_only` | 把出处敏感的量当目标 |
| `tool_detection_gives_install_cmd` | 缺工具时不给装机命令 |

> **为什么需要它**：没有回归测试时，改一个工具会悄悄弄坏另一个 ——
> 这正是"修一个坏一个"的根因。

## ② 行为评测（需 agent 跑）

`evals.json` —— 14 个 case，测 **agent 使用本 skill 时的行为**。

每条断言都可勾选判定，每条都来自真实踩过的坑：

| case | 测什么 |
|---|---|
| `no-hardcoded-style-use-target` | 风格从目标提取，不写死 |
| `ir-required-before-drawing` | 不跳过 IR |
| `geometry-must-be-measured-not-eyeballed` | 几何量必须量 |
| `missing-tool-means-install-not-workaround` | 缺工具去装，不绕开 |
| `geometry-constraints-catch-physics-errors` | 物理错靠约束抓 |
| `metrics-are-diagnostic-not-objective` | 指标是诊断不是目标 |
| `subclass-profile-not-merged` | 用子类档案不用合并的 |
| `local-composition-audit-required` | 全局过了还要查局部 |
| `z-order-draw-sequence` | 先怀疑 z 序 |
| `compare-same-scope` | 比对前先确认同范围 |
| `copyright-before-bundling` | 打包前查许可 |
| `no-substitute-for-reproduction` | 不用图像生成冒充复现 |
| `do-not-trigger-statistics-only` | 边界：纯统计不触发 |
| `do-not-trigger-photo-edit` | 边界：纯照片编辑不触发 |

### 怎么用

对照 `prompt` 给 agent，检查它的行为是否满足全部 `assertions`。
不需要全部通过才算数——**失败的 case 就是 skill 需要改的地方**。
