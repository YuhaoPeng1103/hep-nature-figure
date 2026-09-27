# -*- coding: utf-8 -*-
"""PDF 回渲染验收在本算例里用**通用工具**跑，不再保留私有副本：

    python3 scripts/pdf_roundtrip.py evo.pdf --src src_render.png -o gen/pdf_render.png -c cmp_pdf.png

（这个文件原来叫 verify_final.py，在算例目录里长出来之后被提升成了通用脚本 ——
  它抓的坑是「按 W/pageWidth 直接回渲染会得到 5 倍假性 MAE」，与哪一张图无关。）
"""