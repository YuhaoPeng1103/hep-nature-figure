#!/usr/bin/env python3
"""Confirm the structured figure spec before deterministic assembly.

The receipt binds the client approval to a SHA-256 of the complete spec, so
changing an element, label, connection, geometry, or canvas invalidates it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

try:
    from _console import init_console
    init_console()
except Exception:
    pass

CLIENT_ROLES = {"client", "customer", "author", "user", "客户", "作者", "用户", "甲方"}


def load_spec(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if yaml is not None:
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit("YAML spec requires PyYAML; install pyyaml") from exc


def canonical_hash(spec: dict) -> str:
    payload = json.dumps(
        spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def receipt_path(spec_path: Path, explicit: str | None) -> Path:
    return Path(explicit).expanduser().resolve() if explicit else spec_path.with_suffix(".confirmation.json")


def ids(spec: dict, key: str) -> list[str]:
    return [str(x.get("id", "")) for x in (spec.get(key) or []) if x.get("id")]


def summary(spec: dict) -> dict:
    fig = spec.get("figure") or {}
    canvas = fig.get("canvas") or {}
    return {
        "figure_id": fig.get("id") or fig.get("name") or "",
        "canvas_mm": [canvas.get("width_mm"), canvas.get("height_mm")],
        "target": fig.get("target_journal") or fig.get("target") or "",
        "elements": ids(spec, "elements"),
        "texts": ids(spec, "texts"),
        "connections": ids(spec, "connections"),
        "relationships": ids(spec, "relationships"),
        "hard_physics": ids(spec, "hard_physics"),
        "projection": (spec.get("composition") or {}).get("projection", {}),
        "style_mode": (spec.get("style") or {}).get("mode", ""),
    }


def print_summary(spec: dict, spec_path: Path, digest: str) -> None:
    data = summary(spec)
    print(f"Spec: {spec_path}")
    print(f"SHA-256: {digest}")
    print(f"Canvas: {data['canvas_mm'][0]} x {data['canvas_mm'][1]} mm")
    print(f"Target: {data['target'] or '-'} | Style: {data['style_mode'] or '-'}")
    print("Elements:")
    by_id = {e.get("id"): e for e in (spec.get("elements") or [])}
    for eid in data["elements"]:
        e = by_id[eid]
        selected = e.get("asset") or (
            f"{e.get('asset_family') or '-'}:{e.get('asset_variant') or '-'}"
        )
        options = e.get("variant_options") or []
        print(f"  {eid}: {e.get('name') or selected} | asset={selected} | "
              f"options={len(options)} | role={e.get('physics_role') or '-'}")
    print("Texts:")
    for t in (spec.get("texts") or []):
        print(f"  {t.get('id')}: {t.get('value') or t.get('text') or ''}")
    print("Connections:")
    for c in (spec.get("connections") or []):
        print(f"  {c.get('id')}: {c.get('type')} {c.get('from')} -> {c.get('to')}")
    print("Relationships:")
    for r in (spec.get("relationships") or []):
        print(f"  {r.get('id')}: {r.get('type')} {r.get('subject')} / {r.get('object')}")
    print("Hard physics:")
    for hp in (spec.get("hard_physics") or []):
        print(f"  {hp.get('id')}: {hp.get('claim')} | measure={hp.get('measure')}")


def cmd_check(spec_path: Path, rec_path: Path, quiet: bool = False) -> int:
    spec = load_spec(spec_path)
    if not rec_path.exists():
        print(f"FAIL: confirmation receipt missing: {rec_path}")
        return 1
    receipt = json.loads(rec_path.read_text(encoding="utf-8"))
    digest = canonical_hash(spec)
    errors = []
    if receipt.get("spec_sha256") != digest:
        errors.append("spec changed after confirmation")
    if receipt.get("confirmed_by") not in CLIENT_ROLES:
        errors.append(f"confirmation role is not a client role: {receipt.get('confirmed_by')}")
    if receipt.get("summary") != summary(spec):
        errors.append("confirmed element/text/connection summary no longer matches spec")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    if not quiet:
        print(f"PASS: spec confirmed by {receipt['confirmed_by']} at {receipt.get('confirmed_at')}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Confirm or verify a figure spec")
    ap.add_argument("spec")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--show", action="store_true")
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--receipt")
    ap.add_argument("--reply", default="")
    ap.add_argument("--by", default="")
    a = ap.parse_args()
    spec_path = Path(a.spec).expanduser().resolve()
    if not spec_path.exists():
        raise SystemExit(f"spec not found: {spec_path}")
    rec = receipt_path(spec_path, a.receipt)
    if a.record:
        if a.by not in CLIENT_ROLES:
            raise SystemExit("--by must identify the client/author; agent/auto/codex are rejected")
        if not a.reply.strip():
            raise SystemExit("--reply must preserve the client's original wording")
        spec = load_spec(spec_path)
        receipt = {
            "schema_version": "1.0",
            "spec": str(spec_path),
            "spec_sha256": canonical_hash(spec),
            "confirmed_by": a.by,
            "reply": a.reply,
            "confirmed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "summary": summary(spec),
        }
        rec.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"confirmed {spec_path.name} -> {rec}")
        return 0
    if a.check:
        return cmd_check(spec_path, rec)
    spec = load_spec(spec_path)
    print_summary(spec, spec_path, canonical_hash(spec))
    if rec.exists():
        print()
        return cmd_check(spec_path, rec, quiet=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
