---
description: Initialize a new Slidecraft deck in the current folder — a short interview (topic, audience, language, theme, length, deck type, setting) then scaffolds the empty deck project (folders, deck-context.json, package.json, launcher). No content is generated. Afterwards the user drops inputs into input/ and runs draft-deck.
argument-hint: (run inside the deck folder)
---

# Init Deck

Initialize a deck **in the current working directory**. The deck root *is* the folder
Claude was launched in (D25 — no "output folder" question); every later script resolves the
deck by walking up from CWD for `deck-context.json`. See `/CONTEXT.md` for the vocabulary and
`/SPEC.md` for the mechanics (esp. D38 for the init-deck refinements below).

`<toolkit>` below is the plugin root the wrapper passes; the scaffold script is
`<toolkit>/slidecraft/scripts/scaffold_deck.py`.

## 1. Guard (fast — a single-file check)

Check **only** whether `deck-context.json` already exists in the CWD (one stat / one `Glob`
for `deck-context.json`). If it does, this folder is already a deck: **stop**, tell the user,
and offer to open it or pick another folder. Do **not** re-scaffold.

Do **not** enumerate or recursively scan the directory tree to decide anything — on a
cloud-synced folder (OneDrive) a recursive listing is slow, and it is unnecessary: the folder
need **not** be empty (the user may already have dropped files into `input/`). The single
`deck-context.json` check is the whole guard.

## 2. Interview — part 1 (topic + theme, so the install can start early)

Ask with the **AskUserQuestion** tool, in the user's language. Batch these first, because the
**theme** answer lets us start installing Slidev in the background while the rest of the
interview runs (step 3):

1. **Topic** — the deck's working title and thematic focus. In the help text, explain the
   *user benefit*: this focus guides which knowledge is extracted from the provided sources and
   keeps the slides on-topic. **Never** expose internal terms (no "FOCUS-TOPIC", no "miner",
   no "injection") — the user should not have to think about the machinery.
2. **Audience** — students / experts / management / customers / investors / general public / …
3. **Language** — en / de / … (governs all composed content).
4. **Theme** — where the Slidev theme comes from: the built-in `default`, a local folder
   (`slidev-theme-<brand>/`), an npm package (`slidev-theme-*`), or a GitHub URL. Capture its
   `type` (builtin | local | npm | github) and `source`. (A **local** theme is copied into the
   deck's `theme/` subfolder by the scaffold, so the deck stays self-contained and portable.)

## 3. Prewarm + background install (only if this is a new deck)

As soon as topic + theme are known, lay down the npm project and start the install so the first
preview isn't a long wait:

1. Write a partial answers JSON (`topic` + `theme`, plus any other captured fields) to a temp
   file and run:
   ```
   python "<toolkit>/slidecraft/scripts/scaffold_deck.py" --answers <partial.json> --prewarm
   ```
   This creates the folders, **copies a local theme into `theme/`**, and writes
   `package.json` / `.gitignore` / the launchers. Its JSON output includes
   `node_modules_present`.
2. If `node_modules_present` is `false` **and** Node/npm is available, start the install **in
   the background** from the deck root (CWD), e.g. run `npm install --no-audit --no-fund` with
   the Bash/PowerShell tool's `run_in_background`. Do not block on it — continue the interview.
   It is best-effort: if npm/Node is missing or offline, skip it silently; the launcher installs
   on first run as a fallback.

This background `npm install` is the **only** preparation the preview needs —
there is no separate "build" step; `/draft-deck` starts the Slidev dev server
directly from `slides.md`. Finishing it here is what lets that server start
instantly.

## 4. Interview — part 2 (length, type, setting, metadata)

Continue with **AskUserQuestion** (batched) while the install runs:

5. **Length** — ask for the **maximum duration in minutes** (e.g. "Wie lange soll die
   Vorlesung maximal werden?" → 30 / 45 / 60 / 90 / …). The slide budget is **derived** from
   the duration at ~**1.5 minutes per slide** (the scaffold does the maths), so do **not** ask
   for a slide count separately. Only if the user volunteers a specific maximum number of
   slides, pass it as `max_slides` to override the estimate.
6. **Deck type** — lecture / pitch / executive meeting / status report / conference talk /
   workshop / … (selects the storytelling skill later; also refines the pacing).
7. **Setting** — university course / trade fair / scientific conference / internal meeting / …
8. **Deck metadata (optional, one batched question)** — the values structural slides need
   (cover / footer / thank-you): **presenter** name, **institution/course** (optional), and a
   **date** (default: today — offer it pre-filled, editable). These fill the cover, the running
   footer, and the closing slide. Skipping them is fine — the fields default to empty. Capture
   as `presenter`, `institution`, `course`, `date`.

## 5. Scaffold (deterministic, full)

Write the complete answers to a temp JSON and run the scaffold from the deck root:

```
python "<toolkit>/slidecraft/scripts/scaffold_deck.py" --answers <answers.json>
```

`answers.json` keys: `topic, audience, language, deck_type, setting, max_duration_minutes,
max_slides?, theme:{type, source}` plus the optional metadata `presenter, institution, course,
date` (omit or pass `""` when not captured). `max_slides` is optional — omit it to let the
script derive it from `max_duration_minutes`. This phase is idempotent over the prewarm (it
re-does those steps as no-ops) and additionally:

- writes `associations.json` (`{}`) and `slides.md` (theme + title headmatter),
- writes **`deck-context.json`**: the `deck` block (interview answers, the **derived**
  `max_slides`, and the optional presenter/institution/course/date metadata), the `theme` block
  (with scanned `capabilities` — per-layout **slot roles + intents + defaults** where the theme
  ships a `semantic-layouts.json` — and the theme's `styleguide.md` path), and the derived
  per-agent **injection** blocks.

Do not hand-write any of these files — the script owns the format. The script's JSON output
reports the derived `max_slides` and `minutes_per_slide` — surface those to the user in the
summary so the slide budget is transparent (and they can ask to change it).

## 6. Close

If the background install is still running, mention it's finishing in the background (the
launcher waits for it either way). Then show the scaffold summary and instruct:

> Deck initialized (~{max_slides} slides for {duration} min at ~1.5 min/slide). Put your source
> files (PDF, Markdown, text) into `input/`, then run `/draft-deck`. To preview the deck at any
> time, double-click `show_slide_deck.cmd` (Windows) or `show_slide_deck.sh` (macOS/Linux).

`/draft-deck` now opens the live preview itself (§0 of that command) as soon as it starts, so
the double-click launcher above is the manual/fallback path — useful for reopening the preview
later, or if the automatic launch reported `no-preview`.

No content is generated at this stage.
