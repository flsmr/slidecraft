# Two-Stage Slide Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic single-stage slide composer into a **planner** (one LLM decides the slide: layout, message, and per content-area type + instructions + routed nuggets) and three **specialist designers** (text/table, diagram-in-Vue, image-generation) that each build one content area, with deterministic glue scripts doing all Slidev assembly and owning every OWUI call.

**Architecture:** `compose_deck.py` is a batch driver. Per slide it runs `km compose-brief` → the planner via the invoke shim → `km write-skeleton` (validates the plan JSON, renders a visible wireframe, places `source-image` areas, persists a plan sidecar in the slide state). Then per pending content section it runs `design_section.py` concurrently: `km design-brief` → a designer via OWUI → (`image` only: download) → `km place-design` (deterministic extraction + placement + status promotion). No LLM ever runs inside a `km`/`place-design` mutation (ADR-0001). Every prompt+response is logged under the deck's `logs/prompts/`.

**Tech Stack:** Python 3.10+ (`slidecraft/scripts/km.py`, `invoke_shim.py`, new `design_section.py` + `compose_deck.py`, pytest); Markdown agent-prompt templates (`slidecraft/agents/*.md`); Vue SFCs (`slidecraft/components/*.vue`, custom `<catalog>` blocks); OWUI transport (existing `invoke_shim` executors).

## Global Constraints

- **ADR-0001 (deterministic assembly) holds and is strengthened.** Scripts move files and assemble physical Slidev markdown; they NEVER call an LLM and NEVER write slide prose. `write-skeleton` / `place-design` do all physical assembly; the only LLM seam is the invoke shim / `design_section.py`.
- **Rejection convention (D44):** a persist command exits **1** for a *retryable* validation rejection (model can fix it — the shim re-invokes, cap 2), and **2** (via `gate_exit`) for a *non-retryable* wiring/infra gate. km's `budget_full` is exit 3. Never conflate these.
- **Placeholder discipline (D10):** every prompt input is a named `%PLACEHOLDER%`; `km` computes values only, templates own all prose + ordering; optional inputs resolve to `""`. New placeholder names are **hyphen-style** (`%DECK-TYPE%`, never `%DECK_TYPE%`). The leftover-guard regex is widened to `%[A-Z][A-Z_-]*%` (Task 1).
- **Section types (D5):** exactly `text | diagram | image | source-image`. Medium is the section `type`, not a role.
- **Layout scope now (D4):** `content` (single content role `body`) and `two-cols` (content roles `left`,`right`). No image-split / prop-based image layouts, no grids beyond two columns. Validated against `offered_layouts(ctx)`.
- **Concept-type enum (unchanged):** `structural | motivate | define | compare | relationship | process | cause-effect | finding | categories | claim-support` (the existing `km.CONCEPT_TYPES`).
- **Aspect ratios (D17):** image generation only, **`1:1` or `16:9` only**. Rule: single-column `body` → `16:9`; two-column `left`/`right` → `1:1`. A placed `source-image` keeps its own ratio (no generation).
- **Designer executor defaults:** `text-designer` and `diagram-designer` → `{"executor": "owui", "model": "gdpr.gpt-5.6-sol"}`; `image-designer` → `{"executor": "owui", "model": "nano-banana-pro"}`. Overridable per deck via `deck-context.json`'s `executors` block.
- **All reads that touch model/temp/user files use `encoding="utf-8-sig"`** (BOM tolerance — PowerShell 5.1 / Notepad / OneDrive).
- **Test style:** call `km.cmd_*(deck, argparse.Namespace(...))` against a **real** scaffolded deck (the `deck` / `converted_deck` fixtures in `slidecraft/tests/conftest.py`); assert on written files or the captured JSON (`capsys`). Drive the LLM seam with `wire_fake_executor(deck, tmp_path, role, [responses])` (a scripted `cmd` executor that replays canned responses; `image_arg=True` for vision). Never call a live model.
- **Reference design doc:** [`docs/superpowers/specs/2026-07-22-two-stage-composer-design.md`](../specs/2026-07-22-two-stage-composer-design.md). Decisions **D1–D17**; **ADR-0001** governs assembly, new **ADR-0005** records this split.

---

## Task 1: Widen the leftover-placeholder guard regex

The guard in `render_template` only catches `%[A-Z][A-Z-]*%` (hyphens). A typo like `%DECK_TYPE%` (underscore) would slip through unresolved into a brief. Widen it so underscores are caught too — a one-line hardening that de-risks every template task below.

**Files:**
- Modify: `slidecraft/scripts/km.py:367` (in `render_template`)
- Test: `slidecraft/tests/test_km.py` (add one test)

**Interfaces:**
- Produces: `km.render_template(template: str, values: dict) -> str` — unchanged signature; now `sys.exit`s on a leftover `%[A-Z][A-Z_-]*%` (adds underscore to the guarded alphabet).

- [ ] **Step 1: Write the failing test**

Add to `slidecraft/tests/test_km.py`:

```python
import pytest
from slidecraft.scripts import km


def test_render_template_guard_catches_underscore_placeholder():
    # A hyphen-style placeholder resolves; an UNRESOLVED underscore-style name
    # must still trip the leftover guard (widened regex).
    with pytest.raises(SystemExit) as exc:
        km.render_template("Hello %NAME% and %DECK_TYPE%", {"NAME": "x"})
    assert "%DECK_TYPE%" in str(exc.value)


def test_render_template_resolves_underscore_named_value():
    # A value whose KEY has an underscore still substitutes (only the leftover
    # SCAN changed, not substitution).
    out = km.render_template("v=%DECK_TYPE%", {"DECK_TYPE": "lecture"})
    assert out == "v=lecture"
```

- [ ] **Step 2: Run it to confirm the first test fails**

Run: `python -m pytest slidecraft/tests/test_km.py::test_render_template_guard_catches_underscore_placeholder -v`
Expected: FAIL — no `SystemExit` raised (underscore name slips the old regex).

- [ ] **Step 3: Widen the regex**

In `slidecraft/scripts/km.py`, in `render_template` (around line 367), change:

```python
    leftover = sorted(set(re.findall(r"%[A-Z][A-Z-]*%", out)))
```

to:

```python
    leftover = sorted(set(re.findall(r"%[A-Z][A-Z_-]*%", out)))
```

- [ ] **Step 4: Run both tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km.py -k render_template -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Confirm no regression in the full km suite**

Run: `python -m pytest slidecraft/tests/test_km_compose.py slidecraft/tests/test_km_plan.py -q`
Expected: PASS (the existing `re.search(r"%[A-Z][A-Z-]*%", brief)` assertions in compose tests still hold — no template currently uses underscores).

- [ ] **Step 6: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km.py
git commit -m "fix(km): widen leftover-placeholder guard to catch underscore names"
```

---

## Task 2: `component_catalog()` — extract diagram-component metadata

The diagram designer's prompt needs a live catalog of the shipped diagram components, generated from per-component metadata so adding/removing a component auto-syncs the prompt (D14). This task builds the **extractor** against a synthetic components dir; Task 3 backfills the real `<catalog>` blocks.

**Files:**
- Modify: `slidecraft/scripts/km.py` (add `COMPONENTS_DIR`, `parse_catalog_block`, `component_catalog`)
- Test: `slidecraft/tests/test_km_catalog.py` (new)

**Interfaces:**
- Produces:
  - `km.COMPONENTS_DIR: Path` — `Path(__file__).resolve().parent.parent / "components"` (sibling of `agents/`, same pattern as `AGENTS_DIR`).
  - `km.parse_catalog_block(text: str) -> dict | None` — parse one `.vue`'s `<catalog>…</catalog>` block into `{"use": str, "looks": str, "fill": str}`; `None` when absent.
  - `km.component_catalog(components_dir: Path) -> tuple[str, list[str]]` — returns `(rendered_table, missing_names)`. `rendered_table` is a compact `name · use · looks · fill` block (one component per stanza); `missing_names` lists components with no `<catalog>` block (rendered name-only + flagged). Skips non-diagram infra files (`GenBox`, `SlideFooter`, files starting with `_`).

- [ ] **Step 1: Write the failing tests**

Create `slidecraft/tests/test_km_catalog.py`:

```python
"""Dynamic diagram-component catalog (D14): per-component <catalog> metadata,
extracted + rendered for the diagram designer's %COMPONENT-CATALOG%."""
from __future__ import annotations

from pathlib import Path

from slidecraft.scripts import km


def _write_component(d: Path, name: str, catalog: str | None) -> None:
    block = f"<catalog>\n{catalog}\n</catalog>\n" if catalog else ""
    (d / f"{name}.vue").write_text(
        block + "<script setup></script>\n<template><slot/></template>\n",
        encoding="utf-8")


def test_parse_catalog_block_reads_three_fields():
    text = ("<catalog>\n"
            "use: Linear process with one direction of flow.\n"
            "looks: Left-to-right boxes joined by single arrows.\n"
            "fill: bullet list; each item is a step, 'title | desc'.\n"
            "</catalog>\n<script setup></script>")
    parsed = km.parse_catalog_block(text)
    assert parsed["use"].startswith("Linear process")
    assert parsed["looks"].startswith("Left-to-right")
    assert parsed["fill"].startswith("bullet list")


def test_parse_catalog_block_absent_returns_none():
    assert km.parse_catalog_block("<script setup></script>") is None


def test_component_catalog_renders_present_and_flags_missing(tmp_path):
    d = tmp_path / "components"
    d.mkdir()
    _write_component(d, "FlowDiagram",
                     "use: Linear pipeline.\nlooks: L-to-R boxes.\n"
                     "fill: step = 'title | desc'.")
    _write_component(d, "DecisionTree", None)          # no catalog block
    _write_component(d, "GenBox",                       # infra — never listed
                     "use: internal.\nlooks: x.\nfill: x.")
    (d / "_slotAuthoring.js").write_text("// helper", encoding="utf-8")

    table, missing = km.component_catalog(d)

    assert "FlowDiagram" in table
    assert "Linear pipeline." in table and "L-to-R boxes." in table
    assert "DecisionTree" in table                      # listed name-only
    assert "GenBox" not in table                        # infra excluded
    assert "_slotAuthoring" not in table
    assert missing == ["DecisionTree"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_km_catalog.py -v`
Expected: FAIL — `AttributeError: module 'slidecraft.scripts.km' has no attribute 'parse_catalog_block'`.

- [ ] **Step 3: Implement the extractor in `km.py`**

Add near `AGENTS_DIR` (around line 306):

```python
COMPONENTS_DIR = Path(__file__).resolve().parent.parent / "components"

# Infra / non-diagram files that never appear in the diagram catalog: the
# shared card primitive, the footer, and any private (_-prefixed) module.
CATALOG_EXCLUDE = {"GenBox", "SlideFooter"}

_CATALOG_RE = re.compile(r"<catalog>\s*(.*?)\s*</catalog>", re.S | re.I)


def parse_catalog_block(text: str) -> dict | None:
    """Parse a component's ``<catalog>`` custom SFC block into its three
    fields (``use`` / ``looks`` / ``fill``). Returns ``None`` when the block
    is absent. Vite ignores unknown top-level blocks, so this metadata never
    affects the Slidev build."""
    m = _CATALOG_RE.search(text)
    if not m:
        return None
    fields: dict[str, str] = {}
    key = None
    for line in m.group(1).splitlines():
        fm = re.match(r"^(use|looks|fill)\s*:\s*(.*)$", line.strip(), re.I)
        if fm:
            key = fm.group(1).lower()
            fields[key] = fm.group(2).strip()
        elif key and line.strip():          # continuation line
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return {"use": fields.get("use", ""), "looks": fields.get("looks", ""),
            "fill": fields.get("fill", "")}


def component_catalog(components_dir: Path) -> tuple[str, list[str]]:
    """Render ``%COMPONENT-CATALOG%`` from every diagram component's
    ``<catalog>`` block (D14). Returns ``(table, missing)``: ``table`` is a
    compact per-component stanza list; ``missing`` names components with no
    block (listed name-only, flagged so their metadata gets backfilled).
    A component's NAME is its filename (the diagram designer selects by name)."""
    stanzas: list[str] = []
    missing: list[str] = []
    for p in sorted(components_dir.glob("*.vue")):
        name = p.stem
        if name in CATALOG_EXCLUDE or name.startswith("_"):
            continue
        parsed = parse_catalog_block(p.read_text(encoding="utf-8-sig"))
        if parsed is None:
            missing.append(name)
            stanzas.append(f"- **{name}** — (no catalog metadata)")
            continue
        stanzas.append(
            f"- **{name}** — use: {parsed['use']}\n"
            f"  looks: {parsed['looks']}\n"
            f"  fill: {parsed['fill']}")
    return "\n".join(stanzas), missing
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_catalog.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_catalog.py
git commit -m "feat(km): component_catalog() extracts diagram <catalog> metadata (D14)"
```

---

## Task 3: Backfill `<catalog>` blocks into every diagram component

Add the three-field `<catalog>` block to each **structural / SmartArt / chart** component so `component_catalog()` renders a complete list, and point the README at the per-file metadata as the source of truth. A completeness test locks it: over the real `slidecraft/components/` the `missing` list must be empty.

**Files:**
- Modify: every diagram `.vue` in `slidecraft/components/` (see list below) — add a top-of-file `<catalog>` block
- Modify: `slidecraft/components/README.md` (point "Nested-list authoring" at the per-file `<catalog>` as the source of truth)
- Test: `slidecraft/tests/test_km_catalog.py` (add the real-set completeness test)

**Interfaces:**
- Consumes: `km.component_catalog` (Task 2), `km.COMPONENTS_DIR`, `km.CATALOG_EXCLUDE`.
- Produces: a `<catalog>` block in each shipped diagram component. The `fill` field restates that component's row from the README's per-component nested-list table (§ "Nested-list authoring").

- [ ] **Step 1: Write the failing completeness test**

Add to `slidecraft/tests/test_km_catalog.py`:

```python
def test_shipped_components_all_have_catalog_metadata():
    """Every shipped diagram component (minus infra) carries a <catalog> block,
    so the diagram designer's prompt lists them all with real metadata."""
    table, missing = km.component_catalog(km.COMPONENTS_DIR)
    assert missing == [], f"components missing <catalog> metadata: {missing}"
    # Spot-check a few representative names render with their fields.
    for name in ("FlowDiagram", "DecisionTree", "TwoColumnCompare",
                 "CauseMechanismEffect", "IPODiagram"):
        assert f"**{name}**" in table
    assert "no catalog metadata" not in table
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest slidecraft/tests/test_km_catalog.py::test_shipped_components_all_have_catalog_metadata -v`
Expected: FAIL — `missing` lists every diagram component (none have blocks yet).

- [ ] **Step 3: Add a `<catalog>` block to the top of each component**

For **each** `.vue` below, prepend a `<catalog>` block *before* the existing leading doc comment. Vite ignores unknown top-level custom blocks, so it never affects the build. Use the README's per-component nested-list row for the `fill` field. Template:

```vue
<catalog>
use: <one line — when to choose this component>
looks: <one line — what the rendered figure looks like>
fill: <one line — how to author it from a markdown bullet list, from the README row>
</catalog>
```

Author a block for every component in these two groups (from `README.md`):

**Structural / SmartArt (list-authorable):** `FlowDiagram`, `IPODiagram`, `CycleDiagram`, `ControlLoop`, `HierarchyTree`, `TieredArchitecture`, `PyramidDiagram`, `FunnelDiagram`, `HubSpoke`, `RadialConcept`, `CauseMechanismEffect`, `Fishbone`, `DecisionTree`, `Roadmap`, `NestedBox`, `Staircase`, `BeforeAfter`, `TwoColumnCompare`, `BridgeDiagram`, `GroupedCards`, `Treemap`, `SankeyDiagram`, `GanttChart`.

**Prop-shaped / charts:** `Swimlane`, `AnnotatedArchitecture`, `MatrixQuadrant`, `VennDiagram`, `BarChart`, `PieChart`, `LineChart`, `AreaChart`, `GroupedBarChart`, `StackedBarChart`, `HorizontalBarChart`, `ScatterPlot`, `SlopeChart`, `RadarChart`, `Histogram`, `BoxPlot`, `Heatmap`, `WaterfallChart`. For these the `fill` field describes the **data shape** (props), e.g. `fill: prop-only; :data=[[label, value], …]`.

Worked examples (author the rest the same way — copy the `use`/`looks` from the component's own header comment and the `fill` from the README row):

`FlowDiagram.vue`:
```vue
<catalog>
use: A linear process or pipeline with one clear direction of flow.
looks: Left-to-right boxes joined by single arrows.
fill: bullet list; each top-level item is a step, "title | short description".
</catalog>
```

`DecisionTree.vue`:
```vue
<catalog>
use: A branching decision with yes/no criteria leading to outcomes.
looks: A top-down tree; diamond-ish decision nodes, leaf outcome nodes, labeled edges.
fill: nested bullet list = the tree; a label ending "?" is a decision; child "Yes:"/"No:" sets the edge.
</catalog>
```

`TwoColumnCompare.vue`:
```vue
<catalog>
use: A criterion-by-criterion comparison of two concepts or options.
looks: A two-column table with a criterion label per row and a value in each column.
fill: row = "criterion | left | right"; a leading "= Left title | Right title" li sets the two headings.
</catalog>
```

`CauseMechanismEffect.vue`:
```vue
<catalog>
use: A cause → mechanism → effect chain making the causal path explicit.
looks: Three linked stages left-to-right, each a labeled box with a short description.
fill: exactly 3 items (cause / mechanism / effect), each "label | desc".
</catalog>
```

`IPODiagram.vue`:
```vue
<catalog>
use: An input → process → output structure.
looks: Three stacked/linked panels (Input, Process, Output), each holding items.
fill: exactly 3 items (Input / Process / Output); nested bullets are that panel's items.
</catalog>
```

- [ ] **Step 4: Update the README to name the `<catalog>` block the source of truth**

In `slidecraft/components/README.md`, in the "Nested-list authoring" section, add a short paragraph after the per-component table:

```markdown
> **Source of truth for the diagram designer.** Each component's routing hint,
> appearance, and fill idiom also live in a `<catalog>` block at the top of its
> `.vue` file (`use` / `looks` / `fill`). `km component_catalog()` extracts those
> blocks to build the diagram designer's prompt, so **adding or removing a
> component here automatically adds or removes it from that prompt** (D14). Keep a
> component's `<catalog>` row and its table row above in sync; the `.vue` block wins.
```

- [ ] **Step 5: Run the completeness test**

Run: `python -m pytest slidecraft/tests/test_km_catalog.py::test_shipped_components_all_have_catalog_metadata -v`
Expected: PASS — `missing == []`.

- [ ] **Step 6: Sanity-check the Slidev build ignores the block (manual, quick)**

Confirm the custom block is inert. In any scaffolded deck that imports the theme, the dev server must still start without a Vite parse error for a `<catalog>` block. If a full run is impractical, at minimum verify the block is valid SFC top-level syntax (opens/closes, no stray `</template>`):

Run: `python -c "import re,glob; [print(p) for p in glob.glob('slidecraft/components/*.vue') if len(re.findall(r'<catalog>', open(p,encoding='utf-8').read()))!=len(re.findall(r'</catalog>', open(p,encoding='utf-8').read()))]"`
Expected: no output (every `<catalog>` is balanced).

- [ ] **Step 7: Commit**

```bash
git add slidecraft/components/*.vue slidecraft/components/README.md slidecraft/tests/test_km_catalog.py
git commit -m "feat(components): per-component <catalog> metadata; README points at it (D14)"
```

---

## Task 4: Rewrite the composer into the planner + adapt `compose-brief`

Repoint `agents/slide-composer.md` from a content writer to a **planner** that outputs plan JSON (§4/§5.1), and adapt `km compose-brief` to assemble the planner brief with the new placeholders. The planner writes only the title; it routes every content area to a designer.

**Files:**
- Rewrite: `slidecraft/agents/slide-composer.md`
- Modify: `slidecraft/scripts/km.py` — `cmd_compose_brief` (repoint), add `planner_layouts_section`, `raw_material_section`, `figure_block_section` helpers
- Test: `slidecraft/tests/test_km_compose.py` (replace the compose-brief tests with planner-brief tests)

**Interfaces:**
- Consumes: `offered_layouts`, `style_contract_section`, `slide_type`, `assoc`, `load_nugget`, `load_state`, `load_template`, `render_template`, `write_brief`.
- Produces:
  - `agents/slide-composer.md` — planner template with placeholders `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%STYLE-CONTRACT%` `%WORKING-TITLE%` `%SLIDE-TYPE%` `%INTENDED-FUNCTION%` `%RAW-MATERIAL%` `%FIGURE-BLOCK%` `%LAYOUTS%` `%DECK-METADATA%`.
  - `km.planner_layouts_section(c: dict) -> str` — offered content layouts + their content roles (never physical slots), scoped to single/two-column.
  - `km compose-brief --slide S --out B` renders the planner brief; the plan JSON output contract is §4.

- [ ] **Step 1: Write the new planner template**

Overwrite `slidecraft/agents/slide-composer.md` with:

````markdown
---
name: slide-composer
description: Plans exactly one slide as a pure function — reads its brief (the slide's job, verbatim raw material, layout content-roles, deck metadata) and returns a PLAN JSON (layout, concept_type, title, and per content area a type + instructions + routed nugget ids). Writes only the title; specialist designers build each area. Never touches files, never runs anything, never names a physical slot or a component.
---

# Slide Planner

You plan **one** slide, then you are done. You decide what the slide teaches, its
layout, its assertion title, and — for each content area — *what goes there*, *which
specialist builds it*, and *which knowledge nuggets feed it*. You write **no visible
body content except the title**. Deterministic machinery renders a wireframe from your
plan and dispatches each area to a specialist designer.

- Audience: **%AUDIENCE%** · Deck type: **%DECK-TYPE%** · Language: **%LANGUAGE%**

## The one rule (provenance)

Route only what your raw material supports. Every area's `instructions` and `nuggets`
must trace to the verbatim material in this brief. Thin material → fewer areas, less
routed. That is correct, not a failure.

## What you decide

1. **The didactic function** — one primary `concept_type` (enum below).
2. **The core message** — one sentence: what the audience must remember. It drives the title and the routing.
3. **The assertion title** — 3–7 words, a conclusion/contrast/relationship, not a topic label. Prefer `Automatisierung macht Prozesse skalierbar`; avoid `Hintergrund`, `Vorteile`.
4. **The layout** — one offered layout (see "Layouts you may use"). `content` = one content area (`body`); `two-cols` = two content areas (`left`, `right`).
5. **Per content area** — its `type`, `instructions`, and routed `nuggets`.

`concept_type` ∈ `structural | motivate | define | compare | relationship | process | cause-effect | finding | categories | claim-support`. Honor the intended-function hint (`%INTENDED-FUNCTION%`) unless the material clearly demands otherwise.

## Choosing a type per area (pick the visual shape before the words)

- **`text`** — prose, a list, or a **table**. Comparisons → a table area. One big number → a hero text area.
- **`diagram`** — an on-style structural visual (process, decision tree, cause/effect, hierarchy, cycle, comparison). Choose this when the relationship *is* the point.
- **`source-image`** — **place** a real extracted figure. Route a **figure nugget** (an image nugget carrying an `asset`). **Prefer this over `image`** whenever a routed figure fits — placing a real figure is always more faithful than generating one.
- **`image`** — **generate** a pictorial rendering (only when no real figure fits and the point is genuinely pictorial). Faithful only because the designer renders exact labels verbatim.

Density budget (as guidance you encode by *how much you route*): ≤2–3 content areas, ~30–85 visible words total across the slide, ≤2 hierarchy levels. Do not fill every area; white space is part of the slide.

## Writing `instructions`

- **`text`** — say what claim/structure the area makes and whether prose, a list, or a table; name the relationships to make explicit.
- **`diagram` (must be elaborate)** — write a *natural-language* brief: *what kind* of diagram (the concept shape) **and** *exactly what it shows* — nodes, branches, direction, labels, relationships. **Never name a component**; the diagram designer selects it. Pattern: *"Ein &lt;Diagrammtyp&gt;, der &lt;Konzept&gt; abbildet: &lt;konkrete Knoten, Verzweigungen, Kanten, Beschriftungen&gt;."*
- **`source-image`** — describe what the figure shows (doubles as alt/caption context). Route the figure nugget in `nuggets`.
- **`image`** — describe the scene AND list the exact labels/numbers to render verbatim; invent no text.

## Output contract

Return **only** the JSON object below — no prose before or after, no body content beyond the title.

```json
{
  "layout": "<content | two-cols>",
  "concept_type": "compare",
  "title": "<3–7 word assertion>",
  "sections": {
    "<role>": {"type": "text|diagram|image|source-image", "instructions": "<brief>", "nuggets": ["<id>", "..."]}
  }
}
```

- `sections` keys are the **content-area roles of the chosen layout**: `body` for `content`; `left`/`right` for `two-cols`. Omit an area to fall back to the layout default. `title` is the top-level field, never a section.
- Every routed nugget id must come from "Your slide" below. A `source-image` area must route at least one figure nugget.
- Never name a physical slot and never name a component.

## Your slide

- Working title: **%WORKING-TITLE%**
- Slide type: **%SLIDE-TYPE%**
- Intended didactic function (hint): %INTENDED-FUNCTION%

### Raw material (verbatim — route from this only)

%RAW-MATERIAL%

%FIGURE-BLOCK%

## Layouts you may use

%LAYOUTS%

## Deck metadata

%DECK-METADATA%

Plan in %LANGUAGE%.
````

- [ ] **Step 2: Write the failing planner-brief tests**

Replace the `compose-brief` test block in `slidecraft/tests/test_km_compose.py` (the tests under the "compose-brief — field routing" header, lines ~53–onwards that assert the *old* content-composer brief). Keep the helpers (`_compose_brief`, `PHYSICAL_SLOTS`, imports). Add:

```python
def test_planner_brief_routes_raw_material_and_no_physical_slots(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="First verbatim passage.", page=2)
    _add_nugget(deck, "n2", raw_text="Second verbatim passage.", page=5)
    sid = _create(deck, "Definitions", nuggets="n1,n2", intended_function="define")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # Verbatim raw material reaches the planner (it routes from it).
    assert "First verbatim passage." in brief
    assert "Second verbatim passage." in brief
    # The plan contract + section types are described.
    assert "sections" in brief
    assert "source-image" in brief and "diagram" in brief
    # The hint is offered.
    assert "define" in brief
    # Content layouts advertised by ROLE; never a physical slot; no leftover.
    assert "content" in brief and "two-cols" in brief
    for slot in PHYSICAL_SLOTS:
        assert slot not in brief, f"planner brief leaks physical slot {slot!r}"
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)
    for needle in ("km.py", "--deck", "python ", "write-skeleton"):
        assert needle not in brief


def test_planner_brief_figure_block_lists_figure_nuggets(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Supporting text passage.", page=3)
    _add_nugget(deck, "img1", kind="image", page=4)     # image nugget carries asset
    sid = _create(deck, "Figure with text", nuggets="n1,img1")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # The planner is told a real figure is available to PLACE (source-image).
    assert "img1" in brief
    assert "Available figures" in brief or "figure" in brief.lower()
```

> Note: `_add_nugget`, `_create`, `_set_state`, `_state` are imported from `test_km_plan`; check that `_add_nugget(..., kind="image", ...)` seeds an `asset` under `public/extracted/`. If it does not, add `_add_asset(deck)` in the test and ensure the image nugget's `asset` points at an existing file (mirror `test_km_compose.py::_add_asset`).

- [ ] **Step 3: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_km_compose.py -k planner_brief -v`
Expected: FAIL — the old `compose-brief` emits the content-composer brief (no `sections` contract / raw-material routing wording), and `render_template` will `SystemExit` on the new template's unresolved placeholders.

- [ ] **Step 4: Adapt `cmd_compose_brief` + add helpers in `km.py`**

Replace `cmd_compose_brief` (lines ~919–1038) and add helpers. New helpers:

```python
def planner_layouts_section(c: dict) -> str:
    """Offered CONTENT layouts for the planner, by role — scoped to single-
    column (`content`, role `body`) and two-column (`two-cols`, roles
    `left`/`right`). Never a physical slot name; the medium is a section
    `type`, not a layout, so image-only / prop-image layouts are not offered."""
    lines = []
    for name, entry in offered_layouts(c).items():
        roles = entry.get("roles") or {}
        content_roles = [r for r in roles if r not in ("title", "image")]
        if not content_roles:                       # single content area
            content_roles = ["body"]
        # Scope now: 1 or 2 content areas only.
        if len(content_roles) > 2:
            continue
        intent = entry.get("intent", "")
        lines.append(f"- **{name}**" + (f" — {intent}" if intent else ""))
        lines.append("  content areas (roles): " + ", ".join(content_roles))
    return "\n".join(lines)


def raw_material_section(nugs: list[dict]) -> str:
    """Verbatim raw material for the planner: each text nugget's raw_text with
    its id + locator, each image nugget noted as a placeable figure."""
    parts = []
    for n in nugs:
        nid = n.get("nugget_id", "?")
        loc = nugget_locator(n)
        if n.get("kind") == "image":
            parts.append(f"### Figure nugget {nid} — {loc}\n"
                         f"{str(n.get('description', '')).strip()}")
        else:
            parts.append(f"### Nugget {nid} — {loc}\n"
                         f"{str(n.get('raw_text', '')).strip()}")
    return "\n\n".join(parts) if parts else "(no material)"


def figure_block_section(nugs: list[dict]) -> str:
    """The `%FIGURE-BLOCK%` value: an 'Available figures' list of the image
    nuggets a source-image area may place (id + description + asset presence),
    or '' when the slide routes no figure (optional placeholder, D10)."""
    imgs = [n for n in nugs if n.get("kind") == "image"]
    if not imgs:
        return ""
    lines = ["### Available figures (place via a `source-image` area)"]
    for n in imgs:
        lines.append(f"- {n.get('nugget_id', '?')} — "
                     f"{str(n.get('description', '')).strip()}")
    return "\n".join(lines)


def cmd_compose_brief(root: Path, a):
    """Assemble the PLANNER brief for ONE slide (§5.1): planner template +
    theme style contract + the slide's verbatim raw material + offered content
    layouts (by role) + deck metadata. The planner routes; it writes only the
    title. (Renamed role of the former composer brief.)"""
    sid = a.slide
    stj = load_state(root, sid)
    if not stj:
        sys.exit(f"ERROR: slide {sid} does not exist")
    A = assoc(root)
    if sid not in A:
        sys.exit(f"ERROR: slide {sid} has no association entry")
    nugs = []
    for nid in A[sid]:
        n = load_nugget(root, nid)
        if not n:
            sys.exit(f"ERROR: nugget {nid} missing")
        nugs.append(n)
    stype = slide_type(nugs)

    c = ctx(root)
    inj = c.get("injection", {}).get("slide-composer", {})
    deckb = c["deck"]
    meta_lines = [f"- Topic: {deckb.get('topic', '')}"]
    for label, key in (("Presenter", "presenter"), ("Institution", "institution"),
                       ("Course", "course"), ("Date", "date"), ("Footer", "footer")):
        v = inj.get(key.upper(), deckb.get(key, ""))
        if v:
            meta_lines.append(f"- {label}: {v}")
    hint = stj.get("intended_function")
    values = {
        "AUDIENCE": inj.get("AUDIENCE", deckb.get("audience", "")),
        "DECK-TYPE": inj.get("DECK-TYPE", deckb.get("type", "")),
        "LANGUAGE": inj.get("LANGUAGE", deckb.get("language", "")),
        "STYLE-CONTRACT": "",   # style contract appended after render (below)
        "WORKING-TITLE": stj.get("title", sid),
        "SLIDE-TYPE": stype,
        "INTENDED-FUNCTION": (f"**{hint}** — honor it unless the material "
                              "clearly demands otherwise." if hint
                              else "(none given)"),
        "RAW-MATERIAL": raw_material_section(nugs),
        "FIGURE-BLOCK": figure_block_section(nugs),
        "LAYOUTS": planner_layouts_section(c),
        "DECK-METADATA": "\n".join(meta_lines),
    }
    brief = render_template(load_template("slide-composer"), values)
    brief += style_contract_section(c)
    write_brief(root, a.out, brief)
    log(root, "km", "compose-brief", slide=sid, type=stype, chars=len(brief))
    print(json.dumps({"ok": True, "brief": a.out, "slide": sid,
                      "type": stype, "chars": len(brief)}))
```

> The template's `%STYLE-CONTRACT%` placeholder is resolved to `""` here and the real contract is appended by `style_contract_section` (matching the existing pattern). If you prefer, inline the contract into `%STYLE-CONTRACT%` instead and drop the append — either satisfies the leftover guard. Keep the append to mirror the existing code.

- [ ] **Step 5: Run the planner-brief tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_compose.py -k planner_brief -v`
Expected: PASS.

- [ ] **Step 6: Prune the now-obsolete old-composer brief assertions**

Run the whole compose test file and delete/repair any remaining test that asserts the *old* content-composer brief wording (e.g. "Raw source material", image-only "HEADLINE ONLY"). Keep the `write-slide` tests untouched (write-slide is unchanged this task).

Run: `python -m pytest slidecraft/tests/test_km_compose.py -q`
Expected: PASS (write-slide tests green; planner-brief tests green; no stale compose-brief test remains).

- [ ] **Step 7: Commit**

```bash
git add slidecraft/agents/slide-composer.md slidecraft/scripts/km.py slidecraft/tests/test_km_compose.py
git commit -m "feat(planner): rewrite slide-composer as planner; compose-brief assembles plan brief (D1/D3)"
```

---

## Task 5: `km write-skeleton` — validate the plan, render the wireframe, persist the sidecar

The Stage-1 persist step. Validates the plan JSON (§4), writes `slides/<sid>.md` as a wireframe (each content area a `<!-- TYPE · pending -->` + instruction blockquote), **places** every `source-image` area as an `<img>` from its figure nugget's asset, persists the plan sidecar into the slide state with per-section status, sets state `planned`, and returns the sections still needing a designer. Structural slides bypass the section contract.

**Files:**
- Modify: `slidecraft/scripts/km.py` — add `cmd_write_skeleton`, `content_roles_for`, `aspect_ratio_for`, `validate_plan`; register the `write-skeleton` subparser + dispatch
- Test: `slidecraft/tests/test_km_write_skeleton.py` (new)

**Interfaces:**
- Consumes: `offered_layouts`, `CONCEPT_TYPES`, `assoc`, `load_nugget`, `load_state`, `save_state`, `yaml_str`, `Rejection`, `missing_assets`.
- Produces:
  - `km.content_roles_for(entry: dict) -> list[str]` — a layout entry's content roles: `roles` minus `title`/`image`, or `["body"]` when the layout has no roles map.
  - `km.aspect_ratio_for(role: str) -> str` — `"16:9"` for `body`, `"1:1"` for `left`/`right` (D17).
  - `km write-skeleton --slide S --file PLAN` — validates + writes wireframe + sidecar; prints `{"ok": true, "slide": S, "state": "planned", "pending_sections": [roles…], "placed_sections": [roles…]}`. All rejections are `Rejection` → exit 1 (retryable).
  - Slide state gains `plan`: `{layout, concept_type, title, sections: {role: {type, instructions, nuggets, status}}}`; `status ∈ pending|placed|failed`. Slide `state`: `planned`.

- [ ] **Step 1: Write the failing tests**

Create `slidecraft/tests/test_km_write_skeleton.py`:

```python
"""Stage-1 persist: km write-skeleton validates the plan JSON, renders a
wireframe, places source-image areas, and persists the plan sidecar (design §4/§6)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create


def _write_skeleton(deck: Path, sid: str, plan: dict):
    f = deck / "plan-out.json"
    f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    km.cmd_write_skeleton(deck, Namespace(slide=sid, file=str(f)))


def _md(deck: Path, sid: str) -> str:
    return (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")


def _add_image_nugget(deck: Path, nid: str, name="fig1.png"):
    (deck / "public" / "extracted").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "extracted" / name).write_bytes(b"\x89PNG fake")
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps({
        "nugget_id": nid, "kind": "image", "title": "Fig",
        "information": "- x", "visible_text": ["Predict", "Update"],
        "description": "predict-update loop", "asset": f"/extracted/{name}",
        "source": "chapter_4.md", "page": 2}), encoding="utf-8")
    return nid


def test_two_cols_plan_writes_wireframe_and_pending_sections(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left passage.", page=1)
    _add_nugget(deck, "n2", raw_text="Right passage.", page=1)
    sid = _create(deck, "SLA vs FDM", nuggets="n1,n2")
    capsys.readouterr()

    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare",
        "title": "SLA ist präziser, FDM skaliert",
        "sections": {
            "left": {"type": "text", "instructions": "Table of tradeoffs.",
                     "nuggets": ["n1"]},
            "right": {"type": "diagram", "instructions": "A decision tree …",
                      "nuggets": ["n2"]}}})
    out = json.loads(capsys.readouterr().out)

    assert out["state"] == "planned"
    assert sorted(out["pending_sections"]) == ["left", "right"]
    md = _md(deck, sid)
    assert "layout: cols" in md                 # physical layout (theme)
    assert "SLA ist präziser" in md             # title in frontmatter
    assert "::col-a::" in md and "::col-b::" in md   # physical slots
    assert "pending" in md                       # wireframe marker
    assert "decision tree" in md.lower()         # instruction shown as blockquote
    stj = km.load_state(deck, sid)
    assert stj["plan"]["sections"]["left"]["status"] == "pending"


def test_source_image_section_is_placed_without_a_designer(deck, tmp_path, capsys):
    img = _add_image_nugget(deck, "img1")
    sid = _create(deck, "The tracking loop", nuggets="img1")
    capsys.readouterr()

    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process",
        "title": "The tracking loop",
        "sections": {"body": {"type": "source-image",
                              "instructions": "Reference photo.",
                              "nuggets": ["img1"]}}})
    out = json.loads(capsys.readouterr().out)

    assert out["pending_sections"] == []
    assert out["placed_sections"] == ["body"]
    md = _md(deck, sid)
    assert "/extracted/fig1.png" in md          # the real asset placed
    stj = km.load_state(deck, sid)
    assert stj["plan"]["sections"]["body"]["status"] == "placed"


def test_structural_slide_bypasses_sections(deck, tmp_path, capsys):
    sid = _create(deck, "Object Tracking", nuggets="")     # structural: no nuggets
    capsys.readouterr()
    _write_skeleton(deck, sid, {"layout": "content", "concept_type": "structural",
                                "title": "Object Tracking", "sections": {}})
    out = json.loads(capsys.readouterr().out)
    assert out["pending_sections"] == []
    assert "Object Tracking" in _md(deck, sid)


def test_invalid_layout_is_a_rejection(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _write_skeleton(deck, sid, {
            "layout": "no-such", "concept_type": "define", "title": "T",
            "sections": {"body": {"type": "text", "instructions": "x",
                                  "nuggets": ["n1"]}}})
    assert "layout" in str(exc.value) and str(exc.value) != "2"   # exit 1 (Rejection)


def test_source_image_without_a_figure_nugget_is_rejected(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)             # text, not a figure
    sid = _create(deck, "T", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _write_skeleton(deck, sid, {
            "layout": "content", "concept_type": "define", "title": "T",
            "sections": {"body": {"type": "source-image",
                                  "instructions": "x", "nuggets": ["n1"]}}})
    assert "figure" in str(exc.value).lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_km_write_skeleton.py -v`
Expected: FAIL — `AttributeError: … has no attribute 'cmd_write_skeleton'`.

- [ ] **Step 3: Implement helpers + `validate_plan` + `cmd_write_skeleton` in `km.py`**

Add (place after `build_slide_markdown`, keeping `Rejection` above — it is defined at line ~1183, so move these functions *below* `Rejection` or reference it fine since Python resolves at call time; place them near `cmd_write_slide`):

```python
SECTION_TYPES = ("text", "diagram", "image", "source-image")
ASPECT_BY_ROLE = {"body": "16:9", "left": "1:1", "right": "1:1"}


def content_roles_for(entry: dict) -> list[str]:
    """A layout entry's CONTENT-area roles (design §4): its roles map minus
    `title`/`image`, or `["body"]` when the layout ships no roles map."""
    roles = entry.get("roles") or {}
    content = [r for r in roles if r not in ("title", "image")]
    return content or ["body"]


def aspect_ratio_for(role: str) -> str:
    """The image-generation aspect ratio for a content role (D17): single-
    column `body` → 16:9; two-column `left`/`right` → 1:1."""
    return ASPECT_BY_ROLE.get(role, "16:9")


def validate_plan(root: Path, sid: str, obj, c: dict) -> tuple[dict, dict]:
    """Validate a planner plan JSON (§4). Returns (entry, sections) where
    `entry` is the offered-layout entry and `sections` is the validated
    per-role section map. Raises :class:`Rejection` (retryable, exit 1) on any
    model-fixable problem."""
    if not isinstance(obj, dict):
        raise Rejection("plan must be a single JSON object")
    offered = offered_layouts(c)
    layout = obj.get("layout")
    if not isinstance(layout, str) or layout not in offered:
        raise Rejection(f"layout {layout!r} is not one of the offered "
                        f"layouts: {sorted(offered)}")
    entry = offered[layout]
    concept = obj.get("concept_type")
    if concept not in CONCEPT_TYPES:
        raise Rejection(f"concept_type {concept!r} not in {list(CONCEPT_TYPES)}")
    if not obj.get("title") or not isinstance(obj["title"], str):
        raise Rejection('plan needs a non-empty string "title"')
    sections = obj.get("sections") or {}
    if not isinstance(sections, dict):
        raise Rejection('"sections" must map content-area roles to objects')
    allowed_roles = set(content_roles_for(entry))
    unknown = sorted(set(sections) - allowed_roles)
    if unknown:
        raise Rejection(f"unknown section role(s) {unknown} for layout "
                        f"{layout!r} — allowed: {sorted(allowed_roles)}")
    A = assoc(root)
    associated = set(A.get(sid, []))
    for role, sec in sections.items():
        if not isinstance(sec, dict):
            raise Rejection(f"section {role!r} must be an object")
        stype = sec.get("type")
        if stype not in SECTION_TYPES:
            raise Rejection(f"section {role!r} type {stype!r} not in "
                            f"{list(SECTION_TYPES)}")
        nug_ids = sec.get("nuggets") or []
        if not isinstance(nug_ids, list):
            raise Rejection(f"section {role!r} nuggets must be a list")
        for nid in nug_ids:
            if nid not in associated:
                raise Rejection(f"section {role!r} routes nugget {nid!r} that "
                                "is not associated with this slide")
        if stype == "source-image":
            figs = [nid for nid in nug_ids
                    if (load_nugget(root, nid) or {}).get("kind") == "image"]
            if not figs:
                raise Rejection(f"section {role!r} is source-image but routes "
                                "no figure nugget (an image nugget with an asset)")
            for nid in figs:
                asset = str((load_nugget(root, nid) or {}).get("asset", ""))
                if not asset or not (root / "public" / asset.lstrip("/")).exists():
                    raise Rejection(f"section {role!r} figure {nid} has no asset "
                                    f"under public/ (asset={asset!r})")
    return entry, sections


def _wireframe_placeholder(stype: str, instructions: str) -> str:
    """The visible wireframe for a pending content area: a machine marker + the
    planner's instruction as a blockquote (so a live-watched deck shows what
    each area will become while the designers work)."""
    instr = (instructions or "").strip().replace("\n", " ")
    return (f"<!-- {stype} · pending -->\n\n"
            f"> 🚧 **{stype}** — {instr}")


def cmd_write_skeleton(root: Path, a):
    """Stage-1 persist (§6): validate the plan JSON, render the wireframe,
    place source-image areas, persist the plan sidecar + per-section status,
    set state `planned`, and return the sections still needing a designer.
    Rejection = exit 1 (shim retry; cap-2 = park terminal). A structural plan
    (no sections) composes from title + layout defaults only."""
    sid = a.slide
    stp = root / "slides" / f"{sid}.json"
    sp = root / "slides" / f"{sid}.md"
    if not stp.exists():
        gate_exit(f"ERROR: slide {sid} does not exist")
    stj = load_state(root, sid)
    if stj.get("state") == "locked":
        gate_exit(f"ERROR: slide {sid} is locked")
    if stj.get("state") == "parked":
        gate_exit(f"ERROR: slide {sid} is parked — unpark before planning")
    p = Path(a.file)
    if not p.exists():
        gate_exit(f"ERROR: plan file {a.file} does not exist")
    try:
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: plan output is not valid JSON: {exc}")
    try:
        entry, sections = validate_plan(root, sid, obj, ctx(root))
    except Rejection as exc:
        sys.exit(f"ERROR: {exc}")

    physical_layout = entry["name"]
    roles = entry.get("roles") or {}
    title = str(obj["title"]).strip()
    fm = [f"layout: {physical_layout}", f"title: {yaml_str(title)}"]
    parts = ["---\n" + "\n".join(fm) + "\n---\n"]

    # Title into its slot (if the layout has one), else an H1.
    if "title" in roles:
        parts.append(f"\n::{roles['title']}::\n# {title}\n")
    elif not roles:
        parts.append(f"\n# {title}\n")

    plan_sections: dict[str, dict] = {}
    pending, placed = [], []
    for role in content_roles_for(entry):
        sec = sections.get(role)
        slot = roles.get(role)
        if sec is None:
            plan_sections[role] = {"type": "text", "instructions": "",
                                   "nuggets": [], "status": "placed"}
            continue
        stype = sec["type"]
        instructions = str(sec.get("instructions", ""))
        nug_ids = list(sec.get("nuggets") or [])
        if stype == "source-image":
            fig = next(nid for nid in nug_ids
                       if (load_nugget(root, nid) or {}).get("kind") == "image")
            asset = str((load_nugget(root, fig) or {})["asset"])
            block = f'<img src="{asset}" alt="{title}">'
            status = "placed"; placed.append(role)
        else:
            block = _wireframe_placeholder(stype, instructions)
            status = "pending"; pending.append(role)
        if slot:
            parts.append(f"\n::{slot}::\n{block}\n")
        else:
            parts.append(f"\n{block}\n")
        plan_sections[role] = {"type": stype, "instructions": instructions,
                               "nuggets": nug_ids, "status": status}

    body = "".join(parts)
    for asset in missing_assets(root, body):
        sys.exit(f"ERROR: referenced asset '{asset}' does not exist "
                 f"(expected under public/: public{asset})")
    sp.write_text(body, encoding="utf-8")

    stj["state"] = "planned"
    stj["concept_type"] = obj["concept_type"]
    stj["title"] = title
    stj["plan"] = {"layout": physical_layout, "concept_type": obj["concept_type"],
                   "title": title, "sections": plan_sections}
    # A slide whose only areas were source-image (or defaults) is already done.
    if not pending:
        stj["state"] = "composed"
    save_state(root, sid, stj)
    log(root, "km", "write-skeleton", slide=sid, layout=physical_layout,
        pending=len(pending), placed=len(placed))
    print(json.dumps({"ok": True, "slide": sid, "state": stj["state"],
                      "pending_sections": pending, "placed_sections": placed}))
```

- [ ] **Step 4: Register the subparser + dispatch**

In `main()` (around line 1851, next to `write-slide`):

```python
    wsk = sub.add_parser("write-skeleton"); wsk.add_argument("--slide", required=True); wsk.add_argument("--file", required=True)
```

and in the dispatch dict (around line 1868):

```python
     "write-skeleton": cmd_write_skeleton,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_write_skeleton.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_write_skeleton.py
git commit -m "feat(km): write-skeleton validates plan, renders wireframe, places source-image (D4/D6)"
```

---

## Task 6: The three specialist designer templates

Create the three designer prompt templates (§5.2–5.4). Each builds ONE content area from the planner's instructions + routed nuggets + the full slide raw material (D13). They return **raw content** (Markdown / a component-or-Vue block / an image), not JSON.

**Files:**
- Create: `slidecraft/agents/text-designer.md`, `slidecraft/agents/diagram-designer.md`, `slidecraft/agents/image-designer.md`
- Test: `slidecraft/tests/test_designer_templates.py` (new — render-smoke each template)

**Interfaces:**
- Consumes: `km.load_template`, `km.render_template`.
- Produces three templates with these placeholder sets:
  - text: `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%STYLE-CONTRACT%` `%CORE-MESSAGE%` `%SECTION-ROLE%` `%INSTRUCTIONS%` `%NUGGETS%` `%RAW-MATERIAL%`
  - diagram: the text set **+** `%COMPONENT-CATALOG%`
  - image: `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%CORE-MESSAGE%` `%SECTION-ROLE%` `%INSTRUCTIONS%` `%NUGGETS%` `%RAW-MATERIAL%` `%EXACT-TEXT%` `%ASPECT-RATIO%`

- [ ] **Step 1: Write the render-smoke test (failing)**

Create `slidecraft/tests/test_designer_templates.py`:

```python
"""The three designer templates render with their exact placeholder set and
leave no leftover placeholder (the leftover guard is the real contract)."""
from __future__ import annotations

import re

import pytest

from slidecraft.scripts import km

TEXT_VALUES = {"AUDIENCE": "students", "DECK-TYPE": "lecture", "LANGUAGE": "en",
               "STYLE-CONTRACT": "…", "CORE-MESSAGE": "msg", "SECTION-ROLE": "left",
               "INSTRUCTIONS": "Make a table.", "NUGGETS": "n-raw",
               "RAW-MATERIAL": "all raw"}
DIAGRAM_VALUES = {**TEXT_VALUES, "COMPONENT-CATALOG": "- **FlowDiagram** …"}
IMAGE_VALUES = {"AUDIENCE": "students", "DECK-TYPE": "lecture", "LANGUAGE": "en",
                "CORE-MESSAGE": "msg", "SECTION-ROLE": "body",
                "INSTRUCTIONS": "Render X.", "NUGGETS": "n-raw",
                "RAW-MATERIAL": "all raw", "EXACT-TEXT": "Predict\nUpdate",
                "ASPECT-RATIO": "16:9"}


@pytest.mark.parametrize("name,values", [
    ("text-designer", TEXT_VALUES),
    ("diagram-designer", DIAGRAM_VALUES),
    ("image-designer", IMAGE_VALUES)])
def test_designer_template_renders_clean(name, values):
    out = km.render_template(km.load_template(name), values)
    assert not re.search(r"%[A-Z][A-Z_-]*%", out)
    assert values["INSTRUCTIONS"] in out          # instruction reaches the designer


def test_diagram_template_carries_the_component_catalog():
    out = km.render_template(km.load_template("diagram-designer"), DIAGRAM_VALUES)
    assert "FlowDiagram" in out


def test_image_template_states_aspect_and_exact_text():
    out = km.render_template(km.load_template("image-designer"), IMAGE_VALUES)
    assert "16:9" in out and "Predict" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest slidecraft/tests/test_designer_templates.py -v`
Expected: FAIL — `ERROR: role template not found: …/agents/text-designer.md`.

- [ ] **Step 3: Create `slidecraft/agents/text-designer.md`**

````markdown
---
name: text-designer
description: Builds ONE content area of a slide as text — prose, a list, or a table — from the planner's instructions and the routed nuggets. Returns Markdown for that area only. Never a title, never frontmatter, never another area.
---

# Text / Table Designer

You build **one content area** of a slide: the `%SECTION-ROLE%` area. You return the
Markdown that goes *inside* that area — nothing else. No title, no frontmatter, no layout.

- Audience: **%AUDIENCE%** · Deck type: **%DECK-TYPE%** · Language: **%LANGUAGE%**
- The slide's core message: **%CORE-MESSAGE%**

## Your instructions (from the planner)

%INSTRUCTIONS%

## The one rule (provenance)

Say only what the material supports. Every claim traces to your routed nuggets. Compress
by abstraction, not truncation — keep the meaning, drop the words. Thin material → a short
area. Do not invent facts, numbers, or examples.

## Craft

- Decide **prose vs. list vs. table** from the instruction. A comparison → a Markdown table.
  A sequence → an arrow chain (`**Input** → **Transformation** → **Outcome**`). A small set of
  equal items → bullets (only here). One big number → a hero line.
- Keep relationships explicit (`ermöglicht`, `führt zu`, `im Gegensatz zu`, `→`, in %LANGUAGE%).
- Preserve academic precision: enabler vs. outcome, hypothesis vs. result, tool vs. transformation.
- At most two hierarchy levels; no bullet that wraps several lines; white space is fine.

## Your routed knowledge (verbatim)

%NUGGETS%

## Full slide raw material (context — do not restate other areas)

%RAW-MATERIAL%

## Style contract

%STYLE-CONTRACT%

## Output

Return **only** the Markdown for this area — prose, a list, or a table. No code fence is
required (if you use one, it is stripped). No title, no `::slot::`, no frontmatter, no
commentary. Write in %LANGUAGE%.
````

- [ ] **Step 4: Create `slidecraft/agents/diagram-designer.md`**

````markdown
---
name: diagram-designer
description: Builds ONE content area as an on-style structural diagram — either a shipped diagram component authored from a nested markdown list, or a self-contained Slidev Vue SFC when no component fits. Returns the component/Vue block for that area only.
---

# Diagram Designer

You build **one content area** — the `%SECTION-ROLE%` area — as a structural diagram.

- Audience: **%AUDIENCE%** · Deck type: **%DECK-TYPE%** · Language: **%LANGUAGE%**
- The slide's core message: **%CORE-MESSAGE%**

## Your instructions (from the planner)

%INSTRUCTIONS%

## How to build it

Prefer a **shipped component** authored from a nested markdown bullet list — it is readable,
editable, and on-style by construction. Select the component from the catalog below by
matching your instruction's diagram kind to a component's `use`. Author it with its `fill`
idiom:

```md
<FlowDiagram>

- Capture | raw signal in
- Filter | remove noise
- Estimate | fuse model + measurement

</FlowDiagram>
```

If **no component fits**, return a **self-contained Slidev Vue SFC** (a single ```vue block)
rendering only this content area.

## Component catalog

%COMPONENT-CATALOG%

## House rules (non-negotiable)

- **Structure + icons only. Never hand-draw a depicted object.** If a concept wants a picture,
  use a real Carbon/Phosphor icon + a label, never a bespoke drawing.
- Equal-sized, aligned boxes for peer items; one shared arrowhead; palette from theme tokens
  (`var(--gen-accent)` navy, `--gen-accent-2` ochre, `--gen-accent-3` teal); min 14px text.
- The figure fills its container with no overflow. Use only real icon names (they are
  sanitized at placement; unknown names are replaced).

## Your routed knowledge (verbatim)

%NUGGETS%

## Full slide raw material (context)

%RAW-MATERIAL%

## Style contract

%STYLE-CONTRACT%

## Output

Return **only** the component invocation (with its nested list) **or** one ```vue block for
this area — nothing else. No title, no `::slot::`, no commentary. Labels in %LANGUAGE%.
````

- [ ] **Step 5: Create `slidecraft/agents/image-designer.md`**

````markdown
---
name: image-designer
description: Generates ONE image for a content area (nano-banana-pro), rendering only exact labels verbatim, at the given aspect ratio. Returns a single image.
---

# Image Designer

You generate **one image** for the `%SECTION-ROLE%` content area of a slide.

- Audience: **%AUDIENCE%** · Deck type: **%DECK-TYPE%** · Language: **%LANGUAGE%**
- The slide's core message: **%CORE-MESSAGE%**
- Aspect ratio: **%ASPECT-RATIO%** — render at exactly this ratio.

## Your instructions (from the planner)

%INSTRUCTIONS%

## The faithfulness rule (non-negotiable)

Render **only** the text in the exact-text list below, **verbatim** — every label and number.
Invent no text, no labels, no numbers. If a value is not in the exact-text list or your
instructions, it does not appear in the image. This is what makes a generated image faithful.

## Exact text to render (verbatim)

%EXACT-TEXT%

## Canvas

- A pure-white canvas, content-area only (no slide chrome, no title bar, no page furniture).
- Clean, on-style, legible when projected; the aspect ratio is exactly **%ASPECT-RATIO%**.

## Your routed knowledge

%NUGGETS%

## Full slide raw material (context)

%RAW-MATERIAL%

## Output

Return one image. Do not add explanatory prose.
````

- [ ] **Step 6: Run the render-smoke tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_designer_templates.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add slidecraft/agents/text-designer.md slidecraft/agents/diagram-designer.md slidecraft/agents/image-designer.md slidecraft/tests/test_designer_templates.py
git commit -m "feat(designers): text/diagram/image designer prompt templates (D13/D14/D17)"
```

---

## Task 7: `km design-brief` — assemble one designer's brief

Reads the plan sidecar for a slide+section, renders the matching designer template with all placeholder values: `%INSTRUCTIONS%`, the routed nuggets' verbatim material as `%NUGGETS%`, the **full** slide raw material as `%RAW-MATERIAL%` (D13), `%CORE-MESSAGE%` = the plan title, plus type-specific values (`%COMPONENT-CATALOG%` for diagram; `%EXACT-TEXT%` + `%ASPECT-RATIO%` for image).

**Files:**
- Modify: `slidecraft/scripts/km.py` — add `cmd_design_brief`, `_designer_role_for`, `nuggets_material`; register subparser + dispatch
- Test: `slidecraft/tests/test_km_design_brief.py` (new)

**Interfaces:**
- Consumes: `load_state` (plan sidecar), `assoc`, `load_nugget`, `nugget_locator`, `component_catalog`, `COMPONENTS_DIR`, `style_contract_section`, `render_template`, `load_template`, `write_brief`, `aspect_ratio_for`.
- Produces:
  - `km._designer_role_for(stype: str) -> str` — `text`→`text-designer`, `diagram`→`diagram-designer`, `image`→`image-designer` (`source-image` has no brief — placed by write-skeleton).
  - `km design-brief --slide S --section R --out B` — prints `{"ok": true, "slide": S, "section": R, "type": T, "role": ROLE, "brief": B, "chars": N}`.

- [ ] **Step 1: Write the failing tests**

Create `slidecraft/tests/test_km_design_brief.py`:

```python
"""Stage-2 assemble: km design-brief renders the right designer template with
routed nuggets (%NUGGETS%), the full slide raw material (%RAW-MATERIAL%, D13),
and type-specific values (component catalog / exact-text + aspect ratio)."""
from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _add_image_nugget


def _design_brief(deck: Path, sid: str, role: str, out: Path) -> str:
    km.cmd_design_brief(deck, Namespace(slide=sid, section=role, out=str(out)))
    return out.read_text(encoding="utf-8")


def test_text_design_brief_routes_nuggets_and_full_raw_material(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left verbatim.", page=1)
    _add_nugget(deck, "n2", raw_text="Right verbatim.", page=1)
    sid = _create(deck, "Compare", nuggets="n1,n2")
    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare", "title": "Compare A/B",
        "sections": {
            "left": {"type": "text", "instructions": "Make a table.", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "Short prose.", "nuggets": ["n2"]}}})
    capsys.readouterr()

    brief = _design_brief(deck, sid, "left", tmp_path / "b.md")

    assert "Make a table." in brief                 # instructions
    assert "Left verbatim." in brief                # routed nugget (%NUGGETS%)
    assert "Right verbatim." in brief               # full raw material (D13)
    assert "Compare A/B" in brief                    # %CORE-MESSAGE% = plan title
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)


def test_diagram_design_brief_carries_component_catalog(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Flow verbatim.", page=1)
    sid = _create(deck, "Flow", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "The flow",
        "sections": {"body": {"type": "diagram",
                              "instructions": "A left-to-right pipeline …",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    brief = _design_brief(deck, sid, "body", tmp_path / "b.md")
    assert "FlowDiagram" in brief                    # real catalog injected
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)


def test_image_design_brief_sets_aspect_and_exact_text(deck, tmp_path, capsys):
    img = _add_image_nugget(deck, "img1")            # visible_text ["Predict","Update"]
    _add_nugget(deck, "n1", raw_text="Loop verbatim.", page=1)
    sid = _create(deck, "Loop", nuggets="n1,img1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "The loop",
        "sections": {"body": {"type": "image",
                              "instructions": "Render the predict-update loop.",
                              "nuggets": ["n1", "img1"]}}})
    capsys.readouterr()
    brief = _design_brief(deck, sid, "body", tmp_path / "b.md")
    assert "16:9" in brief                            # body → 16:9 (D17)
    assert "Predict" in brief and "Update" in brief   # %EXACT-TEXT% from visible_text
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_km_design_brief.py -v`
Expected: FAIL — `AttributeError: … 'cmd_design_brief'`.

- [ ] **Step 3: Implement in `km.py`**

```python
def _designer_role_for(stype: str) -> str:
    return {"text": "text-designer", "diagram": "diagram-designer",
            "image": "image-designer"}.get(stype, "")


def nuggets_material(root: Path, nug_ids) -> str:
    """Verbatim material for a set of nugget ids: raw_text for text nuggets,
    visible_text lines for image nuggets, each with a provenance locator."""
    parts = []
    for nid in nug_ids:
        n = load_nugget(root, nid)
        if not n:
            continue
        raw = nugget_raw(n)                 # existing helper: raw_text / visible_text
        if raw:
            parts.append(f"[{nugget_locator(n)}]\n{raw}")
    return "\n\n".join(parts) if parts else "(no material)"


def _exact_text(root: Path, nug_ids) -> str:
    """The verbatim on-figure labels an image designer may render: every image
    nugget's visible_text, one per line. Empty when the routed nuggets carry
    none (the planner's instructions then carry the wording)."""
    lines = []
    for nid in nug_ids:
        n = load_nugget(root, nid) or {}
        vt = n.get("visible_text")
        if isinstance(vt, list):
            lines.extend(str(x) for x in vt)
    return "\n".join(lines) if lines else "(none — render only what the instructions name)"


def cmd_design_brief(root: Path, a):
    """Stage-2 assemble (§6): read the plan sidecar, render the designer
    template for this slide+section with routed material + full slide raw
    material (D13) + type-specific values."""
    sid, role = a.slide, a.section
    stj = load_state(root, sid)
    plan = stj.get("plan") or {}
    sec = (plan.get("sections") or {}).get(role)
    if not sec:
        gate_exit(f"ERROR: slide {sid} has no planned section {role!r}")
    stype = sec["type"]
    designer = _designer_role_for(stype)
    if not designer:
        gate_exit(f"ERROR: section {role!r} type {stype!r} has no designer "
                  "(source-image is placed by write-skeleton)")
    c = ctx(root)
    inj = c.get("injection", {}).get(designer, {})
    deckb = c["deck"]
    all_nug_ids = assoc(root).get(sid, [])
    values = {
        "AUDIENCE": inj.get("AUDIENCE", deckb.get("audience", "")),
        "DECK-TYPE": inj.get("DECK-TYPE", deckb.get("type", "")),
        "LANGUAGE": inj.get("LANGUAGE", deckb.get("language", "")),
        "CORE-MESSAGE": plan.get("title", stj.get("title", sid)),
        "SECTION-ROLE": role,
        "INSTRUCTIONS": sec.get("instructions", ""),
        "NUGGETS": nuggets_material(root, sec.get("nuggets", [])),
        "RAW-MATERIAL": nuggets_material(root, all_nug_ids),   # D13: full slide
    }
    if stype == "diagram":
        table, _missing = component_catalog(COMPONENTS_DIR)
        values["COMPONENT-CATALOG"] = table
    if stype == "image":
        values["EXACT-TEXT"] = _exact_text(root, sec.get("nuggets", []))
        values["ASPECT-RATIO"] = aspect_ratio_for(role)
    # Style contract only for text/diagram (image has no %STYLE-CONTRACT%).
    body = render_template(load_template(designer),
                           {**values, "STYLE-CONTRACT": ""} if stype != "image" else values)
    if stype != "image":
        body += style_contract_section(c)
    write_brief(root, a.out, body)
    log(root, "km", "design-brief", slide=sid, section=role, type=stype,
        chars=len(body))
    print(json.dumps({"ok": True, "slide": sid, "section": role, "type": stype,
                      "role": designer, "brief": a.out, "chars": len(body)}))
```

Register in `main()`:

```python
    db = sub.add_parser("design-brief"); db.add_argument("--slide", required=True); db.add_argument("--section", required=True); db.add_argument("--out", required=True)
```
```python
     "design-brief": cmd_design_brief,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_design_brief.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_design_brief.py
git commit -m "feat(km): design-brief assembles per-section designer prompts (D13/D14/D17)"
```

---

## Task 8: `km place-design` — extract, sanitize, place, promote (incl. icon-sanitize)

The Stage-2 persist step. Deterministically extracts a designer's raw reply, sanitizes icons for diagrams, swaps the wireframe placeholder for the result, updates the section status, and promotes the slide to `composed` when no section is still pending. `km` stays network-free — an `image` reply is already-downloaded (the caller passes `--asset`).

**Files:**
- Modify: `slidecraft/scripts/km.py` — add `ICON_ALLOWLIST_FILE`, `sanitize_icons`, `_extract_designer_reply`, `cmd_place_design`; register subparser + dispatch
- Create: `slidecraft/references/icon-allowlist.txt` (starter allowlist)
- Test: `slidecraft/tests/test_km_place_design.py` (new)

**Interfaces:**
- Consumes: `load_state`, `save_state`, `slugify`, `missing_assets`.
- Produces:
  - `km.sanitize_icons(markup: str) -> str` — replace any Iconify-style icon component (`<carbon-…/>`, `<ph-…/>`, `<mdi-…/>`, `<carbon:…/>`, …) whose name is not in the allowlist with a safe fallback (`<carbon-circle-solid/>`), so a hallucinated icon never crashes the Vite transform.
  - `km place-design --slide S --section R --type T --file REPLY [--asset PATH]` — prints `{"ok": true, "slide": S, "section": R, "status": "placed", "slide_state": "composed|planned"}`. `--type` ∈ `text|diagram|image`.

- [ ] **Step 1: Write the failing tests**

Create `slidecraft/tests/test_km_place_design.py`:

```python
"""Stage-2 persist: km place-design extracts + sanitizes + places a designer
reply and promotes the slide when the last section lands (design §6)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _md, _add_image_nugget


def _place(deck: Path, sid: str, role: str, stype: str, reply: str, asset=None):
    f = deck / f"reply-{role}.txt"
    f.write_text(reply, encoding="utf-8")
    km.cmd_place_design(deck, Namespace(slide=sid, section=role, type=stype,
                                        file=str(f), asset=asset))


def test_place_text_strips_fence_and_swaps_wireframe(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "define", "title": "T",
        "sections": {"body": {"type": "text", "instructions": "prose",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()

    _place(deck, sid, "body", "text",
           "```markdown\n- point one\n- point two\n```")
    out = json.loads(capsys.readouterr().out)

    md = _md(deck, sid)
    assert "- point one" in md and "```" not in md   # fence stripped
    assert "pending" not in md                        # wireframe gone
    assert out["status"] == "placed"
    assert out["slide_state"] == "composed"           # last (only) section landed
    assert km.load_state(deck, sid)["plan"]["sections"]["body"]["status"] == "placed"


def test_place_diagram_writes_sfc_and_sanitizes_icons(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "T",
        "sections": {"body": {"type": "diagram", "instructions": "flow",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()

    reply = ("```vue\n<template><div><carbon-not-a-real-icon/>"
             "<carbon-arrow-right/></div></template>\n```")
    _place(deck, sid, "body", "diagram", reply)

    sfc = (deck / "components" / f"Sec_{sid}_body.vue")
    assert sfc.exists()
    text = sfc.read_text(encoding="utf-8")
    assert "carbon-not-a-real-icon" not in text        # hallucinated icon replaced
    assert "carbon-arrow-right" in text                # allowlisted icon kept
    md = _md(deck, sid)
    assert f"<Sec_{sid}_body" in md


def test_place_diagram_inline_component_is_placed_verbatim(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "T",
        "sections": {"body": {"type": "diagram", "instructions": "flow",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    reply = "<FlowDiagram>\n\n- Capture | in\n- Estimate | out\n\n</FlowDiagram>"
    _place(deck, sid, "body", "diagram", reply)
    md = _md(deck, sid)
    assert "<FlowDiagram>" in md and "Capture | in" in md
    assert not (deck / "components" / f"Sec_{sid}_body.vue").exists()  # no SFC file


def test_place_image_places_img_from_asset(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "finding", "title": "T",
        "sections": {"body": {"type": "image", "instructions": "render",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    (deck / "public" / "gen").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "gen" / f"{sid}_body.png").write_bytes(b"\x89PNG")
    _place(deck, sid, "body", "image", "ignored reply text",
           asset=f"/gen/{sid}_body.png")
    md = _md(deck, sid)
    assert f"/gen/{sid}_body.png" in md


def test_partial_placement_leaves_slide_planned(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="a.", page=1)
    _add_nugget(deck, "n2", raw_text="b.", page=1)
    sid = _create(deck, "T", nuggets="n1,n2")
    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare", "title": "T",
        "sections": {
            "left": {"type": "text", "instructions": "l", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "r", "nuggets": ["n2"]}}})
    capsys.readouterr()
    _place(deck, sid, "left", "text", "- only left")
    out = json.loads(capsys.readouterr().out)
    assert out["slide_state"] == "planned"             # right still pending
```

- [ ] **Step 2: Create the starter icon allowlist**

Create `slidecraft/references/icon-allowlist.txt` (one icon name per line; the shipped components' own icons + a small common set — extendable):

```text
carbon-arrow-right
carbon-arrow-down
carbon-arrow-up
carbon-arrow-left
carbon-circle-solid
carbon-checkmark
carbon-close
carbon-warning
carbon-idea
carbon-data-base
carbon-analytics
carbon-settings
carbon-flow
carbon-tree-view
ph-arrow-right
ph-arrow-down
ph-circle-fill
ph-check
```

- [ ] **Step 3: Run to verify the tests fail**

Run: `python -m pytest slidecraft/tests/test_km_place_design.py -v`
Expected: FAIL — `AttributeError: … 'cmd_place_design'`.

- [ ] **Step 4: Implement icon-sanitize + extraction + `cmd_place_design` in `km.py`**

```python
ICON_ALLOWLIST_FILE = (Path(__file__).resolve().parent.parent
                       / "references" / "icon-allowlist.txt")
ICON_FALLBACK = "carbon-circle-solid"
# Iconify-style icon components: <collection-name/> or <collection:name/>,
# collection is a known short code. Kebab or colon form, self-closing or paired.
_ICON_TAG_RE = re.compile(
    r"<((?:carbon|ph|mdi|tabler|ic|bi|fa|fa6-solid|lucide|material-symbols)"
    r"[-:][a-z0-9-]+)\s*/?>", re.I)


def _load_icon_allowlist() -> set[str]:
    if not ICON_ALLOWLIST_FILE.exists():
        return set()
    return {ln.strip().replace(":", "-").lower()
            for ln in ICON_ALLOWLIST_FILE.read_text(encoding="utf-8-sig").splitlines()
            if ln.strip() and not ln.startswith("#")}


def sanitize_icons(markup: str) -> str:
    """Replace any Iconify icon component whose name is not allow-listed with a
    safe fallback, so a hallucinated icon never crashes the Vite transform. The
    component library forbids hand-drawn objects → real icon + label, and this
    guarantees the 'real' part deterministically."""
    allow = _load_icon_allowlist()

    def repl(m):
        name = m.group(1).replace(":", "-").lower()
        return m.group(0) if name in allow else f"<{ICON_FALLBACK}/>"
    return _ICON_TAG_RE.sub(repl, markup)


_VUE_FENCE_RE = re.compile(r"```vue[ \t]*\n(.*?)```", re.S | re.I)
_ANY_FENCE_RE = re.compile(r"```[a-zA-Z]*[ \t]*\n(.*?)```", re.S)


def _strip_fence(text: str) -> str:
    """Return the last fenced block's contents if the reply is fenced, else the
    whole (trimmed) reply — a designer may or may not fence its output."""
    fences = _ANY_FENCE_RE.findall(text)
    return (fences[-1] if fences else text).strip()


def cmd_place_design(root: Path, a):
    """Stage-2 persist (§6): deterministically extract + place ONE designer's
    reply into its content area, sanitize (diagram), swap the wireframe, update
    the section status, and promote the slide to `composed` when the last
    pending section lands. Network-free: an image reply is already downloaded
    (--asset). Rejection = exit 1 (retryable)."""
    sid, role, stype = a.slide, a.section, a.type
    sp = root / "slides" / f"{sid}.md"
    stj = load_state(root, sid)
    plan = stj.get("plan") or {}
    sec = (plan.get("sections") or {}).get(role)
    if not sec:
        gate_exit(f"ERROR: slide {sid} has no planned section {role!r}")
    physical = plan["layout"]
    entry = next((e for e in ctx(root)["theme"]["capabilities"]["layouts"]
                  if e["name"] == physical), {})
    slot = (entry.get("roles") or {}).get(role)

    if stype == "image":
        if not a.asset:
            gate_exit("ERROR: place-design --type image requires --asset")
        block = f'<img src="{a.asset}" alt="{plan.get("title", sid)}">'
    else:
        reply = Path(a.file).read_text(encoding="utf-8-sig")
        content = _strip_fence(reply)
        if not content.strip():
            sys.exit("ERROR: designer returned empty content")   # exit 1: retry
        if stype == "diagram":
            content = sanitize_icons(content)
            # A full SFC (has <template>) is written to a component file; an
            # inline component invocation is placed verbatim.
            if "<template" in content.lower():
                comp = f"Sec_{slugify(sid).replace('-', '')}_{role}"
                # keep the sid readable in the tag: use the raw sid form.
                comp = f"Sec_{sid}_{role}"
                (root / "components").mkdir(exist_ok=True)
                (root / "components" / f"{comp}.vue").write_text(
                    content if content.lstrip().startswith("<")
                    else content, encoding="utf-8")
                block = f"<{comp} />"
            else:
                block = content
        else:  # text
            block = content

    # Swap the wireframe placeholder in the slot for the real block.
    md = sp.read_text(encoding="utf-8-sig")
    md = _replace_slot_body(md, slot, block) if slot else _append_block(md, block)
    for asset in missing_assets(root, md):
        sys.exit(f"ERROR: referenced asset '{asset}' does not exist "
                 f"(expected under public/: public{asset})")
    sp.write_text(md, encoding="utf-8")

    sec["status"] = "placed"
    if all(s.get("status") in ("placed", "failed")
           for s in plan["sections"].values()):
        stj["state"] = "composed"
    save_state(root, sid, stj)
    log(root, "km", "place-design", slide=sid, section=role, type=stype,
        slide_state=stj["state"])
    print(json.dumps({"ok": True, "slide": sid, "section": role,
                      "status": "placed", "slide_state": stj["state"]}))


def _replace_slot_body(md: str, slot: str, block: str) -> str:
    """Replace the body of a `::slot::` region (up to the next `::` or EOF)
    with `block`. The wireframe placeholder written by write-skeleton is the
    current body; this swaps it for the designer's result."""
    pattern = re.compile(rf"(::{re.escape(slot)}::\n)(.*?)(?=\n::|\Z)", re.S)
    if not pattern.search(md):
        return md.rstrip() + f"\n\n::{slot}::\n{block}\n"
    return pattern.sub(lambda m: m.group(1) + block + "\n", md, count=1)


def _append_block(md: str, block: str) -> str:
    return md.rstrip() + f"\n\n{block}\n"
```

> **Cleanup note:** delete the dead first `comp = f"Sec_{slugify(...)}"` assignment — the final `comp = f"Sec_{sid}_{role}"` is authoritative (kept readable). It is shown above only to flag the intent; keep just the second line.

Register in `main()`:

```python
    pd = sub.add_parser("place-design"); pd.add_argument("--slide", required=True); pd.add_argument("--section", required=True); pd.add_argument("--type", required=True, choices=["text", "diagram", "image"]); pd.add_argument("--file", required=True); pd.add_argument("--asset", default=None)
```
```python
     "place-design": cmd_place_design,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_place_design.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Run all km tests for regressions**

Run: `python -m pytest slidecraft/tests/ -k "km" -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/references/icon-allowlist.txt slidecraft/tests/test_km_place_design.py
git commit -m "feat(km): place-design extracts/sanitizes/places designer output, promotes slide (D9)"
```

---

## Task 9: Register the three designer roles in the invoke shim

The designers need executor config (default models, per-deck overridable) so `design_section.py` can resolve their executors. Designers return **raw** content, not JSON, so they never go through `run_role`'s `parse_structured` — but they DO use `resolve_executor_spec` + `build_executor`. Register them in `ROLES` with a terminal and default executor.

**Files:**
- Modify: `slidecraft/scripts/invoke_shim.py` — add three entries to `ROLES`
- Test: `slidecraft/tests/test_invoke_shim.py` (add resolve tests)

**Interfaces:**
- Produces: `invoke_shim.ROLES` gains `text-designer`, `diagram-designer`, `image-designer` with `terminal: "drop"` (a failed area leaves its wireframe — see §10) and default executors per the Global Constraints. `resolve_executor_spec(role, deck)` works for all three; `deck-context.json`'s `executors` block overrides them.

- [ ] **Step 1: Write the failing tests**

Add to `slidecraft/tests/test_invoke_shim.py`:

```python
import json
from pathlib import Path
from slidecraft.scripts import invoke_shim


def test_designer_roles_have_default_executors():
    for role in ("text-designer", "diagram-designer", "image-designer"):
        assert role in invoke_shim.ROLES
    assert invoke_shim.DEFAULT_EXECUTORS["text-designer"]["model"] == "gdpr.gpt-5.6-sol"
    assert invoke_shim.DEFAULT_EXECUTORS["diagram-designer"]["model"] == "gdpr.gpt-5.6-sol"
    assert invoke_shim.DEFAULT_EXECUTORS["image-designer"]["model"] == "nano-banana-pro"


def test_deck_overrides_designer_model(tmp_path):
    ctx = tmp_path / "deck-context.json"
    ctx.write_text(json.dumps({"executors": {
        "image-designer": {"executor": "owui", "model": "some-other-image-model"}}}),
        encoding="utf-8")
    spec = invoke_shim.resolve_executor_spec("image-designer", tmp_path)
    assert spec["model"] == "some-other-image-model"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_invoke_shim.py -k designer -v`
Expected: FAIL — `KeyError`/`ValueError: unknown role 'text-designer'`.

- [ ] **Step 3: Add the roles to `ROLES` in `invoke_shim.py`**

In the `ROLES` dict (after the `storyteller` entry, ~line 89):

```python
    "text-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "diagram-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "image-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "nano-banana-pro"},
    },
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_invoke_shim.py -k designer -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/invoke_shim.py slidecraft/tests/test_invoke_shim.py
git commit -m "feat(shim): register text/diagram/image designer roles + default executors (D7)"
```

---

## Task 10: Durable prompt + response logging (§7.1)

Every OWUI call is logged under the deck's `logs/prompts/`, grouped per slide, cross-referenced from `logs/actions.jsonl`. Add an `on_attempt` hook to `run_role` (so retries are logged too), a reusable `log_prompt_record` helper, and `--slide` / `--section` / `--run-label` flags to `invoke_shim.main`.

**Files:**
- Modify: `slidecraft/scripts/invoke_shim.py` — add `log_prompt_record`, `run_role(on_attempt=…)`, new CLI flags, wire logging in `main`
- Test: `slidecraft/tests/test_invoke_shim.py` (add logging tests)

**Interfaces:**
- Produces:
  - `invoke_shim.log_prompt_record(deck, *, slide, section, role, model, executor, attempt, status, prompt, response, run_label) -> Path` — writes `logs/prompts/<slide>/<seq>-<role>[-<section>]-<model>.json` (seq zero-padded, ordered within the slide) and appends a reference line to `logs/actions.jsonl` (`action: "prompt-log"`, carrying the record's relative path). `slide` defaults to `_deckwide` when absent.
  - `run_role(..., on_attempt: Callable[[str, str, int], None] | None = None)` — called once per attempt with `(prompt, raw, attempt)` (before persist), so every attempt including retries is captured.
  - `invoke_shim.main` accepts `--slide`, `--section`, `--run-label`; logs each attempt via `on_attempt`.

- [ ] **Step 1: Write the failing tests**

Add to `slidecraft/tests/test_invoke_shim.py`:

```python
def test_run_role_calls_on_attempt_for_every_attempt(tmp_path):
    # A persist that rejects once then accepts → 2 attempts → 2 on_attempt calls.
    calls = []

    class FakeExec:
        supports_image = False
        def __init__(self): self.i = 0
        def run(self, prompt, image=None):
            self.i += 1
            return json.dumps({"n": self.i})

    state = {"first": True}
    def persist(out):
        if state["first"]:
            state["first"] = False
            raise invoke_shim.PersistRejection("try again")

    res = invoke_shim.run_role(
        "knowledge-miner", "BRIEF", persist=persist, executor=FakeExec(),
        on_attempt=lambda prompt, raw, attempt: calls.append((attempt, raw)))
    assert res.status == "ok"
    assert [a for a, _ in calls] == [1, 2]           # both attempts logged


def test_log_prompt_record_writes_per_slide_and_actions_ref(tmp_path):
    deck = tmp_path
    (deck / "deck-context.json").write_text("{}", encoding="utf-8")
    rec = invoke_shim.log_prompt_record(
        deck, slide="slide-1", section="left", role="text-designer",
        model="m", executor="owui", attempt=1, status="ok",
        prompt="P", response="R", run_label="run-A")
    assert rec.exists() and rec.parent.name == "slide-1"
    data = json.loads(rec.read_text(encoding="utf-8"))
    assert data["prompt"] == "P" and data["response"] == "R"
    assert data["run_label"] == "run-A" and data["section"] == "left"
    actions = (deck / "logs" / "actions.jsonl").read_text(encoding="utf-8")
    assert "prompt-log" in actions and "slide-1" in actions
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_invoke_shim.py -k "on_attempt or log_prompt" -v`
Expected: FAIL — `TypeError: run_role() got an unexpected keyword argument 'on_attempt'` / `AttributeError: log_prompt_record`.

- [ ] **Step 3: Implement in `invoke_shim.py`**

Add the helper (near the top, after imports):

```python
import time


def log_prompt_record(deck, *, slide, section, role, model, executor,
                      attempt, status, prompt, response, run_label=None):
    """Write one durable prompt/response record under the deck's
    logs/prompts/<slide>/ and append a reference to logs/actions.jsonl (§7.1).
    Returns the record path. Best-effort: a locked/synced log never raises."""
    from pathlib import Path as _Path
    deck = _Path(deck)
    slide_key = slide or "_deckwide"
    pdir = deck / "logs" / "prompts" / slide_key
    pdir.mkdir(parents=True, exist_ok=True)
    seq = len(list(pdir.glob("*.json"))) + 1
    parts = [f"{seq:03d}", role]
    if section:
        parts.append(section)
    if model:
        parts.append(str(model).replace("/", "-").replace(":", "-"))
    rec_path = pdir / ("-".join(parts) + ".json")
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "slide": slide_key,
              "section": section, "role": role, "model": model,
              "executor": executor, "attempt": attempt, "status": status,
              "run_label": run_label, "prompt": prompt, "response": response}
    rec_path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    try:
        logdir = deck / "logs"
        logdir.mkdir(exist_ok=True)
        with (logdir / "actions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": record["ts"], "agent": "invoke-shim",
                "action": "prompt-log", "role": role, "slide": slide_key,
                "section": section, "attempt": attempt, "status": status,
                "record": str(rec_path.relative_to(deck)).replace("\\", "/"),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return rec_path
```

Extend `run_role` (change the signature + call the hook each attempt):

```python
def run_role(role, brief, *, persist, executor, image=None,
             retry_cap=RETRY_CAP, on_attempt=None):
    ...
    for attempt in range(1, retry_cap + 2):
        try:
            raw = executor.run(prompt, image=image)
        except Exception as exc:
            errors.append(f"executor failure: {exc}")
            if on_attempt:
                on_attempt(prompt, f"<executor failure: {exc}>", attempt)
            return InvokeResult(role=role, status="error", attempts=attempt,
                                errors=errors)
        if on_attempt:
            on_attempt(prompt, raw, attempt)
        try:
            output = parse_structured(raw)
            persist(output)
        ...
```

(Keep the rest of `run_role` unchanged; only the signature, the two `on_attempt(...)` calls, and nothing else.)

In `main`, add the flags after `--out`:

```python
    ap.add_argument("--slide", help="slide id (prompt-log grouping)")
    ap.add_argument("--section", help="section role (designer prompt-log)")
    ap.add_argument("--run-label", dest="run_label",
                    help="optional label to tag this run's prompt records")
```

and wire the hook into the `run_role` call inside `main` (replacing the plain call):

```python
    def _on_attempt(prompt, raw, attempt):
        if a.deck:
            log_prompt_record(
                a.deck, slide=a.slide, section=a.section, role=a.role,
                model=spec.get("model"), executor=spec.get("executor"),
                attempt=attempt, status="attempt", prompt=prompt,
                response=raw, run_label=a.run_label)

    with tempfile.TemporaryDirectory(prefix="invoke-shim-") as tmp:
        result = run_role(
            a.role, brief,
            persist=_persist_via_command(persist_argv, Path(tmp)),
            executor=executor, image=a.image, on_attempt=_on_attempt)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_invoke_shim.py -k "on_attempt or log_prompt" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the whole shim suite for regressions**

Run: `python -m pytest slidecraft/tests/test_invoke_shim.py -q`
Expected: PASS (the added `on_attempt` param is optional; existing calls unaffected).

- [ ] **Step 6: Commit**

```bash
git add slidecraft/scripts/invoke_shim.py slidecraft/tests/test_invoke_shim.py
git commit -m "feat(shim): durable per-slide prompt/response logging + on_attempt hook (D16)"
```

---

## Task 11: `design_section.py` — the atomic expert unit

One seam that builds one content area end-to-end: `km design-brief` → OWUI (the designer's executor) → (`image` only: download the reply to `public/gen/…`) → `km place-design`. Idempotent and independently runnable — this is what a human-in-the-loop calls to re-generate one image or redo one diagram. Logs every attempt (Task 10).

**Files:**
- Create: `slidecraft/scripts/design_section.py`
- Test: `slidecraft/tests/test_design_section.py` (new)

**Interfaces:**
- Consumes: `km.py` CLI (`design-brief`, `place-design`), `invoke_shim.resolve_executor_spec`, `build_executor`, `log_prompt_record`.
- Produces:
  - `design_section.download_image(reply: str, dest: Path) -> Path` — write the image from a `data:` URI, a markdown `![](url)` link, or a bare URL (URL fetch via `requests`); raises `ValueError` on an unrecognizable reply.
  - `design_section.design_one(deck: Path, slide: str, section: str, *, run_label=None, retry=2) -> dict` — runs the full seam; returns `{"ok": bool, "slide", "section", "type", "status": "placed"|"failed", "attempts", "errors"}`. On exhaustion it leaves the wireframe (marks section failed via `place-design` is NOT called; see §10) and returns `status: "failed"`.
  - CLI: `python design_section.py --deck D --slide S --section R [--run-label L]`.

- [ ] **Step 1: Write the failing tests (fake executor)**

Create `slidecraft/tests/test_design_section.py`:

```python
"""design_section.py — the atomic expert unit (design §7): design-brief → OWUI
→ (image: download) → place-design, with per-attempt logging."""
from __future__ import annotations

import base64
import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km, design_section
from slidecraft.tests.conftest import wire_fake_executor
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _md, _add_image_nugget


def test_download_image_from_data_uri(tmp_path):
    raw = base64.b64encode(b"\x89PNG-bytes").decode()
    reply = f"data:image/png;base64,{raw}"
    dest = design_section.download_image(reply, tmp_path / "out.png")
    assert dest.exists() and dest.read_bytes() == b"\x89PNG-bytes"


def test_design_one_text_section_places_and_promotes(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "define", "title": "T",
        "sections": {"body": {"type": "text", "instructions": "prose",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    wire_fake_executor(deck, tmp_path, "text-designer", ["- built point"])

    res = design_section.design_one(deck, sid, "body")
    assert res["status"] == "placed"
    assert "- built point" in _md(deck, sid)
    assert km.load_state(deck, sid)["state"] == "composed"


def test_design_one_image_downloads_and_places(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "finding", "title": "T",
        "sections": {"body": {"type": "image", "instructions": "render",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    raw = base64.b64encode(b"\x89PNGgen").decode()
    wire_fake_executor(deck, tmp_path, "image-designer",
                       [f"data:image/png;base64,{raw}"], image_arg=False)

    res = design_section.design_one(deck, sid, "body")
    assert res["status"] == "placed"
    assert (deck / "public" / "gen" / f"{sid}_body.png").exists()
    assert f"/gen/{sid}_body.png" in _md(deck, sid)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_design_section.py -v`
Expected: FAIL — `ModuleNotFoundError: … design_section` / `AttributeError`.

- [ ] **Step 3: Implement `slidecraft/scripts/design_section.py`**

```python
#!/usr/bin/env python
"""The atomic expert unit (design §7): build ONE content area of a slide.

  km design-brief  →  the designer's OWUI executor  →  (image: download)  →
  km place-design

Idempotent and independently runnable — the human-in-the-loop re-generates a
single image / redoes a single diagram by re-running this. Every attempt's
prompt + response is logged under the deck's logs/prompts/ (§7.1). The script
owns the OWUI loop (D7); the lead never hand-loops a designer.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from slidecraft.scripts import invoke_shim

KM = str(Path(__file__).resolve().parent / "km.py")

_DATA_URI_RE = re.compile(r"data:(image/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)", re.I)
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((\S+?)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")


def download_image(reply: str, dest: Path) -> Path:
    """Write an image from a designer reply: a data: URI, a markdown ![](url)
    link, or a bare URL. Raises ValueError when nothing image-like is found."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    m = _DATA_URI_RE.search(reply)
    if m:
        dest.write_bytes(base64.b64decode(re.sub(r"\s+", "", m.group(2))))
        return dest
    url_m = _MD_IMG_RE.search(reply) or _BARE_URL_RE.search(reply)
    if url_m:
        import requests
        url = url_m.group(1) if url_m.re is _MD_IMG_RE else url_m.group(0)
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    raise ValueError("designer reply carried no data URI, markdown image, or URL")


def _run_km(deck: Path, *args) -> dict:
    proc = subprocess.run([sys.executable, KM, "--deck", str(deck), *args],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip()
                           or f"km {args[0]} exited {proc.returncode}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def design_one(deck: Path, slide: str, section: str, *, run_label=None,
               retry: int = 2) -> dict:
    """Build one content area end-to-end. Returns a status dict; on exhaustion
    leaves the wireframe visible and returns status 'failed' (§10)."""
    deck = Path(deck)
    with tempfile.TemporaryDirectory(prefix="design-") as td:
        tmp = Path(td)
        brief_out = tmp / "brief.md"
        info = _run_km(deck, "design-brief", "--slide", slide,
                       "--section", section, "--out", str(brief_out))
        stype, role = info["type"], info["role"]
        brief = brief_out.read_text(encoding="utf-8-sig")
        spec = invoke_shim.resolve_executor_spec(role, deck)
        executor = invoke_shim.build_executor(spec)

        errors = []
        for attempt in range(1, retry + 2):
            try:
                reply = executor.run(brief, image=None)
            except Exception as exc:                       # transport/infra
                errors.append(f"executor failure: {exc}")
                invoke_shim.log_prompt_record(
                    deck, slide=slide, section=section, role=role,
                    model=spec.get("model"), executor=spec.get("executor"),
                    attempt=attempt, status="error", prompt=brief,
                    response=f"<{exc}>", run_label=run_label)
                break
            invoke_shim.log_prompt_record(
                deck, slide=slide, section=section, role=role,
                model=spec.get("model"), executor=spec.get("executor"),
                attempt=attempt, status="attempt", prompt=brief,
                response=reply, run_label=run_label)
            reply_file = tmp / "reply.txt"
            reply_file.write_text(reply, encoding="utf-8")
            place = ["place-design", "--slide", slide, "--section", section,
                     "--type", stype, "--file", str(reply_file)]
            try:
                if stype == "image":
                    ext = "png"
                    asset_rel = f"/gen/{slide}_{section}.{ext}"
                    download_image(reply, deck / "public" / "gen"
                                   / f"{slide}_{section}.{ext}")
                    place += ["--asset", asset_rel]
                out = _run_km(deck, *place)
                return {"ok": True, "slide": slide, "section": section,
                        "type": stype, "status": "placed",
                        "attempts": attempt, "errors": errors,
                        "slide_state": out.get("slide_state")}
            except (RuntimeError, ValueError) as exc:      # retryable placement
                errors.append(str(exc))
                continue
        return {"ok": False, "slide": slide, "section": section, "type": stype,
                "status": "failed", "attempts": retry + 1, "errors": errors}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slide", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--run-label", dest="run_label", default=None)
    a = ap.parse_args(argv)
    res = design_one(Path(a.deck), a.slide, a.section, run_label=a.run_label)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_design_section.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/design_section.py slidecraft/tests/test_design_section.py
git commit -m "feat(scripts): design_section.py — atomic per-area expert unit (D9)"
```

---

## Task 12: `compose_deck.py` — the batch driver

Enumerate the to-compose set; per slide run `km compose-brief` → the planner via the invoke shim → `km write-skeleton` (structural slides stop here); per pending section run `design_section.design_one` concurrently (bounded pool); emit a JSON report. Scope flags (`--slide` / `--section`) make the batch path and the interactive-redo path the same code.

**Files:**
- Create: `slidecraft/scripts/compose_deck.py`
- Test: `slidecraft/tests/test_compose_deck.py` (new)

**Interfaces:**
- Consumes: `km.py` CLI (`compose-brief`, `write-skeleton`, `park-slide`, `load_state`, `order`, `parked_ids`, `needs_composition`), `invoke_shim.main` (composer invoke with prompt logging), `design_section.design_one`.
- Produces:
  - `compose_deck.to_compose_set(deck: Path) -> list[str]` — active, unlocked slides whose state ∈ `{draft, pending, planned}` (i.e. not yet `composed`/`locked`/`parked`), in deck order.
  - `compose_deck.compose_deck(deck, *, slide=None, section=None, run_label=None, max_workers=4) -> dict` — the report: `{"composed": [...], "parked": [...], "failed_sections": [...], "figure_needed": [...], "run_label": ...}`.
  - CLI: `python compose_deck.py --deck D [--slide S] [--section R] [--run-label L]`.

- [ ] **Step 1: Write the failing test (fake executor, planner + designers)**

Create `slidecraft/tests/test_compose_deck.py`:

```python
"""compose_deck.py — the batch driver (design §7): plan every to-compose slide,
then build each pending section concurrently, to a green deck."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km, compose_deck
from slidecraft.tests.conftest import wire_fake_executor
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _md


def test_compose_deck_plans_then_builds_sections(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left verbatim.", page=1)
    _add_nugget(deck, "n2", raw_text="Right verbatim.", page=1)
    sid = _create(deck, "Compare SLA and FDM", nuggets="n1,n2")
    capsys.readouterr()

    # Planner returns a two-section plan (both text); both designers return prose.
    plan = json.dumps({
        "layout": "two-cols", "concept_type": "compare",
        "title": "SLA präziser, FDM günstiger",
        "sections": {
            "left": {"type": "text", "instructions": "table", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "prose", "nuggets": ["n2"]}}})
    wire_fake_executor(deck, tmp_path, "slide-composer", [plan])
    wire_fake_executor(deck, tmp_path, "text-designer",
                       ["- left built", "- right built"])

    report = compose_deck.compose_deck(deck, run_label="run-A", max_workers=2)

    assert sid in report["composed"]
    assert report["parked"] == [] and report["failed_sections"] == []
    md = _md(deck, sid)
    assert "left built" in md and "right built" in md
    assert km.load_state(deck, sid)["state"] == "composed"


def test_compose_deck_structural_slide_stops_after_skeleton(deck, tmp_path, capsys):
    sid = _create(deck, "Object Tracking", nuggets="")     # structural
    capsys.readouterr()
    plan = json.dumps({"layout": "content", "concept_type": "structural",
                       "title": "Object Tracking", "sections": {}})
    wire_fake_executor(deck, tmp_path, "slide-composer", [plan])

    report = compose_deck.compose_deck(deck, max_workers=2)
    assert sid in report["composed"]
    assert km.load_state(deck, sid)["state"] == "composed"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest slidecraft/tests/test_compose_deck.py -v`
Expected: FAIL — `ModuleNotFoundError: … compose_deck`.

- [ ] **Step 3: Implement `slidecraft/scripts/compose_deck.py`**

```python
#!/usr/bin/env python
"""The batch driver (design §7): plan every to-compose slide, then build each
pending content section concurrently. Scope flags (--slide/--section) make the
batch path and the interactive-redo path the same code.

  per to-compose slide:
    km compose-brief  →  invoke_shim(slide-composer)  →  km write-skeleton
  per pending section (concurrent):
    design_section.design_one   (design-brief → OWUI → [image: download] → place)

The lead launches THIS and reads its report; it never hand-loops OWUI (D7).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from slidecraft.scripts import invoke_shim, km, design_section

KM = str(Path(km.__file__))
SHIM = str(Path(invoke_shim.__file__))


def to_compose_set(deck: Path) -> list[str]:
    """Active, unlocked slides not yet composed, in deck order."""
    out = []
    for sid in km.order(deck):
        stj = km.load_state(deck, sid)
        if stj.get("state") in ("locked", "composed", "parked"):
            continue
        out.append(sid)
    return out


def _plan_slide(deck: Path, sid: str, scratch: Path, run_label) -> dict:
    """compose-brief → planner invoke → write-skeleton. Returns write-skeleton's
    JSON (pending_sections), or {} and parks the slide on the planner terminal."""
    brief = scratch / f"plan-{sid}.md"
    subprocess.run([sys.executable, KM, "--deck", str(deck), "compose-brief",
                    "--slide", sid, "--out", str(brief)],
                   check=True, capture_output=True, text=True, encoding="utf-8")
    result = scratch / f"plan-{sid}.result.json"
    rc = subprocess.run(
        [sys.executable, SHIM, "--role", "slide-composer",
         "--brief-file", str(brief), "--deck", str(deck), "--slide", sid,
         *(["--run-label", run_label] if run_label else []),
         "--out", str(result), "--",
         sys.executable, KM, "--deck", str(deck), "write-skeleton",
         "--slide", sid, "--file", "{out}"],
        capture_output=True, text=True, encoding="utf-8").returncode
    if rc != 0:                                    # planner terminal → park
        subprocess.run([sys.executable, KM, "--deck", str(deck), "park-slide",
                        "--slide", sid, "--reason",
                        "planning failed after retries"],
                       capture_output=True, text=True, encoding="utf-8")
        return {}
    # write-skeleton wrote the sidecar; read pending sections from state.
    plan = km.load_state(deck, sid).get("plan") or {}
    pending = [r for r, s in (plan.get("sections") or {}).items()
               if s.get("status") == "pending"]
    return {"pending_sections": pending}


def compose_deck(deck, *, slide=None, section=None, run_label=None,
                 max_workers=4) -> dict:
    deck = Path(deck)
    report = {"composed": [], "parked": [], "failed_sections": [],
              "figure_needed": [], "run_label": run_label}
    with tempfile.TemporaryDirectory(prefix="compose-deck-") as td:
        scratch = Path(td)
        slides = [slide] if slide else to_compose_set(deck)
        # Stage 1: plan every slide (writes wireframes; places source-image).
        pending_by_slide: dict[str, list[str]] = {}
        for sid in slides:
            if km.load_state(deck, sid).get("state") == "parked":
                continue
            res = _plan_slide(deck, sid, scratch, run_label)
            if not res:
                report["parked"].append(sid)
                continue
            secs = [section] if section else res["pending_sections"]
            pending_by_slide[sid] = secs

        # Stage 2: build every pending section concurrently (bounded).
        jobs = [(sid, sec) for sid, secs in pending_by_slide.items()
                for sec in secs]
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(design_section.design_one, deck, sid, sec,
                                   run_label=run_label): (sid, sec)
                       for sid, sec in jobs}
            for fut in futures:
                sid, sec = futures[fut]
                try:
                    r = fut.result()
                except Exception as exc:               # never crash the batch
                    r = {"status": "failed", "errors": [str(exc)]}
                if r.get("status") != "placed":
                    report["failed_sections"].append(
                        {"slide": sid, "section": sec, "errors": r.get("errors")})

        # Finalize: a slide with all sections placed is composed.
        for sid in pending_by_slide:
            st = km.load_state(deck, sid).get("state")
            if st == "composed":
                report["composed"].append(sid)
        # Structural slides (no pending sections) are already composed.
        for sid in slides:
            if (sid not in report["composed"] and sid not in report["parked"]
                    and km.load_state(deck, sid).get("state") == "composed"):
                report["composed"].append(sid)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slide", default=None)
    ap.add_argument("--section", default=None)
    ap.add_argument("--run-label", dest="run_label", default=None)
    ap.add_argument("--max-workers", dest="max_workers", type=int, default=4)
    a = ap.parse_args(argv)
    report = compose_deck(Path(a.deck), slide=a.slide, section=a.section,
                          run_label=a.run_label, max_workers=a.max_workers)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_compose_deck.py -v`
Expected: PASS (2 passed).

> If `test_compose_deck_structural_slide_stops_after_skeleton` fails because a structural slide's `write-skeleton` already set state `composed` (no pending sections) but the slide was not in `pending_by_slide`, confirm the "Structural slides … already composed" finalize loop catches it. Adjust the finalize logic so any slide the driver planned that is now `composed` lands in `report["composed"]` exactly once.

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/compose_deck.py slidecraft/tests/test_compose_deck.py
git commit -m "feat(scripts): compose_deck.py — batch two-stage driver (D7/D9)"
```

---

## Task 13: ADR-0005 — two-stage composition

Record the architectural decision (D1–D17) in a short ADR, mirroring the ADR-0004 format, noting ADR-0001 still governs assembly.

**Files:**
- Create: `docs/adr/0005-two-stage-composition.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Write the ADR**

Create `docs/adr/0005-two-stage-composition.md`:

```markdown
# Slide composition is two-stage: a planner routes, specialist designers build

One LLM call no longer composes a whole slide. A **planner** (the former
`slide-composer`, rewritten) decides the slide's didactic function, core message,
assertion title, layout, and — per content area — a `type` (`text` / `diagram` /
`image` / `source-image`), natural-language `instructions`, and the routed nugget
ids. Three **specialist designers** (text/table, diagram-in-Vue, image-generation)
each build one area from that brief plus the full slide raw material. Deterministic
glue (`km write-skeleton` / `km place-design`, driven by `compose_deck.py` +
`design_section.py`) validates the plan, renders a visible wireframe, places
`source-image` areas, fans the designer calls to OWUI, and stitches each result
back — with **no LLM inside any assembly step** (ADR-0001, strengthened).

Status: accepted (2026-07-22, D1–D17). Replaces the monolithic single-stage
composer path; `write-slide`'s content-slide role is superseded by
`write-skeleton` + `place-design`.

## Considered options

- **Hard medium lanes** (route each area to a fixed medium) — rejected (D2):
  faithfulness is earned by rich per-area briefs + exact-text discipline, not by
  restricting the composer's medium choice.
- **The planner names the diagram component** — rejected (D15): the planner
  describes the diagram in natural language; the diagram designer selects the
  component from a catalog generated from per-component `<catalog>` metadata (D14),
  so add/remove a component auto-syncs the prompt.
- **A hand-maintained component catalog** — rejected (D14): the catalog is
  extracted from each `.vue`'s `<catalog>` block, the single source of truth.

## Consequences

- **Heterogeneous slides** (a source figure beside a Vue decision tree) are built
  by experts; a visible wireframe renders the instant `write-skeleton` runs, and
  each area fills in as its designer lands (free live-preview progress).
- **Per-area re-generation** is the same code as the batch path (scope flags on
  `compose_deck.py` / `design_section.py`) — the human-in-the-loop seam.
- **Every prompt + response is logged** under the deck's `logs/prompts/<slide>/`
  and cross-referenced from `logs/actions.jsonl` (D16), so a deck's creation can be
  reconstructed, debugged, or re-run against another model.
- **Scripts own every OWUI call** (D7); the lead launches `compose_deck.py` and
  reads its report — it never hand-loops OWUI.
```

- [ ] **Step 2: Commit**

```bash
git add docs/adr/0005-two-stage-composition.md
git commit -m "docs(adr): 0005 two-stage composition (D1–D17)"
```

---

## Task 14: Swap the orchestration to the driver + auto-chain, and prove it end-to-end

Point `/draft-deck` §4 at `compose_deck.py`, note the convert→mine auto-chain, and rewrite the integration test so the **two-stage** pipeline reaches a green `validate` with a fake executor. This is the capstone: it verifies plan → skeleton → designers → placement → validate as one flow.

**Files:**
- Modify: `slidecraft/commands/draft-deck.md` (replace §4 hand-loop with the driver)
- Modify: `slidecraft/commands/init-deck.md` (note: convert runs after scaffold; nuggets exist before planning — D8)
- Modify: `slidecraft/tests/test_draft_deck_integration.py` (drive the two-stage compose path)

**Interfaces:**
- Consumes: `compose_deck.compose_deck`, all prior tasks.
- Produces: a green `validate` over a deck composed by the two-stage pipeline; the `/draft-deck` doc reflects the driver.

- [ ] **Step 1: Rewrite integration §4 in the test harness (failing)**

In `slidecraft/tests/test_draft_deck_integration.py`, replace the per-step `compose(sid)` (which calls `compose-brief` → `write-slide`) with a two-stage path driven by `compose_deck`. Concretely:

- After the plan executes the `create`/`merge` steps (which now leave slides in state `draft`/`pending`, NOT composed), call `compose_deck.compose_deck(deck, run_label="test", max_workers=2)` once, and fold its report into the run report (`parked`, `failed_sections`).
- Wire fake executors for `slide-composer` (planner plans) **and** `text-designer` / `diagram-designer` / `image-designer` (area builds), in addition to the miners/storyteller. Replace the canned `COVER`/`CONTENT`/`FIGURE`/`CLOSING` composer JSON with **planner** plan JSON per slide and designer replies per section.

Update the canned outputs. Example planner + designer set for the happy path (`_full_plan`):

```python
# Planner plans (one per to-compose slide, in compose order).
PLAN_COVER = json.dumps({"layout": "content", "concept_type": "structural",
                         "title": "Object Tracking", "sections": {}})
PLAN_CORE = json.dumps({
    "layout": "content", "concept_type": "define",
    "title": "Tracking estimates state",
    "sections": {"body": {"type": "text", "instructions": "define it",
                          "nuggets": ["<t1>", "<t2>"]}}})   # ids filled at build time
PLAN_FIGURE = json.dumps({
    "layout": "content", "concept_type": "process", "title": "The tracking loop",
    "sections": {"body": {"type": "source-image",
                          "instructions": "place the loop figure",
                          "nuggets": ["<img1>"]}}})
PLAN_SUMMARY = json.dumps({"layout": "content", "concept_type": "structural",
                           "title": "Summary", "sections": {}})
# Designer replies (text area builds; source-image needs none).
DESIGN_CORE_BODY = "- estimate state over time\n- from measurements"
```

Because the plan JSON must reference the **real** just-mined nugget ids, build the planner responses inside the existing `build(deck, by_kind)` callback (it already receives `by_kind`), substituting the ids (mirror how `_full_plan` builds the storyteller plan). Wire the planner + designer fakes from `build`'s return value, extending the `{"plan", "composer"}` contract to `{"plan", "planner": [...], "text_designer": [...], ...}` (rename `composer`).

- [ ] **Step 2: Run to verify the integration test fails**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -v`
Expected: FAIL — the harness still calls `write-slide`, and/or the fake executors for the designer roles are not wired.

- [ ] **Step 3: Update the harness compose step to use `compose_deck`**

Replace the `def compose(sid): …` block and the per-step `compose(sid)` calls in `draft_deck(...)` with a single post-plan driver call:

```python
    from slidecraft.scripts import compose_deck as _cd
    # (fake executors for slide-composer + the three *-designer roles are wired
    #  from build()'s return, alongside the miner/storyteller fakes.)
    cd_report = _cd.compose_deck(deck, run_label="test", max_workers=2)
    report["parked"].extend(cd_report["parked"])
    report["failed_sections"] = cd_report["failed_sections"]
```

Keep the `create`/`associate`/`merge`/`park`/`unpark` step execution exactly as-is (they still run first and leave slides needing composition). Ensure `km.cmd_create` no longer triggers an immediate compose in the harness (the driver composes).

- [ ] **Step 4: Adjust the happy-path assertions**

Update `test_full_draft_reaches_green_validate` assertions for the new physical output: the content slide now carries the **designer's** placed text in its slot (not the old composer's `::heading::`/`body`), and the figure slide places the real asset from a `source-image` section. Replace the `"::heading::" in content_md` assertion with a check that the built text (`estimate state over time`) is in the slot, and keep `IMG_ASSET in figure_md`. Presenter-notes verbatim fill (D39) is not part of the designer path in v1 — drop or relax the `RAW_1 in content_md` note assertion accordingly (note this in the plan's deferred list).

- [ ] **Step 5: Run the full integration test to green**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -v`
Expected: PASS — including the delta re-run, the planner-abort, and the designer-failure-flagged cases (adapt `test_composer_park_terminal_keeps_deck_green` into a `test_designer_failure_is_flagged` using a designer reply that stays empty every attempt, and `test_storyteller_abort_composes_nothing` unchanged).

- [ ] **Step 6: Rewrite `/draft-deck` §4 in the command doc**

In `slidecraft/commands/draft-deck.md`, replace the entire "## 4. Execute the plan + compose" section's per-slide `compose-brief` → `invoke_shim` → `write-slide` loop with the driver. New §4 body:

````markdown
## 4. Execute the plan + compose (two-stage)

Read `plan.json`'s `steps` and run them **in order** (`create-slide` / `associate-nuggets` /
`merge-slides` / `park-slide` / `unpark-slide`) exactly as before — but do **not** compose
per-create. Creating/merging a content slide leaves it needing composition.

Then run the batch driver **once**; it owns all planner + designer OWUI calls (D7):

```
python "<COMPOSE>" --deck <deck> --run-label <run>
```

`<COMPOSE>` = `<toolkit>/slidecraft/scripts/compose_deck.py`. For each to-compose slide it
runs `km compose-brief` → the planner (invoke shim) → `km write-skeleton` (validates the plan,
renders a visible wireframe, places `source-image` areas); then it builds every pending
content section concurrently via `design_section.py` (`km design-brief` → the area's designer
→ `km place-design`). A wireframe renders the instant a slide is planned and each area fills in
as its designer lands — free live-preview progress.

Read the driver's JSON report: `composed` / `parked` (a slide whose planner exhausted) /
`failed_sections` (an area whose designer exhausted — its wireframe stays visible, flagged) /
`figure_needed`. To **re-generate one area** (human-in-the-loop), run the same driver scoped:
`python "<COMPOSE>" --deck <deck> --slide <sid> --section <role>`.
````

Add `<COMPOSE>` to the shorthands list in the doc header (near `<SERVE>`).

- [ ] **Step 7: Note the auto-chain in `init-deck.md`**

In `slidecraft/commands/init-deck.md`, add a short line after scaffolding that convert runs so nuggets exist before planning (D8):

```markdown
After scaffolding, `/init-deck` runs the deterministic **convert** over any files already in
`input/` (convert → mine happens in `/draft-deck`, so nuggets exist before planning). Dropping
new inputs later and re-running `/draft-deck` picks them up (delta behavior).
```

> **Deferred / confirm (D8):** the literal "convert auto-triggers mine" is realized by `/draft-deck`'s existing convert→mine→plan ordering, not by `source_converter.py` invoking a miner (mining is an LLM seam and must stay behind the shim). If the intent is for `source_converter` itself to chain into mining, raise it before implementing — it would move an LLM call into the deterministic converter, which ADR-0001 forbids. This plan keeps the chain in the orchestrator.

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest slidecraft/tests/ -q`
Expected: PASS (all green).

- [ ] **Step 9: Commit**

```bash
git add slidecraft/commands/draft-deck.md slidecraft/commands/init-deck.md slidecraft/tests/test_draft_deck_integration.py
git commit -m "feat(orchestration): /draft-deck uses compose_deck driver; two-stage integration green (D7/D8)"
```

---

## Self-Review

**Spec coverage** (each design section → task):

- §2 D1 replace composer with planner → Task 4. D2 free medium choice → planner template (Task 4) + no lanes in `place-design`. D3 plan JSON → Task 4/5. D4 layout scope → Task 5 (`content_roles_for`, `offered_layouts`). D5 type-not-role → Tasks 5/7/8. D6 source-image vs image → Task 5 (placement) + Task 4 (prefer source-image). D7 driver owns OWUI → Tasks 11/12. D8 auto-chain → Task 14 (+ flagged). D9 script cut (apply + expert unit + batch driver) → Tasks 5/8/11/12. D10 placeholders → all template tasks + Task 1. D11 title top-level, nuggets per section → Tasks 4/5. D12 extra context deferred → not built (noted). D13 designers get full raw material → Task 7 (`%RAW-MATERIAL%`). D14 dynamic catalog → Tasks 2/3. D15 planner describes, designer selects → Tasks 4/6. D16 prompt logging → Task 10. D17 aspect ratio → Tasks 5/7 (`aspect_ratio_for`).
- §4 plan contract + validation → Task 5. §5.1–5.4 templates → Tasks 4/6. §5.5 catalog → Tasks 2/3. §6 km surface (compose-brief/write-skeleton/design-brief/place-design + state machine) → Tasks 4/5/7/8. §7 scripts + transport + logging → Tasks 9/10/11/12. §8 orchestration + auto-chain → Task 14. §9 faithfulness guard → Tasks 6 (prompts) + 8 (place-design deterministic guards). §10 failure handling → Task 12 (planner park), Task 11 (designer failed leaves wireframe). §11 testing → every task's tests + Task 14 integration. §12 files touched → all tasks. §13 open questions → captured in Deferred below.

**Placeholder scan:** no "TBD"/"add error handling"/"similar to Task N" — every step carries real code or real prose. The one intentional flag is the D8 auto-chain (Task 14 Step 7), surfaced as a confirm-before-implement item rather than a silent guess.

**Type consistency:** `content_roles_for(entry)`, `aspect_ratio_for(role)`, `validate_plan(root, sid, obj, c) -> (entry, sections)`, `_designer_role_for(stype)`, `sanitize_icons(markup)`, `download_image(reply, dest)`, `design_one(deck, slide, section, *, run_label, retry)`, `compose_deck(deck, *, slide, section, run_label, max_workers)`, `log_prompt_record(deck, *, slide, section, role, model, executor, attempt, status, prompt, response, run_label)` — names/signatures used identically across Tasks 5/7/8/10/11/12/14. The plan sidecar shape (`stj["plan"]["sections"][role] = {type, instructions, nuggets, status}`) is written in Task 5 and read in Tasks 7/8/12 consistently.

## Deferred (from spec §13, out of v1 core)

- **Render-critic** per-section verify pass; **extra context blocks** (per-nugget digests, sibling-section awareness, deck topic/position); **image-split / prop-based image layouts**; **grids beyond single/two-column**; a per-area **aspect-ratio field** in `semantic-layouts.json` (the layout→ratio mapping is a `km` rule, D17).
- **`%EXACT-TEXT%` sourcing** is v1-minimal (image nuggets' `visible_text`); richer extraction from text nuggets is a later refinement.
- **Presenter-notes verbatim fill (D39)** is not wired into the two-stage path in v1 (Task 14 relaxes the note assertion); decide whether `place-design`/`write-skeleton` should append verbatim notes as `write-slide` did.
- **`write-slide` retirement:** kept in `km.py` for compatibility (no longer called by the driver); remove in a later cleanup once nothing references it.
- **D8 literal auto-chain** (convert→mine inside the converter) — confirm intent (see Task 14 Step 7); ADR-0001 keeps mining behind the shim.
- **Icon allowlist** ships as a starter set (Task 8); expand it as designers surface real icon needs.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-22-two-stage-composer.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
