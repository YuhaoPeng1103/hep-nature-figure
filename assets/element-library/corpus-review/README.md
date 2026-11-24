# Figure and element review queue

`candidate_figures.jsonl` is generated from all legally downloaded PMC and
publisher figures. The current snapshot contains:

- 4,695 local figure records;
- 3,578 unique HEP figures after hash and relevance filtering;
- 408 high-priority and 2,769 medium-priority candidates;
- 8,531 automatic object crops;
- 199 contact sheets, in `sheets/`.

Open `index.html` for the searchable visual list. Every image and crop in this
directory is **review-only**. A crop becomes an active library element only
after object/background review, native SVG redraw, source provenance, and the
normal delivery gates.

```bash
python scripts/figure_element_candidates.py
python scripts/figure_element_candidates.py --force --no-crops
```

The raw images, crops, and sheets are git-ignored because they are a large,
rebuildable cache. The JSONL, HTML and report remain versionable; rerun the
harvesters to restore ignored bytes.
