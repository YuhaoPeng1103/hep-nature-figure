# -*- coding: utf-8 -*-
"""gate3d_rank.py —— 把「3D 感」当第一判据的批量入口（2026-10-06，作者要求）。

作者原话：「a 档是一句话加参考图，构图参考是可选项，看用户提不提供，
而且无论用户提供什么，3d 感是首要。」

所以 3D 不是交付前的一道附加检查，而是**挑图的第一关键字**。

用法：
  python scripts/gate3d_rank.py <图片...> [--ir <IR>] [--expect-plane auto|yes|no]
                             [--json <报告.json>] [--require-all] [--top N]

  --require-all   有任意一张不过闸就非零退出（交付档用这个；挑图时不要加）
  --top N         只打印前 N 张

排序键 = 「渲染风格分」（只用三个量，都不依赖版式）：
    score = grad_frac - edge_frac - max(limb, 0)
  · grad_frac  平滑渐变占比 —— 叠渐变的体积明暗，越高越像渲染
  · edge_frac  硬边占比   —— 平涂的细描边越多越大，减分
  · limb       边缘比中部更亮 —— 平涂/贴纸的特征，减分

★ 为什么不用「高光偏离 offcentre」当排序键（2026-10-06 实测）：
  它是**主体那一块浅灰面**的最亮点离几何中心的距离 —— 对球/团块是有效的 3D 线索，
  对**板面**没意义（板不是球，无所谓高光偏移）。实测它会把 A 档那种带大渐变的
  海报排到 C 档干净图前面。所以只当读数打印，不参与排序。
★ 排序**不看闸门结论**：闸门（3D1/3D2/3D3）是交付判据。
  实测教训：3D1「浅灰面 >= 3% 画布」是按「有块明显板面」标定的，
  集体流这批没有大板面的图会被它集体误杀（最大的浅灰面 2.4% 也判 FAIL）。
★ 判据、阈值、标定全在 check_3d_generic.py 里，这里不许另立标准。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(WS, "scripts", "check_3d_generic.py")


def run_one(img, ir, expect, tmpdir):
    out = os.path.join(tmpdir, os.path.splitext(os.path.basename(img))[0] + "_3d.json")
    cmd = [sys.executable, CHECK, img, "--json", out, "--expect-plane", expect]
    if ir:
        cmd += ["--ir", ir]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    rec = {"file": os.path.basename(img), "path": img, "ok": p.returncode == 0}
    try:
        with open(out, encoding="utf-8") as f:
            rep = json.load(f)
        rec["readings"] = rep.get("readings", {})
        rec["fails"] = rep.get("fails", [])
    except Exception:
        rec["readings"] = {}
        rec["fails"] = ["跑不动 check_3d_generic.py"]
    return rec


def score(d):
    """渲染风格分：只用 grad/edge/limb —— 三个都不依赖版式（见文件头）。"""
    return (float(d.get("grad_frac") or 0)
            - float(d.get("edge_frac") or 0)
            - max(float(d.get("limb") or 0), 0.0))


def main():
    ap = argparse.ArgumentParser(description="3D 感批量排序 + 3D 闸门")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--ir", default=None)
    ap.add_argument("--expect-plane", choices=("auto", "yes", "no"), default="auto")
    ap.add_argument("--json", default=None)
    ap.add_argument("--require-all", action="store_true")
    ap.add_argument("--top", type=int, default=0)
    a = ap.parse_args()

    # 临时报告写系统临时目录 —— 别往 skill 仓库里扔文件（v4.5 修）
    tmpdir = tempfile.mkdtemp(prefix="gate3d_")

    recs = [run_one(p, a.ir, a.expect_plane, tmpdir) for p in a.images]
    for r in recs:
        r["score"] = round(score(r["readings"]), 4)
    recs.sort(key=lambda r: -r["score"])
    shown = recs[:a.top] if a.top else recs

    print("=" * 88)
    print("3D 感排序（挑图第一判据）—— 共 %d 张；其中过 3D 闸门的 %d 张"
          % (len(recs), sum(1 for r in recs if r["ok"])))
    print("=" * 88)
    print("  %-32s %-7s %-6s %-9s %-8s %-8s %-8s"
          % ("文件", "3D分", "闸门", "高光偏离", "limb", "平滑渐变", "硬边"))
    for r in shown:
        d = r["readings"]
        print("  %-32s %-7s %-6s %-9s %-8s %-8s %-8s" % (
            r["file"][:32], r["score"], "PASS" if r["ok"] else "FAIL",
            d.get("offcentre", "-"), d.get("limb", "-"),
            d.get("grad_frac", "-"), d.get("edge_frac", "-")))

    bad = [r for r in recs if not r["ok"]]
    if bad:
        print("\n没过 3D 闸门的（交付档不许用，挑图时只作参考）：")
        for r in bad:
            print("  x %s -- %s" % (r["file"], "；".join(r["fails"])[:100]))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"images": recs}, f, ensure_ascii=False, indent=2)
        print("\n报告 -> %s" % a.json)

    if a.require_all and bad:
        print("\n* --require-all：有 %d 张没过 3D 闸门，不许交付。" % len(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
