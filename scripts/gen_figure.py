#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_figure —— 第 ② 步：把 IR 简报变成【草图】或【成品位图】
=========================================================================

    IR ──ir_to_genbrief──▶ 约束简报 ──gen_figure──▶ 位图草图 ──▶ 成品位图
                                          ↑
                                  --ref 风格参考图（可多张）

## ★ 三件必须说清楚的事

1. **API key 由使用者自己提供，脚本里不存任何 key。**
   读环境变量 `DASHSCOPE_API_KEY`（可用 `--key-env` 换名字）。
   别人的电脑上装了这个 skill，就要用**他自己的** key。
   没设 key 时脚本直接退出并给出设置方法，不会静默失败。

2. **风格参考图是必需的，不是可选项。**
   只给文字简报，出来的图一定很"通用"。`--ref` 把 `_T3精选` 这类
   Nature 风格图直接当 few-shot 参考喂进去（模型 few-shot 能力强）。
   公开仓库里不能塞版权图，但**使用时**可以直接传本地图。

3. **产物全部落盘，并写调用记录。**
   每张图 + `calls.jsonl`（model / seed / size / refs / prompt 指纹 / 输出路径）
   —— 复现和核对计费都靠它。

## 两种接口（自动按模型名选，也可用 --mode 强制）

| mode | 模型 | 端点 | 支持 --ref |
|---|---|---|---|
| `mm` | `qwen-image-*` | multimodal-generation | ✅ 图生图 |
| `t2i` | `wanx*` / `wan*` | text2image（异步轮询） | ❌ 纯文生图 |

**要给参考图就必须用 `mm` 那条**（qwen-image 系列）。实测：`wanx2.0-t2i-turbo`
对结构化示意图太弱（画不出顶点、箭头、e⁺e⁻），且不支持参考图。

## ★ 构图参考（--content-ref）默认「降级」再送（v2.6.8）

`--content-ref-mode auto|layout|full`（默认 `auto`）。

实测（2026-09-27，形变核→火球 算例，**同一份简报**、qwen-image-3.0、seed 53）：

| content-ref 怎么送的 | 与草图布局的列剖面相关 r | 出的火球 |
|---|---|---|
| 原样送（`full`） | 0.873 | **纯色橙盘**（草图的"扁平"风格被一起继承） |
| 不送 | 0.696 | 3D 辉光，但构图跑掉（三取向涨落画成了三个球） |
| 降级成 layout-only | **0.904** | 3D 辉光 + 亮核（构图与风格**同时**拿到） |

原因：qwen-image 是**图生图**，`--content-ref` 给的草图是**扁平**的，
模型会把"扁平"这个**渲染风格**连同构图**一起**继承，把风格参考图稀释掉 ——
于是"用了 diffusion model 却没用它的好处"，火球退化成纯色圆盘。

所以默认（`auto`）：`--stage render` 时把构图参考先降级成
「灰度 + 降采样再放大 + 轻微模糊」的**只含布局**的图（落盘为 `layout_*.png`），
只留"哪儿有什么、多大、什么位置"，去掉颜色与扁平渲染风格；
`--stage sketch` 保持原样（草图阶段本来就该跟手绘稿的形体走）。
想让模型连草图的风格一起继承，显式 `--content-ref-mode full`。

## ★ v2.8：三个新开关（都为了「少花钱、少猜」）

- **`--ref` 缺失直接报错**（要放行才加 `--allow-no-ref`）。以前只打一行
  「（无 —— 出来会偏通用）」就继续 —— 纪律 2（风格参考图必需）等于交给记性。
- **`--prompt-extend` / `--no-prompt-extend`**：默认沿用接口原有行为
  （mm=True / t2i=False）。★ **v4.0 实测推翻了 v2.8 这条建议**：加
  `--no-prompt-extend` 会把简报**原样**当提示词，模型于是把「这是一份说明文档」
  这个先验也一起画出来（图上出现大段中文、章节编号、色卡/图例）。
  同一份简报（7 k 字符）+ 同一批参考图实测：**加 flag 12 张全中，走接口默认
  4 张零漏字** → **草图档不要加这个 flag**（render 档带 --content-ref，本来就干净）。
  实际取值写进 `calls.jsonl`，可回溯。
- **`--size` 与 IR 声明的画布比例不一致时警告**：同一张图两个比例，
  IR 的归一化坐标就失效了（IRC 声明的位置全按比例换算）。

## 用法

    # ① IR → 简报（skill 自带的编译步骤）
    python3 scripts/ir_to_genbrief.py ir/sketch5_upc.ir.yaml --stage sketch -o brief1.md

    # ② 出草图（带风格参考）
    python3 scripts/gen_figure.py --brief brief1.md --stage sketch \\
        --ref refs/T3-33.png --seeds 1,2,3 --outdir gen/

    # ③ 草图过闸口（物理）
    python3 scripts/check_sketch.py gen/sketch_s1.png --ir ir/sketch5_upc.ir.yaml

    # ④ 出成品位图
    python3 scripts/ir_to_genbrief.py ir/sketch5_upc.ir.yaml --stage render -o brief2.md
    python3 scripts/gen_figure.py --brief brief2.md --stage render --ref refs/T3-33.png \\
        --seeds 21,22 --outdir gen/

    # ⑤ 成品位图再过一次同样的闸口（这一步以前漏了）
    python3 scripts/check_sketch.py gen/render_s22.png --ir ir/sketch5_upc.ir.yaml

    # 想看要发什么请求、不真的调 API：
    python3 scripts/gen_figure.py --brief brief1.md --ref refs/T3-33.png --dry-run
"""
from __future__ import annotations

from _console import init_console

init_console()  # Windows：stdout 被管道/重定向时切 UTF-8（否则打印 ✅ 会崩）

from ir_canvas import parse_size, declared_ratio, ratio_deviation, canvas_node, canvas_for_brief

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

DEF_BASE = "https://dashscope.aliyuncs.com"
MM_MODEL_HINT = ("qwen-image",)


# ────────────────────────────────────────────────────────── HTTP 小工具
def _req(url, key, payload=None, method=None, raw=None, ctype=None, timeout=180):
    h = {}
    if key:
        h["Authorization"] = "Bearer " + key
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        h["Content-Type"] = "application/json"
    if raw is not None:
        data = raw
        h["Content-Type"] = ctype
    r = urllib.request.Request(url, data=data, headers=h,
                               method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, "网络错误: %s" % e


def _looks_rate_limited(note):
    """429 / 限流类错误要退避更久 —— 服务端让你慢一点，立刻重试只会再撞一次。"""
    s = str(note).lower()
    return any(h in s for h in ("429", "throttl", "rate limit", "limit exceeded",
                                "too many requests", "quota"))


def ref_to_image_field(path):
    """参考图 → mm 端点 image 字段的值。

    ★ 实测（2026-09-26）：mm 端点**只收**公网 URL 或 base64 data URI，
      **不认 `oss://`**（会报 InvalidParameter: Image must be either a public
      URL (http:// or https://) or a Base64 encoded string）。
      所以本地图一律转 data URI，不再走 OSS 临时上传。
    """
    s = str(path)
    if s.startswith("http://") or s.startswith("https://"):
        return s
    p = pathlib.Path(s)
    if not p.exists():
        raise SystemExit("参考图不存在: %s" % p)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(p.read_bytes()).decode("ascii"))


def download(url, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))
    return dest


def _degrade_to_layout(src, dst, width=160):
    """把构图参考降级成「只含布局」的灰度模糊图（v2.6.8）。

    只留形体（哪儿有什么 / 多大 / 什么位置），丢掉颜色和**扁平的渲染风格** ——
    这样模型就不会把草图的"扁平"当成要继承的风格。

    ★ 实测（2026-09-27，形变核→火球 算例，同一份简报 / 同一 seed 53，qwen-image-3.0）：
      原样送扁平草图 -> 与草图布局的列剖面相关 r=0.873，但火球被压成纯色橙盘；
      降级成 layout-only -> r=0.904 **且**火球是 3D 辉光 + 亮核。
      即降级不是"拿构图换风格"，是两边**都**变好。
    """
    from PIL import Image, ImageFilter
    im = Image.open(str(src)).convert("RGB")
    W, H = im.size
    g = im.convert("L")
    h = max(1, int(round(H * width / float(W))))
    small = g.resize((width, h), Image.BILINEAR)      # 杀细描边 / 文字 / 颗粒
    back = small.resize((W, H), Image.BICUBIC)        # 放回原画布，只剩大形体
    back = back.filter(ImageFilter.GaussianBlur(radius=max(2.0, W / 220.0)))
    dst = pathlib.Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.merge("RGB", (back, back, back)).save(str(dst))
    return dst


def _ref_leak_check(out_png, style_refs, content_refs, skip=False):
    """出图 vs 风格参考：量「有没有把参考图抄了」（v2.6.4）。

    ★ 实测（2026-09-27，用 Claude Code 跑本 skill）：qwen-image 是**图生图**，
      参考图内容越像目标就越容易被**整幅照抄** —— 出的图物体/布局/箭头/文字
      全变成参考图的，而流程里没有任何一步会发现。现在出图后自动量一次，
      把 r 写进 calls.jsonl；r>=0.85 就打印警告（判据见 scripts/ref_leak_check.py）。
      上一步的草图是**构图依据**（本来就该像），所以要走 content_refs，不参与判定。
    """
    if skip or not style_refs:
        return None
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import ref_leak_check as RLC
    except ImportError:
        return None
    try:
        worst, rows = RLC.check(out_png, style_refs, content_refs)
    except Exception as e:                      # 自检失败不许影响出图
        print("  （参考图自检跳过：%s）" % e)
        return None
    sims = {}
    for role, name, r, dh, v in rows:
        if role != "style":
            continue
        sims[name] = round(r, 3)
        if v != "ok":
            print("  ⚠️ 与风格参考 %s 的相似度 r=%.3f（照抄线 %.2f）"
                  % (name, r, RLC.THR_COPY))
    if worst == "copy":
        print("     → 出图疑似把参考图抄了：参考图要换「**内容不同、风格相同**」的；"
              "上一步的草图用 `--content-ref` 传（见 SKILL.md"
              "「输出变成参考图的内容」一节）。")
    elif worst == "high":
        print("     → 与风格参考的相似度偏高，建议人眼比一眼。")
    return worst, sims


# ────────────────────────────────────────────────────────── 两种后端
def _prompt_extend(cfg, default):
    """prompt_extend 的取值：命令行 > 接口默认（mm=True / t2i=False）。

    ★ 默认不变（兼容老行为）；显式给了就听命令行的 —— 结构化的简报
      （坐标/数量/约束）被服务端重写一遍就会被稀释。
    """
    v = cfg.get("prompt_extend")
    return default if v is None else bool(v)


def gen_mm(cfg, prompt, negative, seed, refs):
    content = [{"image": u} for u in refs] + [{"text": prompt}]
    payload = {"model": cfg["model"],
               "input": {"messages": [{"role": "user", "content": content}]},
               "parameters": {"size": cfg["size"], "n": 1,
                              "prompt_extend": _prompt_extend(cfg, True),
                              "watermark": False, "seed": seed}}
    if negative:
        payload["parameters"]["negative_prompt"] = negative
    st, r = _req(cfg["base"] + "/api/v1/services/aigc/multimodal-generation/generation",
                 cfg["key"], payload)
    if not isinstance(r, dict) or "output" not in r:
        return None, "提交失败 %s: %s" % (st, str(r)[:400])
    try:
        url = r["output"]["choices"][0]["message"]["content"][0]["image"]
    except (KeyError, IndexError, TypeError, ValueError):
        return None, "返回里没有图: %s" % json.dumps(r, ensure_ascii=False)[:400]
    return url, json.dumps(r.get("usage", {}), ensure_ascii=False)


def gen_t2i(cfg, prompt, negative, seed, refs):
    if refs:
        return None, ("%s 不支持参考图（t2i 端点只吃文字）。"
                      "要 --ref 就用 qwen-image 系列。" % cfg["model"])
    payload = {"model": cfg["model"], "input": {"prompt": prompt},
               "parameters": {"size": cfg["size"], "n": 1,
                              "prompt_extend": _prompt_extend(cfg, False),
                              "seed": seed}}
    if negative:
        payload["input"]["negative_prompt"] = negative
    h_extra = {"X-DashScope-Async": "enable"}
    r0 = urllib.request.Request(
        cfg["base"] + "/api/v1/services/aigc/text2image/image-synthesis",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + cfg["key"],
                 "Content-Type": "application/json", **h_extra})
    try:
        with urllib.request.urlopen(r0, timeout=90) as resp:
            r = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None, "提交失败 %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:400])
    tid = (r.get("output") or {}).get("task_id")
    if not tid:
        return None, "没有 task_id: %s" % json.dumps(r, ensure_ascii=False)[:400]
    t0 = time.time()
    while time.time() - t0 < cfg["timeout"]:
        time.sleep(2.0)
        st, rr = _req(cfg["base"] + "/api/v1/tasks/" + tid, cfg["key"])
        if not isinstance(rr, dict):
            continue
        out = rr.get("output") or {}
        status = out.get("task_status")
        if status == "SUCCEEDED":
            try:
                return out["results"][0]["url"], json.dumps(
                    out.get("usage", {}), ensure_ascii=False)
            except (KeyError, IndexError):
                return None, "成功但取不到 url: %s" % str(out)[:400]
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            return None, "任务 %s: %s" % (status, str(out)[:400])
    return None, "轮询超时"


# ────────────────────────────────────────────────────────── 主流程
def pick_mode(mode, model):
    if mode != "auto":
        return mode
    return "mm" if any(h in model for h in MM_MODEL_HINT) else "t2i"


def read_brief(a):
    if a.brief:
        return pathlib.Path(a.brief).read_text(encoding="utf-8").strip()
    if a.ir:
        import subprocess
        here = pathlib.Path(__file__).resolve().parent
        tmp = pathlib.Path(a.outdir) / ("_brief_%s.md" % a.stage)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(here / "ir_to_genbrief.py"), a.ir,
               "--stage", a.stage, "-o", str(tmp)]
        if a.style_profile:
            cmd += ["--style-profile", a.style_profile]
        if a.want_class:
            cmd += ["--class", a.want_class]
        subprocess.run(cmd, check=True)
        return tmp.read_text(encoding="utf-8").strip()
    raise SystemExit("要给 --brief brief.md 或 --ir xxx.ir.yaml 之一")


def _load_ir_light(path):
    """只为「画布比例对账」读一遍 IR；读不了不算错误（返回 None）。"""
    try:
        import json as _json
        txt = pathlib.Path(path).read_text(encoding="utf-8")
        try:
            import yaml
            return yaml.safe_load(txt)
        except ImportError:
            return _json.loads(txt)
    except Exception as e:
        print("  ⚠️ 读不了 IR（%s），跳过画布比例对账" % e)
        return None


def main():
    ap = argparse.ArgumentParser(
        description="IR 简报 → 草图 / 成品位图（key 由使用者自备）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("## 用法")[-1])
    ap.add_argument("--brief", default=None, help="ir_to_genbrief 产出的简报 .md")
    ap.add_argument("--ir", default=None, help="直接给 IR，脚本内部先编译成简报")
    ap.add_argument("--style-profile", default=None)
    ap.add_argument("--class", dest="want_class", default=None)
    ap.add_argument("--stage", choices=("sketch", "render"), default="sketch",
                    help="sketch=只求构图；render=要质感（路径 2/3 的第二段）")
    ap.add_argument("--ref", action="append", default=[],
                    help="风格参考图，可多次给（★ 不给就会很'通用'）")
    ap.add_argument("--content-ref", action="append", default=[],
                    help="构图参考图（上一步选中的草图）：出图本来就该像它，"
                         "所以不参与「照抄」判定，并会排在风格参考前面送给模型")
    ap.add_argument("--content-ref-mode", choices=("auto", "full", "layout"),
                    default="auto",
                    help="构图参考的预处理：auto=render 档降级成 layout-only、"
                         "sketch 档原样（默认）；layout=总是降级；full=总是原样。"
                         "★ 实测：原样送扁平草图会把'扁平'渲染风格一起带进去，"
                         "风格参考被稀释（详见文件头部说明）")
    ap.add_argument("--no-ref-check", action="store_true",
                    help="出图后不做「参考图照抄」自检（默认做）")
    ap.add_argument("--allow-no-ref", action="store_true",
                    help="★ 确实要纯文生图才加：不放行时缺 --ref 直接报错"
                         "（只给文字简报出来的图一定「通用」）")
    ap.add_argument("--prompt-extend", action=argparse.BooleanOptionalAction,
                    default=None,
                    help="服务端是否重写提示词。默认沿用接口行为（mm=True / t2i=False）；"
                         "结构化示意图建议 --no-prompt-extend（重写会稀释简报里的坐标/约束）")
    ap.add_argument("--model", default="qwen-image-3.0")
    ap.add_argument("--mode", choices=("auto", "mm", "t2i"), default="auto")
    ap.add_argument("--size", default="1664*928", help="WxH，乘号写 *")
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--negative", default="", help="负面提示词文件（可选）")
    ap.add_argument("--outdir", default="gen")
    ap.add_argument("--api-base", default=None)
    ap.add_argument("--key-env", default="DASHSCOPE_API_KEY")
    ap.add_argument("--timeout", type=float, default=420.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="只写出提示词和调用计划，不调 API（自检用）")
    a = ap.parse_args()

    if not a.ref and not a.allow_no_ref:
        sys.exit("★ 缺少 --ref 风格参考图。\n"
                 "  只给文字简报，出来的图一定是「通用插画脸」—— 这是本 skill 的硬规矩。\n"
                 "  用法：--ref refs/T3-33.png（可多张；优先「内容不同、风格相同」的）\n"
                 "  确实要纯文生图 / 只想自检提示词：加 --allow-no-ref。")

    outdir = pathlib.Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    prompt = read_brief(a)
    (outdir / ("%s_prompt.txt" % a.stage)).write_text(prompt, encoding="utf-8")
    negative = ""
    if a.negative and pathlib.Path(a.negative).exists():
        negative = pathlib.Path(a.negative).read_text(encoding="utf-8").strip()

    mode = pick_mode(a.mode, a.model)
    mode_fn = {"mm": gen_mm, "t2i": gen_t2i}[mode]
    seeds = [int(s) for s in str(a.seeds).split(",") if s.strip()]
    base = a.api_base or os.environ.get("DASHSCOPE_BASE", DEF_BASE)

    print("=" * 66)
    print("阶段        : %s" % a.stage)
    print("模型 / 接口 : %s / %s" % (a.model, mode))
    print("画布        : %s" % a.size)
    # ★ v2.8：简报按 IR 声明的比例写，API 却按 --size 出 —— 同一张图两个比例，
    #   IR 里的归一化坐标全部失效。这里当场对账，别等到出完图才发现。
    size_wh = parse_size(a.size)
    ir_ratio = ir_ratio_dev = None
    if a.ir and not size_wh:
        print("  ⚠️ --size 要写成 W*H（如 1664*928），实得 %r —— 比例对账跳过" % a.size)
    elif a.ir:
        _ir = _load_ir_light(a.ir)
        if _ir:
            ir_ratio = declared_ratio(_ir)
            ir_ratio_dev = ratio_deviation(_ir, size_wh)
            if ir_ratio:
                node, src = canvas_node(_ir)
                bad = ir_ratio_dev is not None and ir_ratio_dev >= 0.12
                print("画布比例    : 请求 %.2f，IR 声明 %.2f（%s）%s"
                      % (size_wh[0] / size_wh[1], ir_ratio, src,
                         ("  ❌ 偏差 %.0f%%" % (ir_ratio_dev * 100)) if bad else "  ✅"))
                if bad:
                    sw, sh, _ = canvas_for_brief(_ir)
                    print("   ⚠️ 同一张图两个比例：简报按 IR 的比例写（建议 %d×%d），"
                          "API 却按 %s 出 —— IR 的归一化坐标会失效。"
                          % (sw, sh, a.size))
    all_ref = list(a.content_ref) + list(a.ref)
    # ★ 构图参考降级（v2.6.8）：扁平草图会把"扁平"渲染风格一起带进去，
    #   把风格参考稀释掉。render 档默认先降级成 layout-only（理由见文件头部）。
    cr_mode = a.content_ref_mode
    if cr_mode == "auto":
        cr_mode = "full" if a.stage == "sketch" else "layout"
    print("构图参考    : %s" % (", ".join(a.content_ref) if a.content_ref else "（无）"))
    print("构图参考模式: %s%s" % (cr_mode, "（auto -> 按 stage 定）" if a.content_ref_mode == "auto" else ""))
    print("风格参考    : %s" % (", ".join(a.ref) if a.ref
          else "（无 —— 已用 --allow-no-ref 放行，出来会偏通用）"))
    print("提示词      : 已写出 %s（%d 字符，sha1 %s）"
          % (outdir / ("%s_prompt.txt" % a.stage), len(prompt),
             hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]))
    print("seed        : %s" % seeds)
    if a.dry_run:
        print("--dry-run：不调 API，到此为止。")
        return

    key = os.environ.get(a.key_env)
    if not key:
        sys.exit("未设置 %s。\n"
                 "  ★ 本脚本不内置任何 key，请用你自己的：\n"
                 "    PowerShell:  $env:%s=\"sk-...\"\n"
                 "    bash:        export %s=sk-...\n"
                 "  没 key 也可以用 --dry-run 自检提示词和调用计划。"
                 % (a.key_env, a.key_env, a.key_env))
    cfg = dict(key=key, base=base.rstrip("/"), model=a.model, size=a.size,
               timeout=a.timeout, prompt_extend=a.prompt_extend)
    pe_eff = _prompt_extend(cfg, mode == "mm")
    print("提示词扩展  : %s%s" % (pe_eff,
          "（接口默认）" if a.prompt_extend is None else "（命令行指定）"))

    # ★ 构图参考降级（v2.6.8）：只把 --content-ref 降级；--ref 风格参考原样送
    sent = {}
    for r in a.content_ref:
        src = pathlib.Path(r)
        if not src.exists():
            sys.exit("参考图不存在: %s" % r)
        if cr_mode == "layout":
            dst = outdir / ("layout_%s.png" % src.stem)
            try:
                _degrade_to_layout(src, dst)
                sent[r] = str(dst)
                print("构图参考降级: %s -> %s（只留布局，去掉扁平风格）"
                      % (src.name, dst.name))
            except Exception as e:            # 降级失败不许影响出图
                print("  ⚠️ 构图参考降级失败（%s: %s）—— 退回原图"
                      % (type(e).__name__, e))
                sent[r] = r
        else:
            sent[r] = r

    refs = []
    for r in all_ref:
        p = pathlib.Path(sent.get(r, r))
        if not p.exists():
            sys.exit("参考图不存在: %s" % r)
        if mode == "mm":
            print("参考图  : %s" % p.name, flush=True)
            refs.append(ref_to_image_field(p))
        else:
            refs.append(str(p))

    log = outdir / "calls.jsonl"
    ok = fail = 0
    outs = []          # 本次成功落盘的文件名（收尾时逐条给闸口命令）
    for sd in seeds:
        t0 = time.time()
        print("[seed %d] %s ..." % (sd, a.model), flush=True)
        # ★ 单个 seed 的**网络抖动**不许打断整批（实测 2026-09-27：形变核→火球 算例，
        #   seed 7 撞上 TimeoutError，整批直接 traceback 退出 —— seed 9 根本没跑，
        #   已经出的 seed 5 也没被记进调用记录。失败也要照常落 calls.jsonl）。
        #   失败重试一次；两次都失败就记 ok=False，继续下一个 seed。
        url, note = None, ""
        tries = 3                       # v2.8：2 -> 3 次；限流时退避更久
        for attempt in range(1, tries + 1):
            try:
                url, note = mode_fn(cfg, prompt, negative, sd, refs)
            except Exception as e:
                url, note = None, "%s: %s" % (type(e).__name__, e)
            if url:
                break
            if attempt < tries:
                rl = _looks_rate_limited(note)
                delay = 5.0 * (2 ** (attempt - 1)) if rl else 3.0
                print("  … 第 %d 次失败（%s）—— %.0f 秒后重试（第 %d/%d 次尝试）%s"
                      % (attempt, note, delay, attempt + 1, tries,
                         "（限流，退避加倍）" if rl else ""), flush=True)
                time.sleep(delay)
        rec = dict(stage=a.stage, model=a.model, mode=mode, size=a.size, seed=sd,
                   refs=[str(r) for r in all_ref],
                   content_refs=[str(r) for r in a.content_ref], n_ref=len(refs),
                   content_ref_mode=cr_mode, prompt_extend=pe_eff,
                   no_style_ref=not a.ref,
                   ir_ratio=ir_ratio,
                   ir_ratio_dev=(round(ir_ratio_dev, 4)
                                 if ir_ratio_dev is not None else None),
                   content_ref_sent=[sent.get(str(r), str(r)) for r in a.content_ref],
                   prompt_sha1=hashlib.sha1(prompt.encode("utf-8")).hexdigest(),
                   prompt_chars=len(prompt), seconds=round(time.time() - t0, 1),
                   ok=bool(url), note=note)
        if not url:
            print("  ✗ %s" % note)
            fail += 1
        else:
            out = outdir / ("%s_s%d.png" % (a.stage, sd))
            download(url, out)
            rec["file"] = out.name
            rec["bytes"] = out.stat().st_size
            outs.append(out.name)
            print("  ✓ %s  %.0f KB  (%s)" % (out.name, out.stat().st_size / 1024.0, note))
            chk = _ref_leak_check(out, a.ref, a.content_ref, skip=a.no_ref_check)
            if chk:
                rec["ref_leak"], rec["ref_sim"] = chk
            ok += 1
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 66)
    print("成功 %d / 失败 %d | 调用记录 %s" % (ok, fail, log))
    print("")
    print("★ 下一步（这两步不能跳）：")
    print("  1. 过物理闸口 —— 备选**一次全喂进去**（脚本支持多张，并落 json）：")
    if outs:
        files = " ".join("%s/%s" % (outdir, nm) for nm in outs)
        print("       python3 scripts/check_sketch.py %s \\" % files)
        print("           --ir <你的.ir.yaml> --json %s/check.json" % outdir)
    else:
        print("       （本次没有成功出图，先看上面对应 seed 的失败原因）")
    print("     ★ render 档再加 --sketch <上一步的草图>：量「构图有没有沿用草图」，"
          "低于 --fidelity-min 直接算硬伤。")
    print("     ★ 出图四周有 1~2px 外框时，先 trim_border.py 裁掉再量"
          "（或给 check_sketch.py 传 --trim N）。")
    print('     它有半张输出是「必须你/模型看图逐条回答」的 IR 几何约束。')
    print('     任何一条答"否" → 改简报重生，不要往下走。')
    if len(outs) > 1:
        print("  2. 排序挑图（别一张张肉眼过）—— 人眼只审没有硬伤的：")
        print("       python3 scripts/pick_best.py %s/check.json" % outdir)
    print("  3. 选定那张后**复制成固定名字**（如 %s/chosen.png）再进下一步，"
          "别让下游脚本去猜 seed。" % outdir)


if __name__ == "__main__":
    main()
