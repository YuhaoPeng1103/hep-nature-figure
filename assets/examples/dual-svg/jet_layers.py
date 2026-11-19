"""Independent transparent layers for the reference jet figure; no appearance-mode switching."""
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from xml.etree import ElementTree as E

import cairosvg
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter, distance_transform_edt

HERE=Path(__file__).resolve().parent
BASE=None
REF=None
W,H=1522,848
NS="http://www.w3.org/2000/svg"
INK="http://www.inkscape.org/namespaces/inkscape"
E.register_namespace("",NS)
E.register_namespace("inkscape",INK)
E.register_namespace("xlink","http://www.w3.org/1999/xlink")


def raster(root,w=W,h=H,white=False):
    png=cairosvg.svg2png(bytestring=E.tostring(root),output_width=w,output_height=h,
                        background_color="white" if white else None)
    return Image.open(BytesIO(png)).convert("RGBA")


def vector_texture(fg,alpha):
    rgb=np.clip(np.rint(fg),0,255).astype(np.uint8)
    aa=np.clip(np.rint(alpha*255),0,255).astype(np.uint8)
    rgba=(rgb[:,:,0].astype(np.uint64)<<24)|(rgb[:,:,1].astype(np.uint64)<<16)|(
          rgb[:,:,2].astype(np.uint64)<<8)|aa.astype(np.uint64)
    rgba[aa==0]=0
    active={}
    fills=defaultdict(list)
    count=0

    def close(key,y0,y1):
        nonlocal count
        x0,x1,col=key
        fills[col].append(f"M{x0} {y0}h{x1-x0}v{y1-y0}H{x0}z")
        count+=1

    for y,row in enumerate(rgba):
        edges=np.r_[0,np.flatnonzero(row[:-1]!=row[1:])+1,W]
        current={}
        for x0,x1 in zip(edges[:-1],edges[1:]):
            x0,x1=int(x0),int(x1)
            col=int(row[x0])
            if not col: continue
            key=(x0,x1,col)
            current[key]=active.pop(key,y)
        for key,start in active.items(): close(key,start,y)
        active=current
    for key,start in active.items(): close(key,start,H)
    result=[]
    for col,parts in sorted(fills.items()):
        a=col&255; rgb=col>>8
        attrs={"fill":f"#{rgb:06x}","d":"".join(parts)}
        if a!=255: attrs["fill-opacity"]=f"{a/255:.8f}"
        result.append(E.Element(f"{{{NS}}}path",attrs))
    return result,count


def compose(bg,fg,a):
    return np.clip(np.rint(fg*a[:,:,None]+bg*(1-a[:,:,None])),0,255)


def unmix(target,bg,prior_rgba,mask,kind):
    """Find a bounded intrinsic foreground color and coverage, before compositing."""
    prior=prior_rgba[:,:,:3].astype(float)
    pa=prior_rgba[:,:,3]/255.
    d=prior-bg
    q=target-bg
    strength=np.sum(q*d,axis=2)/np.maximum(np.sum(d*d,axis=2),1)
    # The lower bound ensures the unpremultiplied color is finite and within gamut.
    low=np.max(np.where(q>=0,q/np.maximum(255-bg,1),-q/np.maximum(bg,1)),axis=2)
    low=np.clip(low,0,1)
    if kind=="glow":
        a=np.maximum(low+.015,np.clip(strength,.02,.97))
    else:
        # Keep intrinsic opacity stable in cone interiors, feather only its own edge.
        a=np.maximum(low+.015,np.maximum(np.clip(strength,0,1),pa*.62))
    a=np.clip(a,.008,1)
    a=np.rint(a*255)/255
    fg=(target-bg*(1-a[:,:,None]))/np.maximum(a[:,:,None],1/255)
    fg=np.clip(np.rint(fg),0,255)
    a=np.where(mask,a,0)
    return fg,a


def build(reference, native, outdir):
    global HERE, BASE, REF
    HERE=Path(outdir).resolve()
    BASE=Path(native).resolve()
    REF=Path(reference).resolve()
    HERE.mkdir(parents=True,exist_ok=True)
    with Image.open(REF) as image:
        if image.size!=(W,H):
            raise ValueError("Adapt the worked geometry/config for a different reference size")
    original=E.parse(BASE).getroot()
    defs=next(n for n in original if n.tag==f"{{{NS}}}defs")
    native={n.get("id"):n for n in original if n.tag==f"{{{NS}}}g"}
    src=np.asarray(Image.open(REF).convert("RGB")).astype(float)

    # Original geometry remains the source for complete silhouettes and editing handles.
    scene=E.Element(f"{{{NS}}}svg",{"width":str(W),"height":str(H),
         "viewBox":f"0 0 {W} {H}","role":"img","aria-labelledby":"title desc"})
    E.SubElement(scene,f"{{{NS}}}title",{"id":"title"}).text="Jet quenching: independently movable transparent vector layers"
    E.SubElement(scene,f"{{{NS}}}desc",{"id":"desc"}).text=(
      "Reference-derived intrinsic colors and alpha, with reconstructed occluded medium. "
      "Every physical object has independent transparent vector texture and native geometric controls. "
      "Moving an object requires only a group transform; no script or visibility-mode switch is necessary. "
      "Hidden surfaces are schematic reconstruction, not recovered source-engineering data.")
    scene.append(deepcopy(defs))
    # Retain the shared contour used by the native fallback's internal clips.
    shared=next(n for n in native["qgp-medium"].iter() if n.get("id")=="qgp-outline")
    next(n for n in scene if n.tag==f"{{{NS}}}defs").append(deepcopy(shared))
    E.SubElement(scene,f"{{{NS}}}rect",{"width":str(W),"height":str(H),"fill":"white"})

    def isolated(key):
        r=E.Element(f"{{{NS}}}svg",{"viewBox":f"0 0 {W} {H}","width":str(W),"height":str(H)})
        r.append(deepcopy(defs))
        r.append(deepcopy(native[key]))
        return np.asarray(raster(r))

    keys=["qgp-medium","quenched-jet","unquenched-jet","gluon-radiation",
          "quenched-fragments","unquenched-fragments","hard-scattering"]
    rgba={k:isolated(k) for k in keys}
    sup={k:rgba[k][:,:,3]>3 for k in keys}
    yy,xx=np.mgrid[:H,:W]
    radius=np.sqrt(((xx-769.5)/186.)**2+((yy-393)/335.4)**2)
    warm=(src[:,:,0]>src[:,:,1]+23)&(src[:,:,1]>src[:,:,2]+10)
    medium_domain=(radius<1.075)&warm
    # Clear the observed foreground before reconstructing the full surface.
    occlusion=np.zeros((H,W),bool)
    for key in keys[1:]:
        occlusion|=binary_dilation(sup[key],iterations=11 if 'jet' in key else 6)
    # The photographed long ray casts a broad soft shadow beyond the nominal
    # cone silhouette. Remove that entire corridor from the reconstructed medium.
    longdist=np.abs((xx-865.8)*.428+(yy-361.2)*.904)
    occlusion |= (longdist<57)&(xx<910)&(yy>305)
    occlusion |= ((xx-865.8)**2+(yy-361.2)**2<62**2)
    occlusion|=((xx>=883)&(xx<=994)&(yy>=363)&(yy<=393))
    med_rgba=rgba["qgp-medium"].astype(float)
    med_prior=compose(np.full_like(src,255),med_rgba[:,:,:3],med_rgba[:,:,3]/255)
    valid=medium_domain&~occlusion
    # Extend the source-minus-parametric-lighting field through hidden regions.
    # This preserves a complete native ellipsoid and continues its grid, instead
    # of letting an inpainting brush drag white paper through the rim.
    weights=gaussian_filter(valid.astype(float),18)
    residual=np.stack([gaussian_filter(np.where(valid,src[:,:,c]-med_prior[:,:,c],0),18)/
                        np.maximum(weights,1e-5) for c in range(3)],axis=2)
    model=np.clip(med_prior+residual,0,255)
    weight=np.clip(distance_transform_edt(~occlusion)/22,0,1)*valid
    clean=np.clip(model*(1-weight[:,:,None])+src*weight[:,:,None],0,255)
    holes=occlusion&(radius<1.07)
    # Source edge colors against white become an intrinsic orange surface with soft alpha.
    ma=np.ones((H,W),float)
    edge=radius>.957
    ma[edge]=np.clip((255-clean[:,:,2][edge])/255,0,1)
    ma[(radius>1.075)|((~medium_domain)&(radius>=1.0)&~occlusion)]=0
    # Use a smooth, geometry-derived alpha in the small repaired boundary intervals.
    a0=med_rgba[:,:,3]/255
    repaired=holes&(radius>.957)
    ma[repaired]=a0[repaired]
    mfg=np.clip((clean-255*(1-ma[:,:,None]))/np.maximum(ma[:,:,None],1/255),0,255)
    medium_target=compose(np.full_like(src,255),mfg,ma)

    metrics={}
    layers=[]

    def add(key,fg,a,label):
        group=E.Element(f"{{{NS}}}g",{"id":key,"data-element":key,
            f"{{{INK}}}groupmode":"layer",f"{{{INK}}}label":label,
            "data-alpha-model":"intrinsic foreground, independent of current background"})
        # Native silhouette controls remain present and are visible in outline editors.
        controls=E.SubElement(group,f"{{{NS}}}g",{"id":key+"-geometry","data-role":"native-geometry",
                                               "display":"none"})
        controls.append(deepcopy(native[key]))
        # Avoid duplicating ids: these controls are only geometric references.
        for n in controls.iter():
            if n is controls: continue
            if n.get("id"): n.set("id",n.get("id")+"-control")
            if n.get("data-element"): n.attrib.pop("data-element")
        texture=E.SubElement(group,f"{{{NS}}}g",{"id":key+"-texture",
            "data-role":"intrinsic-RGBA-vector-texture","shape-rendering":"crispEdges"})
        paths,count=vector_texture(fg,a)
        texture.extend(paths)
        scene.append(group)
        layers.append(key)
        metrics[key]={"vector_rectangles":count,"colored_samples":int((a>0).sum()),
                       "transparent_samples":int(((a>0)&(a<1)).sum())}
        print(key,metrics[key],flush=True)

    add("qgp-medium",mfg,ma,"QGP medium | complete surface, background-free edge")
    bg=medium_target

    # In the long cone the gray color is mixed with orange medium in the screenshot.
    # Estimate intrinsic RGBA against the reconstructed medium, rather than storing that orange.
    for key in ["quenched-jet","unquenched-jet"]:
        support=binary_dilation(sup[key],iterations=2)
        mask=support.copy()
        # Later objects are holes in the observation, not holes in this cone.
        hidden=np.zeros((H,W),bool)
        for upper in ["gluon-radiation","quenched-fragments","unquenched-fragments","hard-scattering"]:
            hidden|=binary_dilation(sup[upper],iterations=2)
        target=src.copy()
        n=rgba[key]
        priorcomp=compose(bg,n[:,:,:3].astype(float),n[:,:,3]/255)
        # Repair hidden cone color with its native gradient. Soft boundaries outside the
        # source cone fade according to its original geometry.
        target[hidden&mask]=priorcomp[hidden&mask]
        foreground,alpha=unmix(target,bg,n,mask,"body")
        # A ray's intrinsic texture is cool gray/blue. Orange from its former
        # background is not part of that texture, even at uncertain edge pixels.
        orange=(foreground[:,:,0]>foreground[:,:,1]*1.20+14)&(
                 foreground[:,:,0]>foreground[:,:,2]*1.25+14)
        foreground[orange&mask]=n[:,:,:3][orange&mask]
        # White near a geometrically uncertain edge must stay transparent, not paint a white rim.
        blank=(src.min(axis=2)>249)&(radius>1.02)
        alpha[blank]=0
        add(key,foreground,alpha,("Quenched long cone" if key=="quenched-jet" else "Unquenched short cone")+" | intrinsic RGBA")
        bg=compose(bg,foreground,alpha)

    for key in ["gluon-radiation","quenched-fragments","unquenched-fragments","hard-scattering"]:
        mask=binary_dilation(sup[key],iterations=1)
        n=rgba[key]
        if key=="gluon-radiation":
            # Emission coverage: source yellow; nearby orange is medium, not the curve.
            yellow=(src[:,:,1]>src[:,:,2]*1.45+12)&(src[:,:,1]>95)&(src[:,:,0]>100)
            mask &= yellow
        if key=="hard-scattering":
            # Native star defines the whole emission support. Subtract the current
            # composed surface before recovering the luminous intrinsic color.
            native_a=n[:,:,3]/255
            mask &= (native_a>.01)
            observed_light=src@np.array([.2126,.7152,.0722])
            underlying_light=bg@np.array([.2126,.7152,.0722])
            mask &= (observed_light>underlying_light+3)
        fg,a=unmix(src,bg,n,mask,"glow" if key in ("hard-scattering","gluon-radiation") else "body")
        # If the observation is unchanged/background colored, retain no opacity.
        projected=np.sum((src-bg)*(n[:,:,:3].astype(float)-bg),axis=2)
        a[(projected<0)&(n[:,:,3]<160)]=0
        add(key,fg,a,key.replace("-"," ").title()+" | transparent independent color")
        bg=compose(bg,fg,a)

    # Real text and original geometric leader/marker; no old glyph patches on top.
    scene.append(deepcopy(native["vertical-marker"]))
    scene.append(deepcopy(native["labels"]))
    target=HERE/"jet_independent.svg"
    E.ElementTree(scene).write(target,encoding="utf-8",xml_declaration=True)
    (HERE/"layer_report.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    # Save canonical foreground alpha arrays to prove rigid edits change no textures.
    np.savez_compressed(HERE/"medium_reconstruction.npz",rgb=mfg.astype(np.uint8),
                        alpha=np.rint(ma*255).astype(np.uint8),repaired=holes)
    raster(scene,2336,1280,white=True).convert("RGB").save(HERE/"jet_independent.png")
    # These edits use ONLY standard SVG group transform and display attributes.
    move=deepcopy(scene)
    for key in ("quenched-jet","quenched-fragments","gluon-radiation"):
        next(n for n in move if n.get("id")==key).set("transform","translate(0 105)")
    E.ElementTree(move).write(HERE/"demo_drag.svg",encoding="utf-8",xml_declaration=True)
    raster(move,2336,1280,white=True).convert("RGB").save(HERE/"demo_drag.png")
    hide=deepcopy(scene)
    next(n for n in hide if n.get("id")=="qgp-medium").set("display","none")
    E.ElementTree(hide).write(HERE/"demo_without_medium.svg",encoding="utf-8",xml_declaration=True)
    raster(hide,2336,1280,white=True).convert("RGB").save(HERE/"demo_without_medium.png")
    print("Saved",target,target.stat().st_size,"bytes",flush=True)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--geometry",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    a=p.parse_args()
    build(a.reference,a.geometry,a.outdir)
