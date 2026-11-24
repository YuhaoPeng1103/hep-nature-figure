# HEP schematic library

Version 5.1 adds a license-aware discovery layer around the existing
`assets/t3-exemplars/` collection.

Current seed: 63 records, 20 locally redistributable figures, 43 metadata-only
references, and 5,245 DOI-deduplicated article candidates from 16 maintained
HEP queries.

## Two tiers

| Tier | Repository contents | Use |
|---|---|---|
| Redistributable | CC0 / CC BY figures with attribution and hashes | `--ref` style library |
| Metadata only | DOI, title, venue, query hit, license/access link | Search and manual retrieval |

Subscription and default-license arXiv figures are never copied into this
repository. Metadata records point to the authoritative source instead.

## Files

- `catalog.json`: verified figures and provenance-only references.
- `catalog.schema.json`: machine-readable record contract.
- `taxonomy.json`: HEP topics, schematic types, style tags, license classes.
- `queries.json`: maintained journal groups and discovery queries.
- `candidates.jsonl`: generated article candidates awaiting figure review.
- `discovery_report.json`: query counts and retrieval date.
- `crossref_report.json`: Crossref pagination coverage for APS/HEP journals.

## Commands

```bash
python scripts/schematic_library.py stats
python scripts/schematic_library.py validate
python scripts/schematic_library.py search --topic jet-quenching --local-only
python scripts/schematic_library.py search --q detector --format markdown
python scripts/schematic_library.py discover --max-per-query 200
python scripts/schematic_library.py discover-crossref --max-per-query 1000
python scripts/schematic_library.py prune-candidates
python scripts/schematic_library.py harvest-europepmc --query-id qgp --max-records 5
python scripts/schematic_library.py import-legacy --log <local-license-log.md>
```

The element-level download path is separate and resumable:

```bash
python scripts/article_element_harvester.py discover
python scripts/article_element_harvester.py harvest --retry-failed --download-pdf
python scripts/article_element_harvester.py harvest-catalog --all-figures --workers 4
python scripts/publisher_figure_harvester.py --dry-run
python scripts/publisher_figure_harvester.py --workers 12
python scripts/figure_element_candidates.py
python scripts/article_element_harvester.py status
```

`search --for-ref` returns only local, redistributable images suitable for the
`--ref` argument. A catalog match is a style reference, not permission to copy
the figure's physics content.

PMC records are deduplicated by graphic URL. The APS/PR adapter independently
checks the CC BY landing page, screens captions for third-party-rights phrases,
and reconstructs 300 dpi figure regions from the PDF. Figures with no caption
or a rights warning remain metadata-only. Automatic element crops generated
from the harvested corpus are review-only until object review and native SVG
rebuild.

## Coverage claim

The catalog is a reproducible, maintained index. It does not claim that every
schematic ever published in these journals is indexed. Coverage is reported by
query family, journal group, license tier, and figure-review status.
