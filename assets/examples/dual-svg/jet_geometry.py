"""Redraw the supplied QGP/jet schematic as editable SVG geometry."""
from html import escape
from io import BytesIO
from math import cos, pi, radians, sin, sqrt
from pathlib import Path
from random import Random

import cairosvg
from PIL import Image

OUT=Path(__file__).resolve().parent
W,H=1522,848
CX,CY,RX,RY=769.5,393.0,186,335.4
VX,VY=865.8,361.2
rng=Random(6672)


def num(value):
    return f"{value:.3f}".rstrip("0").rstrip(".") if isinstance(value,float) else str(value)


def el(tag,body=None,**a):
    at="".join(f' {key.replace("_","-")}="{escape(num(value),quote=True)}"' for key,value in a.items())
    return f"<{tag}{at}/>" if body is None else f"<{tag}{at}>{body}</{tag}>"


def layer(key,title,parts,**a):
    s=el("g","\n"+"\n".join(parts)+"\n",id=key,data_element=key,**a)
    return s.replace("<g ",f'<g inkscape:groupmode="layer" inkscape:label="{escape(title,quote=True)}" ',1)


def xy(p):
    return ",".join(map(num,p))


def path(d,fill="none",**a):
    return el("path",d=d,fill=fill,**a)


def stroke(d,color,width,**a):
    return path(d,stroke=color,stroke_width=width,stroke_linecap="round",stroke_linejoin="round",**a)


def ell(x,y,rx,ry,fill,angle=0,**a):
    if angle:
        a["transform"]=f"rotate({num(angle)} {num(x)} {num(y)})"
    return el("ellipse",cx=x,cy=y,rx=rx,ry=ry,fill=fill,**a)


def dot(x,y,r,fill,**a):
    return el("circle",cx=x,cy=y,r=r,fill=fill,**a)


def url(id):
    return f"url(#{id})"


def copy(id,**a):
    return el("use",href=f"#{id}",**a).replace("<use ",f'<use xlink:href="#{id}" ',1)


def grad(kind,id,stops,**a):
    return el(kind+"Gradient","".join(el("stop",offset=n,stop_color=c,stop_opacity=o) for n,c,o in stops),id=id,**a)


def linear(id,a,b,stops):
    return grad("linear",id,stops,x1=a[0],y1=a[1],x2=b[0],y2=b[1],gradientUnits="userSpaceOnUse")


def glow(id,c,m,opacity=1):
    return grad("radial",id,[(0,c,opacity),(.25,c,opacity*.84),(.58,m,opacity*.36),(1,m,0)])


def sphere(id,colors):
    return grad("radial",id,list(zip((0,.33,.65,.89,1),colors,(1,1,1,1,1))),cx=.48,cy=.47,
                fx=.29,fy=.27,r=.64)


def text(x,y,s,sz=28,anchor="start",**a):
    return el("text",escape(s),x=x,y=y,font_family="Arial, Liberation Sans, sans-serif",font_size=sz,
              font_weight=500,text_anchor=anchor,fill="#262626",**a)


# The cone mouths and the common vertex are mapped from the reference.
m=(VX,VY)
right_path=("M "+xy(m)+" C 926,300 1059,174 1161,76 "
            "Q 1167,70 1174,78 C 1198,100 1226,156 1239,193 "
            "Q 1242,199 1234,202 C 1103,250 959,306 "+xy(m)+" Z")
left_path=("M "+xy(m)+" C 691,411 510,502 268,565 "
           "Q 263,566 266,572 C 285,615 303,658 318,695 "
           "Q 320,702 327,697 C 532,540 670,445 "+xy(m)+" Z")
right_cap=("M 1161,76 Q 1167,70 1174,78 C 1198,100 1226,156 1239,193 "
           "Q 1242,199 1234,202 C 1202,206 1175,188 1158,159 C 1144,132 1151,99 1161,76 Z")
left_cap=("M 268,565 C 293,568 323,605 336,636 C 348,662 337,692 327,697 "
          "Q 320,702 318,695 C 303,658 285,615 266,572 Q 263,566 268,565 Z")


defs=[
    linear("qgp-longitudinal",(0,57),(0,727),
           [(0,"#841602",1),(.115,"#c02202",1),(.27,"#f24c05",1),(.46,"#f36c0e",1),
            (.62,"#df4b01",1),(.72,"#df4f03",1),(.81,"#c63200",1),
            (.94,"#751200",1),(1,"#691200",1)]),
    grad("radial","qgp-depth",[(0,"#741302",0),(.52,"#7a1904",0),(.76,"#8a1804",.22),
                             (.91,"#751202",.44),(1,"#671702",.69)],
         cx=.44,cy=.43,r=.644,fx=.35,fy=.38),
    glow("qgp-bright","#ffd36f","#ff8f22",.94),
    glow("qgp-bounce","#f8862f","#e75009",.69),
    glow("qgp-faint","#ffd36d","#ff8b24",.63),
    # Hand-tuned from broad color patches on the reference, rather than pixels as shapes.
    linear("qgp-side-shade",(583,0),(956,0),[
        (0,"#ab240e",.51),(.105,"#c51c10",.40),(.21,"#b52d12",.13),(.29,"#aa260b",0),
        (.70,"#783007",0),(.80,"#852606",.11),(.91,"#7d2006",.49),
        (.977,"#762005",.57),(1,"#932c0a",.47)]),
    glow("star-warm","#fff7aa","#ffad00"),glow("star-hot","#ffffff","#ffe878"),
    glow("gluon-glow","#f6ff4b","#b9ee1a"),
    sphere("gluon-bead",["#ffffb7","#f6ff48","#e9fa20","#b8c800","#849604"]),
    sphere("silver-blue",["#f4faff","#d2e1f0","#a5b9d2","#7789a4","#526582"]),
    sphere("silver-gray",["#b0bac5","#8c97a6","#75818e","#606b79","#4a5361"]),
    linear("qgp-rim",(659,59),(874,730),[(0,"#ff642e",.97),(.25,"#ff844c",.72),
                                        (.48,"#ff9a49",.36),(.82,"#ff6433",.86),(1,"#ff7531",1)]),
    linear("silk",(595,0),(940,0),[(0,"#ffd099",0),(.26,"#ffda7c",.22),(.53,"#ffe4a2",.45),
                                   (.86,"#ffac44",.11),(1,"#ffad2d",0)]),
    linear("right-long",(VX,VY),(1198,135),[(0,"#567ab2",.97),(.17,"#34578f",1),
              (.51,"#284a83",1),(1,"#202d59",1)]),
    linear("right-shadow",(1145,88),(1206,215),[(0,"#151433",.61),(.33,"#0d214d",.20),
              (.51,"#4f9cff",.08),(.68,"#17315e",.44),(1,"#0c1434",.74)]),
    linear("right-glint",(932,318),(1190,140),[(0,"#5a86c4",.47),(.25,"#3f6db6",.44),
              (.64,"#3d60ab",.38),(1,"#3c5f9e",.1)]),
    linear("right-mouth",(1149,97),(1238,190),[(0,"#142647",.80),(.54,"#263951",.54),(1,"#1c2942",.88)]),
    linear("left-long",(VX,VY),(290,632),[(0,"#555750",.75),(.13,"#464c57",.79),(.45,"#435675",.87),
              (.62,"#576987",.93),(.79,"#8e95a1",.94),(.92,"#c0c0c4",.94),(1,"#c4c5c9",.97)]),
    linear("left-shadow",(244,527),(346,731),[(0,"#343c48",.35),(.32,"#91a3bd",.09),(.51,"#e1e8eb",.29),
              (.79,"#657078",.18),(1,"#55595e",.39)]),
    linear("left-glint",(VX,VY),(298,634),[(0,"#f3b65c",.12),(.17,"#b5c1c8",.30),(.45,"#6794c3",.26),
              (.73,"#c3cad6",.28),(1,"#e1e1e5",.2)]),
    linear("left-warm-depth",(VX,VY),(554,503),[(0,"#4f3619",.29),(.41,"#493511",.38),
              (.61,"#4b392e",.22),(.86,"#453f37",0),(1,"#453f37",0)]),
    linear("left-mouth",(264,561),(339,700),[(0,"#9ca3aa",.23),(.5,"#d5d7d8",.31),(1,"#a6afb5",.24)]),
    el("clipPath",copy("qgp-outline"),id="qgp-clip",clipPathUnits="userSpaceOnUse"),
    el("clipPath",path(right_path),id="right-clip"),
    el("clipPath",path(left_path),id="left-clip"),
]

# Reconstruct visible hemispherical latitude/longitude lines from a 3D ellipsoid.
# Camera pitch puts the top slightly toward the viewer. The exact silhouette is RX/RY.
beta=radians(7.2)
b_cos,b_sin=cos(beta),sin(beta)
A=sqrt((RY*RY-RX*RX*b_sin*b_sin)/(b_cos*b_cos))


def project(lat,lon):
    lat,lon=radians(lat),radians(lon)
    c,s=cos(lat),sin(lat)
    z=sin(lon)*c
    x=CX+RX*cos(lon)*c
    y=CY-A*s*b_cos+RX*z*b_sin
    front=s/A*b_sin+z/RX*b_cos
    return (x,y),front


def mesh_arcs(samples):
    segs=[]
    prev=None
    line=[]
    for p,visible in samples:
        if prev is not None and (visible>=0)!=(prev[1]>=0):
            q,k=prev
            m=k/(k-visible)
            end=(q[0]+(p[0]-q[0])*m,q[1]+(p[1]-q[1])*m)
            if visible>=0:
                line=[end]
            else:
                if line:
                    segs.append(line+[end])
                line=[]
        if visible>=0:
            line.append(p)
        prev=(p,visible)
    if line:
        segs.append(line)
    return " ".join("M "+" L ".join(map(xy,seg)) for seg in segs if len(seg)>1)


parallels=[]
for i,lat in enumerate(range(-78,79,7)):
    d=mesh_arcs(project(lat,theta) for theta in range(-180,181,3))
    if d:
        parallels.append(stroke(d,"#61260f" if lat < -27 else "#5b2b1c",.64+min(.2,abs(lat)*.003),
                                opacity=.24 if i%2==0 else .17,id=f"latitude-{i:02d}"))
meridians=[]
for i,lon in enumerate(range(-180,180,20)):
    d=mesh_arcs(project(phi,lon) for phi in range(-90,91,1))
    if d:
        meridians.append(stroke(d,"#682711",.75,opacity=.23,id=f"longitude-{i:02d}"))

silkpaths=[
    "M 588,339 C 642,289 714,269 809,250 C 851,242 892,227 921,200",
    "M 593,313 C 677,260 767,220 879,228 C 900,231 921,240 934,253",
    "M 590,356 C 680,316 781,297 878,260 C 898,252 914,243 929,229",
    "M 631,380 C 651,299 659,240 711,199 C 743,174 792,164 851,166",
    "M 607,296 C 676,273 742,246 812,241 C 869,237 908,246 937,265",
    "M 600,427 C 629,444 672,435 715,420 C 786,395 853,356 932,347",
    "M 621,471 C 677,505 742,533 800,560 C 823,571 853,581 895,585",
    "M 639,531 C 690,579 736,612 813,622 C 837,625 861,622 880,616",
]
silk=[stroke(d,url("silk"),w,opacity=op) for d,w,op in zip(silkpaths,[3.2,2.3,1.5,3.3,1.9,1.4,2,1.8],
                                                      [.79,.67,.53,.67,.49,.65,.3,.27])]
for j in range(21):
    t=rng.uniform(0,1)
    x=rng.uniform(648,850)
    y=259+rng.uniform(-17,73)-.21*(x-750)
    silk.append(ell(x,y,rng.uniform(39,119),rng.uniform(1.3,7.7),url("qgp-faint"),
                    rng.uniform(-19,-3),opacity=.10+t*.11))

medium=layer("qgp-medium","QGP medium | complete ellipsoid and surface",[
    *[el("g",copy("qgp-outline",fill="none",stroke="#fe5422",stroke_width=w),opacity=o)
      for w,o in [(29,.018),(24,.028),(20,.039),(16,.056),(13,.077),(10,.105),(7,.18),(4.2,.35)]],
    el("g",el("ellipse",id="qgp-outline",cx=CX,cy=CY,rx=RX,ry=RY),fill=url("qgp-longitudinal")),
    layer("medium-light","QGP light and surface highlights",[
        ell(731,300,214,215,url("qgp-bright"),-10,opacity=.96),
        ell(817,459,186,196,url("qgp-bounce"),15,opacity=.81),
        ell(757,286,133,67,url("qgp-faint"),-19,opacity=.66),
        copy("qgp-outline",fill=url("qgp-depth")),
        copy("qgp-outline",fill=url("qgp-side-shade")),
        *silk,
    ],clip_path=url("qgp-clip")),
    layer("medium-mesh","Full visible hemisphere mesh",[
        layer("qgp-latitudes","Ellipsoid parallels",parallels),
        layer("qgp-longitudes","Ellipsoid meridians",meridians),
    ],clip_path=url("qgp-clip")),
    el("g",copy("qgp-outline",fill="none",stroke=url("qgp-rim"),stroke_width=2.4),opacity=.83),
])

rightjet=layer("unquenched-jet","Unquenched jet | full short cone",[
    path(right_path,url("right-long"),id="short-cone",stroke="#1f3156",stroke_width=1.65),
    layer("short-jet-light","Short cone glints and ribs",[
        path(right_path,url("right-shadow"),opacity=.94),
        path("M 865.8,361.2 Q 1006,235 1179,99 Q 1192,123 1202,151 Q 1033,256 865.8,361.2 Z",
             url("right-glint"),opacity=.73),
        *[stroke("M "+xy(m)+" Q "+xy(c)+" "+xy(end),"#657da4",.63,opacity=o)
          for c,end,o in [((1015,200),(1167,77),.23),((1024,213),(1179,97),.19),
                           ((1045,235),(1190,115),.12),((1044,260),(1209,156),.14),
                           ((1045,274),(1238,193),.18)]],
    ],clip_path=url("right-clip")),
    path(right_cap,url("right-mouth"),id="short-jet-mouth",stroke="#10213b",stroke_width=1.05,opacity=.84),
])
leftjet=layer("quenched-jet","Quenched jet | full long cone",[
    path(left_path,url("left-long"),id="long-cone"),
    layer("long-jet-light","Long cone glints and ribs",[
        path(left_path,url("left-shadow"),opacity=.75),
        path("M 865.8,361.2 C 665,438 457,519 278,590 Q 290,626 315,661 "
             "C 527,518 693,417 865.8,361.2 Z",url("left-glint"),opacity=.81),
        path(left_path,url("left-warm-depth")),
        *[stroke("M "+xy(m)+" Q "+xy(c)+" "+xy(end),"#384c6d",.62,opacity=o)
          for c,end,o in [((569,448),(271,569),.17),((590,450),(279,588),.18),
                           ((571,456),(289,611),.13),((584,477),(310,661),.14),
                           ((594,493),(320,697),.16)]],
    ],clip_path=url("left-clip")),
    stroke("M 865.8,361.2 C 691,411 510,502 268,565 Q 263,566 266,572 C 285,615 303,658 318,695 Q 320,702 327,697 C 532,540 670,445 865.8,361.2",
           "#36404e",1.05,opacity=.50),
    path(left_cap,url("left-mouth"),id="long-jet-mouth",stroke="#63656a",stroke_width=.75,opacity=.61),
])

# Charged/colored features are illustrative placements copied from visible anchors.
rad=[]
for i,(x,y) in enumerate([(649,467),(697,445),(745,423),(793,400)]):
    a=radians(246+rng.uniform(-7,9))
    ux,uy=cos(a),sin(a)
    nx,ny=-uy,ux
    d="M "+xy((x,y))
    for step in range(9):
        k=step+1
        dist=k*(3.6+rng.uniform(-.10,.1))
        off=2.7*sin(k*pi/2.25)
        p=(x+dist*ux+off*nx,y+dist*uy+off*ny)
        dist0=dist-1.65
        off0=2.9*sin((k-.5)*pi/2.25)
        q=(x+dist0*ux+off0*nx,y+dist0*uy+off0*ny)
        d+=" Q "+xy(q)+" "+xy(p)
    rad.extend([stroke(d,"#93b713",3.0,opacity=.35),
                stroke(d,"#e9e821",1.13,opacity=.91,id=f"gluon-curve-{i+1}"),
                ell(x,y,9.5,9.5,url("gluon-glow"),opacity=.74),
                dot(x,y,4.3,url("gluon-bead"),id=f"gluon-bead-{i+1}")])
for x,y,k in [(569,501,.24),(586,494,.32),(604,485,.44),(625,476,.41),(672,459,.56),(720,437,.68),
              (770,415,.68),(635,435,.66),(679,413,.55),(775,370,.63)]:
    d=f"M {x-3},{y+2} q 8,-2 4,-5 q -4,-3 2,-5"
    rad.append(stroke(d,"#c8cf25",1.8,opacity=k))
radiation=layer("gluon-radiation","Medium-induced radiation and bright beads",rad)

right_frags=[(1191,114,13.1),(1209,135,11.7),(1215,157,12.3),(1208,179,11.3),
             (1188,177,12.8),(1168,128,13.1),(1192,142,14.1),(1172,158,13.8),
             (1145.8,152,11.9),(1156.4,179,11.8)]
left_frags=[(291,611,11.8),(320.5,614,12.4),(297.7,637,11.7)]


def fragments(coords,id,label,g,stroke_color):
    return layer(id,label,[dot(x,y,r,url(g),stroke=stroke_color,stroke_width=1.10,
                               id=f"{id}-{i+1:02d}") for i,(x,y,r) in enumerate(coords)])


star_list=[
    ell(VX,VY,48,38,url("star-warm"),-27,opacity=.64),
    ell(VX,VY,23,22,url("star-hot"),opacity=.9),
]
for i,(ang,L,base) in enumerate([(-93,32,4),(-53,23,3),(-21,26,2.5),(8,29,4),(46,30,4),
                                (81,21,1.8),(126,28,3.5),(169,25,3),(215,32,3.2),(245,20,2)]):
    a=radians(ang)
    ux,uy=cos(a),sin(a)
    tip=(VX+L*ux,VY+L*uy)
    d="M "+xy((VX-base*uy,VY+base*ux))+" L "+xy(tip)+" L "+xy((VX+base*uy,VY-base*ux))+" Z"
    star_list.append(path(d,["#fffcc3","#ffed9d","#fffbd0"][i%3],opacity=.92 if i%2==0 else .78))
star_list.extend([dot(VX,VY,10.7,url("star-hot")),dot(VX,VY,4.0,"#fffdec")])
scattering=layer("hard-scattering","Hard scattering | common luminous vertex",star_list)

annotation=layer("labels","Original editable labels",[
    text(1372,151,"unquenched jet",28,anchor="middle",id="label-short"),
    text(1372,184,"(short path)",28,anchor="middle"),
    text(149,629,"quenched jet",28,anchor="middle",id="label-long"),
    text(149,661,"(long path)",28,anchor="middle"),
    text(778,784,"QGP medium",28,anchor="middle",id="label-qgp"),
    stroke("M 886,369 L 988,386","#2e2f2c",1.25),
    text(996,395,"hard scattering",28,id="label-vertex"),
])
lengthmarker=layer("vertical-marker","Reference double-headed vertical marker",[
    stroke("M 981.4,522 L 981.4,617","#404243",1.8),
    path("M 981.4,515 L 975.6,529.3 L 987.2,529.3 Z","#404243"),
    path("M 981.4,624 L 975.6,609.7 L 987.2,609.7 Z","#404243"),
])


def main():
    document=('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
              'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
              f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">\n'
              '<title id="title">Short and long jet paths through a quark–gluon plasma</title>\n'
              '<desc id="desc">Editable vector redraw of the supplied image: projected ellipsoid with a surface mesh, two complete overlapping cones, and medium-induced radiation. The vertical double arrow has the same unlabeled visual role as in the reference.</desc>\n'
              '<defs>\n'+"\n".join(defs)+'\n</defs>\n'+
              "\n".join([layer("background","White paper",[el("rect",x=0,y=0,width=W,height=H,fill="#fff")]),
                         medium,leftjet,rightjet,radiation,
                         fragments(left_frags,"quenched-fragments","Sparse gray particles","silver-gray","#64717f"),
                         fragments(right_frags,"unquenched-fragments","Compact blue-gray cluster","silver-blue","#50637f"),
                         scattering,lengthmarker,annotation])+'\n</svg>\n')
    (OUT/"jet_ellipsoid_edit.svg").write_text(document,encoding="utf-8")
    im=Image.open(BytesIO(cairosvg.svg2png(bytestring=document.encode("utf-8"),output_width=2336,
                   output_height=1280,background_color="white"))).convert("RGB")
    im.save(OUT/"jet_ellipsoid_edit.png",dpi=(300,300))


if __name__=="__main__":
    main()
