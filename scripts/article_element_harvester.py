#!/usr/bin/env python3
"""Discover CC BY HEP articles and harvest schematic figures for element extraction."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "assets" / "element-library" / "source-corpus"
ARTICLES = CORPUS / "articles.jsonl"
FIGURES = CORPUS / "figures.jsonl"
REPORT = CORPUS / "report.json"
PROCESSED = CORPUS / "processed_articles.json"
SOURCE_FIGS = CORPUS / "figures"
SOURCE_PDFS = CORPUS / "pdfs"
CATALOG_CANDIDATES = ROOT / "assets" / "schematic-library" / "candidates.jsonl"
CATALOG_ARTICLES = CORPUS / "catalog_articles.jsonl"
TODAY = dt.date.today().isoformat()
UA = "hep-nature-figure/5.1 (mailto:pngyuo@cug.edu.cn)"
PMC_OA = "https://pmc-oa-opendata.s3.amazonaws.com"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
REDISTRIBUTABLE_LICENSES = {
    "cc by", "cc-by", "cc-by-4.0", "cc by 4.0",
    "cc by 3.0", "cc-by-3.0",
}

JOURNALS = (
    '(JOURNAL:"Nature" OR JOURNAL:"Nature Physics" '
    'OR JOURNAL:"Nature Communications" OR JOURNAL:"Communications Physics" '
    'OR JOURNAL:"Scientific Reports" OR JOURNAL:"Nature Reviews Physics")'
)
HEP_TITLE_ABS = (
    '(TITLE_ABS:"quark-gluon plasma" OR TITLE_ABS:"quark gluon plasma" '
    'OR TITLE_ABS:QGP OR TITLE_ABS:"heavy-ion collisions" '
    'OR TITLE_ABS:"heavy ion collisions" '
    'OR TITLE_ABS:"relativistic heavy-ion" OR TITLE_ABS:"relativistic heavy ion" '
    'OR TITLE_ABS:"relativistic nuclear collision" '
    'OR TITLE_ABS:"high-energy nuclear collision" '
    'OR TITLE_ABS:"proton-lead" OR TITLE_ABS:"proton-nucleus" '
    'OR TITLE_ABS:quarkonium '
    'OR TITLE_ABS:"elliptic flow" '
    'OR TITLE_ABS:"jet quenching" OR TITLE_ABS:"electron-ion collider" '
    'OR TITLE_ABS:"ultra-peripheral" OR TITLE_ABS:"QCD phase" '
    'OR TITLE_ABS:"QCD confinement" OR TITLE_ABS:"partonic flow" '
    'OR (TITLE_ABS:hadronization AND TITLE_ABS:collision) '
    'OR (TITLE_ABS:"little-bang" AND TITLE_ABS:nucleosynthesis))'
)
HEP_STRONG_RE = re.compile(
    r"quark[- ]gluon|quarkonium|charmonium|bottomonium|\bqgp\b|jet quench|"
    r"electron[- ]ion collider|\beic\b|ultra[- ]peripheral|"
    r"quantum chromodynamics|qcd (?:phase|transition|confinement|critical|matter)|"
    r"partonic flow|relativistic heavy[- ]ion|high[- ]energy nuclear collision|"
    r"proton[- ](?:lead|nucleus)|heavy[- ]ion collision|ion collision|"
    r"elliptic flow|collective flow|subatomic swirl|spin hydrodynam|"
    r"nuclear geometry|nuclear deformation|nuclear shape|"
    r"little[- ]bang nucleosynthesis|heavy[- ](?:quark|flavor|flavour)|"
    r"\brhic\b|\blhc\b|beam energy scan|hadronization|"
    r"global (?:spin )?polarization|chiral (?:magnetic|vortical)",
    re.I,
)
HEP_CONTEXT_RE = re.compile(
    r"nuclear|hadr|parton|quark|\bqcd\b|collision|relativistic|"
    r"collider|\brhic\b|\blhc\b|spectra|flow|vorticity|hyperon",
    re.I,
)
HEP_NEGATIVE_RE = re.compile(
    r"water[- ]jet|author correction|publisher correction|"
    r"transistor|semiconductor|photovoltaic|solar cell|battery|"
    r"\bdna\b|biological|biomedical|medical|radiotherapy|cancer|"
    r"earth(?:'s)? (?:ring|magnetosphere|ionosphere)|geomagnetic|"
    r"space weather|satellite|catalysis|diamond|material|"
    r"radiation (?:damage|effect|hardness)|single[- ]event",
    re.I,
)
SCHEMATIC_WORDS = {
    "schematic", "illustration", "diagram", "cartoon", "depiction",
    "geometry", "geometric", "workflow", "spacetime", "space-time",
    "detector layout", "3d rendering", "conceptual",
}


def get_json(url: str, timeout=45) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "errCode" in data:
        raise RuntimeError(f"{data['errCode']}: {data.get('errMsg')}")
    return data


def get_bytes(url: str, timeout=45) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", "")


def put_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def put_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def schematic(blob: str) -> bool:
    low = (blob or "").casefold()
    return any(word in low for word in SCHEMATIC_WORDS)


def hep_article_relevant(title: str, abstract: str) -> bool:
    title_text = title or ""
    abstract_text = abstract or ""
    if HEP_NEGATIVE_RE.search(title_text):
        return False
    if HEP_STRONG_RE.search(title_text):
        return True
    if not HEP_CONTEXT_RE.search(title_text):
        return False
    # Generic "spin polarization" / "heavy ion" also appears in condensed
    # matter and radiation-hardness papers. Abstract context is required for
    # the broad phrases, while the strong HEP terms above remain title-based.
    combined = f"{title_text} {abstract_text}"
    return bool(
        re.search(
            r"heavy[- ]ion|spin polarization|nuclear structure|"
            r"collective flow|quark|hadron|relativistic collision",
            combined,
            re.I,
        )
        and HEP_CONTEXT_RE.search(abstract_text)
    )


def text(node) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def springer_url(doi: str, href: str) -> str:
    doi_q = urllib.parse.quote(doi, safe="")
    return ("https://media.springernature.com/full/springer-static/image/"
            f"art%3A{doi_q}/MediaObjects/{Path(href).with_suffix('.png').name}")


def pmc_versions(pmcid: str) -> list[str]:
    """Return available PMC OA article-version prefixes."""
    url = (
        f"{PMC_OA}/?list-type=2&prefix={urllib.parse.quote(pmcid + '.')}"
        "&delimiter=/"
    )
    data, _ = get_bytes(url, timeout=30)
    root = ET.fromstring(data)
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    return [
        node.text.rstrip("/")
        for node in root.findall(".//s3:CommonPrefixes/s3:Prefix", ns)
        if node.text
    ]


def pmc_oa_metadata(pmcid: str) -> dict | None:
    """Select the preferred open-version metadata for a PMC article."""
    candidates = []
    for prefix in pmc_versions(pmcid):
        url = f"{PMC_OA}/metadata/{prefix}.json"
        try:
            data, _ = get_bytes(url, timeout=30)
            row = json.loads(data.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        if not row.get("is_pmc_openaccess") or row.get("is_retracted"):
            continue
        if str(row.get("license_code") or "").casefold() not in REDISTRIBUTABLE_LICENSES:
            continue
        row["_prefix"] = prefix
        candidates.append(row)
    if not candidates:
        return None
    # Prefer the publisher version; version numbers do not otherwise imply
    # recency. Highest version is only the final tie-breaker.
    candidates.sort(
        key=lambda row: (
            bool(row.get("is_manuscript")),
            -int(row.get("version") or 0),
        )
    )
    return candidates[0]


def oa_article_xml(oa: dict) -> bytes:
    xml_url = https_object(oa.get("xml_url", ""))
    if not xml_url:
        raise RuntimeError("PMC OA metadata has no XML URL")
    data, _ = get_bytes(xml_url, timeout=30)
    if b"<article" not in data[:5000]:
        raise RuntimeError("PMC OA XML payload is not JATS")
    return data


def https_object(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("s3://pmc-oa-opendata/"):
        return PMC_OA + "/" + value.removeprefix("s3://pmc-oa-opendata/")
    return value


def image_media_url(href: str, media_urls: list[str]) -> str:
    """Match JATS graphic href to the corresponding PMC OA media object."""
    wanted = Path(href).name.casefold()
    images = [
        url for url in media_urls
        if Path(urllib.parse.urlsplit(url).path).suffix.casefold() in IMAGE_SUFFIXES
    ]
    for url in images:
        if Path(urllib.parse.urlsplit(url).path).name.casefold() == wanted:
            return https_object(url)
    wanted_stem = Path(wanted).stem
    stem_matches = [
        url for url in images
        if Path(urllib.parse.urlsplit(url).path).stem.casefold() == wanted_stem
    ]
    if len(stem_matches) == 1:
        return https_object(stem_matches[0])
    contains = [
        url for url in images
        if wanted_stem in Path(urllib.parse.urlsplit(url).path).name.casefold()
    ]
    return https_object(contains[0]) if len(contains) == 1 else ""


def image_payload(data: bytes, ctype: str) -> bool:
    low = data[:32]
    magic = (
        low.startswith(b"\x89PNG\r\n\x1a\n")
        or low.startswith(b"\xff\xd8\xff")
        or low.startswith(b"RIFF") and b"WEBP" in low
        or low.startswith((b"II*\x00", b"MM\x00*"))
    )
    # S3 returns application/octet-stream for many valid media objects.
    return magic and len(data) >= 1024


def cmd_discover(a):
    query = f"{JOURNALS} AND OPEN_ACCESS:y AND {HEP_TITLE_ABS}"
    cursor = "*"
    seen = {}
    calls = 0
    total = None
    while calls < a.max_calls and len(seen) < a.max_articles:
        params = {
            "query": query, "format": "json", "pageSize": 100,
            "cursorMark": cursor, "resultType": "core",
            "sort": "P_PDATE_D desc",
        }
        payload = get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            + urllib.parse.urlencode(params)
        )
        calls += 1
        total = payload.get("hitCount", total)
        records = ((payload.get("resultList") or {}).get("result") or [])
        for row in records:
            key = (row.get("doi") or row.get("id") or "").lower()
            if not key:
                continue
            if not hep_article_relevant(
                row.get("title") or "",
                row.get("abstractText") or "",
            ):
                continue
            seen[key] = {
                "id": row.get("id"),
                "pmcid": row.get("pmcid"),
                "doi": (row.get("doi") or "").lower(),
                "title": row.get("title"),
                "authors": row.get("authorString"),
                "year": row.get("pubYear"),
                "journal": ((row.get("journalInfo") or {}).get("journal") or {}).get("title"),
                "license": row.get("license"),
                "open_access": row.get("isOpenAccess"),
                "abstract": row.get("abstractText", ""),
                "queries": ["hep-nature-schematic-v1"],
            }
        next_cursor = payload.get("nextCursorMark")
        if not records or next_cursor in (None, cursor):
            break
        cursor = next_cursor
        time.sleep(0.4)
    CORPUS.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        seen.values(),
        key=lambda x: (-int(x.get("year") or 0), x.get("doi", "")),
    )
    put_jsonl(ARTICLES, rows)
    report = {
        "schema_version": "1.0",
        "retrieved": TODAY,
        "query": query,
        "reported_total": total,
        "retrieved_unique": len(rows),
        "calls": calls,
        "complete": total is not None and len(rows) >= total,
    }
    put_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def article_xml(pmcid: str) -> bytes:
    numeric = re.sub(r"^PMC", "", pmcid, flags=re.I)
    query = urllib.parse.urlencode({"db": "pmc", "id": numeric, "retmode": "xml"})
    try:
        data, _ = get_bytes("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + query,
                            timeout=15)
        if b"<article" in data[:5000]:
            return data
    except (urllib.error.URLError, TimeoutError):
        pass
    epmc = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    try:
        data, _ = get_bytes(epmc, timeout=15)
        if b"<article" in data[:2000]:
            return data
    except (urllib.error.URLError, TimeoutError):
        pass
    raise RuntimeError(f"could not retrieve JATS for {pmcid}")


def parse_figures(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    figs = []
    for fig in root.iter():
        if local_name(fig.tag) != "fig":
            continue
        label = caption = href = ""
        for node in fig.iter():
            n = local_name(node.tag)
            if n == "label" and not label:
                label = text(node)
            elif n == "caption" and not caption:
                caption = text(node)
            elif n == "graphic" and not href:
                href = (node.attrib.get("{http://www.w3.org/1999/xlink}href")
                        or node.attrib.get("href") or "")
        if href:
            figs.append({"label": label, "caption": caption, "href": href})
    # Nested JATS figures can expose the same graphic through parent and
    # subfigure nodes. Keep one record per graphic and retain the richest caption.
    unique = {}
    for fig in figs:
        key = fig["href"]
        old = unique.get(key)
        if old is None:
            unique[key] = fig
        else:
            if len(fig["caption"]) > len(old["caption"]):
                old["caption"] = fig["caption"]
            if not old["label"]:
                old["label"] = fig["label"]
    return list(unique.values())


def cmd_harvest(a):
    if not ARTICLES.exists():
        raise SystemExit("run discover first")
    articles = [json.loads(x) for x in ARTICLES.read_text(encoding="utf-8").splitlines() if x]
    existing = {}
    if FIGURES.exists():
        for line in FIGURES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["figure_id"]] = row
    processed = set()
    failures = {}
    if PROCESSED.exists():
        old = json.loads(PROCESSED.read_text(encoding="utf-8"))
        processed = set(old.get("pmcids", []))
        failures = dict(old.get("failures", {}))
    if a.retry_failed:
        processed.difference_update(failures)
        failures = {}
    attempted = 0
    completed = 0
    downloaded_figures = 0
    for article in articles:
        if attempted >= a.max_articles:
            break
        pmcid = article.get("pmcid")
        doi = article.get("doi")
        license_text = str(article.get("license") or "").casefold()
        if not pmcid or not doi or license_text not in REDISTRIBUTABLE_LICENSES:
            continue
        if pmcid in processed and not a.refresh:
            continue
        attempted += 1
        try:
            oa = pmc_oa_metadata(pmcid)
            if oa is None:
                raise RuntimeError("article is not in the current PMC OA bucket under a redistributable licence")
            xml_bytes = oa_article_xml(oa)
            figs = parse_figures(xml_bytes)
        except Exception as exc:
            print(f"WARN {pmcid}: {exc}", file=sys.stderr)
            failures[pmcid] = {"error": str(exc), "updated": TODAY}
            put_json(PROCESSED, {
                "pmcids": sorted(processed),
                "failures": failures,
                "updated": TODAY,
            })
            continue
        schematic_figs = [
            fig for fig in figs
            if schematic(fig["caption"] + " " + article.get("title", ""))
        ]
        pdf_rel = ""
        if a.download_pdf and oa.get("pdf_url"):
            pdf_url = https_object(oa.get("pdf_url", ""))
            pdf_dest = SOURCE_PDFS / f"{pmcid}.pdf"
            try:
                data, _ = get_bytes(pdf_url)
                if not data.startswith(b"%PDF-") or len(data) < 4096:
                    raise ValueError("PDF URL did not return a PDF")
                pdf_dest.parent.mkdir(parents=True, exist_ok=True)
                pdf_dest.write_bytes(data)
                pdf_rel = pdf_dest.relative_to(ROOT).as_posix()
            except Exception as exc:
                print(f"WARN pdf {pmcid}: {exc}", file=sys.stderr)
        image_failures = []
        for fig in schematic_figs:
            fid = re.sub(r"[^a-z0-9]+", "", fig["label"].casefold()) or "fig"
            media_url = image_media_url(fig["href"], oa.get("media_urls", []))
            if not media_url:
                media_url = springer_url(doi, fig["href"])
            suffix = Path(urllib.parse.urlsplit(media_url).path).suffix.casefold()
            if suffix not in IMAGE_SUFFIXES:
                suffix = ".jpg"
            rel = Path(article.get("year") or "unknown") / pmcid / f"{fid}{suffix}"
            dest = SOURCE_FIGS / rel
            try:
                data, ctype = get_bytes(media_url)
                if not image_payload(data, ctype):
                    raise ValueError(f"non-image payload: {ctype} {len(data)} bytes")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            except Exception as exc:
                print(f"WARN image {pmcid} {fig['label']}: {exc}", file=sys.stderr)
                image_failures.append({
                    "label": fig["label"],
                    "href": fig["href"],
                    "url": media_url,
                    "error": str(exc),
                })
                continue
            downloaded_figures += 1
            existing[f"{pmcid}-{fid}"] = {
                "figure_id": f"{pmcid}-{fid}",
                "pmcid": pmcid,
                "doi": doi,
                "title": article.get("title"),
                "authors": article.get("authors"),
                "year": article.get("year"),
                "journal": article.get("journal"),
                "figure_label": fig["label"],
                "caption": fig["caption"],
                "local_file": (SOURCE_FIGS / rel).relative_to(ROOT).as_posix(),
                "remote_image": media_url,
                "license": oa.get("license_code"),
                "pmc_version": oa.get("_prefix"),
                "source_pdf": pdf_rel,
                "topics": article.get("topics", []),
                "source": "europepmc",
            }
        if image_failures:
            failures[pmcid] = {
                "error": f"{len(image_failures)} figure download(s) failed",
                "figure_failures": image_failures,
                "updated": TODAY,
            }
        else:
            failures.pop(pmcid, None)
        processed.add(pmcid)
        completed += 1
        put_jsonl(
            FIGURES,
            sorted(existing.values(), key=lambda x: x["figure_id"]),
        )
        put_json(PROCESSED, {
            "pmcids": sorted(processed),
            "failures": failures,
            "updated": TODAY,
        })
        print(f"[{attempted}/{a.max_articles}] {pmcid}: "
              f"+{len(schematic_figs) - len(image_failures)} downloaded, "
              f"{len(image_failures)} failed",
              flush=True)
        time.sleep(0.25)
    CORPUS.mkdir(parents=True, exist_ok=True)
    put_jsonl(FIGURES, sorted(existing.values(), key=lambda x: x["figure_id"]))
    print(json.dumps({"articles_attempted_this_run": attempted,
                      "articles_completed_this_run": completed,
                      "figures_downloaded_this_run": downloaded_figures,
                      "schematic_figures": len(existing),
                      "processed_articles": len(processed),
                      "failed_articles": len(failures)},
                     ensure_ascii=False, indent=2))
    return 0


def harvest_catalog_one(pmcid: str, candidate: dict, download_pdf: bool,
                        all_figures: bool = False) -> dict:
    oa = pmc_oa_metadata(pmcid)
    if oa is None:
        raise RuntimeError("not in PMC OA or not redistributable CC BY")
    xml_bytes = oa_article_xml(oa)
    figs = parse_figures(xml_bytes)
    schematic_figs = [
        fig for fig in figs
        if schematic(fig["caption"] + " " + (oa.get("title") or ""))
    ]
    selected_figs = figs if all_figures else schematic_figs
    pdf_rel = ""
    if download_pdf and selected_figs and oa.get("pdf_url"):
        try:
            pdf_url = https_object(oa["pdf_url"])
            data, _ = get_bytes(pdf_url)
            if data.startswith(b"%PDF-"):
                pdf_dest = SOURCE_PDFS / f"{pmcid}.pdf"
                pdf_dest.parent.mkdir(parents=True, exist_ok=True)
                pdf_dest.write_bytes(data)
                pdf_rel = pdf_dest.relative_to(ROOT).as_posix()
        except Exception as exc:
            print(f"WARN pdf {pmcid}: {exc}", file=sys.stderr)
    figure_rows = []
    image_failures = []
    for fig_index, fig in enumerate(selected_figs, 1):
        fid = re.sub(r"[^a-z0-9]+", "", fig["label"].casefold()) or "fig"
        fid = f"{fid}-{fig_index:02d}"
        media_url = image_media_url(fig["href"], oa.get("media_urls", []))
        if not media_url:
            image_failures.append({
                "label": fig["label"], "href": fig["href"],
                "error": "no matching PMC OA media object",
            })
            continue
        suffix = Path(urllib.parse.urlsplit(media_url).path).suffix.casefold()
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".jpg"
        rel = (
            Path(str(oa.get("year") or candidate.get("year") or "unknown"))
            / pmcid / f"{fid}{suffix}"
        )
        dest = SOURCE_FIGS / rel
        try:
            data, ctype = get_bytes(media_url)
            if not image_payload(data, ctype):
                raise ValueError(f"non-image payload: {ctype} {len(data)} bytes")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        except Exception as exc:
            image_failures.append({
                "label": fig["label"], "href": fig["href"],
                "url": media_url, "error": str(exc),
            })
            continue
        figure_rows.append({
            "figure_id": f"{pmcid}-{fid}",
            "pmcid": pmcid,
            "doi": oa.get("doi"),
            "title": oa.get("title"),
            "authors": candidate.get("authors"),
            "year": oa.get("year") or candidate.get("year"),
            "journal": oa.get("journal") or candidate.get("journal"),
            "figure_label": fig["label"],
            "caption": fig["caption"],
            "local_file": dest.relative_to(ROOT).as_posix(),
            "remote_image": media_url,
            "license": oa.get("license_code"),
            "pmc_version": oa.get("_prefix"),
            "source_pdf": pdf_rel,
            "topics": candidate.get("topics", []),
            "source": "catalog-pmc",
        })
    catalog_row = {
        "pmcid": pmcid,
        "doi": oa.get("doi"),
        "title": oa.get("title"),
        "authors": candidate.get("authors"),
        "year": oa.get("year") or candidate.get("year"),
        "journal": oa.get("journal") or candidate.get("journal"),
        "license": oa.get("license_code"),
        "pmc_version": oa.get("_prefix"),
        "topics": candidate.get("topics", []),
        "figures": len(selected_figs),
        "failed_figures": image_failures,
        "source_pdf": pdf_rel,
    }
    return {
        "pmcid": pmcid,
        "figures": figure_rows,
        "catalog": catalog_row,
        "image_failures": image_failures,
    }


def cmd_harvest_catalog(a):
    """Harvest every catalogue paper with a PMCID that resolves to CC BY."""
    import concurrent.futures

    if not CATALOG_CANDIDATES.exists():
        raise SystemExit("schematic candidates are missing")
    articles = {}
    for line in CATALOG_CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pmcid = row.get("pmcid")
        if pmcid and hep_article_relevant(
            row.get("title", ""), row.get("abstract", "")
        ):
            articles.setdefault(pmcid, row)
    existing = {}
    if FIGURES.exists():
        for line in FIGURES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["figure_id"]] = row
    processed = set()
    failures = {}
    if PROCESSED.exists():
        old = json.loads(PROCESSED.read_text(encoding="utf-8"))
        processed = set(old.get("pmcids", []))
        failures = dict(old.get("failures", {}))
    todo = []
    permanent_failures = 0
    for pmcid, candidate in sorted(articles.items()):
        if pmcid in processed and not a.refresh:
            continue
        failure = failures.get(pmcid) or {}
        if failure.get("kind") == "permanent_license" and not a.retry_permanent:
            permanent_failures += 1
            continue
        todo.append((pmcid, candidate))
    todo = todo[:max(0, a.max_articles)]
    completed = downloaded = 0
    catalog_rows = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, a.workers)
    ) as pool:
        futures = {
            pool.submit(
                harvest_catalog_one, pmcid, candidate, a.download_pdf,
                a.all_figures
            ): (pmcid, candidate)
            for pmcid, candidate in todo
        }
        for future in concurrent.futures.as_completed(futures):
            pmcid, _candidate = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                message = str(exc)
                failures[pmcid] = {
                    "error": message,
                    "kind": (
                        "permanent_license"
                        if "not in PMC OA" in message
                        or "not redistributable" in message
                        else "transient"
                    ),
                    "updated": TODAY,
                }
                print(f"WARN {pmcid}: {exc}", file=sys.stderr, flush=True)
                continue
            for row in result["figures"]:
                existing[row["figure_id"]] = row
                downloaded += 1
            catalog_rows.append(result["catalog"])
            if result["image_failures"]:
                failures[pmcid] = {
                    "error": f"{len(result['image_failures'])} figure download(s) failed",
                    "figure_failures": result["image_failures"],
                    "updated": TODAY,
                }
            else:
                failures.pop(pmcid, None)
            processed.add(pmcid)
            completed += 1
            put_jsonl(FIGURES, sorted(existing.values(), key=lambda row: row["figure_id"]))
            put_json(PROCESSED, {
                "pmcids": sorted(processed),
                "failures": failures,
                "updated": TODAY,
            })
            print(
                f"[{completed}/{len(todo)}] {pmcid}: "
                f"+{len(result['figures'])} figures, "
                f"{len(result['image_failures'])} failed",
                flush=True,
            )
    if catalog_rows:
        old_rows = []
        if CATALOG_ARTICLES.exists():
            old_rows = [
                json.loads(line) for line in CATALOG_ARTICLES.read_text(
                    encoding="utf-8"
                ).splitlines() if line.strip()
            ]
        merged = {row["pmcid"]: row for row in old_rows}
        merged.update({row["pmcid"]: row for row in catalog_rows})
        put_jsonl(CATALOG_ARTICLES, sorted(merged.values(), key=lambda row: row["pmcid"]))
    print(json.dumps({
        "articles_available_with_pmcid": len(articles),
        "articles_attempted": completed,
        "permanent_failures_skipped": permanent_failures,
        "figures_downloaded": downloaded,
        "processed_articles": len(processed),
        "failed_articles": len(failures),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_reset(a):
    processed = {}
    if not a.clear_figures and FIGURES.exists():
        processed = {
            "pmcids": sorted({
                json.loads(line)["pmcid"]
                for line in FIGURES.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }),
            "failures": {},
            "updated": TODAY,
        }
    else:
        put_jsonl(FIGURES, [])
        processed = {"pmcids": [], "failures": {}, "updated": TODAY}
    put_json(PROCESSED, processed)
    if a.purge_source_files and SOURCE_FIGS.exists():
        resolved = SOURCE_FIGS.resolve()
        allowed = CORPUS.resolve()
        if resolved.parent != allowed:
            raise SystemExit(f"refusing to purge unexpected path: {resolved}")
        shutil.rmtree(resolved)
    print(f"reset harvester state; retained {len(processed['pmcids'])} completed articles")
    return 0


def cmd_status(_a):
    processed = {}
    if PROCESSED.exists():
        processed = json.loads(PROCESSED.read_text(encoding="utf-8"))
    figure_count = 0
    if FIGURES.exists():
        figure_count = sum(1 for line in FIGURES.read_text(encoding="utf-8").splitlines() if line.strip())
    articles = 0
    if ARTICLES.exists():
        articles = sum(1 for line in ARTICLES.read_text(encoding="utf-8").splitlines() if line.strip())
    print(json.dumps({
        "articles_discovered": articles,
        "articles_completed": len(processed.get("pmcids", [])),
        "articles_retryable": len(processed.get("failures", {})),
        "schematic_figures": figure_count,
    }, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Article figure corpus for element extraction")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("discover")
    p.add_argument("--max-articles", type=int, default=400)
    p.add_argument("--max-calls", type=int, default=10)
    p.set_defaults(func=cmd_discover)
    p = sub.add_parser("harvest")
    p.add_argument("--max-articles", type=int, default=100)
    p.add_argument("--retry-failed", action="store_true",
                   help="retry articles whose previous figure download failed")
    p.add_argument("--refresh", action="store_true",
                   help="revisit completed articles to add optional outputs such as PDFs")
    p.add_argument("--download-pdf", action="store_true",
                   help="retain the CC BY publisher PDF for high-resolution redraw")
    p.set_defaults(func=cmd_harvest)
    p = sub.add_parser(
        "harvest-catalog",
        help="harvest all PMC-mapped catalogue papers with CC BY open versions",
    )
    p.add_argument("--max-articles", type=int, default=1000)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--download-pdf", action="store_true")
    p.add_argument("--all-figures", action="store_true")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--retry-permanent", action="store_true",
                   help="retry articles cached as lacking a CC BY PMC OA version")
    p.set_defaults(func=cmd_harvest_catalog)
    p = sub.add_parser("reset")
    p.add_argument("--clear-figures", action="store_true")
    p.add_argument("--purge-source-files", action="store_true",
                   help="also delete downloaded files under source-corpus/figures")
    p.set_defaults(func=cmd_reset)
    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
