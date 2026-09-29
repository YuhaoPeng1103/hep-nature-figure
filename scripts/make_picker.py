#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_picker -- 把 sketch_handoff.py 产的候选，做成**客户自己点**的选择页。

为什么需要它（2026-09-29）：
    sketch_handoff.py 会产 candidates.md + 4up + 可编辑 SVG，材料是全的；
    但「让客户挑」这件事一直没有**入口**、也没有**回执** —— 实际是 agent
    替客户拍板（v3 就是这样：handoff/ 里全都生成了，最后是 agent 自己挑了
    chosen_sketch.png，工作区里找不到任何客户回执）。作者 2026-09-29 要求：
    选择权要真的在客户手上，而且不能靠 agent 自觉。

产物：
    pick.html        客户双击即可看（纯本地、不联网、不依赖任何服务）；
                     每张候选一个大图 + 编号 + **选择码** + 闸口①读数 + 一句话说明；
                     点一下卡片会高亮，并把「回执」两个字复制到剪贴板。
    pick_sheet.png   所有候选一张总览图（贴进聊天窗口用，客户不用开文件）。

用法：
    python scripts/make_picker.py --handoff collective_flow/gen/v5/handoff --tag V5
    # 选项：--notes <json>  给每张候选配一句话说明 {"cand_01": "...", ...}
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

def load_handoff(d: Path):
    p = d / "handoff.json"
    if not p.exists():
        raise SystemExit("找不到 %s —— 先跑 sketch_handoff.py" % p)
    return json.loads(p.read_text(encoding="utf-8"))


def card_html(c, tag, note, picked_first):
    cid = c["cid"]
    code = "%s-%s" % (tag, cid)
    hard = len(c.get("hard") or [])
    soft = len(c.get("soft") or [])
    sel = c.get("selectable", not hard)
    badge = ("<span class='b ok'>闸口① 硬伤 0 / 软警 %d</span>" % soft) if hard == 0 \
        else ("<span class='b bad'>闸口① 硬伤 %d —— 不建议</span>" % hard)
    dis = "" if sel else " disabled"
    img = html.escape(os.path.basename(c["preview"]))
    return """
    <div class="card%(d)s" data-code="%(code)s" tabindex="0">
      <div class="hd"><b>%(cid)s</b> <span class="code">%(code)s</span>%(badge)s</div>
      <img src="%(img)s" alt="%(cid)s">
      <div class="note">%(note)s</div>
      <div class="pick">用这张 &nbsp;<code>%(code)s</code></div>
    </div>""" % {"cid": cid, "code": code, "badge": badge, "img": img,
                 "note": html.escape(note or "（未写说明）"),
                 "d": " dis" if not sel else ""}


HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>%(title)s —— 挑一张草图</title>
<style>
 body{margin:0;background:#f4f6f8;color:#12181f;
      font:15px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 header{position:sticky;top:0;background:#fff;border-bottom:1px solid #dde3ea;
        padding:14px 22px;z-index:9}
 h1{margin:0 0 6px;font-size:19px}
 .sub{color:#5b6673;font-size:13px}
 .how{margin:10px 0 0;padding:10px 14px;background:#f0f6ff;border-left:4px solid #2f7de1;
      font-size:13px;border-radius:4px}
 .how b{color:#12447f}
 .wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));
       gap:16px;padding:18px 22px 120px}
 .card{background:#fff;border:1px solid #dde3ea;border-radius:8px;padding:12px;
       cursor:pointer;transition:.12s;box-shadow:0 1px 2px rgba(20,30,45,.05)}
 .card:hover{border-color:#8fb6ea}
 .card.sel{border-color:#2f7de1;box-shadow:0 0 0 3px #cfe2fb}
 .card.dis{opacity:.5;cursor:not-allowed}
 .hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
 .code{font-family:ui-monospace,Consolas,monospace;font-size:13px;background:#eef2f6;
       padding:2px 8px;border-radius:4px}
 .b{font-size:12px;padding:2px 8px;border-radius:999px}
 .b.ok{background:#e7f6ec;color:#1c6b36}.b.bad{background:#fdeaea;color:#992222}
 img{width:100%%;border:1px solid #eceff3;border-radius:4px;display:block;background:#fff}
 .note{color:#4a5563;font-size:13px;margin:8px 0 6px;min-height:34px}
 .pick{font-size:13px;font-weight:600;color:#2f7de1}
 footer{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #dde3ea;
        padding:12px 22px;box-shadow:0 -2px 10px rgba(20,30,45,.06)}
 footer .line{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 #receipt{font-family:ui-monospace,Consolas,monospace;font-size:15px;background:#f5f8fb;
          border:1px dashed #b9c6d4;padding:7px 12px;border-radius:6px;min-width:230px}
 button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid #2f7de1;
        background:#2f7de1;color:#fff;cursor:pointer}
 button.gray{background:#fff;color:#2f7de1}
 #done{color:#1c6b36;font-weight:600}
</style></head><body>
<header>
  <h1>%(title)s —— 请挑一张草图</h1>
  <div class="sub">%(meta)s</div>
  <div class="how">
    <b>怎么回：</b>点下面任意一张卡片 → 底栏出现<b>选择码</b> → 按住 Ctrl+C 复制，回给我一句就行
    （例如「<code>用 %(first_code)s</code>」）。<br>
    <b>想自己改：</b>说「我改一下」，我把对应的 <code>cand_NN.svg</code> 发你，
    在 Illustrator / Inkscape 里改完传回（改完仍要过闸口①）。<br>
    <b>都不满意：</b>说一声，改简报 / 换 seed 重出一轮（草图上返工最便宜）。
  </div>
</header>
<div class="wrap">
%(cards)s
</div>
<footer><div class="line">
  <b>你选的是：</b><span id="receipt">（还没点）</span>
  <button id="copy">复制选择码</button>
  <button class="gray" id="clear">取消</button>
  <span id="done"></span>
</div></footer>
<script>
var cards=[].slice.call(document.querySelectorAll('.card'));
var rec=document.getElementById('receipt');
cards.forEach(function(c){
  c.addEventListener('click',function(){
    if(c.classList.contains('dis'))return;
    cards.forEach(function(x){x.classList.remove('sel')});
    c.classList.add('sel');
    rec.textContent=c.dataset.code;
    document.getElementById('done').textContent='';
  });
});
document.getElementById('copy').addEventListener('click',function(){
  var t=rec.textContent;
  if(t.indexOf('.png')>=0){return;}
  if(t.indexOf('（')===0){return;}
  navigator.clipboard&&navigator.clipboard.writeText('用 '+t).then(function(){
    document.getElementById('done').textContent='已复制';
  });
});
document.getElementById('clear').addEventListener('click',function(){
  cards.forEach(function(x){x.classList.remove('sel')});
  rec.textContent='（还没点）';document.getElementById('done').textContent='';
});
</script></body></html>
"""


def contact_sheet(cands, tag, notes, out: Path, cols=2, w=900):
    from PIL import Image, ImageDraw, ImageFont

    def font(sz, bold=False):
        # CJK first: the notes are Chinese, and a Latin-only face renders them as blank boxes.
        for n in (("msyhbd.ttc" if bold else "msyh.ttc"),
                  "simhei.ttf", "simsun.ttc", "msyh.ttc",
                  ("segoeuib.ttf" if bold else "segoeui.ttf"), "arialbd.ttf" if bold else "arial.ttf",
                  "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(n, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    F = font(26, True)
    S = font(19)
    tiles = []
    for c in cands:
        p = Path(c["preview"])
        if not p.exists():
            p = Path(c["src"])
        im = Image.open(p).convert("RGB")
        im = im.resize((w, int(im.height * w / im.width)))
        tiles.append((c, im))
    def wrap(txt, fnt, maxw):
        lines, cur = [], ""
        for ch in txt:
            if not cur or fnt.getlength(cur + ch) <= maxw:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines[:2] or [""]

    wrapped = [(c, im, wrap(notes.get(c["cid"]) or "", S, w)) for c, im in tiles]
    rows = (len(tiles) + cols - 1) // cols
    head = 42 + 26 * max(len(t[2]) for t in wrapped)
    th = max(t.height for _, t, _ in wrapped) + head
    W = cols * (w + 24) + 24
    sheet = Image.new("RGB", (W, 76 + rows * th + 16), "white")
    d = ImageDraw.Draw(sheet)
    d.text((24, 20), "请挑一张草图（选择码回给我即可）", fill="#12181f", font=F)
    for i, (c, im, nl) in enumerate(wrapped):
        r, k = divmod(i, cols)
        x = 24 + k * (w + 24)
        y = 76 + r * th
        code = "%s-%s" % (tag, c["cid"])
        hard = len(c.get("hard") or [])
        col = "#b03000" if hard else "#1c6b36"
        d.text((x, y), "%s   [%s]" % (code, ("硬伤 %d" % hard) if hard else "闸口① OK"),
               fill=col, font=F)
        for j, ln in enumerate(nl):
            d.text((x, y + 34 + 26 * j), ln, fill="#4a5563", font=S)
        sheet.paste(im, (x, y + head - 8))
    sheet.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description="生成客户自己点的草图选择页（见文件头）")
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--tag", required=True, help="选择码前缀，例如 V5")
    ap.add_argument("--notes", default=None, help='{"cand_01": "一句话说明"}')
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    hd = Path(a.handoff).resolve()
    d = load_handoff(hd)
    cands = d["candidates"]
    notes = {}
    if a.notes and Path(a.notes).exists():
        notes = json.loads(Path(a.notes).read_text(encoding="utf-8"))
    elif (hd / "notes.json").exists():
        notes = json.loads((hd / "notes.json").read_text(encoding="utf-8"))

    tag = a.tag
    title = a.title or ("%s 草图候选" % tag)
    first = next((c["cid"] for c in cands if c.get("selectable", not c.get("hard"))), cands[0]["cid"])
    meta = "IR: %s &nbsp;|&nbsp; 候选 %d 张 &nbsp;|&nbsp; 画布 %s" % (
        html.escape(str(d.get("ir", "?"))), len(cands),
        "%dx%d" % tuple(cands[0]["size"]) if cands and cands[0].get("size") else "?")

    cards = "\n".join(card_html(c, tag, notes.get(c["cid"]), False) for c in cands)
    out = Path(a.out) if a.out else (hd / "pick.html")
    out.write_text(HTML % {"title": html.escape(title), "meta": meta,
                           "cards": cards, "first_code": "%s-%s" % (tag, first)},
                   encoding="utf-8")
    sheet = contact_sheet(cands, tag, notes, hd / "pick_sheet.png")
    print("已写出 %s" % out)
    print("已写出 %s" % sheet)
    print("选择码：" + "  ".join("%s-%s" % (tag, c["cid"]) for c in cands))
    return 0


if __name__ == "__main__":
    sys.exit(main())