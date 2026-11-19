"""Direct, editable SVG redraw of the supplied turbulent QGP jet illustration."""
from html import escape
from io import BytesIO
from math import atan2, cos, degrees, sin
from pathlib import Path
from random import Random

import cairosvg
from PIL import Image

OUT = Path(__file__).resolve().parent
W, H = 374, 204
R = Random(27605)


def f(n):
    return f"{n:.3f}".rstrip("0").rstrip(".") if isinstance(n, float) else str(n)


def el(name, inner=None, **a):
    attrs = " ".join(f'{k.replace("_","-")}="{escape(f(v), quote=True)}"' for k, v in a.items())
    return f"<{name} {attrs}/>" if inner is None else f"<{name} {attrs}>{inner}</{name}>"


def layer(key, title, parts, **kw):
    return f'<g id="{key}" inkscape:groupmode="layer" inkscape:label="{title}" data-element="{key}"' + (
        " " + " ".join(f'{k.replace("_","-")}="{escape(f(v), quote=True)}"' for k, v in kw.items()) if kw else ""
    ) + ">\n" + "\n".join(parts) + "\n</g>"


def path(d, fill="none", **kw):
    return el("path", d=d, fill=fill, **kw)


def stroke(d, color, width, **kw):
    return path(d, stroke=color, stroke_width=width, stroke_linecap="round", stroke_linejoin="round", **kw)


def ell(x, y, rx, ry, fill, a=0, **kw):
    if a:
        kw["transform"] = f"rotate({f(a)} {f(x)} {f(y)})"
    return el("ellipse", cx=x, cy=y, rx=rx, ry=ry, fill=fill, **kw)


def dot(x, y, r, fill, **kw):
    return el("circle", cx=x, cy=y, r=r, fill=fill, **kw)


def url(key):
    return f"url(#{key})"


def use(id, **kw):
    return '<use href="#'+id+'" xlink:href="#'+id+'" ' + " ".join(
        f'{k.replace("_","-")}="{escape(f(v),quote=True)}"' for k,v in kw.items()) + '/>'


def gradient(kind, key, stops, **kw):
    return el(kind + "Gradient", "".join(el("stop", offset=o, stop_color=c, stop_opacity=a)
                                           for o, c, a in stops), id=key, **kw)


def soft(key, center, mid, edge, alpha=1):
    return gradient("radial", key, [(0,center,alpha),(.32,mid,alpha*.72),(.63,mid,alpha*.27),(1,edge,0)])


outline = ("M 85.6,130.8 C 84,119 89,108 94.9,100.6 "
           "C 92,87 101,74 113,66 C 122,46 145,35 160,30 "
           "C 176,13 198,4.6 220.4,5 C 247,3.2 265,16 270.1,34 "
           "C 275,46 273,52 280.6,66 C 287.7,79 287.3,94 282.7,105.3 "
           "C 289.3,120 280.9,137 271.4,151.4 C 263.4,165 250,173 237.4,176.9 "
           "C 224.7,192 206,200.2 181.2,200.4 C 157.1,202.3 139.5,196.8 124.6,188.6 "
           "C 105.7,184.2 94.3,166 89,151.2 C 86.5,144.7 84.1,136.5 85.6,130.8 Z")

defs = [
    gradient("radial","plasma-body", [
        (0,"#ffae12",1),(.30,"#ff7701",1),(.58,"#e63a00",1),(.83,"#b42100",1),
        (.951,"#cc390c",1),(1,"#ef663c",.94)
    ], cx=".53",cy=".47",r=".55",fx=".55",fy=".40"),
    gradient("linear","plasma-rim", [
        (0,"#ff8657",.78),(.30,"#ffa687",.51),(.48,"#f35b19",.1),
        (.74,"#f74e09",.3),(1,"#ff7029",.73)
    ], x1="0%", y1="0%", x2="74%", y2="100%"),
    gradient("radial","plasma-depth",[(0,"#8f1600",0),(.62,"#8f1600",0),
                                      (.87,"#8d1203",.19),(1,"#8e1c0f",.40)],
             cx=".45",cy=".43",r=".60"),
    soft("heat", "#ffed92", "#ff9707", "#ed3a00"),
    soft("gold", "#fff58d", "#ffba13", "#fb6a00"),
    soft("ember", "#ff9807", "#ee4a00", "#a41a00"),
    soft("shadow", "#9b1a01", "#9d1b03", "#971900"),
    soft("dark-pocket", "#8e1601", "#aa2304", "#a21e03"),
    soft("rim-glow", "#ff6f09", "#f84803", "#ed3a00"),
    soft("jet-puff", "#a0efff", "#1599ff", "#1745e4"),
    soft("impact-halo", "#fff9c2", "#ffeb42", "#ff9817"),
    soft("impact-core", "#ffffff", "#fff9ae", "#ffe633"),
    soft("photon", "#fffbd2", "#ffe83c", "#ff9e00"),
    gradient("linear","quenched-aura", [
        (0,"#3640ed",0),(.22,"#314fff",.42),(.62,"#298cf7",.40),(1,"#99f3ff",.90)
    ], gradientUnits="userSpaceOnUse", x1=44,y1=156,x2=241,y2=95),
    gradient("linear","quenched-core", [
        (0,"#3879f6",0),(.17,"#5d8dff",.5),(.31,"#566aff",.91),
        (.66,"#7dbaff",.86),(1,"#d6fbff",1)
    ], gradientUnits="userSpaceOnUse", x1=46,y1=154,x2=241,y2=96),
    gradient("linear","jet-aura", [
        (0,"#a1f9ff",.07),(.14,"#42e9ff",.23),(.53,"#278feb",.22),
        (.74,"#2d86eb",.12),(.92,"#3969e3",0),(1,"#3969e3",0)
    ], gradientUnits="userSpaceOnUse", x1=240,y1=95,x2=366,y2=55),
    gradient("linear","jet-plume", [
        (0,"#c5fdff",.79),(.23,"#70eaff",.83),(.58,"#29c2f1",.67),
        (.78,"#278ffe",.29),(.94,"#246af1",0),(1,"#246af1",0)
    ], gradientUnits="userSpaceOnUse", x1=240,y1=95,x2=362,y2=55),
    gradient("linear","jet-core", [
        (0,"#fbffff",1),(.28,"#c0ffff",.95),(.56,"#61e9ff",.84),(.88,"#43acff",0),(1,"#43acff",0)
    ], gradientUnits="userSpaceOnUse", x1=240,y1=96,x2=352,y2=59),
    gradient("linear","jet-fan", [
        (0,"#b7faff",.72),(.35,"#4cd2ff",.75),(.73,"#269af5",.51),(1,"#2072f7",0)
    ], gradientUnits="userSpaceOnUse", x1=254,y1=91,x2=367,y2=49),
    el("clipPath",use("qgp-outline"),id="qgp-clip",
       clipPathUnits="userSpaceOnUse"),
]


def curve(points):
    """Catmull-Rom centerline encoded as editable cubic Beziers."""
    coords = lambda p: f"{f(p[0])},{f(p[1])}"
    q = [points[0]] + points + [points[-1]]
    d = "M " + coords(q[0])
    for a,b,c,e in (q[i:i+4] for i in range(len(points)-1)):
        c1 = tuple(b[j]+(c[j]-a[j])/6 for j in range(2))
        c2 = tuple(c[j]-(e[j]-b[j])/6 for j in range(2))
        d += " C " + " ".join(map(coords,(c1,c2,c)))
    return d


# Volumes and emissive channels are drawn from geometric controls, with no sampled source pixels.
light_regions = [
    (222,31,44,24,-12,"rim-glow",.68),(245,59,34,31,28,"heat",.57),
    (189,84,48,29,7,"rim-glow",.84),(208,106,55,35,24,"heat",.45),
    (240,133,37,24,-34,"ember",.68),(151,151,29,33,-37,"rim-glow",.64),
    (183,172,43,25,-4,"ember",.72),(123,109,32,24,-18,"ember",.72),
    (221,160,36,27,-24,"rim-glow",.58),(158,58,33,22,-19,"ember",.7),
    (133,82,35,21,-41,"rim-glow",.48),
]
volume = [ell(x,y,a,b,url(g),t,opacity=o) for x,y,a,b,t,g,o in light_regions]

shadows = [
    (124,102,26,14,-24), (144,77,28,12,-35),(170,42,26,14,-30),
    (193,32,34,12,-20),(247,79,31,13,22),(236,104,33,15,15),
    (207,129,34,13,-14),(237,151,31,16,-30),(168,137,26,12,-18),
    (165,167,42,13,-3),(181,182,40,16,-4),(114,139,31,14,-26),
    (267,117,23,22,25),(234,49,13,15,-9),(172,59,17,11,18),
    (176,95,21,12,-18),(209,99,21,11,53),(111,119,12,15,45),
    (122,169,13,11,27),(163,179,21,11,11),(215,165,14,15,-25),
]
shade = [ell(x,y,a,b,url("dark-pocket"),t,opacity=.59) for x,y,a,b,t in shadows]

# Uneven strands are deliberately staggered so no rigid repeating cell pattern survives.
channels = [
    ([(112,95),(134,82),(151,83),(162,72),(177,70),(182,59)],.79),
    ([(130,73),(138,65),(151,63),(163,53),(174,51)],.67),
    ([(151,54),(166,47),(182,44),(196,34),(207,23)],.5),
    ([(171,65),(181,58),(197,61),(205,56),(208,45),(221,43)],.73),
    ([(195,19),(209,15),(222,20),(240,22),(252,34)],.58),
    ([(221,47),(229,39),(243,41),(253,48),(258,61)],.70),
    ([(236,25),(245,29),(253,37),(255,48),(269,62)],.62),
    ([(108,122),(124,109),(138,106),(151,111),(170,105),(182,91)],.76),
    ([(123,94),(134,97),(150,96),(161,92),(170,81),(185,82),(200,88)],.80),
    ([(152,78),(163,82),(173,77),(185,69),(197,71),(208,80),(226,78)],.58),
    ([(189,88),(205,91),(215,87),(225,91),(229,104),(242,109),(253,118)],.84),
    ([(209,53),(218,57),(226,64),(232,76),(245,77),(264,88)],.67),
    ([(248,57),(247,69),(254,80),(269,81),(276,93),(272,105)],.6),
    ([(99,145),(113,150),(128,145),(144,131),(154,122),(167,120)],.59),
    ([(113,159),(127,157),(136,151),(153,150),(163,140),(171,131),(181,126)],.86),
    ([(119,174),(132,184),(149,183),(163,185),(178,177),(193,172)],.62),
    ([(142,161),(153,159),(166,167),(183,165),(196,160),(203,147),(214,140)],.75),
    ([(170,124),(187,119),(199,124),(210,116),(219,116),(231,122),(248,125)],.81),
    ([(178,141),(192,140),(205,132),(221,134),(234,144),(250,140),(267,134)],.73),
    ([(180,188),(197,181),(206,175),(222,174),(234,163),(239,152)],.71),
    ([(209,165),(222,155),(232,155),(245,148),(255,139),(259,123),(272,118)],.78),
]

swirls, sparks = [], []
for i, (points, strength) in enumerate(channels):
    d = curve(points)
    aura = "#ff6a04" if i % 4 else "#ff9812"
    parts = [stroke(d, aura, 10+R.random()*4, opacity=.10*strength),
             stroke(d,"#ff9400",4.6,opacity=.13*strength),
             stroke(d,"#ffab03",2.1,opacity=.14*strength)]
    for (x,y),(u,v) in zip(points,points[1:]):
        angle = degrees(atan2(v-y,u-x))
        for _ in range(R.randrange(3,6)):
            t = R.uniform(.06, .96)
            px, py = x+(u-x)*t+R.gauss(0,1.7), y+(v-y)*t+R.gauss(0,1.7)
            parts.append(ell(px,py,R.uniform(4.5,11.5),R.uniform(1.8,4.9),
                             url("heat" if R.random()>.34 else "gold"),angle+R.uniform(-32,32),
                             opacity=strength*R.uniform(.27,.82)))
            if R.random()<.38:
                sparks.append(ell(px,py,R.uniform(.42,2.05),R.uniform(.29,1.17),url("gold"),
                                  angle,opacity=strength*R.uniform(.21,.78)))
    swirls.append(el("g","".join(parts),id=f"plasma-filament-{i+1:02d}"))

freckles = []
for i in range(264):
    x, y = R.uniform(91,285), R.uniform(7,201)
    a,b = R.uniform(2.2,12.0), R.uniform(1.5,6.5)
    caustic = .5 + .5*sin(.11*x+.32*sin(.06*y))*sin(.105*y-.6*sin(.09*x))
    freckles.append(ell(x,y,a,b,url(R.choice(("ember","shadow","heat","gold"))),
                        R.uniform(-80,80),opacity=R.uniform(.06,.44)*(caustic*.7+.3)))

qgp = layer("qgp-medium","QGP | full volume and turbulent light",[
    *[el("g",use("qgp-outline",fill="none",stroke="#f45122",stroke_width=width),opacity=alpha)
      for width,alpha in [(7.2,.022),(5.7,.039),(4.3,.056),(3.1,.089),(2.15,.16)]],
    el("g",el("path",d=outline,id="qgp-outline"),fill=url("plasma-body"),id="plasma-silhouette"),
    layer("qgp-texture","Plasma texture | clipped to silhouette",[
        layer("plasma-volumes","Broad orange volumes",volume+shade),
        layer("small-eddies","Warm and dark eddies",freckles),
        layer("hot-filaments","Turbulent emissive filaments",swirls),
        layer("plasma-sparks","Small hot highlights",sparks),
        use("qgp-outline",fill=url("plasma-depth")),
    ],clip_path=url("qgp-clip")),
    el("g",use("qgp-outline",fill="none",stroke=url("plasma-rim"),stroke_width=1.33),opacity=.73),
])

quenched = layer("quenched-jet","Quenched jet | complete long path",[
    path("M 241,95.5 C 204,108 159,119 112,134 C 87,143 67,150 43,157 "
         "C 64,147 86,138 110,130 C 156,117 201,101 241,95.5 Z",url("quenched-aura"),id="quenched-envelope",opacity=.69),
    stroke("M 46,154 C 88,140.2 127,127.4 166,116.3 S 217,102.2 241,95.5",
           url("quenched-aura"),4.6,opacity=.26),
    stroke("M 49,153.3 Q 111,131.8 168,115.8 T 241,95.5",url("quenched-core"),1.91),
    stroke("M 76,144.4 Q 144,122.5 198,107.5 T 241,95.5",url("quenched-core"),.68,opacity=.73),
    *[ell(x,y,R.uniform(.3,1.55),R.uniform(.22,.65),url("jet-puff"),-18,opacity=R.uniform(.16,.45))
      for x,y in [(R.uniform(46,105),0) for _ in range(21)]
      for y in [153.8-.34*(x-48)+R.gauss(0,2.75)]],
])

radiation = []
for i,(pts,alpha) in enumerate([
    ([(154,120),(145,125),(137,129),(131,134),(124,139),(119,145),(110,151)],1),
    ([(177,115),(168,121),(163,126),(155,129),(150,135),(142,140),(137,149)],.86),
    ([(148,126),(139,128),(131,129),(125,133),(119,134)],.62),
    ([(159,131),(157,135),(154,138),(149,140)],.58),
]):
    d=curve(pts)
    bits=[stroke(d,"#ff9d00",4.9,opacity=.28*alpha),
          stroke(d,"#ffb900",2.55,opacity=.65*alpha),
          stroke(d,"#ffef46",.96,opacity=.86*alpha,stroke_dasharray="2 1")]
    for x,y in pts[1:]:
        bits.append(ell(x,y,R.uniform(2.8,4.9),R.uniform(1.55,2.9),url("photon"),
                        -36,opacity=alpha*R.uniform(.53,.94)))
        bits.append(dot(x+R.gauss(0,.7),y+R.gauss(0,.8),R.uniform(.16,.57),"#fff9bd",opacity=.58*alpha))
    radiation.append(el("g","".join(bits),id=f"emission-branch-{i+1}"))

elongated = []
for i in range(106):
    t=R.betavariate(3.6,1.9)
    x=260+102*t
    y=90-(x-258)*.34+R.gauss(0,1.25+4*t)
    elongated.append(ell(x,y,R.uniform(.75,3.6),R.uniform(.24,1.34),url("jet-puff"),
                          R.uniform(-53,-11),opacity=R.uniform(.27,.91)*(1-t*.41)))
    if i%3==0:
        elongated.append(dot(x+R.gauss(0,2),y+R.gauss(0,2),R.uniform(.24,.68),
                             R.choice(("#2369c6","#4ea7e8","#64d8ff")),opacity=R.uniform(.18,.53)))

fan = []
for i in range(16):
    x=R.uniform(316,366)
    y=94-(x-240)*.32+R.gauss(0,5.5)
    fan.append(stroke(f"M 244,94.8 Q {f(x-25)},{f(y+12+R.gauss(0,2))} {f(x)},{f(y)}",
                      url("jet-fan"),R.uniform(.28,1.2),opacity=R.uniform(.21,.75)))

escaping = layer("escaping-jet","Escaping jet | complete short path",[
    path("M 238,96 C 272,80 313,58 363,39 C 379,43 367,64 357,69 "
         "C 316,82 280,87 238,96 Z",url("jet-aura"),id="blue-jet-halo"),
    ell(326,67,38,8.2,url("jet-puff"),-19,opacity=.3),
    path("M 240,95.5 C 273,83 301,64 359,47 C 366,44 367,57 362,59 "
         "C 319,76 285,87 240,95.5 Z",url("jet-plume"),id="blue-jet-plume"),
    *fan,*elongated,
    path("M 240,95.5 Q 295,74.5 348,58 Q 310,77 240,95.5 Z",url("jet-core"),id="blue-jet-core"),
    stroke("M 240,95.5 Q 290,76.3 345,60.3",url("jet-core"),.76,opacity=.87),
])

impact = layer("hard-scattering","Hard scattering | light and impact point",[
    ell(240.5,95.5,18.1,17.3,url("impact-halo"),opacity=.90),
    ell(240.5,95.5,8.5,8.7,url("impact-core"),opacity=.98),
    *[stroke(f"M 240.5,95.5 L {f(240.5+length*cos(a))},{f(95.5+length*sin(a))}",
             "#fff4ac",.62 if i%2 else .9,opacity=.73 if i%2 else .9)
      for i,(a,length) in enumerate(zip([.41,1.0,1.59,2.38,3.48,4.35,4.87,5.53],[6.5,5,8.5,5.6,7,7.6,5.5,8]))],
    dot(240.5,95.5,1.94,"#fffbe6"),
])


def label(key, text, x, y, w, leader=None, ptsize=7.35):
    h = 10.6
    bits = []
    if leader:
        (sx,sy),(ex,ey)=leader
        dx,dy=ex-sx,ey-sy
        length=(dx*dx+dy*dy)**.5
        dx,dy=dx/length,dy/length
        d=f"M {f(sx)},{f(sy)} L {f(ex)},{f(ey)}"
        bits += [stroke(d,"#ffffff",1.66,opacity=.92),stroke(d,"#4a4a4a",.65)]
        tip= [(ex,ey),(ex-2.98*dx+1.20*dy,ey-2.98*dy-1.20*dx),
              (ex-2.98*dx-1.20*dy,ey-2.98*dy+1.20*dx)]
        bits.append(el("polygon", points=" ".join(f"{f(i)},{f(j)}" for i,j in tip),fill="#454545",
                       stroke="#fff",stroke_width=.37))
    bits += [el("rect",x=x-w/2,y=y-h/2+.64,width=w,height=h,rx=4.55,fill="#28100b",opacity=.24),
             el("rect",x=x-w/2,y=y-h/2,width=w,height=h,rx=4.55,fill="#fffefd",stroke="#777",
                stroke_width=.76),
             el("text",escape(text),x=x,y=y+2.5,fill="#272421",font_family="Arial, sans-serif",
                font_size=ptsize,font_weight="700",text_anchor="middle")]
    return el("g","".join(bits),id=key)


labels = layer("labels","Labels and leaders",[
    label("label-qgp","QGP",197.2,36.7,27.1),
    label("label-hard","Hard scattering",216.1,63.8,66.8,((232,68),(241,92))),
    label("label-escaping","Escaping jet",294.6,50.6,55.4,((285,55.5),(273,80.5))),
    label("label-quenched","Quenched jet",88,112.7,58.5,((104,117),(114,129.4))),
    label("label-radiation","Medium-induced radiation",189.8,162.8,106.0,((162,158),(151.9,141.1))),
])


def main():
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'width="1168" height="640" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">\n'
           '<title id="title">Jet quenching in a turbulent quark–gluon plasma</title>\n'
           '<desc id="desc">Illustrative direct SVG redraw from the supplied image. '
           'The hard scattering sends opposite jets through unequal paths. The long-path jet is '
           'quenched and shows medium-induced radiation. The seeded vector texture is decorative.</desc>\n'
           '<defs>\n' + "\n".join(defs) + '\n</defs>\n' +
           layer("background","Paper",[el("rect",x=0,y=0,width=W,height=H,fill="#fff")]) + "\n" +
           "\n".join([qgp,quenched,layer("radiation","Medium-induced radiation",radiation),
                      escaping,impact,labels]) + "\n</svg>\n")
    (OUT/"jet_fireball_edit.svg").write_text(svg,encoding="utf-8")
    rendered = Image.open(BytesIO(cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                           output_width=2336,output_height=1280,background_color="white"))).convert("RGB")
    rendered.save(OUT/"jet_fireball_edit.png", dpi=(300,300))


if __name__=="__main__":
    main()
