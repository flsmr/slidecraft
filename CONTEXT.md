# Slidecraft

A Claude Code toolkit that turns source material into structured, traceable, and reusable
Slidev decks via a workflow of agents whose file and state mutations run through
deterministic scripts (the knowledge manager, `km.py`). This glossary is the ubiquitous
language of the agentic presentation framework (`architecture_proposal.md` = what/why,
`SPEC.md` = how).

## Language

### Building blocks

**Toolkit**:
The engine, installed once per machine **via an npx installer** (a skill-repo, not a
plugin — the MCP that once justified a plugin is gone): registered agent definitions,
storytelling + craft skills, deterministic scripts, the knowledge manager, the workflows,
and the `/init-deck` / `/draft-deck` / `/improve-deck` commands. Contains no visuals, no
theme-specific content, no course content.
_Avoid_: plugin, tool, framework, driver

**Theme**:
The visual identity as its own repository (npm package `slidev-theme-*`, referencable via
GitHub link or local path at `/init-deck`): physical layouts, styles, fonts, colors, plus
the theme's own style guide and visual conventions. Whatever only makes sense for one theme
lives in its repo; the plugin stays generic. A theme knows nothing about how decks are
composed. A **local** theme is copied into the deck's `theme/` subfolder at `/init-deck`
(referenced as `./theme`) so the deck is self-contained (D38); builtin/npm/github themes stay
registry-resolved.
_Avoid_: theme pack, template, design, corporate identity

**Storytelling skill**:
The per-deck-type shape definition (academic-lecture, pitch, …): outline patterns, section
ordering rules, which structural slides fit. Loaded by the Storyteller at outline time via
the Skill tool.
_Avoid_: skeleton, deck-style skill, blueprint, deck template

**Deck**:
One presentation: a self-contained output folder (per-slide markdown files, import
manifest, resources, references.bib). An artifact, never a template.
_Avoid_: presentation project, slideset

### Knowledge concepts

**Input**:
A user-provided document (PDF, Markdown, text, URL capture) dropped into `input/`, awaiting
source conversion. After mining, the original moves to `input/processed/` — the filesystem
is the registry of what has been mined.
_Avoid_: reference, source file, material

**Source conversion**:
The deterministic lead phase (script: `source_converter.py`) that turns inputs into
sources: PDF → paged text, webpage → Markdown, images extracted as image sources. Pure
scripts — no LLM judgment, no nuggets created.
_Avoid_: harmonization, preprocessing, ingestion, parsing

**Source**:
A minable artifact produced by converting an input: the paged text form of a document
(`sources/<name>.json`) or a single extracted image (record in `sources/`, asset in
`assets/extracted/`). Miners consume sources; all nugget provenance points at them. An
input counts as mined when every source derived from it is mined.
_Avoid_: document, reference, harmonized reference, resource, deposit

**Knowledge nugget**:
The unit of mined source knowledge: **one coherent block of teachable material on a single
topic — roughly one slide's worth**, extracted from exactly one source. It carries a
condensed, restructured `information` digest (the miner's own teaching-ready wording) and
is anchored by a **contiguous verbatim passage** (`raw_text` / an image's `visible_text`)
with a precise locator. NOT a single claim or sentence — a source section or topic block is
one nugget; a list in the source is one nugget, never one per item (a 5-page chapter yields
~6–12, not dozens). The same idea in two sources yields two nuggets — deduplication is a
slide-level concern, never a nugget-level one.
_Avoid_: claim, fact, finding, insight, chunk, snippet, evidence sidecar

**Image nugget**:
A knowledge nugget mined from an image source: it carries the asset path, a `figure_type`,
an `information` digest of what the figure teaches, a neutral `description` (for placement
+ alt-text), and **`visible_text`** — every text string in the image transcribed verbatim,
which is the image's provenance anchor. A decorative image (logo, rule, background) yields
no nugget.
_Avoid_: figure nugget, asset, visual

**Backlog**:
All nuggets that no slide references. Now **largely vestigial**: every nugget always gets a
slide, and low-priority material is hidden as a **parked slide** (D34), not left unplaced.
Backlog therefore only appears transiently during corrections (a dissociate without a
re-associate). Hidden knowledge is visible parked slides, not an abstract pool.
_Avoid_: pool, orphans, unused nuggets

### Composition concepts

**Structural slide**:
A slide that gives the deck its shape instead of carrying source knowledge: cover, agenda,
section divider, recap, quiz, references, thank-you. Identified by an empty knowledge-nugget
association list — a structural slide cites no sources.
_Avoid_: framing slide, non-content slide, scaffolding slide, template slide

**Decision point**:
Claude Code's structured option-list question (the AskUserQuestion mechanism) put to the
user. The `/init-deck` interview is a sequence of decision points — topic, audience,
language, theme location, length, deck type, setting — whose answers become the deck
context. (No output-folder question — the deck root is the working directory, D25.)
_Avoid_: prompt, dialog, free-form question

**Deck context**:
The per-deck record of every `/init-deck` decision plus what is derived from it: the
interview answers, the per-agent injection blocks, and the scanned theme capabilities
(`deck-context.json`).
_Avoid_: recipe, config, settings, manifest

**Budget**:
The deck's slide-count target from the deck context — a target, not merely a cap:
create-first deliberately stretches thin material toward it, and merging frees slots once
it is full. Structural slides count against it.
_Avoid_: limit, cap, quota

**Merge**:
The consolidation of two content slides into a new one to free a budget slot: the knowledge
manager mechanically **unions their nugget associations** and retires the originals, then
the Storyteller spawns a **Composer to recompose** the merged slide (D31 — the script never
writes prose; the Composer always runs after). Routine, not exceptional. Sibling move:
**parking** a lower-priority slide instead of merging (Triage, D34).
_Avoid_: combine, condense, rewrite

**Theme capabilities**:
The scanned inventory of a theme's layouts, slots, and components, written into the deck
context at `/init-deck`. The Composer chooses from it; the knowledge manager validates
against it, never chooses.
_Avoid_: theme features, layout catalog

**Injection block**:
A per-role set of deck-specific values in the deck context (`FOCUS-TOPIC`, `AUDIENCE`, …).
The static role/craft lives in a **registered subagent definition** loaded by the runtime
(never in the orchestrator's context); the orchestrator passes only these values in the
**small spawn prompt** at every spawn (D29). Context edits therefore reach the next run,
never a running agent.
_Avoid_: template variables, parameters

**Physical name**:
A theme's real layout file or slot name (`slide5`, `::body-16::`) — the only names Slidev
renders reliably. Slide files always use physical names (May lesson: runtime semantic
aliases fail).
_Avoid_: semantic alias (in rendered files)

### Agent roles

**Lead**:
The `/draft-deck` **workflow** itself: converts inputs to sources, spawns the miners and the
Storyteller, executes the Storyteller's plan via the knowledge manager, spawns the
Composers, validates. Deterministic control flow; makes no content decisions.
_Avoid_: manager, coordinator

**Knowledge miner**:
The teammate that mines nuggets from assigned sources: one per text source, plus one vision
miner per input's image set. Announces every nugget to the Storyteller; never touches
slides.
_Avoid_: extractor, harvester

**Storyteller**:
The single agent that owns deck structure. It reads all nuggets and returns a **structured
plan** — the outline (structural slides) plus, per nugget, a create / associate / merge /
**park** (Triage, D34) decision — which the Lead workflow executes. Owns slide order.
Emits a full plan on a fresh draft, a delta plan on an incremental/refinement run (D32).
Skips `locked` slides (proposes instead). Never writes slide content.
_Avoid_: narrator, director

**Slide composer**:
The fresh subagent spawned per composition: writes one slide's body from its nuggets and
the deck context, choosing the layout that fits the modality mix. One slide, then it
returns.
_Avoid_: author, writer, slide generator

### State & bookkeeping

**Stamp**:
An artifact's stable identity: its millisecond-precision creation timestamp
(`20260716-143512-847`; counter suffix on collision). Titles and filenames may change — the
stamp never does.
_Avoid_: UUID, GUID

**Association**:
The slide → nuggets link (`associations.json`) recording which nuggets a slide presents. A
nugget may serve several slides; an empty list marks a structural slide.
_Avoid_: mapping, linkage

**Slide state**:
The per-slide lifecycle value (`slides/<title>--<stamp>.json`) governing what agents may
change automatically. It binds agents only — the user may hand-edit any slide in any state.
v1 enum: `pending` (skeleton, body not yet written — an in-flight-composition guard so a
reacting Storyteller won't touch a slide mid-compose; `validate` flags any left at run
end), `draft` (composed, pipeline-owned, agents may modify), `locked` (composed,
user-owned, agents *propose* not edit — set **only by explicit user lock**). More states
added only after testing. **Active-vs-parked is not a state** — it lives in `slides.md` as
a commented include (D34). Dropped: `needs-polishing` / `reviewed` (no workflow branches
on them yet).
_Avoid_: sidecar, status, lock flag

**Hand-edit guard**:
The protection for un-`locked` slides the user has hand-edited. The knowledge manager
stamps a `content_hash` on every write; a deterministic pre-tool hook on `set-content` /
`merge-slides` / `park-slide` re-hashes the target and, on a mismatch, prompts the user
(AskUser) before letting an agent overwrite it. Separate from `locked`: `locked` is a
persistent user intent, the hand-edit guard is a per-call safety net checked at edit time.
_Avoid_: auto-lock, dirty flag

**Knowledge manager**:
The deterministic script suite (`km.py`, subcommands `create-nugget`, `create-slide`,
`merge-slides`, `park-slide` / `unpark-slide`, `set-content`, `validate`) through which
every deck mutation flows — validating, logged. Called by agents via an injected absolute
path (`%KM%`); prose bodies are passed as files, never CLI args (D28). Agents decide; the
knowledge manager executes. (No MCP in v1 — D27.)
_Avoid_: MCP server, state manager, file layer, backend

### Review & grounding concepts

**Image-critic**:
The devil's-advocate reviewer for non-photographic figures (diagrams, infographics, mind maps, charts,
redrawn figures). It reads what is actually rendered, cross-checks against the slide's intent and its
associated nuggets, and reports text / colour / shape / logic / hygiene defects. Report-only. Primary
runner: `scripts/image_critic.py` on a SINGLE vision model (GPT-5.6 sol via OWUI); it is the
`image-critic` pass of the improve-deck polish chain. See `agents/image-critic.md`.
_Avoid_: image checker, figure linter

**Didactic-critic**:
The devil's-advocate TEACHING reviewer. Where the grounding-critic checks that facts are true and the
image-critic checks that figures are clean, the didactic-critic asks whether each content slide carries
ONE clear, self-explanatory message a first-time student grasps from the title + lead + figure alone
(presenter muted). It reads the deck's study goals + the slides' associated nuggets, and flags no-message slides,
cryptic bullets, **name-drop lists** (3+ examples with no stated concept — even when every name is
grounded), trivia bullets, goal-orphans, and should-be-visual slides. Report-only; it is the
`didactic-critic` pass of the review chain. The paired **didactic contract** in the authoring
prompts prevents the failure at authoring time. See `agents/didactic-critic.md`.
_Avoid_: content reviewer, slide-critic (mechanical-form pass)
