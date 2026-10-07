# 评测套件

两层，分别测不同的东西。

## ① 工具回归测试（机器可跑）

```bash
python3 evals/test_tools.py        # 39 个 case
python3 evals/test_tools.py -v     # 显示每个 case 防的是什么坑
python3 evals/test_tools.py geom   # 只跑名字含 geom 的
```

**每个 case 对应一个真实踩过的坑。** 不加 pytest 依赖（要能在 ChatGPT 沙箱里跑）。

| case | 防什么 |
|---|---|
| `geom_opposite_velocity` | 两核相向运动：dot<0 |
| `geom_back_to_back_final_state` | 两体末态背对背：dot<0 |
| `geom_no_overlap_upc` | UPC 两核不重叠：竖直间距 > 两核半径和 |
| `gate_deviation_metric` | 偏离要用【区间边界】归一，不是【区间宽度】 |
| `gate_catches_category_error_not_drift` | 范畴错误要阻断（黑白图），正常波动不许阻断（飘的指标没资格卡人） |
| `gate_uses_subclass_profile` | 门禁必须用【子类】档案 |
| `composition_catches_out_of_bounds` | 构图审计能抓到出界文字 |
| `composition_catches_text_overlap` | 构图审计能抓到文字重叠 |
| `render_detects_gradient_failure` | check_render 能抓到'渐变变纯黑' |
| `render_detects_missing_element` | check_render 的元素命中能抓到'字体丢失/元素被盖住'——防 z 序画反导… |
| `profile_stores_ranges_not_points` | 风格档案存【区间】(p25/p75)，不是单点中位数——因为同类的图本来就各不相同 |
| `profile_metrics_are_robust_only` | 只有【跨来源可比】的指标能进档案 |
| `tool_detection_gives_install_cmd` | 缺工具时要给【装机命令】+【装不了时的替代路径】 |
| `console_utf8_survives_piped_stdout` | Windows 上 stdout 被【管道/重定向】时 Python 改用 gbk 编… |
| `tool_detection_survives_missing_latex` | 没装 LaTeX 的机器上 kpsewhich 不存在 |
| `composition_oob_ignores_zero_area_sliver` | 出界判据要按 subpath 判 + 越界部分要有面积 |
| `ink_map_detects_coarse_stroke_interior` | ink_map 要把【粗笔画内部】判成墨迹 |
| `trim_border_removes_frame_and_is_idempotent` | trim_border 要裁掉生图模型稳定画的 1~2px 外框，且【幂等】（裁完再跑… |
| `element_of_accepts_float_predicates_and_tight_fallback` | 元素表的颜色条件要能返回【float 加分】（bool 仍按 +0.22 兼容） |
| `ref_leak_check_flags_copied_reference` | 要能量出『出图把参考图整幅抄了』：同一张图 r>=0.85/照抄、结构不同的图通过 |
| `ir_brief_accepts_list_params` | IR 里参数写成【列表】（三个箭头共用一个元素 -> cx: [0.175, 0.38… |
| `genbrief_style_mode_not_hardcoded_flat` | 生图简报的风格**不许写死成扁平矢量**：IR 的 style 段说要 3D（半写实 … |
| `gen_figure_survives_dead_seeds` | 生图时**单个 seed 的网络抖动不许打断整批**：防 seed 7 撞 Timeo… |
| `trim_border_bg_option_for_light_frame` | 外框可能是**两层**（1px 深线 + 1px 浅灰线 lum 244~249）：默… |
| `gradfit_never_drops_thin_strips` | 真渐变丢台阶块时，**细条（min(w,h)<3）一律不丢**：防浅色球面上的网格线（… |
| `gradfit_aradial_uses_group_transform` | aradial 渐变**不能用 gradientTransform**：cairosv… |
| `dump_elements_table_follows_out_png` | --elmap 的元素明细表要落在 out_png **旁边**，不许写进 cwd：防… |
| `gen_figure_content_ref_sent_as_is` | 构图参考（--content-ref）默认必须**原样送**（v4.7 起不降级） … |
| `genbrief_carries_element_material` | IR 的 `material:` 必须进简报（以前**整段丢**，只用 primiti… |
| `genbrief_lossless_render` | IR 里写了、简报里没有 = 从来没写过（编译器丢字段 = IR 白写） |
| `jet_path_asymmetry_catches_inverted_vertex` | 喷注淬火：穿过介质的【路径长度】必须机器量的出来 |
| `canvas_read_from_composition_not_silently_dropped` | 画布必须**只由 ir_canvas 读**：规范写 composition.canvas，旧代码读 figure.c… |
| `ir_brief_audit_probes_canvas_at_spec_position` | 无损体检的探针必须跟规范同位置：哨兵原来塞在 figure.canvas 下，所以… |
| `check_sketch_multi_image_json_and_pick_best` | 一次出多张要能**一次全查、机器排序、人眼只审入围的** |
| `check_sketch_composition_fidelity_floor` | 闸口以前只查「照抄参考图」，没人查「成品位图有没有沿用草图的构图」 |
| `gen_figure_requires_ref_and_records_prompt_extend` | 风格参考图是硬规矩（只给文字 -> 通用插画脸），缺了要直接报错 |
| `gen_figure_warns_when_size_ratio_differs_from_ir` | 同一张图两个比例就废了 IR 的归一化坐标：简报按 IR 声明写、API 按 -… |
| `gen_figure_backs_off_on_rate_limit` | 429/限流时**立刻重试只会再撞一次** |
| `check_delivery_bitmap_gate_survives_embedded_bitmap` | 投稿门禁 check_bitmaps() 引用了签名里没有的 page：纯矢量 PDF 全绿，**一旦有嵌入位图就 NameError 崩掉** —— 最该拦的场合门禁不在场 |

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
