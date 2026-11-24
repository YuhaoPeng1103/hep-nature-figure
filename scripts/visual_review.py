#!/usr/bin/env python3
"""Record and verify human visual review of a compiled figure."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

try:
    from _console import init_console
    init_console()
except Exception:
    pass

CLIENT_ROLES = {"client", "customer", "author", "user", "客户", "作者", "用户", "甲方"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_path(png: Path, explicit: str | None) -> Path:
    return Path(explicit).expanduser().resolve() if explicit else png.with_suffix(".review.json")


def main():
    ap = argparse.ArgumentParser(description="Visual-review receipt for compiled figure")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--svg", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--pdf")
    ap.add_argument("--receipt")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--by", default="")
    ap.add_argument("--reply", default="")
    a = ap.parse_args()
    spec, svg, png = (Path(a.spec).resolve(), Path(a.svg).resolve(), Path(a.png).resolve())
    pdf = Path(a.pdf).resolve() if a.pdf else None
    for path in (spec, svg, png):
        if not path.exists():
            raise SystemExit(f"missing review input: {path}")
    rec = receipt_path(png, a.receipt)
    current = {
        "spec_sha256": sha256(spec),
        "svg_sha256": sha256(svg),
        "png_sha256": sha256(png),
        "pdf_sha256": sha256(pdf) if pdf and pdf.exists() else None,
    }
    if a.record:
        if a.by not in CLIENT_ROLES:
            raise SystemExit("--by must identify the client/author")
        if not a.reply.strip():
            raise SystemExit("--reply must preserve the reviewer's original wording")
        doc = {
            "schema_version": "1.0",
            **current,
            "reviewed_by": a.by,
            "reply": a.reply,
            "reviewed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "approved",
        }
        rec.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"visual review recorded -> {rec}")
        return 0
    if rec.exists():
        doc = json.loads(rec.read_text(encoding="utf-8"))
        # PDF writers may embed a creation timestamp, so the visual receipt is
        # bound to the deterministic SVG and rendered PNG plus the spec hash.
        errors = [name for name, value in current.items()
                  if name != "pdf_sha256"
                  if value is not None and doc.get(name) != value]
        if doc.get("status") != "approved" or doc.get("reviewed_by") not in CLIENT_ROLES:
            errors.append("review status/reviewer")
        if errors:
            print("FAIL: visual review no longer matches outputs: " + ", ".join(errors))
            return 1
        print(f"PASS: visual review approved by {doc['reviewed_by']} at {doc['reviewed_at']}")
        return 0
    print(f"FAIL: visual review receipt missing: {rec}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
