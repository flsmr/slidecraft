---
description: Run the drafting pipeline over the current deck — convert new inputs to sources, mine knowledge nuggets, plan the deck structure, and compose the slides. Re-runnable — it processes only unmined inputs and integrates new nuggets into the existing deck. Requires an initialized deck (run init-deck first) with files in input/.
argument-hint: (run inside an initialized deck folder)
---

# Draft Deck

Draft (or extend) the deck **in the current working directory**. Requires an initialized
deck (`deck-context.json` present — else tell the user to run `/init-deck`). See `/SPEC.md`
§7 and decisions **D40–D45** for the pipeline this command sequences.

Every LLM role in this pipeline is a **pure function** (D40): the knowledge manager
*assembles* a fully self-contained brief, the invoke **shim** sends it to a pluggable
executor (OWUI or a Claude subagent), and the knowledge manager *persists* the validated
output. **You (the lead) never mine, plan, or compose in your own context, and no role ever
reads a deck file or calls a script.** You only run the deterministic scripts below and read
their JSON output; the nondeterministic work happens behind the shim.

`<toolkit>` is the plugin root the wrapper passes. Shorthands used below:

- `<KM>`   = `<toolkit>/slidecraft/scripts/km.py`
- `<SHIM>` = `<toolkit>/slidecraft/scripts/invoke_shim.py`
- `<CONV>` = `<toolkit>/slidecraft/scripts/source_converter.py`

Run every script with `--deck <deck-root>` (or from the deck's CWD). Do all work in a scratch
dir for the transient brief / result / payload files (e.g. `logs/draft/`); they are not deck
state.

## The one seam pattern (assemble → invoke → persist)

Every role runs the same three steps. The shim is the only nondeterministic call:

```
python "<KM>"   --deck <deck> <assemble-cmd> --out <brief>            # assemble
python "<SHIM>" --role <role> --brief-file <brief> [--image <path>] \
               --deck <deck> --out <result.json> \
               -- python "<KM>" --deck <deck> <persist-cmd> --file {out}   # invoke+persist
```

The shim exit codes are the terminal signal — **read them, never ignore them** (D44):

- **0** — `ok`: the output validated and was persisted.
- **3** — `exhausted`: the model failed validation twice after a retry; `result.json`
  carries the per-role **terminal** (`drop` / `park` / `abort`) and the errors.
- **4** — `error`: transport/infra or a non-retryable gate; `result.json` carries the errors.

`{out}` is a literal placeholder the shim replaces with the parsed-output file — pass it
verbatim. (Do **not** confuse the shim's exit 3 with km's own exit 3 = `budget_full`.)

## 1. Convert (deterministic)

```
python "<CONV>" --deck <deck>
```

Turns each new file in `input/` into `sources/<slug>.json` (paged text + image records, with
the images extracted to `public/extracted/`). Idempotent — already-converted inputs are
skipped. A source record carries `original_file`, `pages`, and an `images` list; each image
record has an `image_source_id`, its `/extracted/…` `path`, `page`, and `context_text`.

## 2. Mine (one invoke per text source + per extracted image)

A source is **unmined** when its record has no `mined_at`. For each unmined source `S`
(read `sources/*.json`):

**a. Mine the text** — one invoke over the whole source text:

```
python "<KM>"   --deck <deck> mine-brief --source <S> --out <brief>
python "<SHIM>" --role knowledge-miner --brief-file <brief> --deck <deck> --out <result> \
               -- python "<KM>" --deck <deck> persist-nuggets --source <S> --file {out}
```

**b. Mine each image** — one invoke per image in `S.images`, the figure passed directly
(the shim encodes it as a base64 data-URL; D45). `mine-brief --image` reports the local
`asset` path to pass as `--image`:

```
python "<KM>"   --deck <deck> mine-brief --image <image_source_id> --out <brief>   # reports "asset"
python "<SHIM>" --role image-miner --brief-file <brief> --image <asset> --deck <deck> --out <result> \
               -- python "<KM>" --deck <deck> persist-nuggets --source <S> --image-source <image_source_id> --file {out}
```

`persist-nuggets` enriches `kind`/`source` and, for images, denormalizes `asset` +
`context_text` + `page` from the source record — the miner never invents them.

**c. Mark the source mined** once its text and every image have been attempted:

```
python "<KM>" --deck <deck> mark-mined --source <S>
```

This stamps `mined_at` and moves the input to `input/processed/`, so a re-run skips it
(delta behavior, D18).

**Miner terminal (drop).** A shim exit 3 or 4 on a miner means that source's text — or that
one figure — produced no nugget. **Flag it** in the run report (e.g. "figure
`chapter-4-p2-img1` mined nothing after 3 attempts") and carry on; the rest of the source
still mines. Never fail silently.

Collect the created nugget ids from each `result.json` / the `persist-nuggets` output — the
storyteller places every one.

## 3. Plan (one storyteller invoke)

```
python "<KM>"   --deck <deck> plan-brief --out <brief>
python "<SHIM>" --role storyteller --brief-file <brief> --deck <deck> --out <result> \
               -- python "<KM>" --deck <deck> write-plan --file {out}
```

The storyteller is a **pure planner** (D41): it sees only nugget *digests* (title +
information + figure description — never raw text or asset paths) and returns a plan — the
structural slides plus, per content slide, the assigned nugget ids and a
create / associate / merge / **park** decision (D34), with an optional `intended_function`
hint. On a **fresh** deck the brief asks for a full plan; on a **re-run** it asks for a
**delta** that integrates the new nuggets into the existing structure and **skips `locked`
slides** (propose, never edit). You never see composed prose — only the plan.

`write-plan` validates the plan deterministically (nugget ids exist, decision types valid,
budget arithmetic sound, hints in the enum, locked slides untouched, no nugget left
unplaced), records it to `plan.json`, and returns an **executable step list** (also in
`plan.json` under `steps`).

**Storyteller terminal (abort).** A shim exit 3/4 here means no valid plan. **Abort the whole
draft with a flagged error** and compose nothing — a deck is never composed off an invalid
plan. Report the errors from `result.json`.

## 4. Execute the plan + compose

Read `plan.json`'s `steps` and run them **in order**. Each step's `op` is a km subcommand:

- `create-slide` → `create-slide --title <t> [--nuggets a,b] [--parked] [--after <id|end>] [--intended-function <f>]` — a **structural** step (its plan entry has `"structural": true` and no nuggets) is just a create with `--nuggets` omitted; there is no `--structural` flag
- `associate-nuggets` → `associate-nuggets --slide <id> --nuggets a,b`
- `merge-slides` → `merge-slides --slides a,b [--title <t>]` (retires its inputs, returns the new id)
- `park-slide` → `park-slide --slide <id> [--reason <r>]` — moves the slide into the rendered **"Backup Slides" appendix** (km auto-manages the divider); a bodyless slide gets a deterministic digest body from its nuggets' `information`, a composed slide keeps its body (D46). Not budget-counted.
- `unpark-slide` → `unpark-slide --slide <id>` — needs a free active slot. It returns **`needs_compose`**: `true` when the slide was a digest preview (discarded → reset to `pending`, must be recomposed); `false` when it kept a real composed body (simply restored — no compose).

The budget gate refuses a create once active slides hit `max_slides` (park/merge frees a
slot first — the plan is already validated to respect this). Capture the `slide_id` each
create and merge returns.

**Compose after every create and every merge, and after an unpark that reports
`needs_compose: true`.** Skip **parked creates** — km already wrote their digest body (D46), and a
directly-parked slide is not part of the main flow. An unpark of a digest slide (`needs_compose:
true`) discards the digest and needs a real composition, so treat it like a create; an unpark that
restored a real body (`needs_compose: false`) is already done. Clean invoke each time:

```
python "<KM>"   --deck <deck> compose-brief --slide <slide_id> --out <brief>
python "<SHIM>" --role slide-composer --brief-file <brief> --deck <deck> --out <result> \
               -- python "<KM>" --deck <deck> write-slide --slide <slide_id> --file {out}
```

The composer sees only *its* slide's routed fields (verbatim `raw_text` for text nuggets,
the figure's `asset` + `description` for image slides — never the `information` digest or a
figure's `visible_text`; D42) and returns semantic role-keyed JSON. `write-slide` maps the
semantic roles to physical slots, applies layout defaults, validates layout + asset, fills
empty presenter notes verbatim from the nuggets (D39), stamps `concept_type`, and turns a
non-empty `figure_needed` into a `FIGURE NEEDED` marker.

**Composer terminal (park).** A shim exit 3 means this slide could not be composed. **Park it
and flag it** so the deck stays valid and the gap is visible:

```
python "<KM>" --deck <deck> park-slide --slide <slide_id> --reason "composition failed after 3 attempts"
```

## 5. Validate + report

```
python "<KM>" --deck <deck> validate
```

`validate` prints a JSON report and **exits non-zero when the deck is not green** — treat a
non-zero exit as a hard failure and surface the `errors`. On success, report:

- the ordered slide list;
- the **Backup Slides** appendix: each parked slide + why (off-storyline, or a composition that
  failed) — these render at the end for the human to review and keep-or-hide (D46);
- any **dropped** nuggets / figures the miners could not produce (flagged in phase 2);
- unresolved `FIGURE NEEDED` markers;
- and, on an aborted run, the storyteller error that stopped it.

Tell the user they can preview with `show_slide_deck.cmd`. Every content slide should trace
to nuggets; the budget is respected; presenter notes are verbatim provenance.

> **Note (D35, target):** the deterministic form of this orchestration is a Workflow
> (`draft_deck.js`) over the *same* seams — miners in `parallel()`, the storyteller as a
> planner, composers in a `pipeline()` — so intermediate nugget/plan/prose data never
> transits the lead's context. v1 ships this command-driven orchestration; migrate to the
> workflow once validated. The integration test `test_draft_deck_integration.py` drives this
> exact sequence with a fake executor to a green `validate`.
