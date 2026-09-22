# -*- coding: utf-8 -*-
"""raster_vector —— 位图 -> 语义分层的全矢量 SVG

  位图（示意图 / 期刊配图）
    ├─ 四叉树平色块   -> 逐像素临摹的色块矢量（quadtree）
    ├─ 文字层         -> 可编辑的真 <text>（labels）
    ├─ 物理元素切分   -> 面板 -> 元素 -> 颜色族 的图层树（elements + panels + groupvec）
    └─ 组装 + 自检     -> SVG + 图层清单（groupvec）

与「像素描摹」的根本差别：**先理解，再临摹**。
  · 文字不是色块，是真 <text>（字号/字体/内容都能改）
  · 图层按物理语义组织（fireball / nucleons / jets / surface …），不是按颜色
  · 逐像素误差可量化：本包实测 MAE 1.48、非文字区 MAE 0.23、PSNR 26.5 dB

依赖：numpy, scipy, Pillow, cairosvg, cairocffi, fontTools（**不需要 cv2 / skimage**）
"""
