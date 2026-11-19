#!/usr/bin/env python3
"""Check a self-contained native SVG and optionally render a layer-hide review image."""

import argparse
import re
from pathlib import Path
from xml.etree import ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
ET.register_namespace("", SVG)
ET.register_namespace("inkscape", INK)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def check(source, required, hide, min_text):
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", source, re.IGNORECASE):
        raise ValueError("SVG must not contain a DTD or entity declaration")
    root = ET.fromstring(source)
    if root.tag != f"{{{SVG}}}svg":
        raise ValueError("expected an SVG document")
    if len(root.get("viewBox", "").replace(",", " ").split()) != 4:
        raise ValueError("SVG must declare a viewBox")

    ids, groups, refs = {}, {}, set()
    texts = 0
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1]
        if name in {"image", "feImage", "foreignObject", "script"}:
            raise ValueError(f"non-native content: {name}")
        key = node.get("id")
        if key:
            if key in ids:
                raise ValueError(f"duplicate id: {key}")
            ids[key] = node
        if name == "g" and (node.get("data-element") or node.get(f"{{{INK}}}groupmode") == "layer"):
            for alias in {key, node.get("data-element")} - {None, ""}:
                groups.setdefault(alias, []).append(node)
        if name == "text" and "".join(node.itertext()).strip():
            texts += 1
        for attr, value in node.attrib.items():
            if attr.rsplit("}", 1)[-1] == "href" and name != "a":
                refs.add(value.strip())
    refs.update(m.group(1).strip().strip("'\"") for m in re.finditer(r"url\(\s*([^)]*)\)", source))
    bad = sorted(ref for ref in refs if not ref.startswith("#") or ref[1:] not in ids)
    if bad:
        raise ValueError(f"unresolved or external SVG references: {', '.join(bad)}")
    if not groups:
        raise ValueError("no named object groups")
    if texts < min_text:
        raise ValueError(f"only {texts} editable text objects; expected at least {min_text}")

    for key in set(required) | set(hide):
        found = groups.get(key, [])
        if len(found) != 1:
            raise ValueError(f"expected one named object group for {key!r}; found {len(found)}")
    for key in hide:
        node = groups[key][0]
        node.set("display", "none")
        node.set("style", node.get("style", "").rstrip(";") + ";display:none")

    return root, texts, len({id(node) for matches in groups.values() for node in matches})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("svg", type=Path)
    p.add_argument("--require", nargs="+", default=[], metavar="OBJECT")
    p.add_argument("--min-text", default=1, type=int, help="use 0 for an unlabeled figure")
    p.add_argument("--hide", nargs="+", default=[], metavar="OBJECT")
    p.add_argument("--hidden-png", type=Path, help="render a modified copy; never changes the SVG")
    a = p.parse_args()
    if a.min_text < 0 or bool(a.hide) != bool(a.hidden_png):
        p.error("--min-text must be nonnegative; --hide and --hidden-png must be given together")
    if a.hidden_png and (a.hidden_png.suffix.lower() != ".png" or a.hidden_png.resolve() == a.svg.resolve()):
        p.error("--hidden-png must be a PNG path distinct from the SVG")
    try:
        root, texts, groups = check(a.svg.read_text(encoding="utf-8-sig"), a.require, a.hide, a.min_text)
    except (OSError, ValueError, ET.ParseError) as exc:
        p.exit(1, f"FAIL: {exc}\n")
    if a.hidden_png:
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=ET.tostring(root), write_to=str(a.hidden_png),
                             output_width=2336, output_height=1280, background_color="white")
        except (ImportError, OSError, ValueError) as exc:
            p.exit(1, f"FAIL: cannot render hidden-layer PNG: {exc}\n")
        print(f"Review {a.hidden_png}: hidden {', '.join(a.hide)}. Inspect the revealed geometry.")
    print(f"PASS: {groups} named object groups, {texts} editable text objects, no raster embeds")


if __name__ == "__main__":
    main()
