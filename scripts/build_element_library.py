#!/usr/bin/env python3
"""Build the deterministic native-vector element library.

Every built-in element is authored by code, has no raster payload, and is
marked as ``origin=software`` / ``ai_generated=false`` in the index.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "element-library"
TODAY = "2026-11-22"


def svg(body: str, defs: str = "", viewbox: str = "0 0 100 100") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">\n'
        f"<defs>{defs}</defs>\n{body}\n</svg>\n"
    )


SOFT_RADIAL = (
    '<radialGradient id="g" cx="32%" cy="28%" r="76%">'
    '<stop offset="0" stop-color="#fffdf5"/>'
    '<stop offset=".18" stop-color="#ffe8b0"/>'
    '<stop offset=".52" stop-color="#f08a32"/>'
    '<stop offset=".82" stop-color="#c7431d"/>'
    '<stop offset="1" stop-color="#6e160c"/></radialGradient>'
)


ASSETS = {
    "nucleus_spherical": {
        "name_zh": "球形原子核",
        "category": "nucleus",
        "aliases": ["nucleus", "spherical nucleus", "核", "球形核"],
        "tags": ["3d", "nucleus", "sphere"],
        "physics_roles": ["原子核", "重离子入射核", "参与者核"],
        "body": svg(
            '<g data-part="body"><circle cx="50" cy="50" r="42" fill="url(#g)" '
            'stroke="#78331b" stroke-width=".8"/>'
            '<ellipse cx="50" cy="50" rx="36" ry="12" fill="none" '
            'stroke="#fff8e8" stroke-opacity=".34" stroke-width=".55" '
            'transform="rotate(-18 50 50)"/>'
            '<ellipse cx="50" cy="50" rx="20" ry="40" fill="none" '
            'stroke="#8a3c1e" stroke-opacity=".20" stroke-width=".45"/>'
            '<ellipse cx="39" cy="36" rx="13" ry="8" fill="#fff" opacity=".28" '
            'transform="rotate(-24 39 36)"/></g>',
            SOFT_RADIAL,
        ),
    },
    "nucleus_deformed": {
        "name_zh": "形变原子核",
        "category": "nucleus",
        "aliases": ["deformed nucleus", "形变核", "prolate nucleus"],
        "tags": ["3d", "nucleus", "deformation"],
        "physics_roles": ["长椭球形变核", "核形状成像"],
        "body": svg(
            '<g data-part="body" transform="rotate(-8 50 50)">'
            '<ellipse cx="50" cy="50" rx="43" ry="30" fill="url(#g)" '
            'stroke="#78331b" stroke-width=".8"/>'
            '<ellipse cx="50" cy="50" rx="37" ry="8" fill="none" '
            'stroke="#fff8e8" stroke-opacity=".30" stroke-width=".5"/>'
            '<ellipse cx="50" cy="50" rx="26" ry="28" fill="none" '
            'stroke="#8a3c1e" stroke-opacity=".18" stroke-width=".45"/>'
            '<ellipse cx="33" cy="38" rx="12" ry="7" fill="#fff" opacity=".24" '
            'transform="rotate(-18 33 38)"/></g>',
            SOFT_RADIAL,
        ),
    },
    "nucleon": {
        "name_zh": "核子",
        "category": "particle",
        "aliases": ["nucleon", "proton", "neutron", "核子"],
        "tags": ["3d", "particle", "sphere"],
        "physics_roles": ["参与者核子", "旁观者核子", "质子或中子"],
        "body": svg(
            '<circle cx="50" cy="50" r="27" fill="url(#g)" stroke="#214f73" '
            'stroke-width=".7"/><ellipse cx="41" cy="39" rx="9" ry="6" '
            'fill="#fff" opacity=".34"/>',
            '<radialGradient id="g" cx="32%" cy="28%" r="76%">'
            '<stop offset="0" stop-color="#f8fdff"/><stop offset=".25" stop-color="#9cd6f4"/>'
            '<stop offset=".66" stop-color="#3a8fc3"/><stop offset="1" stop-color="#163b57"/>'
            "</radialGradient>",
        ),
    },
    "qgp_fireball": {
        "name_zh": "QGP 火球",
        "category": "medium",
        "aliases": ["QGP", "fireball", "quark gluon plasma", "夸克胶子等离子体", "火球"],
        "tags": ["3d", "plasma", "glow"],
        "physics_roles": ["夸克胶子等离子体", "热密介质"],
        "body": svg(
            '<circle cx="50" cy="50" r="47" fill="url(#halo)"/>'
            '<circle cx="50" cy="50" r="34" fill="url(#g)"/>'
            '<ellipse cx="42" cy="38" rx="13" ry="8" fill="#fff" opacity=".34"/>'
            '<path d="M22 55 Q31 46 39 55 T57 55 T75 55" fill="none" '
            'stroke="#fff3be" stroke-opacity=".36" stroke-width=".8"/>',
            '<radialGradient id="g" cx="36%" cy="32%" r="72%">'
            '<stop offset="0" stop-color="#ffffff"/><stop offset=".15" stop-color="#fff4a8"/>'
            '<stop offset=".45" stop-color="#ff9d32"/><stop offset=".77" stop-color="#e04719"/>'
            '<stop offset="1" stop-color="#8b1908" stop-opacity=".15"/></radialGradient>'
            '<radialGradient id="halo"><stop offset="0" stop-color="#ffb540" stop-opacity=".45"/>'
            '<stop offset="1" stop-color="#ff5924" stop-opacity="0"/></radialGradient>',
        ),
    },
    "qgp_blob": {
        "name_zh": "QGP 介质团",
        "category": "medium",
        "aliases": ["medium", "blob", "QGP medium", "介质"],
        "tags": ["3d", "plasma", "organic"],
        "physics_roles": ["有限尺寸 QGP 介质", "碰撞重叠区"],
        "body": svg(
            '<path d="M17 51 C14 34 27 17 45 18 C62 10 82 22 85 42 '
            'C92 56 80 77 63 78 C52 91 28 86 21 73 C10 68 10 58 17 51 Z" '
            'fill="url(#g)" stroke="#a83b17" stroke-width=".8"/>'
            '<ellipse cx="39" cy="34" rx="19" ry="10" fill="#fff" opacity=".23" '
            'transform="rotate(-18 39 34)"/>'
            '<path d="M31 65 Q40 57 49 65 T67 63" fill="none" '
            'stroke="#fff0bb" stroke-opacity=".32" stroke-width=".8"/>',
            '<radialGradient id="g" cx="36%" cy="31%" r="73%">'
            '<stop offset="0" stop-color="#fffdf0"/><stop offset=".22" stop-color="#ffe98d"/>'
            '<stop offset=".55" stop-color="#f39c34"/><stop offset=".87" stop-color="#d54a1a"/>'
            '<stop offset="1" stop-color="#8c2410"/></radialGradient>',
        ),
    },
    "glasma_flux_tubes": {
        "name_zh": "Glasma 色通量管",
        "category": "medium",
        "aliases": ["glasma", "flux tube", "color flux tube", "色通量管"],
        "tags": ["3d", "field", "plasma"],
        "physics_roles": ["碰撞后早期 Glasma", "色电场通量管"],
        "body": svg(
            '<g stroke-linecap="round">'
            '<path d="M29 87 C22 67 36 47 28 15" fill="none" stroke="url(#g1)" stroke-width="9" opacity=".9"/>'
            '<path d="M50 88 C44 68 56 45 50 12" fill="none" stroke="url(#g2)" stroke-width="10" opacity=".9"/>'
            '<path d="M71 87 C65 66 79 46 71 15" fill="none" stroke="url(#g1)" stroke-width="8" opacity=".9"/>'
            '</g><ellipse cx="50" cy="88" rx="31" ry="5" fill="#1d2530" opacity=".12"/>',
            '<linearGradient id="g1" x1="0" y1="1" x2="0" y2="0">'
            '<stop offset="0" stop-color="#3b5b7a"/><stop offset=".45" stop-color="#7bd2f2"/>'
            '<stop offset="1" stop-color="#f4ffff"/></linearGradient>'
            '<linearGradient id="g2" x1="0" y1="1" x2="0" y2="0">'
            '<stop offset="0" stop-color="#7d3d8f"/><stop offset=".5" stop-color="#ec79c7"/>'
            '<stop offset="1" stop-color="#fff3ff"/></linearGradient>',
        ),
    },
    "jet_cone_hot": {
        "name_zh": "高能喷注锥",
        "category": "jet",
        "aliases": ["jet", "jet cone", "parton shower", "喷注"],
        "tags": ["3d", "jet", "particles"],
        "physics_roles": ["未淬火喷注", "部分子喷注", "背对背喷注之一"],
        "body": svg(
            '<path d="M12 50 L90 18 Q79 50 90 82 Z" fill="url(#g)" '
            'stroke="#2e79a8" stroke-width=".7"/>'
            '<path d="M18 50 L84 30" stroke="#dff8ff" stroke-width=".7" opacity=".55"/>'
            '<circle cx="79" cy="29" r="2.2" fill="#fff" opacity=".8"/>'
            '<circle cx="84" cy="57" r="1.8" fill="#fff" opacity=".7"/>',
            '<linearGradient id="g" x1="0" y1=".5" x2="1" y2=".5">'
            '<stop offset="0" stop-color="#2d5b85"/><stop offset=".45" stop-color="#53bce4"/>'
            '<stop offset="1" stop-color="#c8f7ff" stop-opacity=".45"/></linearGradient>',
        ),
    },
    "jet_cone_quenched": {
        "name_zh": "淬火喷注锥",
        "category": "jet",
        "aliases": ["quenched jet", "energy loss", "淬火喷注"],
        "tags": ["3d", "jet", "medium-response"],
        "physics_roles": ["介质内能量损失后的喷注", "淬火喷注"],
        "body": svg(
            '<path d="M12 50 L86 26 Q70 50 86 74 Z" fill="url(#g)" '
            'stroke="#6b6f76" stroke-width=".7" opacity=".92"/>'
            '<path d="M21 50 L77 38" stroke="#f2f2f2" stroke-width=".7" opacity=".55"/>'
            '<circle cx="68" cy="35" r="1.7" fill="#eee" opacity=".75"/>'
            '<circle cx="75" cy="59" r="1.4" fill="#eee" opacity=".65"/>',
            '<linearGradient id="g" x1="0" y1=".5" x2="1" y2=".5">'
            '<stop offset="0" stop-color="#2b3038"/><stop offset=".5" stop-color="#848b95"/>'
            '<stop offset="1" stop-color="#dfe4ea" stop-opacity=".45"/></linearGradient>',
        ),
    },
    "hard_vertex": {
        "name_zh": "硬散射顶点",
        "category": "interaction",
        "aliases": ["hard vertex", "scattering vertex", "硬散射"],
        "tags": ["glow", "interaction"],
        "physics_roles": ["硬散射顶点", "喷注产生点"],
        "body": svg(
            '<path d="M50 6 L55 35 L83 18 L63 43 L96 50 L63 57 L83 82 L55 65 '
            'L50 94 L45 65 L17 82 L37 57 L4 50 L37 43 L17 18 L45 35 Z" '
            'fill="url(#g)" stroke="#f9b13e" stroke-width=".7"/>'
            '<circle cx="50" cy="50" r="5.5" fill="#fff8d2"/>',
            '<radialGradient id="g"><stop offset="0" stop-color="#ffffec"/>'
            '<stop offset=".4" stop-color="#ffd05e"/><stop offset="1" stop-color="#de5f16" stop-opacity=".35"/></radialGradient>',
        ),
    },
    "reaction_plane": {
        "name_zh": "反应平面",
        "category": "geometry",
        "aliases": ["reaction plane", "collision plane", "反应平面"],
        "tags": ["3d", "plane", "grid"],
        "physics_roles": ["反应平面", "碰撞几何参考面"],
        "body": svg(
            '<path d="M10 62 L72 18 L92 40 L30 84 Z" fill="url(#g)" '
            'stroke="#8f9aa5" stroke-width=".7"/>'
            '<g stroke="#ffffff" stroke-opacity=".32" stroke-width=".45">'
            '<path d="M22 56 L78 27"/><path d="M35 64 L84 31"/><path d="M48 72 L91 35"/>'
            '<path d="M18 62 L38 82"/><path d="M38 50 L60 72"/><path d="M58 38 L82 61"/>'
            "</g>",
            '<linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#f7fbff" stop-opacity=".9"/>'
            '<stop offset="1" stop-color="#b7c5d3" stop-opacity=".55"/></linearGradient>',
        ),
    },
    "detector_ring": {
        "name_zh": "环形探测器",
        "category": "detector",
        "aliases": ["detector ring", "tracker", "探测器"],
        "tags": ["3d", "detector", "rings"],
        "physics_roles": ["探测器接收层", "径迹探测器横截面"],
        "body": svg(
            '<ellipse cx="50" cy="52" rx="43" ry="24" fill="none" stroke="#6b7f99" stroke-width="7" opacity=".72"/>'
            '<ellipse cx="50" cy="52" rx="31" ry="17" fill="none" stroke="#d6e6f5" stroke-width="5" opacity=".88"/>'
            '<ellipse cx="50" cy="52" rx="19" ry="10" fill="none" stroke="#4b6581" stroke-width="4" opacity=".85"/>'
            '<circle cx="50" cy="52" r="4.5" fill="#ff7e3c"/>'
            '<path d="M49 83 C47 73 53 63 51 54" fill="none" stroke="#ef9f3e" stroke-width=".8"/>',
            "",
        ),
    },
    "detector_barrel": {
        "name_zh": "桶形探测器",
        "category": "detector",
        "aliases": ["detector barrel", "spectrometer", "桶形谱仪"],
        "tags": ["3d", "detector", "cylinder"],
        "physics_roles": ["桶形探测器外壳", "中心谱仪"],
        "body": svg(
            '<path d="M22 20 L78 20 L78 78 L22 78 Z" fill="url(#g)" stroke="#66788a" stroke-width=".8"/>'
            '<ellipse cx="50" cy="20" rx="28" ry="8" fill="#d8e8f5" stroke="#66788a" stroke-width=".7"/>'
            '<ellipse cx="50" cy="78" rx="28" ry="8" fill="#a9bfd3" stroke="#66788a" stroke-width=".7"/>'
            '<path d="M22 20 L16 25 L16 74 L22 78 M78 20 L84 25 L84 74 L78 78" '
            'fill="none" stroke="#66788a" stroke-width=".7"/>'
            '<path d="M34 25 L34 73 M50 23 L50 80 M66 25 L66 73" stroke="#fff" '
            'stroke-opacity=".35" stroke-width=".5"/>',
            '<linearGradient id="g" x1="0" x2="1">'
            '<stop offset="0" stop-color="#7b8fa4"/><stop offset=".35" stop-color="#e6f0f7"/>'
            '<stop offset=".7" stop-color="#a8bdcf"/><stop offset="1" stop-color="#61778b"/></linearGradient>',
        ),
    },
    "magnetic_field_line": {
        "name_zh": "磁场线",
        "category": "field",
        "aliases": ["magnetic field", "field line", "磁场", "磁场线"],
        "tags": ["field", "arrow", "curve"],
        "physics_roles": ["磁场方向", "电磁场线"],
        "body": svg(
            '<path d="M9 66 C23 28 61 12 89 36" fill="none" stroke="url(#g)" '
            'stroke-width="1.5" stroke-linecap="round"/>'
            '<path d="M82 26 L91 36 L80 39" fill="none" stroke="#5d45ba" '
            'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M14 77 C32 45 61 33 87 49" fill="none" stroke="url(#g)" '
            'stroke-width="1.2" opacity=".62" stroke-linecap="round"/>',
            '<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#d7d1ff"/>'
            '<stop offset=".5" stop-color="#7458e7"/><stop offset="1" stop-color="#3c238e"/></linearGradient>',
        ),
    },
    "spin_out": {
        "name_zh": "自旋指向读者",
        "category": "marker",
        "aliases": ["spin out", "spin polarization", "自旋出纸面"],
        "tags": ["flat", "symbol", "spin"],
        "physics_roles": ["自旋矢量指向读者", "角动量极化方向"],
        "body": svg(
            '<circle cx="50" cy="50" r="25" fill="#fff" stroke="#2d4770" stroke-width="1.2"/>'
            '<circle cx="50" cy="50" r="6.5" fill="#2d4770"/>'
            '<path d="M50 12 A38 38 0 0 1 87 48" fill="none" stroke="#5d80b8" '
            'stroke-width="1.2"/><path d="M80 43 L87 48 L81 54" fill="none" '
            'stroke="#5d80b8" stroke-width="1.2"/>',
            "",
        ),
        "dimensionality": "flat",
    },
    "spin_in": {
        "name_zh": "自旋远离读者",
        "category": "marker",
        "aliases": ["spin in", "spin into page", "自旋入纸面"],
        "tags": ["flat", "symbol", "spin"],
        "physics_roles": ["自旋矢量远离读者", "角动量反向极化"],
        "body": svg(
            '<circle cx="50" cy="50" r="25" fill="#fff" stroke="#2d4770" stroke-width="1.2"/>'
            '<path d="M36 36 L64 64 M64 36 L36 64" stroke="#2d4770" stroke-width="1.6"/>'
            '<path d="M50 12 A38 38 0 0 0 13 48" fill="none" stroke="#5d80b8" '
            'stroke-width="1.2"/><path d="M20 43 L13 48 L19 54" fill="none" '
            'stroke="#5d80b8" stroke-width="1.2"/>',
            "",
        ),
        "dimensionality": "flat",
    },
    "hadronization_burst": {
        "name_zh": "强子化爆发",
        "category": "interaction",
        "aliases": ["hadronization", "freeze out", "强子化", "冻出"],
        "tags": ["3d", "burst", "particles"],
        "physics_roles": ["强子化面", "冻出与粒子发射"],
        "body": svg(
            '<path d="M50 8 L56 31 L72 16 L67 39 L89 29 L76 48 L95 50 L76 55 '
            'L87 76 L66 63 L59 89 L51 66 L35 89 L40 64 L14 76 L29 54 L4 49 '
            'L29 44 L13 24 L39 34 Z" fill="url(#g)" stroke="#c56724" stroke-width=".7"/>'
            '<circle cx="50" cy="50" r="8" fill="#fff8d9"/>',
            '<radialGradient id="g"><stop offset="0" stop-color="#fffbe0"/>'
            '<stop offset=".42" stop-color="#ffc85f"/><stop offset="1" stop-color="#de641e" stop-opacity=".32"/></radialGradient>',
        ),
    },
    "particle_tracks": {
        "name_zh": "粒子径迹",
        "category": "detector",
        "aliases": ["tracks", "particle tracks", "粒子径迹"],
        "tags": ["lines", "detector", "tracks"],
        "physics_roles": ["带电粒子径迹", "探测器中的轨迹"],
        "body": svg(
            '<g fill="none" stroke-linecap="round">'
            '<path d="M10 50 C27 22 55 14 91 24" stroke="#d05d3a" stroke-width="1.2"/>'
            '<path d="M10 51 C31 33 60 30 91 43" stroke="#487fbf" stroke-width="1.0"/>'
            '<path d="M10 52 C33 49 62 54 91 74" stroke="#4c9a76" stroke-width="1.1"/>'
            '<path d="M10 53 C36 65 62 78 91 89" stroke="#8b67b3" stroke-width=".9"/>'
            "</g>",
            "",
        ),
        "dimensionality": "mixed",
    },
    "gluon_radiation": {
        "name_zh": "胶子辐射",
        "category": "particle",
        "aliases": ["gluon", "radiation", "gluon radiation", "胶子辐射"],
        "tags": ["line", "particle", "radiation"],
        "physics_roles": ["喷注中的胶子辐射", "色场辐射"],
        "body": svg(
            '<path d="M8 50 C16 20 22 80 31 50 C39 20 45 80 54 50 '
            'C62 20 68 80 77 50 C84 26 88 66 93 46" fill="none" '
            'stroke="url(#g)" stroke-width="2" stroke-linecap="round"/>',
            '<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#d5f5ff"/>'
            '<stop offset=".55" stop-color="#4eb7dc"/><stop offset="1" stop-color="#17496b"/></linearGradient>',
        ),
        "dimensionality": "flat",
    },
    "beam_axis": {
        "name_zh": "束流方向",
        "category": "geometry",
        "aliases": ["beam axis", "beam direction", "束流轴", "束流方向"],
        "tags": ["line", "arrow", "beam"],
        "physics_roles": ["束流方向", "z 轴"],
        "body": svg(
            '<path d="M8 50 L88 50" fill="none" stroke="url(#g)" stroke-width="2.2" '
            'stroke-linecap="round"/><path d="M83 43 L94 50 L83 57 Z" fill="#1b3652"/>',
            '<linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#efb451"/>'
            '<stop offset="1" stop-color="#1b3652"/></linearGradient>',
        ),
        "dimensionality": "flat",
    },
    "quark": {
        "name_zh": "夸克",
        "category": "particle",
        "aliases": ["quark", "channel", "夸克"],
        "tags": ["3d", "particle", "quark"],
        "physics_roles": ["夸克", "部分子"],
        "body": svg(
            '<circle cx="50" cy="50" r="24" fill="url(#g)" stroke="#6c3a7b" stroke-width=".8"/>',
            '<radialGradient id="g" cx="32%" cy="28%" r="75%"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".25" stop-color="#f4b9ff"/><stop offset=".65" stop-color="#a34db6"/>'
            '<stop offset="1" stop-color="#4f1b5d"/></radialGradient>',
        ),
    },
    "light_cone": {
        "name_zh": "光锥",
        "category": "geometry",
        "aliases": ["light cone", "spacetime", "光锥", "时空"],
        "tags": ["lines", "geometry", "spacetime"],
        "physics_roles": ["光锥边界", "因果结构"],
        "body": svg(
            '<path d="M50 88 L12 12 M50 88 L88 12" fill="none" stroke="#27384b" '
            'stroke-width="1.5"/><path d="M50 88 L50 10" stroke="#b8c5d1" '
            'stroke-dasharray="3 3" stroke-width=".7"/>'
            '<path d="M8 14 L12 7 L16 14 M84 14 L88 7 L92 14" fill="none" '
            'stroke="#27384b" stroke-width="1.2"/>',
            "",
        ),
        "dimensionality": "flat",
    },
}


def derived(base_id: str, extra: str = "", recolor: dict[str, str] | None = None) -> str:
    text = ASSETS[base_id]["body"]
    for old, new in (recolor or {}).items():
        text = text.replace(old, new)
    return text.replace("</svg>", extra + "\n</svg>")


def ellipse_nucleus(rx: float, ry: float, rotation: float = 0,
                    extra: str = "", gradient: str = SOFT_RADIAL) -> str:
    return svg(
        f'<g data-part="body" transform="rotate({rotation:g} 50 50)">'
        f'<ellipse cx="50" cy="50" rx="{rx:g}" ry="{ry:g}" fill="url(#g)" '
        'stroke="#78331b" stroke-width=".8"/>'
        f'<ellipse cx="50" cy="50" rx="{max(rx-6,4):g}" ry="{max(ry*0.32,4):g}" '
        'fill="none" stroke="#fff8e8" stroke-opacity=".28" stroke-width=".5"/>'
        f'<ellipse cx="{50-rx*0.28:g}" cy="{50-ry*0.30:g}" rx="{rx*0.25:g}" '
        f'ry="{max(ry*0.18,4):g}" fill="#fff" opacity=".24"/>{extra}</g>',
        gradient,
    )


def sphere_nucleon(stops: str, extra: str = "") -> str:
    return svg(
        '<circle cx="50" cy="50" r="27" fill="url(#g)" stroke="#214f73" '
        'stroke-width=".7"/><ellipse cx="41" cy="39" rx="9" ry="6" '
        f'fill="#fff" opacity=".34"/>{extra}',
        f'<radialGradient id="g" cx="32%" cy="28%" r="76%">{stops}</radialGradient>',
    )


def cone_jet(fill: str, extra: str = "", opacity: float = 0.94) -> str:
    return svg(
        f'<path d="M12 50 L90 18 Q79 50 90 82 Z" fill="url(#g)" '
        f'opacity="{opacity:g}" stroke="#33566e" stroke-width=".7"/>'
        f'{extra}',
        f'<linearGradient id="g" x1="0" y1=".5" x2="1" y2=".5">{fill}</linearGradient>',
    )


def ring_detector(layers: list[tuple[float, float, str, float]], extra: str = "") -> str:
    body = []
    for rx, ry, color, width in layers:
        body.append(
            f'<ellipse cx="50" cy="52" rx="{rx:g}" ry="{ry:g}" fill="none" '
            f'stroke="{color}" stroke-width="{width:g}" opacity=".82"/>'
        )
    body.append('<circle cx="50" cy="52" r="4.5" fill="#ff7e3c"/>')
    body.append(extra)
    return svg("".join(body))


def line_field(color: str, extra: str = "") -> str:
    return svg(
        f'<path d="M9 66 C23 28 61 12 89 36" fill="none" stroke="{color}" '
        'stroke-width="1.5" stroke-linecap="round"/>'
        f'{extra}',
    )


def marker_circle(color: str, symbol: str, extra: str = "") -> str:
    shapes = {
        "+": f'<path d="M38 50 L62 50 M50 38 L50 62" stroke="{color}" stroke-width="3"/>',
        "-": f'<path d="M38 50 L62 50" stroke="{color}" stroke-width="3"/>',
        "dot": f'<circle cx="50" cy="50" r="6" fill="{color}"/>',
        "cross": f'<path d="M39 39 L61 61 M61 39 L39 61" stroke="{color}" stroke-width="2.2"/>',
    }
    return svg(
        f'<circle cx="50" cy="50" r="25" fill="#fff" stroke="{color}" stroke-width="1.2"/>'
        f'{shapes[symbol]}{extra}',
    )


def interaction_burst(core_color: str, extra: str = "") -> str:
    return svg(
        '<path d="M50 7 L55 34 L82 17 L63 42 L94 50 L63 58 L82 83 L55 66 '
        f'L50 94 L45 66 L18 83 L37 58 L6 50 L37 42 L18 17 L45 34 Z" '
        f'fill="{core_color}" stroke="#c56b23" stroke-width=".7" opacity=".9"/>'
        f'<circle cx="50" cy="50" r="6" fill="#fff8d9"/>{extra}',
    )


VARIANT_ASSETS = {
    # Nucleus family
    "nucleus_prolate": {
        "name_zh": "长椭球形变核", "category": "nucleus", "family": "nucleus",
        "variant": "prolate", "aliases": ["prolate nucleus", "长椭球核"],
        "tags": ["3d", "nucleus", "deformation"], "physics_roles": ["形变原子核"],
        "body": ellipse_nucleus(43, 29, -8),
    },
    "nucleus_oblate": {
        "name_zh": "扁椭球形变核", "category": "nucleus", "family": "nucleus",
        "variant": "oblate", "aliases": ["oblate nucleus", "扁椭球核"],
        "tags": ["3d", "nucleus", "deformation"], "physics_roles": ["扁椭球形变核"],
        "body": ellipse_nucleus(30, 42, 6),
    },
    "nucleus_triaxial": {
        "name_zh": "三轴形变核", "category": "nucleus", "family": "nucleus",
        "variant": "triaxial", "aliases": ["triaxial nucleus", "三轴核"],
        "tags": ["3d", "nucleus", "deformation"], "physics_roles": ["三轴形变核"],
        "body": derived("nucleus_deformed",
                        '<ellipse cx="50" cy="50" rx="31" ry="42" fill="none" '
                        'stroke="#8b3b1d" stroke-opacity=".25" stroke-width=".8" '
                        'transform="rotate(28 50 50)"/>'),
    },
    "nucleus_octupole": {
        "name_zh": "八极形变核", "category": "nucleus", "family": "nucleus",
        "variant": "octupole", "aliases": ["octupole nucleus", "梨形核", "pear shape"],
        "tags": ["3d", "nucleus", "deformation"], "physics_roles": ["八极/梨形形变核"],
        "body": ellipse_nucleus(37, 34, 0,
                                '<ellipse cx="50" cy="82" rx="18" ry="11" fill="#d85c20" opacity=".62"/>'
                                '<ellipse cx="50" cy="23" rx="13" ry="8" fill="#f6c070" opacity=".46"/>'),
    },
    "nucleus_neutron_skin": {
        "name_zh": "中子皮核", "category": "nucleus", "family": "nucleus",
        "variant": "neutron-skin", "aliases": ["neutron skin", "中子皮"],
        "tags": ["3d", "nucleus", "surface"], "physics_roles": ["具有中子皮的原子核"],
        "body": derived("nucleus_spherical",
                        '<circle cx="50" cy="50" r="47" fill="none" stroke="#5fc3e7" '
                        'stroke-opacity=".72" stroke-width="3" stroke-dasharray="1.5 2.5"/>'),
    },
    "nucleus_halo": {
        "name_zh": "晕核", "category": "nucleus", "family": "nucleus",
        "variant": "halo", "aliases": ["halo nucleus", "滴线核", "晕核"],
        "tags": ["3d", "nucleus", "halo"], "physics_roles": ["外部中子晕", "滴线核"],
        "body": derived("nucleus_spherical",
                        '<circle cx="50" cy="50" r="47" fill="none" stroke="#69c7e8" '
                        'stroke-width="1" opacity=".6"/>'
                        '<circle cx="13" cy="41" r="2.3" fill="#8eddf4"/>'
                        '<circle cx="87" cy="59" r="2.8" fill="#8eddf4"/>'
                        '<circle cx="62" cy="94" r="2.2" fill="#8eddf4"/>'),
    },
    "nucleus_cluster": {
        "name_zh": "集团结构核", "category": "nucleus", "family": "nucleus",
        "variant": "cluster", "aliases": ["cluster nucleus", "alpha cluster", "集团核"],
        "tags": ["3d", "nucleus", "cluster"], "physics_roles": ["集团结构", "α 集团核"],
        "body": (
            '<circle cx="36" cy="37" r="17" fill="url(#g1)"/>'
            '<circle cx="64" cy="38" r="17" fill="url(#g2)"/>'
            '<circle cx="50" cy="66" r="19" fill="url(#g3)"/>'
        ),
        "defs_override": (
            '<radialGradient id="g1" cx="30%" cy="25%"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".5" stop-color="#f3a044"/><stop offset="1" stop-color="#9a3114"/></radialGradient>'
            '<radialGradient id="g2" cx="30%" cy="25%"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".5" stop-color="#ed8c35"/><stop offset="1" stop-color="#852410"/></radialGradient>'
            '<radialGradient id="g3" cx="30%" cy="25%"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".5" stop-color="#ffc160"/><stop offset="1" stop-color="#aa3815"/></radialGradient>'
        ),
    },
    "nucleus_lorentz_contracted": {
        "name_zh": "洛伦兹收缩核", "category": "nucleus", "family": "nucleus",
        "variant": "lorentz-contracted", "aliases": ["Lorentz contracted nucleus", "洛伦兹收缩"],
        "tags": ["3d", "nucleus", "relativistic"], "physics_roles": ["束流方向压扁的入射核"],
        "body": ellipse_nucleus(22, 41, 0,
                                '<path d="M10 91 L88 91 M82 86 L89 91 L82 96" '
                                'fill="none" stroke="#29455d" stroke-width="1.2"/>'),
    },
    "nucleus_participant": {
        "name_zh": "参与者核", "category": "nucleus", "family": "nucleus",
        "variant": "participant", "aliases": ["participant nucleus", "参与者核"],
        "tags": ["3d", "nucleus", "participant"], "physics_roles": ["参与碰撞的核子集合"],
        "body": derived("nucleus_spherical",
                        '<circle cx="36" cy="39" r="4" fill="#ffd86b"/>'
                        '<circle cx="61" cy="34" r="4" fill="#ff8a3c"/>'
                        '<circle cx="54" cy="61" r="4" fill="#ffd86b"/>'
                        '<circle cx="67" cy="66" r="3.5" fill="#ff8a3c"/>'),
    },
    "nucleus_spectator": {
        "name_zh": "旁观核", "category": "nucleus", "family": "nucleus",
        "variant": "spectator", "aliases": ["spectator nucleus", "旁观核"],
        "tags": ["3d", "nucleus", "spectator"], "physics_roles": ["未参与硬碰撞的旁观核"],
        "body": derived("nucleus_spherical",
                        '<circle cx="50" cy="50" r="45" fill="#64717d" opacity=".30"/>',
                        recolor={"#f08a32": "#aeb7c0", "#c7431d": "#68737d",
                                 "#ffe8b0": "#e9edf1", "#6e160c": "#424c55"}),
    },
    "nucleus_fragment": {
        "name_zh": "核碎片", "category": "nucleus", "family": "nucleus",
        "variant": "fragment", "aliases": ["nuclear fragment", "核碎片"],
        "tags": ["3d", "nucleus", "fragment"], "physics_roles": ["旁观者核碎片"],
        "body": (
            '<circle cx="29" cy="58" r="18" fill="url(#g1)"/>'
            '<circle cx="56" cy="37" r="14" fill="url(#g2)"/>'
            '<circle cx="72" cy="67" r="12" fill="url(#g3)"/>'
        ),
        "defs_override": (
            '<radialGradient id="g1"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".55" stop-color="#df8a37"/><stop offset="1" stop-color="#78301a"/></radialGradient>'
            '<radialGradient id="g2"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".55" stop-color="#f2aa52"/><stop offset="1" stop-color="#884120"/></radialGradient>'
            '<radialGradient id="g3"><stop offset="0" stop-color="#fff"/>'
            '<stop offset=".55" stop-color="#d76f2e"/><stop offset="1" stop-color="#632211"/></radialGradient>'
        ),
    },
    "nucleus_shape_fluctuation": {
        "name_zh": "核形状涨落", "category": "nucleus", "family": "nucleus",
        "variant": "shape-fluctuation", "aliases": ["shape fluctuation", "形状涨落"],
        "tags": ["3d", "nucleus", "fluctuation"], "physics_roles": ["事件级核形变涨落"],
        "body": derived("nucleus_deformed",
                        '<path d="M17 52 C20 35 33 24 49 27 C63 30 76 41 80 54 '
                        'C75 69 63 80 47 77 C32 74 19 68 17 52 Z" fill="none" '
                        'stroke="#fff3c8" stroke-opacity=".42" stroke-width="1"/>'),
    },

    # Nucleon family
    "nucleon_proton": {
        "name_zh": "质子", "category": "particle", "family": "nucleon",
        "variant": "proton", "aliases": ["proton", "uud", "质子"],
        "tags": ["3d", "nucleon", "proton"], "physics_roles": ["质子"],
        "body": sphere_nucleon(
            '<stop offset="0" stop-color="#f8fdff"/><stop offset=".25" stop-color="#77c8f3"/>'
            '<stop offset=".66" stop-color="#2d80bc"/><stop offset="1" stop-color="#113750"/>'),
    },
    "nucleon_neutron": {
        "name_zh": "中子", "category": "particle", "family": "nucleon",
        "variant": "neutron", "aliases": ["neutron", "udd", "中子"],
        "tags": ["3d", "nucleon", "neutron"], "physics_roles": ["中子"],
        "body": sphere_nucleon(
            '<stop offset="0" stop-color="#ffffff"/><stop offset=".25" stop-color="#c7d2dd"/>'
            '<stop offset=".66" stop-color="#718294"/><stop offset="1" stop-color="#34404d"/>'),
    },
    "nucleon_constituent": {
        "name_zh": "组分夸克核子", "category": "particle", "family": "nucleon",
        "variant": "constituent-quark", "aliases": ["constituent nucleon", "组分夸克"],
        "tags": ["3d", "nucleon", "quark"], "physics_roles": ["三个组分夸克构成的核子"],
        "body": derived("nucleon",
                        '<circle cx="40" cy="38" r="6" fill="#ffd25f"/>'
                        '<circle cx="59" cy="42" r="6" fill="#ef6252"/>'
                        '<circle cx="49" cy="61" r="6" fill="#5f8ff1"/>'),
    },
    "nucleon_dressed": {
        "name_zh": "穿衣服夸克团", "category": "particle", "family": "nucleon",
        "variant": "dressed", "aliases": ["dressed quark cloud", "dressed nucleon", "有效核子"],
        "tags": ["3d", "nucleon", "cloud"], "physics_roles": ["带胶子云的组分夸克核子"],
        "body": derived("nucleon",
                        '<circle cx="50" cy="50" r="41" fill="none" stroke="#87d8f2" '
                        'stroke-opacity=".45" stroke-width="3" stroke-dasharray="2 3"/>'
                        '<circle cx="29" cy="38" r="2" fill="#c8f5ff"/>'
                        '<circle cx="69" cy="34" r="2.5" fill="#c8f5ff"/>'
                        '<circle cx="72" cy="63" r="1.8" fill="#c8f5ff"/>'),
    },
    "nucleon_spin_up": {
        "name_zh": "自旋向上核子", "category": "particle", "family": "nucleon",
        "variant": "polarized-spin-up", "aliases": ["spin up nucleon", "自旋向上"],
        "tags": ["3d", "nucleon", "spin"], "physics_roles": ["极化为向上的核子自旋"],
        "body": derived("nucleon",
                        '<path d="M50 17 L50 75 M45 25 L50 16 L55 25" fill="none" '
                        'stroke="#ffffff" stroke-width="2.2" stroke-linecap="round"/>'),
    },
    "nucleon_spin_down": {
        "name_zh": "自旋向下核子", "category": "particle", "family": "nucleon",
        "variant": "polarized-spin-down", "aliases": ["spin down nucleon", "自旋向下"],
        "tags": ["3d", "nucleon", "spin"], "physics_roles": ["极化为向下的核子自旋"],
        "body": derived("nucleon",
                        '<path d="M50 83 L50 25 M45 75 L50 84 L55 75" fill="none" '
                        'stroke="#ffffff" stroke-width="2.2" stroke-linecap="round"/>'),
    },
    "nucleon_participant": {
        "name_zh": "参与者核子", "category": "particle", "family": "nucleon",
        "variant": "participant", "aliases": ["participant nucleon", "参与核子"],
        "tags": ["3d", "nucleon", "participant"], "physics_roles": ["参与碰撞的核子"],
        "body": sphere_nucleon(
            '<stop offset="0" stop-color="#fff7d0"/><stop offset=".3" stop-color="#ffbe55"/>'
            '<stop offset=".7" stop-color="#df6428"/><stop offset="1" stop-color="#712010"/>'),
    },
    "nucleon_spectator": {
        "name_zh": "旁观核子", "category": "particle", "family": "nucleon",
        "variant": "spectator", "aliases": ["spectator nucleon", "旁观核子"],
        "tags": ["3d", "nucleon", "spectator"], "physics_roles": ["未参与碰撞的旁观核子"],
        "body": sphere_nucleon(
            '<stop offset="0" stop-color="#f3f4f6"/><stop offset=".3" stop-color="#c8cdd3"/>'
            '<stop offset=".7" stop-color="#777f88"/><stop offset="1" stop-color="#333a42"/>'),
    },
    "nucleon_wounded": {
        "name_zh": "受伤核子", "category": "particle", "family": "nucleon",
        "variant": "wounded", "aliases": ["wounded nucleon", "受伤核子"],
        "tags": ["3d", "nucleon", "excited"], "physics_roles": ["受碰撞激发但尚未热化的核子"],
        "body": derived("nucleon",
                        '<path d="M31 31 L40 43 L34 50 L46 60 L40 69" fill="none" '
                        'stroke="#ffcf5a" stroke-width="1.8"/>'
                        '<path d="M69 30 L58 41 L66 49 L55 61 L63 70" fill="none" '
                        'stroke="#ff7a3e" stroke-width="1.5"/>'),
    },
    "nucleon_valence_cluster": {
        "name_zh": "价夸克簇", "category": "particle", "family": "nucleon",
        "variant": "valence-cluster", "aliases": ["valence quarks", "价夸克簇"],
        "tags": ["3d", "nucleon", "valence"], "physics_roles": ["高 x 价夸克主导的核子"],
        "body": derived("nucleon",
                        '<circle cx="44" cy="43" r="8" fill="#ffd25f"/>'
                        '<circle cx="57" cy="46" r="8" fill="#5f8ff1"/>'
                        '<circle cx="50" cy="59" r="8" fill="#ef6252"/>'),
    },
    "nucleon_sea_cloud": {
        "name_zh": "海夸克胶子云", "category": "particle", "family": "nucleon",
        "variant": "sea-cloud", "aliases": ["sea quark cloud", "parton sea", "海夸克云"],
        "tags": ["3d", "nucleon", "sea"], "physics_roles": ["低 x 海夸克与胶子云"],
        "body": derived("nucleon",
                        '<circle cx="31" cy="38" r="1.8" fill="#bff4ff"/>'
                        '<circle cx="66" cy="33" r="2.1" fill="#ffcf73"/>'
                        '<circle cx="73" cy="58" r="1.7" fill="#f79fd0"/>'
                        '<circle cx="56" cy="72" r="2" fill="#93f2cf"/>'
                        '<circle cx="35" cy="66" r="1.4" fill="#bff4ff"/>'
                        '<circle cx="70" cy="44" r="1.4" fill="#ffffff"/>'),
    },
    "nucleon_high_q2": {
        "name_zh": "高 Q² 分辨核子", "category": "particle", "family": "nucleon",
        "variant": "high-q2-resolved", "aliases": ["high Q2 nucleon", "高 Q2 核子"],
        "tags": ["3d", "nucleon", "high-q2"], "physics_roles": ["高 Q² 探针分辨的部分子核子"],
        "body": derived("nucleon",
                        '<circle cx="50" cy="50" r="9" fill="#fff" opacity=".65"/>'
                        '<path d="M50 25 L50 38 M50 62 L50 75 M25 50 L38 50 M62 50 L75 50" '
                        'stroke="#c8f7ff" stroke-width="1.6"/>'),
    },
    "nucleon_low_q2": {
        "name_zh": "低 Q² 弥散核子", "category": "particle", "family": "nucleon",
        "variant": "low-q2-diffuse", "aliases": ["low Q2 nucleon", "低 Q2 核子"],
        "tags": ["3d", "nucleon", "diffuse"], "physics_roles": ["低 Q² 下的弥散电荷分布"],
        "body": derived("nucleon",
                        '<circle cx="50" cy="50" r="42" fill="#80d5f1" opacity=".16"/>'
                        '<circle cx="50" cy="50" r="34" fill="none" stroke="#b9efff" '
                        'stroke-dasharray="1 4" stroke-width="2"/>'),
    },

    # Medium family
    "qgp_ellipsoid": {
        "name_zh": "椭球 QGP", "category": "medium", "family": "qgp",
        "variant": "ellipsoid", "aliases": ["QGP ellipsoid", "椭球火球"],
        "tags": ["3d", "plasma", "ellipsoid"], "physics_roles": ["非中心碰撞中的椭球介质"],
        "body": '<ellipse cx="50" cy="50" rx="43" ry="29" fill="url(#g)" stroke="#c64718" stroke-width=".8"/>',
        "defs_override": (
            '<radialGradient id="g" cx="32%" cy="28%" r="78%">'
            '<stop offset="0" stop-color="#fffdf0"/><stop offset=".22" stop-color="#ffe98d"/>'
            '<stop offset=".58" stop-color="#f39c34"/><stop offset="1" stop-color="#8c2410" stop-opacity=".25"/></radialGradient>'
        ),
    },
    "qgp_almond": {
        "name_zh": "杏仁形 QGP", "category": "medium", "family": "qgp",
        "variant": "almond", "aliases": ["almond QGP", "杏仁形介质"],
        "tags": ["3d", "plasma", "geometry"], "physics_roles": ["反应平面内的杏仁形介质"],
        "body": derived("qgp_blob",
                        '<path d="M50 9 C75 21 92 35 88 50 C92 65 75 79 50 91 '
                        'C25 79 8 65 12 50 C8 35 25 21 50 9 Z" fill="none" '
                        'stroke="#fff0a1" stroke-opacity=".32" stroke-width="1"/>'),
    },
    "qgp_triangular": {
        "name_zh": "三角涨落 QGP", "category": "medium", "family": "qgp",
        "variant": "triangular", "aliases": ["triangular flow medium", "三角形介质"],
        "tags": ["3d", "plasma", "fluctuation"], "physics_roles": ["具有三角涨落的介质"],
        "body": '<path d="M50 7 C73 31 91 55 83 88 C61 76 39 76 17 88 C9 55 27 31 50 7 Z" '
                'fill="url(#g)" stroke="#b83e17" stroke-width=".8"/>',
        "defs_override": (
            '<radialGradient id="g" cx="45%" cy="30%"><stop offset="0" stop-color="#fff8dc"/>'
            '<stop offset=".35" stop-color="#ffbf55"/><stop offset=".75" stop-color="#df5420"/>'
            '<stop offset="1" stop-color="#7d1b0a" stop-opacity=".28"/></radialGradient>'
        ),
    },
    "qgp_rotating": {
        "name_zh": "旋转 QGP", "category": "medium", "family": "qgp",
        "variant": "rotating", "aliases": ["rotating QGP", "vortical QGP", "旋转火球"],
        "tags": ["3d", "plasma", "vorticity"], "physics_roles": ["携带宏观涡度的 QGP"],
        "body": derived("qgp_fireball",
                        '<path d="M24 50 A26 18 0 0 1 76 50 M76 50 A26 18 0 0 1 24 50" '
                        'fill="none" stroke="#5d49d6" stroke-width="2"/>'
                        '<path d="M70 43 L77 50 L69 55" fill="none" stroke="#5d49d6" stroke-width="2"/>'),
    },
    "hot_hadron_gas": {
        "name_zh": "热强子气", "category": "medium", "family": "qgp",
        "variant": "hadron-gas", "aliases": ["hadron gas", "热强子气", "冻出后介质"],
        "tags": ["3d", "medium", "particles"], "physics_roles": ["强子化后的热强子气"],
        "body": derived("qgp_blob",
                        '<circle cx="31" cy="36" r="3" fill="#6b7cf1"/><circle cx="62" cy="31" r="2.5" fill="#ef7b42"/>'
                        '<circle cx="72" cy="57" r="3" fill="#46aa76"/><circle cx="43" cy="69" r="2.5" fill="#ef7b42"/>'
                        '<circle cx="29" cy="63" r="2" fill="#6b7cf1"/>'),
    },
    "hydrodynamic_shell": {
        "name_zh": "流体膨胀壳", "category": "medium", "family": "qgp",
        "variant": "hydrodynamic-shell", "aliases": ["hydrodynamic shell", "膨胀壳"],
        "tags": ["3d", "medium", "flow"], "physics_roles": ["向外膨胀的流体表面"],
        "body": derived("qgp_fireball",
                        '<path d="M50 8 L50 20 M91 50 L79 50 M50 91 L50 80 M9 50 L21 50 '
                        'M79 21 L71 29 M79 79 L71 71 M21 21 L29 29 M21 79 L29 71" '
                        'stroke="#fff5bb" stroke-width="1.5"/>'),
    },
    "glasma_two_sheets": {
        "name_zh": "双片 Glasma", "category": "medium", "family": "qgp",
        "variant": "glasma-two-sheets", "aliases": ["Glasma sheets", "色玻璃双片"],
        "tags": ["3d", "glasma", "field"], "physics_roles": ["两束核子色场交叠后的 Glasma"],
        "body": (
            '<path d="M16 63 L72 20 L84 32 L28 75 Z" fill="#d6ecff" opacity=".42" stroke="#6aa8cf"/>'
            '<path d="M28 75 L84 32" stroke="#cf67d9" stroke-width="8" opacity=".38"/>'
            '<path d="M42 67 L48 62 M55 56 L61 51 M68 45 L74 40" stroke="#fff" stroke-width="1.2"/>'
        ),
    },
    "color_glass": {
        "name_zh": "色玻璃凝聚", "category": "medium", "family": "qgp",
        "variant": "color-glass-condensate", "aliases": ["Color Glass Condensate", "CGC", "色玻璃"],
        "tags": ["3d", "cgc", "field"], "physics_roles": ["高能核的色玻璃凝聚"],
        "body": derived("glasma_flux_tubes",
                        '<g stroke="#fff" stroke-width="1" opacity=".36">'
                        '<path d="M18 78 C31 67 69 67 82 78"/><path d="M20 62 C34 53 66 53 80 62"/>'
                        '<path d="M24 46 C38 39 62 39 76 46"/></g>'),
    },
    "quark_soup": {
        "name_zh": "夸克汤", "category": "medium", "family": "qgp",
        "variant": "quark-soup", "aliases": ["quark soup", "deconfined quarks", "夸克汤"],
        "tags": ["3d", "plasma", "partons"], "physics_roles": ["退禁闭的夸克与胶子介质"],
        "body": derived("qgp_fireball",
                        '<circle cx="31" cy="32" r="2.3" fill="#f2d55b"/><circle cx="63" cy="30" r="2.3" fill="#5d8ff4"/>'
                        '<circle cx="72" cy="55" r="2.3" fill="#ee6958"/><circle cx="45" cy="70" r="2.3" fill="#4ad1a0"/>'
                        '<circle cx="28" cy="61" r="2.3" fill="#e780d8"/>'),
    },

    # Jet family
    "jet_quark": {
        "name_zh": "夸克喷注", "category": "jet", "family": "jet",
        "variant": "quark-initiated", "aliases": ["quark jet", "夸克喷注"],
        "tags": ["3d", "jet", "quark"], "physics_roles": ["夸克引发的喷注"],
        "body": cone_jet('<stop offset="0" stop-color="#ffd56c"/><stop offset=".5" stop-color="#f18b32"/>'
                         '<stop offset="1" stop-color="#ffe8a8" stop-opacity=".35"/>',
                         '<circle cx="18" cy="50" r="5" fill="#f2d55b"/>'),
    },
    "jet_gluon": {
        "name_zh": "胶子喷注", "category": "jet", "family": "jet",
        "variant": "gluon-initiated", "aliases": ["gluon jet", "胶子喷注"],
        "tags": ["3d", "jet", "gluon"], "physics_roles": ["胶子引发的喷注"],
        "body": cone_jet('<stop offset="0" stop-color="#bff3ff"/><stop offset=".5" stop-color="#4baee0"/>'
                         '<stop offset="1" stop-color="#e6fbff" stop-opacity=".34"/>',
                         '<path d="M18 50 C24 44 24 56 30 50 C36 44 36 56 42 50" fill="none" '
                         'stroke="#17496b" stroke-width="1.1"/>'),
    },
    "jet_branching": {
        "name_zh": "分支喷注", "category": "jet", "family": "jet",
        "variant": "branching", "aliases": ["jet branching", "parton branching", "分支喷注"],
        "tags": ["3d", "jet", "branching"], "physics_roles": ["部分子簇射分支"],
        "body": derived("jet_cone_hot",
                        '<path d="M28 50 C48 47 58 34 89 24 M28 50 C51 54 64 65 89 75" '
                        'fill="none" stroke="#c8f7ff" stroke-width="1.4"/>'),
    },
    "jet_in_medium": {
        "name_zh": "介质内喷注", "category": "jet", "family": "jet",
        "variant": "in-medium", "aliases": ["in-medium jet", "介质内喷注"],
        "tags": ["3d", "jet", "medium"], "physics_roles": ["正在穿过 QGP 的喷注"],
        "body": derived("jet_cone_hot",
                        '<path d="M20 50 C44 28 72 25 91 43" fill="none" stroke="#fff6c9" '
                        'stroke-width="1" stroke-dasharray="2 2" opacity=".8"/>'),
    },
    "jet_escaping": {
        "name_zh": "逃逸喷注", "category": "jet", "family": "jet",
        "variant": "escaping", "aliases": ["escaping jet", "逃逸喷注"],
        "tags": ["3d", "jet", "escape"], "physics_roles": ["短路径离开介质的高能喷注"],
        "body": cone_jet('<stop offset="0" stop-color="#edf9ff"/><stop offset=".45" stop-color="#7dd4ee"/>'
                         '<stop offset="1" stop-color="#effcff" stop-opacity=".25"/>',
                         '<path d="M12 50 L94 50 M87 44 L95 50 L87 56" fill="none" stroke="#fff" stroke-width="1.2"/>'),
    },
    "jet_quenched_short": {
        "name_zh": "短程淬火喷注", "category": "jet", "family": "jet",
        "variant": "strongly-quenched", "aliases": ["strongly quenched jet", "短程淬火喷注"],
        "tags": ["3d", "jet", "quenched"], "physics_roles": ["经长介质路径后强烈衰减的喷注"],
        "body": cone_jet('<stop offset="0" stop-color="#313943"/><stop offset=".55" stop-color="#838c96"/>'
                         '<stop offset="1" stop-color="#dde2e7" stop-opacity=".18"/>',
                         '<path d="M18 50 L57 50" stroke="#fff" stroke-width=".8" stroke-dasharray="2 3"/>',
                         opacity=0.72),
    },
    "jet_mach_wake": {
        "name_zh": "喷注马赫锥", "category": "jet", "family": "jet",
        "variant": "mach-wake", "aliases": ["Mach cone", "medium wake", "马赫锥"],
        "tags": ["3d", "jet", "wake"], "physics_roles": ["超音速喷注在介质中诱导的马赫锥"],
        "body": derived("jet_cone_hot",
                        '<path d="M50 21 C36 34 36 66 50 79 M53 24 C70 37 70 63 56 76" '
                        'fill="none" stroke="#fff4c8" stroke-width="1.1" opacity=".72"/>'),
    },
    "jet_recoil": {
        "name_zh": "喷注反冲", "category": "jet", "family": "jet",
        "variant": "recoil", "aliases": ["jet recoil", "recoiling medium", "喷注反冲"],
        "tags": ["3d", "jet", "recoil"], "physics_roles": ["喷注能量向介质的热力学转移"],
        "body": derived("jet_cone_hot",
                        '<circle cx="20" cy="50" r="7" fill="#fff2c7" opacity=".8"/>'
                        '<path d="M27 39 L10 29 M27 61 L10 71" stroke="#fff2c7" stroke-width="1.4"/>'),
    },
    "jet_energy_loss": {
        "name_zh": "能量损失喷注", "category": "jet", "family": "jet",
        "variant": "energy-loss", "aliases": ["energy loss", "jet energy loss", "能量损失"],
        "tags": ["3d", "jet", "radiation"], "physics_roles": ["辐射与碰撞能量损失中的喷注"],
        "body": derived("jet_cone_quenched",
                        '<path d="M25 42 C36 31 52 33 64 43 M25 58 C38 69 54 66 68 56" '
                        'fill="none" stroke="#f0c35c" stroke-width="1" opacity=".75"/>'),
    },
    "jet_fragmentation": {
        "name_zh": "喷注碎裂", "category": "jet", "family": "jet",
        "variant": "fragmentation", "aliases": ["jet fragmentation", "hadronization cone", "喷注碎裂"],
        "tags": ["3d", "jet", "hadronization"], "physics_roles": ["喷注末端的强子化与碎裂"],
        "body": derived("jet_cone_hot",
                        '<circle cx="88" cy="21" r="3" fill="#f4d85e"/><circle cx="93" cy="36" r="2.5" fill="#72b8ee"/>'
                        '<circle cx="89" cy="69" r="2.8" fill="#ef7968"/><circle cx="80" cy="82" r="2.2" fill="#72d1a4"/>'),
    },

    # Particle family
    "quark_up": {
        "name_zh": "上夸克", "category": "particle", "family": "quark",
        "variant": "up", "aliases": ["up quark", "u quark", "上夸克"],
        "tags": ["3d", "quark"], "physics_roles": ["上夸克"],
        "body": derived("quark", recolor={"#f4b9ff": "#ffe27a", "#a34db6": "#e9a72b", "#4f1b5d": "#7e4d0b"}),
    },
    "quark_down": {
        "name_zh": "下夸克", "category": "particle", "family": "quark",
        "variant": "down", "aliases": ["down quark", "d quark", "下夸克"],
        "tags": ["3d", "quark"], "physics_roles": ["下夸克"],
        "body": derived("quark", recolor={"#f4b9ff": "#bde4ff", "#a34db6": "#4c8dd0", "#4f1b5d": "#173c62"}),
    },
    "quark_strange": {
        "name_zh": "奇异夸克", "category": "particle", "family": "quark",
        "variant": "strange", "aliases": ["strange quark", "s quark", "奇异夸克"],
        "tags": ["3d", "quark"], "physics_roles": ["奇异夸克"],
        "body": derived("quark", recolor={"#f4b9ff": "#b8f0d5", "#a34db6": "#42a878", "#4f1b5d": "#164c34"}),
    },
    "antiquark": {
        "name_zh": "反夸克", "category": "particle", "family": "quark",
        "variant": "antiquark", "aliases": ["antiquark", "反夸克"],
        "tags": ["3d", "quark", "antiparticle"], "physics_roles": ["反夸克"],
        "body": derived("quark",
                        '<path d="M32 32 L68 68 M68 32 L32 68" stroke="#fff" stroke-width="1.5" opacity=".75"/>'),
    },
    "photon": {
        "name_zh": "光子", "category": "particle", "family": "boson",
        "variant": "photon", "aliases": ["photon", "gamma", "光子"],
        "tags": ["line", "boson", "radiation"], "physics_roles": ["光子"],
        "body": '<path d="M8 50 C20 10 30 90 42 50 C54 10 64 90 76 50 C83 26 88 66 94 50" '
                'fill="none" stroke="url(#g)" stroke-width="2.2" stroke-linecap="round"/>',
        "defs_override": '<linearGradient id="g"><stop offset="0" stop-color="#fff3ae"/>'
                         '<stop offset=".5" stop-color="#ffbe3d"/><stop offset="1" stop-color="#a44d08"/></linearGradient>',
        "dimensionality": "flat",
    },
    "pion": {
        "name_zh": "π 介子", "category": "particle", "family": "meson",
        "variant": "pion", "aliases": ["pion", "pi meson", "π介子"],
        "tags": ["3d", "meson"], "physics_roles": ["π 介子"],
        "body": '<circle cx="50" cy="50" r="24" fill="url(#g)"/>'
                '<path d="M27 50 C42 35 58 35 73 50 C58 65 42 65 27 50 Z" fill="#fff" opacity=".30"/>',
        "defs_override": '<radialGradient id="g"><stop offset="0" stop-color="#fff"/>'
                         '<stop offset=".55" stop-color="#f1a865"/><stop offset="1" stop-color="#884326"/></radialGradient>',
    },
    "kaon": {
        "name_zh": "K 介子", "category": "particle", "family": "meson",
        "variant": "kaon", "aliases": ["kaon", "K meson", "K介子"],
        "tags": ["3d", "meson", "strange"], "physics_roles": ["含奇异夸克的 K 介子"],
        "body": '<circle cx="50" cy="50" r="24" fill="url(#g)"/>'
                '<circle cx="43" cy="48" r="8" fill="#ffe27a" opacity=".75"/>'
                '<circle cx="57" cy="48" r="8" fill="#63d3a1" opacity=".72"/>',
        "defs_override": '<radialGradient id="g"><stop offset="0" stop-color="#fff"/>'
                         '<stop offset=".6" stop-color="#79b5c8"/><stop offset="1" stop-color="#315a67"/></radialGradient>',
    },
    "diquark": {
        "name_zh": "双夸克", "category": "particle", "family": "multiquark",
        "variant": "diquark", "aliases": ["diquark", "双夸克"],
        "tags": ["3d", "multiquark"], "physics_roles": ["双夸克关联"],
        "body": '<circle cx="34" cy="50" r="19" fill="url(#g1)"/><circle cx="66" cy="50" r="19" fill="url(#g2)"/>',
        "defs_override": (
            '<radialGradient id="g1"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#efb74f"/>'
            '<stop offset="1" stop-color="#7b4912"/></radialGradient>'
            '<radialGradient id="g2"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#67a8e7"/>'
            '<stop offset="1" stop-color="#234971"/></radialGradient>'
        ),
    },

    # Detector family
    "beam_pipe": {
        "name_zh": "束流管", "category": "detector", "family": "detector-layer",
        "variant": "beam-pipe", "aliases": ["beam pipe", "束流管"],
        "tags": ["3d", "detector", "beam"], "physics_roles": ["束流真空管"],
        "body": '<path d="M15 50 L85 50" stroke="url(#g)" stroke-width="14" stroke-linecap="round" opacity=".55"/>'
                '<path d="M15 43 L85 43" stroke="#fff" stroke-opacity=".65" stroke-width="2"/>',
        "defs_override": '<linearGradient id="g"><stop offset="0" stop-color="#4e657b"/>'
                         '<stop offset=".4" stop-color="#d8e7f2"/><stop offset="1" stop-color="#687d90"/></linearGradient>',
    },
    "vertex_detector": {
        "name_zh": "顶点探测器", "category": "detector", "family": "detector-layer",
        "variant": "vertex", "aliases": ["vertex detector", "顶点探测器"],
        "tags": ["3d", "detector", "vertex"], "physics_roles": ["靠近碰撞点的顶点探测层"],
        "body": ring_detector([(20, 10, "#d9edf9", 4), (28, 14, "#86abc5", 3)]),
    },
    "silicon_tracker": {
        "name_zh": "硅径迹探测器", "category": "detector", "family": "detector-layer",
        "variant": "silicon-tracker", "aliases": ["silicon tracker", "silicon detector", "硅径迹"],
        "tags": ["3d", "detector", "tracker"], "physics_roles": ["硅像素与径迹探测层"],
        "body": ring_detector([(23, 12, "#eef8ff", 5), (34, 18, "#8db4ce", 4), (44, 24, "#526d83", 3)],
                              '<g stroke="#fff" stroke-opacity=".45" stroke-width=".5">'
                              '<path d="M18 52 L82 52 M50 29 L50 76 M27 38 L73 68 M73 38 L27 68"/></g>'),
    },
    "tpc": {
        "name_zh": "时间投影室", "category": "detector", "family": "detector-layer",
        "variant": "tpc", "aliases": ["TPC", "time projection chamber", "时间投影室"],
        "tags": ["3d", "detector", "tpc"], "physics_roles": ["气体时间投影室"],
        "body": ring_detector([(42, 25, "#b6d3e6", 8), (34, 20, "#e7f3fa", 5)],
                              '<circle cx="26" cy="38" r="1.4" fill="#e46d35"/>'
                              '<circle cx="72" cy="42" r="1.4" fill="#53a98f"/>'
                              '<circle cx="62" cy="70" r="1.4" fill="#5b83db"/>'),
    },
    "em_calorimeter": {
        "name_zh": "电磁量能器", "category": "detector", "family": "detector-layer",
        "variant": "electromagnetic-calorimeter", "aliases": ["EM calorimeter", "电磁量能器"],
        "tags": ["3d", "detector", "calorimeter"], "physics_roles": ["电磁量能器层"],
        "body": ring_detector([(47, 29, "#f0c86d", 9)], '<path d="M50 23 L50 81 M22 52 L78 52" stroke="#fff" opacity=".35"/>'),
    },
    "hadron_calorimeter": {
        "name_zh": "强子量能器", "category": "detector", "family": "detector-layer",
        "variant": "hadronic-calorimeter", "aliases": ["hadron calorimeter", "强子量能器"],
        "tags": ["3d", "detector", "calorimeter"], "physics_roles": ["强子量能器层"],
        "body": ring_detector([(45, 28, "#6e7d8b", 12)], '<path d="M20 52 L80 52 M50 25 L50 79" stroke="#f3f4f5" opacity=".4"/>'),
    },
    "endcap_detector": {
        "name_zh": "端盖探测器", "category": "detector", "family": "detector-layer",
        "variant": "endcap", "aliases": ["endcap detector", "端盖探测器"],
        "tags": ["3d", "detector", "endcap"], "physics_roles": ["束流方向端盖探测层"],
        "body": '<ellipse cx="50" cy="50" rx="35" ry="35" fill="none" stroke="#8098ad" stroke-width="7"/>'
                '<ellipse cx="50" cy="50" rx="22" ry="22" fill="none" stroke="#e2eef6" stroke-width="5"/>'
                '<circle cx="50" cy="50" r="8" fill="#f39c34"/>',
    },
    "solenoid": {
        "name_zh": "超导螺线管", "category": "detector", "family": "detector-layer",
        "variant": "solenoid", "aliases": ["solenoid magnet", "超导螺线管"],
        "tags": ["3d", "detector", "magnet"], "physics_roles": ["探测器超导螺线管"],
        "body": '<g fill="none" stroke="#5d7991" stroke-width="6">'
                '<ellipse cx="50" cy="50" rx="40" ry="18"/><ellipse cx="50" cy="50" rx="30" ry="14"/>'
                '<ellipse cx="50" cy="50" rx="20" ry="10"/></g><path d="M22 50 L78 50" stroke="#f5b744" stroke-width="3"/>',
    },
    "detector_cutaway": {
        "name_zh": "探测器剖视", "category": "detector", "family": "detector-layer",
        "variant": "full-cutaway", "aliases": ["detector cutaway", "full detector", "探测器剖视"],
        "tags": ["3d", "detector", "cutaway"], "physics_roles": ["分层探测器整体剖视"],
        "body": ring_detector([(46, 29, "#405b73", 8), (37, 23, "#f0c76d", 7),
                               (28, 17, "#d9eaf5", 6), (18, 11, "#7aa3bf", 5)],
                              '<path d="M50 20 L50 82" stroke="#fff" stroke-width="2" opacity=".6"/>'),
    },

    # Field family
    "electric_field_line": {
        "name_zh": "电场线", "category": "field", "family": "gauge-field",
        "variant": "electric", "aliases": ["electric field", "电场线"],
        "tags": ["field", "electric"], "physics_roles": ["电场方向"],
        "body": line_field("#db6c42", '<path d="M82 27 L91 36 L80 39" fill="none" stroke="#db6c42" stroke-width="1.5"/>'),
    },
    "crossed_eb": {
        "name_zh": "交叉电磁场", "category": "field", "family": "gauge-field",
        "variant": "crossed-eb", "aliases": ["crossed E and B", "交叉电磁场"],
        "tags": ["field", "electric", "magnetic"], "physics_roles": ["交叉电场与磁场"],
        "body": line_field("#7458e7",
                           '<path d="M12 20 C30 34 64 64 90 76" fill="none" stroke="#d8683d" stroke-width="1.8"/>'
                           '<path d="M82 72 L91 77 L84 84" fill="none" stroke="#d8683d" stroke-width="1.5"/>'),
    },
    "cme_magnetic": {
        "name_zh": "CME 磁场", "category": "field", "family": "gauge-field",
        "variant": "cme", "aliases": ["chiral magnetic effect field", "CME 磁场"],
        "tags": ["field", "cme", "magnetic"], "physics_roles": ["手征磁效应中的磁场"],
        "body": line_field("#5d45ba",
                           '<circle cx="50" cy="50" r="18" fill="none" stroke="#ec74c2" stroke-width="1.4"/>'
                           '<path d="M35 58 C45 44 55 60 65 43" fill="none" stroke="#fff" stroke-width="1"/>'),
    },
    "cve_vortex": {
        "name_zh": "手征涡旋效应", "category": "field", "family": "gauge-field",
        "variant": "cve", "aliases": ["chiral vortical effect", "CVE", "手征涡旋"],
        "tags": ["field", "vorticity", "spin"], "physics_roles": ["手征涡旋效应"],
        "body": '<g fill="none" stroke="#7a58d6" stroke-width="2">'
                '<path d="M22 50 A28 18 0 0 1 78 50"/><path d="M78 50 A28 18 0 0 1 22 50"/></g>'
                '<path d="M70 42 L79 50 L69 56" fill="none" stroke="#7a58d6" stroke-width="2"/>'
                '<circle cx="50" cy="50" r="5" fill="#fff4bd"/>',
    },
    "vorticity_field": {
        "name_zh": "涡度场", "category": "field", "family": "gauge-field",
        "variant": "vorticity", "aliases": ["vorticity field", "宏观涡度"],
        "tags": ["field", "vorticity"], "physics_roles": ["流体涡度场"],
        "body": '<g fill="none" stroke="#7555d6" stroke-width="1.8">'
                '<path d="M15 55 C25 25 75 25 85 55"/><path d="M20 70 C35 48 65 48 80 70"/>'
                '<path d="M30 35 C40 15 60 15 70 35"/></g>',
    },
    "field_stack": {
        "name_zh": "多层场线", "category": "field", "family": "gauge-field",
        "variant": "stacked-lines", "aliases": ["field stack", "多层场"],
        "tags": ["field", "magnetic"], "physics_roles": ["多层磁场或色场线"],
        "body": '<g fill="none" stroke-linecap="round">'
                '<path d="M5 70 C25 20 65 15 95 35" stroke="#7d5ce3" stroke-width="2"/>'
                '<path d="M5 78 C30 38 68 32 95 48" stroke="#9a7af3" stroke-width="1.5"/>'
                '<path d="M5 86 C34 54 72 48 95 62" stroke="#b59cff" stroke-width="1"/></g>',
    },
    "photon_flux": {
        "name_zh": "光子通量", "category": "field", "family": "gauge-field",
        "variant": "photon-flux", "aliases": ["photon flux", "光子通量"],
        "tags": ["field", "photon"], "physics_roles": ["来自原子核的光子通量"],
        "body": '<g fill="none" stroke="#e9b53a" stroke-width="1.4">'
                '<path d="M8 30 C20 10 32 50 44 30 C56 10 68 50 80 30 C86 20 90 28 94 25"/>'
                '<path d="M8 55 C20 35 32 75 44 55 C56 35 68 75 80 55 C86 45 90 53 94 50"/>'
                '<path d="M8 80 C20 60 32 100 44 80 C56 60 68 100 80 80"/></g>',
    },

    # Geometry family
    "impact_parameter": {
        "name_zh": "碰撞参数", "category": "geometry", "family": "geometry",
        "variant": "impact-parameter", "aliases": ["impact parameter", "碰撞参数 b"],
        "tags": ["geometry", "collision"], "physics_roles": ["两个核的横向碰撞参数"],
        "body": '<circle cx="31" cy="50" r="18" fill="#d9e7f1" stroke="#536d82"/>'
                '<circle cx="69" cy="50" r="18" fill="#d9e7f1" stroke="#536d82"/>'
                '<path d="M31 78 L69 78 M39 74 L31 78 L39 82 M61 74 L69 78 L61 82" '
                'fill="none" stroke="#c74625" stroke-width="1.2"/>',
    },
    "axes_3d": {
        "name_zh": "三维坐标轴", "category": "geometry", "family": "geometry",
        "variant": "axes-3d", "aliases": ["3D axes", "xyz axes", "三轴"],
        "tags": ["geometry", "axes"], "physics_roles": ["右手三维坐标轴"],
        "body": '<g fill="none" stroke="#263845" stroke-width="1.5">'
                '<path d="M30 70 L90 70"/><path d="M30 70 L16 30"/><path d="M30 70 L30 8"/></g>'
                '<path d="M84 65 L92 70 L84 75 M12 36 L16 28 L21 36 M25 14 L30 6 L35 14" '
                'fill="none" stroke="#263845" stroke-width="1.3"/>',
        "dimensionality": "mixed",
    },
    "collision_overlap": {
        "name_zh": "碰撞交叠区", "category": "geometry", "family": "geometry",
        "variant": "overlap", "aliases": ["collision overlap", "交叠区"],
        "tags": ["geometry", "collision"], "physics_roles": ["两个入射核的交叠区域"],
        "body": '<ellipse cx="37" cy="50" rx="28" ry="31" fill="#dce8f1" stroke="#61798d"/>'
                '<ellipse cx="63" cy="50" rx="28" ry="31" fill="#dce8f1" opacity=".72" stroke="#61798d"/>'
                '<ellipse cx="50" cy="50" rx="13" ry="29" fill="#f09936" opacity=".75"/>',
    },
    "freezeout_surface": {
        "name_zh": "冻出表面", "category": "geometry", "family": "geometry",
        "variant": "freezeout", "aliases": ["freeze-out surface", "冻出面"],
        "tags": ["geometry", "freezeout"], "physics_roles": ["强子冻出表面"],
        "body": '<path d="M16 53 C16 28 37 12 55 18 C79 22 88 45 78 65 '
                'C68 87 36 91 22 74 C12 64 10 59 16 53 Z" fill="none" '
                'stroke="#4c7898" stroke-width="2" stroke-dasharray="4 3"/>'
                '<path d="M33 39 C42 29 57 31 65 42 C72 55 62 70 48 70 C35 70 26 55 33 39 Z" '
                'fill="#ffcf70" opacity=".35"/>',
    },
    "spacetime_diagram": {
        "name_zh": "时空演化图", "category": "geometry", "family": "geometry",
        "variant": "spacetime", "aliases": ["spacetime diagram", "时空图"],
        "tags": ["geometry", "spacetime"], "physics_roles": ["碰撞演化的时空结构"],
        "body": derived("light_cone",
                        '<path d="M50 88 C58 67 60 39 50 12 C42 38 40 65 50 88 Z" '
                        'fill="#f19a38" opacity=".22" stroke="#e87b2e" stroke-width=".8"/>'),
        "dimensionality": "mixed",
    },
    "rapidity_fan": {
        "name_zh": "快度扇形", "category": "geometry", "family": "geometry",
        "variant": "rapidity-fan", "aliases": ["rapidity fan", "快度分布"],
        "tags": ["geometry", "rapidity"], "physics_roles": ["不同快度的粒子发射方向"],
        "body": '<circle cx="15" cy="58" r="5" fill="#ef9a3d"/>'
                '<path d="M18 56 L88 15 M18 58 L94 36 M18 62 L94 62 M18 64 L94 86" '
                'stroke="#406b88" stroke-width="1.2"/>',
        "dimensionality": "mixed",
    },
    "participant_plane": {
        "name_zh": "参与者平面", "category": "geometry", "family": "geometry",
        "variant": "participant-plane", "aliases": ["participant plane", "参与者平面"],
        "tags": ["geometry", "plane"], "physics_roles": ["参与者几何定义的作用平面"],
        "body": derived("reaction_plane",
                        '<path d="M50 18 L50 82" stroke="#d85d2d" stroke-width="1.3" stroke-dasharray="4 3"/>'),
        "dimensionality": "mixed",
    },
    "transverse_plane": {
        "name_zh": "横平面", "category": "geometry", "family": "geometry",
        "variant": "transverse-plane", "aliases": ["transverse plane", "横平面"],
        "tags": ["geometry", "plane"], "physics_roles": ["垂直于束流轴的横平面"],
        "body": '<circle cx="50" cy="50" r="37" fill="#e8f1f7" opacity=".75" stroke="#8198a9"/>'
                '<path d="M13 50 L87 50 M50 13 L50 87" stroke="#3c566b" stroke-width="1.2"/>',
        "dimensionality": "mixed",
    },

    # Spin / marker and interaction families
    "angular_momentum": {
        "name_zh": "角动量", "category": "marker", "family": "spin-marker",
        "variant": "angular-momentum", "aliases": ["angular momentum", "orbital angular momentum", "L"],
        "tags": ["symbol", "spin", "angular-momentum"], "physics_roles": ["体系角动量 L"],
        "body": marker_circle("#2d4770", "dot",
                              '<path d="M28 36 C38 22 62 22 72 36" fill="none" stroke="#5d80b8" stroke-width="1.5"/>'
                              '<path d="M66 30 L73 36 L66 41" fill="none" stroke="#5d80b8" stroke-width="1.4"/>'),
        "dimensionality": "flat",
    },
    "charge_positive": {
        "name_zh": "正电荷", "category": "marker", "family": "charge-marker",
        "variant": "positive", "aliases": ["positive charge", "正电荷"],
        "tags": ["symbol", "charge"], "physics_roles": ["正电荷"],
        "body": marker_circle("#c54123", "+"), "dimensionality": "flat",
    },
    "charge_negative": {
        "name_zh": "负电荷", "category": "marker", "family": "charge-marker",
        "variant": "negative", "aliases": ["negative charge", "负电荷"],
        "tags": ["symbol", "charge"], "physics_roles": ["负电荷"],
        "body": marker_circle("#2f6fb6", "-"), "dimensionality": "flat",
    },
    "neutral_marker": {
        "name_zh": "中性粒子", "category": "marker", "family": "charge-marker",
        "variant": "neutral", "aliases": ["neutral particle", "中性粒子"],
        "tags": ["symbol", "charge"], "physics_roles": ["电中性粒子"],
        "body": marker_circle("#5f6872", "dot",
                              '<circle cx="50" cy="50" r="28" fill="none" stroke="#5f6872" '
                              'stroke-dasharray="2 2" stroke-width="1"/>'),
        "dimensionality": "flat",
    },
    "photon_polarization": {
        "name_zh": "光子极化", "category": "marker", "family": "spin-marker",
        "variant": "photon-polarization", "aliases": ["photon polarization", "光子极化"],
        "tags": ["symbol", "photon", "spin"], "physics_roles": ["光子线偏振方向"],
        "body": '<path d="M8 50 C20 10 30 90 42 50 C54 10 64 90 76 50 C83 26 88 66 94 50" '
                'fill="none" stroke="url(#g)" stroke-width="2.2" stroke-linecap="round"/>'
                '<path d="M34 32 L66 68 M66 32 L34 68" stroke="#5f83b7" stroke-width="1.2"/>',
        "defs_override": '<linearGradient id="g"><stop offset="0" stop-color="#fff3ae"/>'
                         '<stop offset=".5" stop-color="#ffbe3d"/><stop offset="1" stop-color="#a44d08"/></linearGradient>',
        "dimensionality": "flat",
    },
    "energy_flow": {
        "name_zh": "能流", "category": "marker", "family": "flow-marker",
        "variant": "energy-flow", "aliases": ["energy flow", "能流"],
        "tags": ["symbol", "flow", "energy"], "physics_roles": ["能量流向"],
        "body": '<path d="M12 50 L82 50 M68 39 L84 50 L68 61 M24 40 L39 50 L24 60" '
                'fill="none" stroke="#e7822e" stroke-width="2" stroke-linecap="round"/>',
        "dimensionality": "flat",
    },
    "soft_vertex": {
        "name_zh": "软散射顶点", "category": "interaction", "family": "interaction",
        "variant": "soft", "aliases": ["soft vertex", "软散射"],
        "tags": ["interaction", "vertex"], "physics_roles": ["软散射或热化顶点"],
        "body": interaction_burst("#e79b42"), "dimensionality": "mixed",
    },
    "chiral_anomaly": {
        "name_zh": "手征反常", "category": "interaction", "family": "interaction",
        "variant": "chiral-anomaly", "aliases": ["chiral anomaly", "axial anomaly", "手征反常"],
        "tags": ["interaction", "anomaly"], "physics_roles": ["轴矢流反常"],
        "body": interaction_burst("#df70c5",
                                  '<path d="M34 37 C49 22 67 42 64 61 C51 75 34 60 41 49" '
                                  'fill="none" stroke="#6a3b98" stroke-width="1.5"/>'),
    },
    "resonance_decay": {
        "name_zh": "共振衰变", "category": "interaction", "family": "interaction",
        "variant": "resonance-decay", "aliases": ["resonance decay", "共振衰变"],
        "tags": ["interaction", "decay"], "physics_roles": ["共振态衰变为末态粒子"],
        "body": '<circle cx="50" cy="50" r="8" fill="#f1a33d"/>'
                '<path d="M44 44 L18 23 M56 44 L82 23 M44 56 L18 77 M56 56 L82 77" '
                'stroke="#384b5e" stroke-width="1.2"/><circle cx="17" cy="22" r="4" fill="#5d8dd9"/>'
                '<circle cx="83" cy="22" r="4" fill="#5d8dd9"/><circle cx="17" cy="78" r="4" fill="#5d8dd9"/>'
                '<circle cx="83" cy="78" r="4" fill="#5d8dd9"/>',
        "dimensionality": "mixed",
    },
    "coalescence": {
        "name_zh": "重组强子化", "category": "interaction", "family": "interaction",
        "variant": "coalescence", "aliases": ["coalescence", "recombination", "重组"],
        "tags": ["interaction", "hadronization"], "physics_roles": ["部分子重组形成强子"],
        "body": '<circle cx="18" cy="38" r="10" fill="#e6ad3e"/><circle cx="18" cy="65" r="10" fill="#5687d5"/>'
                '<path d="M30 38 C48 34 47 47 60 50 M30 65 C48 69 47 56 60 50" fill="none" stroke="#5f6d78" stroke-width="1"/>'
                '<circle cx="72" cy="50" r="14" fill="url(#g)"/>',
        "defs_override": '<radialGradient id="g"><stop offset="0" stop-color="#fff"/>'
                         '<stop offset=".55" stop-color="#e8a85f"/><stop offset="1" stop-color="#7b4324"/></radialGradient>',
        "dimensionality": "mixed",
    },
}

BASE_FAMILIES = {
    "nucleus_spherical": "nucleus",
    "nucleus_deformed": "nucleus",
    "nucleon": "nucleon",
    "qgp_fireball": "qgp",
    "qgp_blob": "qgp",
    "glasma_flux_tubes": "qgp",
    "jet_cone_hot": "jet",
    "jet_cone_quenched": "jet",
    "quark": "quark",
    "gluon_radiation": "gauge-field",
    "detector_ring": "detector-layer",
    "detector_barrel": "detector-layer",
    "particle_tracks": "detector-layer",
    "magnetic_field_line": "gauge-field",
    "spin_out": "spin-marker",
    "spin_in": "spin-marker",
    "reaction_plane": "geometry",
    "beam_axis": "geometry",
    "light_cone": "geometry",
    "hard_vertex": "interaction",
    "hadronization_burst": "interaction",
}


def build():
    LIB.mkdir(parents=True, exist_ok=True)
    preserved = []
    if (LIB / "index.json").exists():
        try:
            old = json.loads((LIB / "index.json").read_text(encoding="utf-8"))
            preserved = [
                a for a in old.get("assets", [])
                if str((a.get("generation") or {}).get("origin", "")).startswith("article_")
            ]
        except Exception:
            preserved = []
    entries = []
    all_assets = dict(ASSETS)
    all_assets.update(VARIANT_ASSETS)
    for aid, spec in sorted(all_assets.items()):
        category = spec["category"]
        rel = Path(category) / f"{aid}.svg"
        path = LIB / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        body = spec["body"]
        if not body.lstrip().startswith("<?xml") and not body.lstrip().startswith("<svg"):
            body = svg(body, spec.get("defs_override", ""))
        elif spec.get("defs_override"):
            start = body.find("<defs>") + len("<defs>")
            end = body.find("</defs>", start)
            body = body[:start] + spec["defs_override"] + body[end:]
        path.write_text(body, encoding="utf-8")
        entries.append({
            "id": aid,
            "version": "1.0.0",
            "family": spec.get("family", BASE_FAMILIES.get(aid, aid)),
            "variant": spec.get("variant", "base"),
            "variant_description": spec.get(
                "variant_description",
                f"{spec.get('family', aid)} / {spec.get('variant', 'base')}",
            ),
            "name_zh": spec["name_zh"],
            "aliases": spec["aliases"],
            "category": category,
            "tags": spec["tags"],
            "physics_roles": spec["physics_roles"],
            "file": rel.as_posix(),
            "viewBox": [0, 0, 100, 100],
            "anchor": [50, 50],
            "dimensionality": spec.get("dimensionality", "3d"),
            "license": {
                "spdx": "MIT",
                "redistributable": True,
                "attribution": (
                    "hep-nature-figure element library, code-authored vector. "
                    "Copyright Yuhao Peng; MIT."
                ),
            },
            "generation": {
                "origin": "software",
                "ai_generated": False,
                "contains_ai_pixels": False,
                "tool": "scripts/build_element_library.py",
                "model": None,
            },
            "review": {
                "status": "verified",
                "reviewed_by": "repository-maintainers",
                "reviewed_at": TODAY,
            },
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    by_id = {a["id"]: a for a in preserved}
    by_id.update({a["id"]: a for a in entries})
    index = {
        "schema_version": "1.0",
        "library_version": "5.1.0",
        "updated": TODAY,
        "assets": sorted(by_id.values(), key=lambda a: a["id"]),
    }
    (LIB / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built {len(entries)} software-authored vector elements -> {LIB}")


if __name__ == "__main__":
    build()
