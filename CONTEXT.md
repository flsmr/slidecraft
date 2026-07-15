# Slidecraft

A Claude Code plugin that turns raw course material into grounded, presentable Slidev decks
via canonical agent workflows wrapped in deterministic scripts. This glossary is the
ubiquitous language for the modularization concept (plugin / theme pack / skeleton / deck).

## Language

### Building blocks

**Plugin**:
The engine, installed once per machine: canonical workflows, agents, deterministic scripts,
and the new-deck interview. Contains no visuals, no deck structure, no course content.
_Avoid_: tool, framework, driver

**Theme**:
The visuals only: an npm package (`slidev-theme-*`) of physical layouts, styles, fonts, and
colors. A theme knows nothing about how slides are composed into a deck.
_Avoid_: template, design, corporate identity

**Theme pack**:
The distribution unit and repo: one theme package plus the skeletons written for it
(`slidev-theme-<name>/` + `skeletons/`). Downloading a theme pack brings compatible
skeletons along; both evolve in the same version history.
_Avoid_: theme repo, library, collection

**Skeleton**:
A fully self-contained deck structure definition inside a theme pack: skeleton.json (the
ordered framing-slide sequence, decision points, workflow configuration), the framing-slide
templates (in the theme's physical names — compatible by construction), its own
author-guide.md (house style), and diagram-style.md (AI-visual rules). One skeleton = one
copyable folder; duplication between skeletons is accepted for independence.
_Avoid_: deck type, blueprint, format, outline

**Deck**:
One presentation: a self-contained output folder (per-slide markdown files, import
manifest, resources, references.bib). An artifact, never a template.
_Avoid_: presentation project, slideset

### Composition concepts

**Framing slide**:
A skeleton-defined non-content slide (cover, agenda, section divider, exam focus, summary,
thank-you). Each is opt-out-able at deck creation; content slides always exist and are
never framing slides.
_Avoid_: scaffolding slide, template slide

**Decision point**:
A question the new-deck interview must ask the user, rendered as a checkbox/option list.
Decision points are defined by the plugin (theme choice, skeleton choice, slide opt-outs)
and by skeletons (e.g. title, course code, date for the cover).
_Avoid_: prompt, dialog, setting

**Workflow configuration**:
The skeleton's parameters for the canonical workflows: which extension points run and how
(e.g. `citations: apa-7th`, galleries on/off). Configures, never redefines, control flow.
_Avoid_: hooks, overrides, plugins

**Extension point**:
A named, plugin-defined step in a canonical workflow that a skeleton may switch on/off or
parameterize. The set of extension points is fixed by the plugin.
_Avoid_: hook, callback

**Recipe**:
The per-deck record of every decision: theme pack + skeleton (with version), slide
opt-outs, all decision-point answers, sections, and enrichment settings
(`<deck>/resources/recipe.json`). Decks are independent artifacts: skeleton updates never
propagate; the recipe makes the creation re-runnable.
_Avoid_: config, settings, manifest

**Physical name**:
A theme's real layout file or slot name (`slide5`, `::body-16::`) — the only names Slidev
renders reliably. Skeleton templates always use physical names (May lesson: runtime
semantic aliases fail).
_Avoid_: semantic alias (in rendered files)

### Review & grounding concepts

**Evidence sidecar**:
The per-slide raw-reference record: `<deck>/resources/evidence/<slug>.json`, same basename as the
slide markdown. Holds each claim's source key + locator + verbatim excerpt, and each figure's
intended labels / relationships / `must_not` traps. The written spec reviewers check against instead
of re-deriving the truth. Authoring workflows emit it; `scripts/write_evidence.py` persists/merges it;
grounding-critic and image-critic read it. See `references/evidence-sidecars.md`.
_Avoid_: source note, grounding file, metadata

**Consistency contract**:
The visual-language rules in a skeleton's `diagram-style.md` (one shape per role, one connector style,
merged lines share one arrowhead, one justified accent, no decorative marks, fill the canvas, uniform
spacing/margins, chart harmonisation, scope fidelity). The SINGLE source of truth for both sides: the
figure generator (`scripts/gen_figure.py`) pastes it into every prompt, and the image-critic enforces it.
_Avoid_: style guide, design rules (when referring specifically to the contract)

**Image-critic**:
The devil's-advocate reviewer for non-photographic figures (diagrams, infographics, mind maps, charts,
redrawn figures). It reads what is actually rendered, cross-checks against the slide's intent and the
evidence sidecar, and reports text / colour / shape / logic / hygiene defects. Report-only. Primary
runner: `scripts/image_critic.py` on a SINGLE vision model (GPT-5.6 sol via OWUI); it is the
`image-critic` pass of the improve-deck polish chain. See `agents/image-critic.md`.
_Avoid_: image checker, figure linter
