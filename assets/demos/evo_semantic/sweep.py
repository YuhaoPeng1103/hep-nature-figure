# -*- coding: utf-8 -*-
"""sweep.py -- 位图→矢量的【配置扫描 + 量化评价】实验台（可复用）

为什么要有它
------------
「像不像」不能靠眼睛说。临摹的参数（--q 调色板 / --R 四叉树色差 / 要不要真渐变）
互相耦合，改一个就动全身 —— 实测本图：真渐变在 --q 16 时救地板色阶、
到 --q 32 时反而**更差**（见 README.md 的 A/B 表）。所以先立两个**自动**指标：

  MAE / >8% / >32%   逐像素 —— 忠实度。★ 有两个 MAE 口径，别混：
                       MAE      = 通道平均差（与 raster_to_vector_semantic.py 的
                                  --check 自检同一个定义，可直接对照）
                       MAEmax   = 最大通道差（更严；单通道偏色不互相稀释）
  贴边比             在「源图本来就平滑」的像素上，复现图的相邻像素 |梯度| 均值
                     ÷ 源图同一处的均值 —— 平滑度
                     >1 = 复现图比源图更"花"（块感/斑块/色阶台阶都在这里露出来）
                     <1 = 比源图更光滑（把源图的低幅噪点磨掉了，通常是好事）
                     注意：它量不到大面积的 1~2 级色阶台阶（台阶边界像素占比很小），
                     所以色阶台阶还要靠**放大对照图**看 —— 本脚本会顺手出对照图。

用法
----
    python3 sweep.py --src gen/render_s31_clean.png --words words.txt \
                     --panels sweep_panels.py --cases sweep_cases.json --outdir gen
    每个用例产出 gen/_sw_<tag>.svg 与 gen/_sw_<tag>_sbs.png（上=源位图 下=复现）
"""
import argparse, io, json, os, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
import cairosvg

ALL = ["stage1-nucleus", "stage2-fluctuations", "stage3-nucleus-A", "stage3-nucleus-B",
       "stage3-overlap", "stage4-fireball", "stage4-nucleons"]


def find_runner():
    """定位 raster_to_vector_semantic.py：环境变量 HEPNF_SCRIPTS > 从本文件往上找"""
    env = os.environ.get("HEPNF_SCRIPTS")
    if env:
        p = Path(env)
        return p / "raster_to_vector_semantic.py" if (p / "raster_to_vector_semantic.py").exists() \
            else p / "scripts" / "raster_to_vector_semantic.py"
    here = Path(__file__).resolve()
    for up in here.parents:
        for c in (up / "scripts" / "raster_to_vector_semantic.py",
                  up / "raster_to_vector_semantic.py"):
            if c.exists():
                return c
    raise SystemExit("找不到 raster_to_vector_semantic.py（设 HEPNF_SCRIPTS=<scripts 目录>）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--words", default="")
    ap.add_argument("--panels", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--outdir", default="gen")
    ap.add_argument("--W", type=int, default=0, help="工作宽度（默认=源图宽度）")
    ap.add_argument("--K", type=int, default=7)
    ap.add_argument("--sbs", action="store_true", default=True, help="出对照图（默认出）")
    a = ap.parse_args()

    runner = find_runner()
    src_img = Image.open(a.src).convert("RGB")
    W, H = src_img.size
    Wd = a.W or W
    src = np.asarray(src_img, float)
    if Wd != W:
        src_img = src_img.resize((Wd, int(H * Wd / W)), Image.LANCZOS)
        src = np.asarray(src_img, float)
    H = src.shape[0]

    def lum(i):
        return 0.299 * i[..., 0] + 0.587 * i[..., 1] + 0.114 * i[..., 2]

    Ls = lum(src)
    med = ndimage.median_filter(Ls, size=21)
    flat = (med < 232) & (np.abs(med - Ls) < 10)          # 源图本来就平滑的地方
    fx = flat[:, :-1] & flat[:, 1:]
    fy = flat[:-1, :] & flat[1:, :]
    ex0 = np.abs(np.diff(Ls, axis=1))[fx].mean()
    ey0 = np.abs(np.diff(Ls, axis=0))[fy].mean()
    print("源图平滑体贴边能量: Ex %.3f Ey %.3f (n=%d)" % (ex0, ey0, fx.sum()))

    def ratio(Lr):
        return (np.abs(np.diff(Lr, axis=1))[fx].mean() / ex0,
                np.abs(np.diff(Lr, axis=0))[fy].mean() / ey0)

    cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))["cases"]
    rows = []
    for cs in cases:
        tag, R, Q = cs["tag"], str(cs.get("R", 10)), str(cs.get("Q", 16))
        kill = cs.get("kill", [])
        js = {e: None for e in (ALL if "*" in kill else kill)}
        js.update(cs.get("spec") or {})
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        if js:
            env["EXP_JSON"] = json.dumps(js)
        out = os.path.abspath(os.path.join(a.outdir, "_sw_%s.svg" % tag))
        # ★ 一律传绝对路径：子进程的 cwd 不确定，而 --panels / --words 是**相对 cwd**
        #   解析的（实测踩过：漏了 env=env 让 A/B 两档跑出完全一样的数）。
        cmd = [sys.executable, str(runner), os.path.abspath(a.src), "-o", out,
               "--panels", os.path.abspath(a.panels), "--W", str(Wd),
               "--R", R, "--K", str(a.K), "--q", Q]
        if a.words:
            cmd += ["--words", os.path.abspath(a.words)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        log = r.stdout + r.stderr
        npath = re.search(r"<path> (\d+) \| <text>", log)
        if not npath or not os.path.exists(out):
            print("[%s] 失败\n%s" % (tag, log[-1500:]))
            continue
        png = cairosvg.svg2png(url=out, output_width=Wd, output_height=H)
        re_ = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), float)
        d = np.abs(src - re_).max(2)
        rx, ry = ratio(lum(re_))
        mse = ((src - re_) ** 2).mean()
        mae = float(np.abs(src - re_).mean())
        print("[%s] R%s Q%s | MAE %.3f (MAEmax %.3f) | >8 %.2f%% | >32 %.2f%% | "
              "PSNR %.2f dB | 贴边比 %.2f/%.2f | path %s | %.2f MB"
              % (tag, R, Q, mae, d.mean(), (d > 8).mean() * 100, (d > 32).mean() * 100,
                 10 * np.log10(255 * 255 / mse), rx, ry, npath.group(1),
                 os.path.getsize(out) / 1e6))
        rows.append((tag, mae, (d > 8).mean() * 100, rx, int(npath.group(1))))
        if a.sbs:
            gap = 14
            c = Image.new("RGB", (Wd, H * 2 + gap), "white")
            c.paste(Image.fromarray(src.astype(np.uint8)), (0, 0))
            c.paste(Image.fromarray(re_.astype(np.uint8)), (0, H + gap))
            c.save(os.path.join(a.outdir, "_sw_%s_sbs.png" % tag))
        sys.stdout.flush()
    if rows:
        print("\n=== 汇总（忠实度↑ / 平滑度：贴边比→1.0 最好）===")
        for t, m, e, r, n in sorted(rows, key=lambda z: z[1]):
            print("  %-18s MAE %.3f  >8 %.2f%%  贴边比 %.2f  path %d" % (t, m, e, r, n))


if __name__ == "__main__":
    main()