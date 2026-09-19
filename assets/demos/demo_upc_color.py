#!/usr/bin/env python3
"""
UPC 图 v2 —— 修正版
====================
v1 的问题（用户一眼看出）：
  · IR 里我把它定义成"纯线条无渐变" → 选 TikZ → 得到 1980 年代教科书插图
  · 饱和度 0.002，而 T3 类内区间 [0.242, 0.370] —— 全类都有色，就它纯黑白
  · 门禁当时把它放过了（我把 saturation 降级成"仅提醒"）

v2 的修正：
  · 核用彩色渐变 + 核子，不再是空椭圆
  · 光子交换用发光的波浪线（电磁场的视觉语言）
  · 顶点有闪光
  · 构图均衡，不留大片空白
"""
import math, random, sys
from pathlib import Path
sys.path.insert(0,'hep-nature-figure/scripts')
from svg_lib import SVG
import geom

OUT=Path("repro"); OUT.mkdir(exist_ok=True)
W,H=806,382
s=SVG(W,H)
FONT="DejaVu Sans"

def nucleus(cx, cy, rx, ry, base_hi, base_mid, base_lo, seed=3):
    """彩色核：渐变 + 描边 + 内部核子"""
    m = s.radial([(0.00, base_hi, 0.96), (0.42, base_mid, 0.93),
                  (1.00, base_lo, 0.90)], cx=0.38, cy=0.34, r=0.82)
    s.add(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
          f'fill="url(#{m})" stroke="{base_lo}" stroke-width="2.0" '
          f'stroke-opacity="0.9"/>')
    rng=random.Random(seed); pts=[]
    for i in range(13):
        for _ in range(20):
            a=rng.uniform(0,2*math.pi); d=math.sqrt(rng.uniform(0,1))
            px,py=cx+d*rx*0.70*math.cos(a), cy+d*ry*0.70*math.sin(a)
            r=rng.uniform(3.0,4.8)
            if all((px-qx)**2+(py-qy)**2>(r+qr*0.85)**2 for qx,qy,qr in pts):
                pts.append((px,py,r)); break
    pts.sort(key=lambda q:(q[1],q[0]))
    for (px,py,r) in pts:
        mm=s.radial([(0.0,"#e8eeff",0.85),(0.35,base_hi,0.95),(1.0,base_lo,1.0)],
                    cx=0.35,cy=0.30,r=0.80)
        s.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" '
              f'fill="url(#{mm})"/>')

def glow_line(x1,y1,x2,y2,col,w,op=0.30,blur=6):
    s.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
          f'stroke="{col}" stroke-width="{w}" stroke-opacity="{op}" '
          f'stroke-linecap="round" filter="url(#{s.blur(blur)})"/>')

def wave(x1,y1,x2,y2,amp,turns,col,w,op=1.0):
    a=math.atan2(y2-y1,x2-x1); L=math.hypot(x2-x1,y2-y1); p=[]
    for i in range(81):
        t=i/80; u=t*L; v=math.sin(t*turns*2*math.pi)*amp
        p.append((x1+u*math.cos(a)-v*math.sin(a), y1+u*math.sin(a)+v*math.cos(a)))
    d="M "+" L ".join(f"{x:.1f} {y:.1f}" for x,y in p)
    s.add(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" '
          f'stroke-linecap="round" opacity="{op}"/>')

def arrow(x1,y1,x2,y2,col,w):
    a=math.atan2(y2-y1,x2-x1)
    s.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
          f'stroke="{col}" stroke-width="{w}" stroke-linecap="round"/>')
    L=w*5.0; px,py=-math.sin(a),math.cos(a)
    s.add(f'<path d="M {x2:.1f} {y2:.1f} '
          f'L {x2-L*math.cos(a)+px*L*0.52:.1f} {y2-L*math.sin(a)+py*L*0.52:.1f} '
          f'L {x2-L*math.cos(a)-px*L*0.52:.1f} {y2-L*math.sin(a)-py*L*0.52:.1f} Z" '
          f'fill="{col}"/>')

def tx(x,y,t,sz=15,an="middle",col="#1a1a1a"):
    s.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{sz}" font-family="{FONT}" '
          f'fill="{col}" text-anchor="{an}">{t}</text>')

# ── 几何 ──
CA, CB = 92, 286          # 上核 / 下核中心 y
XA, XB = 108, 692          # 左 / 右核中心 x
RX, RY = 31, 62
VX, VY = 400, 189          # 相互作用顶点

s.begin_layer("layer-nuclei","1 原子核")
nucleus(XA, CA, RX, RY, "#8ea4f0", "#3a52b8", "#141f6e", seed=1)   # A 蓝
nucleus(XA, CB, RX, RY, "#b096e8", "#6a3ab8", "#2a146e", seed=2)   # B 紫
nucleus(XB, CA, RX, RY, "#8ea4f0", "#3a52b8", "#141f6e", seed=4)
nucleus(XB, CB, RX, RY, "#b096e8", "#6a3ab8", "#2a146e", seed=5)
s.end_layer()

s.begin_layer("layer-arrows","2 速度箭头")
# 核 A 向右（蓝色系），核 B 向左（紫色系）
arrow(XA+RX+8, CA, XA+142, CA, "#3a4fa8", 4.4)
arrow(XB-RX-8, CB, XB-142, CB, "#5a3aa8", 4.4)
s.end_layer()

s.begin_layer("layer-photons","3 光子交换")
# 两核之间的电磁相互作用：发光的波浪线
# 光子线从【上核下缘】到【下核上缘】——现在间距有 70px，波能展开
for dx in (-86, 86):
    glow_line(VX+dx, CA+RY+4, VX+dx, CB-RY-4, "#5ac8ff", 15, 0.32, 8)
    wave(VX+dx, CA+RY+4, VX+dx, CB-RY-4, 11, 4, "#2a8fd0", 2.5)
# 碰撞参数 b：上下核中心之间的虚线 + 参考线
s.add(f'<line x1="{VX}" y1="{CA}" x2="{VX}" y2="{CB}" stroke="#333" '
      f'stroke-width="1.3" stroke-dasharray="6 4"/>')
for yy, lbl in [(CA, None), (CB, None)]:
    s.add(f'<line x1="{VX-70}" y1="{yy}" x2="{VX+70}" y2="{yy}" '
          f'stroke="#888" stroke-width="0.9"/>')
tx(VX-12, (CA+CB)/2+6, "b", 16, "end", "#333")
s.end_layer()

s.begin_layer("layer-vertex","4 相互作用顶点")
gl = s.mat_glow("#ffe08a")
s.add(f'<circle cx="{VX}" cy="{VY}" r="52" fill="url(#{gl})" opacity="0.85"/>')
for i in range(12):
    a=2*math.pi*i/12
    s.add(f'<line x1="{VX}" y1="{VY}" x2="{VX+26*math.cos(a):.1f}" '
          f'y2="{VY+26*math.sin(a):.1f}" stroke="#b06010" stroke-width="2.0" '
          f'stroke-linecap="round" opacity="0.85"/>')
s.add(f'<circle cx="{VX}" cy="{VY}" r="5" fill="#fff8e0" stroke="#b06010" '
      f'stroke-width="1.2"/>')
s.end_layer()

s.begin_layer("layer-final","5 末态粒子")
arrow(VX+10, VY-4, VX+138, VY-78, "#c0392b", 3.2)
arrow(VX-10, VY+4, VX-138, VY+78, "#2a6ae0", 3.2)
s.end_layer()

s.begin_layer("layer-labels","6 标注")
tx(XA, CA-RY-20, "nucleus A", 15)
tx(XB+22, CB+RY+6, "nucleus B", 15, "start")
tx(XA+96, CA-18, "v", 15)
tx(XB-100, CB-14, "v", 15)
tx(VX-96, VY-24, "γ", 17)
tx(VX+96, VY+34, "γ", 17)
tx(VX+30, VY+52, "γγ → X", 15, "start")
tx(VX+140, VY-88, "e⁺", 16, "start", "#8a1a10")
tx(VX-140, VY+94, "e⁻", 16, "end", "#14327a")
s.add(f'<text x="{W/2}" y="{H-16}" font-size="14" font-family="{FONT}" '
      f'fill="#1a1a1a" text-anchor="middle">Ultra-peripheral collision: the '
      f'nuclei pass without overlapping; the interaction is purely '
      f'electromagnetic</text>')
s.end_layer()

s.save(OUT/"upc_v2.svg"); s.render(OUT/"upc_v2.png", width=1900)
s.render(OUT/"upc_v2.pdf")
print("已输出 upc_v2")
