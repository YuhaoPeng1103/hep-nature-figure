#!/usr/bin/env python3
"""Validate geometry/texture SVG deliverables and an edit that changes only object transforms."""
import argparse
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree as ET

NS="http://www.w3.org/2000/svg"


def load(path):
    text=path.read_text(encoding="utf-8-sig")
    root=ET.fromstring(text)
    if root.tag!=f"{{{NS}}}svg" or len(root.get("viewBox","").replace(","," ").split())!=4:
        raise ValueError(f"{path}: missing SVG/viewBox")
    ids=[n.get("id") for n in root.iter() if n.get("id")]
    if len(ids)!=len(set(ids)):
        raise ValueError(f"{path}: duplicate ids")
    refs=set()
    for node in root.iter():
        if node.tag.rsplit("}",1)[-1] in ("image","feImage","foreignObject","script"):
            raise ValueError(f"{path}: raster/foreignObject/script is not allowed")
        for key,value in node.attrib.items():
            if key.rsplit("}",1)[-1]=="href":
                refs.add(value)
    refs.update(m.group(1).strip().strip("'\"") for m in re.finditer(r"url\(\s*([^)]*)\)",text))
    if any(not r.startswith("#") or r[1:] not in ids for r in refs):
        raise ValueError(f"{path}: external or unresolved SVG reference")
    groups={n.get("id"):n for n in root if n.get("data-element") and n.get("id")!="background"}
    if not groups:
        raise ValueError(f"{path}: no named top-level physical objects")
    words=["".join(n.itertext()).strip() for n in root.iter(f"{{{NS}}}text")]
    return root,groups,words


def named_objects(root):
    objects = {}
    for node in root:
        if node.tag == f"{{{NS}}}defs":
            continue
        if node.get("id") and node.get("data-element"):
            objects[node.get("id")] = node
        if node.tag == f"{{{NS}}}g":
            objects.update(named_objects(node))
    return objects


def validate_edit(original, edited, changed, kind):
    before, after = deepcopy(original), deepcopy(edited)
    original_objects, edited_objects = named_objects(before), named_objects(after)
    if not set(changed) <= original_objects.keys() & edited_objects.keys():
        raise ValueError("Unknown changed object")
    for key in changed:
        previous = original_objects[key].attrib.pop(kind, None)
        current = edited_objects[key].attrib.pop(kind, None)
        if previous == current:
            raise ValueError(f"{key}: declared edit made no change")
    if ET.tostring(before) != ET.tostring(after):
        raise ValueError("Edit changed content outside the declared attributes")


def rgba_probe(root,obj,modified,report_only=False):
    import cairosvg
    import numpy as np
    from PIL import Image
    m=re.fullmatch(r"\s*translate\(\s*(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)\s*\)\s*",
                   modified.get("transform",""))
    if not m or obj.get("transform"):
        raise ValueError("RGBA probe requires a single translate(dx dy) from an untransformed group")
    dx,dy=map(float,m.groups())
    if dx!=int(dx) or dy!=int(dy):
        raise ValueError("RGBA probe needs integer source-pixel translation")
    dx,dy=int(dx),int(dy)
    _,_,w,h=map(float,root.get("viewBox").replace(","," ").split())
    if (w,h)!=(int(w),int(h)) or min(w,h)<=0:
        raise ValueError("RGBA probe requires a positive integer viewBox size")
    w,h=int(w),int(h)
    if abs(dx)>=w or abs(dy)>=h:
        raise ValueError("RGBA probe has no overlap inside the canvas")
    images=[]
    for group in (obj,modified):
        doc=ET.Element(f"{{{NS}}}svg",{"viewBox":root.get("viewBox"),"width":str(w),"height":str(h)})
        for name in ("font-family","fill","stroke","font-size"):
            if name in root.attrib: doc.set(name,root.get(name))
        for node in root:
            if node.tag==f"{{{NS}}}defs": doc.append(deepcopy(node))
        doc.append(deepcopy(group))
        data=cairosvg.svg2png(bytestring=ET.tostring(doc),output_width=w,output_height=h)
        images.append(np.asarray(Image.open(BytesIO(data)).convert("RGBA")))
    a,b=images
    # Reject translation which clips visible original pixels: otherwise a crop
    # could hide a failure rather than proving the complete object is preserved.
    yy,xx=np.where(a[:,:,3]>0)
    if not len(xx) or min(xx+dx)<0 or max(xx+dx)>=w or min(yy+dy)<0 or max(yy+dy)>=h:
        raise ValueError("RGBA probe requires a nonempty object fully inside the edited canvas")
    left,right=max(0,-dx),min(w,w-dx)
    top,bottom=max(0,-dy),min(h,h-dy)
    reference = a[top:bottom, left:right]
    translated = b[top+dy:bottom+dy, left+dx:right+dx]
    permitted=np.zeros((h,w),dtype=bool)
    permitted[top+dy:bottom+dy,left+dx:right+dx]=True
    if not b[..., 3].any():
        raise ValueError("RGBA probe did not render the translated object")
    if b[:,:,3][~permitted].any():
        raise ValueError("Unexpected pixels outside the translated object")
    if np.array_equal(reference, translated):
        print("PASS: intrinsic object RGBA identical after integer translation")
        return
    if not report_only:
        raise ValueError("Intrinsic RGBA changed after translation")

    foreground = (reference[..., 3] > 0) | (translated[..., 3] > 0)
    a, b = reference[foreground].astype(float), translated[foreground].astype(float)
    difference = np.abs(a - b)
    a[:, :3] *= a[:, 3:] / 255
    b[:, :3] *= b[:, 3:] / 255
    premultiplied = np.abs(a - b)
    print(f"DIAGNOSTIC: RGBA differs at {np.any(difference > 0, axis=1).sum()} / "
          f"{len(a)} foreground pixels after alignment (0-255 channels)")
    print(f"  Straight RGBA MAE {difference.mean():.6f}, max {difference.max():.0f}")
    print(f"  Premultiplied RGBA MAE {premultiplied.mean():.6f}, max {premultiplied.max():.3f}")
    print("  Exact RGBA equality not met. Inspect the aligned object and scene renders.")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--geometry",type=Path,required=True)
    p.add_argument("--texture",type=Path,required=True)
    p.add_argument("--edited",type=Path)
    p.add_argument("--changed",nargs="+",default=[])
    p.add_argument("--kind",choices=("transform","display"),default="transform")
    p.add_argument("--rgba-object",help="optional expensive RGBA translation probe")
    p.add_argument("--rgba-report-only", action="store_true",
                   help="report rendering differences without requiring exact RGBA equality")
    a=p.parse_args()
    if a.rgba_report_only and not a.rgba_object:
        p.error("--rgba-report-only requires --rgba-object")
    if bool(a.edited)!=bool(a.changed) or (a.rgba_object and (not a.edited or a.kind!="transform")):
        p.error("--edited requires --changed, and --rgba-object requires a transform edit")
    try:
        gr,gg,gt=load(a.geometry)
        tr,tg,tt=load(a.texture)
        if gr.get("viewBox")!=tr.get("viewBox") or gg.keys()!=tg.keys():
            raise ValueError("Two variants must share the same viewBox and top-level object IDs (except background)")
        if sorted(gt)!=sorted(tt):
            raise ValueError("Native text content differs between variants")
        if not any(n.get("data-role")=="intrinsic-RGBA-vector-texture" for n in tr.iter()):
            raise ValueError("Texture variant lacks declared independent RGBA textures")
        if any(n.get("data-role")=="appearance-patch" for n in tr.iter()):
            raise ValueError("The old background-dependent appearance patch is not the texture deliverable")
        if a.edited:
            er,_,_=load(a.edited)
            validate_edit(tr, er, a.changed, a.kind)
            print(f"PASS: edit changes only {a.kind} on the declared objects")
            if a.rgba_object:
                if a.rgba_object not in a.changed: raise ValueError("RGBA object must be among --changed")
                original, edited = named_objects(tr), named_objects(er)
                if a.rgba_object not in tg:
                    raise ValueError("RGBA probe requires a top-level object to preserve its scene context")
                rgba_probe(tr, original[a.rgba_object], edited[a.rgba_object], a.rgba_report_only)
        print(f"PASS: both variants, {len(tg)} named objects, {len(tt)} native text objects, no raster embeds")
    except (ImportError,OSError,ValueError,ET.ParseError) as exc:
        p.exit(1,f"FAIL: {exc}\n")


if __name__=="__main__":
    main()
