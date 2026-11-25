# 路线 B：图像生成 —— 可执行全流程（2026-09-26 重写）

> 本文件由 `SKILL.md`（v4.24）下沉，完整保留「路线 B：图像生成」全流程原文。
> 文中的 `references/...`、`scripts/...` 路径都相对于 **skill 根目录**。

适合**质感优先**的图。**默认走这条路。** 完整命令链：

```bash
# ── 0. 写 IR（强制，见「路由协议 2」）────────────────────────
#    IR 就是"完善后给模型的 prompt"，它约束生图质量。

# ── 1. IR → 约束简报 ──────────────────────────────────────
python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage sketch -o brief1.md
#
#    ★★ v4.2 起，**默认先走「极简首轮 + 增量补约束」**（作者 2026-10-05 要求）：
#       别一上来就灌几 k 字符的规格书；先给「一句话 + 面板序列」，物理错的地方下一轮再补，
#       一次只补**错的那几条**（对了的不重复写）。
#
#         python3 scripts/brief_lite.py ir/xxx.ir.yaml --tier 0 --size 2048*704 -o gen/lite0.md
#         #   → 出图（照第 2 步）
#         #   → 看图 + 闸门，把**画错**的点写进 gen/round0_fail.md（一段话，不是重发规格书）
#         python3 scripts/brief_lite.py ir/xxx.ir.yaml --tier 1 --size 2048*704 \
#             --add gen/round0_fail.md -o gen/lite1.md
#
#       tier 0 = 一句话 + 画布/面板序列 + 输出硬约束   （实测 QGP：548 字符，原规格书 7559）
#       tier 1 = tier 0 + 3D 空间线索 + 每面板一句形态（实测 QGP：1427 字符）
#         ★ v4.4：3D 线索 = 通用 4 条（板/接触阴影/三轴/光源）+ 火球、核子球团两条按 IR 关键字条件追加（实测：牛顿/法拉第 4 条、UPC 5 条、QGP 6 条）
#       一句话取 IR 的 figure.one_liner（推荐自己写一句），没有就退回首句 physics_claim。
#       为什么不做成"自动把失败约束全塞进去"：增量要人判断（看上一轮的图 + 闸门报告），
#       工具只负责把增量拼进简报。
#
#    ★ 实测（QGP，2026-10-05，qwen-image-3.0 mm，同两张风格参考）：
#       极简档的画面**更接近** Gemini 那类"好看"，但**物理并没有自动变对**——
#       tier 0 那轮照样把 z 轴与运动方向画反、核没被压扁；补了增量约束的 tier 1 才把
#       「薄饼方向 / 板面三轴 / 色场管取向」做对（3D 闸门：tier0 1/2 过，tier1 1/2 过，
#       但 tier1 通过那张的板面占比 4.9% vs tier0 的 0.40%）。
#       → "提示词短 = 画面好看" 与 "物理对" 是两件事，前者靠生图模型，后者只能靠增量约束 + 闸门。
#
#    ★ v4.25：D 档的“错”= 上一轮 check_sketch 人工项里所有答“否”的硬物理（HP1–HP6），
#      不是只写自己注意到的那两条。漏一条，模型就会按“其余原样保留”把它保住
#      （实测 UPC：D 档只写 beam/b，黄色 QGP 椭圆被完整保留；D2 点名删除后才消失）。
#    ★ v4.25：B/C/D 只要用整幅风格参考图，简报必须有【参考图自带、本图不要】一节，
#      逐条点名风格图里的物理对象（如“黄色椭圆 QGP 火球 + 放射箭头”）。ladder_gate L14 硬判 D 档。
#    ★ 整幅风格图带错误物理时，可用同一本风格书抽出的材质卡当 --ref；L7 用
#      --ladder-waive "ref_is_material_card_from_same_stylebook" 放行，理由写进交付说明。
#    ★ 完整规格书（本行下面这条）留给**复现论文图**这类必须逐条对账的 A 类任务。

# ── 2. 出草图（★ 必须带风格参考图；key 用你自己的）──────────
python3 scripts/gen_figure.py --brief brief1.md --stage sketch \
    --ref refs/T3-33.png --seeds 1,2,3 --outdir gen/
#   产物：gen/sketch_s1.png、gen/sketch_prompt.txt、gen/calls.jsonl
#   ★ 模型**稳定**在四周画 1~2px 外框：简报里写「不要外框」没用、
#     --negative 加 border/frame/picture frame 也没用（实测 5/5 全有框）
#     → 别求它，确定性裁掉；后面所有步骤都用 *_clean.png：
#   ★ 外框可能是**两层**（1px 深线 + 1px 浅灰线 lum 244~249）：默认阈值只认深线，
#     浅灰线会留下来变成多余细边 → 这种图加 --bg 0.975 再裁一次
#     （实测 2026-09-27：形变核→火球 算例，下 2px + 右 1px 就是这么裁掉的）。
python3 scripts/trim_border.py gen/sketch_s1.png -o gen/sketch_s1_clean.png

# ── 3. 草图矢量化输出（人可改）────────────────────────────
python3 scripts/sketch_to_vector.py gen/sketch_s1_clean.png -o gen/sketch_s1.svg --ocr
#   不用写 panels.py：草图靠自动切分，每个形体一个子层（part-01…）
#   ★ 默认 --q 16（每通道颜色量化级数）。草图边缘的抗锯齿会切出数万条碎路径，
#     量化后才能“给人改”。实测：0->30412 条/MAE 0.376；16->2111 条/MAE 1.102
#     （>8 色阶像素 0.31%，与不量化的 0.32% 持平，但路径少 14 倍）。要更精就 --q 0。

# ── 4. ★ 闸口①：草图过物理检查（不能跳）────────────────────
python3 scripts/check_sketch.py gen/sketch_s1_clean.png --ir ir/xxx.ir.yaml
#   ★ 一次出了多张备选？**一次全喂进去** + 落 json，再自动排序挑图
#     （人眼只审没有硬伤的 —— 实测 UPC：8 个 seed 只有 3 张合格）：
#     python3 scripts/check_sketch.py gen/sketch_s*_clean.png --ir ir/xxx.ir.yaml \
#         --json gen/check1.json
#     python3 scripts/pick_best.py gen/check1.json

# ── 4.5 ★★ 交接点（v3.0）：多张草图 → 让用户挑 / 让用户改 ──────
#   ★ 默认**停下来**。草图是全链最便宜的返工点，而 "哪张更像你要讲的物理" 只有作者知道；
#     pick_best 负责把没硬伤的排前面（机器能做的都做了），拍板是人做的事。
python3 scripts/sketch_handoff.py gen/sketch_s*_clean.png --ir ir/xxx.ir.yaml \
    --json gen/check1.json --outdir handoff
#   产物：handoff/candidates.md（表格 + 预览图 + 三种回音怎么回）、
#         handoff/cand_01.svg（可编辑，每形体一个 part-NN 子层）、cand_01_preview.png
#   → 把 candidates.md 给用户看，问清楚：① 用第几张？ ② 还是下载 SVG 自己改？
#   ★ v3.1：别再把「我贴了 candidates.md」当成「已经问过了」—— 要留下**回执**：
#     ① 生成客户能点的选择页（底栏给选择码，不用让客户在仓库里翻 markdown）：
#        python3 scripts/make_picker.py --handoff handoff --tag V5 \
#            --notes handoff/notes.json --title "集体流产生"
#        -> handoff/pick.html（双击可点）+ handoff/pick_sheet.png（贴聊天窗口用）
#     ② 客户回话后落回执（--by 只认客户侧的值；写 agent 一律判失败）：
#        python3 scripts/choice_gate.py --handoff handoff --record \
#            --code V5-cand_06 --reply "用第 6 张" --by client
#        -> handoff/choice.json（候选 / 位图 / 原话 / 时间戳）
#     ③ 第 5 步之前机械校验（ref_guard.py --run 会自动带上它）：
#        python3 scripts/choice_gate.py --handoff handoff    # 非零退出 = 不许出成品位图
#   [为什么不是「说一句就行」：一次真实任务里 handoff/ 材料齐全、candidates.md 也贴了，
#    但工作区**找不到任何回执**，最后是 agent 自己挑了一张往下走 —— 约定拦不住，
#    只有闸门拦得住。]
#   ★ 用户改完传回 → 灌回流程（**强制重过闸口①**，人改不豁免）：
#     python3 scripts/sketch_ingest.py handoff/cand_02_edited.svg --ir ir/xxx.ir.yaml \
#         --size 1664*928 -o gen/sketch_edited_clean.png
#     过了闸口才继续第 5 步，且第 5 步的 --content-ref 换成 gen/sketch_edited_clean.png
#   ★ 用户说"你定" → **也要留回执**（--by manual），否则闸门过不去：
#     python3 scripts/choice_gate.py --handoff handoff --record \
#         --code V5-cand_01 --reply "你定吧" --by manual
#     然后按 pick_best 的顺序取第一张往下走
#   ★ 拿不到回音就不要往下走：成品位图一次出图要花钱，草图返工几乎免费

# ── 5. 出成品位图（★ 草图 + 风格参考图都要带）──────────────
#   ★ 风格档在**简报编译这一步**定（`ir_to_genbrief.py --style-mode auto|flat|render3d`，
#     默认 auto，按 IR 的 style 段判；**gen_figure.py 没有这个参数**）：
#     IR 写 3D/半写实/体积/网格线 -> render3d（球面明暗+高光+真渐变）；
#     判不出 -> ref（跟随参考图）。参考图是风格书，不是内容模板。
python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage render -o brief2.md
python3 scripts/gen_figure.py --brief brief2.md --stage render \
    --content-ref gen/sketch_s1_clean.png --ref refs/T3-33.png --seeds 21,22 --outdir gen/
#   ★ 上一步选中的草图走 **--content-ref**（不是 --ref）：它是构图依据（已过闸口①）。
#     ⚠️ 别把草图写进 --ref —— --ref 只收风格书（角色写错 ref_guard 会拦）。
#     只传风格参考图 = 让模型重新猜一遍构图，构图会被改坏
#     （实测 2026-09-26：UPC 算例漏传草图，成品位图把核 B 画成了横扁，
#      与 IR 的 Lorentz 收缩方向相反）。
#   ★ 草图**原样送**（--content-ref-mode auto -> full，v4.7 起不再降级）：
#     位图这一步就是对草图的润色 —— 形体 / 材质 / 光照 / 文字都该原样带进去。
#     ★ 旧默认（v2.6.8–v4.6.3）是 render 档先降级成 layout-only（灰度模糊、只留布局）；
#     它只为**扁平**草图标定（形变核→火球：原样送 0.873 但火球=纯色橙盘；
#     降级后 0.904 且火球=3D 辉光+亮核）。草图自己已经 3D 时降级是纯损失 ——
#     2026-10-07 法拉第算例实测：降级图连 3D0 都过不了，构图保真反而没变好
#     （0.416/0.654 vs 原样 0.425/0.597），且三轴闸门 2/2 FAIL（模糊图承载不了
#     可读的 x/y/z 标签）。所以只有**扁平**草图才显式加 --content-ref-mode layout。
#   成品位图同样带外框 → 同样裁掉再进闸口/临摹（外框两层时加 --bg 0.975）：
python3 scripts/trim_border.py gen/render_s22.png -o gen/render_s22_clean.png --bg 0.975

# ── 6. ★ 闸口②：成品位图再过一次同一个闸口 ─────────────────
#   ★ 加 --sketch 给出**构图依据**：闸口会量「成品位图有没有沿用草图的构图」
#     （布局相关 r；低于 --fidelity-min 直接算硬伤）。锚点（形变核→火球）：
#     完全不带构图参考 0.696 = 构图跑掉；带草图 0.87–0.90。
python3 scripts/check_sketch.py gen/render_s22_clean.png --ir ir/xxx.ir.yaml \
    --sketch gen/sketch_s1_clean.png

# ── 7. 同时输出原生几何版与独立透明纹理版 SVG ─────────────────────
#    读 references/direct-svg-redraw.md；按对象写 draw.py 或 SVG。
#    试编辑（ID 和遮挡对象改为当前图的）：
python3 scripts/check_direct_svg.py fig_edit.svg --require qgp reaction-plane \
        --hide qgp --hidden-png fig_hide_qgp.png
#    检查露出的网格确实完整。

# ── 8. 三道门禁 + 返修单 → 交付 ───────────────────────────
python3 scripts/check_render.py fig.png --probe 0.5,0.10
python3 scripts/check_delivery.py fig.pdf --svg fig.svg
python3 scripts/audit_composition.py fig.pdf
python3 scripts/repair_brief.py fig.svg --profile assets/style-profiles.json
```

## ★ 关键设计：位图的定位是「更好的草图」，但**它过了闸口就必须照它画**

草图阶段只求"构图清晰、元素齐全"，不追求质感 —— 质感由第 5 步负责。

到了第 7 步，**位图已经过了闸口②，物理是对的**，所以直接重绘应以它为构图和外观依据。
对不上 = 位图错了，回去改简报重出，**不要**在矢量那步偷偷"修正"。

确认位图基准后，最终两版分别运行 [原尺寸保真门禁](svg-fidelity.md) 和 [4 倍回渲染](continuous-gradient-svg.md)，再核对独立对象的显隐和平移。

> ⚠️ 老版本这里写着"绘画那步要按 IR 的 geometry_constraints 正确执行、
> **不要照抄位图的几何**" —— 那是**闸口还没补上**时候的写法（怕把位图的物理错误抄进去）。
> 现在闸口②已经拦在位图前面，这句就反了，2026-09-26 改掉。
> ★ v4.5 补充：这一条要和「位图精修」合起来看 —— 位图**自己也会错**（实测：会加 IR 里没有的英文词、会把形状改走样），所以「照它画」之前必须先跑 `gate3d_rank.py --require-all` + `axis_gate.py` + 逐条对照错误清单；位图那一步不过闸，就回去改简报重出位图，而不是带着错往下走。

## ★★ 这条规则有闸门了（v3.2）：`scripts/bitmap_conformance.py`

「照它画」以前只是**约定** —— 2026-09-30 实测它就失守过一次：集体流图第 5 版把
**位图之前就存在**的 `build_figure_v3.py` 整份搬过来（文本相似度 **96.0%**），
只换内容层，底盘常量原样继承，板子倾角差了 **11.3 度**，而**五道门禁全绿**
—— 没有一道在量「成品和位图像不像」。

所以别靠"记得照它"，把两边各量一遍：

    python3 scripts/bitmap_conformance.py <所选位图> <成品.png|.svg>

比的是架构几何：面板数、每个面板的**上边界倾角 / 板左缘 x / 板左上角 y /
侧边界角**、宽高比。超阈值 → **非零退出，不许出成品**。实测标定：

    位图 vs v5（沿用旧底盘）→ 拒绝：上边界倾角 17.79 -> 6.45（差 -11.33 度）
    位图 vs v6（重做底盘）  → 仍拒绝：b/c 两块板的左缘 x 与左上角 y 差 3.3~8.3 mm
    位图 vs 它自己           → 通过（自检）

★ **量不出来 ≠ 通过**：拟合不可信或两边至少一侧量不出来的量列成「不可比」，
  不计失败；但可比总数 < 3 时判「无法比对」而不放行。
★ 有意与位图不同（位图物理错了、客户要求改）才加 `--allow-diff "理由"`，
  并在交付说明里写明。

## ★ 生图那一步（gen_figure.py）

| 事 | 怎么做 | 为什么 |
|---|---|---|
| **API key** | 读环境变量 `DASHSCOPE_API_KEY`，**脚本不存 key** | 别人装了 skill 得用**他自己的** key |
| **风格参考图** | `--ref 图1.png --ref 图2.png`（可多张）。**缺了直接报错** —— 要纯文生图才加 `--allow-no-ref` | 只给文字 → 出来一定很"通用"。参考图 = Nature 风格书。纪律交给记性就等于没有（v2.8 从"打一行警告就继续"改成硬错误）|
| **两个接口** | `qwen-image-*` → 图生图（**支持 --ref**）；`wanx*`/`wan*` → 纯文生图 | 要参考图只能用前者 |
| **image 字段** | 本地图 → **base64 data URI**（自动）；公网 URL 直接透传 | mm 端点**只收**公网 URL 或 base64，**不认 `oss://`** —— 实测提交报 400 `Image must be either a public URL or a Base64 encoded string`（v2.6.1 修）|
| **两个产物** | 草图 PNG + **草图 SVG** + 成品位图，全部落盘 | 用户要能拿到中间产物 |
| **裁外框** | 出图后跑 `scripts/trim_border.py in.png -o out_clean.png` | 模型**稳定**在四周画 1~2px 外框，简报与 `--negative` 都拦不住（实测 5/5）→ 确定性裁掉，别求模型 |
| **提示词扩展** | `--prompt-extend` / `--no-prompt-extend`（默认沿用接口行为：mm=True / t2i=False）| ★ **v4.0 实测推翻了 v2.8 的建议**：`prompt_extend=True` 会让服务端**重写提示词**，看起来会稀释简报 → 但**关掉它更糟**：`--no-prompt-extend` 把简报**原样**当提示词，模型于是把「这是一份说明文档」这个先验也画出来（图上出现大段中文、章节编号、色卡）。实测同一份简报 + 同一批参考图：**加 flag 12 张全中，走接口默认 4 张零漏字** → **草图档不要加这个 flag**。实际取值记进 `calls.jsonl` |
| **画布比例对账** | `--size` 与 IR 声明的比例不符时当场警告 | 同一张图两个比例，IR 的归一化坐标就废了（实测 sketch5_upc 声明 2.10、默认 `--size` 1.79，差 15%）|
| **调用留痕** | `gen/calls.jsonl` 记 model/seed/size/refs/prompt 指纹 + `prompt_extend` / `no_style_ref` / `ir_ratio_dev` | 出图后要能溯源、核对计费、回溯提示词有没有被服务端重写 |
| **单个 seed 抖动** | 失败**重试 2 次**（共 3 次尝试），仍失败记 `ok=False` 继续下一个 seed | 实测 2026-09-27：seed 7 撞 TimeoutError 让整批 traceback 退出 —— seed 9 根本没跑、已出的 seed 5 也没进 `calls.jsonl` |
| **限流退避** | 429 / Throttling / rate limit 判为限流 → 退避 5s、10s（普通故障 3s）| 限流时立刻重试只会再撞一次；批量出图（多 seed）最容易撞 |
| 没 key 时 | `--dry-run` 只写提示词和调用计划 | 自检不用花钱 |

> 实测（UPC 图，2026-09-26）：`wanx2.0-t2i-turbo` 对结构化示意图太弱
> （画不出顶点/箭头/e⁺e⁻），且不支持参考图；`qwen-image-3.0` 8 个 seed 出图，
> 只有 3 张同时满足"两条平行虚线 + 不重叠 + 相向运动 + 双光子汇聚 + e⁺e⁻ 背对背"。

## ★ 参考图 = 风格书（v2.6.7）

**要的是**：参考图提供**风格**（配色 / 线条 / 材质 / 光影 / **渲染方式**）。
它**不是**要逐像素复刻的内容模板 —— **但复刻了也不是错**：A 档的参考图本来就大致等于
你要的物理内容（作者 2026-10-12：「A 档复刻参考图就复刻参考图呗，说明参考图大致就是我要的
物理内容啊」），所以**别把「长得像参考图」当 bug 去修**。
**「期刊矢量插画风」不等于「扁平 2D」**：`_T3精选` 里 T3-02 那条线本身就是
**3D 渲染**的矢量插画（核子球面明暗 + 高光 + 经纬网格线 + 火球橙→红多层渐变）。
参考图里**没有**的物理对象，按 IR 画出来就行，不要因为"参考图里没有"就不画。

**据此定风格档**（`ir_to_genbrief.py --style-mode`，默认 `auto`）：

| 档 | 简报第四节怎么写 | 什么时候用 |
|---|---|---|
| `flat` | 扁平矢量：平涂 + 细描边 | IR 明说要扁平（简单的流程图式示意图） |
| `render3d` | 3D 渲染插画：球面明暗 + 高光 + 柔和阴影 + **真 `<gradient>`** + 网格线 | IR 明说 3D / 半写实 / 体积 / 网格线（T3-02 那条线） |
| `ref` | **跟随参考图**：先看参考图是 2D 还是 3D，照它的渲染方式来 | `auto` 判不出时的默认 |

`auto` 的判据 = IR 的 `style` 段（`classification` / `evidence` / `conventions`）
关键词：含 `3D` / 体积 / 网格线 / 半写实 → `render3d`；含 扁平 / 平涂 → `flat`；
都没有 → `ref`。（`sketch` 档的扁平问题见下面 ★）
★ **2026-10-08 起 `sketch` 档不再强制扁平**（作者原话：「不要有限制观感的东西」，
选 A 档）：草图只管**构图**，允许体积与明暗、允许渐变色阶；只要求**不堆噪点 /
材质纹理** —— 因为下一步要自动切矢量图层。实测 `--q 16` 量化后，带明暗的草图切出
5.3k–6.3k 条路径，与原来扁平稿的 5.4k–5.7k 同量级，**没有变碎**。
（旧说法「sketch 档永远保持扁平，那不是最终风格」已作废。）成品位图档按上表走。

> ★ **默认档 = `render3d`（作者 2026-09-28 定）**：所有配图**一律** 3D 明暗风，
> IR 的 `style.mode` 一律写 `render3d`；扁平（`flat`）**只允许**出现在
> ①承载定量数据的面板（谱 / 曲线 / 误差带 / 场图 / 极坐标数据）
> ②纯抽象内容（演化序列色条、晶格示意、流程条），且必须在交付说明里写明理由。
> 即使是这两类，同一张图里的**物理示意图面板仍必须是 3D 的**。
> 依据：`_T3精选` 21 张里 18 张带 3D 明暗体积语言，剩下 3 张（T3-50/T3-59/T3-60）
> 主体是平面 —— 而那 3 张画的正是「演化序列 / 晶格 / 流程条」。
> 反例代价：一张扁平示意图把五道门禁全过了（见上「验证」一节）。

## ★ 反过来：该学的风格没学到怎么办（v2.6.7 / v2.6.8）

**现象**：出的图又干又平，火球是个**纯色圆盘**，完全没有参考图那种 3D 质感 ——
用了 diffusion model 却没用它的好处。

**根因一（v2.6.7 实测，形变核→火球 算例）：简报把风格写死了。**
IR 的 `style` 明写「半写实插画 / 3D 椭球 / 球面明暗 + 网格线 / 火球橙→红渐变」，
而 `ir_to_genbrief.py` 生成的简报却写着「目标是期刊矢量插画风，**不是 3D 渲染图**」
—— IR 与简报**直接打架**，模型照简报走，于是出纯色圆盘。

> ⚠️ 这是「风格没学到」的病：查**简报里有没有禁止 3D**，别去量参考图相似度。

**根因二（v2.6.8 实测）：构图参考（`--content-ref`）把"扁平"当风格一起送进去了。**

上面那条修完，简报已经不禁 3D 了，可出图**还是**纯色圆盘 —— 因为
`--content-ref` 传的是**扁平草图**，而 qwen-image 是**图生图**：它会
把草图的**渲染风格**连同构图**一起**继承，风格参考被稀释掉。

| content-ref 怎么送的（形变核→火球，同一简报 / seed 53） | 与草图布局的列剖面相关 r | 出的火球 |
|---|---|---|
| 原样送（旧行为） | 0.873 | **纯色橙盘** |
| 不送 | 0.696 | 3D 辉光，但构图跑掉（三取向涨落画成三个球） |
| **降级成 layout-only** | **0.904** | 3D 辉光 + 亮核 |

修法：`gen_figure.py --content-ref-mode auto|layout|full`。
★ **v4.7 起默认 `auto` = 原样送（`full`）** —— 上表那个降级只对**扁平**草图成立，
所以它现在是 opt-in：只有草图本身是扁平稿时才显式 `--content-ref-mode layout`
（降级成「灰度 + 降采样再放大 + 轻微模糊」的只含布局的图，落盘 `layout_*.png`）。
草图已经 3D 时降级是纯损失（2026-10-07 法拉第算例：降级档三轴闸门 2/2 FAIL，
连可读的 x/y/z 标签都被磨掉）。送的是哪张记在 `calls.jsonl` 的 `content_ref_sent`。
★ 对**扁平**草图，这不是"拿构图换风格"：**两边同时变好**（0.873 → 0.904）。

排查顺序（按这个顺序，别跳）：
1. 打开简报看**第四节（风格）+ 第五节（禁止项）**：出现「不是 3D 渲染图」
   → 风格档错了（IR 要 3D 却给了 flat）。重出简报：
   ```bash
   python3 scripts/ir_to_genbrief.py ir/xxx.ir.yaml --stage render \
       --style-mode render3d -o brief2.md     # 或 --style-mode auto，让 IR 自己判
   ```
2. 简报第四节现在会把 IR 的 `style.palette` / `line_widths` **原样带出来**；
   要是没有，就往 IR 的 `style` 段补配色和线宽（`render3d` 档尤其需要）。
3. **查 `calls.jsonl` 的 `content_ref_mode` / `content_ref_sent`**：先量**草图自己**是
   不是已经 3D（`scripts/gate3d_rank.py <草图>`）。草图**扁平**、而这一轮又送了
   **原样草图**（`full`）→ 加 `--content-ref-mode layout` 用**同一个 seed** 再跑一遍 ——
   这是最便宜的一刀，实测同时救回风格和构图。★ 草图已经 3D 时**不要**降级：
   降级会把形体与可读的轴标签一起磨掉（2026-10-07 法拉第算例，三轴闸门 2/2 FAIL）。
4. 到这里才对不上，才考虑换模型 / 加 seed。

## ★ 出的图「很 AI」/ 火球像颗光滑糖球（v2.6.9）

**现象**：形体、构图、配色都对，但一看就"很 AI"—— 发光体是一颗**光滑高光的球**，
内部空空如也。用户拿别的模型（网页版）出的同题材图一比，明显更有内容。

**根因（实测，形变核→火球 算例）：IR 的 `material:` 根本没进简报。**
`ir_to_genbrief.py` 的元素表以前只带 `primitive`（形态），`material`（材质）
**全文件 0 次出现**；而简报里却**硬编码**着一句
「火球/热区：内亮外暗的多层半透明渐变（亮核→橙→红）…边缘柔和但不模糊」——
不管 IR 写什么，模型都被按在一颗光滑高光球上。
再叠加禁止项「不要添加 IR 清单里没有的东西」，模型连内部结构都**不许**加。

> **光滑高光 + 均匀径向渐变 + 无内部结构 = 通用 CG 球 = 用户说的「AI 画风」。**

**修法**（v2.6.9）：

1. 元素表每条带 `【材质：…】`（和 `【形态：…】` 并列）—— IR 写了什么就送什么。
2. 删掉硬编码的火球描述，改成「**发光体 / 热区怎么画，以第一节各元素的【材质】为准**」。
3. 禁止项第 1 条改成禁**【独立物体/箭头/文字/装饰光晕】**；
   【材质】里写明的内部结构（分层 / 组元颗粒 / 场线 / 亮核 / 外壳 / 日冕）**必须画**。
4. 「颗粒/噪点」澄清为**胶片颗粒/噪点纹理** —— 示意性的细小符号不算。

**所以在这条路线上，发光体一定要在 IR 的 `material:` 里写清楚"里面有什么"**：

```yaml
material: >
  **哑光**（不要高光反射 / 塑料光泽 / 辉光外溢 bloom）。
  由内到外**分三层、边界要看得出来是三层**：① 亮黄白热核 ② 橙→红等离子体壳
  ③ 半透明橙红日冕（边缘羽化）。内部散布**组元颗粒**与**弯曲短丝线**（胶子场），
  随机分布、不排成规则网格。最里面是 4 个相互重叠的参与者核子球。
```

**实测数字**（qwen-image-3.0，同一份构图 / **同一个 seed 53**，只改 spec）：
火球盘内「内部高频能量」旧 spec **0.0103**（全部里最平滑 = 纯渐变球）
→ 新 spec **0.0265 / 0.0418**（seed 53 / 51），即 **2.6~4 倍**；
盘内最亮 1% 亮度与内部小暗团数同步上升。数字与对照图见
`assets/demos/evo3d_fireball_spec/`。

---

## `check_sketch.py` 为什么要分两类输出（`references/ir-spec.md` 有详述）

| 输出 | 谁判 | 例 |
|---|---|---|
| ■ 自动测到的 | 机器 | 内容边界/出界、重心偏移、留白分布、画布比例被改、风格量测 |
| ■ 必须逐条回答的 | **人/模型看图** | IR 的 `geometry_constraints` 逐条变成待答问题 |

**机器判不了物理。** 把"检查物理"从一句原则变成**必须填的动作**，
才拦得住"图像模型把喷注画反、把非中心碰撞画成同心"这类错。

## ★ 第 7 步：两版 SVG

默认同时交付 `<stem>_edit.svg`（原生几何重绘版）与 `<stem>_texture.svg`（独立透明纹理版），各附 PNG、源码和试编辑结果。两版使用同一对象表、viewBox 与原生文字；纹理版拖动仅改变组变换，不关闭纹理或切换重绘稿。 按 [双版流程](dual-svg.md) 做反混合、遮挡补全与无切换拖动验证，使用 `check_svg_pair.py`。

见 [直接重绘 SVG](direct-svg-redraw.md)。按对象直接重绘：量参考图的比例与锚点 → 列对象和前后关系 → 画出完整形体（包括可合理补画的遮挡部分） → 用真渐变、独立阴影和原生文字塑形 → 回渲染、隐藏/移动一个对象核对。SVG 不嵌位图；每个物体是可单独编辑的命名组。

已有作者指定的成品图、只要重绘 SVG 时，从对象拆解直接开始，跳过生图、草图阶梯和逐像素临摹。需要创作新图时，草图、作者选择和成品位图门禁照旧，最后按对象重绘 SVG。

只有作者明确要像素级保真、对照旧算法或维护旧稿时，才走临摹备用。复杂渐变按 [连续渐变 SVG](continuous-gradient-svg.md) 放大抽查，并用原尺寸面板误差定位偏差。详见 [临摹备用](bitmap-to-vector.md)。

## ★ 参考图 vs 画法规律：**能直接给图就别提炼**

`assets/t3-exemplars/` 里有 **17 张 CC BY 4.0 的 T3 参考图**
（STAR / ALICE / CMS / 开放获取的 arXiv 论文，逐张署名与加工说明见 `NOTICE.md`）。
5.1 还可用 `assets/schematic-library/redistributable/` 中的 CC0 / CC BY 图，
先用 `schematic_library.py search --for-ref` 只筛本地图。

| | 给参考图 | 给提炼的规律 |
|---|---|---|
| 效果 | **无损、最好**（模型 few-shot 能力强） | 有损压缩 |
| 内部/本地 | ✅ **直接用图** | 不需要 |
| **公开发布** | ❌ 版权 | ✅ 只剩这条路 |

**「风格档案（数字）」和「画法规律（文字）」本质是同一个东西：
参考图的【版权干净代理物】。** 它们不是方法论，是降级方案 ——
因为多数期刊图不能随仓库分发（本仓库只留了 2 张 CC-BY）。

**所以：内部用直接调图；公开版用那 2 张 CC-BY + 代理物。**

> 那些"规律"（核带网格线、火球有纹理、衬板给中间调、粗黑箭头、
> 先定全局光源）都是从 8 张 T3 精选看图看出来的 —— **是总结，不是源头。**

---
