#!/usr/bin/env python3
"""Rebuild selected article-derived vector elements as native SVG geometry.

The source crop remains the visual/provenance reference. The output contains
only editable circles, paths, gradients and native text; no traced pixel
clusters or embedded images are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

from cartoon_lib import Cartoon

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "element-library"
INDEX = LIB / "index.json"
TODAY = "2026-11-22"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def marker_defs(prefix: str) -> str:
    return f"""
    <marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="8.5" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="#18212b"/>
    </marker>
    <marker id="{prefix}-flow" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5.5" markerHeight="5.5" orient="auto">
      <path d="M0 0 L10 5 L0 10 z" fill="#84a3cf"/>
    </marker>
"""


def cartoon_svg(cart: Cartoon, asset_id: str, group_id: str) -> str:
    """Serialize a Cartoon canvas as a transparent article-derived asset."""
    text = cart.tostring().replace(
        "<svg xmlns=",
        f'<svg data-element-asset="{asset_id}" '
        f'data-origin="article_vector_native" xmlns=',
        1,
    )
    text = text.replace(
        f'<g id="{group_id}"',
        f'<g id="{group_id}" data-element="{group_id}"',
        1,
    )
    text = text.replace(
        "</svg>",
        f'  <metadata id="native-source-redraw">{group_id}</metadata>\n</svg>',
        1,
    )
    return text


def sphere_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    variant = (asset.get("variant") or "").casefold()
    palette = {
        "red": ("#ff9696", "#d92834", "#73040d"),
        "gray": ("#f0f1f3", "#9ca1a8", "#4e535a"),
        "green": ("#b8ff93", "#22cd45", "#075a1b"),
        "purple": ("#bca8ff", "#5831e5", "#211060"),
        "proton": ("#ffc1c3", "#df6871", "#872a34"),
        "neutron": ("#c5d8ff", "#557dc9", "#1e3e78"),
    }
    if "gray" in variant:
        key = "gray"
    elif "green" in variant:
        key = "green"
    elif "purple" in variant:
        key = "purple"
    elif "neutron" in variant:
        key = "neutron"
    elif "proton" in variant:
        key = "proton"
    else:
        key = "red"
    light, mid, dark = palette[key]
    fx, fy = (0.34, 0.28)
    if "left" in variant:
        fx, fy = 0.24, 0.43
    elif "right" in variant:
        fx, fy = 0.73, 0.38
    elif "bottom" in variant:
        fx, fy = 0.44, 0.72
    elif "back" in variant:
        fx, fy = 0.48, 0.20
    elif "highlight" in variant:
        fx, fy = 0.64, 0.28
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-ball" cx="{fx}" cy="{fy}" r=".72">
      <stop offset="0" stop-color="{light}"/>
      <stop offset=".18" stop-color="{mid}"/>
      <stop offset=".76" stop-color="{mid}"/>
      <stop offset="1" stop-color="{dark}"/>
    </radialGradient>
    <linearGradient id="{prefix}-rim" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".52"/>
      <stop offset=".4" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="1" stop-color="#000000" stop-opacity=".26"/>
    </linearGradient>
  </defs>
  <g id="nucleon" data-element="{aid}">
    <ellipse id="contact-shade" cx="65" cy="112" rx="34" ry="8"
             fill="#0b1118" opacity=".13"/>
    <circle id="volume" cx="64" cy="62" r="48" fill="url(#{prefix}-ball)"
            stroke="{dark}" stroke-width="1.1"/>
    <path id="rim-light" d="M25 43 A48 48 0 0 1 91 22"
          fill="none" stroke="url(#{prefix}-rim)" stroke-width="5"
          stroke-linecap="round" opacity=".75"/>
    <ellipse id="specular" cx="{36 if fx < .5 else 82}" cy="{34 if fy < .5 else 82}"
             rx="10" ry="6" fill="#ffffff" opacity=".58"/>
    <ellipse id="specular-soft" cx="{38 if fx < .5 else 80}" cy="{47 if fy < .5 else 70}"
             rx="17" ry="9" fill="#ffffff" opacity=".13"/>
  </g>
</svg>
"""


def pair_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    variant = aid.casefold()
    color_map = {
        "red": ("#ff8e91", "#e12532", "#850511"),
        "cyan": ("#b9ffff", "#12cbd6", "#006a73"),
        "green": ("#b8ff98", "#1bc84b", "#07581b"),
        "magenta": ("#ffb4ff", "#cf32df", "#66056d"),
        "yellow": ("#fff59a", "#e7c51a", "#786100"),
        "blue": ("#b9d5ff", "#235bd5", "#0a2a72"),
        "gray": ("#f4f5f7", "#9ca1a8", "#4d5258"),
    }
    order = ["red", "cyan", "magenta", "green", "yellow", "blue", "gray"]
    colors = [color_map[name] for name in order if name in variant]
    if len(colors) < 2:
        colors = [color_map["red"], color_map["cyan"]]
    triplet = "triplet" in variant
    positions = [(60, 62), (103, 53)]
    if triplet:
        positions.append((88, 91))
    defs = []
    balls = []
    for i, (cx, cy) in enumerate(positions):
        light, mid, dark = colors[i % len(colors)]
        defs.append(
            f'<radialGradient id="{prefix}-p{i}" cx=".34" cy=".28" r=".72">'
            f'<stop offset="0" stop-color="{light}"/>'
            f'<stop offset=".22" stop-color="{mid}"/>'
            f'<stop offset="1" stop-color="{dark}"/>'
            f'</radialGradient>'
        )
        balls.append(
            f'<circle cx="{cx}" cy="{cy}" r="20" fill="url(#{prefix}-p{i})" '
            f'stroke="{dark}" stroke-width="1"/>'
            f'<ellipse cx="{cx-7}" cy="{cy-8}" rx="5" ry="3" '
            f'fill="#ffffff" opacity=".52"/>'
        )
    arrow = ""
    if "outgoing" in variant or "pair_red_green" in variant:
        arrow = (
            f'<path d="M118 39 C141 31 150 28 162 21" fill="none" '
            f'stroke="#18212b" stroke-width="4" marker-end="url(#{prefix}-arrow)"/>'
        )
    else:
        arrow = (
            f'<path d="M74 80 C98 84 117 80 140 70" fill="none" '
            f'stroke="#18212b" stroke-width="3.5" marker-end="url(#{prefix}-arrow)"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 130"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {''.join(defs)}
    <marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="8.5" refY="5"
            markerWidth="5" markerHeight="5" orient="auto-start-reverse">
      <path d="M0 0 L10 5 L0 10 z" fill="#18212b"/>
    </marker>
  </defs>
  <g id="parton-cluster" data-element="{aid}">
    {''.join(balls)}
    {arrow}
  </g>
</svg>
"""


def quark_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    variant = (asset.get("variant") or "").casefold()
    colors = {
        "red": ("#ff9c9c", "#df2635", "#74050f"),
        "green": ("#beff94", "#24c94a", "#07551b"),
        "blue": ("#bed9ff", "#2866da", "#0a2d76"),
        "gray": ("#f1f2f4", "#9da2a9", "#4a4f56"),
    }
    name = next((x for x in colors if x in variant), "red")
    light, mid, dark = colors[name]
    anti = "qbar" in variant or "antiquark" in variant
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-g" cx=".35" cy=".28" r=".75">
      <stop offset="0" stop-color="{light}"/>
      <stop offset=".24" stop-color="{mid}"/>
      <stop offset="1" stop-color="{dark}"/>
    </radialGradient>
  </defs>
  <g id="quark-marker" data-element="{aid}">
    <circle cx="50" cy="50" r="34" fill="url(#{prefix}-g)" stroke="{dark}"
            stroke-width="1.2"/>
    <ellipse cx="38" cy="34" rx="8" ry="4.5" fill="#fff" opacity=".42"/>
    <text x="50" y="62" text-anchor="middle" font-family="DejaVu Sans, Arial"
          font-size="34" font-weight="700" fill="#ffffff">{'q' if not anti else 'q'}</text>
    {'' if not anti else '<path d="M34 25 H66" stroke="#fff" stroke-width="3" stroke-linecap="round"/>'}
    {'' if 'striped' not in variant else '<path d="M24 34 L76 66 M24 50 L76 82" stroke="#18212b" stroke-width="3" opacity=".55"/>'}
  </g>
</svg>
"""


def medium_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    outer = "outer" in aid
    dots = ""
    if outer:
        pairs = [(70, 70, "cyan"), (91, 58, "magenta"), (188, 85, "green"),
                 (205, 121, "yellow"), (80, 235, "blue"), (192, 258, "red")]
        fills = {"cyan": "#1ad5de", "magenta": "#d634df", "green": "#28cf4c",
                 "yellow": "#ead11e", "blue": "#2f64de", "red": "#e12835"}
        dots = "".join(
            f'<circle cx="{x}" cy="{y}" r="8" fill="{fills[c]}"/>' for x, y, c in pairs
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {marker_defs(prefix)}
    <radialGradient id="{prefix}-medium" cx=".48" cy=".42" r=".62">
      <stop offset="0" stop-color="#f7f7f7"/>
      <stop offset=".58" stop-color="#b8babd"/>
      <stop offset="1" stop-color="#595c60"/>
    </radialGradient>
    <clipPath id="{prefix}-clip">
      <path d="M139 24 C181 25 210 54 219 99 C226 137 249 170 237 209
               C226 247 206 277 171 304 C141 327 114 337 78 314
               C48 294 29 272 26 231 C22 184 43 166 50 132
               C57 98 51 67 79 43 C98 28 119 24 139 24 Z"/>
    </clipPath>
  </defs>
  <g id="partonic-medium" data-element="{aid}">
    <path d="M139 24 C181 25 210 54 219 99 C226 137 249 170 237 209
             C226 247 206 277 171 304 C141 327 114 337 78 314
             C48 294 29 272 26 231 C22 184 43 166 50 132
             C57 98 51 67 79 43 C98 28 119 24 139 24 Z"
          fill="url(#{prefix}-medium)" stroke="#4e5155" stroke-width="2"/>
    <g clip-path="url(#{prefix}-clip)" opacity=".72">
      <ellipse cx="74" cy="58" rx="44" ry="18" fill="#ffffff"/>
      <ellipse cx="191" cy="179" rx="58" ry="25" fill="#ffffff" opacity=".55"/>
      <ellipse cx="116" cy="283" rx="48" ry="18" fill="#303338" opacity=".22"/>
    </g>
    {dots}
    <g stroke="#1d242b" stroke-width="3" fill="none" marker-end="url(#{prefix}-arrow)">
      <path d="M70 120 L91 92"/><path d="M110 86 L106 53"/>
      <path d="M152 92 L176 64"/><path d="M204 166 L239 163"/>
      <path d="M193 230 L227 249"/><path d="M142 283 L155 317"/>
      <path d="M91 273 L61 291"/><path d="M56 208 L24 216"/>
    </g>
  </g>
</svg>
"""


def vortex_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    if "charged_disk" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="charged-vortex" data-element="{aid}">
    <circle cx="50" cy="50" r="38" fill="#08090b"/>
    <circle cx="50" cy="50" r="34" fill="none" stroke="#25272a" stroke-width="2"/>
    <text x="50" y="59" text-anchor="middle" font-family="DejaVu Sans, Arial"
          font-size="25" fill="#fff">q<tspan dy="-7" font-size="17">e</tspan></text>
  </g>
</svg>
"""
    if "b_arrow" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 70 320"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>{marker_defs(prefix)}</defs>
  <g id="magnetic-axis" data-element="{aid}">
    <path d="M35 300 L35 28" fill="none" stroke="#ec2c24" stroke-width="7"
          stroke-dasharray="11 9" marker-end="url(#{prefix}-arrow)"/>
    <text x="48" y="32" font-family="DejaVu Serif, Times" font-size="22"
          font-weight="700" fill="#111">B</text>
  </g>
</svg>
"""
    nest = "nest" in aid
    loops = ""
    for i in range(5 if nest else 1):
        ry = 45 + i * 17
        rx = (125 if not nest else 132 - i * 7)
        cy = 115
        loops += (
            f'<ellipse cx="145" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" '
            f'stroke="#20aee7" stroke-width="{6 if nest else 7}" opacity="{1 - i*.11}"/>'
            f'<path d="M{145-rx+16} {cy+ry*.45} L{145-rx} {cy+ry*.18}" '
            f'stroke="#20aee7" stroke-width="8" marker-end="url(#{prefix}-flow)"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 240"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {marker_defs(prefix)}
    <marker id="{prefix}-red" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="5" markerHeight="5" orient="auto">
      <path d="M0 0 L10 5 L0 10 z" fill="#d9231c"/>
    </marker>
  </defs>
  <g id="vortex-ring" data-element="{aid}">
    <path d="M160 230 L160 18" stroke="#df2a22" stroke-width="6"
          stroke-dasharray="10 9" marker-end="url(#{prefix}-red)"/>
    {loops}
    <text x="26" y="71" font-family="DejaVu Serif, Times" font-size="25"
          font-style="italic" font-weight="700" fill="#111">J</text>
    <text x="125" y="125" font-family="DejaVu Serif, Times" font-size="22"
          font-style="italic" fill="#333">ω</text>
    {'' if nest else '<circle cx="262" cy="142" r="31" fill="#060708"/><text x="262" y="150" text-anchor="middle" font-family="DejaVu Sans, Arial" font-size="18" fill="#fff">q<tspan dy="-5" font-size="13">e</tspan></text>'}
  </g>
</svg>
"""


def event_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    if "z_target" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 110 100"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="z-axis-symbol" data-element="{aid}">
    <circle cx="42" cy="50" r="27" fill="#fff" stroke="#25313d" stroke-width="4"/>
    <circle cx="42" cy="50" r="10" fill="#25313d"/>
    <text x="78" y="64" font-family="DejaVu Serif, Times" font-size="42"
          font-style="italic" fill="#111">z</text>
  </g>
</svg>
"""
    if "topology" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {marker_defs(prefix)}
    <radialGradient id="{prefix}-event" cx=".42" cy=".38" r=".68">
      <stop offset="0" stop-color="#bff4ef"/><stop offset="1" stop-color="#258f9c"/>
    </radialGradient>
    <linearGradient id="{prefix}-cone" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#f6d46c"/><stop offset="1" stop-color="#e28b43"/>
    </linearGradient>
  </defs>
  <g id="event-topology" data-element="{aid}">
    <path d="M160 332 L160 35" stroke="#111" stroke-width="3" marker-end="url(#{prefix}-arrow)"/>
    <path d="M40 248 L338 248" stroke="#111" stroke-width="3" marker-end="url(#{prefix}-arrow)"/>
    <path d="M160 248 L246 184" stroke="#111" stroke-width="3"/>
    <text x="148" y="22" font-family="DejaVu Serif, Times" font-size="24" font-style="italic">y</text>
    <text x="342" y="278" font-family="DejaVu Serif, Times" font-size="24" font-style="italic">x</text>
    <circle cx="160" cy="235" r="74" fill="url(#{prefix}-event)" opacity=".86"/>
    <path d="M160 235 L286 92 L336 126 L222 257 Z"
          fill="url(#{prefix}-cone)" opacity=".74"/>
    <path d="M160 235 L30 326 L70 354 L207 270 Z"
          fill="url(#{prefix}-cone)" opacity=".76"/>
    {''.join(f'<path d="M160 235 L{160+63*math.cos(a):.1f} {235+63*math.sin(a):.1f}" stroke="#1c5e97" stroke-width="2.3" stroke-dasharray="7 6" marker-end="url(#{prefix}-arrow)"/>' for a in [i*math.pi/4 for i in range(8)])}
    <path d="M188 214 L285 111" stroke="#b4512d" stroke-width="3.2" stroke-dasharray="7 6" marker-end="url(#{prefix}-arrow)"/>
    <path d="M135 250 L55 329" stroke="#b4512d" stroke-width="3.2" stroke-dasharray="7 6" marker-end="url(#{prefix}-arrow)"/>
    <path d="M160 235 L300 105" stroke="#2f8f3b" stroke-width="3" stroke-dasharray="8 6" marker-end="url(#{prefix}-arrow)"/>
    <text x="305" y="94" font-family="DejaVu Serif, Times" font-size="22" font-style="italic" fill="#236e23">n</text>
    <circle cx="329" cy="36" r="13" fill="#fff" stroke="#111" stroke-width="3"/>
    <circle cx="329" cy="36" r="4" fill="#111"/>
    <text x="347" y="49" font-family="DejaVu Serif, Times" font-size="24" font-style="italic">z</text>
  </g>
</svg>
"""
    if "jetty" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 220"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>{marker_defs(prefix)}</defs>
  <g id="jetty-cone" data-element="{aid}">
    <circle cx="62" cy="164" r="46" fill="#66c8c6" opacity=".72"/>
    <path d="M62 164 L212 62 L262 98 Z" fill="#f4be48" opacity=".82"/>
    <path d="M62 164 L205 67" stroke="#b6572c" stroke-width="4" stroke-dasharray="8 6"/>
    <path d="M83 147 L226 70" stroke="#b6572c" stroke-width="4" stroke-dasharray="8 6" marker-end="url(#{prefix}-arrow)"/>
    <path d="M100 171 L245 103" stroke="#b6572c" stroke-width="4" stroke-dasharray="8 6" marker-end="url(#{prefix}-arrow)"/>
    <path d="M62 164 L270 41" stroke="#31963d" stroke-width="3" stroke-dasharray="9 7"/>
    <text x="275" y="35" font-family="DejaVu Serif, Times" font-size="22" font-style="italic" fill="#236e23">n</text>
  </g>
</svg>
"""
    if "isotropic_cone" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 220"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>{marker_defs(prefix)}</defs>
  <g id="isotropic-cone" data-element="{aid}">
    <path d="M230 150 L66 64 L27 93 L189 188 Z" fill="#f1bf51" opacity=".84"/>
    <path d="M230 150 L57 72 M230 150 L51 115 M230 150 L60 161"
          stroke="#c8502b" stroke-width="4" stroke-dasharray="8 6"
          marker-end="url(#{prefix}-arrow)"/>
    <circle cx="230" cy="150" r="58" fill="#72d0cd" opacity=".58"/>
  </g>
</svg>
"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {marker_defs(prefix)}
    <radialGradient id="{prefix}-event" cx=".4" cy=".35" r=".68">
      <stop offset="0" stop-color="#c5f6ee"/><stop offset="1" stop-color="#2f969d"/>
    </radialGradient>
  </defs>
  <g id="event-source" data-element="{aid}">
    <circle cx="150" cy="154" r="104" fill="url(#{prefix}-event)" opacity=".84"/>
    {''.join(f'<path d="M150 154 L{150+91*math.cos(a):.1f} {154+91*math.sin(a):.1f}" stroke="#1d5d98" stroke-width="3" stroke-dasharray="8 7" marker-end="url(#{prefix}-arrow)"/>' for a in [i*math.pi/4 for i in range(8)])}
  </g>
</svg>
"""


def detector_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    if "tof_arc" in aid:
        segs = "".join(
            f'<path d="M{25+i*34} 66 A150 150 0 0 1 {55+i*34} 18" '
            f'stroke="#d5aa24" stroke-width="26" fill="none"/>'
            for i in range(9)
        )
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 340 100"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="tof-arc" data-element="{aid}">
    <path d="M20 86 A180 180 0 0 1 320 86" stroke="#805e18" stroke-width="36" fill="none"/>
    {segs}
  </g>
</svg>
"""
    if "vertex" in aid or "track_bundle" in aid:
        size = 280
        center = (150, 150)
        lines = []
        for i in range(32):
            angle = i * 2 * math.pi / 32
            x = 150 + 112 * math.cos(angle)
            y = 150 + 112 * math.sin(angle)
            color = "#9ca5ad"
            if i in {6, 7, 8}:
                color = "#1d46bd"
            elif i in {18, 19, 20}:
                color = "#d9212e"
            lines.append(
                f'<path d="M{center[0]} {center[1]} Q{(center[0]+x)/2+18*math.sin(angle):.1f} '
                f'{(center[1]+y)/2-18*math.cos(angle):.1f} {x:.1f} {y:.1f}" '
                f'fill="none" stroke="{color}" stroke-width="1.5" opacity=".82"/>'
            )
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="particle-tracks" data-element="{aid}">
    {''.join(lines)}
    <circle cx="150" cy="150" r="4" fill="#111"/>
  </g>
</svg>
"""
    seg = "".join(
        f'<path d="M{200+167*math.cos(a):.1f} {200+167*math.sin(a):.1f} '
        f'L{200+188*math.cos(a):.1f} {200+188*math.sin(a):.1f}" '
        f'stroke="#fff3b0" stroke-width="2" opacity=".72"/>'
        for a in [i*2*math.pi/72 for i in range(72)]
    )
    tracks = ""
    for i in range(28):
        angle = i * 2 * math.pi / 28 + 0.04 * math.sin(i * 1.7)
        c1a = angle - 0.55 - 0.22 * math.cos(i * .8)
        c2a = angle + 0.28 + 0.16 * math.sin(i * 1.13)
        c1r = 55 + 24 * math.sin(i * .6)
        c2r = 105 + 18 * math.cos(i * .9)
        ex, ey = 200 + 151 * math.cos(angle), 200 + 151 * math.sin(angle)
        color = "#1d46bd" if i in (7, 8) else "#d9212e" if i in (20, 21) else "#a5adb4"
        width = 2.2 if i in (7, 8, 20, 21) else 1.0
        tracks += (
            f'<path d="M200 200 C{200+c1r*math.cos(c1a):.1f} '
            f'{200+c1r*math.sin(c1a):.1f} '
            f'{200+c2r*math.cos(c2a):.1f} {200+c2r*math.sin(c2a):.1f} '
            f'{ex:.1f} {ey:.1f}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" opacity=".8"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-gold" cx=".45" cy=".4" r=".7">
      <stop offset="0" stop-color="#fff08a"/><stop offset="1" stop-color="#a6740f"/>
    </radialGradient>
  </defs>
  <g id="detector-ring" data-element="{aid}">
    <circle cx="200" cy="200" r="183" fill="none" stroke="url(#{prefix}-gold)" stroke-width="34"/>
    <circle cx="200" cy="200" r="158" fill="#fff"/>
    {seg}
    {tracks}
    <circle cx="200" cy="200" r="3" fill="#111"/>
  </g>
</svg>
"""


def flow_arrow_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    right = "right" in aid
    if right:
        body = "M18 52 L102 52 L102 22 L164 65 L102 108 L102 78 L18 78 Z"
        vb = "0 0 180 130"
    else:
        body = "M54 125 L90 52 L90 92 L108 92 L108 52 L144 125 Z"
        vb = "0 0 180 150"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <linearGradient id="{prefix}-g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#d7e6ff"/>
      <stop offset=".52" stop-color="#91b2e4"/>
      <stop offset="1" stop-color="#597fb7"/>
    </linearGradient>
  </defs>
  <g id="partonic-flow-arrow" data-element="{aid}">
    <path d="{body}" fill="url(#{prefix}-g)" stroke="#587fb5" stroke-width="1.3"/>
  </g>
</svg>
"""


def nucleus_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    if "shape_" in aid:
        idx = int(aid.rsplit("_", 1)[-1])
        rx, ry = [(78, 52), (70, 58), (82, 47), (64, 60), (75, 49), (79, 62)][idx - 1]
        tilt = [-14, 18, -29, 12, -21, 24][idx - 1]
        grid = "".join(
            f'<ellipse cx="0" cy="0" rx="{rx}" ry="{ry*f:.2f}" fill="none" '
            f'stroke="#56606a" stroke-width=".65" opacity=".55"/>'
            for f in (0.22, 0.45, 0.68)
        )
        grid += "".join(
            f'<ellipse cx="0" cy="0" rx="{rx*f:.2f}" ry="{ry}" fill="none" '
            f'stroke="#56606a" stroke-width=".55" opacity=".36"/>'
            for f in (0.28, 0.56, 0.82)
        )
        spots = ""
        for i in range(15):
            sx = 130 + rx * 0.68 * math.sin(i * 2.17)
            sy = 110 + ry * 0.68 * math.cos(i * 1.63)
            spots += (
                f'<ellipse cx="{sx:.1f}" cy="{sy:.1f}" rx="{rx*(.18+.08*(i%3)):.1f}" '
                f'ry="{ry*(.12+.05*(i%2)):.1f}" '
                f'fill="{"#ffffff" if i%3 else "#29323b"}" '
                f'opacity="{.11+.05*(i%4)}" filter="url(#{prefix}-blur)"/>'
            )
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 220"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-n" cx=".38" cy=".3" r=".75">
      <stop offset="0" stop-color="#d9dde2"/>
      <stop offset=".55" stop-color="#96a0aa"/>
      <stop offset="1" stop-color="#48525d"/>
    </radialGradient>
    <filter id="{prefix}-blur"><feGaussianBlur stdDeviation="7"/></filter>
    <clipPath id="{prefix}-clip"><ellipse cx="130" cy="110" rx="{rx}" ry="{ry}"/></clipPath>
  </defs>
  <g id="nucleus-shape" data-element="{aid}"
     transform="translate(130 110) rotate({tilt})">
    <ellipse cx="0" cy="0" rx="{rx}" ry="{ry}" fill="url(#{prefix}-n)"
             stroke="#414b55" stroke-width="1.4"/>
    <g clip-path="url(#{prefix}-clip)" transform="translate(-130 -110)">{spots}{grid}</g>
    <ellipse cx="-25" cy="-27" rx="24" ry="13" fill="#fff" opacity=".28"/>
  </g>
</svg>
"""
    double = "body_body" in aid or "tip_tip" in aid
    if double:
        rotate = -8 if "body_body" in aid else 78
        def cluster(prefix_name: str) -> str:
            bits = []
            for i in range(40):
                a = i * 2.399963
                rr = math.sqrt((i + 0.5) / 40)
                x = 74 * rr * math.cos(a)
                y = 51 * rr * math.sin(a)
                color = "red" if i % 3 else "blue"
                bits.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{6.3 if rr>.25 else 5.2}" '
                    f'fill="url(#{prefix}-{color})" stroke="#6d747d" '
                    f'stroke-width=".35"/>'
                    f'<circle cx="{x-2:.1f}" cy="{y-2.2:.1f}" r="1.8" fill="#fff" opacity=".36"/>'
                )
            return "".join(bits)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 220"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-n" cx=".38" cy=".28" r=".74">
      <stop offset="0" stop-color="#ecedef"/><stop offset=".62" stop-color="#9ca3aa"/>
      <stop offset="1" stop-color="#444b52"/>
    </radialGradient>
    <radialGradient id="{prefix}-red" cx=".34" cy=".28" r=".72">
      <stop offset="0" stop-color="#ffd7d7"/><stop offset=".28" stop-color="#ef7779"/>
      <stop offset="1" stop-color="#982d3a"/>
    </radialGradient>
    <radialGradient id="{prefix}-blue" cx=".34" cy=".28" r=".72">
      <stop offset="0" stop-color="#d7e3ff"/><stop offset=".28" stop-color="#6f8fd6"/>
      <stop offset="1" stop-color="#304f91"/>
    </radialGradient>
  </defs>
  <g id="incoming-nuclei" data-element="{aid}">
    <g transform="translate(103 110) rotate({rotate})">
      <ellipse rx="79" ry="56" fill="url(#{prefix}-n)" stroke="#444b52"/>
      {cluster("left")}
    </g>
    <g transform="translate(257 110) rotate({-rotate})">
      <ellipse rx="79" ry="56" fill="url(#{prefix}-n)" stroke="#444b52"/>
      {cluster("right")}
    </g>
  </g>
</svg>
"""
    nucleons = ""
    fills = [f"url(#{prefix}-red)", f"url(#{prefix}-blue)"]
    for i in range(34):
        angle = i * 2.399963
        radius = 82 * math.sqrt((i + 0.5) / 34)
        x = 130 + radius * math.cos(angle)
        y = 152 + radius * 0.62 * math.sin(angle)
        fill = fills[i % 2]
        nucleons += (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.2" fill="{fill}" '
            f'stroke="#fff" stroke-opacity=".45" stroke-width=".7"/>'
            f'<circle cx="{x-2.4:.1f}" cy="{y-2.6:.1f}" r="2.2" fill="#fff" opacity=".45"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 300"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-red" cx=".34" cy=".28" r=".72">
      <stop offset="0" stop-color="#ffd7d7"/><stop offset=".28" stop-color="#ef7779"/>
      <stop offset="1" stop-color="#982d3a"/>
    </radialGradient>
    <radialGradient id="{prefix}-blue" cx=".34" cy=".28" r=".72">
      <stop offset="0" stop-color="#d7e3ff"/><stop offset=".28" stop-color="#6f8fd6"/>
      <stop offset="1" stop-color="#304f91"/>
    </radialGradient>
  </defs>
  <g id="prolate-nucleus" data-element="{aid}">
    <ellipse cx="130" cy="151" rx="102" ry="111" fill="#cbd8e6" opacity=".18"/>
    {nucleons}
    <ellipse cx="130" cy="151" rx="103" ry="112" fill="none"
             stroke="#46556a" stroke-width="1.4" stroke-dasharray="6 5"/>
  </g>
</svg>
"""


def qgp_svg(asset: dict) -> str:
    aid = asset["id"]
    fireball = "fireball" in aid
    cart = Cartoon(320, 300, bg="none")
    cart.begin_layer("qgp-medium", "QGP volume, density fluctuations and rim")
    if fireball:
        cart.qgp_fireball(160, 150, 102, vortices=7, ring=True, glow=True)
        cart.add(
            '<path d="M48 156 C48 53 254 43 274 145 C286 250 78 290 48 156 Z" '
            'fill="none" stroke="#6f55bd" stroke-width="3" opacity=".45"/>'
        )
        cart.add(
            '<path d="M68 95 C133 49 231 55 260 115" fill="none" '
            'stroke="#6f55bd" stroke-width="2" opacity=".40"/>'
        )
    else:
        cart.qgp_blob(
            160, 152, 112, ry=.76, seed=31, glow=1.25,
            n_spots=22, wobble=.10,
        )
    cart.end_layer()
    return cartoon_svg(cart, aid, "qgp-medium")


def t330_qgp_fireball_svg(asset: dict) -> str:
    """Native redraw of the T3-30 electromagnetic fireball crop.

    The perspective grid, purple field lines and external arrows are separate
    physical/context layers in the source and must not be baked into a QGP
    element. This redraw keeps the fireball, radiation and partons only.
    """
    aid = asset["id"]
    prefix = slug(aid)
    silhouette = ""
    crop_rel = (asset.get("generation") or {}).get("crop_file")
    if crop_rel:
        try:
            import cv2
            import numpy as np
            from PIL import Image

            alpha = np.asarray(
                Image.open(LIB / crop_rel).convert("RGBA")
            )[:, :, 3]
            contours, _ = cv2.findContours(
                (alpha > 0).astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_NONE,
            )
            if contours:
                contour = max(contours, key=cv2.contourArea)
                points = cv2.approxPolyDP(contour, 0.8, True)[:, 0, :]
                silhouette = (
                    "M" + " L".join(f"{int(x)} {int(y)}" for x, y in points) + " Z"
                )
        except Exception:
            silhouette = ""
    particle_specs = [
        (290, 131, 16, "cyan"), (383, 158, 13, "violet"),
        (207, 211, 12, "yellow"), (447, 235, 12, "yellow"),
        (356, 237, 8, "orange"), (283, 254, 8, "violet"),
        (293, 273, 8, "orange"), (401, 283, 7, "cream"),
        (241, 312, 10, "gray"), (447, 342, 11, "gray"),
        (319, 343, 8, "orange"), (293, 352, 8, "orange"),
        (372, 381, 8, "cream"), (272, 401, 11, "violet"),
        (342, 438, 8, "yellow"),
    ]
    colors = {
        "cyan": ("#d9ffff", "#58d6df", "#16848f"),
        "violet": ("#efc4ff", "#a44dcc", "#5f1f77"),
        "yellow": ("#fff7be", "#f2c33c", "#8f6904"),
        "cream": ("#ffffff", "#e7ddcb", "#8e8577"),
        "orange": ("#ffe4a8", "#f39a36", "#9c4a0c"),
        "gray": ("#f0f1f3", "#a9aeb4", "#62686f"),
    }
    defs = []
    balls = []
    for index, (cx, cy, radius, key) in enumerate(particle_specs):
        light, mid, dark = colors[key]
        gid = f"{prefix}-part-{index}"
        defs.append(
            f'<radialGradient id="{gid}" cx=".34" cy=".28" r=".72">'
            f'<stop offset="0" stop-color="{light}"/>'
            f'<stop offset=".25" stop-color="{mid}"/>'
            f'<stop offset="1" stop-color="{dark}"/>'
            f"</radialGradient>"
        )
        balls.append(
            f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="url(#{gid})" '
            f'stroke="{dark}" stroke-width="1"/>'
            f'<circle cx="{cx - radius * .3:.1f}" cy="{cy - radius * .32:.1f}" '
            f'r="{radius * .24:.1f}" fill="#fff" opacity=".48"/>'
        )
    rays = []
    for index in range(28):
        angle = math.radians(index * 360 / 28 + 2)
        x1 = 280 + 18 * math.cos(angle)
        y1 = 318 + 14 * math.sin(angle)
        length = 178 if index % 3 else 214
        x2 = 280 + length * math.cos(angle)
        y2 = 318 + 0.62 * length * math.sin(angle)
        rays.append(
            f'<path d="M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}" '
            'stroke="#ee8a2d" stroke-width="2.3" stroke-linecap="round" opacity=".72"/>'
        )
    spirals = []
    for cx, cy, scale in ((324, 180, 1.0), (208, 272, .9), (405, 350, .8), (286, 360, .72)):
        loop = [f"M{cx - 15 * scale:.1f} {cy:.1f}"]
        for i in range(1, 5):
            loop.append(
                f"C{cx - 17 * scale:.1f} {cy - 13 * scale:.1f} "
                f"{cx + 17 * scale:.1f} {cy - 13 * scale:.1f} "
                f"{cx + 12 * scale:.1f} {cy:.1f} "
                f"C{cx + 9 * scale:.1f} {cy + 12 * scale:.1f} "
                f"{cx - 10 * scale:.1f} {cy + 12 * scale:.1f} "
                f"{cx - 8 * scale:.1f} {cy:.1f}"
            )
            cx += 17 * scale
        spirals.append(
            f'<path d="{" ".join(loop)}" fill="none" stroke="#4a3b36" '
            'stroke-width="2.2" stroke-linecap="round" opacity=".82"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 550 450"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    {''.join(defs)}
    <radialGradient id="{prefix}-halo" cx=".5" cy=".58" r=".52">
      <stop offset="0" stop-color="#ff9b3d" stop-opacity=".92"/>
      <stop offset=".48" stop-color="#f47d45" stop-opacity=".68"/>
      <stop offset=".78" stop-color="#e7805f" stop-opacity=".28"/>
      <stop offset="1" stop-color="#efb09d" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="{prefix}-body" cx=".50" cy=".60" r=".62" fx=".52" fy=".43">
      <stop offset="0" stop-color="#fff2a2"/>
      <stop offset=".12" stop-color="#ffd66f"/>
      <stop offset=".40" stop-color="#ffab54"/>
      <stop offset=".73" stop-color="#ef6d3f"/>
      <stop offset=".92" stop-color="#df5736" stop-opacity=".90"/>
      <stop offset="1" stop-color="#d24a31" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="{prefix}-shade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#d34b29" stop-opacity="0"/>
      <stop offset=".55" stop-color="#d4522f" stop-opacity=".05"/>
      <stop offset="1" stop-color="#9f3528" stop-opacity=".24"/>
    </linearGradient>
    <radialGradient id="{prefix}-core" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#fffce7"/>
      <stop offset=".16" stop-color="#fff38b"/>
      <stop offset=".52" stop-color="#ffd05f" stop-opacity=".78"/>
      <stop offset="1" stop-color="#ffb84c" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="{prefix}-clip"><path d="{silhouette}"/></clipPath>
  </defs>
  <g id="qgp-medium" data-element="{aid}">
    <ellipse cx="285" cy="280" rx="224" ry="182" fill="url(#{prefix}-halo)"/>
    <path d="{silhouette}" fill="url(#{prefix}-body)"/>
    <path d="{silhouette}" fill="none" stroke="#e85d3a"
          stroke-width="3.2" opacity=".28"/>
    <path d="{silhouette}" fill="none" stroke="#ffb37d"
          stroke-width="1.1" opacity=".58"/>
    <g clip-path="url(#{prefix}-clip)">
      <ellipse cx="281" cy="340" rx="205" ry="100" fill="url(#{prefix}-shade)"/>
    </g>
    <g id="radiation-rays">{''.join(rays)}</g>
    <ellipse cx="280" cy="318" rx="88" ry="58" fill="url(#{prefix}-core)"/>
    <g id="partons">{''.join(balls)}</g>
    <g id="parton-spirals">{''.join(spirals)}</g>
  </g>
</svg>
"""


def medium_trace_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    shell = "shell" in aid
    if shell:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-shell" cx=".45" cy=".42" r=".65">
      <stop offset="0" stop-color="#d8dde2"/><stop offset=".72" stop-color="#9ea7b0"/>
      <stop offset="1" stop-color="#747d85"/>
    </radialGradient>
  </defs>
  <g id="hadronizing-shell" data-element="{aid}">
    <ellipse cx="130" cy="180" rx="89" ry="145" fill="url(#{prefix}-shell)"
             stroke="#59636d" stroke-width="1.5"/>
    <ellipse cx="130" cy="180" rx="65" ry="117" fill="#f4f5f6" opacity=".7"/>
    {''.join(f'<path d="M{52+13*i} 123 C{105+6*i} {94+3*i} {129+4*i} {164-2*i} {126+7*i} {244+2*i}" fill="none" stroke="#63707b" stroke-width=".8" opacity=".7"/>' for i in range(11))}
  </g>
</svg>
"""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>
    <radialGradient id="{prefix}-hard" cx=".48" cy=".45" r=".6">
      <stop offset="0" stop-color="#fff8da"/><stop offset=".45" stop-color="#efd9ad"/>
      <stop offset=".85" stop-color="#c6ac86"/><stop offset="1" stop-color="#9e8665" stop-opacity=".15"/>
    </radialGradient>
  </defs>
  {marker_defs(prefix)}
  <g id="hadronic-medium" data-element="{aid}">
    <rect x="18" y="18" width="224" height="324" rx="36" fill="url(#{prefix}-hard)" opacity=".72"/>
    {''.join(f'<path d="M{82+24*i} {90+42*i%210} l{28*(1 if i%2 else -1)} {-24 if i%3 else 30}" stroke="#4a3b2d" stroke-width="2" fill="none" marker-end="url(#{prefix}-arrow)"/>' for i in range(12))}
    {''.join(f'<circle cx="{78+41*(i%5)}" cy="{86+44*(i//5)}" r="3.2" fill="{["#429cc1","#f4cf54","#b75fc8"][i%3]}"/>' for i in range(15))}
  </g>
</svg>
"""


def detector_cutaway_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    if "tracker_face" in aid:
        return detector_svg(asset)
    if "eic" in aid:
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 300"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="eic-spectrometer" data-element="{aid}">
    <path d="M20 168 L340 168" stroke="#46515c" stroke-width="7"/>
    <path d="M20 145 C115 145 145 154 182 166 C215 176 272 174 335 139"
          fill="none" stroke="#68a9d2" stroke-width="3" opacity=".75"/>
    <path d="M20 191 C115 191 145 181 182 168 C215 158 272 160 335 198"
          fill="none" stroke="#d07b56" stroke-width="3" opacity=".75"/>
    {''.join(f'<ellipse cx="{72+i*43}" cy="168" rx="{13+i%2*4}" ry="{38+i*8}" '
             f'fill="none" stroke="{["#b35b63","#d3a83f","#4e80bd","#6f8e83"][i%4]}" stroke-width="8" opacity=".92"/>'
             f'<path d="M{72+i*43} {168-(38+i*8)} L{72+i*43} {168+(38+i*8)}" '
             f'stroke="{["#b35b63","#d3a83f","#4e80bd","#6f8e83"][i%4]}" stroke-width="5"/>'
             for i in range(7))}
    <circle cx="183" cy="167" r="6" fill="#f1c84b"/>
  </g>
</svg>
"""
    star = "star" in aid
    radii = [44, 66, 88, 112, 138] if star else [40, 60, 82, 104, 126]
    colors = ["#3f76b8", "#a95f74", "#caa73c", "#718d87", "#9aa0a6"]
    shells = '<path d="M82 180 L314 180" stroke="#4a535d" stroke-width="6"/>'
    for i, r in enumerate(radii):
        shells += (
            f'<ellipse cx="315" cy="180" rx="{r*.27:.1f}" ry="{r*.62:.1f}" '
            f'fill="none" stroke="{colors[i]}" stroke-width="{16 if i in (1,3) else 10}" opacity=".92"/>'
            f'<ellipse cx="90" cy="180" rx="{r*.27:.1f}" ry="{r*.62:.1f}" '
            f'fill="none" stroke="{colors[i]}" stroke-width="{12 if i in (1,3) else 7}" opacity=".56"/>'
            f'<path d="M90 {180-r*.62:.1f} L315 {180-r*.62:.1f} '
            f'M90 {180+r*.62:.1f} L315 {180+r*.62:.1f}" '
            f'stroke="{colors[i]}" stroke-width="{14 if i in (1,3) else 8}" opacity=".9"/>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <g id="detector-cutaway" data-element="{aid}">
    {shells}
    <path d="M315 92 A90 90 0 0 0 315 268 Z" fill="#ffffff" opacity=".2"/>
    <ellipse cx="315" cy="180" rx="22" ry="22" fill="#f0c325"/>
    <circle cx="315" cy="180" r="5" fill="#fff"/>
  </g>
</svg>
"""


def field_arrow_svg(asset: dict) -> str:
    aid = asset["id"]
    prefix = slug(aid)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 90 360"
     data-element-asset="{aid}" data-origin="article_vector_native">
  <defs>{marker_defs(prefix)}</defs>
  <g id="magnetic-field-arrow" data-element="{aid}">
    <path d="M45 330 L45 28" stroke="#e33529" stroke-width="8"
          stroke-linecap="round" marker-end="url(#{prefix}-arrow)"/>
    <path d="M45 312 C15 270 72 230 38 190 C8 150 72 116 45 74"
          fill="none" stroke="#6f56bd" stroke-width="2.3" opacity=".58"/>
  </g>
</svg>
"""


def draw(asset: dict, allow_existing: bool = False) -> str | None:
    aid = asset["id"]
    fam = asset.get("family")
    origin = (asset.get("generation") or {}).get("origin")
    if origin != "article_vector_trace" and not allow_existing:
        return None
    if fam == "nucleon":
        return sphere_svg(asset)
    if fam == "quark" and "article_pmc130" in aid:
        return pair_svg(asset)
    if fam == "quark" and "article_t311" in aid:
        return quark_svg(asset)
    if aid in {"article_pmc130_medium_left", "article_pmc130_medium_outer"}:
        return medium_svg(asset)
    if aid.startswith("article_pmc701_"):
        return vortex_svg(asset)
    if aid.startswith("article_pmc891_"):
        return event_svg(asset)
    if aid.startswith("article_pmc125_"):
        return detector_svg(asset)
    if aid.startswith("article_pmc130_flow_arrow"):
        return flow_arrow_svg(asset)
    if fam == "nucleus" and "article_t302" in aid:
        return nucleus_svg(asset)
    if fam == "qgp" and "article_t302" in aid:
        return qgp_svg(asset)
    if aid == "article_t330_qgp_fireball":
        return t330_qgp_fireball_svg(asset)
    if fam == "qgp" and "article_t330" in aid:
        return qgp_svg(asset)
    if fam == "qgp" and "article_t312" in aid:
        return medium_trace_svg(asset)
    if fam == "detector-layer" and aid in {
        "article_t321_tracker_face", "article_t311_cms_detector",
        "article_t331_star_cutaway", "article_t72_eic_detector",
    }:
        return detector_cutaway_svg(asset)
    if fam == "gauge-field" and aid == "article_t334_magnetic_arrow":
        return field_arrow_svg(asset)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Native-redraw selected article elements")
    ap.add_argument("--check", action="store_true",
                    help="report selected IDs without writing")
    ap.add_argument("--ids", nargs="*", default=[],
                    help="override the automatic element selection")
    a = ap.parse_args()
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    wanted = set(a.ids)
    selected = []
    for asset in doc["assets"]:
        if wanted and asset["id"] not in wanted:
            continue
        svg = draw(asset, allow_existing=bool(wanted))
        if svg is not None:
            selected.append((asset, svg))
    if a.check:
        print("\n".join(asset["id"] for asset, _ in selected))
        return 0

    for asset, svg in selected:
        gen = asset.setdefault("generation", {})
        edit_rel = gen.get("edit_file")
        out = LIB / edit_rel if edit_rel and (LIB / edit_rel).exists() else LIB / asset["file"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
        vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
        gen.update({
            "origin": "article_vector_native",
            "ai_generated": False,
            "contains_ai_pixels": False,
            "tool": "rebuild_article_vectors.py",
            "model": None,
            "redraw_method": (
                "object-level native SVG geometry with editable gradients; "
                "source crop used as the visual/physical reference, not embedded"
            ),
            "processing": (
                "native geometry redraw; circles/paths/gradients/native text only; "
                "no embedded raster and no AI pixels"
            ),
        })
        gen["edit_sha256"] = sha256(out)
        asset["viewBox"] = vb
        asset["anchor"] = [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2]
        asset["review"] = {
            **asset.get("review", {}),
            "status": "manual-reviewed",
            "reviewed_by": "repository-maintainers",
            "reviewed_at": TODAY,
            "note": "native redraw checked against source crop; not a pixel-level trace",
        }
        asset["sha256"] = sha256(out)
        print(f"{asset['id']}: native {vb}")
    doc["updated"] = TODAY
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    lines = [
        "# Native article-derived element notices",
        "",
        "These SVGs are object-level redraws based on the cited CC BY figure",
        "regions. They contain editable geometry, gradients and native text, not",
        "embedded raster, traced pixel clusters or AI-generated pixels.",
        "",
    ]
    native = [
        asset for asset in doc["assets"]
        if (asset.get("generation") or {}).get("origin") == "article_vector_native"
    ]
    held = [
        asset for asset in native
        if (asset.get("review") or {}).get("status") not in {
            "verified", "reviewed", "manual-reviewed",
        }
    ]
    if held:
        lines += [
            "> Held assets are excluded from safe mode pending an accepted redraw: "
            + ", ".join(f"`{asset['id']}`" for asset in held),
            "",
        ]
    lines += [
        "| Element | Source asset | Source crop | Method | Review |",
        "|---|---|---|---|---|",
    ]
    for asset in native:
        gen = asset["generation"]
        lines.append(
            f"| `{asset['id']}` | `{gen.get('source_asset_id', '')}` | "
            f"`{gen.get('source_bbox_px', '')}` | native geometry redraw | "
            f"`{(asset.get('review') or {}).get('status', '')}` |"
        )
    (LIB / "source-derived" / "NATIVE_NOTICE.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    trace_assets = [
        asset for asset in doc["assets"]
        if (asset.get("generation") or {}).get("origin") == "article_vector_trace"
    ]
    trace_lines = ["# Source-derived element notices", ""]
    if trace_assets:
        trace_lines += ["| Element | Source asset | Crop px |", "|---|---|---|"]
        for asset in trace_assets:
            gen = asset["generation"]
            trace_lines.append(
                f"| `{asset['id']}` | `{gen.get('source_asset_id', '')}` | "
                f"`{gen.get('source_bbox_px', '')}` |"
            )
    else:
        trace_lines.append(
            "No active element uses pixel tracing. See `NATIVE_NOTICE.md`."
        )
    trace_lines.append("")
    (LIB / "source-derived" / "NOTICE.md").write_text(
        "\n".join(trace_lines), encoding="utf-8"
    )
    print(f"rebuilt {len(selected)} native article elements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
