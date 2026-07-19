# Slidecraft — Implementation Spec (v1)

**Status:** working implementation spec, consolidating the grilling + prototyping session
of 2026-07-17 **and the pure-function-roles grilling of 2026-07-19 (D40–D45; ticket 11)**.
Companion to `architecture_proposal.md` (the *what/why*, decisions D1–D24)
and `CONTEXT.md` (the vocabulary). This document is the *how*: what is a deterministic
script vs. a skill vs. an agent template vs. a command, where each lives, how deck-config
injection works, and what is proven vs. still missing.

Where this spec and the proposal disagree, **this spec wins** — it is grounded in working
prototypes (see §10 Evidence).

---

## 1. Decisions added (D25–D45)

| # | Decision |
|---|---|
| **D25** | **Deck root = working directory.** The user creates the target folder, launches Claude inside it, and runs `/init-deck`. No "output folder" interview question. Every script resolves the deck by walking up from CWD for `deck-context.json` and **fails loudly** if absent. No path parameters, no env vars, no `open_deck` handle — statelessness makes the "which process owns state" question moot. |
| **D26** | **All resource material is content by default.** There is no structural-nugget class. Study goals, objectives, summaries-of-substance — all mined as content nuggets. If such a nugget reaches the final deck and the user wants it repurposed (e.g. an agenda), they ask. Miners never decide "this is structural." |
| **D27** | **No MCP for v1 — plain Python scripts.** The knowledge manager is `km.py`, a subcommand CLI (`create-slide`, `merge-slides`, `set-content`, `validate`, `create-nugget`). The **orchestrator** calls it by absolute path (`%KM%`); since D40, LLM roles never call scripts themselves. Revisit MCP only if bad-formatting/escaping errors accumulate in practice. Rationale: the prototype ran end-to-end on scripts; MCP's one hard advantage (escaping-free prose payloads) is neutralised by the **body-file convention** (D28). |
| **D28** | **Prose payloads travel as files, never as CLI arguments.** Passing a multi-line slide body as a shell argument silently truncates it (demonstrated: ~300 chars → 42, no error, on PowerShell 5.1). The orchestrator writes the LLM's returned payload to a temp file; `write-slide --file PATH` (composer pipeline, D43) or `set-content --body-file PATH` (direct edits) reads it. Path arguments only, ever, on every script. |
| **D29** | *(Narrowed by D40/D44, 2026-07-19: applies only to the **storyteller** executor — miners/composer run as OWUI invoke calls with km-assembled briefs; role/craft is inlined into briefs at assemble time.)* **Agents are REGISTERED subagent types with static definitions; deck values go in the small spawn prompt** (revises the prototype's "orchestrator renders the whole template"). Role/craft lives in the installed definition (`~/.claude/agents/<role>.md`), loaded by the **runtime** as the subagent's system prompt — it never enters the orchestrator's context. The definition is generic (no `%…%` placeholders; agent defs can't template — F4): "mine the source given in your prompt, for the topic given in your prompt". The orchestrator injects only deck-specific values (focus topic, deck root, `%KM%`, slide id, nugget ids) in a **few-hundred-token spawn prompt**. This keeps the orchestrator lean and deterministic. `tools:` allowlists are not relied upon (reported unreliable); the system is **soft-enforced** — the script is the paved road, `validate` catches drift. |
| **D34** | **Triage by parking (the Storyteller's third move, beside merge).** Every nugget **always gets a slide** — none are left unplaced. When the budget is full and a nugget arrives, the Storyteller may (a) associate to a fitting slide, (b) **merge** two condensable slides, or (c) **park** a lower-priority / off-storyline slide to free an active slot, then create the newcomer. *(Post-D41: associate/merge/park/create are **decision types in the plan**, executed by the orchestrator; parked-slide knowledge reaches the Storyteller via `plan-brief`'s deck-state injection, not by reading files.)* **Park** = the slide's `src:` include is moved into a commented block in `slides.md`; the slide **file and association are preserved** (composed prose kept, D31-style). The parked block is part of the injected deck state, so a later story shift can un-park it. `km` verbs: `park-slide`, `unpark-slide` (needs a free active slot), `create-slide --parked` (create directly parked when the newcomer itself is lowest-priority and the deck is full). **Budget counts only active (uncommented) includes** (revises D14: structural counts, parked does not). Consequence: **backlog (D1) is now vestigial** — hidden knowledge is *visible parked slides*, not an abstract pool; D1 is demoted to correction-only. |
| **D35** | **`/draft-deck` orchestrator = a Workflow; the Storyteller is a planner.** The workflow (deterministic JS, GA) runs the pipeline: `parallel()` miner **invoke-shim calls** (OWUI, D44) → collect nuggets → **one Storyteller** (Claude-subagent adapter) that returns a *structured plan* (slides, their nuggets, merge/park decisions — full plan on a fresh draft, delta plan on an increment, D32) → the workflow executes the plan via `km` scripts → `pipeline()` composer **invoke-shim calls** at the **top level** (no nested spawning). Intermediate nugget/plan data stays in workflow script variables, never in a conversation context. Fallback is a plain `/draft-deck` command driving the same seams. |
| **D36** | **State model + hand-edit guard.** Slide state enum = `pending` / `draft` / `locked` (D2-binding, agents only); `pending` marks in-flight or interrupted composition (`validate` flags any left at run end); `locked` is set **only by explicit user lock**, never auto. Hand-edited-but-unlocked slides are protected *dynamically*: `km` stamps a `content_hash` on every write, and a **deterministic PreToolUse hook** on `set-content`/**`write-slide`**/`merge-slides`/`park-slide` re-hashes the target and, on mismatch, returns an **"ask"** decision (the one user-prompt allowed to pause a Workflow — D35), so the user approves before an agent overwrites their edit. This also covers the merge-of-a-hand-edited-slide case. Dropped `needs-polishing`/`reviewed` (nothing branches on them yet). |
| **D37** | **Refinement is reactive; two commands + conversation.** `/draft-deck` changes deck *shape* (new material, and constraint changes — budget/audience/language — via a Storyteller replan that skips `locked` slides). `/improve-deck` changes *quality* (runs the existing critics → auto-fix drafts, propose on locks; no add/remove/reorder). Per-slide conversational edits are handled in-session. **The deck context is the control surface:** the user should not have to call `/draft-deck` after editing a constraint — a change to `deck-context.json` triggers the matching refinement. Mechanism: a PostToolUse hook on `deck-context.json` edits + a stored context-hash diff for raw hand-edits detect the change; the session then runs the refinement (a hook surfaces/dispatches, it does not itself run the interactive pass). |
| **D30** | *(Superseded for the composer by D43: the craft is merged into the unified composer template; the skill remains the human-facing craft doc and the source for form-checking reviewers.)* **Craft lives in a skill, loaded by path.** Slide-writing craft (density budget, visual-type-first, assertion titles, evidence bullets, figure placement) is the `compose-slide` skill. Agents **read it by explicit path** (injected as `%SKILL%`), not via skill auto-discovery (unreliable for spawned agents). |
| **D31** | **Merge always recomposes** (supersedes D10's "Composer is not called after a merge"). `merge-slides` is mechanical at the *file* level — it unions the merged slides' nugget associations onto one new slide, retires the originals, frees a budget slot — and then the **orchestrator invokes a Composer** on the merged slide (spawning language superseded by D41), exactly as after a create. The rule for every operation: **scripts move files and associations; the Composer writes words; no script ever writes slide prose.** |
| **D32** | **One unified Storyteller loop for draft and increment.** A fresh draft is the incremental loop starting from an empty deck. New nuggets (first run or a later added source) flow through the same create-first → budget-gate → merge-to-make-room logic. Proven: the same loop drafted a 5-slide deck and later absorbed a 6th nugget into the full deck via merge, losing no provenance. |
| **D33** | **Packaging: skill-repo + npx installer, no plugin.** With MCP gone, nothing structurally needs a plugin. The npx installer copies: commands → `~/.claude/commands/slidecraft/`; **role prompt templates → `~/.claude/slidecraft/agents/` (read by the km assemble subcommands — D40; a `~/.claude/agents/` registration only for the storyteller's Claude-subagent executor if the adapter needs a registered type — narrowed D29)**; the **invoke shim + unified composer template** (D43/D44); workflows → `~/.claude/workflows/`; scripts + skills → `~/.claude/slidecraft/{scripts,skills}/` (referenced by absolute path). Agent teams are **not** required for v1 — the pipeline runs on subagents/Workflow. Teams remain a later enhancement for live observability only. |
| **D39** | **Presenter notes default to the nuggets' raw knowledge (2026-07-18).** A composed slide body is telegraphic (≤ 60 words, D30); the full verbatim source behind it belongs in the **Slidev speaker notes** so the presenter has it while talking. `set-content` therefore fills notes it finds **empty**: after writing, if the body carries no presenter-notes block, it **appends** one assembled from each associated nugget's **raw knowledge** — `raw_text` for a text nugget, `visible_text` for an image nugget — labelled with the source locator (`chapter_4.pdf p.2`). **If empty** is the whole gate: a composer that authored its own notes keeps them; a **structural** slide (no nuggets) gets nothing. This is done **deterministically in `km`, not by the Composer**, on purpose — the notes must be *verbatim*, and an LLM paste risks paraphrase/truncation (the very reason the verbatim guard exists). It is a deliberate, narrow carve-out to "no script writes slide prose" (D31): notes are **not composed prose** but verbatim provenance copied from the nuggets, so assembling them mechanically is the reliable choice. Detection = a trailing HTML comment that is not a `FIGURE NEEDED` / skeleton marker; a literal `-->` inside the verbatim text is neutralised so it can't close the note early. |
| **D38** | **`/init-deck` UX refinements (2026-07-18 first-run feedback).** Four changes, all baked into `init-deck.md` + `scaffold_deck.py`: **(a) Fast guard** — the "already a deck?" check is a single `deck-context.json` stat, never a recursive directory scan (slow on OneDrive); the folder need **not** be empty (inputs may already sit in `input/`). **(b) Prewarm + background install** — `scaffold_deck.py --prewarm` runs the topic+theme-only steps (folders, theme copy, `package.json`, `.gitignore`, launchers) right after the theme is chosen (interview part 1), so `/init-deck` can start `npm install` **in the background** while the rest of the interview runs; Slidev is installed before the first preview instead of on first launcher click. The launchers now check for the real `slidev` binary (not just `node_modules/`), so a half-finished background install is completed rather than skipped. **(c) Local-theme localization** — a `local` theme is copied into the deck's **`theme/`** subfolder and referenced as `./theme` (in `slides.md` + the theme block), so the deck is self-contained/portable; builtin/npm/github themes stay registry-resolved. **(d) Duration→slides pacing** — the length question asks **max duration in minutes**; `max_slides` is *derived* at **1.5 min/slide** (the academic/lecture pace; per-deck-type table in `scaffold_deck.py`, from the legacy Slide-to-Time Ratios), so no separate slide-count question. An explicit `max_slides` still overrides. **(e) Topic question wording** — framed by user benefit ("this focus guides which knowledge is extracted from your sources"); internal terms (FOCUS-TOPIC, miner) are never surfaced to the user. Deck-context `schema_version` → `0.5`. |

**Decisions added 2026-07-19 (pure-function roles; the full spec is ticket 11):**

| # | Decision |
|---|---|
| **D40** | **Pure-function roles; assemble → invoke → persist.** Every LLM role (knowledge-miner, image-miner, storyteller, slide-composer) is a **pure function**: a fully self-contained prompt in, structured output out — no file reads, no script calls, no IDs to chase inside a prompt. Three stages per role, sequenced by the orchestrator: **assemble** — `km` renders a **brief** via new deterministic subcommands `mine-brief`, `plan-brief`, `compose-brief` (injecting source text, nugget digests, or a slide's routed fields + inlined craft); **invoke** — a thin pluggable **executor shim** sends the brief to OWUI or a Claude subagent; **persist** — `km` validates and writes (`create-nugget`, new `write-slide`). Payloads still travel as files (D28). Supersedes the agents-call-km-themselves model. |
| **D41** | **The storyteller is a pure planner; the orchestrator executes.** The storyteller returns a **structured plan** — ordered structural slides; per content slide the nugget IDs and a create / associate / merge / park decision (D34); optional **`intended_function`** hint per content slide (D43 enum) — and never spawns composers, never sees composed bodies. Full plan on a fresh draft, delta plan on a re-run, `locked` slides skipped (D32/D36). **Supersedes D12** and the storyteller template's "you spawn a Composer" language; hardens D35. |
| **D42** | **Field-routing contract — the two briefs read opposite fields of the same nugget.** *Storyteller brief* per nugget: `title` + `information` digest (+ image `figure_type`/`description`); never `raw_text`/`visible_text`/assets. *Composer brief* per slide by slide type: **structural** → deck metadata + layout defaults; **text-only** → nuggets' verbatim `raw_text` + `source`/`page` (citation footer); **image+text** → co-nuggets' `raw_text` + image `asset`/`description` (body from text nuggets only — the figure is placed, never paraphrased); **image-only** → `asset` + `description` + `context_text` (nearest text block) — **headline only, no body text**. The composer never sees `information` or `visible_text`; those remain persist-side inputs (D39 notes fill). Image `description` = 1–2 sentences, **content first, then form**. |
| **D43** | **The composer emits semantic role-keyed JSON; `km write-slide` owns physical assembly.** Output: `{layout, concept_type, content: {role: md…}, image?: {asset, alt}, figure_needed?, notes?}`. **`concept_type` enum** (from the compose-slide craft): `structural | motivate | define | compare | relationship | process | cause-effect | finding | categories | claim-support`; the storyteller's `intended_function` hint uses the same enum and the composer may override it when the raw content demands. `write-slide` maps roles → **physical** slot names via the theme's roles map, applies `defaults`, emits frontmatter + `::physical::` blocks, validates layout/assets, fills empty notes verbatim (D39), stamps `concept_type` into the slide state file — **the LLM never sees a physical slot name; ADR-0001 becomes a script guarantee.** The unified composer template merges the compose-slide craft + composer role into one tunable prompt, deleting only the dead mechanics (script calls, disk reads, slot rules). Supersedes D30's load-by-path for the composer. |
| **D44** | **Executor seam, defaults, rejection loop.** One shim `invoke(role, prompt, image?)` with two adapters: the **OWUI client** (OpenAI-compatible; an image rides as a base64 data-URL content part — transport proven) and a **Claude subagent**. Defaults: miners + composer → **`gdpr.gpt-5.6-sol`** (EU-hosted, verified live 2026-07-19); storyteller → **Claude subagent**. Per-role executor/model = config with toolkit defaults, deck-context override. On persist rejection (verbatim guard, layout/asset/schema, plan schema): re-invoke with the error appended, **cap 2**, then the per-role terminal: **miner → drop the nugget + flag** (nothing exists to park), **composer → park the slide + flag**, **storyteller → abort the draft run with a flagged error** (nothing is composed without a valid plan). Each invoke is stateless; the shim wraps the loop. |
| **D45** | **Image nuggets are self-contained; the image-miner is strictly per-image.** One miner call per extracted image, the image passed **directly** (no IDs). At persist, `create-nugget` **denormalizes `asset` (public `/extracted/…` path) + `context_text` (nearest text block) onto the image nugget** from the source record via the `image_source_id` the *workflow* holds. The image-miner prompt stays conceptual (what the figure teaches), never a reproduction spec. |

**Source-conversion context capture (Round 9):** each image source carries the **single
nearest text block** (smallest vertical gap from the image rect's top or bottom edge; no
regex, language-agnostic) as its caption/attribution anchor. See
`docs/source-conversion-limitations.md` for accepted gaps (vector figures, multi-column,
tiled images, scanned PDFs) and the parked Mistral-OCR future direction.

---

## 2. Artifact inventory — script vs. skill vs. agent-template vs. command

| Artifact | Kind | Deterministic? | Home (installed) | Called / loaded how |
|---|---|---|---|---|
| `/init-deck` | command | — | `~/.claude/commands/slidecraft/` | user types `/init-deck` |
| `/draft-deck` | command (orchestrator) | — | `~/.claude/commands/slidecraft/` | user types `/draft-deck` |
| `source_converter.py` | script | yes | `~/.claude/slidecraft/scripts/` | lead runs it, path args only |
| `scan_theme.py` | script | yes | `~/.claude/slidecraft/scripts/` | `/init-deck` runs it |
| `km.py` | script (state ops + brief assembly) | yes | `~/.claude/slidecraft/scripts/` | orchestrator calls `python "<KM>" <sub>` (D40) |
| invoke shim | script (executor adapters) | no (calls LLMs) | `~/.claude/slidecraft/scripts/` | orchestrator: `invoke(role, prompt, image?)` — OWUI or Claude subagent (D44) |
| `knowledge-miner.md` | role prompt template | no (LLM) | `~/.claude/slidecraft/agents/` | inlined into brief by `km mine-brief` (D40) |
| `image-miner.md` | role prompt template | no (LLM) | " | " (one call per image, image passed directly — D45) |
| `storyteller.md` | role prompt template | no (LLM) | " | inlined by `km plan-brief`; executed as Claude subagent (D44) |
| `slide-composer.md` | **unified** role+craft template (D43) | no (LLM) | " | inlined by `km compose-brief` |
| `compose-slide/SKILL.md` | craft source (merged into the unified composer template — D43) | no | `~/.claude/slidecraft/skills/` | human-facing craft doc; runtime prompt derives from the unified template |
| storytelling skills (e.g. `academic-lecture`) | skill (craft) | no | `~/.claude/slidecraft/skills/` | inlined into the storyteller brief by `km plan-brief` (D40) |

**Rule of thumb:** *deterministic + path-only payload → script. Model judgment → role
prompt template (a pure function — D40). Reusable craft/rules → skill, inlined at assemble
time. User entry point → command.*

---

## 3. The deck project (on disk, under CWD)

```
deck-root/                         # = CWD; contains deck-context.json (D25)
├── deck-context.json              # interview answers + injection blocks + theme caps
├── input/                         # user-dropped PDFs/md/txt (+ URL→md)
│   └── processed/                 # fully-mined inputs (filesystem = registry)
├── sources/                       # converted: paged text + image-source records
├── assets/extracted/              # images pulled from PDFs
├── nuggets/                       # one JSON per knowledge nugget (§6)
├── slides/                        # <title>--<stamp>.md + .json (state) per slide
├── theme/                         # local theme copied in for self-containment (D38; local themes only)
├── associations.json              # slide-id → [nugget-ids]; [] = structural
├── logs/actions.jsonl             # one line per km mutation
├── slides.md                      # Slidev entry; src-includes in order
├── show_slide_deck.cmd            # double-click launcher — Windows (scaffolded by /init-deck)
└── show_slide_deck.sh             # double-click launcher — macOS/Linux
```

**Rendering (how a deck is shown) — verified 2026-07-18.** Slidev resolves its **theme from a
local `node_modules/`**, so a viewed deck is a real (minimal) npm project, not pure data:
- **`package.json`** — `/init-deck` scaffolds it declaring `@slidev/cli` + the chosen theme
  (`@slidev/theme-default`, or the local/npm theme). The `theme:` in `slides.md`'s headmatter
  names it.
- **`node_modules/`** — created by `npm install` on first view (the launcher does this). It is
  heavy and **must be excluded from sync** (`.gitignore` + a OneDrive ignore); the deck's
  *data* stays portable, its build deps do not travel.
- **Servable assets live under `public/`** — Slidev serves `public/` at the site root, so an
  extracted image at `public/extracted/rp-devtime.png` is referenced as `/extracted/…`. A
  root-relative `assets/…` path **fails the Vite build** (proven). Therefore
  `source_converter.py` writes extracted images to `public/extracted/` and the image-composer
  writes generated figures to `public/generated/`; the image nugget's asset path and every
  slide reference use the `/`-rooted public URL. `km set-content` validates that referenced
  `/…` assets exist under `public/`.

Viewing = `npm install` (first run) then `slidev slides.md --open` from the deck root, wrapped
in the double-clickable launchers `/init-deck` scaffolds — `show_slide_deck.cmd` (Windows) and
`show_slide_deck.sh` (macOS/Linux) — which install on first run, print the clickable `localhost`
link, and open the browser. Evidence: the prototype deck
built clean (`✓ built in 2.87s`) once assets were moved to `public/` and referenced as `/…`.

---

## 4. Deck-config injection (verified mechanism)

1. `/init-deck` writes `deck-context.json` with an `injection` block: per-role placeholder
   values derived from the interview (`FOCUS-TOPIC`, `MAX-SLIDES`, `AUDIENCE`,
   `LANGUAGE`, `DECK-TYPE`, …) plus scanned theme capabilities **and the per-role
   executor/model block (D44)**.
2. **Rendering lives in `km` (D40):** the assemble subcommands (`mine-brief`, `plan-brief`,
   `compose-brief`) read the role's prompt template, strip its frontmatter, string-replace
   `%PLACEHOLDER%` → value, and **inject the routed data itself** — the source text for a
   miner, the nugget digests for the storyteller, one slide's routed nugget fields + layout
   roles/intents/defaults for the composer (D42). No infra paths, IDs-to-chase, or script
   instructions appear in a brief — the prompt is fully self-contained.
3. The rendered brief goes to the **invoke shim** (D44): OWUI chat call for miners/composer,
   Claude subagent for the storyteller.
4. Assembly happens on **every** invoke, so a context edit reaches the next run
   automatically; a running invoke never re-injects.

Verified (2026-07-17, pre-D40 form): miner, image-miner, storyteller, composer all rendered
with zero unresolved placeholders and behaved per the rendered instructions.

---

## 5. `km.py` contract (v1)

Deck root from `--deck` or CWD walk-up (D25). Every mutation appends to
`logs/actions.jsonl`. Prose bodies via `--body-file` only (D28).

| Subcommand | Behaviour | Caller |
|---|---|---|
| `create-nugget --file PATH [--image-source ID]` | Validates a miner-produced nugget JSON (verbatim guard — built & verified), assigns stamp id + filename, writes to `nuggets/`. Enforces field schema (§6). **For image nuggets, denormalizes `asset` + `context_text` onto the nugget from the referenced source record (D45) [TO BUILD — the denormalization only]** | orchestrator (persist stage, D40) |
| `create-slide --title T --nuggets a,b --after ID\|end [--parked]` | Stamped skeleton `.md` + state `.json` (`draft`) + association entry + inserts into `slides.md`. **Atomic budget gate:** exits non-zero `{"error":"budget_full"}` when **active** slides reach `max_slides` (structural counts, parked does not — D34). `--parked` creates directly into the parked block (no active-slot use). Never writes body. | orchestrator (executing the plan, D41) |
| `merge-slides --slides a,b --title T` | New stamped slide carrying the **union** of inputs' nuggets; retires originals; fixes `slides.md` (frees a slot). Never writes body (D31 — Composer runs after). | orchestrator (executing the plan, D41) |
| `park-slide --slide ID` / `unpark-slide --slide ID` | Move a slide's `src:` include into / out of the commented parked block in `slides.md`; file + association untouched (D34). Un-park needs a free active slot. State ↔ `parked`. | orchestrator (executing the plan, D41) |
| `set-content --slide ID --body-file PATH` | Reads body from file; validates frontmatter present, `layout` in theme capabilities, referenced `assets/…` paths exist; writes; state→`composed`. **Presenter-notes fallback (D39):** when the body has no speaker-notes block, appends one built verbatim from the slide's nuggets' raw knowledge (`raw_text` / `visible_text` + locator); composer-authored notes and structural slides are left untouched. Returns `{"ok":true,"notes_added":bool}`. **Retained for direct-markdown edits; the composer pipeline persists via `write-slide` (D43).** | session / tools |
| `write-slide --slide ID --file PATH` | **[D43, TO BUILD]** Reads the composer's semantic role-keyed JSON; maps roles → physical slots via the theme's roles map; applies `defaults`; emits frontmatter + `::physical::` blocks; validates layout + assets; fills empty notes verbatim (D39); stamps `concept_type` into the slide state file; renders `figure_needed` as the `FIGURE NEEDED` marker. Rejects with a structured error (drives the D44 retry loop). **Guarded by the D36 hand-edit hook** (it is the composer pipeline's write path). | orchestrator |
| `mine-brief --source ID [--image IMAGE-SOURCE-ID]` | **[D40, TO BUILD]** Renders the self-contained miner brief: role template + injection values + the **source text** (text brief) or the **image reference + `context_text`** (vision brief). | orchestrator |
| `plan-brief` | **[D40/D42, TO BUILD]** Renders the self-contained storyteller brief: role template + deck constraints + inlined storytelling craft + **all nugget digests** (`title`/`information`/`figure_type`/`description` — never `raw_text`/`visible_text`) + current deck state (incl. the parked block) on a re-run. | orchestrator |
| `write-plan --file PATH` | **[D40/D41, TO BUILD]** Validates the storyteller's returned plan against its schema — nugget ids exist, decision types valid, structural slides well-formed, budget arithmetic sound, `intended_function` values in the D43 enum — records it (log + plan file), and hands the orchestrator an executable step list. Rejects with a structured error (drives the D44 retry; cap 2 exhausted → **abort the draft run with a flagged error**). | orchestrator (persist stage, D40) |
| `compose-brief --slide ID` | **[D40/D42, TO BUILD]** Renders the self-contained composer brief for one slide by slide type (structural / text-only / image+text / image-only), routing exactly the D42 fields + layout roles/intents/defaults + deck metadata + the optional `intended_function` hint. | orchestrator |
| `validate` | md↔state pairing, associations resolve, stamp uniqueness, `slides.md` complete/duplicate-free, budget respected. | lead |

**Verbatim guard (built into `create-nugget`, verified):** reject a nugget whose `raw_text`
is not a **symmetric-normalised** substring of its source (strip markdown emphasis, unicode
quotes/dashes, page markers from *both* sides before comparing). Verified 61/61 pass with
symmetric normalisation; a naive one-sided check produced false rejections.

Error shape: `{"error": "<code>", ...context}` + non-zero exit, so an agent can react.

---

## 6. Nuggets (the object, tuned against a hand-labelled gold set)

A nugget is **one coherent block of teachable material on a single topic — roughly one
slide's worth**, NOT a single claim. (Early "one claim = one nugget" shredded a 5-page
chapter into 53 fragments; the tuned rule yields 6–12, matching the human gold set.)

**Text nugget:**
```json
{ "nugget_id": "<stamp>", "kind": "text", "source": "chapter_4.pdf", "page": 2,
  "title": "Processing technologies and accuracies",
  "information": "- condensed teaching bullets (the miner's own wording)\n- 2–7 bullets",
  "raw_text": "<contiguous verbatim passage, the provenance anchor, ~150–950 chars>" }
```
**Image nugget** adds: `figure_type`, `visible_text` (every string in the image, verbatim
— the image's provenance anchor), `description` (**1–2 sentences, content first then form**
— what the figure is about, then its shape; for placement + alt-text, never a label
inventory — D42), and **denormalized at persist time from the source record (D45):**
`asset` (public `/extracted/…` path) + `context_text` (nearest text block). The miner never
produces paths or IDs. Decorative images → miner returns `{"nuggets": []}`.

Miner rules that moved the needle (evidence §10): "a list in the source is ONE nugget";
"never split a sentence"; a stated target ("6–12, not 40"). `FOCUS-TOPIC` is context for
register, **not a filter** — and keeping it short worked as well as an elaborate one.

---

## 7. Pipeline (unified draft + increment, D32)

```
/draft-deck (lead / orchestrator — every role runs assemble → invoke → persist, D40)
 1 CONVERT     source_converter.py: input/* → sources/ paged text; images → public/extracted/
               + each image source carries its nearest text block. Extraction only.
 2 MINE        per text source: km mine-brief → invoke (OWUI, D44) → km create-nugget.
               Per EXTRACTED IMAGE (one call each, image passed directly — D45):
               km mine-brief --image → invoke (OWUI vision) → km create-nugget
               (denormalizes asset + context_text). Verbatim-guard reject → re-invoke
               with error, cap 2, then drop+flag (D44). Mark sources mined; input→processed.
 3 PLAN        km plan-brief (all nugget DIGESTS — D42) → invoke (Claude subagent) →
               structured plan: structural slides; per content slide nugget ids +
               create/associate/merge/park + optional intended_function hint (D41/D43)
               → km write-plan validates the plan schema; reject → re-invoke, cap 2,
               then ABORT the draft run with a flagged error (D44).
 4 EXECUTE +   the ORCHESTRATOR walks the plan: km create-slide/merge-slides/park-slide;
   COMPOSE     after every create AND merge: km compose-brief --slide (routed raw fields,
               D42) → invoke (OWUI) → km write-slide (semantic JSON → physical Slidev,
               concept_type stamped — D43). Reject → re-invoke, cap 2, then park+flag.
 5 FINISH      lead runs km validate; report (parked slides, flags, FIGURE NEEDED).
```
An **incremental run** (added source) is steps 1–5 restricted to new inputs; the
Storyteller starts from a full/partial deck and the same create/merge logic absorbs the
new nuggets. Proven end-to-end.

**Streaming vs. batch:** v1 uses **batch per source** (miner returns a list) via stateless
invoke-shim calls (OWUI, D44) — no mailboxes, no agent teams, no experimental flag. Live-streaming via agent
teams (one nugget at a time) is a later enhancement for observability, not required for
incrementality.

---

## 8. Known tensions to resolve (feed the remaining open questions)

- **Density vs. merge.** Repeated merging accumulates nuggets faster than the 40-word
  density cap allows (a 6-nugget merged slide measured 44 words). Options: a `split`
  operation; a merge that defers surplus nuggets to backlog; or accept overfull as a
  later cleanup-agent concern (proposal §10). **Unresolved.**
- **Structural-slide maintenance.** The agenda/title is created before content exists;
  who refreshes it at the end? (Proposal Q8.)
- **Storyteller fit/merge heuristic** beyond "least-distinct by title/information."
  (Proposal Q4.)
- **Error handling** in the loop: *the persist-rejection/retry half is resolved by D44*
  (re-invoke with error, cap 2, per-role terminal). Still open: a miner invoke dying
  mid-source (the source must not be marked mined), long-run context. (Proposal Q5,
  narrowed.)

---

## 9. What's built vs. missing (minimal running version)

Target flow: launch in folder → `/init-deck` → interview → drop PDF → `/draft-deck` → view.

**Built & proven end-to-end (§10):**
- `km.py` — create-nugget (+ verbatim guard), create-slide (+ budget gate), merge-slides,
  set-content (+ `public/` asset validation), park/unpark, validate.
- `source_converter.py` — PDF→paged text + image extraction to `public/extracted/` (`/…`
  paths) + nearest-text-block context.
- `scaffold_deck.py` + `scan_theme.py` — deck scaffold + theme-capability scan. Two phases
  (D38): `--prewarm` (folders + local-theme copy into `theme/` + `package.json` so `npm install`
  can run in the background during the interview) and the full scaffold (deck-context, slides.md,
  derived `max_slides` from duration ÷ 1.5 min/slide).
- Agent templates: knowledge-miner, image-miner, storyteller, slide-composer, image-composer;
  `compose-slide` skill; the injection mechanism.
- Commands: `/init-deck`, `/draft-deck` (wrappers installed via `install_commands.py`).
- **Launchers: `/init-deck` always scaffolds BOTH `show_slide_deck.cmd` (Windows) and
  `show_slide_deck.sh` (macOS/Linux, exec bit set) into the deck** — copied by
  `scaffold_deck.py` from `slidecraft/templates/`.
- The full flow verified on a freshly scaffolded deck: scaffold → convert → mine → plan
  (budget gate → merge) → compose → `validate ok`; deck renders green once assets are in
  `public/`.

**Remaining for a polished v1:**
1. **The D40–D45 pure-function refactor (ticket 11):** km assemble subcommands (`mine-brief`,
   `plan-brief`, `compose-brief`) + `write-slide` persist + image-nugget denormalization;
   the invoke shim (OWUI `gdpr.gpt-5.6-sol` / Claude subagent) with the cap-2 retry → park+flag
   loop; the unified composer template (craft merged, mechanics removed); the planner-only
   storyteller template; `concept_type` on the slide state file.
2. `/improve-deck` (critic/polish chain) + the hand-edit guard hook (D36) + reactive-context
   dispatch (D37).
3. The `/draft-deck` **Workflow** form (D35) — v1 ships the command-driven orchestration
   over the same seams.
4. npx skill-repo installer (D33; now also ships the invoke shim + unified templates).
5. image-composer live integration into `/improve-deck` (loop validated standalone, §10).
6. (Narrowed D29) registered-subagent-type packaging — now relevant only for the storyteller;
   miners/composer are OWUI calls by default (D44).

---

## 10. Evidence (2026-07-17 prototype, SPRINT_4 chapter 4)

- **Nugget mining tuned to a human gold set:** 6 runs of `gpt-5.6-sol`, stable at 10–11
  nuggets (gold = 8), 8/8 gold topics covered, **61/61 excerpts verbatim** under symmetric
  normalisation. Earlier "one-claim" rule gave 53 shredded fragments — rejected.
- **Image miner:** 8 runs, every one 1 nugget, 8/8 labels transcribed verbatim, **0
  invented numbers** (correctly reported "axes have no numeric scale"). Page context made
  no measurable difference to fidelity.
- **Storyteller draft:** real agent, budget 5, 11 nuggets → hit budget gate → merged →
  spawned Composers → 11/11 nuggets placed, `validate ok`.
- **Composer density:** before `compose-slide` skill, a merged slide was ~90 words (wall
  of text); after, **37 words**, 3 telegraphic bullets, assertion H1, figure placed.
- **Incremental merge:** added a 12th nugget to the full deck → same loop merged two
  slides (unioned 6 nuggets, none lost) → created + composed the newcomer → still 5/5,
  `validate ok`. Confirmed density-vs-merge tension (44-word merged slide).
- **Transport:** slide body via CLI arg truncated silently (~300→42 chars); via
  `--body-file`, full body intact. → D28.
```
