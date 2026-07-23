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

- `<KM>`      = `<toolkit>/slidecraft/scripts/km.py`
- `<SHIM>`    = `<toolkit>/slidecraft/scripts/invoke_shim.py`
- `<CONV>`    = `<toolkit>/slidecraft/scripts/source_converter.py`
- `<COMPOSE>` = `<toolkit>/slidecraft/scripts/compose_deck.py`
- `<SERVE>`   = `<toolkit>/slidecraft/scripts/serve_deck.py`

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

## 0. Start the live preview (background) + status

Kick this off first, concurrently with the pipeline — it must not block mining:

    python "<SERVE>" --deck <deck>         # run with the tool's run_in_background

Read its one-line JSON: `served` (browser opening) / `reused` (already live) /
`no-preview` (Node or npm missing — continue drafting; files still update, the
user previews later via `show_slide_deck`). Record which, for the final report.

Then set the first status so the browser shows progress immediately:

    python "<KM>" --deck <deck> set-status --phase convert --label "Converting inputs…"

The status slide is inline and **uncounted** (never consumes a budget slot).
Update it at each phase transition below; clear it at the end.

## 1. Convert (deterministic)

```
python "<CONV>" --deck <deck>
```

Turns each new file in `input/` into `sources/<slug>.json` (paged text + image records, with
the images extracted to `public/extracted/`). Idempotent — already-converted inputs are
skipped. A source record carries `original_file`, `pages`, and an `images` list; each image
record has an `image_source_id`, its `/extracted/…` `path`, `page`, and `context_text`.

Once conversion produces the source count `<N sources>`, update the status:

    python "<KM>" --deck <deck> set-status --phase mine --detail "0/<N sources>" --label "Mining sources…"

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
(delta behavior, D18). Then bump the status detail with the running count of sources mined:

```
python "<KM>" --deck <deck> set-status --phase mine --detail "<done>/<N>" --label "Mining sources…"
```

**Miner terminal (drop).** A shim exit 3 or 4 on a miner means that source's text — or that
one figure — produced no nugget. **Flag it** in the run report (e.g. "figure
`chapter-4-p2-img1` mined nothing after 3 attempts") and carry on; the rest of the source
still mines. Never fail silently.

Collect the created nugget ids from each `result.json` / the `persist-nuggets` output — the
storyteller places every one.

## 3. Plan (one storyteller invoke)

Before the storyteller invoke, update the status:

    python "<KM>" --deck <deck> set-status --phase plan --label "Planning deck structure…"

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

## 4. Execute the plan + compose (two-stage)

Read `plan.json`'s `steps` and run them **in order**. Each step's `op` is a km subcommand —
but do **not** compose per-create. Creating/merging a content slide leaves it needing
composition; the batch driver in the next step owns that.

- `create-slide` → `create-slide --title <t> [--nuggets a,b] [--parked] [--after <id|end>] [--intended-function <f>]` — a **structural** step (its plan entry has `"structural": true` and no nuggets) is just a create with `--nuggets` omitted; there is no `--structural` flag
- `associate-nuggets` → `associate-nuggets --slide <id> --nuggets a,b`
- `merge-slides` → `merge-slides --slides a,b [--title <t>]` (retires its inputs, returns the new id)
- `park-slide` → `park-slide --slide <id> [--reason <r>]` — moves the slide into the rendered **"Backup Slides" appendix** (km auto-manages the divider); a bodyless slide gets a deterministic digest body from its nuggets' `information`, a composed slide keeps its body (D46). Not budget-counted.
- `unpark-slide` → `unpark-slide --slide <id>` — needs a free active slot. It returns **`needs_compose`**: `true` when the slide was a digest preview (discarded → reset to `pending`, so the driver will recompose it); `false` when it kept a real composed body (simply restored — nothing to recompose).

The budget gate refuses a create once active slides hit `max_slides` (park/merge frees a
slot first — the plan is already validated to respect this). Skip nothing here for composition:
a **parked create** already has its digest body (D46) and is not part of the main flow; every
other active, uncomposed slide is picked up automatically by the driver below.

Then run the batch driver **once**; it owns all planner + designer OWUI calls (D7):

```
python "<COMPOSE>" --deck <deck> --run-label <run>
```

For each to-compose slide (active, unlocked, not yet composed — in deck order) it runs
`km compose-brief` → the planner (invoke shim) → `km write-skeleton` (validates the plan,
renders a visible **wireframe**, and PLACES any `source-image` area from the mined figure);
then it builds every pending content section **concurrently** via `design_section.py`
(`km design-brief` → the area's designer → `km place-design`). A wireframe renders the instant
a slide is planned and each area fills in as its designer lands — free live-preview progress.
Update the status while it runs:

    python "<KM>" --deck <deck> set-status --phase compose --detail "<composed>/<total>" --label "Composing slides…"

Read the driver's JSON report and fold it into the run report:

- `composed` — slides finished (all sections placed, or structural title-only);
- `parked` — a slide whose **planner** exhausted (cap-2 retries) → parked + flagged, so the
  deck stays valid and the gap is visible (its Backup entry carries the reason);
- `failed_sections` — an **area whose designer** exhausted: its wireframe stays visible and the
  section is flagged (the slide is still a valid `planned` file — never silently dropped);
- `figure_needed` — areas that still want a generated figure.

To **re-generate one area** (human-in-the-loop, e.g. redo a diagram or a generated image), run
the same driver scoped to a single slide+section — same code path, idempotent:

```
python "<COMPOSE>" --deck <deck> --slide <slide_id> --section <role>
```

## 5. Validate + report

On success, clear the transient status slide so the finished deck is clean:

    python "<KM>" --deck <deck> clear-status

On an **aborted** run (storyteller terminal, §3), do NOT clear — instead set a
terminal status so the browser reflects the stop, then surface the error:

    python "<KM>" --deck <deck> set-status --phase aborted --label "Draft aborted — see report"

```
python "<KM>" --deck <deck> validate
```

`validate` prints a JSON report and **exits non-zero when the deck is not green** — treat a
non-zero exit as a hard failure and surface the `errors`. On success, report:

- the ordered slide list;
- the **Backup Slides** appendix: each parked slide + why (off-storyline, or a **planner** that
  exhausted, §4) — these render at the end for the human to review and keep-or-hide (D46);
- any **`failed_sections`** the driver reported: an area whose designer exhausted keeps a visible
  wireframe on an otherwise-valid `planned` slide — flag each so the human can re-run that one
  area (`--slide <id> --section <role>`);
- any **dropped** nuggets / figures the miners could not produce (flagged in phase 2);
- and, on an aborted run, the storyteller error that stopped it;
- whether the live preview was active (served / reused / no-preview) and, if serving, that it
  stays running — close the window / Ctrl-C to stop it.

Tell the user they can preview with `show_slide_deck.cmd`. Every content slide should trace
to nuggets and the budget is respected.

> **Note (D35, target):** the deterministic form of this orchestration is a Workflow
> (`draft_deck.js`) over the *same* seams — miners in `parallel()`, the storyteller as a
> planner, composers in a `pipeline()` — so intermediate nugget/plan/prose data never
> transits the lead's context. v1 ships this command-driven orchestration; migrate to the
> workflow once validated. The integration test `test_draft_deck_integration.py` drives this
> exact sequence with a fake executor to a green `validate`.
