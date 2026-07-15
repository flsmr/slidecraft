# Slidecraft Workflow Design

The agreed end-to-end design of the slidecraft user workflow, settled in a grilled design session
on 2026-07-04/05. Each decision carries its *why*. This is the durable record; change it only by
revisiting the decision, not by drift.

> **2026-07-07 modularization session (see `/CONTEXT.md` + `/docs/adr/`):** decisions 4, 5, 11 and
> 13 are superseded/refined by the THEME-PACK model: a theme pack repo = the visuals-only theme
> package + `skeletons/` (self-contained deck structures in the theme's physical names —
> ADR-0001). Skeletons configure the canonical workflows only through fixed extension points
> (ADR-0002). The new-deck interview (theme -> skeleton -> slide opt-outs -> skeleton decision
> points) replaces the type-collection bootstrap; registered pack links live in user-local
> config. Decks remain independent artifacts, now with full provenance in recipe.json.

---

## The 15 decisions

### Identity

**1. Eventually public / open-source.** Everything IU-specific (ILSE theme, iu-sprint type, OWUI
config) stays private. The public product ships a general LECTURE deck type as reference.
*Why: the tool's shape generalizes beyond IU; but IU material is licensed/internal.*

**2. Generalize by extraction, not up-front.** The remaining IU decks ship first on the working
pipeline; a piece is promoted to general/documented only after proving itself on real decks.
Public release is the final milestone. *Why: speculative generality already failed once (the
May CIF machinery); battle-tested extraction is mechanical and safe.*

### Core model

**3. One front door.** New deck → pick a **deck type** → type-specific interview → pipeline runs.
Deck types are the template concept; the generic authoring path is the fallback type.
*Why: three parallel entry paths (authoring skill, sprint-deck, hand-built) confuse users and
fork conventions.*

**4. A deck type is a declarative folder; one generic engine runs all types.**

```
deck-types/<name>/
  type.json         # recipe schema + interview + enrichment toggles + theme reference
  skeleton.md       # fixed scaffolding slides with {{placeholders}}
  author-guide.md   # house style + slot templates handed to authors
  prompts/          # author.md, critic.md, mindmap.md, ... ({{placeholders}})
  (workflow.js)     # optional override; absent = generic engine
```

Users create types by copy + edit — no code. *Why: "build your own deck type" is the extension
mechanism of a public tool; code as the barrier kills it.*

**5. Each type binds ONE theme, by reference.** `type.json` names the theme (npm name or git URL);
scaffold resolves/installs it. Themes remain independent `slidev-theme-*` repos; several types can
share one theme without drift. *Why: skeleton + guide must be written in physical slot names (the
May lesson: semantic aliases do not render in Slidev); theme-agnostic projection machinery is
deferred until a second theme genuinely forces it.*

**6. The recipe holds everything variable; interview = derive first, confirm second.** Extraction
runs *before* any question; the user gets ONE pre-filled confirmation round (checkboxes + short
edits) covering only judgment calls; answers persist to a hand-editable, re-runnable `recipe.json`.
The interview never asks what the sources can answer. *Why: in SPRINT_3 the section list, page
ranges and figures were all derived from the TOC automatically; asking would be absurd.*

### Build & improve

**7. The confirm round is the only checkpoint.** After it the build is fully autonomous: live
progress tree (Workflow tool) while running, DONE report at the end, review afterward.
*Why: chosen explicitly (review-at-end over checkpoints); the confirm round IS plan approval.*

**8. Per-slide files.** `slides/<descriptive-name>.md` per slide + `slides.md` as an ordered
`src:`-import manifest (the authoring skill's existing convention, now unified). *Why: tweaks
become clean single-file edits with history; parallel agents cannot collide; SPRINT_1's ~30
iterations were fragile string surgery on a 70KB monolith.*

**9. Improve loop: tweak phrases + improve-deck passes.** A tweak invocation is itself the
approval; passes auto-apply high/medium-confidence fixes and only *suggest* the rest.
*Why: approve-fatigue defeats review; the user reviews exceptions, not every action.*

**10. Image backends live OUTSIDE the repo.** The repo holds only the calling convention
(`OWUI_SKILL_DIR` discovery + graceful skip when absent + a DONE-report flag). The OWUI client is
a machine-local implementation (`~/.claude/skills/owui/` with a private `.env`), one of possibly
several backends later; a pluggable interface is a public-milestone extraction. *Why: the client
only works on specific machines and its config is personal; decks must still build with zero
image backend (mind map skipped, galleries are Wikimedia and public-safe).*

### Distribution

**11. Deck types are distributed as TYPE COLLECTIONS: one repo holds 1..n deck types.**
A collection repo has a `deck-types/` folder with one or more type folders. The private IU
collection holds `iu-sprint` (later `iu-casestudy`, ...) versioned together; the public starter
collection holds `lecture`. *Why (amended from one-repo-per-type): multiple related types must
stay in sync; one collection repo = one clone, one history.*

**12. Prompts live in the type folder; output schemas stay in the engine.** A type customizes
what agents are told, never what shape they return — that contract keeps assembly deterministic
and user-created types safe.

**13. The plugin ships engine-only, with a first-run bootstrap.** `add-type <repo-url>` clones a
collection into a local types directory the engine scans. On first use with no types installed,
the front door offers to install the official starter collection. *Why: keeps the model pure
(every type comes from a collection repo) while solving first-run UX with one consented prompt.*

**14. Decks are plain output folders.** Self-contained npm projects (SPRINT_4/, ...), in no shared
repo; optionally git-init'd individually. *Why: they are artifacts, large and binary-heavy.*

**15. Refactor before SPRINT_4; SPRINT_4 validates.** Type folders + generic engine + per-slide
output land first; the next real deck is the test — the same discipline that had SPRINT_3 catch
the args-passing and Wikimedia-429 bugs. SPRINT_2/3 are migrated to per-slide files ahead of this
(migration tool: `scripts/split_deck.py`) so the improve loop works on them immediately.

---

## The user journey

### Setup, once per machine (~15 min)

| Step | Who | What |
|---|---|---|
| S1 | user | Install Claude Code + the slidecraft plugin (engine-only) |
| S2 | user | Prereqs: Node, `pip install pymupdf pillow requests` |
| S3 | user | `add-type <collection-repo-url>` (or accept the first-run starter offer). Referenced themes resolve automatically at scaffold time |
| S4 | user *(optional)* | Configure a machine-local image backend (e.g. the OWUI skill + `.env`). Absent = mind-map/diagram enrichment skips, DONE report says so |

### Per deck (~30 min wall clock, ~5 min of user attention)

| Step | Who | What |
|---|---|---|
| 1 | **user** | "New deck" → pick deck type (checkbox) + name |
| 2 | **user** | Drop sources into `resources/` (chapter PDF, template PPTX, catalogue, ...) |
| 3 | engine | Scaffold + extract (TOC → sections, figures, source lines) |
| 4 | **user** | **Confirm round** — one pre-filled screen: sections, slide targets, enrichment toggles, agenda position → `recipe.json` |
| 5 | engine | Autonomous build: parallel authors → enrichment → grounding-critic → per-slide assembly → build → image verification |
| 6 | **user** | DONE report → review `/overview/` → present, or fire tweak phrases (each = single-file edit + rebuild) |

In the loop: 1, 2, 4, 6. Out of the loop: 3, 5.

---

## Migration notes (IU decks)

- `slidev-theme-ilse` becomes its own private git repo (currently a plain folder under
  `Präsentationen/slidecraft-themes/`), referencable from `type.json`.
- The private collection repo (e.g. `slidecraft-types-iu`) gets `deck-types/iu-sprint/` extracted
  from today's `references/ilse-author-guide.md`, `recipe.example.json`, the scaffolding slides,
  and the inline prompts in `workflows/sprint_deck.js`.
- SPRINT_2 and SPRINT_3 are split to per-slide files with `scripts/split_deck.py` (round-trip
  verified); SPRINT_1 stays a monolith unless touched again.
- OWUI client stays at `~/.claude/skills/owui/` per machine; never enters any repo.
