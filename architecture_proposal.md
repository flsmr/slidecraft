# Slidecraft – Agentic Presentation Framework

**Version:** 0.4 (consolidated working draft)
**Status:** Architecture proposal — integrates the v0.1 draft, the decision rounds, the detailed v1 workflow input, the grilling session of 2026-07-16 (10 grill rounds + platform capability verification against Claude Code docs), and the domain-modeling session of 2026-07-16 (`CONTEXT.md` is the canonical vocabulary)
**Basis:** Slidev-based Claude plugin, executed via **Claude Code agent teams**
**Scope note:** Slide-theme *generation* already exists in this repo and is **out of scope**. Image creation, the polishing workflow, and the Spectator (audience-review) agent are **deferred** — v1 targets the core mechanics: input → source → nugget → slide → deck.

---

## 1. Project Goal

Slidecraft turns source material into structured, traceable, and reusable presentation slides.

Users place input files (PDF, Markdown, web URLs, later spreadsheets/images) into an `input/` directory. An agent team converts these inputs into sources, extracts atomic **Knowledge Nuggets**, assigns them to slides, composes slide content, and assembles a Slidev deck — under global constraints (topic, audience, deck type, setting, language, length) captured in an initial interview.

Core guarantees:

- Every slide remains traceable to its source material (full provenance).
- Slides in protected lifecycle states are never silently rewritten by agents.
- New source material is integrated deterministically.
- All file/state mutations go through deterministic, logged MCP operations, so the system cannot corrupt its own bookkeeping.

---

## 2. Decisions Locked

### 2.1 From the first definition rounds

| # | Decision |
|---|----------|
| D1 | **Knowledge Nuggets live in a central store**, one JSON file per nugget. Slides reference nuggets via the Knowledge Association file (D6/§7.5). Nuggets with no referencing slide form the natural backlog pool. |
| D2 | **Lifecycle states bind agents only.** The user may always hand-edit any slide in any state. States govern what *agents* may change automatically. |
| D3 | **V1 agent set = core three + deterministic validation:** Knowledge Miner, Storyteller, Slide Composer. Design/Review/Asset agents come later (v1.1+), partly by adopting existing repo components. |
| D4 | **Review findings (later) are lifecycle-aware:** findings on `draft` slides may auto-trigger fixes; findings on protected slides become proposals. |
| D5 | **Relationship to existing sprint-deck pipeline: parallel v2, reuse per part.** Proven components (image critic, reference renderer, SVG figure builder, OWUI image generation) are adopted individually where they fit. Sprint-deck keeps working during the transition. |
| D6 | **Identity via timestamp stamps, not UUIDs.** Nuggets and slides carry a unique creation stamp (date-time, millisecond precision; the MCP appends a counter suffix on collision). Slide filenames = self-speaking title + fixed stamp postfix; the title part may change, the stamp is the stable reference. |
| D7 | `slides.md` (the main deck file) owns slide order. Whether a richer deck manifest is needed stays open (Q3). |
| D8 | **Agent templates are static with placeholders**, rendered at spawn time by scripted string replacement — see §6.4 for the verified mechanism. |

### 2.2 From the grilling session (2026-07-16)

| # | Decision |
|---|----------|
| D9 | **Placement rule: create-first.** As long as the slide budget is not reached, every incoming nugget creates a new slide. Fit-checking against existing slides begins only once the budget is full. Accepted consequence: early slides are thin (often one bullet from one nugget) and **merging is the routine consolidation mechanism**, not the exception. Confirmed by D24: the budget is a target — no pre-budget association. |
| D10 | **Merging is pure mechanical appending — no automatic recomposition.** The Storyteller decides *which* slides to merge based on their content; the MCP `merge_slides` function deterministically appends the merged slides' content (aggregating bullet points) and joins their associations. The Composer is **not** called after a merge. Overfull slides are a later cleanup agent's concern (out of scope). |
| D11 | **Execution model: Claude Code agent teams.** The `/draft-deck` session is the team lead; the team is spawned for the drafting run and torn down when it finishes. Later user changes (new references, constraint edits) trigger different teams/workflows, defined later. Requires the experimental flag `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (see §11 platform facts). |
| D12 | **Roster: lead + N miner teammates + 1 storyteller teammate; the Composer is a fresh foreground subagent** spawned by the Storyteller, one per composition, guaranteeing a clean context every time (no spill-over between slides). No fast pass — every nugget flows serially through the Storyteller (chosen over miner-spawned or lead-dispatched composer topologies). |
| D13 | **Handoffs: messages trigger, files carry.** SendMessage is the only trigger channel (e.g. miner→storyteller: "nugget `<id>` created"). Messages carry only IDs; the receiver reads the actual data fresh from disk. The MCP action log provides observability. |
| D14 | **The outline creates real slides immediately.** Structural slides (title, agenda, learning goals, recap, quiz, references, thank-you — whatever the Storyteller deems fitting) are identified by an **empty association list** (no nugget IDs) — no extra marker. **Budget = total deck**: "if the user says X slides, they get X slides." Structural slides count against the budget and are never merge candidates. |
| D15 | **Composer write path: MCP `update_slide_content`.** The composer submits the full slide body; the MCP validates (frontmatter intact, layout exists in theme capabilities, stamp/filename untouched), writes, and logs. The §8 all-mutations-via-MCP principle holds without exception. |
| D16 | **Theme capabilities are scanned at `/init-deck`** by a deterministic script (layouts, slots, components) and written into `deck-context.json`. The Composer *chooses* the most appropriate layout per slide from that list; the MCP validates the choice but never makes it. Re-scan on `/change-theme`. |
| D17 | **Interview additions: topic and language.** Topic feeds the `%FOCUS-TOPIC%` injection for miners; language (en/de/…) governs all composed content. |
| D18 | **Re-run contract: mine only new inputs.** After an input is fully mined (every source derived from it, D22), it is **moved to `input/processed/`** — the filesystem is the input registry. A `/draft-deck` re-run processes only what remains in `input/`, and new nuggets flow into the existing deck. |

Deliberately deferred: full idempotency layer, approval UX, hand-edit reconciliation details, incremental-change workflows beyond D18.

### 2.3 From the domain-modeling session (2026-07-16)

| # | Decision |
|---|----------|
| D19 | **Vocabulary is canonical in `CONTEXT.md`.** Key renames: `references/` → `input/` (user files = **inputs**; "reference" now means citations only), converted artifacts = **sources** ("resource" rejected; the conversion step was later renamed harmonization → **source conversion**), deck-style skill → **storytelling skill**, "theme pack" culled (a **theme is its own repo** carrying style guide + visual conventions; skeletons abolished), "evidence sidecar" and "consistency contract" culled (nugget + association carry provenance natively). |
| D20 | **One nugget = one source anchor, definitionally.** The same idea in two sources yields two nuggets; deduplication is a slide-level concern, never a nugget-level one. |
| D21 | **Images are mined, not converted into nuggets.** Source conversion is extraction-only (pure scripts, no LLM/vision calls): each extracted image becomes an **image source**. Roster: one miner per text source plus **one vision miner per input's image set** (serial over its images). All nuggets — including image nuggets — are miner-created and announced to the Storyteller. |
| D22 | **`mark_source_mined` replaces `mark_source_processed`:** marks one source mined; the MCP moves the *input* to `input/processed/` automatically when the last of its sources is marked (deterministic refcount). |
| D23 | **The Composer may place existing extracted images** (placement ≠ generation; resolves Q7): the asset path comes from the image nugget; `update_slide_content` validates referenced asset paths exist; layout choice follows the slide's modality mix (image-only → figure layout, image + text → side-by-side). |
| D24 | **D9 confirmed strict — the budget is a target, not a cap.** With thin material, create-first deliberately stretches the deck toward the requested length; mixed-modality slides emerge via post-budget fit/merge, never via pre-budget association. |

---

## 3. User-Facing Workflow

### 3.1 `/init-deck` — project initialization

Starts a short interview using **user decision points**, asking for:

1. **Topic** (working title; the deck's thematic focus — presented to the user by benefit
   ("guides which knowledge is extracted from your sources"), never as internal machinery — D38(e))
2. **Audience** (students, experts, management, customers, investors, general public, …)
3. **Language** (en / de / …)
4. **Slide-theme location** — built-in `default`, local folder, npm package, or GitHub URL. A
   **local** theme is copied into the deck's `theme/` subfolder and referenced as `./theme`, so
   the deck is self-contained (D38(c)). Asked early (with topic) so the Slidev install can start
   in the background during the rest of the interview (D38(b)).
5. ~~Slide-deck output folder~~ — **removed**: the deck root is the working directory (D25).
6. **Length** — the **maximum duration in minutes**; the slide budget is *derived* at ~1.5
   min/slide (per-deck-type pacing, D38(d)). An explicit slide count overrides.
7. **Deck type** — pitch / lecture / executive meeting / status report / conference talk / workshop / …
8. **General context / setting** — university course, trade fair (Messe), scientific conference, internal meeting, …

> Superseded/refined by the SPEC: D25 (no output-folder question) and **D38** (fast guard, prewarm
> + background install, local-theme localization to `theme/`, duration→slides pacing, topic wording).

Then `/init-deck`:

1. Scaffolds the deck folder structure (§5).
2. **Scans the theme** and writes the theme-capabilities block into the deck context (D16).
3. Creates the **deck context file** (§7.1) from the interview — including the derived per-agent injection blocks.
4. Instructs the user: *"Put your input files into `input/`, then run `/draft-deck`."*

No content is generated at this stage.

### 3.2 Adding inputs

The user drops files into `input/`: PDF, Markdown, plain text. If the user provides a **web URL** (conversationally or in a links file), a preparatory step copies the page content into a Markdown file in `input/` first. Already-mined inputs live in `input/processed/` and are skipped (D18/D22).

### 3.3 `/draft-deck` — drafting run

Spawns the agent team and runs the v1 pipeline (§4). On completion the team is torn down. Re-runs process only unmined inputs (D18/D22).

### 3.4 Later iteration

Post-drafting refinement is preferably conversational ("integrate the new sources", "reduce to 20 minutes", …) and triggers dedicated teams/workflows — defined later.

---

## 4. V1 Pipeline

### 4.1 Flow

```
/draft-deck  (lead session)
  │
  ├─ 1. HARMONIZE  (lead; deterministic scripts, extraction only — D21)
  │     every file in input/ (not processed/) → text-form JSON in sources/
  │     PDFs: text split per page, page numbers preserved
  │     PDF images: extracted to assets/extracted/; each image becomes
  │     its own image source (record in sources/) — no nuggets yet
  │
  ├─ 2. SPAWN TEAM
  │     first the Storyteller teammate → it creates the OUTLINE:
  │       real structural slides via MCP create_slide (empty associations),
  │       shaped by the storytelling SKILL for the deck type (invoked at
  │       runtime via the Skill tool — see §11 fact F6)
  │     then per input: one Miner teammate for its text source
  │       + one vision-Miner teammate for its image sources (D21)
  │
  ├─ 3. MINE  (miner teammates, parallel; vision miners serial over images)
  │     extract nuggets via MCP create_knowledge_nugget
  │     per nugget: SendMessage to Storyteller ("nugget <id> created")
  │     when a source is fully mined: MCP mark_source_mined (the MCP moves
  │     the input to input/processed/ once ALL its sources are mined, D22),
  │     then the miner idles
  │
  ├─ 4. STORYTELL + COMPOSE  (storyteller teammate, strictly serial)
  │     drains its mailbox one nugget at a time — see §4.2
  │     composer = fresh foreground subagent per composition (D12)
  │
  └─ 5. FINISH  (lead)
        all miners idle + storyteller mailbox empty
        → lead runs MCP validate_deck, reports results, team is torn down
```

### 4.2 Storyteller per-nugget decision logic (D9, D10)

For every nugget message, in arrival order:

1. **Budget not reached** → `create_slide` (MCP; atomic budget gate — fails if the deck just filled up), spawn a fresh Composer subagent for it (foreground), then place the slide in `slides.md` (`insert_slide` / `update_deck_order`).
2. **Budget reached, nugget fits an existing slide** → `associate_knowledge_nugget`, then spawn a Composer subagent to update that slide's content so the new nugget actually appears on it (`update_slide_content`). Nuggets may be associated to multiple slides, but scope must be tight.
3. **Budget reached, no fit** → pick the most similar existing slides and `merge_slides` (purely mechanical append + association join, **no recomposition**, D10). The merge frees a budget slot → proceed as case 1 for the incoming nugget. The Composer runs **once**, for the new slide only.

Structural slides (empty associations) are never merge candidates (D14).

While the Storyteller is blocked on a foreground Composer, incoming miner messages queue in its mailbox — natural backpressure and serialization (single writer for `slides.md` and `associations.json` order decisions).

### 4.3 Trigger relationships (v1, final)

```
lead                 → source conversion, team spawn/teardown, final validation
miner → storyteller  : SendMessage "nugget <id> created"   (IDs only, D13)
storyteller → composer: foreground subagent spawn (fresh context each time)
composer → storyteller: implicit — subagent returns, storyteller continues
```

No other agent-to-agent triggers exist in v1. Subagents cannot message teammates; the composer's completion *is* its return (§11 facts F2/F5).

---

## 5. Deck Project Directory Structure (v1)

```
deck-root/
├── deck-context.json            # context + injection blocks + theme capabilities (§7.1)
├── input/                       # unmined user-provided files (+ URL→md copies)
│   └── processed/               # fully-mined inputs — filesystem as registry (D18/D22)
├── sources/                     # converted sources: text form + image-source records (§7.2)
├── slides/
│   ├── kalman-filter--20260716-143512-847.md     # slide file (§7.3)
│   └── kalman-filter--20260716-143512-847.json   # slide state file (§7.6)
├── nuggets/                     # one JSON per Knowledge Nugget (§7.4)
├── associations.json            # slide-ID → [nugget-IDs]; empty list = structural (§7.5)
├── assets/
│   └── extracted/               # images pulled out of PDFs during source conversion
├── logs/                        # continuous crafting logs (§9)
├── theme/                       # local theme copied in for self-containment (D38(c); local themes only)
└── slides.md                    # main deck file: includes all slides in order (§7.7)
```

---

## 6. Agent Team (v1)

Agent role definitions live in the **`agents/` folder of the Slidecraft plugin (this repo)** as static templates. Roster per D12: **lead + N miner teammates + 1 storyteller teammate + composer subagents.**

### 6.1 Lead (the `/draft-deck` session — not an LLM role definition)

Runs source-conversion scripts, renders agent templates and spawns the team, monitors progress, runs final validation, tears the team down. Does not make content decisions.

### 6.2 Knowledge Miner (per input: one for the text source + one vision miner for the image sources)

- **Input:** its assigned sources (§7.2) + injected focus context (`%FOCUS-TOPIC%` etc.). Vision miners work through their input's image sources serially (D21).
- **Task:** extract atomic Knowledge Nuggets — smallest self-contained units, one central idea each, one source each.
- **Output:** nugget JSON via MCP `create_knowledge_nugget`; one SendMessage to the Storyteller per nugget; `mark_source_mined` per finished source (D22).
- **Never:** decides slide order, combines sources into one nugget, writes slide text, touches slides.
- **Open (top priority):** precise nugget content/granularity rules — Q1.

### 6.3 Storyteller (one teammate; the serial flow-control point)

- **On spawn:** creates the outline as real structural slides (D14), shaped by the storytelling skill for the deck type (loaded at runtime via the Skill tool — frontmatter preloading does not work for teammates, §11 F6).
- **Steady state:** drains its mailbox per §4.2; spawns one fresh Composer subagent per composition; owns all `slides.md` ordering.
- **Injected at spawn:** max slides/duration, deck type, audience, setting, language, topic. A resumed/idle teammate never re-injects — if the user changes the deck context, the *next* team spawn sees the new values.
- **Never:** writes slide content itself (Composer does), decides visual styling.

### 6.4 Slide Composer (fresh foreground subagent per composition)

- **Spawned by the Storyteller** with a rendered prompt: the target slide ID, its nugget IDs, deck-context values, and the theme-capabilities block.
- **Task:** compose the slide body — headline, key message, bullets, text. May **place** an existing extracted image via its image nugget's asset path (placement ≠ generation, D23); leaves **placeholders** for images that would have to be generated (never creates images). Chooses the most appropriate layout from the theme capabilities (D16), following the slide's modality mix (image-only → figure layout; image + text → e.g. side-by-side).
- **Write path:** MCP `update_slide_content` only (D15).
- **Clean context guaranteed:** every spawn is a new isolated context; nothing spills between slides (D12).

### 6.5 Dynamic prompt injection (verified mechanism, D8)

Platform facts (§11 F3/F4): agent definition files have **no native templating**, and no hook can modify a system prompt at spawn time (`SubagentStart` exists but can only inject additional context as a reminder). Therefore:

- Agent templates in `agents/` contain placeholders (`%FOCUS-TOPIC%`, `%MAX-SLIDES%`, `%DECK-TYPE%`, `%AUDIENCE%`, `%LANGUAGE%`, …).
- **The lead renders the template** (scripted, deterministic string replace against the deck context's injection blocks) **and passes the result as the spawn prompt.** For teammates spawned from an agent definition, the definition body is appended to the system prompt and the rendered values travel in the spawn prompt.
- Injection happens on **every spawn**, so context edits propagate to the next run automatically.

### 6.6 Explicitly out of scope for v1

Design Agent, Review Agent, asset/image generation, **Spectator agent**, slide-condensing cleanup agent, approval/proposal UX. The architecture must not block adding them later.

---

## 7. Structural Files / Components

### 7.1 Deck context file — `deck-context.json`

Created by `/init-deck`. Draft:

```json
{
  "schema_version": "0.3",
  "deck": {
    "topic": "Mobile Robot Localization",
    "type": "lecture",
    "audience": "master students",
    "setting": "university course",
    "language": "en",
    "max_slides": 25,
    "max_duration_minutes": 45
  },
  "theme": {
    "type": "local | github",
    "source": "../themes/iu-theme | https://github.com/...",
    "capabilities": {
      "layouts": [
        { "name": "default", "slots": ["default"] },
        { "name": "two-cols", "slots": ["default", "right"] },
        { "name": "image-right", "slots": ["default"], "props": ["image"] }
      ],
      "components": ["Callout", "Timeline"]
    }
  },
  "injection": {
    "knowledge-miner": {
      "FOCUS-TOPIC": "localization algorithms for mobile robots, sensor models, state estimation"
    },
    "storyteller": {
      "MAX-SLIDES": "25",
      "MAX-DURATION-MINUTES": "45",
      "DECK-TYPE": "lecture",
      "AUDIENCE": "master students",
      "SETTING": "university course",
      "LANGUAGE": "en"
    },
    "slide-composer": {
      "AUDIENCE": "master students",
      "DECK-TYPE": "lecture",
      "LANGUAGE": "en"
    }
  }
}
```

### 7.2 Source — `sources/<name>.json`

Every input is transcribed **before** mining, so miners never need PDF tooling. A document input yields one text source; each extracted image yields its own image source:

```json
{
  "source_id": "lidar-introduction--20260716-141002-113",
  "original_file": "input/lidar-introduction.pdf",
  "type": "pdf",
  "converted_at": "2026-07-16T14:10:02.113+02:00",
  "pages": [
    { "page": 1, "text": "..." },
    { "page": 2, "text": "..." }
  ],
  "images": [
    {
      "image_source_id": "lidar-introduction-p4-img1--20260716-141003-201",
      "path": "assets/extracted/lidar-introduction-p4-img1.png",
      "page": 4
    }
  ]
}
```

- PDF text split per page with page numbers kept (citation-precise locators). Nugget locators cite the original input filename; after mining, the input lives in `input/processed/` (D18/D22).
- Markdown/text inputs: single text block or heading-based sections.
- **Each extracted image becomes its own image source**, mined by the input's vision miner into image nuggets (§7.4, D21) — source conversion itself creates no nuggets.

### 7.3 Individual slide files — `slides/<title>--<stamp>.md`

- Slidev-compatible Markdown, conforming to the chosen theme and its layout slots.
- Filename = self-speaking title + `--` + unique fixed timestamp postfix. The title part may be renamed (via MCP `rename_slide`); the **stamp is the slide's stable ID**.

### 7.4 Knowledge Nugget — `nuggets/<stamp>.json`

```json
{
  "nugget_id": "20260716-143512-847",
  "type": "definition | concept | fact | pros | cons | example | process | image | ...",
  "brief": "LiDAR measures distance via laser light travel time (5–25 words)",
  "excerpt": "Verbatim text passage that is the basis for this nugget.",
  "source": {
    "source_id": "lidar-introduction--20260716-141002-113",
    "file": "input/lidar-introduction.pdf",
    "page": 4
  },
  "created_at": "2026-07-16T14:35:12.847+02:00",
  "created_by": "knowledge-miner"
}
```

Fixed rules: `excerpt` is verbatim (provenance anchor); `brief` is 5–25 words (MCP-enforced); PDF locators = filename + page. **Image nuggets** additionally carry the asset path, a vision-model description, all keywords/labels visible in the image, and the source locator.

**The precise content definition of Knowledge Nuggets is the top open definition task (Q1).**

### 7.5 Knowledge Association — `associations.json`

```json
{
  "deck-title--20260716-143000-001": [],
  "kalman-filter--20260716-143512-847": ["20260716-143512-847", "20260716-143601-102"]
}
```

- Slide ID → list of nugget IDs. **Empty list = structural slide** (title/agenda/quiz/recap/… — D14).
- A nugget may appear under multiple slides (tight scope). Nuggets under no slide = backlog (D1).
- Only mutated through MCP functions.

### 7.6 Slide State file — `slides/<title>--<stamp>.json`

*(Working name: **Slide State**, replacing "sidecar".)*

```json
{
  "slide_id": "kalman-filter--20260716-143512-847",
  "state": "draft | locked | needs-polishing | ...(to be defined)",
  "title": "Kalman Filter",
  "created_at": "2026-07-16T14:35:12.847+02:00",
  "updated_at": "2026-07-16T14:40:00.000+02:00"
}
```

- States bind **agents only** (D2). Knowledge/provenance lives in nuggets + associations, not here. State enum = Q2.

### 7.7 Main slide-deck file — `slides.md`

The Slidev entry point; includes all slide files in presentation order. **Order lives here**, maintained exclusively by the Storyteller through MCP ordering functions (D7). A richer deck manifest (persisted narrative notes) remains open (Q3).

---

## 8. Internal MCP: deterministic state operations

All file/state changes go through a **plugin-bundled MCP server** (auto-registered via the plugin's `.mcp.json`, available to lead, teammates, and subagents — §11 F7). Functions are deterministic scripts guaranteeing correct formats, naming, and referential integrity.

**Context economy (resolved):** ONE server suffices. Per-agent `tools:` allowlists can whitelist individual MCP functions by name (`mcp__knowledge-manager__create_knowledge_nugget`), so each agent sees only its relevant functions — no server splitting needed (§11 F8). Note: plugin-shipped agent definitions cannot declare `mcpServers` frontmatter, but the server is plugin-bundled globally anyway.

Every call is logged (§9): calling agent, action, useful payload info.

### 8.1 Confirmed function set

| Function | Behavior | Callers |
|---|---|---|
| `create_knowledge_nugget` | Builds nugget JSON; unique stamped filename (counter suffix on collision, D6); validates metadata; enforces brief word count 5–25. | Miner |
| `create_slide` | Creates slide md (title + new stamp) + empty association entry + Slide State file. **Atomic budget gate:** fails when the deck is at `max_slides` (total incl. structural, D14). | Storyteller |
| `associate_knowledge_nugget` | Registers nugget ID under slide ID; validates both exist; no duplicates. | Storyteller |
| `merge_slides` | Purely mechanical (D10): new slide file + stamp (new title is an input), re-links all nugget associations, **appends** the merged slides' content (slide "grows"), merges Slide State files, retires the old slides. No LLM, no recomposition. | Storyteller |
| `update_slide_content` | Accepts full slide body; validates frontmatter, layout against theme capabilities, referenced asset paths exist (D23), stamp/filename untouched; writes + logs (D15). | Composer |
| `insert_slide` / `update_deck_order` | Places a slide in `slides.md` / rewrites the include order; validates every slide appears exactly once. | Storyteller |
| `mark_source_mined` | Marks one source mined; moves the parent input to `input/processed/` once all its sources are mined (D18/D22); logs. | Miner |
| `validate_deck` | Consistency check: md↔state pairs, associations point to existing files, stamps unique, slides.md complete and duplicate-free, budget respected. | Lead |

### 8.2 Proposed additions (to confirm)

| Function | Why |
|---|---|
| `rename_slide` | Renames the title part keeping the stamp; updates `slides.md` include and references. |
| `set_slide_state` | Validated state transitions (against Q2 state machine); logged. |
| `get_deck_overview` | Ordered slide list + titles/states/nugget briefs — cheap context for Storyteller decisions (fit-checking, merge candidates). |
| `get_slide` | One slide's markdown + state + associated nuggets (Composer input package). |
| `list_unassigned_nuggets` | The backlog pool. |
| `dissociate_knowledge_nugget` | Inverse of associate (cleanup/corrections). |
| `retire_slide` | Explicit, logged removal path (merge byproduct; keeps provenance). |

### 8.3 Source-conversion tooling

`source_converter.py` (PDF→paged JSON, image extraction into image sources, URL→markdown — extraction only, no vision calls, D21) runs in the **lead** before team spawn. It is a plain pipeline script, not part of the knowledge manager.

---

## 9. Logging

Continuous, append-only logs in `logs/`:

- **Action log** (`logs/actions.jsonl`): one entry per MCP call — timestamp, calling agent, function, key payload (nugget brief on create/associate, slide IDs on merge), result/error.
- **Pipeline log** (`logs/pipeline.jsonl`): phase transitions, teammate spawn/idle/shutdown, per-source nugget counts, slides created/merged, validation results.

Purpose: observability, debugging, and the raw material for later idempotency/audit features. Exact schemas defined with the MCP contracts (Q6).

---

## 10. Out of Scope for v1 (parked, not discarded)

- Image/diagram/asset *generation* (the Composer leaves placeholders for images that would have to be generated; placing existing extracted images is allowed per D23).
- Polishing workflow; condensing overfull (merged) slides.
- Spectator agent; Design and Review agents (v1.1+, reusing repo components per D5).
- Change proposals / approval UX.
- Full idempotency layer beyond D18's filesystem registry.
- Incremental workflows beyond "re-run mines only new sources".

---

## 11. Verified Platform Facts (Claude Code, 2026-07)

The grill was grounded against current docs (agent teams page + capability fact-check). Design-relevant facts:

| # | Fact | Consequence here |
|---|---|---|
| F1 | Subagents are strictly run-to-completion; resumable later with context intact (SendMessage). | "Waiting" agents must be teammates, not subagents. |
| F2 | **Agent teams** (experimental, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`): teammates are full sessions that idle, wake on messages, message each other directly (mailboxes), share a task list; team is torn down with the session. | The execution model of D11. Storyteller "waits for nuggets" for real. |
| F3 | `SubagentStart` hook exists but **cannot modify system prompts/agent definitions**; only additional-context injection. | Placeholder rendering happens in the lead before spawn (§6.4). |
| F4 | Agent definition files have **no native templating**. | Same as F3: scripted render → spawn prompt. |
| F5 | **In-process teammates cannot run background subagents** (foreground only; background spawn errors — a teammate's background work can't outlive the lead's process). Subagents cannot message teammates; results return to the spawner. Split-pane mode needs tmux/iTerm2 — impractical on Windows. | Storyteller composes serially, foreground (D12). "Kick off + inbox on finish" exists only for the lead — rejected in favor of the serial model. |
| F6 | Teammates spawned from agent definitions honor `tools:` and `model:`, but **`skills:` and `mcpServers:` frontmatter are ignored**; the definition body is appended to the system prompt. | Storytelling skills are invoked at runtime via the Skill tool (§6.3); MCP comes from the plugin bundle. |
| F7 | Plugins can bundle MCP servers (`.mcp.json`, auto-started, available to subagents/teammates). | The Knowledge-Manager MCP ships in the Slidecraft plugin. |
| F8 | Per-agent `tools:` allowlists can whitelist **individual MCP tools by name**. | One MCP server, per-role visibility (§8). |
| F9 | Known team limitations: no team resumption via `/resume`, task-status lag, slow shutdowns, one team per session, no nested teams, permissions bubble to the lead. | Accepted for v1 (experimental dependency); file-based state (D13) keeps a workflow-based fallback possible. |

---

## 12. Open Questions (next definition tasks, in priority order)

**Q1 — Knowledge Nugget content definition** *(user-flagged as must-define)*: granularity rules (min/max size), the type enum, tables/formulas handling, excerpt length bounds, near-duplicate handling across sources.

**Q2 — Slide State machine**: state enum (`draft`, `locked`, `needs-polishing`, …), per-state agent permissions (D2), transition triggers.

**Q3 — Deck narrative persistence**: the Storyteller's narrative reasoning lives only in its (torn-down) context. Do incremental workflows later need a persisted outline/narrative artifact, or does `get_deck_overview` + the structural slides suffice as recoverable context?

**Q4 — Storyteller fit/merge heuristics**: once the budget is full — how "fits an existing slide" and "most similar slides" are judged (baseline: titles + nugget briefs via `get_deck_overview`), and what happens when even merging finds no sensible candidates.

**Q5 — Error handling in the serial loop**: composer subagent fails mid-slide, `create_slide` race on the last budget slot, a miner dies mid-source (the source must not be marked mined, so its input never moves to `processed/`), storyteller context exhaustion on long runs — define retry/degradation per case.

**Q6 — MCP function contracts**: finalize §8.1/§8.2 signatures, validation rules, error codes, log schemas.

**Q7 — RESOLVED as D23**: the Composer may place existing extracted images (placement ≠ generation); `update_slide_content` validates referenced asset paths; layout follows the slide's modality mix.

**Q8 — Structural slide content maintenance**: the agenda slide is created before content exists — who refreshes it at the end of the run (storyteller finalization step vs. left to later polishing)?

**Q9 — Storytelling skills**: author the first skill (academic-lecture, matching the primary use case), define its contract with the Storyteller (outline patterns, section ordering rules); pitch-deck second.

**Q10 — Deferred earlier questions**: input *change/deletion* behavior (D18 covers only *new* inputs), duration↔slide-count precedence, approval interaction, scale expectations, multi-user packaging.

---

## 13. Suggested Next Working Session

1. Define Knowledge Nugget content + JSON schema precisely (Q1).
2. Define the Slide State machine (Q2).
3. Finalize the Knowledge-Manager-MCP contracts (Q6).
4. Define Storyteller fit/merge heuristics + error handling (Q4, Q5).
5. Translate into implementation tickets in `tickets/unspecified/`.
