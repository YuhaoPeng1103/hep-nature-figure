# Semantic Release Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete and validate the three-artifact semantic release workflow, including same-colour competition, release gating, manifests, and workspace integration.

**Architecture:** Harden the existing `semantic_release.py` and `semantic_conflicts.py` baseline, add a deterministic `semantic_competition.py` resolver, and add `release_gate.py`. Generated SVG artifacts remain derivatives of IR, bitmap, and semantic trace.

**Tech Stack:** Python 3.10+, NumPy, SciPy, Pillow, existing SVG/render helpers, the project’s custom `evals/test_tools.py` runner.

**Spec:** `docs/superpowers/specs/2026-11-10-semantic-release-architecture-design.md`

## Global Constraints

- Production figures remain `2336*1280` where applicable; tests may use small synthetic fixtures.
- Model/chat previews stay at <=1800 px; release/vector processing uses full-size files.
- IR + approved bitmap + semantic trace are the truth source; SVG files are derived artifacts.
- Amodal completion may enter pick paths only; it never becomes visible trace geometry.
- All schematics remain `render3d`; synthetic unit fixtures do not alter production defaults.
- No paid API calls or real provider credentials in tests.
- Missing renderer-dependent checks report `unavailable`, never `pass`.

## Review Focus

- Same-colour competition must not change protected object cores or disconnect them.
- Low-confidence disagreement must remain visibly unresolved instead of being auto-labelled.
- Edit-only and visual-only releases must not invoke or reference missing artifacts.
- Manifest hashes and semantic element sets must fail closed on stale or mismatched files.
- Pick-layer validation must not pretend success when the required renderer is unavailable.

---

### Task 1: Harden Release Orchestration

**Files:**
- Modify: `scripts/semantic_release.py`
- Modify: `scripts/pick_layer.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes: `tag_root(svg_text: str, role: str, contract: str) -> str` and the existing release CLI.
- Produces: `artifact_record(path: pathlib.Path, role: str, contract: str, **extra) -> dict[str, object]`.
- Produces: pick SVG root metadata `data-artifact="visual-pick"` and `data-contract="object-pick"`.

- [ ] **Step 1: Add grouped failing tests**

Add a `release_fixture(tmp)` helper under the semantic-release test section. It writes a 96×64 PNG and a minimal semantic trace containing `background`, `nucleus`, and `plate` groups. Add three cases:

```python
@case("semantic_release_happy_path", "edit/visual/pick + hashed manifest")
def test_semantic_release_happy_path(): ...

@case("semantic_release_partial_modes", "edit-only/visual-only/no-pick skip absent artifacts")
def test_semantic_release_partial_modes(): ...

@case("semantic_release_fails_closed", "mismatched IDs/stale hashes fail")
def test_semantic_release_fails_closed(): ...
```

Assertions:

- happy path produces three SVGs, three distinct `data-contract` values, and a `release-v1` manifest;
- every manifest artifact SHA-256 matches the on-disk file;
- partial modes return zero and leave absent artifacts as `null`;
- an edit-only run with pick enabled does not call `pick_layer.py`;
- altered later content or mismatched element sets make validation fail.

- [ ] **Step 2: Run the new cases and verify they fail**

Run: `python evals/test_tools.py semantic_release`
Expected: failures showing missing pick metadata, incorrect partial-mode handling, or absent fail-closed checks.

- [ ] **Step 3: Implement the release fixes**

In `scripts/semantic_release.py`:

- extract artifact metadata construction into `artifact_record(...)`;
- reject combinations where pick output is requested without a visual master;
- run pick only when the visual master exists;
- tag the pick root with `visual-pick/object-pick`;
- validate manifest hashes and semantic IDs before writing;
- retain the existing `truth_source` field so `release-v1` remains backward-compatible.

In `scripts/pick_layer.py`, accept `--artifact-role` and `--contract` with defaults `visual-pick` and `object-pick`, and tag the SVG root without altering geometry.

- [ ] **Step 4: Run the release cases**

Run: `python evals/test_tools.py semantic_release`
Expected: all three cases pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/semantic_release.py scripts/pick_layer.py evals/test_tools.py
git commit -m "feat: harden semantic release artifacts"
```

---

### Task 2: Add Release Gate

**Files:**
- Create: `scripts/release_gate.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes: a `release-v1` manifest and its referenced SVGs.
- Produces: `check_release(manifest: pathlib.Path, render_visual: pathlib.Path | None = None, render_pick: pathlib.Path | None = None) -> tuple[list[dict[str, object]], bool]`.
- CLI: `python scripts/release_gate.py --manifest <release.json> [--render-visual <png> --render-pick <png>] [--json <report.json>]`.

- [ ] **Step 1: Add failing gate tests**

Add:

```python
@case("release_gate_contracts", "hashes, IDs, no raster, true text, pick groups")
def test_release_gate_contracts(): ...

@case("release_gate_renderer_unavailable", "missing renderer is unavailable, not pass")
def test_release_gate_renderer_unavailable(): ...
```

Use the Task 1 fixture. Mutate one SVG to add `<image>`, remove one `data-element`, outline one `<text>`, and remove one pick group in separate assertions. Assert each mutation fails. Passing only one or neither rendered PNG must emit `render_check=unavailable`.

- [ ] **Step 2: Run the gate tests and verify they fail**

Run: `python evals/test_tools.py release_gate`
Expected: failures because `release_gate.py` does not exist.

- [ ] **Step 3: Implement `release_gate.py`**

Use XML parsing, not string-only matching. It must:

- verify schema `hep-nature-figure/release-v1`;
- verify every referenced path exists and every SHA-256 matches;
- compare sorted `data-element` sets in edit and visual masters;
- reject `<image>` in all vector artifacts;
- compare text content from the manifest source trace with edit and visual masters;
- require one `data-object="1"` path or group per element in the pick artifact;
- compare provided PNG files byte-for-byte and report `unavailable` if either is absent.

- [ ] **Step 4: Run the gate tests**

Run: `python evals/test_tools.py release_gate`
Expected: both cases pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/release_gate.py evals/test_tools.py
git commit -m "feat: add semantic release gate"
```

---

### Task 3: Implement Same-Colour Competition

**Files:**
- Create: `scripts/semantic_competition.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes: source RGB array, integer label map, element names, optional IR elements, and audit boundary pairs.
- Produces: `resolve_conflicts(src: np.ndarray, lab: np.ndarray, names: list[str], ir_elements: list[dict], pairs: list[dict], band: int = 4, max_area_change: float = 0.15) -> tuple[np.ndarray, np.ndarray, list[dict]]`.
- Produces: competed label map, float confidence map in `[0,1]`, and per-proposal records.
- CLI outputs `*_competed.npy`, `*_names.txt`, `*_confidence.npy`, `*_competition.json`, and `*_competition.png`.

- [ ] **Step 1: Add failing resolver tests**

Add:

```python
@case("semantic_competition_same_colour", "edge/shape resolves a same-colour boundary")
def test_semantic_competition_same_colour(): ...

@case("semantic_competition_guards", "protected cores, topology, ambiguity")
def test_semantic_competition_guards(): ...
```

Create a deterministic 80×60 synthetic image with two adjacent same-colour regions and a visible vertical edge at `x=42`; initialize the boundary at `x=50`. Assert the resolved boundary moves toward 42, both core masks are unchanged, and the confidence report records accepted pixels. Add a proposal that would create a hole/disconnection and assert it is rejected. Leave a zero-evidence strip and assert it retains the original label with low confidence.

- [ ] **Step 2: Run resolver tests and verify they fail**

Run: `python evals/test_tools.py semantic_competition`
Expected: failures because the module and CLI do not exist.

- [ ] **Step 3: Implement the deterministic resolver**

Use robust Lab medians/Gaussian approximations for colour cost, `distance_transform_edt` for core/thinness, Sobel magnitude plus distance to strong edges for boundary support, and local standard deviation for texture. Restrict updates to the audit boundary band. Iterate row-major until no accepted change or three passes.

Acceptance rules:

- never change protected cores;
- preserve at least 95% of each object’s initial area;
- reject relabels that disconnect the protected core;
- accept only weighted-cost improvements above a fixed confidence margin;
- write all accepted and rejected proposals to JSON with reason codes.

- [ ] **Step 4: Run resolver tests**

Run: `python evals/test_tools.py semantic_competition`
Expected: both cases pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/semantic_competition.py evals/test_tools.py
git commit -m "feat: resolve same-colour semantic boundaries"
```

---

### Task 4: Integrate Audit and Competition Provenance

**Files:**
- Modify: `scripts/semantic_release.py`
- Modify: `scripts/semantic_conflicts.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes: optional `--audit-json` and `--competition-json`.
- Produces: manifest fields `semantic_audit`, `semantic_competition`, and `unresolved_high_risk`.
- Conflict JSON keeps `high_risk_pairs` and adds stable `schema="hep-nature-figure/conflicts-v1"`.

- [ ] **Step 1: Add failing integration tests**

Extend `test_semantic_release_happy_path` and add:

```python
@case("semantic_release_conflict_provenance", "audit/competition hashes and strict failure")
def test_semantic_release_conflict_provenance(): ...
```

Assert both JSON inputs are hashed into the manifest, their element IDs match the release, high-risk records survive verbatim, and `--strict-conflicts` exits non-zero before writing a successful manifest.

- [ ] **Step 2: Run the integration case and verify it fails**

Run: `python evals/test_tools.py semantic_release_conflict`
Expected: failure because provenance fields and strict mode are absent.

- [ ] **Step 3: Implement provenance integration**

Add the CLI flags and manifest records. Validate that audit/competition names are a subset of release element IDs. `--strict-conflicts` fails when either report contains high-risk unresolved records. Do not rerun segmentation inside release.

- [ ] **Step 4: Run release tests**

Run: `python evals/test_tools.py semantic_release`
Expected: all release and conflict-provenance cases pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/semantic_release.py scripts/semantic_conflicts.py evals/test_tools.py
git commit -m "feat: record semantic conflict provenance"
```

---

### Task 5: Workspace and Skill Integration

**Files:**
- Modify: `scripts/init_workspace.py`
- Modify: `references/scripts.md`
- Modify: `SKILL.md`
- Modify: `CHANGELOG.md`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes: completed release tools.
- Produces: workspace shims `semantic_release.py`, `semantic_conflicts.py`, `semantic_competition.py`, and `release_gate.py`.
- Produces: one documented release command sequence.

- [ ] **Step 1: Add failing documentation and shim test**

Add:

```python
@case("semantic_release_workspace_integration", "shims and commands are discoverable")
def test_semantic_release_workspace_integration(): ...
```

Run `init_workspace.py` into a temporary directory and assert all four shims exist and execute `--help`. Assert `SKILL.md` names `semantic_release.py` and `release_gate.py`.

- [ ] **Step 2: Run the integration test and verify it fails**

Run: `python evals/test_tools.py semantic_release_workspace`
Expected: failure because shims/docs are absent.

- [ ] **Step 3: Update integration and documentation**

Add the four shims to `init_workspace.py`. Document this sequence:

```text
semantic_conflicts.py -> semantic_competition.py -> raster trace with competed elmap
-> semantic_release.py -> release_gate.py
```

State that competition output is derived and reviewable, visual master is for submission PDF, edit master is for revision, and pick is an interaction layer. Add a concise v4.27 changelog entry.

- [ ] **Step 4: Run the integration test**

Run: `python evals/test_tools.py semantic_release_workspace`
Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/init_workspace.py references/scripts.md SKILL.md CHANGELOG.md evals/test_tools.py
git commit -m "docs: integrate semantic release workflow"
```

---

### Task 6: Full Regression and Baseline Sample

**Files:**
- Modify only if a regression exposes a defect in the files above.

**Interfaces:**
- Consumes: all Phase 1 tools.
- Produces: verification evidence for the phase.

- [ ] **Step 1: Run focused semantic tests**

Run: `python evals/test_tools.py semantic`
Expected: all semantic release, competition, conflict, and workspace cases pass.

- [ ] **Step 2: Run the existing regression suite**

Run: `python evals/test_tools.py`
Expected: zero failures.

- [ ] **Step 3: Run an existing-fixture smoke test**

Use the UPC or jet-quenching demo source plus its checked-in panel definitions to produce a semantic trace if a reusable trace fixture does not exist. Run the full release and gate. Record path counts, artifact sizes, manifest validation, and any renderer-unavailable result.

- [ ] **Step 4: Fix only observed regressions and rerun**

Run the smallest affected focused case, then the full suite once.

- [ ] **Step 5: Commit final fixes**

```powershell
git add scripts evals references SKILL.md CHANGELOG.md
git commit -m "test: verify semantic release foundation"
```
