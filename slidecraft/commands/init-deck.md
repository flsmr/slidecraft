---
description: Initialize a new Slidecraft deck in the current folder — a short interview (topic, audience, language, theme, length, deck type, setting) then scaffolds the empty deck project (folders, deck-context.json, package.json, launcher). No content is generated. Afterwards the user drops inputs into input/ and runs draft-deck.
argument-hint: (run inside the deck folder)
---

# Init Deck

Initialize a deck **in the current working directory** (D25 — the deck root *is* the folder
Claude was launched in). The interview is **declared data**, walked mechanically: you call
`AskUserQuestion` exactly as the spec declares, resolve each branch with a deterministic helper,
and never improvise wording or research anything. The **only** time you exercise judgement is a
branching question answered via **"Other"** (§ step 4).

`<toolkit>` is the plugin root the wrapper passes. Scripts used:

- `<SCAFFOLD>` = `<toolkit>/slidecraft/scripts/scaffold_deck.py`
- `<SCAN>`     = `<toolkit>/slidecraft/scripts/scan_theme.py`
- `<IV>`       = `<toolkit>/slidecraft/scripts/init_interview.py`
- Spec: `<toolkit>/slidecraft/data/init_questions.json`

## 1. Guard (fast — a single-file check)

Check **only** whether `deck-context.json` already exists in the CWD (one stat / one `Glob`). If
it does, this folder is already a deck: **stop**, tell the user, offer to open it or pick another
folder. Do **not** re-scaffold and do **not** recursively scan the tree (slow on OneDrive, and
unnecessary — the folder need not be empty).

## 2. Interview part 1 — topic + theme (so the install can start early)

Walk the spec's `topic` question, then ask the **theme** question (handled specially — it is *not*
in the spec because its answer is compound). Ask both with **AskUserQuestion**, in the user's
language:

1. **`topic`** — the deck's working title / thematic focus. In the help text explain the *user
   benefit* (this focus guides which knowledge is extracted and keeps slides on-topic). Never
   expose internal terms.
2. **Theme** — where the Slidev theme comes from: built-in `default`, a local folder
   (`slidev-theme-<brand>/`), an npm package (`slidev-theme-*`), or a GitHub URL. Capture its
   `type` (builtin | local | npm | github) and `source`. (A **local** theme is copied into the
   deck's `theme/` subfolder by the scaffold, so the deck stays self-contained.)

## 3. Prewarm + background install + scan (on the theme answer)

As soon as topic + theme are known:

1. Write a partial answers JSON (`topic` + `theme`) to a temp file and run:
   ```
   python "<SCAFFOLD>" --answers <partial.json> --prewarm
   ```
   This creates folders, **copies a local theme into `theme/`**, and writes `package.json` /
   `.gitignore` / launchers. Its JSON output includes `node_modules_present`.
2. If `node_modules_present` is `false` **and** Node/npm is available, start `npm install
   --no-audit --no-fund` **in the background** from the deck root (CWD) with the tool's
   `run_in_background`. Do not block on it. Best-effort: skip silently if npm is missing/offline.
3. **Scan the now-copied theme** to derive the cover-slot questions for part 2 — this rides the
   same background window the install uses, so it adds no latency. For a **local** theme:
   ```
   python "<SCAN>" --type local --source ./theme
   ```
   (for builtin/npm/github pass the captured `type`/`source`). Feed the resulting `capabilities`
   to `scaffold_deck.cover_slot_questions` — either import it, or replicate its rule: find the
   layout whose `alias == "cover"` (else physical `name == "cover"`, else none); ask one
   free-text question per role/slot name it exposes, **skipping** `date`, `title`, and a bare
   `default`. If there is no cover layout, ask no metadata questions.

## 4. Interview part 2 — length, type, setting, cover metadata

Continue with **AskUserQuestion** (batched, up to 4 per call) while the install runs. Walk the
remaining spec questions in order — `language`, `deck_type`, `setting`, `max_duration_minutes` —
plus any **cover-slot questions** from step 3. For each spec question:

- Ask it exactly as declared. After the answer, resolve the follow-up deterministically:
  ```
  python "<IV>" follow-up --qid <question-id> --answer "<the answer>"
  ```
  - `follow_up` non-null → ask that follow-up question next.
  - `llm_decides: true` → the user answered a **branching** question via **"Other"**: *this* is
    where you (the LLM) decide whether a follow-up applies and, if so, ask a sensible one. This is
    the sole judgement call in the whole command.
  - both null/false → record the answer and move on (a leaf "Other" is just the answer — never a
    branch).
- **Length:** ask for the **maximum duration in minutes**; the slide budget is *derived* from it
  (~1.5 min/slide; the scaffold does the maths) — do not ask for a slide count. Only if the user
  volunteers a specific maximum, pass it as `max_slides`.
- **Cover metadata:** the cover-slot questions replace the old fixed presenter/institution/course/
  date batch. Fill a `date` slot programmatically with **today**; a `title` slot reuses the topic
  (both are never asked). Collect the cover-slot answers into a `cover` object keyed by slot name.

## 5. Scaffold (deterministic, full)

Write the complete answers to a temp JSON and run from the deck root:

```
python "<SCAFFOLD>" --answers <answers.json>
```

`answers.json` keys: `topic, audience, language, deck_type, setting, max_duration_minutes,
max_slides?, theme:{type, source}`, plus a `cover` object `{slot: value}` for the theme-derived
metadata (omit slots the user skipped). `max_slides` is optional (derived from the duration when
absent). This phase is idempotent over the prewarm and additionally writes `associations.json`,
`slides.md`, and **`deck-context.json`** (the `deck` block incl. the derived `max_slides` and the
`cover` map, the `theme` block with scanned `capabilities` + `styleguide.md` path, and the derived
per-agent `injection` blocks). Do not hand-write any of these files — the script owns the format.
The script reports the derived `max_slides` / `minutes_per_slide`; surface those so the budget is
transparent.

## 6. Close

If the background install is still running, mention it's finishing (the launcher waits either
way). Show the scaffold summary and instruct:

> Deck initialized (~{max_slides} slides for {duration} min at ~1.5 min/slide). Put your source
> files (PDF, Markdown, text) into `input/`, then run `/draft-deck`. To preview at any time,
> double-click `show_slide_deck.cmd` (Windows) or `show_slide_deck.sh` (macOS/Linux).

No content is generated at this stage — `/init-deck` runs no LLM role. The convert→mine→plan
chain lives in `/draft-deck`.
