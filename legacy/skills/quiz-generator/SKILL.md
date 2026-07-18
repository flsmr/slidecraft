---
name: quiz-generator
description: >
  Insert interactive quiz and check-for-understanding slides at strategic points
  in a presentation to increase audience engagement and verify comprehension.
  Triggers on "add quizzes", "add check-for-understanding", "make it
  interactive", "add poll slides", "test comprehension", "add knowledge
  checks", "add CFU slides".
---

# Quiz Generator Skill

You analyze a slide deck's CIF, identify strategic points to insert interactive quiz slides (multiple-choice, true/false, open prompt, or predict-then-reveal), generate the quiz content with strict cognitive-load limits, insert new slides into the CIF without disturbing existing slide IDs, and re-render the deck.

Quiz slides are **inserted between** content slides — they are **not** transformations of existing slides. Unlike `visual-enrichment` and `example-generator`, this skill **adds new slides**.

Before starting, read `references/best-practices.md` for design rules and apply them throughout. Quizzes are subject to the same one-idea-per-slide and density limits as any other slide.

---

## Step 1 — Read the CIF and Identify Quiz Insertion Points

Read `.slidecraft/cif.json`. Walk the `slides` array in order and identify candidate insertion points using the rules below.

### Insertion-point heuristic — apply in order

**Rule A — Section-boundary quizzes (always propose):**

For every slide whose `layout` is one of `section`, `section-gray`, `section-overview`, or `divider`, propose **one quiz inserted immediately before** that section break. The quiz tests material from the section that is about to end.

Exception: do not propose a quiz before the **first** section slide of the deck — there is no preceding material to test.

**Rule B — Mid-section quizzes (optional, propose where useful):**

Within any single section, if there are **4 or more consecutive slides with layout `default`** covering related material, propose **one mid-section quiz** inserted after the second or third of those slides. The placement should sit at a natural breath point — usually after a slide that completes a sub-topic.

**Rule C — Total cap:**

The total number of quizzes must not exceed `ceil(N / 8)`, where `N` is the total slide count of the original deck (before insertions).

Examples:
- 10-slide deck → max 2 quizzes
- 16-slide deck → max 2 quizzes
- 17-slide deck → max 3 quizzes
- 24-slide deck → max 3 quizzes
- 32-slide deck → max 4 quizzes

If the candidate set exceeds the cap, prioritise:
1. Section-boundary quizzes (Rule A) first.
2. Then mid-section quizzes (Rule B) in order of appearance.
3. Drop the lowest-priority candidates until the cap is satisfied.

### Skip the very first and very last slides

Never insert a quiz at position 1 (before the cover) or at the final position (after `end`). Quizzes belong in the body of the deck.

### Quiz-type classification

For each insertion point, choose the quiz type that best fits the material under test:

| Quiz Type           | When to use                                                                                            |
|---|---|
| `multiple-choice`   | The material includes specific facts, definitions, or named distinctions where plausible distractors can be written. |
| `true-false`        | The material includes a single claim that audiences commonly misremember or misapply.                  |
| `open-prompt`       | The material is interpretive, strategic, or context-dependent — there is no single right answer.       |
| `predict-then-reveal` | The material includes a specific number, outcome, or empirical result that benefits from priming guessing first. |

---

## Step 2 — Build and Present the Proposal Table

After identifying every insertion point and choosing a type for each, build a proposal table and present it to the user **before generating any quiz content**.

Format:

```
Quiz Generator Proposals
=========================

After slide | Quiz Type           | Covers slides | Draft question
------------|---------------------|---------------|---------------------------------------------------
04          | multiple-choice     | 03–04         | Which property does encapsulation primarily protect?
07          | true-false          | 05–07         | Conway's Law applies only to software companies. (T/F)
09          | predict-then-reveal | 08–09         | What percentage of formatting time does Slidecraft save?
13          | open-prompt         | 11–13         | Where would tight coupling actually be the right choice?

Deck length: 16 slides. Cap (ceil(16/8)) = 2.
Proposed: 4 quizzes — exceeds cap. After priority dropping: 2 quizzes
(slide-04 multiple-choice, slide-09 predict-then-reveal).

Apply all proposals? Or list which to keep / change:
```

Wait for the user's response. Accept:

- **"yes" / "all" / "apply all"** → proceed with all proposed quizzes (after cap).
- A list of insertion points → apply only those.
- **"skip N"** or **"change N to <type>"** → adjust before proceeding.
- **"raise cap to X"** → if the user explicitly asks for more quizzes than the heuristic recommends, honour their request but warn that engagement drops when quiz frequency exceeds ~1 per 5 slides.
- **"none"** → exit the skill without modifying the CIF.

Do not proceed until the user has responded.

---

## Step 3 — Generate Quiz Content

For each approved insertion point, generate valid quiz content according to its type. Rules and examples follow.

### 3a. Multiple-choice

A multiple-choice quiz presents one question with four options, one correct.

**Rules:**
- **1 question**, **≤ 20 words**.
- **Exactly 4 options**, labelled A / B / C / D.
- Each option **≤ 8 words**.
- Exactly **one** option is correct; the other three are plausible distractors drawn from common audience misconceptions (not absurd filler).
- The correct letter and a **1-line explanation** go in `notes`.

**Example slide body:**

```markdown
**Which property does encapsulation primarily protect?**

- A. Performance
- B. Internal state
- C. Memory footprint
- D. Compile time
```

**Example notes:**

```
Correct answer: B. Encapsulation hides internal state behind a stable
interface so callers cannot become coupled to implementation details.
Distractor A is the most common wrong answer — clarify that encapsulation
is about coupling, not speed.
```

### 3b. True/false

A true/false quiz presents one statement; audience votes true or false.

**Rules:**
- **1 statement**, **≤ 25 words**.
- The answer (True or False) goes in `notes`, with a **1-line justification**.
- The statement should be one audiences plausibly disagree on — avoid trivially true or trivially false statements.

**Example slide body:**

```markdown
**True or false?**

Conway's Law applies only to software companies.
```

**Example notes:**

```
Answer: False. Conway's Law applies to any organisation that produces a
system with components and interfaces — including hardware teams, regulatory
bodies, and even academic departments producing curricula.
```

### 3c. Open prompt

An open prompt asks a question with no listed options; the audience answers aloud or in small groups.

**Rules:**
- **1 question**, **≤ 25 words**.
- No multiple-choice options on the slide.
- Notes must include a **"What to listen for"** paragraph: the 2–3 answer threads the speaker should expect, and how to react to each.
- Use open prompts when there is no single right answer or when discussion is more valuable than evaluation.

**Example slide body:**

```markdown
**Discuss with your neighbour:**

Where would tight coupling actually be the right choice?
```

**Example notes:**

```
What to listen for:
- Single-team, small-codebase scenarios — affirm these are valid.
- Tightly synchronised state (e.g. a database transaction) — affirm.
- "Performance" alone — push back; coupling is rarely the fastest fix.
Allow 90 seconds, then take 2–3 answers from the room before moving on.
```

### 3d. Predict-then-reveal

A predict-then-reveal slide stages a guess, then reveals the actual answer on the same slide using Slidev's click-based progressive disclosure.

**Rules:**
- The setup question prompts the audience to **predict** a number or outcome.
- The reveal uses Slidev's `<v-click>` directive so the actual answer appears on click, after audience guesses are collected.
- Setup ≤ 20 words. Reveal value plus 1 explanatory sentence ≤ 30 words.
- Notes must instruct the speaker to take audience guesses **before** advancing the click.

**Example slide body:**

````markdown
**Predict:**

What percentage of total deck-creation time goes to manual formatting?

<v-click>

**Actual: 42 %**

Across 50 surveyed presenters in 2024 — more than content writing (35 %) or review (15 %).

</v-click>
````

**Example notes:**

```
Take 3–4 guesses from the room. Most audiences guess 15–25 %. Click to
reveal 42 % — the surprise gap is the engagement hook. Bridge into the
next section by asking what would happen if that 42 % could be reduced.
```

In the CIF, store the entire Markdown block (including `<v-click>` tags) as a plain string in the `content` field. The renderer passes Slidev directives through verbatim.

---

## Step 4 — Apply Cognitive-Load Limits

Before writing any quiz to the CIF, check these hard limits. If a limit is exceeded, apply the specified remediation.

| Limit                                       | Rule                                | Remediation                                                                                      |
|---|---|---|
| Question length                             | ≤ **20 words** (≤ 25 for true-false and open prompts) | Rewrite tighter. If the question genuinely needs more setup, the slide before it should carry that setup. |
| Option length (multiple-choice)             | ≤ **8 words** per option            | Trim, or switch to `open-prompt` if the answer space genuinely resists short options.            |
| Number of options                           | **Exactly 4** for multiple-choice   | If 5+ plausible answers exist, switch the quiz type to `open-prompt` rather than crowding the slide. |
| Quizzes per slide                           | **1** per slide, never two          | Pick the stronger quiz; the other becomes a candidate for a later insertion point.                |
| Adjacent quizzes                            | **Never insert two quiz slides in a row.** | If two candidate insertion points are adjacent (no content slide between), drop the lower-priority one. |
| Total quizzes                               | ≤ **ceil(N/8)** for total deck length N | Apply the priority-drop rule from Step 1.                                                       |

---

## Step 5 — Insert Quiz Slides into the CIF

Quiz slides are inserted, not transformed. This step requires care because slide IDs must remain stable for any external references (history snapshots, content-review records, etc.) made before this run.

### 5a. Save history

Before any modification, copy the current CIF to the history folder:

```
.slidecraft/history/cif-YYYYMMDD-HHMMSS.json
```

Use the current date and time (UTC). Create `.slidecraft/history/` if it does not exist.

### 5b. Choose the quiz layout

Read the workspace's theme manifest (typically `<themePath>/manifest.json`, found via `.slidecraft.json → themePath`). If the theme exposes a `quiz` layout in its layout list, use `layout: "quiz"` on inserted slides. Otherwise fall back to `layout: "default"`.

Record the chosen layout in the completion summary so the user knows whether their theme provided a dedicated quiz layout.

### 5c. Construct each new slide object

For each approved insertion point, build a new slide object:

```json
{
  "id": "slide-NN-q",
  "layout": "quiz",
  "title": "Quick check — <2–4 word topic>",
  "content": "<quiz body markdown as a single string, including any <v-click> tags>",
  "notes": "<answer + reasoning, per Step 3 rules>",
  "meta": { "quizSlide": true }
}
```

Where:

- `NN` is the **two-digit ID** of the slide the quiz is inserted **after**. Example: a quiz inserted after `slide-04` gets the ID `slide-04-q`.
- The `-q` suffix is used to avoid disturbing the zero-padded sequential numbering of the existing slides. **Do not renumber** existing slides — this is the key difference from `interactive-editing`, which renumbers on every structural change.
- If two quizzes share the same insertion-after slide (which the no-adjacent rule should already prevent), the second gets `-q2`. This should not happen in normal operation.
- The `title` should signal that this is a check-for-understanding, not regular content. "Quick check — <topic>" is the canonical pattern; alternatives: "Check your intuition", "Predict, then continue", "Discussion".

### 5d. Insert into the slides array

For each new slide, find the index of the after-slide in the existing `slides` array and insert the new slide object immediately after that index. Process insertions from **highest index to lowest** so each insertion does not shift the indices of pending insertions.

Do not modify or renumber any other slide. Existing slides keep their IDs.

### 5e. Set `meta.quizSlide` and write the file

On every inserted slide, ensure `meta.quizSlide` is `true`. Then write the updated object back to `.slidecraft/cif.json` with two-space indentation and UTF-8 encoding.

---

## Step 6 — Re-render

After writing the CIF, run the renderer to produce `slides.md`.

Read `.slidecraft.json` in the workspace root to find `pluginDir`, then run:

```bash
python <plugin-dir>/scripts/render-cif.py --input .slidecraft/cif.json --output slides.md
```

If the render fails (non-zero exit code or stderr output), report the error verbatim, revert `.slidecraft/cif.json` from the history copy, and do not leave a broken `slides.md`.

After a successful render, present a summary:

```
Quiz Generator Complete
=======================

Original deck length : 16 slides
Quizzes inserted     : 2 (cap was ceil(16/8) = 2)
New deck length      : 18 slides
Layout used          : "quiz" (theme provides a dedicated quiz layout)

Inserted slides:
  slide-04-q  multiple-choice    after slide-04  — "Quick check — Encapsulation"
  slide-09-q  predict-then-reveal after slide-09 — "Predict — Formatting Time"

Dropped candidates (priority cap):
  after slide-07 (true-false)
  after slide-13 (open-prompt)

CIF saved to .slidecraft/cif.json
History copy: .slidecraft/history/cif-20260526-143200.json
slides.md re-rendered successfully.
```

---

## Slidev Click-Reveal — Technical Notes

For `predict-then-reveal` quizzes, the reveal mechanism uses Slidev's `<v-click>` component. The audience sees the prediction prompt first; the speaker advances with a click (spacebar, right-arrow, or remote) and the answer appears.

**Slidev syntax recap:**

````markdown
**Predict:**

Setup question goes here.

<v-click>

**Actual: <answer>**

One sentence of context.

</v-click>
````

Both the opening `<v-click>` and the closing `</v-click>` must be on their own lines with blank lines around them — Slidev's Markdown parser treats them as HTML blocks.

To stage multiple reveals on a single slide (e.g. answer + then explanation), nest `<v-click>` blocks. **Do not do this** for quiz slides — one reveal per slide keeps the cognitive load matched to the one-question rule.

For multiple-choice and true-false quizzes, **do not** use `<v-click>` to hide options. All options must be visible from the start of the slide so the audience can read while the speaker reads them aloud.

---

## Inserted-ID Numbering — Why `-q` Suffix

The `interactive-editing` skill renumbers slides on every structural change (delete, move, swap, merge). The quiz generator deliberately does **not** renumber, because:

- Quiz insertion is an "enhancement pass" applied late in authoring, after slide IDs may already be referenced in other artefacts (history snapshots, review reports, external screenshots, embedded permalinks).
- Stable IDs let downstream tools diff "before quiz pass" vs. "after quiz pass" trivially: any slide whose ID matches `slide-\d+-q` is new in this pass.
- The visual numbering shown to the audience (slide 5 of 18) is derived by the renderer from array position — the `-q` suffix is internal CIF bookkeeping only and is not displayed.

If the user later runs `interactive-editing` and triggers a structural change, that skill's renumber pass will normalise everything (including replacing `-q` suffixes with regular two-digit IDs). That is expected and fine — at that point the audit trail of "what the quiz pass added" lives in the history snapshot, not in the IDs.

---

## Quiz Content Sourcing — Technical Notes

A quiz is only useful if its question can be answered from material the audience just saw. Each quiz you generate must be **traceable** to specific preceding slides.

- For a section-boundary quiz, the question must be answerable from the slides in the section that is ending.
- For a mid-section quiz, the question must be answerable from the slides between the previous quiz (or section break) and the insertion point.
- Never test material that has not yet been shown — that is not a quiz, it is a guessing game and the audience will disengage.
- Never write a "trick" question whose correct answer depends on an exception not mentioned on screen. If the exception is worth testing, it is worth a content slide first.

When you draft each question, mentally trace which slide(s) carry the answer. If you cannot point to a specific slide, the question does not belong here — either drop it or add a content slide first (which is out of scope for this skill — propose it to the user instead).

---

## Key Rules (Always Follow)

- **Never edit `slides.md` directly.** All changes go through the CIF.
- **Always save to history before overwriting the CIF.**
- **Quizzes must be answerable from material the audience just saw.** Never test unseen content; never trick the audience with unstated exceptions.
- **Every quiz must include its answer plus reasoning in speaker notes.** For open prompts, this becomes a "what to listen for" paragraph.
- **Never insert two quizzes in a row.** If candidate insertion points are adjacent, drop the lower-priority one.
- **Never exceed the `ceil(N/8)` cap** unless the user explicitly raises it after seeing the warning.
- **Never renumber existing slides.** Inserted slides use the `slide-NN-q` suffix pattern. Renumbering is the responsibility of `interactive-editing`, not this skill.
- **Always present the proposal table and wait for user approval before generating any quiz content.**
- **Read `references/best-practices.md`** at the start and apply its one-idea-per-slide rule: one question per quiz slide, never two.
