"""Produce both SVG variants of the worked 1522x848 jet example."""
import argparse
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import re
from PIL import Image
from jet_layers import build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--stem",default="jet")
    a=p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*",a.stem):
        p.error("--stem must be a simple filename stem")
    with Image.open(a.reference) as img:
        if img.size!=(1522,848):
            p.error("This worked example needs its 1522x848 reference; adapt the scene for a new image")
    output=a.outdir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    spec=spec_from_file_location("jet_geometry_example",Path(__file__).with_name("jet_geometry.py"))
    geom=module_from_spec(spec)
    spec.loader.exec_module(geom)
    geom.OUT=output
    geom.main()
    gsvg=output/(a.stem+"_edit.svg")
    gpng=output/(a.stem+"_edit.png")
    (output/"jet_ellipsoid_edit.svg").replace(gsvg)
    (output/"jet_ellipsoid_edit.png").replace(gpng)
    build(a.reference.resolve(),gsvg,output)
    (output/"jet_independent.svg").replace(output/(a.stem+"_texture.svg"))
    (output/"jet_independent.png").replace(output/(a.stem+"_texture.png"))
    print("Both variants:",gsvg,output/(a.stem+"_texture.svg"))


if __name__=="__main__":
    main()
