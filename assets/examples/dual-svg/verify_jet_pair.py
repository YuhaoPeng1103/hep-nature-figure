"""Verify that drag edits only transforms, with textures/alpha unchanged and no raster embeds."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as E

import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps

from jet_layers import NS, W, H, raster

HERE=Path(__file__).resolve().parent


def digest(node):
    node=deepcopy(node)
    node.attrib.pop("transform",None)
    node.attrib.pop("display",None)
    return sha256(E.tostring(node)).hexdigest()


def main():
    import argparse
    global HERE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--stem",default="jet")
    a=p.parse_args()
    HERE=a.outdir.resolve()
    source=E.parse(HERE/(a.stem+"_texture.svg")).getroot()
    moved=E.parse(HERE/"demo_drag.svg").getroot()
    hidden=E.parse(HERE/"demo_without_medium.svg").getroot()
    defs=next(n for n in source if n.tag==f"{{{NS}}}defs")
    base={n.get("id"):n for n in source if n.get("data-element")}
    drag={n.get("id"):n for n in moved if n.get("data-element")}
    hide={n.get("id"):n for n in hidden if n.get("data-element")}
    assert base.keys()==drag.keys()==hide.keys()
    modified={"quenched-jet","quenched-fragments","gluon-radiation"}
    for key,obj in base.items():
        assert digest(obj)==digest(drag[key])==digest(hide[key]),key
        if key in modified:
            assert drag[key].get("transform")=="translate(0 105)"
        else:
            assert obj.get("transform")==drag[key].get("transform"),key
    assert hide["qgp-medium"].get("display")=="none"
    for key in base.keys()-{"qgp-medium"}:
        assert hide[key].get("display")==base[key].get("display"),key
    ids=[n.get("id") for n in source.iter() if n.get("id")]
    assert len(ids)==len(set(ids))
    assert not any(n.tag.rsplit("}",1)[-1] in ("image","foreignObject","script") for n in source.iter())

    # Independent transparent layer, rendered before and after an integer translation.
    images=[]
    for obj in (base["quenched-jet"],drag["quenched-jet"]):
        v=E.Element(f"{{{NS}}}svg",{"width":str(W),"height":str(H),"viewBox":f"0 0 {W} {H}"})
        v.append(deepcopy(defs))
        v.append(deepcopy(obj))
        images.append(np.asarray(raster(v)))
    assert np.array_equal(images[0][:-105],images[1][105:]),"intrinsic RGBA changed during drag"
    assert not images[1][:105,:,3].any()

    ref=np.asarray(Image.open(
      a.reference).convert("RGB"))
    result=np.asarray(raster(source,white=True).convert("RGB"))
    error=np.abs(result.astype(np.int16)-ref.astype(np.int16))
    report={
      "native_size":[W,H],"independent_top_level_object_groups":len(base),"native_text_objects":len(list(source.iter(f"{{{NS}}}text"))),
      "embedded_images":0,"move_only_changes_transform":True,"hide_only_changes_display":True,
      "long_jet_RGBA_identical_after_translation":True,
      "source_RGB_mean_absolute_error":float(error.mean()),"source_RGB_max_error":int(error.max()),
      "source_fraction_any_RGB_difference":float(np.any(error,axis=2).mean()),
      "reference_identical":bool(not error.any()),
      "reconstructed_occlusion":"Complete medium behind former jets, with extended parametric grid and lighting."
    }
    (HERE/"verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)

    # One bounded JPEG preview through the workspace preview tool.
    files=[("Initial placement",HERE/(a.stem+"_texture.png")),
           ("Dragged with normal SVG transform",HERE/"demo_drag.png"),
           ("Medium hidden",HERE/"demo_without_medium.png")]
    sheet=Image.new("RGB",(1800,405),"#eaf0f2")
    d=ImageDraw.Draw(sheet)
    try:
        font=ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf",19)
    except OSError:
        font=ImageFont.load_default()
    for i,(title,path) in enumerate(files):
        x=12+i*596
        d.rectangle((x,12,x+581,391),fill="white")
        d.text((x+11,23),title,font=font,fill="#26343b")
        with Image.open(path) as im:
            thumb=ImageOps.contain(im.convert("RGB"),(572,319),Image.Resampling.LANCZOS)
        sheet.paste(thumb,(x+(582-thumb.width)//2,63+(319-thumb.height)//2))
    sheet.save(HERE/"edit_proof.png")


if __name__=="__main__":
    main()
