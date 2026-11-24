# High-priority object rebuild queue

This directory is the first per-object pass over the 408 `high` priority
figures from `corpus-review`.

Current result:

- 3,599 object proposals considered from recorded and resegmented candidates;
- 3,595 need manual object separation or redraw;
- 4 pass the conservative single-object rule and have a smooth native SVG
  candidate, spanning 2 figures;
- zero objects have been added to the active element library.

The 1,265 manual rows are not failures of the source extraction. Most automatic
boxes contain several connected physical objects, labels, axes, or diagram
lines that must be split semantically. The pipeline deliberately refuses to
turn a whole compound panel into an "element".

Files:

- `objects.jsonl`: per-object source, transparent cutout, vector-candidate hash,
  audit metrics, and status;
- `report.json`: counts and review artifacts;
- `index.html`: review-only transparent cutouts;
- `sheets/native-candidates-*.jpg`: cutout versus native-vector candidates.

```bash
python scripts/priority_element_rebuild.py --dry-run
python scripts/priority_element_rebuild.py
python scripts/priority_element_rebuild.py --force
```

The generated crops and candidate SVGs are a rebuildable review cache. They do
not enter `index.json` without manual approval.
