"""Hand-built editable SVG of the supplied jet quenching schematic.

The reference is used only to judge layout, proportions and palette. No raster
read, tracing, filters or image embedding are required to rebuild this SVG.
"""
from html import escape
from math import hypot, sin, cos, pi
from pathlib import Path
from random import Random

import cairosvg

OUT = Path(__file__).resolve().parent
W, H = 840, 459
OUTPUT = (2336, 1280)


def tag(name, inside=None, **kw):
    a = ''.join(f' {k.replace("_", "-")}="{escape(str(v), quote=True)}"'
                for k, v in kw.items() if v is not None)
    return f'<{name}{a}/>' if inside is None else f'<{name}{a}>{inside}</{name}>'


def fmt(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.')


def xy(point):
    return ','.join(fmt(v) for v in point)


def url(name):
    return f'url(#{name})'


def path(d, fill='none', **kw):
    return tag('path', d=d, fill=fill, **kw)


def line(a, b, stroke, width, **kw):
    return path(f'M {xy(a)} L {xy(b)}', stroke=stroke, stroke_width=width, **kw)


def ellipse(x, y, rx, ry, fill, **kw):
    return tag('ellipse', cx=x, cy=y, rx=rx, ry=ry, fill=fill, **kw)


def polygon(points, fill, **kw):
    return tag('polygon', points=' '.join(xy(p) for p in points), fill=fill, **kw)


def layer(id_, label, children):
    return (f'<g id="{id_}" inkscape:groupmode="layer" inkscape:label="{escape(label)}" '
            f'data-element="{id_}">' + '\n' + '\n'.join(children) + '\n</g>')


def ntext(x, y, content, size=12, **kw):
    return tag('text', content, x=x, y=y, font_family='Arial', font_size=size, fill='#171717', **kw)


def grad(kind, id_, stops, **kw):
    s = ''.join(tag('stop', offset=p, stop_color=c, stop_opacity=o)
                for p, c, o in (tuple(t) if len(t) == 3 else (*t, 1) for t in stops))
    return tag(kind+'Gradient', s, id=id_, **kw)


def radial(id_, stops, **kw):
    return grad('radial', id_, stops, **kw)


def linear(id_, a, b, stops):
    return grad('linear', id_, stops, x1=a[0], y1=a[1], x2=b[0], y2=b[1],
                gradientUnits='userSpaceOnUse')


def pointer(a, b, color='#181a1c', width=1.4, head=9, half=3.2, id_=None):
    d = hypot(b[0]-a[0], b[1]-a[1])
    ux, uy = (b[0]-a[0])/d, (b[1]-a[1])/d
    base = (b[0]-head*ux, b[1]-head*uy)
    h = [b, (base[0]-uy*half, base[1]+ux*half),
         (base[0]+uy*half, base[1]-ux*half)]
    return tag('g', line(a, (b[0]-head*.76*ux, b[1]-head*.76*uy), color, width,
                         data_axis=id_.removeprefix('axis-')) +
               polygon(h, color), id=id_)


board = [(56, 169), (531, 66), (798, 237), (266, 407)]
a, b, c, d = board
board_d = 'M ' + ' L '.join(xy(p) for p in board) + ' Z'


def project(u, v):
    """Projective grid on the four given board corners."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    dx, dy = d
    x1, x2, sx = bx-cx, dx-cx, ax-bx+cx-dx
    y1, y2, sy = by-cy, dy-cy, ay-by+cy-dy
    det = x1*y2-x2*y1
    g = (sx*y2-x2*sy)/det
    h = (x1*sy-sx*y1)/det
    den = 1+g*u+h*v
    return ((ax+((1+g)*bx-ax)*u+((1+h)*dx-ax)*v)/den,
            (ay+((1+g)*by-ay)*u+((1+h)*dy-ay)*v)/den)


plasma_outline = ('M305.8 190.7 C304.9 179.4 310.0 170.2 315.6 158.6 '
                  'C321.8 144.7 328.5 123.6 339.8 110.5 C352.2 96.1 370.0 86.5 389.0 82.4 '
                  'C412.0 75.1 432.2 78.8 452.8 85.2 C473.8 91.7 495.0 97.1 507.8 113.3 '
                  'C512.0 119.4 514.3 123.3 522.2 130.9 C534.0 142.7 537.4 164.6 537.5 181.8 '
                  'C538.2 194.1 532.0 210.6 526.5 224.8 C518.7 245.1 511.9 254.8 497.2 270.5 '
                  'C486.6 281.8 470.7 286.5 450.8 291.6 C426.2 297.8 402.2 299.9 378.6 292.5 '
                  'C356.9 288.9 338.4 283.6 328.6 266.1 C322.2 255.4 322.0 245.6 315.6 229.7 '
                  'C311.0 216.7 307.5 202.9 305.8 190.7 Z')


defs = [
    tag('clipPath', path(board_d), id='board-clip'),
    tag('clipPath', path(plasma_outline, '#fff'), id='plasma-clip'),
    linear('board-face', (330, 365), (245, 95),
           [(0,'#d7dbe2'),(.54,'#dcdde1'),(1,'#d7dbe1')]),
    linear('board-grid', (300, 398), (321, 88),
           [(0,'#abb2bb',.78),(.67,'#a9afb6',.58),(1,'#a5adb6',.49)]),
    radial('contact-dark', [(0,'#262836',.74),(.36,'#393a45',.52),(.70,'#555762',.24),(1,'#5f6476',0)]),
    radial('contact-soft', [(0,'#3b3e4b',.34),(.46,'#464858',.25),(.74,'#5a626e',.11),(1,'#676c79',0)]),
    radial('contact-plasma', [(0,'#382c25',.57),(.37,'#4e3e38',.42),(.67,'#64584f',.25),(1,'#736862',0)]),
    radial('overspill', [(0,'#db9a5d',.20),(.51,'#e3a76c',.12),(.78,'#eac8ac',.035),(1,'#ebcbb4',0)]),
    radial('plasma-volume', [(0,'#ffe9b9'),(.22,'#ffd39d'),(.42,'#f6ad70'),(.61,'#e98440'),
                             (.77,'#d26a2d'),(.91,'#ac4c1e'),(1,'#8e3919')],
           cx='.48', cy='.45', r='.65', fx='.43', fy='.33'),
    radial('plasma-vol-light', [(0,'#fff8dc',.82),(.38,'#ffdcab',.63),(.69,'#ffbc79',.26),(1,'#ffd1a5',0)],
           cx='.50', cy='.50', r='.50', fx='.47', fy='.42'),
    linear('plasma-top-shade', (405, 81), (405, 154),
           [(0,'#9c3304',.61),(.22,'#ab420d',.49),(.50,'#b54c0e',.28),
            (.73,'#bd540e',.12),(1,'#c95710',0)]),
    linear('plasma-left-shade', (304, 179), (365, 179),
           [(0,'#a33a08',.74),(.26,'#ad4010',.42),(.56,'#b85018',.16),(1,'#bd5b27',0)]),
    linear('plasma-right-shade', (538, 183), (482, 183),
           [(0,'#8d391a',.52),(.22,'#a44218',.34),(.56,'#b14819',.13),(1,'#c15820',0)]),
    linear('deep-plasma', (411, 189), (411, 296),
           [(0,'#923905',0),(.28,'#943c0a',.02),(.61,'#763616',.17),(1,'#572d17',.55)]),
    linear('left-beam', (93, 260), (137, 248),
           [(0,'#a1adba',.72),(.44,'#8c98a8',.90),(1,'#798698')]),
    linear('right-beam', (766, 129), (721, 142),
           [(0,'#a4adbb',.65),(.39,'#8996a5'),(1,'#7e899a')]),
    linear('escaping-tone', (273, 11), (380, 153),
           [(0,'#008acc'),(.17,'#00a6de'),(.52,'#06c5ee'),(.78,'#5be5f4'),
            (.93,'#b6f0e4'),(1,'#f7f6c5')]),
    linear('quenched-tone', (379, 155), (567, 389),
           [(0,'#ebe6c7'),(.18,'#b9bfb8'),(.51,'#a5aaab'),(.80,'#929ba7'),(1,'#515c66')]),
    radial('scatter-glow', [(0,'#ffffdd',1),(.10,'#fffbba',.92),(.30,'#ffec94',.55),
                             (.55,'#ffe591',.19),(1,'#ffebac',0)]),
    linear('radiation-cream', (500, 188), (576, 352),
           [(0,'#fff0cc',.46),(.19,'#fff0d5',.64),(.61,'#fff8e9',.87),(1,'#fff9ec',.92)]),
    linear('radiation-orange', (399, 192), (539, 334),
           [(0,'#d9a16a',.88),(.38,'#d9965b',.72),(.71,'#f5ad70',.84),(1,'#e99667',.73)]),
]

for name, palette in {
    'pearl': ['#f7f7fb','#d7d8e3','#a6a8b8','#808296','#616685','#51566d'],
    'pearl-blue': ['#eeeeF5','#cacedb','#a2a4b6','#7c7f95','#626684','#51556d'],
    'pearl-silver': ['#f8f8fe','#dce0e9','#b4b5c3','#8b8ea3','#686c88','#535971'],
    'pearl-shadow': ['#c6c9d6','#aaacbf','#8e91a8','#757994','#606582','#50536b'],
}.items():
    defs.append(radial(name, list(zip([0,.20,.44,.66,.86,1],palette)),
                       cx='.49', cy='.48', r='.59', fx='.34', fy='.29'))

for name, colors in {
    'cobalt': ['#699cdc','#466fbd','#30549a'],
    'azure': ['#77a8e6','#3474bb','#28579a'],
    'emerald': ['#77bc69','#41a55d','#288755'],
    'red': ['#e28463','#c85d45','#a84a34'],
    'violet': ['#8b83de','#6059bd','#5147a2'],
    'gold': ['#f3d862','#dab62d','#b99421'],
    'bronze': ['#e7b36b','#bd9461','#a57748'],
    'ash': ['#bbb096','#a3977a','#847558'],
}.items():
    defs.append(radial('parton-'+name, list(zip([0,.52,1],colors)),
                       cx='.49', cy='.48', r='.56', fx='.32', fy='.28'))

layers = [layer('background','00 White background',
                [tag('rect',x=0,y=0,width=W,height=H,fill='#fff')])]
layers += [layer('reaction-plane','01 Reaction plane · x–z grid',[
    path('M56 169 L266 407 L798 237 L798 239.3 L266.3 408.5 L55.2 171.2 Z','#a8aeba',opacity=.8),
    path(board_d, url('board-face'), stroke='#a0a8b5', stroke_width=.75),
    tag('g', '\n'.join(
        [line(project(i/9,0), project(i/9,1), url('board-grid'), 1.15, id=f'grid-x-{i}')
         for i in range(1,9)] +
        [line(project(0,j/7), project(1,j/7),url('board-grid'),1.05,id=f'grid-z-{j}')
         for j in range(1,7)]), clip_path=url('board-clip'), id='continuous-grid'),
    line(d,c,'#a0a9b7',1.65,opacity=.73,id='front-board-edge'),
])]
layers += [layer('cast-shadows','02 Cast and contact shadows',[
    ellipse(209,302,86,29,url('contact-soft'),transform='rotate(-15 209 302)',opacity=.6),
    ellipse(534,302,166,90,url('overspill'),transform='rotate(5 534 302)'),
    tag('g','\n'.join([
        ellipse(206,292,82,36,url('contact-soft'),transform='rotate(20 206 292)'),
        ellipse(202,295,63,27,url('contact-dark'),transform='rotate(22 202 295)'),
        ellipse(679,206,83,35,url('contact-soft'),transform='rotate(22 679 206)'),
        ellipse(677,215,60,27,url('contact-dark'),transform='rotate(10 677 215)'),
        ellipse(438,268,157,69,url('contact-soft'),transform='rotate(-6 438 268)'),
        ellipse(428,265,130,57,url('contact-plasma'),transform='rotate(-7 428 265)'),
        ellipse(423,276,103,38,url('contact-plasma'),transform='rotate(-8 423 276)',opacity=.76),
    ]),clip_path=url('board-clip'),id='shadows-on-board'),
])]
layers += [layer('incoming-arrows','03 Incoming Pb beam arrows',[
    polygon([(94,254),(113,248),(110,241),(137,247),(121,264),(119,259),(101,265)],url('left-beam'),id='left-beam-arrow'),
    polygon([(764,134),(742,140),(745,146),(722,140),(738,123),(740,129),(758,123)],url('right-beam'),id='right-beam-arrow'),
])]

# Coordinates are hand placed, in the 2× detail coordinate system of each Pb
# cluster. Listed rear surface to front; every nucleon remains its own ellipse.
left = [
    (38,86,18,24),(23,114,15,24),(26,147,15,22),(45,172,16,21),
    (72,194,19,22),(101,195,20,22),(129,185,19,24),(159,174,22,23),(186,153,23,23),
    (216,128,24,23),(228,100,17,22),(217,72,21,20),(201,51,22,20),
    (165,41,25,24),(124,35,23,20),(88,46,21,18),(60,60,19,20),
    (202,91,22,23),(179,69,22,22),(126,57,26,26),(92,76,24,24),(56,83,21,22),
    (49,122,20,25),(68,110,23,23),(36,125,15,22),(39,148,17,23),(64,171,21,23),
    (89,181,22,22),(115,176,25,24),(153,161,25,24),(193,135,25,25),
    (224,107,24,28),(185,99,24,26),(151,80,24,25),(115,101,24,26),
    (71,105,23,22),(73,141,24,25),(111,139,24,24),(149,121,23,26),
]
right = [
    (65,32,16,17),(94,25,17,15),(125,26,19,15),(151,37,21,18),
    (174,52,20,19),(196,66,18,19),(195,86,17,21),(202,109,21,23),
    (199,136,22,23),(186,156,21,23),(167,175,22,24),(142,180,21,23),
    (114,182,22,24),(84,179,21,22),(62,168,19,22),(43,148,18,21),
    (34,124,15,23),(27,96,16,22),(31,73,16,19),(43,54,18,17),
    (54,47,17,17),(86,44,22,22),(115,34,20,19),(145,45,20,21),
    (190,88,20,25),(195,139,22,23),(177,164,21,22),(152,167,24,23),
    (112,169,25,23),(82,172,23,21),(67,154,23,23),(44,129,19,21),
    (33,99,18,23),(54,76,20,23),(88,79,23,23),(126,51,23,21),
    (167,68,24,25),(202,95,21,23),(170,115,25,24),(136,121,22,24),
    (129,89,21,22),(64,111,23,23),(101,122,23,26),
]


def nucleus(items, offset, prefix):
    rng = Random(47 if prefix=='left' else 19)
    palette = ('pearl','pearl-blue','pearl-silver','pearl','pearl-blue','pearl-silver')
    center = (194, 251, 47, 41) if prefix == 'left' else (672, 166, 44, 37)
    ans = [ellipse(*center,url('pearl-shadow'),id=f'{prefix}-nucleus-mid-volume')]
    for i, (x,y,rx,ry) in enumerate(items,1):
        fill = 'pearl-shadow' if i<16 and y > 125 else rng.choice(palette)
        cx,cy=offset[0]+x/2,offset[1]+y/2
        ans.append(ellipse(fmt(cx),fmt(cy),fmt(rx*.49),fmt(ry*.49),url(fill),
                           stroke='#6c7088',stroke_opacity=.14,stroke_width=.45,
                           id=f'{prefix}-nucleon-{i:02}'))
    return ans


layers += [layer('lead-left','04 Pb nucleus · near side',nucleus(left,(134,194),'left')),
           layer('lead-right','05 Pb nucleus · far side',nucleus(right,(614,113),'right'))]

rim = [path(plasma_outline, stroke='#cb6947', stroke_width=w, opacity=o,
            stroke_linejoin='round',id=f'qgp-halo-{i}')
       for i,(w,o) in enumerate([(18,.023),(15,.027),(12,.042),(10,.058),
                                (8,.076),(6,.09),(4,.15),(2,.19)],1)]
layers += [layer('qgp','06 QGP medium · editable volume and shading',[
    *rim,
    path(plasma_outline,url('plasma-volume'),id='qgp-shape'),
    tag('g','\n'.join([
        ellipse(419,167,127,107,url('plasma-vol-light'),id='energy-density-core'),
        path(plasma_outline,url('plasma-top-shade'),id='upper-volume-shading'),
        path(plasma_outline,url('plasma-left-shade'),id='left-volume-shading'),
        path(plasma_outline,url('plasma-right-shade'),id='right-volume-shading'),
        path(plasma_outline,url('deep-plasma'),id='lower-volume-shading'),
    ]),clip_path=url('plasma-clip'),id='qgp-volumetric-light'),
])]

partons = [
    (388.6,104.7,4.8,'cobalt'),(424.6,106.0,3.8,'ash'),(463.6,118.6,3.8,'bronze'),
    (430.0,127.0,5.5,'emerald'),(473.1,142.5,4.9,'emerald'),(441.6,156.9,5.2,'violet'),
    (489.3,177.1,5.1,'azure'),(428.5,185.1,4.6,'red'),(465.6,186.2,4.6,'gold'),
    (339.1,192.5,4.2,'red'),(381,209,3.8,'emerald'),(367.2,227.2,4.0,'azure'),
    (413.4,228.4,5.4,'azure'),(489.9,215.6,5.2,'emerald'),(437,254.2,5.6,'red'),
    (411.3,267.7,4.5,'ash'),
]
layers += [layer('plasma-partons','07 Partons in the medium',[
    ellipse(x,y,r,r,url('parton-'+c),id=f'parton-{i:02}')
    for i,(x,y,r,c) in enumerate(partons,1)
])]

layers += [layer('escaping-jet','08 Escaping jet · high transverse momentum',[
    path('M265.1 6.3 L297.2 26.2 L286.3 29.0 '
         'C319.1 69.1 351.1 112.0 379.9 154.4 '
         'C345.5 121.0 310.3 75.5 280.6 36.5 L275.6 41.6 Z',
         url('escaping-tone'),id='escaping-arrow'),
    path('M279 27 C306 60 342 110 378 153 C349 119 311 72 280 31 Z',
         '#b1f0f2',opacity=.15,id='escaping-jet-highlight'),
])]

layers += [layer('quenched-jet','09 Quenched jet · low transverse momentum',[
    path('M380 155 C418 194 492 293 539.2 354.2 '
         'L543.1 352 L565.9 387.2 L533.6 359.4 L535.9 358.2 '
         'C487.8 300.9 415.4 211.9 380 155 Z',
         url('quenched-tone'),id='quenched-arrow'),
    path('M387 163 C430 215 478 280 532 349 L538 353 '
         'C490 293 441 222 387 163 Z','#e2e0d3',opacity=.28,id='quenched-arrow-highlight'),
])]

layers += [layer('gluon-arcs','10 Gluon radiation · long emission arcs',[
    path('M496 199 C518 207 537 230 542 254 C548 283 536 305 519 312 '
         'C537 295 543 278 538 256 C533 234 517 216 496 199 Z',
         url('radiation-cream'),id='arc-inner'),
    path('M510 187.8 C536 196 566 217 580 250 C593 281 590 315 570 339 '
         'C586 309 587 281 576 252 C563 223 534 205 509.5 191 Z',
         url('radiation-cream'),id='arc-middle'),
    path('M534 186.7 C567 191 603 215 618 248 C632 276 631 297 623 313 '
         'C628 290 622 274 613 251 C598 222 564 199 533.6 189.3 Z',
         url('radiation-cream'),id='arc-outer'),
])]

# Hand-composed wavy splines represent gluon radiation along the long jet.
radiation = [
    ('M397 187 C411 183 407 193 416 197 S416 211 422 209 S427 195 433 199 S443 211 435 214 '
     'S433 220 443 220 S454 220 457 217 S461 221 467 216',1.65,.96),
    ('M414 202 C420 198 423 205 425 211 S430 219 433 224 S440 224 444 230 '
     'S449 232 453 231 S457 236 457 240',1.25,.94),
    ('M435 221 C431 225 439 225 441 231 S445 242 451 241 S455 241 457 247 '
     'S465 249 468 249 S471 254 475 254 S481 250 488 252',1.45,.86),
    ('M461 244 C463 251 462 257 470 257 S476 261 477 266 S483 270 487 268 '
     'S490 270 495 268 S500 266 503 267',1.35,.86),
    ('M476 265 C480 268 480 279 484 282 S491 280 497 283 S504 287 506 283 '
     'S514 281 517 280 S521 282 526 278',1.25,.93),
    ('M495 286 C500 289 499 299 505 299 S511 298 518 301 S524 307 532 306 '
     'S536 303 541 304',1.5,.90),
    ('M507 303 C514 308 516 315 521 314 S531 319 536 316 S541 313 545 315 '
     'S549 316 552 312',1.35,.93),
    ('M516 313 C523 318 520 326 527 325 S535 328 540 325 S543 328 547 325',1.28,.93),
    ('M527 325 C531 332 534 330 539 332 S546 334 552 331',1.1,.93),
]
layers += [layer('gluon-waves','11 Gluon radiation · wavy emissions',[
    path(d_,stroke=url('radiation-orange'),stroke_width=w,opacity=o,
         stroke_linecap='round',id=f'wavy-gluon-{i}')
    for i,(d_,w,o) in enumerate(radiation,1)
])]

origin = (379.3,155.8)
rng = Random(810)
ray_bits = [ellipse(*origin,32,31,url('scatter-glow'),id='vertex-halo')]
for i, (angle, length, width) in enumerate([
        (4,26,1.6),(26,31,1.9),(47,24,1.2),(70,31,1.4),(95,29,1.75),
        (117,27,1.6),(142,35,1.7),(162,30,1.7),(187,25,1.5),
        (216,29,1.4),(237,25,1.4),(266,29,1.35),(292,25,1.6),
        (313,32,1.5),(335,28,1.55)],1):
    a0=angle*pi/180
    u,v=cos(a0),sin(a0)
    x,y=origin
    ray_bits.append(polygon([(x-2*u-width*v,y-2*v+width*u),
                             (x+length*u,y+length*v),
                             (x-2*u+width*v,y-2*v-width*u)],
                            '#fff7cb' if i%4==0 else '#fff9d4',
                            id=f'vertex-ray-{i:02}',opacity=.78+rng.random()*.22))
ray_bits += [ellipse(*origin,6.4,6.4,url('scatter-glow'),id='vertex-hot-core')]
layers += [layer('hard-scatter','12 Hard scattering · common vertex',ray_bits)]

layers += [layer('coordinate-axes','13 Coordinate axes · right-handed x, y, z',[
    pointer((48,384.2),(48,330.2),width=1.38,head=9.2,half=3.25,id_='axis-y'),
    pointer((48,384.2),(111.2,366.2),width=1.42,head=9.4,half=3.05,id_='axis-z'),
    pointer((48,384.2),(85.7,425.2),width=1.38,head=9.2,half=3.10,id_='axis-x'),
    ntext(44.4,324.8,'y',13.1,font_weight='bold',text_anchor='start',id='axis-y-label',data_plain='y'),
    ntext(118,369.0,'z',13.1,font_weight='bold',text_anchor='start',id='axis-z-label',data_plain='z'),
    ntext(90.5,435,'x',13.1,font_weight='bold',text_anchor='start',id='axis-x-label',data_plain='x'),
])]

lead = '#31302e'
layers += [layer('annotations','14 Callouts and editable scientific labels',[
    line((245.5,46.7),(287.7,64.6),lead,1.12),
    line((580.7,63.8),(517.1,108.1),lead,1.20),
    line((331.3,236.6),(368.9,188.3),lead,1.19),
    line((418.2,408.6),(398.6,359.0),lead,1.02),
    line((649,294.3),(608.2,274.2),lead,1.12),
    path('M569.7 375.4 C580 372.4 588.9 367.1 599.0 358.5',stroke=lead,stroke_width=.78),
    ntext(193,30.3,'escaping jet',12.5,id='escaping-label'),
    ntext(193,47.4,'(high '+tag('tspan','p',font_style='italic')+
          tag('tspan','T',font_size=8.4,dy=2.3)+tag('tspan',')',dy=-2.3),
          12,id='high-pt-label'),
    ntext(550,59.4,'QGP medium',12.4,id='medium-label'),
    ntext(313.4,251.6,'hard scattering',12.7,id='vertex-label'),
    ntext(91.9,280.9,'Pb',12.4,id='left-nucleus-label'),
    ntext(721.4,117.6,'Pb',12.4,id='right-nucleus-label'),
    ntext(390,425.7,'reaction plane',12.1,id='plane-label'),
    ntext(652.3,303.0,'gluon radiation',12.2,id='radiation-label'),
    ntext(602.6,373.0,'quenched jet',12.35,id='quenched-label'),
    ntext(602.6,389.3,'(low '+tag('tspan','p',font_style='italic')+
          tag('tspan','T',font_size=8.4,dy=2.3)+tag('tspan',')',dy=-2.3),
          12,id='low-pt-label'),
])]


def draw():
    dest = OUT / 'jet_plane_edit.svg'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'width="{OUTPUT[0]}" height="{OUTPUT[1]}" viewBox="0 0 {W} {H}">\n'
           '<title>Jet quenching in the reaction plane</title>\n'
           '<desc>Editable schematic. z is the beam direction; x is the impact '
           'parameter direction; y is normal to the x–z reaction plane.</desc>\n'
           '<defs>\n' + '\n'.join(defs) + '\n</defs>\n' +
           '\n'.join(layers) + '\n</svg>\n')
    dest.write_text(svg, encoding='utf-8')
    cairosvg.svg2png(bytestring=svg.encode('utf-8'), write_to=str(OUT/'jet_plane_edit.png'),
                     output_width=OUTPUT[0], output_height=OUTPUT[1], background_color='#fff')


if __name__ == '__main__':
    draw()
