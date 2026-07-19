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
_Avoid_ (as nugget synonyms): claim, fact, finding, insight, chunk, snippet, evidence
sidecar — the [[concept type]] enum values `finding`/`claim-support` are unaffected

**Image nugget**:
A knowledge nugget mined from an image source: it carries a `figure_type`, an `information`
digest of what the figure teaches, a `description` (1–2 sentences, **content first, then
form** — for placement + alt-text, never a label inventory — D42), and **`visible_text`** —
every text string in the image transcribed verbatim, which is the image's provenance
anchor. At persist time the knowledge manager **denormalizes `asset` (public path) and
`context_text` (nearest text block) onto it** from the source record (D45), so composition
never joins across files. A decorative image (logo, rule, background) yields no nugget.
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
language, theme location, length (**max duration**; slides derived at ~1.5 min/slide, D38),
deck type, setting — whose answers become the deck context. (No output-folder question — the
deck root is the working directory, D25. Theme is asked early so the Slidev install can run in
the background during the rest of the interview, D38.)
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
the **Lead workflow invokes a Composer** (assemble → invoke → persist, D40/D41) to
recompose the merged slide (D31 — the script never writes prose; the Composer always runs
after). Routine, not exceptional. Sibling move:
**parking** a lower-priority slide instead of merging (Triage, D34).
_Avoid_: combine, condense, rewrite

**Theme capabilities**:
The scanned inventory of a theme's layouts, slots, and components, written into the deck
context at `/init-deck`. The Composer chooses from it; the knowledge manager validates
against it, never chooses.
_Avoid_: theme features, layout catalog

**Injection block**:
A per-role set of deck-specific values in the deck context (`FOCUS-TOPIC`, `AUDIENCE`, …,
plus the per-role executor/model choice — D44). The knowledge manager's **assemble**
subcommands fill them into the role's prompt template when rendering a [[brief]] (D40).
Context edits therefore reach the next invoke, never a running one.
_Avoid_: template variables, parameters

**Brief**:
The fully **self-contained prompt** a role receives — role template + injection values +
the routed data itself (source text for a miner; nugget digests for the Storyteller; one
slide's routed fields for the Composer — D42). Rendered deterministically by the knowledge
manager (`mine-brief` / `plan-brief` / `compose-brief`); contains no file paths to read, no
scripts to call, no IDs to chase, so the same brief runs on any executor (D40/D44).
_Avoid_: spawn prompt, rendered template, context package

**Invoke shim**:
The one deliberately nondeterministic seam: `invoke(role, brief, image?)` → structured
output. Two adapters — the Open WebUI client (OpenAI-compatible chat; images as base64
data-URL content parts) and a Claude subagent. Defaults: miners + Composer → EU-hosted
`gdpr.gpt-5.6-sol`; Storyteller → Claude subagent (D44). Wraps the bounded rejection loop:
persist rejects → re-invoke with the error appended, cap 2, then the per-role terminal —
miner: drop nugget + flag; composer: park slide + flag; storyteller: abort the run with a
flagged error (D44).
_Avoid_: executor layer, LLM gateway, model router

**Concept type**:
The slide's declared didactic function, one enum value (`structural`, `motivate`, `define`,
`compare`, `relationship`, `process`, `cause-effect`, `finding`, `categories`,
`claim-support`). The Storyteller may plan it as an `intended_function` hint; the Composer
sets the final value from the actual content; the knowledge manager stamps it into the
slide state file, where later critics read it (D43).
_Avoid_: slide function, teaching pattern, template type

**Physical name**:
A theme's real layout file or slot name (`slide5`, `::body-16::`) — the only names Slidev
renders reliably. Slide files always use physical names (May lesson: runtime semantic
aliases fail). Since D43 this is a **script guarantee**: the Composer emits semantic roles;
the knowledge manager's `write-slide` maps them to physical names — no LLM ever emits (or
sees) a physical slot name.
_Avoid_: semantic alias (in rendered files)

**Presenter notes**:
The Slidev speaker notes of a slide — the trailing `<!-- … -->` comment, shown only in the
presenter view. By default they are **not** authored by the Composer: when the composed body
leaves them empty, the knowledge manager (`write-slide` in the composer pipeline;
`set-content` on direct markdown writes) fills them **verbatim from the slide's nuggets' raw
knowledge** (`raw_text` / an image's `visible_text`, each with its source locator), so the
presenter keeps the full source behind the telegraphic body (D39). The Composer may write its
own notes to override; a structural slide (no nuggets) gets none. A deliberate, verbatim-only
carve-out to "the knowledge manager never writes prose" — the notes are copied provenance, not
composed prose.
_Avoid_: speaker comment, slide notes payload, footnotes

### Agent roles

**Lead** (the orchestrator):
The `/draft-deck` **workflow** itself: converts inputs to sources, runs every role through
**assemble → invoke → persist** (D40) — miners, the Storyteller planner, then per plan step
the Composer — and executes all mutations via the knowledge manager; the [[invoke shim]]
wraps the cap-2 retry → park/drop/abort loop (D44). Validates at the end. Deterministic
control flow; makes no content decisions.
_Avoid_: manager, coordinator

**Knowledge miner**:
The pure-function role that mines nuggets: one invoke per text source (the source text is
injected into its [[brief]] — it never opens files), plus one vision invoke **per extracted
image**, the image passed directly (D45). Returns nugget JSON; the knowledge manager
persists it (verbatim guard, stamps, image denormalization). Runs on OWUI by default (D44).
Never touches slides.
_Avoid_: extractor, harvester, teammate

**Storyteller**:
The single pure-planner role that owns deck structure. It reads all nuggets **as digests
only** (`title` + `information`, plus an image's `figure_type`/`description` — never
`raw_text`, `visible_text`, or assets — D42) and returns a **structured plan** — the
outline (structural slides) plus, per nugget, a create / associate / merge / **park**
(Triage, D34) decision and an optional `intended_function` hint ([[concept type]] enum) —
which the Lead workflow executes. Owns slide order. Emits a full plan on a fresh draft, a
delta plan on an incremental/refinement run (D32). Skips `locked` slides (proposes
instead). Never writes slide content, never spawns composers, never sees composed bodies
(D41). Runs as a Claude subagent (D44).
_Avoid_: narrator, director

**Slide composer**:
The pure-function role invoked once per composition: writes one slide from its [[brief]] —
the verbatim `raw_text` of its slide's nuggets plus their `source`/`page` locators for the
citation footer (never the `information` digest, never `visible_text` — D42), an image's
`asset`/`description`, or for an image-only slide the
`context_text` (headline only, no body). Chooses the layout that fits the modality mix and
returns **semantic role-keyed JSON** with a final [[concept type]]; the knowledge manager's
`write-slide` does all physical Slidev assembly (D43). Leaves the [[presenter notes]] empty
by default — the knowledge manager fills them verbatim from the nuggets' raw knowledge
(D39). Runs on OWUI by default (D44). One slide, then it returns.
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
v1 enum: `pending` (skeleton, body not yet written — marks in-flight or interrupted
composition; `validate` flags any left at run
end), `draft` (composed, pipeline-owned, agents may modify), `locked` (composed,
user-owned, agents *propose* not edit — set **only by explicit user lock**). More states
added only after testing. **Active-vs-parked is not a state** — it lives in `slides.md` as
a commented include (D34). Dropped: `needs-polishing` / `reviewed` (no workflow branches
on them yet).
_Avoid_: sidecar, status, lock flag

**Hand-edit guard**:
The protection for un-`locked` slides the user has hand-edited. The knowledge manager
stamps a `content_hash` on every write; a deterministic pre-tool hook on `set-content` /
`write-slide` / `merge-slides` / `park-slide` re-hashes the target and, on a mismatch, prompts the user
(AskUser) before letting an agent overwrite it. Separate from `locked`: `locked` is a
persistent user intent, the hand-edit guard is a per-call safety net checked at edit time.
_Avoid_: auto-lock, dirty flag

**Knowledge manager**:
The deterministic script suite (`km.py`) through which every deck mutation **and every
brief assembly** flows — validating, logged. Mutation subcommands: `create-nugget` (+ image
denormalization, D45), `create-slide`, `merge-slides`, `park-slide` / `unpark-slide`,
`set-content`, `write-slide` (semantic → physical, D43), `validate`. Assemble subcommands:
`mine-brief`, `plan-brief`, `compose-brief` (D40). Called by the **orchestrator** — roles
are pure functions and never call scripts themselves (D40). Payloads are passed as files,
never CLI args (D28). Roles decide; the knowledge manager executes. (No MCP in v1 — D27.)
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
