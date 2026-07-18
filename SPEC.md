# Slidecraft — Implementation Spec (v1)

**Status:** working implementation spec, consolidating the grilling + prototyping session
of 2026-07-17. Companion to `architecture_proposal.md` (the *what/why*, decisions D1–D24)
and `CONTEXT.md` (the vocabulary). This document is the *how*: what is a deterministic
script vs. a skill vs. an agent template vs. a command, where each lives, how deck-config
injection works, and what is proven vs. still missing.

Where this spec and the proposal disagree, **this spec wins** — it is grounded in working
prototypes (see §10 Evidence).

---

## 1. Decisions added this session (D25–D37)

| # | Decision |
|---|---|
| **D25** | **Deck root = working directory.** The user creates the target folder, launches Claude inside it, and runs `/init-deck`. No "output folder" interview question. Every script resolves the deck by walking up from CWD for `deck-context.json` and **fails loudly** if absent. No path parameters, no env vars, no `open_deck` handle — statelessness makes the "which process owns state" question moot. |
| **D26** | **All resource material is content by default.** There is no structural-nugget class. Study goals, objectives, summaries-of-substance — all mined as content nuggets. If such a nugget reaches the final deck and the user wants it repurposed (e.g. an agenda), they ask. Miners never decide "this is structural." |
| **D27** | **No MCP for v1 — plain Python scripts.** The knowledge manager is `km.py`, a subcommand CLI (`create-slide`, `merge-slides`, `set-content`, `validate`, `create-nugget`). Agents call it by absolute path, injected as `%KM%`. Revisit MCP only if bad-formatting/escaping errors accumulate in practice. Rationale: the prototype ran end-to-end on scripts; MCP's one hard advantage (escaping-free prose payloads) is neutralised by the **body-file convention** (D28). |
| **D28** | **Prose payloads travel as files, never as CLI arguments.** Passing a multi-line slide body as a shell argument silently truncates it (demonstrated: ~300 chars → 42, no error, on PowerShell 5.1). The Composer writes the body to a temp file; `set-content --body-file PATH` reads it. Path arguments only, ever, on every script. |
| **D29** | **Agents are REGISTERED subagent types with static definitions; deck values go in the small spawn prompt** (revises the prototype's "orchestrator renders the whole template"). Role/craft lives in the installed definition (`~/.claude/agents/<role>.md`), loaded by the **runtime** as the subagent's system prompt — it never enters the orchestrator's context. The definition is generic (no `%…%` placeholders; agent defs can't template — F4): "mine the source given in your prompt, for the topic given in your prompt". The orchestrator injects only deck-specific values (focus topic, deck root, `%KM%`, slide id, nugget ids) in a **few-hundred-token spawn prompt**. This keeps the orchestrator lean and deterministic. `tools:` allowlists are not relied upon (reported unreliable); the system is **soft-enforced** — the script is the paved road, `validate` catches drift. |
| **D34** | **Triage by parking (the Storyteller's third move, beside merge).** Every nugget **always gets a slide** — none are left unplaced. When the budget is full and a nugget arrives, the Storyteller may (a) associate to a fitting slide, (b) **merge** two condensable slides, or (c) **park** a lower-priority / off-storyline slide to free an active slot, then create the newcomer. **Park** = the slide's `src:` include is moved into a commented block in `slides.md`; the slide **file and association are preserved** (composed prose kept, D31-style). The Storyteller reads the parked block and sees the parked knowledge, so a later story shift can un-park it. `km` verbs: `park-slide`, `unpark-slide` (needs a free active slot), `create-slide --parked` (create directly parked when the newcomer itself is lowest-priority and the deck is full). **Budget counts only active (uncommented) includes** (revises D14: structural counts, parked does not). Consequence: **backlog (D1) is now vestigial** — hidden knowledge is *visible parked slides*, not an abstract pool; D1 is demoted to correction-only. |
| **D35** | **`/draft-deck` orchestrator = a Workflow; the Storyteller is a planner.** The workflow (deterministic JS, GA) runs the pipeline: `parallel()` miners by `agentType` → collect nuggets → **one Storyteller** that returns a *structured plan* (slides, their nuggets, merge/park decisions — full plan on a fresh draft, delta plan on an increment, D32) → the workflow executes the plan via `km` scripts → `pipeline()` composers at the **top level** (no nested spawning). Intermediate nugget/plan data stays in workflow script variables, never in a conversation context. Build-time check: confirm `agent({agentType})` + `--parked`/plan execution; fallback is a plain `/draft-deck` command driving the same subagents. |
| **D36** | **State model + hand-edit guard.** Slide state enum = `pending` / `draft` / `locked` (D2-binding, agents only); `pending` is the in-flight-composition guard (a reacting Storyteller must not touch a `pending` slide); `locked` is set **only by explicit user lock**, never auto. Hand-edited-but-unlocked slides are protected *dynamically*: `km` stamps a `content_hash` on every write, and a **deterministic PreToolUse hook** on `set-content`/`merge-slides`/`park-slide` re-hashes the target and, on mismatch, returns an **"ask"** decision (the one user-prompt allowed to pause a Workflow — D35), so the user approves before an agent overwrites their edit. This also covers the merge-of-a-hand-edited-slide case. Dropped `needs-polishing`/`reviewed` (nothing branches on them yet). |
| **D37** | **Refinement is reactive; two commands + conversation.** `/draft-deck` changes deck *shape* (new material, and constraint changes — budget/audience/language — via a Storyteller replan that skips `locked` slides). `/improve-deck` changes *quality* (runs the existing critics → auto-fix drafts, propose on locks; no add/remove/reorder). Per-slide conversational edits are handled in-session. **The deck context is the control surface:** the user should not have to call `/draft-deck` after editing a constraint — a change to `deck-context.json` triggers the matching refinement. Mechanism: a PostToolUse hook on `deck-context.json` edits + a stored context-hash diff for raw hand-edits detect the change; the session then runs the refinement (a hook surfaces/dispatches, it does not itself run the interactive pass). |
| **D30** | **Craft lives in a skill, loaded by path.** Slide-writing craft (density budget, visual-type-first, assertion titles, evidence bullets, figure placement) is the `compose-slide` skill. Agents **read it by explicit path** (injected as `%SKILL%`), not via skill auto-discovery (unreliable for spawned agents). The same skill is the single source of truth for the Composer *and* for form-checking reviewers. |
| **D31** | **Merge always recomposes** (supersedes D10's "Composer is not called after a merge"). `merge-slides` is mechanical at the *file* level — it unions the merged slides' nugget associations onto one new slide, retires the originals, frees a budget slot — and then the Storyteller spawns a Composer on the merged slide, exactly as after a create. The rule for every operation: **scripts move files and associations; the Composer writes words; no script ever writes slide prose.** |
| **D32** | **One unified Storyteller loop for draft and increment.** A fresh draft is the incremental loop starting from an empty deck. New nuggets (first run or a later added source) flow through the same create-first → budget-gate → merge-to-make-room logic. Proven: the same loop drafted a 5-slide deck and later absorbed a 6th nugget into the full deck via merge, losing no provenance. |
| **D33** | **Packaging: skill-repo + npx installer, no plugin.** With MCP gone, nothing structurally needs a plugin. The npx installer copies: commands → `~/.claude/commands/slidecraft/`; **agent definitions → `~/.claude/agents/` (must be user-scope to be spawnable as `agentType` — D29)**; workflows → `~/.claude/workflows/`; scripts + skills → `~/.claude/slidecraft/{scripts,skills}/` (referenced by absolute path). Agent teams are **not** required for v1 — the pipeline runs on subagents/Workflow. Teams remain a later enhancement for live observability only. |
| **D38** | **`/init-deck` UX refinements (2026-07-18 first-run feedback).** Four changes, all baked into `init-deck.md` + `scaffold_deck.py`: **(a) Fast guard** — the "already a deck?" check is a single `deck-context.json` stat, never a recursive directory scan (slow on OneDrive); the folder need **not** be empty (inputs may already sit in `input/`). **(b) Prewarm + background install** — `scaffold_deck.py --prewarm` runs the topic+theme-only steps (folders, theme copy, `package.json`, `.gitignore`, launchers) right after the theme is chosen (interview part 1), so `/init-deck` can start `npm install` **in the background** while the rest of the interview runs; Slidev is installed before the first preview instead of on first launcher click. The launchers now check for the real `slidev` binary (not just `node_modules/`), so a half-finished background install is completed rather than skipped. **(c) Local-theme localization** — a `local` theme is copied into the deck's **`theme/`** subfolder and referenced as `./theme` (in `slides.md` + the theme block), so the deck is self-contained/portable; builtin/npm/github themes stay registry-resolved. **(d) Duration→slides pacing** — the length question asks **max duration in minutes**; `max_slides` is *derived* at **1.5 min/slide** (the academic/lecture pace; per-deck-type table in `scaffold_deck.py`, from the legacy Slide-to-Time Ratios), so no separate slide-count question. An explicit `max_slides` still overrides. **(e) Topic question wording** — framed by user benefit ("this focus guides which knowledge is extracted from your sources"); internal terms (FOCUS-TOPIC, miner) are never surfaced to the user. Deck-context `schema_version` → `0.5`. |

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
| `km.py` | script (state ops) | yes | `~/.claude/slidecraft/scripts/` | agents call `python "%KM%" <sub>` |
| `knowledge-miner.md` | agent template | no (LLM) | `~/.claude/slidecraft/agents/` | read → rendered → spawn prompt |
| `image-miner.md` | agent template | no (LLM) | " | " |
| `storyteller.md` | agent template | no (LLM) | " | " |
| `slide-composer.md` | agent template | no (LLM) | " | " |
| `compose-slide/SKILL.md` | skill (craft) | no | `~/.claude/slidecraft/skills/` | read by path (`%SKILL%`) |
| storytelling skills (e.g. `academic-lecture`) | skill | no | `~/.claude/slidecraft/skills/` | Storyteller loads at outline time |

**Rule of thumb:** *deterministic + path-only payload → script. Model judgment → agent
template. Reusable craft/rules → skill. User entry point → command.*

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
   `LANGUAGE`, `DECK-TYPE`, …) plus scanned theme capabilities.
2. The orchestrator, before each spawn, reads the role's agent template, strips its
   frontmatter, and does a scripted string-replace of `%PLACEHOLDER%` → value, including
   infra paths `%KM%`, `%DECK-ROOT%`, `%SKILL%`, `%LAYOUTS%`, and (for the composer)
   `%SLIDE-ID%`, `%NUGGET-IDS%`.
3. The rendered text is passed as the prompt to a `general-purpose` subagent.
4. Injection happens on **every** spawn, so a context edit reaches the next run
   automatically; a running agent never re-injects.

Verified: miner, image-miner, storyteller, composer all rendered with zero unresolved
placeholders and behaved per the rendered instructions.

---

## 5. `km.py` contract (v1)

Deck root from `--deck` or CWD walk-up (D25). Every mutation appends to
`logs/actions.jsonl`. Prose bodies via `--body-file` only (D28).

| Subcommand | Behaviour | Caller |
|---|---|---|
| `create-nugget --file PATH` | Validates a miner-produced nugget JSON, assigns stamp id + filename, writes to `nuggets/`. Enforces field schema (§6). **[TO BUILD]** | miner |
| `create-slide --title T --nuggets a,b --after ID\|end [--parked]` | Stamped skeleton `.md` + state `.json` (`draft`) + association entry + inserts into `slides.md`. **Atomic budget gate:** exits non-zero `{"error":"budget_full"}` when **active** slides reach `max_slides` (structural counts, parked does not — D34). `--parked` creates directly into the parked block (no active-slot use). Never writes body. | storyteller |
| `merge-slides --slides a,b --title T` | New stamped slide carrying the **union** of inputs' nuggets; retires originals; fixes `slides.md` (frees a slot). Never writes body (D31 — Composer runs after). | storyteller |
| `park-slide --slide ID` / `unpark-slide --slide ID` | Move a slide's `src:` include into / out of the commented parked block in `slides.md`; file + association untouched (D34). Un-park needs a free active slot. State ↔ `parked`. | storyteller |
| `set-content --slide ID --body-file PATH` | Reads body from file; validates frontmatter present, `layout` in theme capabilities, referenced `assets/…` paths exist; writes; state→`composed`. | composer |
| `validate` | md↔state pairing, associations resolve, stamp uniqueness, `slides.md` complete/duplicate-free, budget respected. | lead |

**Verbatim guard (to add to `create-nugget`):** reject a nugget whose `raw_text` is not a
**symmetric-normalised** substring of its source (strip markdown emphasis, unicode
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
— the image's provenance anchor), `description` (neutral, for placement/alt-text),
`asset` (path). Decorative images → miner returns `{"nuggets": []}`.

Miner rules that moved the needle (evidence §10): "a list in the source is ONE nugget";
"never split a sentence"; a stated target ("6–12, not 40"). `FOCUS-TOPIC` is context for
register, **not a filter** — and keeping it short worked as well as an elaborate one.

---

## 7. Pipeline (unified draft + increment, D32)

```
/draft-deck (lead / orchestrator)
 1 CONVERT     source_converter.py: input/* → sources/ paged text; images → assets/extracted/
               + each image source carries its nearest text block. Extraction only.
 2 MINE        per text source: spawn knowledge-miner (rendered template);
               per image set: spawn image-miner. Each returns a LIST of nuggets;
               persist via km create-nugget. Mark sources mined; move input→processed.
 3 STORYTELL   spawn storyteller (rendered). It reads all nuggets, outlines structural
               slides, then create-first places content nuggets; on budget_full it
               MERGES the two least-distinct content slides to free a slot.
 4 COMPOSE     after every create AND every merge, storyteller spawns a fresh Composer
               (clean context) that loads compose-slide skill, writes via set-content.
 5 FINISH      lead runs km validate; report.
```
An **incremental run** (added source) is steps 1–5 restricted to new inputs; the
Storyteller starts from a full/partial deck and the same create/merge logic absorbs the
new nuggets. Proven end-to-end.

**Streaming vs. batch:** v1 uses **batch per source** (miner returns a list) on plain
subagents — no mailboxes, no agent teams, no experimental flag. Live-streaming via agent
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
- **Error handling** in the loop: composer fails mid-slide, miner dies mid-source (source
  must not be marked mined), long-run context. (Proposal Q5.)

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
1. Agents as **registered subagent types** (D29 context-economy optimization) — v1 currently
   renders templates by path (works, but loads the template into the orchestrator's context).
2. `/improve-deck` (critic/polish chain) + the hand-edit guard hook (D36) + reactive-context
   dispatch (D37).
3. The `/draft-deck` **Workflow** form (D35) — v1 ships the command-driven orchestration.
4. npx skill-repo installer (D33).
5. image-composer live integration into `/improve-deck` (loop validated standalone, §10).

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
