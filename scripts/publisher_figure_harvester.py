#!/usr/bin/env python3
"""Harvest legally available publisher figure records beyond PMC.

The current adapter handles APS/Physical Review CC BY landing pages. It keeps a
resumable metadata index, downloads figure media only when the article and
figure caption pass the licence checks, and records enough provenance for
later element extraction. This is deliberately not a paywall bypass.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "assets" / "schematic-library"
CANDIDATES = LIB / "candidates.jsonl"
CORPUS = ROOT / "assets" / "element-library" / "source-corpus" / "publisher"
FIGURES = CORPUS / "figures.jsonl"
PROCESSED = CORPUS / "processed_articles.json"
MEDIA = CORPUS / "figures"
PDF_CACHE = CORPUS / "pdfs"
TODAY = dt.date.today().isoformat()
UA = "hep-nature-figure/5.1 (mailto:pngyuo@cug.edu.cn)"
CC_BY_RE = re.compile(
    r"(?i)creativecommons\.org/licenses/by/(?:3\.0|4\.0)|(?:^|[;\s])cc[- ]?by(?:$|[;\s])"
)
RIGHTS_RE = re.compile(
    r"(?i)reprinted with permission|adapted with permission|"
    r"copyright\s*©|courtesy of|used with permission|"
    r"all rights reserved"
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def request_bytes(url: str, timeout: int = 60) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", ""), response.geturl()


def image_payload(data: bytes, content_type: str = "") -> bool:
    ctype = (content_type or "").casefold()
    if ctype in {"application/octet-stream", "binary/octet-stream"}:
        ctype = ""
    if ctype.startswith("image/"):
        return len(data) >= 1024
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"GIF8")
        or data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ) and len(data) >= 1024


def slug(value: str, limit: int = 90) -> str:
    value = urllib.parse.unquote(value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return value[:limit] or hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def is_aps(candidate: dict) -> bool:
    doi = str(candidate.get("doi") or "").casefold()
    journal = str(candidate.get("journal") or "")
    return doi.startswith("10.1103/") or journal.startswith("Physical Review")


def arxiv_id(candidate: dict) -> str:
    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z-]+/\d{7})",
        str(candidate.get("oa_url") or ""),
        re.I,
    )
    return match.group(1) if match else ""


def redistributable(candidate: dict) -> bool:
    return bool(CC_BY_RE.search(str(candidate.get("license") or "")))


def hep_candidate(candidate: dict) -> bool:
    try:
        from article_element_harvester import hep_article_relevant
    except Exception:
        return True
    return hep_article_relevant(
        str(candidate.get("title") or ""),
        str(candidate.get("abstract") or ""),
    )


def parse_aps_figures(page: str, base_url: str) -> list[dict]:
    """Return unique figure media and labels from an APS landing page."""
    from lxml import html as lxml_html

    doc = lxml_html.fromstring(page)
    found = {}
    for img in doc.xpath(
        "//div[@aria-label='Article figures']//img[@src]"
    ):
        src = img.get("src") or ""
        if not src:
            continue
        url = urllib.parse.urljoin(base_url, src)
        alt = (img.get("alt") or "").strip()
        label_match = re.search(r"(?:figure|fig\.?)\s*(\d+)", alt, re.I)
        index = int(label_match.group(1)) if label_match else len(found) + 1
        found.setdefault(index, {
            "label": f"Figure {index}",
            "remote_image": url,
        })
    return [found[index] for index in sorted(found)]


def page_has_cc_by(page: str) -> bool:
    from lxml import html as lxml_html

    doc = lxml_html.fromstring(page)
    hrefs = " ".join(doc.xpath("//a/@href"))
    return bool(CC_BY_RE.search(hrefs))


def pdf_figure_data(pdf_data: bytes) -> dict[int, dict]:
    """Extract caption blocks and conservative high-resolution crop regions."""
    try:
        import fitz
    except ImportError:
        return {}
    figures = {}
    with fitz.open(stream=pdf_data, filetype="pdf") as doc:
        for page in doc:
            blocks = [
                {
                    "box": tuple(float(v) for v in block[:4]),
                    "text": str(block[4] or "").strip(),
                }
                for block in page.get_text("blocks")
            ]
            for block in blocks:
                match = re.match(
                    r"(?i)(?:FIG\.?|FIGURE)\s*(\d+)[.:]?\s+",
                    block["text"],
                )
                if not match:
                    continue
                number = int(match.group(1))
                if number in figures:
                    continue
                x0, y0, x1, y1 = block["box"]
                full_width = (x1 - x0) >= page.rect.width * 0.65
                above = []
                for other in blocks:
                    if other is block:
                        continue
                    ox0, oy0, ox1, oy1 = other["box"]
                    if oy1 >= y0 - 2:
                        continue
                    if oy1 <= 45 or oy0 >= page.rect.height - 45:
                        continue
                    overlap = max(0.0, min(x1, ox1) - max(x0, ox0))
                    if overlap < max(1.0, min(x1 - x0, ox1 - ox0) * 0.35):
                        continue
                    above.append(oy1)
                previous_end = max(above, default=45.0)
                crop_x0 = 42.0 if full_width else x0 - 4
                crop_x1 = page.rect.width - 42.0 if full_width else x1 + 4
                crop_y0 = max(42.0, previous_end + 5.0)
                crop_y1 = max(crop_y0 + 1.0, y0 - 4.0)
                if crop_y1 - crop_y0 < 45:
                    continue
                figures[number] = {
                    "page_index": page.number,
                    "pdf_rect": [crop_x0, crop_y0, crop_x1, crop_y1],
                    "caption": html.unescape(re.sub(r"\s+", " ", block["text"]))[:4000],
                }
    return figures


def pdf_url_from_landing(landing_url: str) -> str:
    if "/abstract/" in landing_url:
        return landing_url.replace("/abstract/", "/pdf/", 1)
    parsed = urllib.parse.urlsplit(landing_url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + ".pdf", "", "")
    )


def harvest_aps_one(candidate: dict, keep_pdf: bool = False) -> dict:
    doi = str(candidate.get("doi") or "").strip()
    landing = f"https://doi.org/{urllib.parse.quote(doi, safe='/():')}"
    page_data, page_ctype, final_url = request_bytes(landing)
    if "text/html" not in (page_ctype or "").casefold():
        raise RuntimeError(f"landing page is not HTML: {page_ctype}")
    page = page_data.decode("utf-8", "replace")
    if not page_has_cc_by(page):
        raise PermissionError("landing page does not confirm CC BY")
    figs = parse_aps_figures(page, final_url)
    if not figs:
        raise RuntimeError("no APS figure-band images found")

    pdf_figures = {}
    pdf_rel = ""
    pdf_sha = ""
    pdf_data = b""
    pdf_url = pdf_url_from_landing(final_url)
    try:
        pdf_data, pdf_ctype, _ = request_bytes(pdf_url)
        if pdf_data.startswith(b"%PDF-"):
            pdf_figures = pdf_figure_data(pdf_data)
            pdf_sha = sha256_bytes(pdf_data)
            if keep_pdf:
                dest = PDF_CACHE / (slug(doi) + ".pdf")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(pdf_data)
                pdf_rel = dest.relative_to(ROOT).as_posix()
    except (OSError, RuntimeError, urllib.error.URLError):
        pass

    records = []
    skipped = []
    retry_ids = []
    article_key = slug(doi)
    for fig in figs:
        index_match = re.search(r"(\d+)", fig["label"])
        index = int(index_match.group(1)) if index_match else len(records) + 1
        figure_pdf = pdf_figures.get(index) or {}
        caption = figure_pdf.get("caption", "")
        rights_unverified = not caption
        rights_flag = bool(RIGHTS_RE.search(caption)) or rights_unverified
        row = {
            "figure_id": f"aps-{article_key}-fig{index:02d}",
            "candidate_id": candidate.get("candidate_id"),
            "doi": doi,
            "title": candidate.get("title"),
            "authors": candidate.get("authors"),
            "year": candidate.get("year"),
            "journal": candidate.get("journal"),
            "figure_label": fig["label"],
            "caption": caption,
            "remote_image": fig["remote_image"],
            "license": "CC-BY-4.0",
            "license_source_url": final_url,
            "rights_review": (
                "caption unavailable; figure kept metadata-only"
                if rights_unverified
                else "caption flags third-party rights"
                if rights_flag
                else "no third-party permission phrase in extracted caption"
            ),
            "topics": candidate.get("topics", []),
            "source": "aps-html",
            "source_pdf_sha256": pdf_sha,
            "source_pdf": pdf_rel,
        }
        if rights_flag:
            row["local_file"] = ""
            row["status"] = (
                "metadata-only-caption-unavailable"
                if rights_unverified
                else "metadata-only-rights-review"
            )
            skipped.append(row["figure_id"])
            records.append(row)
            continue
        data = None
        suffix = ".png"
        try:
            import fitz

            with fitz.open(stream=pdf_data, filetype="pdf") as doc:
                page = doc[figure_pdf["page_index"]]
                pixmap = page.get_pixmap(
                    clip=fitz.Rect(figure_pdf["pdf_rect"]),
                    dpi=300,
                    alpha=False,
                )
                data = pixmap.tobytes("png")
            if len(data) < 1024:
                raise ValueError("PDF figure crop is empty")
            row["extraction_method"] = "pdf-region-300dpi"
        except Exception:
            data, ctype, _ = request_bytes(fig["remote_image"])
            if not image_payload(data, ctype):
                row["local_file"] = ""
                row["status"] = "image-download-failed"
                skipped.append(row["figure_id"])
                retry_ids.append(row["figure_id"])
                records.append(row)
                continue
            raw_suffix = Path(urllib.parse.urlsplit(fig["remote_image"]).path).suffix.casefold()
            suffix = raw_suffix if raw_suffix in IMAGE_SUFFIXES else ".jpg"
            row["extraction_method"] = "publisher-thumbnail-fallback"
        dest = MEDIA / "aps" / str(candidate.get("year") or "unknown") / article_key / (
            f"fig{index:02d}{suffix}"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)
        row.update({
            "local_file": dest.relative_to(ROOT).as_posix(),
            "local_sha256": sha256(dest),
            "status": "downloaded",
        })
        records.append(row)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "doi": doi,
        "figures": records,
        "skipped_figure_ids": skipped,
        "retry_figure_ids": retry_ids,
        "landing_url": final_url,
    }


def harvest_arxiv_one(candidate: dict, keep_pdf: bool = False) -> dict:
    arxiv = arxiv_id(candidate)
    if not arxiv:
        raise ValueError("candidate has no arXiv id")
    abs_url = f"https://arxiv.org/abs/{arxiv}"
    page_data, page_ctype, final_url = request_bytes(abs_url)
    if "text/html" not in (page_ctype or "").casefold():
        raise RuntimeError(f"arXiv landing page is not HTML: {page_ctype}")
    page = page_data.decode("utf-8", "replace")
    if not page_has_cc_by(page):
        raise PermissionError("arXiv version does not confirm CC BY")
    pdf_url = f"https://arxiv.org/pdf/{arxiv}"
    pdf_data, pdf_ctype, _ = request_bytes(pdf_url)
    if not pdf_data.startswith(b"%PDF-"):
        raise RuntimeError(f"arXiv PDF endpoint returned {pdf_ctype}")
    pdf_figures = pdf_figure_data(pdf_data)
    if not pdf_figures:
        raise RuntimeError("no numbered figure captions found in arXiv PDF")
    pdf_sha = sha256_bytes(pdf_data)
    pdf_rel = ""
    if keep_pdf:
        dest = PDF_CACHE / (slug("arxiv-" + arxiv) + ".pdf")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pdf_data)
        pdf_rel = dest.relative_to(ROOT).as_posix()

    records = []
    skipped = []
    retry_ids = []
    article_key = slug("arxiv-" + arxiv)
    for index, figure in sorted(pdf_figures.items()):
        caption = figure.get("caption", "")
        rights_unverified = not caption
        rights_flag = bool(RIGHTS_RE.search(caption)) or rights_unverified
        row = {
            "figure_id": f"arxiv-{article_key}-fig{index:02d}",
            "candidate_id": candidate.get("candidate_id"),
            "arxiv": arxiv,
            "doi": candidate.get("doi"),
            "title": candidate.get("title"),
            "authors": candidate.get("authors"),
            "year": candidate.get("year"),
            "journal": candidate.get("journal"),
            "figure_label": f"Figure {index}",
            "caption": caption,
            "remote_image": pdf_url,
            "license": "CC-BY-4.0",
            "license_source_url": final_url,
            "rights_review": (
                "caption unavailable; figure kept metadata-only"
                if rights_unverified
                else "caption flags third-party rights"
                if rights_flag
                else "no third-party permission phrase in extracted caption"
            ),
            "topics": candidate.get("topics", []),
            "source": "arxiv-pdf",
            "source_pdf_sha256": pdf_sha,
            "source_pdf": pdf_rel,
        }
        if rights_flag:
            row["local_file"] = ""
            row["status"] = (
                "metadata-only-caption-unavailable"
                if rights_unverified
                else "metadata-only-rights-review"
            )
            skipped.append(row["figure_id"])
            records.append(row)
            continue
        try:
            import fitz

            with fitz.open(stream=pdf_data, filetype="pdf") as doc:
                page = doc[figure["page_index"]]
                pixmap = page.get_pixmap(
                    clip=fitz.Rect(figure["pdf_rect"]),
                    dpi=300,
                    alpha=False,
                )
                data = pixmap.tobytes("png")
            if len(data) < 1024:
                raise ValueError("PDF figure crop is empty")
        except Exception as exc:
            row["local_file"] = ""
            row["status"] = "image-extraction-failed"
            row["error"] = str(exc)
            skipped.append(row["figure_id"])
            retry_ids.append(row["figure_id"])
            records.append(row)
            continue
        dest = MEDIA / "arxiv" / str(candidate.get("year") or "unknown") / article_key / (
            f"fig{index:02d}.png"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)
        row.update({
            "local_file": dest.relative_to(ROOT).as_posix(),
            "local_sha256": sha256(dest),
            "extraction_method": "pdf-region-300dpi",
            "status": "downloaded",
        })
        records.append(row)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "doi": candidate.get("doi"),
        "arxiv": arxiv,
        "figures": records,
        "skipped_figure_ids": skipped,
        "retry_figure_ids": retry_ids,
        "landing_url": final_url,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Harvest publisher CC BY HEP figures")
    ap.add_argument("--max-articles", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--keep-pdf", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not CANDIDATES.exists():
        raise SystemExit("candidate index is missing")

    candidates = [
        row for row in load_jsonl(CANDIDATES)
        if (is_aps(row) or arxiv_id(row))
        and redistributable(row)
        and hep_candidate(row)
    ]
    existing_rows = load_jsonl(FIGURES)
    existing = {row["figure_id"]: row for row in existing_rows}
    state = (
        json.loads(PROCESSED.read_text(encoding="utf-8"))
        if PROCESSED.exists()
        else {}
    )
    processed = set(state.get("candidate_ids", []))
    failures = dict(state.get("failures", {}))
    for failure in failures.values():
        message = str(failure.get("error") or "")
        if any(
            marker in message
            for marker in (
                "does not confirm CC BY",
                "no APS figure-band images",
                "no numbered figure captions",
            )
        ):
            failure["kind"] = "permanent"
    pending = []
    for candidate in candidates:
        cid = str(candidate.get("candidate_id") or candidate.get("doi"))
        if cid in processed and not args.refresh:
            continue
        failure = failures.get(cid) or {}
        if failure.get("kind") == "permanent" and not args.retry_failed:
            continue
        pending.append(candidate)
    pending = pending[:max(0, args.max_articles)]
    if args.dry_run:
        print(json.dumps({
            "publisher_cc_by_hep_candidates": len(candidates),
            "aps_candidates": sum(is_aps(row) for row in candidates),
            "arxiv_candidates": sum(bool(arxiv_id(row)) and not is_aps(row) for row in candidates),
            "pending_this_run": len(pending),
            "processed": len(processed),
            "cached_failures": len(failures),
        }, ensure_ascii=False, indent=2))
        return 0

    completed = downloaded = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(8, args.workers))
    ) as pool:
        futures = {
            pool.submit(
                harvest_aps_one if is_aps(candidate) else harvest_arxiv_one,
                candidate,
                args.keep_pdf,
            ): candidate
            for candidate in pending
        }
        for future in concurrent.futures.as_completed(futures):
            candidate = futures[future]
            cid = str(candidate.get("candidate_id") or candidate.get("doi"))
            try:
                result = future.result()
            except PermissionError as exc:
                failures[cid] = {
                    "kind": "permanent",
                    "error": str(exc),
                    "updated": TODAY,
                }
                print(f"SKIP {cid}: {exc}", file=sys.stderr, flush=True)
                put_json(PROCESSED, {
                    "candidate_ids": sorted(processed),
                    "failures": failures,
                    "updated": TODAY,
                })
                continue
            except Exception as exc:
                message = str(exc)
                failures[cid] = {
                    "kind": (
                        "permanent"
                        if any(
                            marker in message
                            for marker in (
                                "does not confirm CC BY",
                                "no APS figure-band images",
                                "no numbered figure captions",
                            )
                        )
                        else "transient"
                    ),
                    "error": message,
                    "updated": TODAY,
                }
                print(f"WARN {cid}: {exc}", file=sys.stderr, flush=True)
                put_json(PROCESSED, {
                    "candidate_ids": sorted(processed),
                    "failures": failures,
                    "updated": TODAY,
                })
                continue
            for row in result["figures"]:
                existing[row["figure_id"]] = row
                if row.get("status") == "downloaded":
                    downloaded += 1
            if result["retry_figure_ids"]:
                failures[cid] = {
                    "kind": "figure",
                    "error": f"{len(result['retry_figure_ids'])} figure(s) failed",
                    "figure_ids": result["retry_figure_ids"],
                    "updated": TODAY,
                }
            else:
                failures.pop(cid, None)
                processed.add(cid)
            completed += 1
            put_jsonl(FIGURES, sorted(existing.values(), key=lambda row: row["figure_id"]))
            put_json(PROCESSED, {
                "candidate_ids": sorted(processed),
                "failures": failures,
                "updated": TODAY,
            })
            print(
                f"[{completed}/{len(pending)}] {cid}: "
                f"+{sum(row.get('status') == 'downloaded' for row in result['figures'])} "
                f"figure(s)",
                flush=True,
            )
    print(json.dumps({
        "publisher_cc_by_hep_candidates": len(candidates),
        "aps_candidates": sum(is_aps(row) for row in candidates),
        "arxiv_candidates": sum(bool(arxiv_id(row)) and not is_aps(row) for row in candidates),
        "attempted": completed,
        "figures_downloaded": downloaded,
        "processed_articles": len(processed),
        "cached_failures": len(failures),
    }, ensure_ascii=False, indent=2))
    status_counts = {}
    source_counts = {}
    for row in existing.values():
        status_counts[row.get("status", "unknown")] = (
            status_counts.get(row.get("status", "unknown"), 0) + 1
        )
        source_counts[row.get("source", "unknown")] = (
            source_counts.get(row.get("source", "unknown"), 0) + 1
        )
    put_json(CORPUS / "report.json", {
        "schema_version": "1.0",
        "updated": TODAY,
        "candidate_articles": len(candidates),
        "processed_articles": len(processed),
        "cached_failures": len(failures),
        "figure_records": len(existing),
        "by_status": status_counts,
        "by_source": source_counts,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
