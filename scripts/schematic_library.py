#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""License-aware HEP schematic asset library.

The library has two jobs:
  1. index figures that are genuinely useful as visual references;
  2. keep copyrighted figures out of the repository while preserving enough
     provenance to retrieve them lawfully.

Only CC0 / CC BY images are copied to ``redistributable/``. Subscription,
default-license arXiv, NC, and ND figures remain metadata-only records.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "schematic-library"
CATALOG = LIB / "catalog.json"
TAXONOMY = LIB / "taxonomy.json"
QUERIES = LIB / "queries.json"
CANDIDATES = LIB / "candidates.jsonl"
REPORT = LIB / "discovery_report.json"
CROSSREF_REPORT = LIB / "crossref_report.json"
EXEMPLARS = ROOT / "assets" / "t3-exemplars"
REDISTRIBUTABLE = LIB / "redistributable"

MAILTO = "pngyuo@cug.edu.cn"
USER_AGENT = "hep-nature-figure/5.1 (mailto:pngyuo@cug.edu.cn)"
TODAY = dt.date.today().isoformat()

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
SCHEMATIC_WORDS = {
    "cartoon", "schematic", "illustration", "diagram", "depiction", "sketch",
    "workflow", "timeline", "geometry", "geometric", "visualization",
    "visualisation", "concept", "conceptual", "spacetime", "space-time",
    "phase diagram", "detector layout", "beamline",
}

HEP_STRONG_RE = re.compile(
    r"heavy[- ]ion|relativistic nuclear|nuclear collision|"
    r"quark[- ]gluon|\bqgp\b|\bqcd\b|quarkonium|"
    r"jet quench|parton|nucleon|nuclear structure|"
    r"collective flow|elliptic flow|chiral magnetic|"
    r"spin polarization|lambda hyperon|ultra[- ]peripheral|"
    r"photonuclear|electron[- ]ion collider|\beic\b|"
    r"particle collider|heavy[- ]flavor|color glass|"
    r"proton[- ](?:lead|nucleus) collision|nuclear modification|"
    r"hadron(?:ic|ization|production|collider)|"
    r"relativistic heavy[- ]?ion|event[- ]by[- ]event",
    re.I,
)

LEGACY_TOPIC_MAP = {
    "T3-01": ["initial-state", "qgp"],
    "T3-02": ["nuclear-structure", "qgp"],
    "T3-03": ["spin-polarization", "qgp"],
    "T3-11": ["qgp", "detectors"],
    "T3-12": ["hadronization", "qgp"],
    "T3-20": ["phase-transition", "qgp"],
    "T3-21": ["detectors", "qgp"],
    "T3-22": ["phase-transition", "qgp"],
    "T3-23": ["observables", "hadronization"],
    "T3-30": ["initial-state", "qgp", "electromagnetic-fields"],
    "T3-31": ["detectors"],
    "T3-34": ["initial-state", "electromagnetic-fields"],
    "T3-35": ["initial-state", "spin-polarization"],
    "T3-36": ["initial-state", "electromagnetic-fields"],
    "T3-60": ["upc", "nuclear-structure"],
    "T3-72": ["eic", "detectors"],
    "T3-73": ["detectors"],
}

LEGACY_TYPE_MAP = {
    "T3-01": ["3d-illustration", "timeline", "spacetime-evolution"],
    "T3-02": ["3d-illustration", "timeline", "spacetime-evolution"],
    "T3-03": ["3d-illustration", "geometry-diagram"],
    "T3-11": ["3d-illustration", "detector-cutaway"],
    "T3-12": ["3d-illustration"],
    "T3-20": ["phase-diagram"],
    "T3-21": ["detector-cutaway"],
    "T3-22": ["phase-diagram"],
    "T3-23": ["timeline", "geometry-diagram"],
    "T3-30": ["3d-illustration", "geometry-diagram"],
    "T3-31": ["3d-illustration", "detector-cutaway"],
    "T3-34": ["3d-illustration", "geometry-diagram"],
    "T3-35": ["3d-illustration", "geometry-diagram"],
    "T3-36": ["3d-illustration", "geometry-diagram"],
    "T3-60": ["3d-illustration", "geometry-diagram"],
    "T3-72": ["3d-illustration", "detector-cutaway"],
    "T3-73": ["3d-illustration", "detector-cutaway"],
}

LEGACY_METADATA = {
    "T3-04": {
        "paper_title": "Chiral magnetic effect reveals the topology of gauge fields in heavy-ion collisions",
        "doi": "10.1038/s42254-020-00254-6",
        "journal": "Nature Reviews Physics",
        "year": 2021,
        "authors": ["Dmitri E. Kharzeev", "Jinfeng Liao"],
    },
    "T3-05": {
        "paper_title": "Chiral magnetic effect reveals the topology of gauge fields in heavy-ion collisions",
        "doi": "10.1038/s42254-020-00254-6",
        "journal": "Nature Reviews Physics",
        "year": 2021,
        "authors": ["Dmitri E. Kharzeev", "Jinfeng Liao"],
    },
    "T3-06": {
        "paper_title": "Chiral magnetic effect reveals the topology of gauge fields in heavy-ion collisions",
        "doi": "10.1038/s42254-020-00254-6",
        "journal": "Nature Reviews Physics",
        "year": 2021,
        "authors": ["Dmitri E. Kharzeev", "Jinfeng Liao"],
    },
    "T3-07": {
        "paper_title": "Pattern of global spin alignment of phi and K*0 mesons in heavy-ion collisions",
        "doi": "10.1038/s41586-022-05557-5",
        "journal": "Nature",
        "year": 2023,
        "authors": ["STAR Collaboration"],
    },
    "T3-08": {
        "paper_title": "Pattern of global spin alignment of phi and K*0 mesons in heavy-ion collisions",
        "doi": "10.1038/s41586-022-05557-5",
        "journal": "Nature",
        "year": 2023,
        "authors": ["STAR Collaboration"],
    },
    "T3-09": {
        "paper_title": "Global Lambda hyperon polarization in nuclear collisions",
        "doi": "10.1038/nature23004",
        "journal": "Nature",
        "year": 2017,
        "authors": ["STAR Collaboration"],
    },
    "T3-10": {
        "paper_title": "Global Lambda hyperon polarization in nuclear collisions",
        "doi": "10.1038/nature23004",
        "journal": "Nature",
        "year": 2017,
        "authors": ["STAR Collaboration"],
    },
}


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm_doi(value: str | None) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.lower()


def _slug(value: str, limit: int = 64) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower()
    return (value or "entry")[:limit]


def _text(blob: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", blob or ""))).strip()


def _matches_any(blob: str, words) -> bool:
    low = (blob or "").casefold()
    return any(w.casefold() in low for w in words)


def _infer_topics(blob: str, taxonomy: dict) -> list[str]:
    out = []
    for topic, spec in taxonomy["topics"].items():
        if _matches_any(blob, spec.get("keywords", [])):
            out.append(topic)
    return out


def _infer_types(blob: str) -> list[str]:
    low = (blob or "").casefold()
    out = []
    if re.search(r"(^|[^a-z0-9])(3d|three-dimensional)(?=$|[^a-z0-9])", low):
        out.append("3d-illustration")
    if any(x in low for x in ("detector", "spectrometer", "beamline")):
        out.append("detector-cutaway")
    if any(x in low for x in ("phase diagram", "qcd phase")):
        out.append("phase-diagram")
    if any(x in low for x in ("timeline", "evolution", "stages", "workflow")):
        out.append("timeline")
    if any(x in low for x in ("geometry", "reaction plane", "impact parameter")):
        out.append("geometry-diagram")
    if any(x in low for x in ("panel a", "panels", "multi-panel", "(a)", "(b)")):
        out.append("multi-panel")
    if not out:
        out.append("flat-diagram")
    return list(dict.fromkeys(out))


def _infer_style(blob: str) -> dict:
    low = (blob or "").casefold()
    tags = []
    if re.search(r"(^|[^a-z0-9])(3d|three-dimensional|rendered|render)(?=$|[^a-z0-9])", low):
        tags.append("render3d")
    for name in ("translucent", "metallic", "plasma", "detector", "field lines"):
        if name in low:
            tags.append(name.replace(" ", "-"))
    return {
        "mode": "render3d" if "render3d" in tags else "illustration",
        "projection": "axonometric" if "3d" in low else "unspecified",
        "tags": tags,
    }


def _doi_url(doi: str) -> str:
    doi = _norm_doi(doi)
    return f"https://doi.org/{doi}" if doi else ""


def _legacy_figure_label(stem: str, code: str) -> str:
    if re.search(r"ED\d+[a-z]?(?:[_-]|$)", stem, re.I) and code == "T3-03":
        m = re.search(r"ED(\d+)[a-z]?", stem, re.I)
        return f"Extended Data Fig. {m.group(1)}g" if m else code
    m = re.search(r"(?:^|_)ED(\d+)([a-z])?(?:_|$)", stem, re.I)
    if m:
        return f"Extended Data Fig. {m.group(1)}{m.group(2) or ''}"
    m = re.search(r"(?:^|_)Fig(\d+)([a-z])?(?:_|$)", stem, re.I)
    if m:
        return f"Fig. {m.group(1)}{m.group(2) or ''}"
    return code


def _request_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 4 * (attempt + 1)
            except ValueError:
                delay = 4 * (attempt + 1)
            time.sleep(max(2.0, delay))
    raise RuntimeError("unreachable")


def _request_bytes(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("Content-Type", "")


def _legacy_entries(taxonomy: dict) -> list[dict]:
    """Seed verified records from the existing CC BY exemplar directory."""
    entries = []
    previous = {}
    for path in sorted(EXEMPLARS.glob("*")):
        if path.suffix.lower() not in IMAGE_EXT:
            continue
        code = path.stem.split("_", 1)[0]
        blob = path.stem.replace("_", " ")
        paper_title = blob
        doi = ""
        arxiv = ""
        authors = ""
        journal = ""
        year = None
        processing = "retained from the existing t3-exemplars library; see its NOTICE.md"
        notice = EXEMPLARS / "NOTICE.md"
        if notice.exists():
            for line in notice.read_text(encoding="utf-8").splitlines():
                if f"`{path.name}`" in line:
                    cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    if len(cells) >= 4:
                        authors = cells[1]
                        source_cell = cells[2]
                        processing = re.sub(r"<[^>]+>", "", cells[3]).strip()
                        m = re.search(r"https?://doi\.org/([^)\s]+)", source_cell)
                        if m:
                            doi = _norm_doi(m.group(1))
                        m = re.search(r"arxiv\.org/abs/([^)\s]+)", source_cell)
                        if m:
                            arxiv = m.group(1).rstrip(".,")
                        m = re.search(r"\*([^*]+)\*", source_cell)
                        if m:
                            paper_title = _text(m.group(1))
                        m = re.search(r"\*\*([^*]+)\*\*", source_cell)
                        if m:
                            journal = _text(m.group(1))
                        years = re.findall(r"\b(19|20)\d{2}\b", source_cell)
                        if years:
                            year = int(re.findall(r"\b(?:19|20)\d{2}\b", source_cell)[-1])
                    if authors in {"同上", "same", "ibid"} and previous:
                        authors = previous.get("authors", authors)
                        paper_title = previous.get("title", paper_title)
                        doi = previous.get("doi", doi)
                        arxiv = previous.get("arxiv", arxiv)
                        journal = previous.get("journal", journal)
                        year = previous.get("year", year)
                    if not year:
                        ym = re.search(r"\b(?:19|20)\d{2}\b", path.stem)
                        if ym:
                            year = int(ym.group(0))
                    if arxiv and not journal:
                        journal = "arXiv"
                    previous = {
                        "authors": authors, "title": paper_title, "doi": doi,
                        "arxiv": arxiv, "journal": journal, "year": year,
                    }
                    break
        title = re.sub(r"^T3-\d+_", "", path.stem).replace("_", " ")
        entry = {
            "asset_id": code,
            "legacy_code": code,
            "status": "verified_figure",
            "kind": "figure",
            "title": title,
            "figure_label": _legacy_figure_label(path.stem, code),
            "figure_caption": "",
            "paper": {
                "doi": doi,
                "arxiv": arxiv,
                "title": paper_title,
                "authors": [authors] if authors else [],
                "year": year,
                "journal": journal,
                "volume": "",
            },
            "topics": LEGACY_TOPIC_MAP.get(code, _infer_topics(blob, taxonomy) or ["qgp"]),
            "schematic_types": LEGACY_TYPE_MAP.get(code, _infer_types(blob)),
            "style": _infer_style(blob),
            "license": {
                "spdx": "CC-BY-4.0",
                "redistributable": True,
                "source_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": f"{authors}. {paper_title}. {journal}".strip(),
                "note": processing,
            },
            "local_file": path.relative_to(ROOT).as_posix(),
            "remote_image": None,
            "sha256": _sha256(path),
            "source": "t3-exemplars",
            "retrieved": TODAY,
            "provenance": {"notice": "assets/t3-exemplars/NOTICE.md"},
            "notes": "Legacy verified exemplar.",
        }
        entries.append(entry)
    return entries


def cmd_seed(_args):
    taxonomy = _load_json(TAXONOMY)
    entries = _legacy_entries(taxonomy)
    _write_json(CATALOG, {
        "schema_version": "5.1.0",
        "library_version": "5.1.0",
        "updated": TODAY,
        "entries": entries,
    })
    print(f"seeded {len(entries)} verified entries -> {CATALOG}")


def _legacy_log_entries(log_path: Path, taxonomy: dict,
                        skip_existing: bool = True) -> list[dict]:
    """Import metadata-only rows from the local _T3精选 licence ledger.

    The ledger is intentionally not copied into the public repository because
    its filenames point at restricted local downloads. Only text metadata is
    merged into the public catalog.
    """
    existing_entries = {e["asset_id"]: e for e in _catalog().get("entries", [])}
    present = set(existing_entries)
    entries = []
    last_context = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        m = re.search(r"`(T3-\d+)[^`]*\.(?:png|jpe?g|webp|tif?f)`", cells[0], re.I)
        if not m:
            continue
        code = m.group(1)
        if code in existing_entries and (
            skip_existing or existing_entries[code].get("source") != "legacy-index"
        ):
            continue
        source_cell = " | ".join(cells[1:])
        low = source_cell.casefold()
        if "cc by-nc-nd" in low or "cc-by-nc-nd" in low:
            spdx = "CC-BY-NC-ND-4.0"
        elif "cc-by" in low or "cc by" in low:
            spdx = "CC-BY-4.0"
        elif "arxiv" in low:
            spdx = "arXiv-default"
        else:
            spdx = "publisher-copyright"
        doi_m = re.search(r"10\.\d{4,9}/[^\s)|<]+", source_cell)
        arxiv_m = re.search(r"arxiv[:\s/]*([0-9]{4}\.[0-9]{4,5}|[a-z-]+/\d{7})",
                            source_cell, re.I)
        year_m = re.search(r"\b(?:19|20)\d{2}\b", source_cell)
        doi = _norm_doi(doi_m.group(0)) if doi_m else ""
        arxiv = arxiv_m.group(1) if arxiv_m else ""
        year = int(year_m.group(0)) if year_m else None
        if "同上" in source_cell and last_context:
            doi = doi or last_context.get("doi", "")
            arxiv = arxiv or last_context.get("arxiv", "")
            year = year or last_context.get("year")
        title = re.sub(r"^T3-\d+_", "", Path(cells[0].strip("`")).stem).replace("_", " ")
        journal = ""
        for cell in cells[1:]:
            candidate = _text(cell)
            if ("figs/" in candidate or candidate in {"同上", "⚠️"}):
                continue
            if re.search(
                r"(Nature|Physical Review|Phys\. Rev|Communications Physics|"
                r"Reviews of Modern|Nuclear Physics|European Physical|"
                r"Journal of High Energy|Physics Reports|arXiv)",
                candidate, re.I,
            ):
                journal = candidate[:160]
                break
        if not journal:
            journal = "arXiv" if arxiv else "unknown"
        if arxiv:
            journal = "arXiv"
        if "同上" in source_cell and last_context:
            journal = last_context.get("journal", journal)
        known = LEGACY_METADATA.get(code)
        if known:
            doi = known["doi"]
            journal = known["journal"]
            year = known["year"]
        if not year:
            ym = re.search(r"\b(?:19|20)\d{2}\b", Path(cells[0].strip("`")).stem)
            year = int(ym.group(0)) if ym else None
        source_url = _doi_url(doi) if doi else (
            f"https://arxiv.org/abs/{arxiv}" if arxiv else "")
        entry = {
            "asset_id": code,
            "legacy_code": code,
            "status": "metadata_only",
            "kind": "figure",
            "title": title,
            "figure_label": _legacy_figure_label(title, code),
            "figure_caption": "",
            "paper": {
                "doi": doi,
                "arxiv": arxiv,
                "title": known["paper_title"] if known else title,
                "authors": known["authors"] if known else [],
                "year": year if known else (int(year_m.group(0)) if year_m else None),
                "journal": journal,
                "volume": "",
            },
            "topics": _infer_topics(title, taxonomy) or ["qgp"],
            "schematic_types": _infer_types(title),
            "style": _infer_style(title),
            "license": {
                "spdx": spdx,
                "redistributable": False,
                "source_url": source_url,
                "attribution": _text(source_cell),
                "note": "metadata imported from local licence ledger; image intentionally not redistributed",
            },
            "local_file": None,
            "remote_image": None,
            "sha256": None,
            "source": "legacy-index",
            "retrieved": TODAY,
            "provenance": {"local_license_log": "_T3精选/LICENSE_记录.md"},
            "notes": "Local-only image; obtain lawfully and verify the licence before reuse.",
        }
        entries.append(entry)
        present.add(code)
        if doi or arxiv:
            last_context = {
                "doi": doi, "arxiv": arxiv, "journal": journal,
                "year": entry["paper"]["year"],
            }
    return entries


def cmd_import_legacy(args):
    path = Path(args.log).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"licence log not found: {path}")
    entries = _legacy_log_entries(path, _load_json(TAXONOMY),
                                  skip_existing=not args.refresh)
    if entries:
        added, updated = _merge_entries(entries)
    else:
        added = updated = 0
    print(json.dumps({"metadata_added": added, "metadata_updated": updated},
                     ensure_ascii=False, indent=2))
    return 0


def _catalog() -> dict:
    if not CATALOG.exists():
        raise SystemExit("catalog.json is missing; run `schematic_library.py seed`")
    return _load_json(CATALOG)


def _required(entry: dict) -> set[str]:
    return {
        "asset_id", "status", "kind", "title", "paper", "topics",
        "schematic_types", "style", "license", "source", "retrieved",
    }


def cmd_validate(_args):
    catalog = _catalog()
    tax = _load_json(TAXONOMY)
    topics = set(tax["topics"])
    types = set(tax["schematic_types"])
    statuses = set(tax["statuses"])
    allowed_licenses = set(tax["redistributable_licenses"]) | set(tax["metadata_only_licenses"])
    errors = []
    ids = set()
    dois_fig = set()
    for i, entry in enumerate(catalog.get("entries", []), 1):
        where = f"entry[{i}] {entry.get('asset_id', '?')}"
        missing = _required(entry) - set(entry)
        if missing:
            errors.append(f"{where}: missing {sorted(missing)}")
            continue
        aid = entry["asset_id"]
        if aid in ids:
            errors.append(f"{where}: duplicate asset_id")
        ids.add(aid)
        if entry["status"] not in statuses:
            errors.append(f"{where}: bad status {entry['status']}")
        unknown = set(entry["topics"]) - topics
        if unknown:
            errors.append(f"{where}: unknown topics {sorted(unknown)}")
        unknown = set(entry["schematic_types"]) - types
        if unknown:
            errors.append(f"{where}: unknown schematic types {sorted(unknown)}")
        lic = entry["license"]
        if lic.get("spdx") not in allowed_licenses:
            errors.append(f"{where}: unmanaged license {lic.get('spdx')}")
        local = entry.get("local_file")
        if lic.get("redistributable"):
            if not local:
                errors.append(f"{where}: redistributable entry has no local_file")
            else:
                p = ROOT / local
                if not p.exists():
                    errors.append(f"{where}: missing local file {local}")
                elif entry.get("sha256") and _sha256(p) != entry["sha256"]:
                    errors.append(f"{where}: sha256 mismatch for {local}")
                tail = Path(local).as_posix()
                if not (tail.startswith("assets/t3-exemplars/") or
                        tail.startswith("assets/schematic-library/redistributable/")):
                    errors.append(f"{where}: local file outside approved style libraries")
        elif local:
            errors.append(f"{where}: metadata-only entry must not carry local_file")
        doi = _norm_doi((entry["paper"] or {}).get("doi"))
        fig = (doi, entry.get("figure_label", "").casefold())
        if doi and entry.get("figure_label"):
            if fig in dois_fig:
                errors.append(f"{where}: duplicate DOI/figure")
            dois_fig.add(fig)
    candidate_ids = set()
    candidate_dois = set()
    candidates = 0
    if CANDIDATES.exists():
        for lineno, line in enumerate(CANDIDATES.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"candidates.jsonl:{lineno}: {exc}")
                continue
            candidates += 1
            cid = row.get("candidate_id")
            if not cid:
                errors.append(f"candidates.jsonl:{lineno}: missing candidate_id")
            elif cid in candidate_ids:
                errors.append(f"candidates.jsonl:{lineno}: duplicate candidate_id {cid}")
            candidate_ids.add(cid)
            if not row.get("title"):
                errors.append(f"candidates.jsonl:{lineno}: missing title")
            if not row.get("topics"):
                errors.append(f"candidates.jsonl:{lineno}: missing topics")
            elif set(row["topics"]) - topics:
                errors.append(f"candidates.jsonl:{lineno}: unknown topics {sorted(set(row['topics']) - topics)}")
            doi = _norm_doi(row.get("doi"))
            if doi:
                if doi in candidate_dois:
                    errors.append(f"candidates.jsonl:{lineno}: duplicate DOI {doi}")
                candidate_dois.add(doi)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"PASS: {len(catalog['entries'])} catalog entries + {candidates} article candidates")
    return 0


def _haystack(entry: dict) -> str:
    parts = [
        entry.get("asset_id", ""), entry.get("title", ""),
        entry.get("figure_label", ""), entry.get("figure_caption", ""),
        entry.get("notes", ""), entry.get("source", ""),
    ]
    paper = entry.get("paper") or {}
    parts.extend(str(paper.get(k, "")) for k in ("doi", "arxiv", "title", "journal"))
    parts.extend(str((entry.get("license") or {}).get(k, ""))
                 for k in ("spdx", "attribution", "note"))
    parts.extend(entry.get("topics", []))
    parts.extend(entry.get("schematic_types", []))
    parts.extend((entry.get("style") or {}).get("tags", []))
    return " ".join(parts).casefold()


def _load_candidates() -> list[dict]:
    if not CANDIDATES.exists():
        return []
    out = []
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.append({
            "asset_id": row.get("candidate_id", ""),
            "status": "article_candidate",
            "kind": "paper",
            "title": row.get("title", ""),
            "figure_label": "",
            "figure_caption": "",
            "paper": {
                "doi": row.get("doi", ""),
                "arxiv": row.get("arxiv", ""),
                "title": row.get("title", ""),
                "authors": row.get("authors", []),
                "year": row.get("year"),
                "journal": row.get("journal", ""),
                "volume": "",
            },
            "topics": row.get("topics", []),
            "schematic_types": [],
            "style": {"mode": "unknown", "projection": "unknown", "tags": []},
            "license": {
                "spdx": row.get("license") or "unverified",
                "redistributable": False,
                "source_url": row.get("oa_url") or _doi_url(row.get("doi", "")),
                "attribution": "",
                "note": "article-level candidate; exact figure and licence still need review",
            },
            "local_file": None,
            "remote_image": None,
            "sha256": None,
            "source": "openalex",
            "retrieved": row.get("retrieved", ""),
            "provenance": {
                "matched_queries": row.get("matched_queries", []),
                "open_access": row.get("open_access", {}),
            },
            "notes": row.get("abstract", ""),
        })
    return out


def _search_entries(entries, args):
    tokens = re.findall(r"[\w-]+", (args.q or "").casefold())
    out = []
    for e in entries:
        hay = _haystack(e)
        if tokens and not all(t in hay for t in tokens):
            continue
        if args.topic and not set(args.topic).issubset(set(e.get("topics", []))):
            continue
        if args.type and not set(args.type).issubset(set(e.get("schematic_types", []))):
            continue
        if args.style and not set(args.style).issubset(set((e.get("style") or {}).get("tags", []))):
            continue
        if args.source and e.get("source") != args.source:
            continue
        lic = e.get("license") or {}
        if args.local_only and not e.get("local_file"):
            continue
        if args.for_ref:
            local = e.get("local_file")
            if not lic.get("redistributable") or not local:
                continue
            if Path(local).suffix.lower() not in IMAGE_EXT:
                continue
        if args.metadata_only and lic.get("redistributable"):
            continue
        out.append(e)
    return out[:args.limit]


def cmd_search(args):
    entries = _catalog()["entries"]
    if not args.catalog_only:
        entries = entries + _load_candidates()
    found = _search_entries(entries, args)
    if args.for_ref and not args.format:
        for e in found:
            print(e["local_file"])
        return 0
    if args.format == "json" or args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("No matching entries.")
        return 0
    for e in found:
        paper = e["paper"]
        lic = e["license"]
        locator = e.get("local_file") or lic.get("source_url") or _doi_url(paper.get("doi", ""))
        print(f"- {e['asset_id']} | {paper.get('year') or '?'} | "
              f"{paper.get('journal') or e.get('source')} | {e['status']}")
        print(f"  {e['title']}")
        print(f"  topics={','.join(e['topics'])} | license={lic.get('spdx')} | {locator}")
    return 0


def cmd_stats(_args):
    catalog = _catalog()
    entries = catalog["entries"]
    def counts(key):
        d = {}
        for e in entries:
            v = key(e)
            if isinstance(v, list):
                for x in v:
                    d[x] = d.get(x, 0) + 1
            else:
                d[v] = d.get(v, 0) + 1
        return dict(sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0]))))
    summary = {
        "catalog_entries": len(entries),
        "article_candidates": len(_load_candidates()),
        "by_status": counts(lambda e: e["status"]),
        "by_source": counts(lambda e: e["source"]),
        "by_journal": counts(lambda e: e["paper"].get("journal") or "unknown"),
        "by_license": counts(lambda e: e["license"].get("spdx")),
        "by_topic": counts(lambda e: e["topics"]),
        "local_redistributable": sum(
            bool(e.get("local_file")) and bool(e["license"].get("redistributable"))
            for e in entries
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _openalex_abstract(work: dict) -> str:
    inv = work.get("abstract_inverted_index")
    if not inv:
        return ""
    words = []
    for word, positions in inv.items():
        for pos in positions:
            words.append((pos, word))
    words.sort()
    return " ".join(word for _, word in words)


def _discover_one(query: dict, issns: list[str],
                  max_records: int) -> tuple[list[dict], int]:
    """Page through OpenAlex instead of silently truncating at one page."""
    target = max(1, max_records)
    page_size = min(200, target)
    page = 1
    total = 0
    rows = []
    taxonomy = _load_json(TAXONOMY)
    while len(rows) < target:
        params = {
            "search": query["query"],
            "per-page": page_size,
            "page": page,
            "filter": "primary_location.source.issn:" + "|".join(issns),
            "mailto": MAILTO,
        }
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        data = _request_json(url)
        results = data.get("results", [])
        total = int((data.get("meta") or {}).get("count") or len(results))
        for work in results:
            src = ((work.get("primary_location") or {}).get("source") or {})
            best = work.get("best_oa_location") or {}
            doi = _norm_doi(work.get("doi"))
            abstract = _openalex_abstract(work)
            text = " ".join(
                (work.get("title") or "", abstract, " ".join(query.get("topics", [])))
            )
            if not _is_hep_relevant(text):
                continue
            rows.append({
                "candidate_id": "oa-" + (work.get("id") or doi).rstrip("/").rsplit("/", 1)[-1],
                "title": work.get("title") or "",
                "doi": doi,
                "year": work.get("publication_year"),
                "authors": [
                    (a.get("author") or {}).get("display_name", "")
                    for a in work.get("authorships", [])[:12]
                ],
                "journal": src.get("display_name", ""),
                "publisher": src.get("host_organization_name", ""),
                "cited_by_count": work.get("cited_by_count", 0),
                "open_access": work.get("open_access") or {},
                "oa_url": best.get("pdf_url") or best.get("landing_page_url") or "",
                "license": best.get("license") or "",
                "topics": list(dict.fromkeys(
                    query.get("topics", []) + _infer_topics(text, taxonomy)
                )),
                "matched_queries": [query["id"]],
                "figure_status": "unreviewed",
                "source": "openalex",
                "retrieved": TODAY,
                "abstract": abstract[:1000],
            })
            if len(rows) >= target:
                break
        if len(results) < page_size:
            break
        page += 1
        time.sleep(0.2)
    return rows, total


def cmd_discover(args):
    qdoc = _load_json(QUERIES)
    groups = qdoc["journal_groups"]
    selected_groups = args.journal_group or [
        "nature_portfolio", "aps", "hep", "general_science",
    ]
    issns = []
    for name in selected_groups:
        if name not in groups:
            raise SystemExit(f"unknown journal group: {name}")
        issns.extend(groups[name]["issns"])
    issns = list(dict.fromkeys(issns))
    queries = qdoc["queries"]
    if args.query_id:
        wanted = set(args.query_id)
        queries = [q for q in queries if q["id"] in wanted]
        missing = wanted - {q["id"] for q in queries}
        if missing:
            raise SystemExit(f"unknown query ids: {sorted(missing)}")
    by_key = {}
    if CANDIDATES.exists():
        for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("doi") or row.get("candidate_id")
            if key:
                by_key[key] = row
    query_report = []
    for q in queries:
        try:
            rows, total = _discover_one(q, issns, args.max_per_query)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            query_report.append({"id": q["id"], "error": str(exc)})
            print(f"WARN {q['id']}: {exc}", file=sys.stderr)
            continue
        query_report.append({
            "id": q["id"], "query": q["query"], "reported_total": total,
            "retrieved": len(rows),
        })
        for row in rows:
            key = row["doi"] or row["candidate_id"]
            if key in by_key:
                merged = by_key[key]["matched_queries"]
                by_key[key]["matched_queries"] = sorted(set(merged + [q["id"]]))
                by_key[key]["topics"] = sorted(set(by_key[key]["topics"] + row["topics"]))
            else:
                by_key[key] = row
        print(f"{q['id']}: {len(rows)}/{total}")
        time.sleep(0.8)
    rows = sorted(by_key.values(), key=lambda r: (
        -(r.get("cited_by_count") or 0), -(r.get("year") or 0), r.get("title", "")
    ))
    CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        tmp = CANDIDATES.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(CANDIDATES)
    report = {
        "schema_version": "5.1.0",
        "retrieved": TODAY,
        "source": "OpenAlex",
        "journal_groups": selected_groups,
        "issns": issns,
        "queries": query_report,
        "unique_candidates": len(rows),
        "coverage_note": "Counts are reported per query; unique-candidate total is lower after DOI deduplication.",
    }
    _write_json(REPORT, report)
    print(f"retained {len(rows)} unique candidates -> {CANDIDATES}")
    return 0


def _crossref_year(item: dict):
    for key in ("published-print", "published-online", "issued", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            return int(parts[0])
    return None


def _crossref_authors(item: dict) -> list[str]:
    out = []
    for author in item.get("author", [])[:20]:
        value = " ".join(
            x for x in (author.get("given", ""), author.get("family", "")) if x
        ).strip()
        if value:
            out.append(value)
    return out


def cmd_discover_crossref(args):
    qdoc = _load_json(QUERIES)
    groups = qdoc["journal_groups"]
    selected_groups = args.journal_group or ["aps", "hep"]
    issns = []
    for name in selected_groups:
        if name not in groups:
            raise SystemExit(f"unknown journal group: {name}")
        issns.extend(groups[name]["issns"])
    issns = list(dict.fromkeys(issns))
    queries = qdoc["queries"]
    if args.query_id:
        wanted = set(args.query_id)
        queries = [q for q in queries if q["id"] in wanted]
        missing = wanted - {q["id"] for q in queries}
        if missing:
            raise SystemExit(f"unknown query ids: {sorted(missing)}")

    by_key = {}
    if CANDIDATES.exists():
        for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("doi") or row.get("candidate_id")
            if key:
                by_key[key] = row

    query_report = []
    taxonomy = _load_json(TAXONOMY)
    filter_value = "type:journal-article," + ",".join(f"issn:{x}" for x in issns)
    for query in queries:
        params = {
            "query.bibliographic": query["query"],
            "rows": min(1000, max(1, args.max_per_query)),
            "filter": filter_value,
            "select": (
                "DOI,title,author,published-print,published-online,issued,created,"
                "container-title,license,URL,is-referenced-by-count,abstract"
            ),
            "mailto": MAILTO,
        }
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        try:
            data = _request_json(url, timeout=60)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            query_report.append({"id": query["id"], "error": str(exc)})
            print(f"WARN crossref {query['id']}: {exc}", file=sys.stderr)
            continue
        message = data.get("message") or {}
        items = message.get("items") or []
        query_report.append({
            "id": query["id"],
            "query": query["query"],
            "reported_total": message.get("total-results", len(items)),
            "retrieved": len(items),
        })
        added = 0
        for item in items:
            doi = _norm_doi(item.get("DOI"))
            title = _text(" ".join(item.get("title") or []))
            abstract = _text(item.get("abstract") or "")
            if not _is_hep_relevant(" ".join((title, abstract))):
                continue
            key = doi or item.get("URL") or title
            if key in by_key:
                row = by_key[key]
                row["matched_queries"] = sorted(set(
                    row.get("matched_queries", []) + [query["id"]]
                ))
                row["topics"] = sorted(set(
                    row.get("topics", []) + query.get("topics", [])
                ))
                continue
            license_urls = [
                x.get("URL", "") for x in item.get("license", []) if x.get("URL")
            ]
            by_key[key] = {
                "candidate_id": "cr-" + re.sub(r"[^a-z0-9]+", "-", doi or title)[:80],
                "title": title,
                "doi": doi,
                "year": _crossref_year(item),
                "authors": _crossref_authors(item),
                "journal": _text(" ".join(item.get("container-title") or [])),
                "publisher": "",
                "cited_by_count": item.get("is-referenced-by-count", 0),
                "open_access": {"license_urls": license_urls},
                "oa_url": item.get("URL", ""),
                "license": "; ".join(license_urls),
                "topics": list(dict.fromkeys(
                    query.get("topics", [])
                    + _infer_topics(" ".join((title, abstract)), taxonomy)
                )),
                "matched_queries": [query["id"]],
                "figure_status": "unreviewed",
                "source": "crossref",
                "retrieved": TODAY,
                "abstract": abstract[:1000],
            }
            added += 1
        print(f"crossref {query['id']}: {added} new / {len(items)} retrieved")
        time.sleep(0.3)

    rows = sorted(by_key.values(), key=lambda row: (
        -(row.get("year") or 0),
        -(row.get("cited_by_count") or 0),
        row.get("title", ""),
    ))
    if rows:
        tmp = CANDIDATES.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(CANDIDATES)
    report = {
        "schema_version": "5.1.0",
        "retrieved": TODAY,
        "source": "Crossref",
        "journal_groups": selected_groups,
        "issns": issns,
        "queries": query_report,
        "unique_candidates": len(rows),
    }
    _write_json(CROSSREF_REPORT, report)
    print(f"retained {len(rows)} unique candidates -> {CANDIDATES}")
    return 0


def cmd_prune_candidates(_args):
    """Remove cross-query lexical false positives from the merged candidate file."""
    if not CANDIDATES.exists():
        raise SystemExit("candidates.jsonl does not exist")
    rows = []
    removed = []
    seen_ids = set()
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        blob = " ".join((row.get("title") or "", row.get("abstract") or ""))
        low = blob.casefold()
        not_article = any(
            marker in low
            for marker in (" pp.,", " eds.", "proceedings of the", "book review")
        )
        cid = row.get("candidate_id")
        if _is_hep_relevant(blob) and not not_article and cid not in seen_ids:
            rows.append(row)
            seen_ids.add(cid)
        else:
            removed.append({
                "doi": row.get("doi"),
                "title": row.get("title"),
                "journal": row.get("journal"),
            })
    rows.sort(key=lambda row: (
        -(row.get("year") or 0),
        -(row.get("cited_by_count") or 0),
        row.get("title", ""),
    ))
    tmp = CANDIDATES.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(CANDIDATES)
    _write_json(LIB / "candidate_prune_report.json", {
        "schema_version": "5.1.0",
        "retrieved": TODAY,
        "retained": len(rows),
        "removed": len(removed),
        "removed_examples": removed[:100],
    })
    print(f"retained {len(rows)} HEP candidates; removed {len(removed)} lexical false positives")
    return 0


def cmd_map_pmc(args):
    """Resolve candidate DOIs to PMCID/PMID through NCBI ID Converter."""
    rows = []
    if not CANDIDATES.exists():
        raise SystemExit("candidates.jsonl does not exist")
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    todo = [
        row for row in rows
        if row.get("doi")
        and row.get("pmc_lookup") not in {"found", "not_found"}
    ]
    found = not_found = calls = 0
    for start in range(0, len(todo), max(1, args.batch_size)):
        batch = todo[start:start + max(1, args.batch_size)]
        ids = [row["doi"] for row in batch]
        params = {
            "ids": ",".join(ids),
            "format": "json",
            "tool": "hep-nature-figure",
            "email": MAILTO,
        }
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?" + urllib.parse.urlencode(
            params, safe=",:"
        )
        calls += 1
        try:
            payload = _request_json(url, timeout=60)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"WARN PMC mapping batch {calls}: {exc}", file=sys.stderr)
            continue
        records = {
            _norm_doi(record.get("requested-id")): record
            for record in payload.get("records", [])
        }
        for row in batch:
            record = records.get(_norm_doi(row.get("doi")), {})
            if record.get("pmcid"):
                row["pmcid"] = record["pmcid"]
                row["pmid"] = record.get("pmid")
                row["pmc_lookup"] = "found"
                found += 1
            else:
                row["pmc_lookup"] = "not_found"
                not_found += 1
        if start == 0 or start + len(batch) >= len(todo) or calls % 5 == 0:
            tmp = CANDIDATES.with_suffix(".jsonl.tmp")
            with tmp.open("w", encoding="utf-8", newline="\n") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            tmp.replace(CANDIDATES)
        print(
            f"PMC mapping {min(start + len(batch), len(todo))}/{len(todo)}: "
            f"found={found}, not_found={not_found}",
            flush=True,
        )
        time.sleep(0.35)
    tmp = CANDIDATES.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(CANDIDATES)
    report = {
        "schema_version": "5.1.0",
        "retrieved": TODAY,
        "candidates": len(rows),
        "looked_up_this_run": len(todo),
        "calls": calls,
        "found_this_run": found,
        "not_found_this_run": not_found,
        "with_pmcid": sum(bool(row.get("pmcid")) for row in rows),
    }
    _write_json(LIB / "pmc_mapping_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


EPMC_JOURNALS = {
    "nature_portfolio": [
        'JOURNAL:"Nature"', 'JOURNAL:"Nature Physics"',
        'JOURNAL:"Nature Communications"', 'JOURNAL:"Communications Physics"',
        'JOURNAL:"Scientific Reports"', 'JOURNAL:"Nature Reviews Physics"',
    ],
    "general_science": [
        'JOURNAL:"Science"', 'JOURNAL:"Science Advances"',
    ],
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node, name: str) -> str:
    for child in node.iter():
        if _local_name(child.tag) == name:
            return _text("".join(child.itertext()))
    return ""


def _epmc_article_meta(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    meta = {"title": "", "journal": "", "year": None, "authors": []}
    for node in root.iter():
        name = _local_name(node.tag)
        if name == "journal-title" and not meta["journal"]:
            meta["journal"] = _text("".join(node.itertext()))
        elif name == "year" and meta["year"] is None:
            try:
                meta["year"] = int(_text("".join(node.itertext())))
            except ValueError:
                pass
    article_meta = next(
        (node for node in root.iter() if _local_name(node.tag) == "article-meta"),
        None,
    )
    if article_meta is not None:
        for node in article_meta.iter():
            if _local_name(node.tag) == "article-title" and not meta["title"]:
                meta["title"] = _text("".join(node.itertext()))
        seen = set()
        collaborations = []
        for contrib in article_meta.iter():
            if _local_name(contrib.tag) != "contrib":
                continue
            collab = next(
                (n for n in contrib.iter() if _local_name(n.tag) == "collab"),
                None,
            )
            if collab is not None:
                value = _text("".join(collab.itertext()))
                m = re.search(
                    r"(?:The\s+)?[A-Za-z0-9&.'’()\- ]{0,80}Collaboration",
                    value, re.I,
                )
                if m:
                    value = m.group(0).strip()
                elif len(value) > 100:
                    value = value[:100].rsplit(" ", 1)[0].strip()
                if value and value not in collaborations:
                    collaborations.append(value)
            else:
                surname = _child_text(contrib, "surname")
                given = _child_text(contrib, "given-names")
                value = " ".join(x for x in (given, surname) if x)
            if not collab and value and value not in seen:
                seen.add(value)
                meta["authors"].append(value)
        if collaborations:
            meta["authors"] = collaborations
    return meta


def _epmc_figures(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for fig in root.iter():
        if _local_name(fig.tag) != "fig":
            continue
        label = ""
        caption = ""
        href = ""
        for node in fig.iter():
            name = _local_name(node.tag)
            if name == "label" and not label:
                label = _text("".join(node.itertext()))
            elif name == "caption" and not caption:
                caption = _text("".join(node.itertext()))
            elif name == "graphic" and not href:
                href = (node.attrib.get("{http://www.w3.org/1999/xlink}href")
                        or node.attrib.get("href") or "")
        caption = re.sub(r"\\documentclass(?:\[[^]]+\])?\{minimal\}.*?\\begin\{document\}",
                         " ", caption)
        caption = caption.replace("\\end{document}", " ")
        caption = re.sub(r"\\(?:usepackage|setlength)\{[^}]+\}", " ", caption)
        caption = _text(caption)
        out.append({"label": label, "caption": caption, "href": href})
    return out


def _springer_image_url(doi: str, href: str) -> str:
    encoded = urllib.parse.quote(_norm_doi(doi), safe="")
    # Springer MediaObjects exposes a canonical PNG rendition for both the
    # HTML JPG/J2K and ESM filenames. The original .jpg URL often returns the
    # publisher's HTML interstitial instead of the image.
    href_png = str(Path(href).with_suffix(".png"))
    return ("https://media.springernature.com/full/springer-static/image/"
            f"art%3A{encoded}/MediaObjects/{urllib.parse.quote(href_png)}")


def _fetch_pmc_xml(pmcid: str) -> bytes:
    """Fetch JATS text from Europe PMC, falling back to NCBI eutils."""
    errors = []
    epmc = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    try:
        data, _ = _request_bytes(epmc, timeout=20)
        if b"<article" in data[:2000]:
            return data
        errors.append(f"Europe PMC returned {len(data)} bytes without an article")
    except (urllib.error.URLError, TimeoutError) as exc:
        errors.append(f"Europe PMC: {exc}")
    numeric_id = re.sub(r"^PMC", "", pmcid, flags=re.I)
    query = urllib.parse.urlencode({
        "db": "pmc", "id": numeric_id, "retmode": "xml",
        "tool": "hep-nature-figure", "email": MAILTO,
    })
    ncbi = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + query
    try:
        data, _ = _request_bytes(ncbi, timeout=45)
        if b"<article" in data[:5000]:
            return data
        errors.append(f"NCBI returned {len(data)} bytes without an article")
    except (urllib.error.URLError, TimeoutError) as exc:
        errors.append(f"NCBI: {exc}")
    raise OSError("; ".join(errors))


def _is_schematic(text: str) -> bool:
    return _matches_any(text, SCHEMATIC_WORDS)


def _is_hep_relevant(text: str) -> bool:
    return bool(HEP_STRONG_RE.search(text or ""))


def _is_hep_title(text: str) -> bool:
    return bool(HEP_STRONG_RE.search(text or ""))


def _merge_entries(new_entries: list[dict]) -> tuple[int, int]:
    catalog = _catalog()
    existing = {e["asset_id"]: e for e in catalog["entries"]}
    doi_figure = {
        (_norm_doi((e.get("paper") or {}).get("doi")), e.get("figure_label", "").casefold())
        for e in existing.values()
        if _norm_doi((e.get("paper") or {}).get("doi")) and e.get("figure_label")
    }
    added = updated = 0
    for e in new_entries:
        if e["asset_id"] in existing:
            updated += 1
        elif ((_norm_doi((e.get("paper") or {}).get("doi")),
               e.get("figure_label", "").casefold()) in doi_figure):
            continue
        else:
            added += 1
            doi = _norm_doi((e.get("paper") or {}).get("doi"))
            if doi and e.get("figure_label"):
                doi_figure.add((doi, e["figure_label"].casefold()))
        existing[e["asset_id"]] = e
    catalog["entries"] = sorted(existing.values(), key=lambda e: e["asset_id"])
    catalog["updated"] = TODAY
    _write_json(CATALOG, catalog)
    return added, updated


def cmd_harvest_epmc(args):
    qdoc = _load_json(QUERIES)
    qmap = {q["id"]: q for q in qdoc["queries"]}
    if args.query_id not in qmap:
        raise SystemExit(f"unknown query id: {args.query_id}")
    query = qmap[args.query_id]
    journal_group = args.journal_group or "nature_portfolio"
    if journal_group not in EPMC_JOURNALS:
        raise SystemExit(f"Europe PMC adapter does not support group: {journal_group}")
    journal_clause = "(" + " OR ".join(EPMC_JOURNALS[journal_group]) + ")"
    epmc_term = query.get("epmc_query") or query["query"]
    epmc_query = f"{journal_clause} AND OPEN_ACCESS:y AND ({epmc_term})"
    params = {
        "query": epmc_query, "format": "json",
        "pageSize": max(1, min(args.max_records, 50)), "resultType": "core",
    }
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params)
    doc = _request_json(url, timeout=45)
    results = (doc.get("resultList") or {}).get("result", [])
    new_entries = []
    downloaded = 0
    tax = _load_json(TAXONOMY)
    for result in results:
        license_text = (result.get("license") or "").strip().casefold()
        if license_text not in {"cc by", "cc-by", "cc-by-4.0"}:
            continue
        pmcid = result.get("pmcid") or ""
        doi = _norm_doi(result.get("doi"))
        if not pmcid or not doi:
            continue
        try:
            xml_bytes = _fetch_pmc_xml(pmcid)
            meta = _epmc_article_meta(xml_bytes)
            figs = _epmc_figures(xml_bytes)
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
            print(f"WARN {pmcid}: {exc}", file=sys.stderr)
            continue
        if not _is_hep_title(meta["title"] or result.get("title", "")):
            continue
        for fig in figs:
            if not fig["href"]:
                continue
            combined = " ".join((meta["title"], fig["label"], fig["caption"]))
            if args.only_schematic and not _is_schematic(combined):
                continue
            fig_slug = re.sub(r"[^a-z0-9]+", "", (fig["label"] or fig["href"]).casefold())
            fig_slug = _slug(fig_slug or "figure", 32)
            asset_id = f"epmc-{pmcid.lower()}-{fig_slug}"
            rel = Path("assets") / "schematic-library" / "redistributable" / "europepmc" / f"{asset_id}.png"
            dest = ROOT / rel
            remote = _springer_image_url(doi, fig["href"])
            try:
                data, ctype = _request_bytes(remote, timeout=45)
                if not ctype.startswith("image/") or len(data) < 1024:
                    raise ValueError(f"non-image response: {ctype} {len(data)}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                downloaded += 1
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                print(f"WARN image {pmcid} {fig['label']}: {exc}", file=sys.stderr)
                continue
            authors = meta["authors"][:20]
            attribution = (
                f"{', '.join(authors[:8])}{' et al.' if len(authors) > 8 else ''}. "
                f"{meta['title']}. {meta['journal']} ({meta['year'] or 'n.d.'})."
            )
            entry = {
                "asset_id": asset_id,
                "status": "verified_figure",
                "kind": "figure",
                "title": f"{fig['label']}: {meta['title']}".strip(": "),
                "figure_label": fig["label"],
                "figure_caption": fig["caption"],
                "paper": {
                    "doi": doi,
                    "arxiv": "",
                    "title": meta["title"] or result.get("title", ""),
                    "authors": authors,
                    "year": meta["year"] or int(result.get("pubYear") or 0) or None,
                    "journal": meta["journal"] or result.get("journalTitle", ""),
                    "volume": "",
                },
                "topics": list(dict.fromkeys(query.get("topics", []) + _infer_topics(combined, tax))),
                "schematic_types": _infer_types(combined),
                "style": _infer_style(combined),
                "license": {
                    "spdx": "CC-BY-4.0",
                    "redistributable": True,
                    "source_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": attribution,
                    "note": "full-size publisher figure downloaded; no crop or pixel edit",
                },
                "local_file": rel.as_posix(),
                "remote_image": remote,
                "sha256": _sha256(dest),
                "source": "europepmc",
                "retrieved": TODAY,
                "provenance": {
                    "pmcid": pmcid,
                    "europepmc_query_id": args.query_id,
                    "fulltext_xml": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                    "fulltext_fallback": f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={re.sub(r'^PMC', '', pmcid, flags=re.I)}&retmode=xml",
                    "graphic_href": fig["href"],
                },
                "notes": "Caption matched schematic-language heuristic; visually review before use.",
            }
            new_entries.append(entry)
        time.sleep(0.35)
    if new_entries:
        added, updated = _merge_entries(new_entries)
    else:
        added = updated = 0
    print(json.dumps({
        "query_id": args.query_id,
        "records_seen": len(results),
        "figures_downloaded": downloaded,
        "catalog_added": added,
        "catalog_updated": updated,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="HEP schematic library")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed", help="create catalog.json from t3-exemplars")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("import-legacy",
                       help="import metadata-only rows from a local licence ledger")
    p.add_argument("--log", required=True)
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_import_legacy)

    p = sub.add_parser("validate", help="validate licenses, hashes, IDs, and taxonomy")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="print catalog coverage counts")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("search", help="search figure and metadata records")
    p.add_argument("--q", default="")
    p.add_argument("--topic", action="append", default=[])
    p.add_argument("--type", action="append", default=[])
    p.add_argument("--style", action="append", default=[])
    p.add_argument("--source")
    p.add_argument("--local-only", action="store_true")
    p.add_argument("--metadata-only", action="store_true")
    p.add_argument("--catalog-only", action="store_true")
    p.add_argument("--for-ref", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--format", choices=["json", "markdown"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("discover", help="discover article candidates through OpenAlex")
    p.add_argument("--journal-group", action="append",
                   choices=["nature_portfolio", "aps", "hep", "general_science"])
    p.add_argument("--query-id", action="append")
    p.add_argument("--max-per-query", type=int, default=50)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser(
        "discover-crossref",
        help="expand Physical Review and HEP journal candidates through Crossref",
    )
    p.add_argument("--journal-group", action="append",
                   choices=["nature_portfolio", "aps", "hep", "general_science"])
    p.add_argument("--query-id", action="append")
    p.add_argument("--max-per-query", type=int, default=1000)
    p.set_defaults(func=cmd_discover_crossref)

    p = sub.add_parser(
        "prune-candidates",
        help="remove non-HEP lexical false positives from the merged candidate index",
    )
    p.set_defaults(func=cmd_prune_candidates)

    p = sub.add_parser(
        "map-pmc",
        help="resolve candidate DOIs to PMCID/PMID through NCBI ID Converter",
    )
    p.add_argument("--batch-size", type=int, default=50)
    p.set_defaults(func=cmd_map_pmc)

    p = sub.add_parser("harvest-europepmc",
                       help="download figures from CC BY Europe PMC articles")
    p.add_argument("--query-id", required=True)
    p.add_argument("--journal-group", default="nature_portfolio",
                   choices=sorted(EPMC_JOURNALS))
    p.add_argument("--max-records", type=int, default=5)
    p.add_argument("--all-figures", dest="only_schematic", action="store_false",
                   help="include data-heavy figures too; schematic filter is on by default")
    p.set_defaults(only_schematic=True)
    p.set_defaults(func=cmd_harvest_epmc)
    return ap


def main():
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args) or 0


try:
    from _console import init_console
    init_console()
except Exception:
    pass


if __name__ == "__main__":
    sys.exit(main())
