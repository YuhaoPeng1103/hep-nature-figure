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
    python3 scripts/gen_figure.py --brief brief1.md --dry-run
"""
from __future__ import annotations

import argparse
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


def upload_ref(base, key, path):
    """本地图 → oss:// URL（DashScope 临时上传，48h 有效）。

    mm 端点的 image 字段只收 URL 或 oss:// 引用，本地路径要先走这一步。
    """
    st, pol = _req(base + "/api/v1/uploads?action=getPolicy&model=qwen-image-edit-plus", key)
    if not isinstance(pol, dict) or "data" not in pol:
        raise SystemExit("取上传策略失败 (%s): %s" % (st, str(pol)[:300]))
    d = pol["data"]
    mp = "----genfigure"
    parts = []
    for k, v in [("OSSAccessKeyId", d["access_key_id"]), ("policy", d["policy"]),
                 ("Signature", d["signature"]), ("key", d["key"]),
                 ("x-oss-object-acl", d["x_oss_object_acl"]),
                 ("x-oss-forbid-overwrite", d["x_oss_forbid_overwrite"]),
                 ("success_action_status", "200")]:
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (mp, k, v)).encode("utf-8"))
    p = pathlib.Path(path)
    ct = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (mp, p.name, ct)).encode("utf-8"))
    parts.append(p.read_bytes())
    parts.append(("\r\n--%s--\r\n" % mp).encode("utf-8"))
    st, r = _req(d["upload_host"], None, raw=b"".join(parts), method="POST",
                 ctype="multipart/form-data; boundary=" + mp)
    if st not in (200, 201, 204):
        raise SystemExit("参考图上传失败 (%s): %s" % (st, str(r)[:300]))
    return "oss://" + d["key"]


def download(url, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))
    return dest


# ────────────────────────────────────────────────────────── 两种后端
def gen_mm(cfg, prompt, negative, seed, refs):
    content = [{"image": u} for u in refs] + [{"text": prompt}]
    payload = {"model": cfg["model"],
               "input": {"messages": [{"role": "user", "content": content}]},
               "parameters": {"size": cfg["size"], "n": 1, "prompt_extend": True,
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
                              "prompt_extend": False, "seed": seed}}
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
    print("风格参考    : %s" % (", ".join(a.ref) if a.ref else "（无 —— 出来会偏通用）"))
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
               timeout=a.timeout)

    refs = []
    for r in a.ref:
        p = pathlib.Path(r)
        if not p.exists():
            sys.exit("参考图不存在: %s" % r)
        if mode == "mm":
            print("上传参考图  : %s" % p.name, flush=True)
            refs.append(upload_ref(cfg["base"], key, p))
        else:
            refs.append(str(p))

    log = outdir / "calls.jsonl"
    ok = fail = 0
    for sd in seeds:
        t0 = time.time()
        print("[seed %d] %s ..." % (sd, a.model), flush=True)
        url, note = mode_fn(cfg, prompt, negative, sd, refs)
        rec = dict(stage=a.stage, model=a.model, mode=mode, size=a.size, seed=sd,
                   refs=[str(r) for r in a.ref], n_ref=len(refs),
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
            print("  ✓ %s  %.0f KB  (%s)" % (out.name, out.stat().st_size / 1024.0, note))
            ok += 1
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 66)
    print("成功 %d / 失败 %d | 调用记录 %s" % (ok, fail, log))
    print("""
★ 下一步（这两步不能跳）：
  1. 草图/成品位图都要过物理闸口 —— 同一个 check_sketch.py 跑两次：
       python3 scripts/check_sketch.py %s/%s_s*.png --ir <你的.ir.yaml>
     它有半张输出是「必须你/模型看图逐条回答」的 IR 几何约束。
     任何一条答"否" → 改简报重生，不要往下走。
  2. 把选中的那张的位置记下来（seed 写进图注/README），否则复现不了。""" % (outdir, a.stage))


if __name__ == "__main__":
    main()
