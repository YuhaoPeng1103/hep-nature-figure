# Element-spec compiler demo

This is a technical pipeline example, not a client-approved final figure.

```bash
python scripts/spec_confirm.py assets/spec-examples/qgp-jet-article-elements.spec.yaml --show
python scripts/spec_compile.py assets/spec-examples/qgp-jet-article-elements.spec.yaml \
  --experiment --safe-mode --source-derived-only \
  --outdir assets/demos/element-spec/output --stem qgp-jet
```

`output/qgp-jet.*` is the canonical article-derived example: all six
physical element groups come from CC BY article figures. The earlier
`qgp-jet-element.spec.yaml` remains only a primitive-composition regression
fixture and is not the canonical example.
Its `composition.layout` declares the initial-state, hard-scattering and
final-state regions plus an axonometric reaction-plane grid, beamline and axis
triad. The compiler checks those groups and writes `layout_checks` into the
manifest.

Submission flow uses a second visual-review receipt:

```bash
python scripts/visual_review.py \
  --spec figure.spec.yaml --svg out/figure.svg \
  --png out/figure.png --pdf out/figure.pdf \
  --record --by client --reply "图和物理关系通过"
python scripts/spec_compile.py figure.spec.yaml \
  --outdir out --stem figure --safe-mode --final
```

Same-position alternatives:

```bash
python scripts/element_variants.py list \
  --spec assets/spec-examples/qgp-jet-article-elements.spec.yaml \
  --element participant_nucleon
python scripts/element_variants.py preview \
  --spec assets/spec-examples/qgp-jet-article-elements.spec.yaml \
  --element participant_nucleon --safe-only \
  --outdir assets/element-library/overviews/nucleon_slot_picker_v51
```

The preview renders every alternative at the same `x_mm/y_mm/width/height`,
so the author compares object appearance rather than layout.

Flow demonstrated:

1. structured canvas, elements, text, connections, physical relationships, and
   measurable hard-physics constraints;
2. machine checks for opposite incoming rays and the back-to-back jet angle;
3. element lookup from `assets/element-library/`;
4. deterministic SVG assembly with native text and code-built connectors;
5. Nature profile checks for physical dimensions, 5–7 pt labels, line widths,
   and semantic colour families;
6. 600 dpi PNG, vector PDF, render/3D/delivery checks;
7. a second visual-review receipt checked by `--final`;
8. submission-safe mode rejecting AI-origin elements.

`qgp-jet_manifest.json` records the spec hash, confirmation status, asset hashes,
licences, AI flags, and all gate results. The manifest says
`confirmation=experimental` because no client confirmation was fabricated.

## Source-derived composition

`source-derived-output/source-elements.*` is compiled with
`--source-derived-only`. Every physical element in that figure comes from a
CC BY article figure via `article_vector_native`; no system primitive, pixel
trace cluster, or AI pixel is used.

```bash
python scripts/spec_compile.py assets/spec-examples/source-derived-elements.spec.yaml \
  --experiment --safe-mode --source-derived-only \
  --outdir assets/demos/element-spec/source-derived-output --stem source-elements
```
