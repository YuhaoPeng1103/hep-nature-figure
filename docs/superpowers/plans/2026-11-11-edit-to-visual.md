# Edit-to-Visual Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the visual master and pick layer from a modified `edit-master.svg` without a unified editable/fidelity representation.

**Architecture:** Render the edit master and per-element masks, synthesize a derived semantic trace, run the existing smooth visual builder, rebuild pick paths, and write a release manifest linking all derivatives.

**Tech Stack:** Python 3.10+, ElementTree, Pillow, CairoSVG, NumPy/SciPy/OpenCV, existing semantic release helpers.

**Spec:** `docs/superpowers/specs/2026-11-10-semantic-release-architecture-design.md`

## Global Constraints

- Full occlusion and amodal reconstruction are out of scope.
- `edit-master` is the semantic source; visual and pick are derived artifacts.
- Supported edits: colour, translation, scaling, moderate shape adjustment.
- Unsupported topology changes fail explicitly; do not hallucinate texture.
- Text remains real `<text>`.
- No paid provider calls in tests.

## Review Focus

- Editing one object must not change unrelated object IDs or labels.
- Element masks must preserve holes and visible intersections.
- A missing or malformed edit master must fail before rebuilding visual artifacts.
- Visual and pick outputs must share the edit master's semantic IDs.
- CairoSVG limitations must be reported, not hidden.

---

### Task 1: Edited SVG to Derived Trace

**Files:**
- Create: `scripts/edit_to_visual.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Produces: `render_edit_master(edit_svg: Path, outdir: Path, stem: str) -> tuple[Path, Path, list[str]]`.
- Produces: PNG render, derived semantic trace SVG, semantic IDs.

- [ ] **Step 1: Add failing extraction test**

Create a release fixture, alter the edit master's nucleus fill/translation, and call the new compiler in `--trace-only` mode. Assert:

- output PNG and derived trace exist;
- element IDs equal the edit master;
- edited nucleus pixels appear at the new location;
- all `<text>` content is preserved.

- [ ] **Step 2: Run and verify failure**

Run: `$env:PYTHONUTF8='1'; python evals/test_tools.py edit_to_visual_trace`

- [ ] **Step 3: Implement extraction**

Parse SVG with ElementTree; copy `<defs>`, render the full root and each `data-element` group with CairoSVG on transparent canvases, convert alpha masks to paths through `shade_smooth.smoothed_clip_svg`, and copy text groups from the edit master.

- [ ] **Step 4: Run extraction test**

Run: `$env:PYTHONUTF8='1'; python evals/test_tools.py edit_to_visual_trace`

- [ ] **Step 5: Commit**

```powershell
git add scripts/edit_to_visual.py evals/test_tools.py
git commit -m "feat: derive semantic trace from edit master"
```

---

### Task 2: Rebuild Visual and Pick

**Files:**
- Modify: `scripts/edit_to_visual.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Consumes Task 1's derived raster/trace.
- Produces: `<stem>_visual_mesh.svg`, `<stem>_visual_pick.svg`, `<stem>_edit_release.json`.

- [ ] **Step 1: Add failing rebuild test**

Add `edit_to_visual_rebuild`: compile an edited release and assert visual/pick exist, visual contains `pixel-fidelity`, pick contains `object-pick`, IDs match the edit master, and the manifest hashes all derivatives.

- [ ] **Step 2: Run and verify failure**

Run: `$env:PYTHONUTF8='1'; python evals/test_tools.py edit_to_visual_rebuild`

- [ ] **Step 3: Implement rebuild**

Invoke `shade_smooth.py` with the derived raster/trace, tag the visual root, build visible-only pick paths from the derived trace, tag the pick root, and write `edit-to-visual-v1` manifest records.

- [ ] **Step 4: Run rebuild test**

Run: `$env:PYTHONUTF8='1'; python evals/test_tools.py edit_to_visual_rebuild`

- [ ] **Step 5: Commit**

```powershell
git add scripts/edit_to_visual.py evals/test_tools.py
git commit -m "feat: rebuild visual artifacts from edit master"
```

---

### Task 3: Fail Closed on Unsupported Inputs

**Files:**
- Modify: `scripts/edit_to_visual.py`
- Test: `evals/test_tools.py`

**Interfaces:**
- Produces actionable failures for malformed SVG, missing semantic groups, duplicate IDs, empty masks, and unsupported extreme area collapse.

- [ ] **Step 1: Add failing guard test**

Add `edit_to_visual_guards` covering missing `data-element`, duplicate IDs, a group rendered to an empty mask, and invalid artifact contract. Assert failure before a visual manifest is written.

- [ ] **Step 2: Run and verify failure**

Run: `$env:PYTHONUTF8=1; python evals/test_tools.py edit_to_visual_guards`

- [ ] **Step 3: Implement validation**

Validate root contract, unique semantic IDs, positive dimensions, XML parseability, and non-empty physical masks. Treat `background` as the only allowed full-canvas element.

- [ ] **Step 4: Run guard test**

Run: `$env:PYTHONUTF8=1; python evals/test_tools.py edit_to_visual_guards`

- [ ] **Step 5: Commit**

```powershell
git add scripts/edit_to_visual.py evals/test_tools.py
git commit -m "fix: fail closed in edit-to-visual compiler"
```

---

### Task 4: Integration and Final Verification

**Files:**
- Modify: `scripts/init_workspace.py`
- Modify: `references/scripts.md`
- Modify: `SKILL.md`
- Modify: `CHANGELOG.md`
- Test: `evals/test_tools.py`

- [ ] **Step 1: Extend workspace integration test**

Require an `edit_to_visual.py` shim and documentation command in `SKILL.md` and `references/scripts.md`.

- [ ] **Step 2: Implement integration and docs**

Add the shim and document:

```text
modify edit-master -> edit_to_visual.py -> visual-master + visual-pick + manifest
```

Update CHANGELOG v4.27 with the narrowed scope and explicit non-support for occlusion/amodal reconstruction.

- [ ] **Step 3: Run focused tests**

Run: `$env:PYTHONUTF8=1; python evals/test_tools.py edit_to_visual`

- [ ] **Step 4: Run full suite**

Run: `$env:PYTHONUTF8=1; python evals/test_tools.py`

- [ ] **Step 5: Commit**

```powershell
git add scripts/init_workspace.py references/scripts.md SKILL.md CHANGELOG.md evals/test_tools.py
git commit -m "docs: integrate edit-to-visual workflow"
```
