# Article source corpus

This directory is the resumable input layer for `article_element_harvester.py`.
It does not claim exhaustive journal coverage. It records a systematic Europe
PMC search, licence resolution through the PMC Open Access bucket, and the
legally downloadable subset.

## Current state

- `articles.jsonl`: 10 records from the initial narrow discovery pass.
- `processed_articles.json`: 159 legacy PMC articles processed; 46 remain in the
  retry/failure set and are never treated as success.
- `figures.jsonl`: 1,138 legacy PMC/JATS figure records. New PMC rows deduplicate
  by graphic URL; the review index also deduplicates all local bytes.
- `figures/`: redistributable CC BY figure bytes (ignored git cache).
- `pdfs/`: optional CC BY PDF cache (ignored).
- `publisher/`: APS/PR + arXiv figure records and 300 dpi PDF crops.

The broader metadata index is in `../../schematic-library/`: 5,245 DOI-
deduplicated candidates across Nature, Physical Review/APS and core HEP
journals. Subscription and non-CC-BY figures stay metadata-only.

## Commands

```bash
python scripts/article_element_harvester.py discover
python scripts/article_element_harvester.py harvest --retry-failed --download-pdf
python scripts/article_element_harvester.py harvest-catalog --all-figures --workers 4
python scripts/publisher_figure_harvester.py --workers 12
python scripts/figure_element_candidates.py
python scripts/article_element_harvester.py status
```

`harvest` selects a non-retracted open version with a redistributable CC BY
licence. Each figure record retains DOI, licence, PMC version, source media URL,
local SHA-addressable output path, and optional source PDF. The extraction step
is documented in `../source-elements.json`.

The publisher layer currently includes an APS/PR CC BY adapter. It reads figure
media from the landing page and reconstructs a high-resolution figure crop from
the PDF; captions containing third-party permission language, or cases where a
caption cannot be extracted, remain metadata-only.

Completed publisher pass (2026-11-22): 574 strict HEP + CC BY candidates, 524
articles processed, 4,568 figure records, and 3,557 downloaded high-resolution
figure regions. The other 1,011 records remain metadata-only because the exact
caption could not be verified; 50 article-level failures stay in the retry cache.

Older catalog batches predate the stricter title/abstract classifier. They are
kept as auditable history, but `figure_element_candidates.py` rejects known
cross-domain keyword collisions before any figure enters the review queue.

Final review snapshot after the publisher pass: 4,695 local figure records,
3,578 unique HEP figures after hash/relevance filtering, 8,531 review-only
object candidates and 199 contact sheets. `corpus-review/index.html` is the
browsable review queue.

Raw `figures/`, `pdfs/`, publisher figure bytes and review sheets are ignored by
git because they are large and rebuildable. The committed JSONL manifests keep
source URLs, licences and hashes; rerun the harvesters to restore the cache.
