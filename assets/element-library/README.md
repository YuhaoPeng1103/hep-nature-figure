# Element-level vector library

Each entry in `index.json` points to a standalone transparent SVG with no
embedded raster. Built-in assets are code-authored and carry
`origin=software`, `ai_generated=false`.

The library separates two provenance classes:

- `software`: 107 original code-authored system primitives;
- Article-derived elements use a two-file contract:
  - `_edit.svg`: default native object geometry, gradients and native text;
  - `_texture.svg`: optional smooth-path fidelity reference.
- `index.json`'s `file` points to the scalable edit version;
  `generation.edit_file` and `generation.texture_file` expose both paths.
- In a spec element, `render_mode: edit` is the default;
  `render_mode: texture` selects the fidelity reference without changing
  placement.
- Per-element texture deviations are retained in
  `source-derived/texture_metrics.json`; they do not add information beyond the
  source raster.

All 74 article-derived elements are separate from system primitives.
`source-elements.json` also retains disabled review candidates; run extraction
with `--replace --prune` so contaminated or label-containing crops do not enter
the public index.

The nucleon family has 30 variants, including 16 article-derived forms. The
same-position picker can exchange front-lit, side-lit, back-lit, proton,
neutron and fragment-nucleon appearances without changing the slot geometry.

`source-corpus/` is the reproducible upstream layer. It records the HEP query,
DOI, licence, PMC version, figure caption, original media URL and optional CC
BY PDF. `article_element_harvester.py` is resumable: download failures stay in
`failures` and are retried with `--retry-failed`.

`source-corpus/publisher/` adds legally reachable publisher figures beyond PMC.
The current APS adapter verifies the CC BY landing page, screens captions for
third-party-rights phrases, and reconstructs the figure region from the PDF at
300 dpi. `corpus-review/candidate_figures.jsonl` and `corpus-review/index.html`
are the figure-level review queue; its automatic object crops are `review-only`
and are never active library assets.

Final review snapshot: 4,695 local records -> 3,578 unique HEP figures -> 408
high-priority and 2,769 medium-priority review images -> 8,531 object
candidates. The raw figure/crop bytes are a rebuildable local cache and are
git-ignored; the JSONL, report, provenance and hashes remain auditable.

`article_t330_qgp_fireball` comes from the CC BY arXiv review 2512.00739.
The perspective grid, purple electromagnetic field lines and external black
arrows are a separate context layer and are deliberately excluded. Native and
texture versions keep the QGP volume, orange radiation, partons and spirals
(`MAE 0.851`, `>32 0.12%` against the clean native reconstruction).

The canonical QGP-jet scene uses `article_prl125_qgp_jet_scene`, rebuilt from
PRL 125, 122301 Fig. 1. Its native SVG keeps separate QGP, reaction-plane,
photon, jet, axes and label groups; no raster image is embedded.

Native rebuild provenance is listed in
[`source-derived/NATIVE_NOTICE.md`](source-derived/NATIVE_NOTICE.md). Remaining
traces are listed in [`source-derived/NOTICE.md`](source-derived/NOTICE.md).

```bash
python scripts/rebuild_article_vectors.py --check
python scripts/rebuild_article_vectors.py
python scripts/element_texture_vectorize.py
```

The rebuild script ignores already-native assets unless explicit IDs are
provided, so `--ids <asset-id> ...` is the safe way to refresh one object after
changing its geometry function.

Browse the family sheets:

- [Nucleon variants](overviews/nucleon_variants_v51_expanded.png)
- [Texture SVG vs source crop](overviews/texture_source_comparison_v51.png)
- [Article QGP source vs native redraw](overviews/qgp_source_vs_redraw_v52.png)
- [All article-derived native edit elements](overviews/article_derived_native_v51.png)
- [Nucleus variants](overviews/nucleus_variants.png)
- [Per-element pixel-error metrics](source-derived/texture_metrics.json)
- [Pixel-error table](source-derived/texture_metrics.md)
- [Same-position nucleon picker: 29 safe variants](overviews/nucleon_slot_picker_v51/variant_sheet.png)
- [Article-derived-only nucleon picker: 16 variants](overviews/nucleon_slot_picker_source_v51/variant_sheet.png)

```bash
python scripts/element_library.py validate
python scripts/element_library.py list --safe-only
python scripts/element_library.py list --family nucleon
python scripts/element_library.py show qgp_fireball
```

## AI supplementation

When an element is missing, generate or draw it externally, remove the
background, then archive it with explicit provenance:

```bash
python scripts/element_library.py ingest-ai \
  --id detector_custom --source cleaned.png --name-zh 自定义探测器 \
  --category detector --license CC-BY-4.0 --origin ai_raster \
  --tool "image generator" --model MODEL --prompt-file prompt.txt \
  --reviewer author --review-note "silhouette checked against the source"
```

PNG inputs are cropped to their alpha bounds and vectorized with `vtracer`.
`origin=ai_raster` and `origin=ai_generated_vector` are always marked as AI
assets. `origin=ai_assisted_redraw` is allowed only when the submitted file is
already native SVG and contains no AI pixels.

If automatic tracing leaves a bitmap-like element, use the
`references/direct-svg-redraw.md` object-by-object workflow to redraw a clean
transparent SVG, then ingest that SVG. The resulting asset must describe the
redraw as a modification of the cited source; tracing or redraw never upgrades
its source resolution.

## Submission-safe mode

`spec_compile.py --safe-mode` admits only licence-cleared software or human
vectors with `contains_ai_pixels=false`. AI-origin assets remain available for
exploration but are excluded from the submission-safe build.
