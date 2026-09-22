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


_CAND_MATH = [
    ("HEP_VEC_FONT_MATH", None),
    ("C:/Windows/Fonts/DejaVuSans.ttf", "DejaVu Sans"),
    ("C:/Windows/Fonts/ARIALUNI.TTF", "Arial Unicode MS"),
    ("C:/Windows/Fonts/seguisym.ttf", "Segoe UI Symbol"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVu Sans"),
]


def _family_of(path):
    """从 TTF/OTF 里读**真正的** family name。

    ★ 实测坑：环境变量覆盖分支原来写死
      `"Arial" if "arial" in p.lower() else "Liberation Sans"`，
      于是 `HEP_VEC_FONT=DejaVuSans.ttf` 会在 SVG 里写
      `font-family="Liberation Sans"`，而量字宽用的是 DejaVuSans.ttf ——
      两者字宽不同，**文字整体错位，而且完全静默**。
      本模块的头号纪律就是「量字宽的字体必须和 SVG 里写的族名一致」，
      所以族名只能从字体文件本身读，不能靠文件名猜。
    fontTools 本来就是本包的依赖（labels.py 用它读 hmtx），这里不新增依赖。
    """
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(path, fontNumber=0, lazy=True)
        try:
            for rec in t["name"].names:
                if rec.nameID == 1:
                    fam = rec.toUnicode().split("\x00")[0].strip()
                    if fam:
                        for suf in (" Bold Italic", " Bold Oblique", " Bold",
                                    " Italic", " Oblique", " Regular", " Light",
                                    " Medium", " SemiBold"):
                            if fam.endswith(suf):
                                fam = fam[: -len(suf)]
                        return fam
        finally:
            t.close()
    except Exception as e:
        raise SystemExit("读不出 %s 的 family name（%s）。"
                         "族名必须和字体文件一致，不能猜 —— 换个字体文件，"
                         "或修好它的 name 表。" % (path, e))
    raise SystemExit("%s 的 name 表里没有 family name。" % path)


def pick_math():
    """数学符号兜底字体 —— 主字体（Arial）没有 ⊥ ≳ ⟨⟩ 这类字符时用它。

    实测：Arial 缺 U+22A5(⊥) / U+2273(≳) / U+27E8-9(⟨⟩)。缺字的标签会被
    labels.has_glyph 静默丢掉，所以要么换字体、要么丢标签 —— 这里选换字体。
    找不到就返回 (None, None)，调用方按「没有兜底」处理（照旧丢标签），不报错。
    """
    if "math" in _cache:
        return _cache["math"]
    for path, fam in _CAND_MATH:
        if fam is None:
            p = os.environ.get(path)
            if p and os.path.exists(p):
                _cache["math"] = (p, _family_of(p))
                return _cache["math"]
            continue
        if os.path.exists(path):
            _cache["math"] = (path, fam)
            return _cache["math"]
    _cache["math"] = (None, None)
    return _cache["math"]


def pick(bold=False):
    """返回 (字体文件路径, SVG 里该写的 font-family 单值)。找不到就报错，不静默降级。"""
    if bold in _cache:
        return _cache[bold]
    for path, fam in _CAND[bold]:
        if fam is None:                       # 环境变量覆盖
            p = os.environ.get(path)
            if p and os.path.exists(p):
                _cache[bold] = (p, _family_of(p))
                return _cache[bold]
            continue
        if os.path.exists(path):
            _cache[bold] = (path, fam)
            return _cache[bold]
    raise SystemExit(
        "找不到可用字体。装一个（如 fonts-liberation / DejaVu），"
        "或用环境变量指定：HEP_VEC_FONT=/path/to/font.ttf")
