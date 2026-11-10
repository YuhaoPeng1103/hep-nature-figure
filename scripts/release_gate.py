#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a semantic release manifest and its derived SVG artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


AUX_ELEMENT_IDS = {"detail-layer"}
PICK_IGNORE = {"background"}
SCHEMA = "hep-nature-figure/release-v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_svg(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def element_ids(root: ET.Element) -> list[str]:
    seen = set()
    out = []
    for node in root.iter():
        value = node.attrib.get("data-element", "")
        if value and value not in AUX_ELEMENT_IDS and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def text_counter(root: ET.Element) -> Counter:
    values = []
    for node in root.iter():
        if local_name(node.tag) == "text":
            text = "".join(node.itertext())
            text = " ".join(text.split())
            if text:
                values.append(text)
    return Counter(values)


def row(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def check_release(manifest: Path, render_visual: Path | None = None,
                  render_pick: Path | None = None) -> tuple[list[dict], bool]:
    rows: list[dict] = []
    ok = True
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        return [row("manifest", "fail", "cannot read manifest: %s" % exc)], False
    if data.get("schema") != SCHEMA:
        rows.append(row("schema", "fail", "expected %s" % SCHEMA))
        ok = False
    else:
        rows.append(row("schema", "pass", SCHEMA))

    sources = data.get("truth_source") or {}
    source_paths = {}
    for name in ("bitmap", "trace", "ir"):
        item = sources.get(name)
        if not item:
            continue
        path = Path(item["path"])
        if not path.exists():
            rows.append(row("source:" + name, "fail", "missing %s" % path))
            ok = False
        elif sha256(path) != item.get("sha256"):
            rows.append(row("source:" + name, "fail", "stale hash %s" % path))
            ok = False
        else:
            rows.append(row("source:" + name, "pass", str(path)))
            source_paths[name] = path

    artifact_paths = {}
    roots = {}
    for name, item in (data.get("artifacts") or {}).items():
        if not item:
            continue
        path = Path(item["path"])
        if not path.exists():
            rows.append(row("artifact:" + name, "fail", "missing %s" % path))
            ok = False
            continue
        if sha256(path) != item.get("sha256"):
            rows.append(row("artifact:" + name, "fail", "stale hash %s" % path))
            ok = False
            continue
        try:
            root = parse_svg(path)
        except Exception as exc:
            rows.append(row("artifact:" + name, "fail", "invalid SVG: %s" % exc))
            ok = False
            continue
        artifact_paths[name] = path
        roots[name] = root
        role = root.attrib.get("data-artifact")
        contract = root.attrib.get("data-contract")
        expected = (item.get("role"), item.get("contract"))
        if (role, contract) != expected:
            rows.append(row("root:" + name, "fail",
                            "metadata %r != %r" % ((role, contract), expected)))
            ok = False
        else:
            rows.append(row("root:" + name, "pass", "%s/%s" % expected))

    id_sets = {name: element_ids(root) for name, root in roots.items()
               if name in ("edit_master", "visual_master", "visual_pick")}
    physical_ids = id_sets.get("edit_master") or id_sets.get("visual_master") or []
    if "edit_master" in id_sets and "visual_master" in id_sets:
        a, b = set(id_sets["edit_master"]), set(id_sets["visual_master"])
        if a != b:
            rows.append(row("elements", "fail",
                            "edit-only=%s visual-only=%s" %
                            (sorted(a - b), sorted(b - a))))
            ok = False
        else:
            rows.append(row("elements", "pass", "%d semantic IDs" % len(a)))

    for name, root in roots.items():
        images = [node for node in root.iter() if local_name(node.tag) == "image"]
        if images:
            rows.append(row("raster:" + name, "fail",
                            "%d embedded raster element(s)" % len(images)))
            ok = False
        else:
            rows.append(row("raster:" + name, "pass", "no embedded raster"))

    trace = source_paths.get("trace")
    expected_text = text_counter(parse_svg(trace)) if trace and trace.exists() else Counter()
    for name in ("edit_master", "visual_master"):
        root = roots.get(name)
        if root is None:
            continue
        actual = text_counter(root)
        if actual != expected_text:
            rows.append(row("text:" + name, "fail",
                            "missing=%s extra=%s" %
                            (list((expected_text - actual).elements()),
                             list((actual - expected_text).elements()))))
            ok = False
        else:
            rows.append(row("text:" + name, "pass",
                            "%d editable text run(s)" % sum(actual.values())))

    pick = roots.get("visual_pick")
    if pick is not None:
        hit_ids = set()
        for node in pick.iter():
            if node.attrib.get("data-object") != "1":
                continue
            if node.attrib.get("data-sub") == "sub-object":
                continue
            value = node.attrib.get("data-element", "")
            if value:
                hit_ids.add(value)
        expected_ids = set(physical_ids) - PICK_IGNORE
        if not expected_ids.issubset(hit_ids):
            rows.append(row("pick", "fail",
                            "missing targets=%s" % sorted(expected_ids - hit_ids)))
            ok = False
        else:
            rows.append(row("pick", "pass", "%d semantic targets" % len(expected_ids)))

    if render_visual and render_pick and render_visual.exists() and render_pick.exists():
        same = render_visual.read_bytes() == render_pick.read_bytes()
        rows.append(row("render", "pass" if same else "fail",
                        "pick layer changes rendered bytes" if not same else
                        "rendered bytes identical"))
        ok = ok and same
    else:
        rows.append(row("render", "unavailable",
                        "provide both --render-visual and --render-pick"))
    return rows, ok


def main() -> int:
    ap = argparse.ArgumentParser(description="validate a semantic release")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--render-visual")
    ap.add_argument("--render-pick")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    rows, ok = check_release(
        Path(a.manifest).resolve(),
        Path(a.render_visual).resolve() if a.render_visual else None,
        Path(a.render_pick).resolve() if a.render_pick else None,
    )
    render = next((r for r in rows if r["check"] == "render"), {})
    report = {"schema": "hep-nature-figure/release-gate-v1", "ok": ok,
              "render_check": render.get("status", "unavailable"), "checks": rows}
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    for item in rows:
        print("%-22s %-11s %s" % (item["check"], item["status"], item["detail"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
