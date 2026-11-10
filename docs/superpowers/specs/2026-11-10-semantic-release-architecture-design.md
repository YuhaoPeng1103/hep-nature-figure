# Semantic Release Architecture

Date: 2026-11-10
Status: approved 2026-11-11

## Goal

Turn the existing raster-to-vector pipeline into an auditable semantic release
pipeline with three explicit artifact contracts:

1. `edit-master`: semantic objects and a small number of editable primitives.
2. `visual-master`: high-fidelity gradient geometry for submission output.
3. `visual-pick`: invisible hit paths that select a complete physical object.

At the same time, remove the single-provider bottleneck and add a reproducible
cross-provider benchmark. IR, the approved bitmap, and the semantic trace remain
the source of truth; SVG files are derived build artifacts.

## Current Baseline

The following uncommitted work is retained as the implementation baseline:

- `scripts/semantic_release.py`
- `scripts/semantic_conflicts.py`
- contract metadata added to `scripts/trace_rebuild.py`
- contract metadata added to `scripts/shade_smooth.py`

The existing A/B/C/D generation ladder, reference-role gates, customer choice
gate, 3D gate, and axis gate remain authoritative.

## Non-Goals

- Do not claim fully automatic physics-aware segmentation.
- Do not replace human confirmation of ambiguous same-colour objects.
- Do not silently convert inferred hidden geometry into visible trace geometry.
- Do not expose API keys in logs, manifests, or benchmark output.
- Do not make paid provider calls during tests or dry runs.

## Architecture

### 1. Semantic Release Core

`scripts/semantic_release.py` becomes the only supported entry point for the
three-artifact release.

Required behavior:

- Build `*_edit.svg`, `*_visual_mesh.svg`, and `*_visual_pick.svg`.
- Preserve one stable `data-element` namespace across edit and visual masters.
- Tag roots with `data-artifact` and `data-contract`.
- Write a `release-v1` JSON manifest containing source hashes, artifact hashes,
  preset, element IDs, completion mode, rules, and technical limits.
- Support `edit-only`, `visual-only`, and `no-pick` without invoking tools for
  artifacts that were not requested.
- Refuse to build a pick artifact from a missing visual master.
- Default pick geometry to visible-only; declared amodal completion requires an
  explicit JSON input and is recorded in the manifest.
- Optionally run the semantic conflict audit and include its report hash and
  high-risk count in the manifest.

### 2. Release Gate

Add `scripts/release_gate.py` to validate a completed release.

Hard checks:

- Manifest schema, hashes, and referenced files are valid.
- Edit and visual masters contain identical semantic element ID sets.
- Vector artifacts contain no `<image>` elements.
- Required label text remains `<text>` where the source trace used text.
- The pick artifact contains one semantic hit group per declared element.
- The pick layer renders invisibly; the visual and visual-pick renders are
  byte-identical when the renderer is available.
- A `--strict-conflicts` release fails when unresolved high-risk boundaries
  remain.

Read-only diagnostics:

- path counts and file sizes;
- element-specific reproduction error when an elmap is supplied;
- smoothness metrics when a rendered visual master is supplied;
- mapping from edit objects to visual and pick groups.

### 3. Conflict Audit

`scripts/semantic_conflicts.py` remains an audit tool, not a replacement
segmenter.

It reports:

- same-colour adjacent classes;
- pixels whose colour evidence favours the neighbouring class;
- boundaries without sufficient edge support;
- declared overlaps and the expected front object from IR z-order.

Colour competition, weak edges, and z-order violations are separate readings.
IR z-order constrains ownership; it is never treated as visible pixel evidence.

### 3.1 Same-Colour Competition Resolver

Add conflict resolution as a separate deterministic stage after the audit. It
must not silently replace the original semantic map.

Inputs:

- source bitmap;
- initial `elmap.npy` and element names;
- IR element roles, primitives, materials, and z-order;
- the audit's pairwise conflict report.

For each adjacent conflicting pair, keep object cores fixed and optimize
ownership only inside a bounded boundary band. The pixel cost combines:

- distance to each class's robust Lab-colour distribution;
- local gradient support and edge distance;
- local texture/contrast similarity;
- thinness and distance-transform shape prior;
- distance from the original boundary;
- optional declared overlap and z-order prior.

The resolver uses deterministic local updates followed by topology checks. A
candidate relabel is accepted only when it improves the weighted cost, does not
disconnect either object's protected core, and does not exceed per-pair area
change limits. Ambiguous pixels remain assigned to the initial map and are
reported with confidence.

Outputs are separate derived files:

- `elmap_competed.npy` and `el_names_competed.txt`;
- a confidence map;
- a change report containing changed pixels, accepted/rejected proposals, and
  reason codes;
- an overlay comparing initial, accepted, and unresolved boundaries.

The release manifest records the original elmap and competition-report hashes.
The original trace remains the visible-geometry truth source; competition may
change semantic ownership, not invent hidden geometry.

### 4. Generation Providers

Add `scripts/providers/` with a provider protocol and implementations for:

- DashScope/Qwen image generation and editing;
- OpenAI Image API;
- Gemini image generation and editing.

The `gen_figure.py` CLI and guard-token behavior remain stable. Add:

- `--provider auto|dashscope|openai|gemini`;
- capability discovery for references, seeds, custom sizes, multi-turn editing,
  and direct SVG output;
- normalized results containing bytes/URL, MIME type, provider request ID,
  effective model, and normalized usage/cost metadata;
- provider-specific errors translated to a shared error type.

Provider adapters must never put keys in command lines or manifests.

### 5. Provider Benchmark

Add `scripts/benchmark_providers.py` and a small declarative benchmark suite.

The benchmark:

- uses fixed IR, style references, and approved content references;
- executes only with explicit `--execute`;
- runs the existing sketch, render, 3D, axis, layout, and text checks;
- records provider, model, seed, latency, errors, and normalized cost metadata;
- writes machine-readable JSON plus a compact Markdown table;
- anonymizes outputs before optional human ranking.

The benchmark does not declare a global winner from visual preference alone.
Physics, text/label accuracy, 3D reading, and vectorizability are reported
separately.

### 6. Semantic Bootstrap

Add `scripts/semantic_bootstrap.py` to reduce manual `panels.py` work.

It consumes IR, the approved bitmap, and an optional existing `panels.py`.
It runs the existing IR-guided contour segmenter, then emits:

- `elmap.npy` and `el_names.txt`;
- an initial minimal `panels_*.py`;
- a conflict report;
- a human-review checklist for labels unresolved by visible evidence.

The generated table is a starting point. Ambiguous boundaries remain marked for
human confirmation rather than being silently accepted.

### 7. Direct SVG Branch

Providers that advertise direct SVG output may produce a vector draft from the
brief.

This branch is limited to:

- flat diagrams;
- line art;
- icons and graphical abstractions.

It is not a default replacement for 3D illustrated schematics. Direct SVG must
pass the same delivery checks for embedded images, text, element metadata, and
artifact contract. A provider that cannot edit a raster and return SVG cannot
provide both the render-edit and direct-SVG steps in one call.

## Presets

Release presets expose the fidelity/editability trade-off instead of pretending
one SVG wins both:

- `draft`: minimum geometry for rapid shape/colour revision.
- `balanced`: default; moderate path count and sufficient smoothness.
- `fidelity`: maximum visual fidelity for submission.

Preset thresholds must be calibrated per figure. Acceptance uses per-element
MAE, boundary-band MAE, smoothness (`p99` and `>8` proportion), path count, PDF
size, and manual editability. Whole-image MAE alone is not sufficient.

## Data Flow

```text
IR + approved bitmap + semantic trace
                  |
                  +--> edit master ------> semantic revision
                  |
                  +--> visual master ----> submission PDF
                  |
                  +--> visible/declared masks
                              |
                              +--> pick paths

IR + bitmap + optional panels
                  |
                  +--> semantic bootstrap -> trace / conflict audit

brief + style refs + optional content ref
                  |
                  +--> provider adapter -> raster or direct SVG
```

## Delivery Phases

### Phase 1: Semantic Release Foundation

- harden the existing release and conflict tools;
- add the same-colour competition resolver and confidence output;
- add release gate, manifest integration, workspace shims, and tests;
- document artifact roles and source-of-truth rules.

### Phase 2: Provider Abstraction and Benchmark

- add provider protocol and adapters;
- preserve existing CLI and guards;
- add explicit-execute benchmark suite and normalized reporting.

### Phase 3: Semantic Bootstrap and Direct SVG

- automate initial semantic tables from IR;
- integrate conflict-guided human review;
- add provider-capability-gated direct SVG generation and validation.

## Error Handling

- Invalid inputs exit non-zero before paid API calls.
- Missing optional dependencies produce actionable diagnostics.
- Unsupported provider capabilities fail explicitly; no silent fallback to a
  different model or output format.
- Artifact hash mismatch, element mismatch, and undeclared amodal completion are
  hard failures.
- Renderer-dependent checks report `unavailable`, not `pass`, when the required
  renderer is absent.

## Testing

Keep the session within ten grouped tests:

1. release happy path with edit, visual, pick, and manifest;
2. edit-only, visual-only, and no-pick control flow;
3. mismatched element IDs and stale hashes fail;
4. visible-only versus declared amodal completion provenance;
5. conflict audit and same-colour competition on synthetic cases, including
   protected cores, topology rejection, and unresolved ambiguity;
6. provider dry-run, capability rejection, and secret redaction;
7. benchmark dry-run schema and fixed-input enforcement;
8. semantic bootstrap produces elmap/names/table and flags ambiguity;
9. direct SVG rejects embedded raster and preserves required text;
10. existing guarded `gen_figure.py` regressions remain green.

Paid provider integration is not part of automated tests.

## Acceptance Criteria

- One command builds and validates a three-artifact release from an existing
  semantic trace.
- The resulting manifest proves all artifacts and inputs by SHA-256.
- `release_gate.py` catches element drift, embedded raster, missing pick groups,
  and hash mismatches.
- Same-colour competition reduces tested high-risk boundary area without
  changing protected object cores or inventing hidden geometry.
- Existing generation tests remain green with DashScope as the default.
- OpenAI and Gemini adapters pass mocked dry-run tests and are selectable without
  changing guard behavior.
- The benchmark emits a reproducible comparison matrix without making paid calls
  by default.
- Semantic bootstrap removes the mandatory blank-page `panels.py` step while
  retaining explicit ambiguity review.

## Risks

- Renderer differences can change smoothness and pick-layer equality checks.
- Provider APIs and model names change frequently; capability names must be
  configuration-backed.
- Direct SVG output may outline text or contain proprietary structure; delivery
  checks remain mandatory.
- The edit and visual masters can diverge if both are hand-edited. The release
  gate detects semantic ID drift, and the documented workflow rebuilds visual
  artifacts from the edit master.
