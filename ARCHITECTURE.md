# Slidecraft — Architecture

The **what/why** of Slidecraft. Companion docs: `SPEC.md` (the *how* — the `km.py`
contract, pipeline steps, decisions D25–D47) and `CONTEXT.md` (the canonical
vocabulary). Where this doc and SPEC.md disagree on mechanism, **SPEC.md wins** —
it is grounded in working prototypes.

> This file supersedes the former `architecture_proposal.md` (decisions D1–D24).
> The pivot from that proposal's agent-team/MCP design to the current
> pure-function-roles pipeline is recorded in the appendix.

## 1. Mission & core guarantees

Slidecraft turns source material into structured, traceable, and reusable
presentation slides.

Users place input files (PDF, Markdown, web URLs, later spreadsheets/images) into
an `input/` directory. The pipeline converts these inputs into sources, extracts
**Knowledge Nuggets**, assigns them to slides, composes slide content, and
assembles a Slidev deck — under global constraints (topic, audience, deck type,
setting, language, length) captured in an initial interview.

Core guarantees:

- Every slide remains traceable to its source material (full provenance).
- Slides in protected lifecycle states are never silently rewritten by agents.
- New source material is integrated deterministically.
- All file/state mutations go through the deterministic, logged **knowledge
  manager (`km.py`)**, so the system cannot corrupt its own bookkeeping. *(No MCP
  — D27; see appendix.)*

## 2. Ubiquitous language

`CONTEXT.md` is the single canonical glossary (nugget, association, slide state,
budget, brief, variant, …). This doc does not restate terms — read it there.

## 3. The pipeline — plan then execute

`/draft-deck` runs a **deterministic orchestration** over five phases; the only
nondeterministic step is the executor invoke behind a shim. Every role runs the
same seam — **assemble → invoke → persist** (D40):

1. **Convert** — inputs → `sources/` (paged text + extracted images). Deterministic.
2. **Mine** — one invoke per text source + one per extracted image → validated
   **nuggets** (verbatim guard).
3. **Plan** — one **Storyteller** invoke returns a *structured plan* (structural
   slides; per content slide the nugget ids + a create / associate / merge / park
   decision). Validated into `plan.json`.
4. **Execute + compose** — the orchestrator walks the plan via `km`, and after
   every create / merge / unpark invokes the **Composer** on that slide.
5. **Validate** — `km validate` gates the deck; report.

The authoritative step list, exit codes, and terminals live in **SPEC.md §7**.
The durable *why* behind placement: **create-first, budget-is-a-target** — with
thin material the deck is stretched toward the requested length, and merge/park
free slots once it is full (never pre-budget association). Every nugget always
gets a slide (Triage — merge, or **park** into the rendered *Backup Slides*
appendix).

## 4. Roles as pure functions

Each LLM role is a **pure function**: a fully self-contained brief in, structured
output out — no file reads, no script calls, no IDs chased inside a prompt (D40).
The roles: **knowledge-miner**, **image-miner** (one call per image), the
**Storyteller** (a pure *planner* — sees only nugget digests, never composes),
and the **Slide composer** (one slide at a time, emits semantic role-keyed JSON).
They run behind the **executor shim** — Open WebUI by default, a Claude subagent
for the Storyteller (D44). See `CONTEXT.md` (Agent roles) and SPEC.md §2/§4.

## 5. The knowledge manager (`km.py`)

The deterministic boundary through which **every** deck mutation and **every**
brief assembly flows — validated and logged. Roles decide; `km` executes; it
never writes slide prose (the narrow, verbatim carve-outs — presenter notes D39,
Backup digests D46 — copy already-distilled miner output, they do not compose).
Payloads travel as **files, never CLI args** (D28). The subcommand contract is
**SPEC.md §5**.

*Why not an MCP server?* The one hard advantage of MCP (escaping-free prose
payloads) is neutralised by the body-file convention, and the prototype ran
end-to-end on plain scripts — so v1 is a subcommand CLI, revisited only if
escaping errors accumulate (D27).

## 6. The deck on disk

A deck is self-contained under the working directory (`deck-context.json`,
`input/`, `sources/`, `nuggets/`, `slides/`, `associations.json`, `plan.json`,
`slides.md`, `public/extracted/`, `logs/actions.jsonl`, a localized `theme/`, and
the `show_slide_deck.{cmd,sh}` launchers). The authoritative tree + each file's
schema is **SPEC.md §3 / §5–§6**.

## 7. State & provenance

- **Stamp** — a millisecond creation timestamp is an artifact's stable identity;
  titles and filenames may change, the stamp never does.
- **Association** — `associations.json` links each slide to its nuggets (empty
  list = structural slide).
- **Slide state** — `pending / draft / composed / locked`, with `parked` as a
  transient overlay; binds agents only, the user may hand-edit anything (D36).
- **Hand-edit guard** — a content-hash pre-tool check protects un-`locked`
  hand-edits from agent overwrites (D36).
- **Variants** — a slide may hold coexisting renderings; the active one is the
  postfix-less `slides/<sid>.md`, alternatives are `<sid>_vN.md`, and selection
  is a pure rename (D47). See `CONTEXT.md` + ADR-0004.

## 8. Deferred / not yet built

- **Variant *creation* from composer lanes** (image-gen vs. diagram vs. text) —
  the D47 *mechanics* (cycling, merge-preserves-predecessors) are specified;
  differentiated creation is later. Until then variants arise only from merge.
- **`/improve-deck`** quality/polish chain — critics (grounding, image, didactic)
  → auto-fix drafts / propose on locks — and its **image generation** lane
  (`image-composer`), plus the **hand-edit guard hook** and **reactive-context
  dispatch** (D36/D37).
- **The `/draft-deck` Workflow form** (D35) — v1 ships command-driven
  orchestration over the same seams.
- Live-streaming via agent teams (observability only); Spectator/approval UX.

## Appendix — superseded design history

The project began as an agent-team + internal-MCP design (the old
`architecture_proposal.md`, D1–D24). The current pipeline replaced it; the map:

| Old design | Replaced by | Now |
|---|---|---|
| Internal **MCP** for state ops (D15, §8) | **D27** | Plain `km.py` subcommand CLI |
| **Agent teams** + SendMessage execution (D11, D13) | **D35 / D40** | Deterministic orchestration; files carry, no mailboxes |
| Storyteller **spawns Composer** subagents (D12) | **D41** | Storyteller is a pure planner; the orchestrator executes the plan |
| Merge = mechanical append, **no recompose** (D10) | **D31** | Merge always recomposes (and, D47, keeps predecessors as variants) |
| Lead renders templates at spawn time (D8) | **D40** | `km` assemble subcommands render self-contained briefs |
| Backlog **pool** for set-aside knowledge (D1) | **D34 / D46** | Visible *Backup Slides* appendix, not an abstract pool |

Verified platform facts and the original open-questions list from the proposal are
historical; the live open tensions are carried in **SPEC.md §8**.
