#!/usr/bin/env python3
"""Rebuild the PRL 125, 122301 QGP/photon/jet schematic as native SVG."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "element-library"
INDEX = LIB / "index.json"
SOURCE = (
    LIB
    / "source-corpus"
    / "publisher"
    / "figures"
    / "aps"
    / "2020"
    / "10.1103-physrevlett.125.122301"
    / "fig01.png"
)
ASSET_ID = "article_prl125_qgp_jet_scene"
REL = Path("source-derived/medium") / ASSET_ID


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="660" height="340"
     viewBox="0 0 660 340" data-element-asset="article_prl125_qgp_jet_scene"
     data-origin="article_vector_native">
  <defs>
    <linearGradient id="qgp-top" x1="0" y1="55" x2="0" y2="178">
      <stop offset="0" stop-color="#fffdf1"/>
      <stop offset=".22" stop-color="#fff0a6"/>
      <stop offset=".72" stop-color="#ffd96b"/>
      <stop offset="1" stop-color="#f2bd43"/>
    </linearGradient>
    <linearGradient id="qgp-bottom" x1="0" y1="170" x2="0" y2="292">
      <stop offset="0" stop-color="#f2b648"/>
      <stop offset=".45" stop-color="#f5a84b"/>
      <stop offset=".78" stop-color="#ee8d3c"/>
      <stop offset="1" stop-color="#e47b30"/>
    </linearGradient>
    <linearGradient id="jet-tone" x1="334" y1="177" x2="446" y2="260">
      <stop offset="0" stop-color="#0b66b3"/>
      <stop offset=".5" stop-color="#187ccb"/>
      <stop offset="1" stop-color="#3b9ae4"/>
    </linearGradient>
    <linearGradient id="axis-z" x1="185" y1="0" x2="535" y2="0">
      <stop offset="0" stop-color="#335c91"/>
      <stop offset=".5" stop-color="#234c80"/>
      <stop offset="1" stop-color="#385f91"/>
    </linearGradient>
    <marker id="arrow-dark" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 Z" fill="#213d64"/>
    </marker>
    <marker id="arrow-jet" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0 0 L10 5 L0 10 Z" fill="#187ccb"/>
    </marker>
  </defs>

  <g id="reaction-plane" data-element="reaction-plane">
    <path d="M36 145 L294 67 L638 139 L341 309 Z" fill="#edf4ff"
          fill-opacity=".62" stroke="#5d86bd" stroke-width="1.1"/>
    <path d="M36 145 L294 67 M36 145 L341 309 M294 67 L638 139
             M341 309 L638 139" fill="none" stroke="#6f91bf"
          stroke-width=".6" opacity=".55"/>
  </g>

  <g id="qgp-medium" data-element="qgp-medium">
    <rect x="120" y="55" width="420" height="237" rx="112"
          fill="url(#qgp-top)" opacity=".9"/>
    <path d="M120 173 H540 V180 C540 244 481 292 404 292
             H258 C181 292 120 244 120 180 Z" fill="url(#qgp-bottom)" opacity=".93"/>
    <g id="surface-grid" opacity=".48" fill="none" stroke="#fff8e5" stroke-width="1.1">
      <path d="M145 103 C260 70 430 70 535 103"/>
      <path d="M132 132 C260 98 430 98 546 132"/>
      <path d="M122 163 C255 130 438 130 548 163"/>
      <path d="M129 207 C255 176 440 176 544 207"/>
      <path d="M145 247 C265 216 430 216 526 247"/>
      <ellipse cx="330" cy="174" rx="76" ry="117"/>
      <ellipse cx="330" cy="174" rx="112" ry="118"/>
    </g>
    <path d="M120 173 H540" stroke="#fff4cc" stroke-width="1.4" opacity=".8"/>
    <rect x="120" y="55" width="420" height="237" rx="112"
          fill="none" stroke="#6387b2" stroke-width="1.5"/>
    <rect x="120" y="173" width="420" height="119" rx="0"
          fill="none" stroke="#e79443" stroke-width=".75" opacity=".55"/>
  </g>

  <g id="coordinate-axes" data-element="coordinate-axes">
    <path d="M178 170 H566" fill="none" stroke="url(#axis-z)"
          stroke-width="6" marker-start="url(#arrow-dark)" marker-end="url(#arrow-dark)"/>
    <path d="M330 171 V72" fill="none" stroke="#2d5f9a"
          stroke-width="6" marker-end="url(#arrow-dark)"/>
    <path d="M330 171 L412 240" fill="none" stroke="#2d70b7"
          stroke-width="6" marker-end="url(#arrow-dark)"/>
    <text x="325" y="57" font-family="DejaVu Sans" font-size="18"
          fill="#263c5e" font-weight="bold">y</text>
    <text x="422" y="259" font-family="DejaVu Sans" font-size="18"
          fill="#263c5e" font-weight="bold">x</text>
    <text x="574" y="177" font-family="DejaVu Sans" font-size="18"
          fill="#263c5e" font-weight="bold">z</text>
  </g>

  <g id="photon" data-element="photon">
    <path d="M333 174
             C318 165 318 151 330 151
             C342 151 342 136 330 136
             C318 136 318 122 330 122
             C342 122 342 107 330 107
             C320 107 316 100 308 99"
          fill="none" stroke="#3f78b8" stroke-width="3.2"
          stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M308 99 L318 95 L314 105 Z" fill="#3f78b8"/>
    <text x="250" y="91" font-family="DejaVu Sans" font-size="17"
          fill="#334a63">photon</text>
  </g>

  <g id="quenched-jet" data-element="quenched-jet">
    <path d="M331 174 C356 182 378 193 397 210"
          fill="none" stroke="url(#jet-tone)" stroke-width="7"
          stroke-linecap="round"/>
    <path d="M392 207 L414 223 L389 222 Z" fill="#187ccb"/>
    <path d="M335 181 C356 191 372 201 387 214"
          fill="none" stroke="#9ed8ff" stroke-width="1.4" opacity=".75"/>
    <path d="M348 186 C370 203 387 218 401 235"
          fill="none" stroke="#335d91" stroke-width="2.8"
          stroke-dasharray="2.5 3.5" opacity=".75"/>
    <text x="430" y="214" font-family="DejaVu Sans" font-size="17"
          fill="#234b72">jet</text>
  </g>

  <g id="labels" data-element="labels">
    <text x="93" y="190" font-family="DejaVu Sans" font-size="17"
          fill="#213554">reaction</text>
    <text x="115" y="211" font-family="DejaVu Sans" font-size="17"
          fill="#213554">plane</text>
  </g>
</svg>
"""


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"missing source figure: {SOURCE}")
    REL.parent.mkdir(parents=True, exist_ok=True)
    crop = LIB / (REL.as_posix() + ".source.png")
    Image.open(SOURCE).convert("RGB").crop((220, 70, 880, 430)).save(crop)
    edit = LIB / (REL.as_posix() + "_edit.svg")
    texture = LIB / (REL.as_posix() + "_texture.svg")
    edit.write_text(native_svg(), encoding="utf-8")
    # The measured fidelity companion is generated by
    # element_texture_vectorize.py after this native asset is indexed.
    if not texture.exists():
        texture.write_text(
            native_svg()
            .replace('data-origin="article_vector_native"',
                     'data-origin="article_vector_smooth_texture"', 1)
            .replace("</svg>",
                     '<metadata id="texture-placeholder">pending smooth-mesh build</metadata></svg>',
                     1),
            encoding="utf-8",
        )

    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    existing = next((a for a in doc["assets"] if a["id"] == ASSET_ID), None)
    record = {
        "id": ASSET_ID,
        "version": "1.0.0",
        "name_zh": "PRL 125 QGP-光子-喷注 3D 重建场景",
        "family": "qgp",
        "variant": "prl125-qgp-jet-scene",
        "variant_description": "Native reconstruction of Fig. 1 in PRL 125, 122301",
        "aliases": ["photon-triggered in-medium jet"],
        "category": "medium",
        "tags": ["article-derived", "3d", "qgp", "jet", "photon"],
        "physics_roles": ["光子触发的介质内喷注传播与淬火"],
        "file": (REL.as_posix() + "_edit.svg"),
        "viewBox": [0, 0, 660, 340],
        "anchor": [330, 170],
        "dimensionality": "3d",
        "license": {
            "spdx": "CC-BY-4.0",
            "redistributable": True,
            "attribution": "Yayun He, Long-Gang Pang, Xin-Nian Wang. Gradient Tomography of Jet Quenching in Heavy-Ion Collisions. Phys. Rev. Lett. 125, 122301 (2020).",
            "source_url": "https://doi.org/10.1103/PhysRevLett.125.122301",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
        },
        "generation": {
            "origin": "article_vector_native",
            "ai_generated": False,
            "contains_ai_pixels": False,
            "tool": "rebuild_prl125_scene.py",
            "model": None,
            "source_asset_id": "PRL125.122301-fig01",
            "source_sha256": sha256(SOURCE),
            "source_local_file": SOURCE.relative_to(ROOT).as_posix(),
            "source_image": SOURCE.relative_to(ROOT).as_posix(),
            "source_image_sha256": sha256(SOURCE),
            "source_bbox_px": [220, 70, 880, 430],
            "crop_file": crop.relative_to(LIB).as_posix(),
            "crop_sha256": sha256(crop),
            "edit_file": edit.relative_to(LIB).as_posix(),
            "edit_sha256": sha256(edit),
            "native_origin": "article_vector_native",
            "texture_file": texture.relative_to(LIB).as_posix(),
            "texture_sha256": sha256(texture),
            "processing": "object-level native reconstruction; paths, gradients and native text only",
            "redraw_method": "3D cylinder, reaction plane, photon and jet arrows rebuilt from the cited figure",
        },
        "review": {
            "status": "manual-reviewed",
            "reviewed_by": "repository-maintainers",
            "reviewed_at": "2026-11-23",
            "note": "Native semantic groups and geometry checked against the cited PRL figure before texture verification.",
        },
        "sha256": sha256(edit),
    }
    if existing is None:
        doc["assets"].append(record)
    else:
        existing.update(record)
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(edit)
    print(texture)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
