---
description: Run the drafting pipeline over the current deck — convert new inputs to sources, mine knowledge nuggets, plan the deck structure, and compose the slides. Re-runnable — it processes only unmined inputs and integrates new nuggets into the existing deck. Requires an initialized deck (run init-deck first) with files in input/.
argument-hint: (run inside an initialized deck folder)
---

# Draft Deck

Draft (or extend) the deck **in the current working directory**. Requires an initialized deck
(`deck-context.json` present — else tell the user to run `/init-deck`). See `/SPEC.md` §7 for
the pipeline and D29/D35 for how agents are spawned.

Spawn each agent as a **general-purpose subagent** whose prompt is that role's template
(`<toolkit>/slidecraft/agents/<role>.md`, frontmatter stripped) with the deck-context
`injection` values substituted for its `%PLACEHOLDER%`s — read those from `deck-context.json`.
(v1 renders templates by path; the D29 registered-subagent-type optimization is deferred until
the agents are installed as subagent types.) `<toolkit>` is the **plugin root the wrapper
passes**; `<KM>` is `<toolkit>/slidecraft/scripts/km.py`. Run every `km`/script call with
`--deck <deck-root>` (or from the deck's CWD).

## 1. Convert (deterministic)

```
python "<toolkit>/slidecraft/scripts/source_converter.py" --deck <deck-root>
```

Turns each new file in `input/` into `sources/<slug>.json` (paged text + image records in
`public/extracted/`). Idempotent — already-converted inputs are skipped.

## 2. Mine (parallel subagents)

For each text source, spawn a **`knowledge-miner`**; for each source with images, spawn an
**`image-miner`**. Inject `FOCUS-TOPIC` (+ `LANGUAGE`) and the source id. Each miner returns a
list of nuggets and persists every one via `km create-nugget --file <tmp>` (the verbatim guard
rejects any excerpt not found in the source). Collect the created nugget ids.

## 3. Plan (one storyteller)

Spawn one **`storyteller`** with the injection block (max-slides, deck-type, audience, setting,
language, topic) and the nugget ids. It reads the nuggets and returns a **plan**: the outline
(structural slides) plus, per content nugget, a create / associate / merge / **park** decision
(D34). On a re-run it plans a **delta** against the existing deck, skipping `locked` slides
(propose, don't edit).

## 4. Execute the plan + compose

For each plan step, in order:
- **create / merge / park** → the corresponding `km` call (`create-slide [--parked]`,
  `merge-slides`, `park-slide`). The budget gate refuses once active slides hit `max_slides`;
  the hand-edit hook may prompt before touching a hand-edited slide.
- After every create and every merge, spawn a fresh **`slide-composer`** for that slide
  (clean context each). It loads the `compose-slide` skill, writes the body within the density
  budget, references any figure by its `/extracted/…` public path, and writes via
  `km set-content --body-file <tmp>`.

## 5. Validate + report

```
python "<KM>" --deck <deck-root> validate
```

Report: the ordered slide list, any parked slides + why, unresolved `FIGURE NEEDED` markers,
and the validate result. Tell the user they can preview with `show_slide_deck.cmd`.

> **Note (D35, target):** the deterministic form of this orchestration is a Workflow
> (`draft_deck.js`) — miners in `parallel()`, storyteller as a planner, composers in a
> `pipeline()` at the top level — which keeps intermediate nugget/plan data out of the lead's
> context. v1 ships this command-driven orchestration (proven on subagents); migrate to the
> workflow once validated.
