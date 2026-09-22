# -*- coding: utf-8 -*-
"""fonts.py —— 字体定位（跨平台）

★ 关键约束：用来量字宽的字体，必须和 SVG 里 font-family 指定的字体一致。
  否则 cairo / Illustrator 用别的字体渲染，文字位置与字号全错。

实测坑（别改回去）：
  font-family="Arial, Helvetica, sans-serif" 这种**列表** cairo 解析不了，
  会静默退回 sans-serif —— 宽度差 11.5%（Arial 1076px vs sans-serif 1200px）。
  所以 SVG 里只写**单值** font-family。

用环境变量覆盖：HEP_VEC_FONT / HEP_VEC_FONT_BOLD
"""
import os

_CAND = {
    False: [("HEP_VEC_FONT", None),
            ("C:/Windows/Fonts/arial.ttf", "Arial"),
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "Liberation Sans"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVu Sans"),
            ("/System/Library/Fonts/Supplemental/Arial.ttf", "Arial")],
    True:  [("HEP_VEC_FONT_BOLD", None),
            ("C:/Windows/Fonts/arialbd.ttf", "Arial"),
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "Liberation Sans"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVu Sans"),
            ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "Arial")],
}
_cache = {}


def pick(bold=False):
    """返回 (字体文件路径, SVG 里该写的 font-family 单值)。找不到就报错，不静默降级。"""
    if bold in _cache:
        return _cache[bold]
    for path, fam in _CAND[bold]:
        if fam is None:                       # 环境变量覆盖
            p = os.environ.get(path)
            if p and os.path.exists(p):
                f = "Arial" if "arial" in p.lower() else "Liberation Sans"
                _cache[bold] = (p, f)
                return _cache[bold]
            continue
        if os.path.exists(path):
            _cache[bold] = (path, fam)
            return _cache[bold]
    raise SystemExit(
        "找不到可用字体。装一个（如 fonts-liberation / DejaVu），"
        "或用环境变量指定：HEP_VEC_FONT=/path/to/font.ttf")
