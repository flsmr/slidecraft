---
description: Run the drafting pipeline over the current deck — convert new inputs to sources, mine knowledge nuggets, plan the deck structure, and compose the slides. Re-runnable — it processes only unmined inputs and integrates new nuggets into the existing deck. Requires an initialized deck (run init-deck first) with files in input/.
argument-hint: (run inside an initialized deck folder)
---

# Draft Deck

Draft (or extend) the deck **in the current working directory**. Requires an initialized deck
(`deck-context.json` present — else tell the user to run `/init-deck`). The whole pipeline is one
deterministic driver; you only pick the mode, start the preview, run the driver once, and read
its report. Every LLM role runs behind the invoke shim inside the driver — **you never mine,
plan, or compose in your own context.**

`<toolkit>` is the plugin root the wrapper passes:

- `<DRAFT>` = `<toolkit>/slidecraft/scripts/draft_deck.py`
- `<SERVE>` = `<toolkit>/slidecraft/scripts/serve_deck.py`

## 1. Ask the mode (one AskUserQuestion)

Ask, in the user's language, with **two** options:

- **"Process (chunk up) input knowledge only"** → `digest` — convert + mine; stops there. No
  slides are created. Use this to build up nuggets from new inputs without (re)composing.
- **"Process input knowledge and create slide deck"** → `full` — the whole
  convert→mine→plan→compose→validate pipeline.

## 2. Start the live preview (full mode only)

If the user chose **full**, start the background live server *before* the driver so the user can
watch the deck grow as slides compose:

    python "<SERVE>" --deck <deck>      # run with the tool's run_in_background

Read its one-line JSON: `served` (browser opening) / `reused` (already live) / `no-preview`
(Node/npm missing, or `ports 3030-3040 all in use` — continue drafting; the files still update
and the user can preview later via `show_slide_deck`). Record which, for the final report. In
**digest** mode, skip this — nothing gets composed.

## 3. Run the driver once

```
python "<DRAFT>" --deck <deck> --mode <digest|full> [--run-label <label>]
```

The driver re-derives all state from the filesystem each run (input/ vs input/processed/ for
convert, `mined_at` for mine, slide state for plan/compose), so a re-run after any stop resumes
by construction. It emits **one JSON report**:

```
{ "status": "ok"|"error", "mode": ..., "convert": {...}, "mine": {...},
  "plan": {...}|null, "compose": {...}|null, "validate": {...}|null,
  "stopped_at": null|"mine"|"plan", "stopped_detail"?: {...} }
```

## 4. Read the report

- **`status: "ok"`** — present the summary from the report:
  - `convert.sources_created`, `mine.sources_mined`, `mine.nuggets_created`;
  - any **dropped** miners (`mine.dropped` — a source's text or a figure that yielded no nugget
    after retries): flag each so the user knows what was skipped;
  - **full mode only:** `plan.slides_planned`; the composed slide list and the **Backup Slides**
    appendix from `compose.parked` (a slide whose *planner* exhausted → parked + flagged);
    `compose.failed_sections` (an *area* whose designer exhausted — its wireframe stays visible
    on an otherwise-valid slide; the user can re-run one area with
    `python "<toolkit>/slidecraft/scripts/compose_deck.py" --deck <deck> --slide <id> --section <role>`);
    `compose.figure_needed`; and `validate` (`ok` / `errors`). If `validate.exit_ok` is false,
    treat the deck as not green and surface `validate.errors`.
  - whether the live preview was `served`/`reused`/`no-preview`, and that a served preview stays
    running (close the window / Ctrl-C to stop it).
  - In **digest** mode, stop here — `plan`/`compose`/`validate` are `null` by design (not run).
    In **full** mode they are also `null` when there was nothing to do (no unplaced nuggets and
    nothing left to compose — e.g. re-running on an already-finished deck); that is a success,
    not an error.
- **`status: "error"`** — the one case you investigate. `stopped_at` names the phase and
  `stopped_detail.errors` carries the specifics — **read them to tell the cause apart**, then
  **re-run the same command** (it resumes from where it stopped by re-deriving state):
  - a **`mine`** stop is a transport/infra failure invoking a miner (e.g. OWUI unreachable); it
    resumes from the un-mined source once the cause is fixed.
  - a **`plan`** stop can be any of three causes, all surfaced here: the storyteller produced an
    invalid plan after retries (nothing is composed off an invalid plan), a transport/infra
    failure while invoking the storyteller (e.g. OWUI/Claude CLI unreachable), or a deterministic
    km step failing while executing an already-written plan. `stopped_detail.errors` distinguishes
    them — a validation message points at the nuggets/plan; a transport message points at the
    executor being down. Re-running resumes once the underlying cause (bad inputs, or a downed
    service) is resolved.

Tell the user they can preview any time with `show_slide_deck.cmd` (Windows) / `show_slide_deck.sh`
(macOS/Linux). Every content slide traces to nuggets and the slide budget is respected.
