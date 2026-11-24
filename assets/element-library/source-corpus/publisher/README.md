# Publisher figure cache

This layer extends the PMC/JATS corpus to publisher pages that expose a
reproducible figure API or PDF and an explicit redistributable licence.

Current adapters:

- APS / Physical Review: verify a CC BY link on the article landing page, read
  the figure band, and render caption-matched regions from the PDF at 300 dpi.
- arXiv: verify a CC BY licence on the abstract page, then use the same PDF
  caption/region extraction.

`figures.jsonl` keeps one record per figure with DOI, title, caption, source
image URL, licence, source-page URL, PDF hash, local image hash and extraction
method. The raw `figures/` and `pdfs/` bytes are ignored by git because they are
large and rebuildable.

Safety rules:

- no paywall bypass;
- a missing page-level licence stops the article;
- a missing caption or a caption containing a third-party-rights phrase keeps
  the figure metadata-only;
- a PDF crop is a review source, not an approved element;
- automatic object crops never enter `assets/element-library/index.json`.

```bash
python scripts/publisher_figure_harvester.py --dry-run
python scripts/publisher_figure_harvester.py --workers 8
python scripts/figure_element_candidates.py
```
