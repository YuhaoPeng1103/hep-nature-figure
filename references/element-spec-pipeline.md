# Element-spec production pipeline

This is the v5.1 code-composition route. The structured spec is the IR: it is
the object of user confirmation, physics review, compilation, and iteration.

```
spec draft / author sketch
  -> spec_confirm.py (client-confirmed IR)
  -> element_library.py (licensed vector resolution; AI provenance retained)
  -> spec_compile.py (deterministic SVG assembly)
  -> nature_gate.py + render / 3D / delivery checks
  -> SVG + PDF + 600 dpi PNG + manifest
```

## Spec layers

| Layer | Required content |
|---|---|
| `figure` | ID, title, target journal, canvas in mm |
| `style` | `render3d`, background, palette, typography |
| `composition` | projection, right-handed coordinates, beam axis, layout regions and guides |
| `elements` | stable ID, asset ID, physics role, mm placement, z order |
| `texts` | native text, mm position, point size, font |
| `connections` | arrows/lines/elbows/freeform paths between semantic elements |
| `relationships` | inside, overlaps, originates-from, behind/front, etc. |
| `hard_physics` | claim + measurable/falsifiable criterion |

The full spec is hashed into `.confirmation.json`. Changing any byte-level
semantic value invalidates confirmation and requires a new client receipt.

Each hard-physics item declares `verification: machine|human`. Machine checks
currently support `opposite_rays`, `angle_between_rays`, and `distance_ratio`
on element centres. Human checks remain visible in the manifest and require
visual review; they are never silently treated as machine-verified.

`composition.layout` makes placement part of the IR instead of a loose list of
coordinates. The compiler validates declared regions, horizontal incoming-state
alignment, symmetry about the overlap, back-to-back jets, and label avoidance.
Reaction-plane grids, beamlines and axis triads are code-rendered structural
guides, not article-derived physical elements.

Element slots preserve the source aspect ratio by default (`fit: contain`).
Use `fit: stretch` only when a non-uniform mapping is an explicit physics or
layout decision; silently stretching a source crop changes both the object and
the antialiased texture boundary.

## Element library

```bash
python scripts/element_library.py validate
python scripts/element_library.py list --safe-only
python scripts/element_library.py show qgp_fireball
```

Built-in elements are transparent native SVGs. Their metadata records family,
variant, licence,
attribution, SHA-256, dimensionality, review, and generation origin.

Article-derived entries are paired: `_edit.svg` is the default scalable native
SVG, and `_texture.svg` is the optional fidelity reference. Set
`render_mode: texture` on one element to use the latter without changing its
slot.
The `smooth-mesh` texture backend keeps broad illumination as continuous
two-dimensional gradients and adds a fine residual mesh for lines and
anti-aliased edges. It uses the source alpha as exact geometry, composites the
visible appearance over white, and removes the crop's white canvas rectangle.
Transparent RGB hidden outside the silhouette must never become a colour halo.
The texture remains pure vector and has no embedded image. Publication output
uses `_edit.svg` unless the verified texture is selected explicitly.
Their metadata records source asset, source SHA-256, crop box, texture error
metrics and redraw method. `software` entries are separate code-authored
fallbacks.

For fidelity review, compare the source crop and SVG at the same original pixel
size. QGP T3-30 is the regression fixture: after excluding its perspective grid
and field context, native/texture agreement is `MAE 0.851`, `>32 0.12%`. A redraw
with visibly displaced objects does not pass merely because its object groups
and layer names are complete.

The current library has 181 variants: 74 article-derived native redraws plus
107 software fallbacks. The nucleon family has 30
variants, 16 of them article-derived. Use
`source-corpus/` for reproducible upstream article discovery and the optional
CC BY PDF that improves crop resolution.

```bash
python scripts/article_element_harvester.py status
python scripts/article_element_harvester.py harvest --retry-failed --download-pdf
python scripts/article_element_harvester.py harvest-catalog --all-figures --workers 4
python scripts/publisher_figure_harvester.py --dry-run
python scripts/publisher_figure_harvester.py --workers 12
python scripts/figure_element_candidates.py
python scripts/priority_element_rebuild.py --dry-run
python scripts/priority_element_rebuild.py --object-source both
python scripts/rebuild_article_vectors.py --check
python scripts/rebuild_article_vectors.py
```

The wider metadata candidate index is separate from redistribution rights:
5,245 DOI-deduplicated papers are indexed, but only the CC BY subset is copied
into the repository.

PMC graphic URLs are deduplicated. The APS adapter resolves CC BY landing
pages and reconstructs figure regions from the PDF at 300 dpi; missing captions
or third-party-rights phrases remain metadata-only. The review index
deduplicates images by hash, filters non-HEP keyword collisions, ranks likely
schematics, and emits review-only object crops. A crop enters the active
element library only after object review and a native SVG redraw.

`priority_element_rebuild.py` is the first object-level pass over the `high`
queue. It combines recorded boxes with finer connected-component proposals,
removes the connected light background, and emits a smooth-path native SVG only
for a compact single object with no text/line-art evidence. Mixed panels,
labels, axes and connected diagrams remain explicitly marked for manual
separation. Current pass: 3,599 proposals, 4 native candidates, 3,595 manual
rows, zero automatic promotions.

### Same-position alternatives

An element can keep one placement while offering multiple appearances:

```yaml
- id: participant_nucleon
  asset_family: nucleon
  asset_variant: article_t335_red_nucleon_top
  variant_options:
    - article_t335_red_nucleon_top
    - article_t335_red_nucleon_bottom
    - article_t335_purple_nucleon
    - nucleon_proton
  x_mm: 137
  y_mm: 73
```

```bash
python scripts/element_variants.py list --spec figure.spec.yaml --element participant_nucleon
python scripts/element_variants.py preview --spec figure.spec.yaml \
  --element participant_nucleon --safe-only --outdir variants/nucleon
```

Every preview uses the same slot position and dimensions, so the author chooses
only the object form. `record` stores the author's code/reply; `apply` writes
the chosen `asset_variant` back to the spec. The changed spec must be confirmed
again before compilation.

AI supplementation:

```bash
python scripts/element_library.py ingest-ai \
  --id custom_detector --source cleaned.png \
  --name-zh 自定义探测器 --category detector \
  --license CC-BY-4.0 --origin ai_raster \
  --tool image-generator --model MODEL --prompt-file prompt.txt \
  --reviewer author --review-note "silhouette and physics checked"
```

PNG files are cropped to alpha bounds and vectorized with `vtracer`. AI origin
and model provenance are mandatory. Missing AI provenance is not accepted.

## Confirmation and compilation

```bash
# Human-readable element list; send this to the author.
python scripts/spec_confirm.py figure.spec.yaml --show

# Record the author's own reply. agent/auto/codex are rejected.
python scripts/spec_confirm.py figure.spec.yaml --record \
  --by client --reply "元素和关系可以，开始编译"

python scripts/spec_compile.py figure.spec.yaml \
  --outdir out --stem figure --safe-mode
```

`spec_compile.py` refuses to run without a matching receipt unless
`--experiment` is explicit. Experimental manifests never claim client approval.

The first compile is the preview package. After viewing it:

```bash
python scripts/visual_review.py \
  --spec figure.spec.yaml --svg out/figure.svg \
  --png out/figure.png --pdf out/figure.pdf \
  --record --by client --reply "图和物理关系通过"

python scripts/spec_compile.py figure.spec.yaml \
  --outdir out --stem figure --safe-mode --final
```

`--final` hashes the SVG/PDF/PNG back to the visual-review receipt and refuses
if the deterministic spec/SVG/PNG changed. The PDF hash is recorded for audit,
but may vary because writers can embed creation timestamps.

## Nature profile

`assets/spec-profiles/nature-2026.json` defines:

- 89 mm single-column or 183 mm double-column canvas;
- 5–12 pt text, recommended 5–7 pt;
- 0.25–3 pt connectors;
- controlled semantic colour families;
- 300 dpi minimum for photographs and 600 dpi for combination/line art.

The compiler writes native `<text>`, code-generated arrows, no embedded raster,
and a provenance manifest. It exports SVG, PDF, and a 600 dpi PNG.

## Submission-safe mode

`--safe-mode` rejects:

- `ai_raster`
- `ai_generated_vector`
- groups marked `data-ai-generated=true`
- embedded `<image>`

`--source-derived-only` is stricter: every physical element must have
`generation.origin=article_vector_native` or `article_vector_trace`.

AI-origin assets remain available for exploration outside safe mode. A vector
redrawn in software from a reviewed AI concept may be labelled
`ai_assisted_redraw` only when it contains no AI pixels.

Safe mode is an asset-provenance filter, not a journal-policy waiver. The
corresponding author remains responsible for the target journal's current AI
and image-integrity disclosure rules.
