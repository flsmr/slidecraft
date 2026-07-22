# Two-stage slide composition — composer plans, specialist designers build

**Status:** design (brainstorm output, pending review)
**Date:** 2026-07-22
**Supersedes:** the monolithic single-stage composer path (D42/D43 output contract; `slide-composer` as a content writer). ADR-0001 (deterministic assembly) still holds and is *strengthened*.

---

## 1. Motivation

Today one LLM call composes a whole slide: `slide-composer` reads a self-contained brief and returns semantic role-keyed JSON (`content: {role → markdown}`), which `km write-slide` maps to physical slots. The composer both *decides* the slide (didactics, layout, message) **and** *writes* every word, including any diagram markup.

This feature splits those two jobs:

- a **composer/planner** decides the didactic function, the core message, the layout, and — per content area — *what goes there*, *which specialist builds it*, and *which knowledge nuggets feed it*; it writes no visible body content except the title;
- three **specialist designers** each build one content area from the planner's instructions plus the routed nuggets: **text/table**, **diagram** (Vue), **image** (generation);
- deterministic **glue scripts** apply the layout, render a visible skeleton, fan the designer calls out to OWUI, and stitch each result back into its area — with **no LLM in the assembly** (ADR-0001).

The payoff: heterogeneous slides (e.g. a source figure on the left, a Vue decision-tree on the right) composed by experts, a visible intermediate "wireframe" for progress, and per-area re-generation for human-in-the-loop polishing.

## 2. Decisions locked in brainstorming

| # | Decision |
|---|---|
| D1 | **Replace** the production composer. The two-stage system becomes `/draft-deck`'s default compose path; `slide-composer.md` becomes the planner. |
| D2 | **Composer free choice** of medium per area — no hard lanes. Faithfulness is earned by rich per-area briefs + the exact-text discipline, not by restricting image-gen. |
| D3 | Composer output = a **plan JSON**: `layout`, `concept_type`, `title`, and `sections{role → {type, instructions, nuggets}}`. |
| D4 | **Roles are the layout's content areas.** Scope now = single-column (`title`,`body`) and two-column (`title`,`left`,`right`). No image-split / prop-based image layouts. |
| D5 | Medium is the **`type`**, not a role: `text \| diagram \| image \| source-image`. An image fills a normal area via its type. |
| D6 | `source-image` = **place** a real extracted figure (asset resolved from the routed figure nugget); **no OWUI call**. `image` = **generate** (nano-banana-pro). Placing is preferred; the composer chooses. |
| D7 | **A driver script owns every OWUI call.** The lead (Claude) launches drivers and reads reports; it never hand-loops OWUI. |
| D8 | **Auto-chain backward:** the deck command triggers convert; convert auto-triggers mine. Nuggets exist before planning. |
| D9 | **Script cut = option B:** a deterministic apply step + independent per-section expert units + a batch driver that reuses them (scope flags). |
| D10 | **Every prompt input is a named placeholder.** `km` computes values only; templates own all prose + ordering. Optional inputs resolve to `""`. |
| D11 | Title is a top-level field (composer writes it); nuggets are assigned **per section**. |
| D12 | Extra context (per-nugget digests, sibling-section awareness, deck topic/position) is **deferred** to a later stage. |
| D13 | **All designers also receive the full slide raw material** (`%RAW-MATERIAL%`) as context, in addition to their section's routed `%NUGGETS%`. |
| D14 | **The diagram catalog is generated dynamically from per-component metadata** baked into each `.vue` (custom `<catalog>` block; sidecar fallback). Add/remove a component ⇒ the prompt auto-syncs. Each entry: `use` / `looks` / `fill`. |
| D15 | **The composer describes a diagram in natural language** — the concept type + exactly what to show — and does **not** name a component; the diagram designer selects it from the catalog. |
| D16 | **Every composed prompt + response is logged durably** under the deck's `logs/prompts/`, grouped per slide by filename and cross-referenced from the chronological `logs/actions.jsonl`, with an optional `run_label` for model comparison. |
| D17 | **The image designer is told the target aspect ratio** (`%ASPECT-RATIO%`), restricted to **1:1** or **16:9** and derived by `km` from the layout + area: single-column `body` → 16:9; two-column `left`/`right` → 1:1. Generate-only (a placed `source-image` keeps its own ratio). |

## 3. Architecture

```
create-deck ──▶ convert ──▶ mine ──▶ plan ──▶ compose_deck.py ──▶ validate
(init-deck)    (auto)      (auto)   (story-   │
                                    teller)   │  per to-compose slide:
                                              ├─ km compose-brief
                                              ├─ invoke_shim(slide-composer) ─ OWUI ─▶ plan JSON
                                              ├─ km write-skeleton   (layout + wireframe + place source-image)
                                              └─ per pending section (concurrent):
                                                   design_section.py
                                                     ├─ km design-brief   (assemble expert prompt)
                                                     ├─ OWUI (text/diagram/image model)
                                                     └─ km place-design    (stitch into the slot)
```

- **Stage 1 (plan):** one OWUI call per slide → the plan JSON. Persisted; renders a wireframe immediately.
- **Stage 2 (build):** one OWUI call per non-`source-image` section, fanned out concurrently; each result stitched into its area as it lands. `source-image` sections are placed by the deterministic apply step — no call.
- **Glue:** `km write-skeleton` / `km place-design` do all physical Slidev assembly (ADR-0001). The scripts own the OWUI loop (D7); the lead only launches `compose_deck.py` and reads its report.

## 4. Composer output contract (plan JSON)

```json
{
  "layout": "two-cols",
  "concept_type": "compare",
  "title": "SLA ist präziser, FDM skaliert günstiger",
  "sections": {
    "left":  { "type": "source-image", "instructions": "Referenzfoto des SLA-Bauteils.", "nuggets": ["n0021"] },
    "right": { "type": "diagram", "instructions": "Ein Entscheidungsbaum zur Wahl des Fertigungsverfahrens: Ausgangsknoten 'Feine Details nötig?' verzweigt zu SLA (ja) bzw. zur Folgefrage 'Hohe Stückzahl?'; diese verzweigt zu FDM (ja) und zu SLA (nein). Kriterien als Entscheidungsknoten, Verfahren (SLA/FDM) als Endknoten, kurze Begründung an jeder Kante.", "nuggets": ["n0007","n0011"] }
  }
}
```

**Fields**

- `layout` — one of the **offered** layout names for scope now: `content` (single column) or `two-cols`. Validated against `offered_layouts(ctx)`.
- `concept_type` — one of `structural | motivate | define | compare | relationship | process | cause-effect | finding | categories | claim-support` (the existing `CONCEPT_TYPES`).
- `title` — the assertion title string. Written directly by the planner (no designer round-trip).
- `sections` — keyed by the layout's **content-area roles** (`body` for single-column; `left`/`right` for two-column). Omitted roles fall back to the layout's defaults. `title` is **not** a section (it's the top-level field).

**Section object** (uniform for all four types):

- `type` — `text | diagram | image | source-image`.
- `instructions` — the composer's brief for that area (fills `%INSTRUCTIONS%`). For `source-image` it doubles as alt/caption context.
- `nuggets` — the nugget ids whose material feeds this area (the composer's didactic routing). For `source-image` the list must include a **figure nugget** (carries `asset`); the glue resolves the asset from it — the plan never carries a raw path.

**Validation (`km write-skeleton`, all `Rejection` = retryable):** layout ∈ offered; `concept_type` ∈ enum; every section key ∈ the layout's content roles; `type` ∈ the four values; `source-image` sections route at least one figure nugget whose asset exists under `public/`; `nuggets` ids exist and are associated with the slide.

**Structural slides bypass this contract** (D-note): cover / section-divider / closing slides have no content areas — `write-skeleton` composes them from `title` + layout defaults + deck metadata, no `sections`, no designer calls.

## 5. The four prompt templates

All are fully-placeholdered (D10). `km`'s assemble subcommands compute every value; `render_template` already fails loudly on an unresolved `%X%`.

> **Placeholder naming fix:** the leftover-guard regex is `%[A-Z][A-Z-]*%` (hyphens, no underscores). Widen it to `%[A-Z][A-Z_-]*%` and standardize new names hyphen-style regardless, so a typo like `%DECK_TYPE%` can never slip the guard.

### 5.1 Composer / planner (`agents/slide-composer.md`, rewritten)

**Owns:** didactic function, core message, assertion title, layout choice, per-area routing (type + instructions + nuggets), and the **density budget** (how much each area should carry). Writes no body content.

**Placeholders:** `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%STYLE-CONTRACT%` `%WORKING-TITLE%` `%SLIDE-TYPE%` `%INTENDED-FUNCTION%` `%RAW-MATERIAL%` `%FIGURE-BLOCK%` `%LAYOUTS%` `%DECK-METADATA%` (optional ones resolve to `""`).

**Output:** the plan JSON of §4, nothing else.

**Craft rules carried over from the current composer** (retained, re-pointed at *planning*): one main teaching message; assertion title 3–7 words; density budget (≤2–3 content areas, ~30–85 visible words total, ≤2 hierarchy levels) — now expressed as *guidance to the designers* via `instructions`, and enforced by *how much* the planner routes to each area; pick the visual shape before the words (choose the area `type` from the purpose: comparison→table; sequence/flow→diagram; one big number→hero text; pictorial→`source-image`/`image`); make relationships explicit; preserve academic precision and concept roles (enabler/mechanism/outcome). **Prefer `source-image` over `image`** when a routed figure fits.

**Diagram instructions must be elaborate (D15).** For a `diagram` area the composer writes a *natural-language* brief — *what kind* of diagram (the identified concept type) **and** *exactly what it should show* (nodes, branches, direction, labels, relationships) — but never names a component; the diagram designer selects the component from the catalog. Pattern: *"Ein &lt;Diagrammtyp&gt;, der &lt;Konzept&gt; abbildet: &lt;konkrete Elemente, Verzweigungen, Beschriftungen&gt;."* (see the §4 example) — not a terse fragment.

### 5.2 Text / table designer (`agents/text-designer.md`, new)

**Owns:** local writing craft for one area — prose, lists, and tables — bound to its nuggets' provenance.

**Placeholders:** `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%STYLE-CONTRACT%` `%CORE-MESSAGE%` `%SECTION-ROLE%` `%INSTRUCTIONS%` `%NUGGETS%` `%RAW-MATERIAL%`.

**Output:** Markdown for the area only (prose / list / **table**) — no title, no frontmatter, no code fence required. Decides prose-vs-table from the instruction. Compress by abstraction, not truncation; every claim traces to `%NUGGETS%`.

### 5.3 Diagram designer (`agents/diagram-designer.md`, new)

**Owns:** on-style structural visuals for one area.

**Placeholders:** `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%STYLE-CONTRACT%` `%CORE-MESSAGE%` `%SECTION-ROLE%` `%INSTRUCTIONS%` `%NUGGETS%` `%RAW-MATERIAL%` `%COMPONENT-CATALOG%`. `%COMPONENT-CATALOG%` is generated dynamically from per-component metadata — see §5.5.

**Output — one of:**
- a **component invocation** using the shipped library (`<DecisionTree>` / `<FlowDiagram>` / `<TwoColumnCompare>` …) with a nested markdown bullet list or props (the readable, editable, on-style-by-construction path — **preferred when a component fits**); or
- a **self-contained Slidev Vue SFC** (freestyle) in a single ```vue block, content-area only, when no component fits.

**House rules** (from the validated prototype build prompts): structure + icons, **never hand-drawn depicted objects** — fall back to a real Carbon/Phosphor icon + label; one shared arrowhead marker; equal-sized aligned boxes for peers; palette from theme tokens; min 14px; fills its container, no overflow. Only real icon names (icon-sanitize runs at placement).

### 5.4 Image designer (`agents/image-designer.md`, new — `generate` only)

**Owns:** faithful pictorial rendering for one area.

**Placeholders:** `%AUDIENCE%` `%DECK-TYPE%` `%LANGUAGE%` `%CORE-MESSAGE%` `%SECTION-ROLE%` `%INSTRUCTIONS%` `%NUGGETS%` `%RAW-MATERIAL%` `%EXACT-TEXT%` `%ASPECT-RATIO%`.

**Output:** one image (nano-banana-pro), **at exactly `%ASPECT-RATIO%`** (`1:1` or `16:9` only — the ratios the model is tuned for). Content-area only, pure-white canvas, **every label rendered verbatim from `%EXACT-TEXT%`** (the discipline that made diffusion faithful in the bake-off), exact numeric values only. `design_section.py` downloads the reply and places it.

### 5.5 Component catalog (dynamic, single source of truth)

`%COMPONENT-CATALOG%` is **not hand-maintained.** Each diagram component in `slidecraft/components/*.vue` carries its own catalog metadata, and `km` extracts + renders the list at brief-assembly time — so **adding or removing a component automatically adds or removes it from the diagram designer's prompt** (D14).

**Embedding.** A custom SFC block at the top of each component (Vite ignores unknown custom blocks, so it never affects the Slidev build):

```vue
<catalog>
use: Linear process or pipeline with one clear direction of flow.
looks: Left-to-right boxes joined by single arrows.
fill: bullet list; each top-level item is a step, "title | short description".
</catalog>
```

Three fields per component: **`use`** — when to choose it (one line, the routing hint); **`looks`** — one-line description of the resulting figure; **`fill`** — how to author it from a markdown bullet list (the nested-list idiom the components `README` already tabulates centrally — this moves it per-file). The component **name** is the filename. Prop-only components (charts, `Swimlane`, `MatrixQuadrant`, `VennDiagram`) describe their data shape in `fill` instead of a list idiom.

**Extraction.** `km`'s `component_catalog(root)` scans the deck theme's `components/` junction, parses each `<catalog>` block, and renders `%COMPONENT-CATALOG%` as a compact table (`name · use · looks · fill`). A component missing the block is listed name-only and flagged so its metadata gets backfilled. **Sidecar fallback:** `components/<Name>.catalog.yaml` for any component that cannot host the block (none currently).

## 6. Knowledge-manager surface + slide state

**Plan sidecar.** The plan is stored in the slide's state file `slides/<sid>.json` under `plan`, with a per-section `status` (`pending | placed | failed`), so `design-brief`/`place-design` can read each section independently and the driver can resume.

**Slide state machine:** `pending → planned → composed` (plus existing `parked` / `locked`). `write-skeleton` sets `planned` (and places `source-image` sections → `status: placed`); `place-design` flips a section to `placed`/`failed`; the slide promotes to `composed` when no section is still `pending`.

**New / changed subcommands:**

- `compose-brief --slide S --out B` *(adapted)* — assembles the **planner** brief (§5.1 template + all placeholder values). Slide-type routing (`text-only`/`image-text`/`structural`) drives which optional blocks are non-empty.
- `write-skeleton --slide S --file PLAN` *(new, persist for the planner)* — validates the plan (§4), writes `slides/<sid>.md`: frontmatter `layout: <physical>` + `title`, and each content role's `::slot::` holding a **wireframe placeholder** (`<!-- TYPE · pending -->` + the instruction as a blockquote). Places every `source-image` section as an `<img>` from its figure nugget's asset. Persists the plan sidecar. Returns the list of sections still needing a designer.
- `design-brief --slide S --section R --out B` *(new, assemble)* — reads the plan sidecar; renders the matching designer template (§5.2–5.4) with `%INSTRUCTIONS%`, the routed nuggets' `raw_text` as `%NUGGETS%`, the **full slide raw material** (every associated nugget's `raw_text`) as `%RAW-MATERIAL%` (D13), `%CORE-MESSAGE%` = the plan title, plus type-specific values (`%COMPONENT-CATALOG%` for diagram — built by `component_catalog()` from the components' metadata, §5.5; `%EXACT-TEXT%` + `%ASPECT-RATIO%` for image, the ratio derived from the layout + area per D17 — `body` → `16:9`, `left`/`right` → `1:1`).
- `place-design --slide S --section R --type T --file REPLY [--asset PATH]` *(new, persist)* — deterministic extraction + placement + validation:
  - `text` → strip an optional fence, place Markdown into the slot;
  - `diagram` → extract the component invocation or the ```vue SFC; **icon-sanitize**; if an SFC, write `components/Sec_<sid>_<role>.vue` and place `<Sec… />`, else place the inline component markdown;
  - `image` → place `<img src="/gen/…">` from `--asset` (already downloaded by the caller — `km` stays network-free);
  - swaps the wireframe placeholder for the result, re-runs the asset checker, updates section status, promotes the slide when done.

`write-slide` is retired for content slides (superseded by `write-skeleton` + `place-design`); it may remain for structural slides or be folded into `write-skeleton`'s structural path.

## 7. Scripts — transport reuse + the two drivers

**Transport reuse.** `invoke_shim` stays the single transport home. The **composer** goes through `run_role` unchanged (JSON output → persist via `km write-skeleton`). The **designers return raw content** (Markdown / Vue / an image), not JSON, so they use a raw path rather than `parse_structured`:

- register `text-designer` / `diagram-designer` / `image-designer` in the executor-spec registry so `deck-context.json`'s `executors` block can override their models (default: text/diagram = `gdpr.gpt-5.6-sol`; image = `nano-banana-pro`);
- `design_section.py` builds the executor via `resolve_executor_spec` + `build_executor`, runs a small retry loop on empty/inextractable replies, and — for `image` — downloads the reply to `public/gen/<sid>_<role>.<ext>` (the prototype's `download_image`: data-URI / markdown link / bare URL).

**`design_section.py --deck D --slide S --section R`** — the atomic expert unit (one seam): `km design-brief` → OWUI → (`image`: download) → `km place-design`. Idempotent and **independently runnable** — this is what the human-in-the-loop invokes to *re-generate this image / redo this diagram* without recomposing the slide.

**`compose_deck.py --deck D [--slide S] [--section R]`** — the batch driver:
1. enumerate the **to-compose set** — slides that are unlocked and `pending`/`needs_compose` (or the scoped `--slide`);
2. per slide: `km compose-brief` → `invoke_shim --role slide-composer -- km write-skeleton` (structural slides stop here);
3. per pending section: run `design_section.py` **concurrently** (bounded pool);
4. emit a JSON report: composed / parked slides, per-section `placed`/`failed`, unresolved `FIGURE NEEDED`.

Scope flags make the batch path and the interactive-redo path the *same code*.

### 7.1 Prompt & response logging (D16)

Every OWUI call is logged durably under the deck's **`logs/prompts/`**, so a deck's creation can be reconstructed, debugged, or re-run against a different model.

**Captured per call:** the exact prompt sent (the assembled brief — and, on a retry, the error-appended variant), the raw response, and meta: `role`, `slide`, `section` (designers), `model`, `executor`, `attempt`, `status`, timestamp, and an optional `run_label`. For an `image` call the "response" is the reply text (URL / base64 marker) plus the saved asset path under `public/gen/`.

**Association — both ways:**
- **By name:** records are grouped per slide — `logs/prompts/<slide_id>/<seq>-<role>[-<section>]-<model>.json` (`seq` zero-padded, ordered within the slide) — so every prompt behind one slide sits together.
- **Chronologically:** each record is referenced from the existing append-only `logs/actions.jsonl` (the entry carries the record's relative path), so the whole run replays in order and any prompt is one hop away.

**Wiring:** at the transport callers, which know the context — `invoke_shim.main` (composer; also miners / storyteller) and `design_section.py` (designers). `run_role` gains an optional `on_attempt(prompt, raw, attempt)` callback so **every** attempt (including retries) is logged, not just the last. `invoke_shim` and `design_section` take optional `--slide` / `--section` / `--run-label` flags to populate the meta + path; `compose_deck.py` passes one `run_label` per run.

**Model comparison:** because a record holds the exact prompt + model + response, re-running a logged prompt against another model and diffing the output is a thin helper on top (natural extension; not v1 core). Logs live in the deck (not the toolkit) and follow the existing `logs/` gitignore.

## 8. Orchestration & auto-chain

- **`/init-deck` (create-deck)** triggers `convert` after scaffolding; **`convert`** auto-triggers `mine` (D8) — so by planning time the nuggets exist. A re-run picks up newly-added `input/` files (existing delta behavior).
- **`/draft-deck` §4 changes:** replace the per-slide hand-loop (`compose-brief` → `invoke_shim` → `write-slide`) with a single `compose_deck.py --deck <deck>` run; read its report. Mining/planning may keep their current lead-driven seams for now, or move to drivers later (out of scope here).
- **Live preview:** the wireframe renders the instant `write-skeleton` runs; each area fills in as its designer lands — the progress signal, for free, via the existing live-preview server.

## 9. Faithfulness guard

Free medium choice (D2) puts the weight on the briefs, not lanes:

- **text / diagram designers** are bound to their section's nuggets — the same provenance discipline the monolithic composer had, localized; prompt-enforced.
- **image designer** renders **only** the `%EXACT-TEXT%` list (no invented labels/numbers).
- **`place-design`** enforces the deterministic guarantees: assets exist under `public/`, icons sanitized, non-empty output, no unknown asset references.
- A per-section **render-critic** verify pass is a natural later add; **deferred** from v1 core.

## 10. Failure handling

- **planner exhausted/error** → **park** the slide (existing composer terminal), flagged in the report.
- **designer exhausted/error** → leave the wireframe **placeholder** visible, mark the section `failed`, flag it; siblings and the rest of the deck are unaffected (the slide still renders).
- **`source-image` asset missing** → `write-skeleton` rejection (planner re-invoke) or a report flag if it only surfaces at placement.

## 11. Testing

- `km` unit tests: `write-skeleton` (validation, wireframe output, source-image placement, sidecar, structural bypass), `design-brief` (placeholder resolution, no leaked physical slots), `place-design` (per-type extraction: fence strip / Vue extract + icon-sanitize / `<img>`; placeholder swap; status/promotion).
- `design_section.py` + `compose_deck.py` integration with the **fake executor** to a green `validate` (extend `test_draft_deck_integration.py`).
- Prompt logging (§7.1): a call writes a per-slide record under `logs/prompts/<slide>/` and an `actions.jsonl` reference; a retried call produces one record per attempt; the `run_label` is threaded through.
- Regression: the leftover-placeholder guard still fires; offered names never leak physical slots.

## 12. Files touched

- `agents/slide-composer.md` — rewrite to the planner contract (§5.1).
- `agents/text-designer.md`, `agents/diagram-designer.md`, `agents/image-designer.md` — new (§5.2–5.4).
- `scripts/km.py` — adapt `compose-brief`; add `write-skeleton` / `design-brief` / `place-design` / `component_catalog()`; plan sidecar + state; widen the placeholder regex; retire/fold `write-slide` for content slides.
- `components/*.vue` — backfill a `<catalog>` metadata block (`use` / `looks` / `fill`) into each diagram component (§5.5); update the `README` to point at the per-file metadata as the source of truth.
- `scripts/invoke_shim.py` — register the three designer roles for executor config; add the `run_role` `on_attempt` logging hook and `--slide` / `--section` / `--run-label` flags; write per-call prompt records + `actions.jsonl` references (§7.1).
- `scripts/design_section.py`, `scripts/compose_deck.py` — new; both log prompts/responses to `logs/prompts/` (§7.1); `compose_deck.py` mints one `run_label` per run.
- `commands/draft-deck.md` — swap §4 to the driver; `commands/init-deck.md` + `scripts/source_converter.py` — convert→mine auto-chain.
- `deck-context.json` executors defaults (designer models).
- `docs/adr/0005-two-stage-composition.md` — new ADR (records D1–D16; ADR-0001 still governs assembly).
- tests as in §11.

## 13. Open questions / deferred

- **Structural slides bypass** the designer pipeline (§4) — assumed; confirm.
- **Diagram designer** prefers a catalog component, freestyle SFC as fallback — decided (D14/D15; reinforced by the dynamic catalog, §5.5).
- **Component metadata embedding** — the plan is a custom `<catalog>` SFC block (Vite ignores unknown blocks); verify during implementation that it is inert in the Slidev build; `components/<Name>.catalog.yaml` sidecar is the fallback.
- **Deferred to a later stage:** render-critic; extra context blocks (digests, sibling-section awareness, deck topic/position); image-split / prop-based image layouts; richer multi-area grids beyond single/two-column; a per-area **aspect-ratio field** in `semantic-layouts.json` (the layout→ratio mapping is a `km` rule for now, D17).
