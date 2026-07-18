---
name: compose-slide
description: The craft of writing one Slidev slide body from knowledge nuggets — density limits, visual-type-first, assertion titles, evidence bullets, figure placement. Use when composing or revising a single slide's content, or when a reviewer judges a slide's form. Triggers on "compose this slide", "write the slide body", "the slide is too long / too dense", "fix this slide's content".
---

# Compose a slide

You write the body of **one** slide from its assigned knowledge nuggets. Real teaching
copy — not a paste of the nugget digest, not a wall of text.

## The one rule (provenance)

**Say only what your nuggets support.** Every word traces to a nugget's `raw_text` or
`visible_text` anchor. No facts, numbers, or examples from your own knowledge. Thin
nuggets → short slide. That is correct, not a failure.

## Density budget — a hard cap, not a target

A content slide is a headline the speaker talks *around*, not a document. Caps for an
academic/technical slide (tighten further for keynote):

- **≤ 40 words of body total.** Count them. Over 40 = cut.
- **3–5 bullets**, never more than 6. Fewer is better — whitespace is the speaker's room.
- **≤ 8 words per bullet.** Telegraphic: drop articles. "Additive processes need no dies"
  not "The additive processes do not need any forming dies".
- **No prose paragraphs on a content slide.** One short lead line is allowed; a second
  paragraph is the wall-of-text auto-fail. If you wrote sentences, convert to bullets or cut.
- **One message.** A first-time reader grasps the point from title + lead alone. Two
  unrelated points → lead with the stronger, drop or defer the other. (You cannot merge
  slides — that is the Storyteller's job; you just compose what you were given, tightly.)

## Title and assertion

- **Title (frontmatter `title:`)** — a concept *name*: 1–5 words, a noun phrase. No
  sentence, no formula, no lone capital letters or operators. "Rapid prototyping", not
  "Rapid prototyping reaches quality sooner".
- **Body `# H1`** — the one **assertion**, ≤ 10 words, the claim the slide proves.
  `# Reaches high quality soonest`. This is what carries the argument; write it first,
  then let the bullets be its evidence.

## Bullets are evidence, not paraphrase

Each bullet is a *separate, specific* support for the assertion — a named thing, a number,
a mechanism. If a bullet just restates the title, delete it. **Concrete beats abstract
every time**: "Layer thickness down to 0.05 mm" beats "high accuracy".

No **name-drop lists**: if a nugget lists seven industries, state the *concept the list
shows* and give two or three examples — never all seven as bullets.

## Pick the visual type before the words

Choose the shape first; the words follow. Reaching for bullets first is the AI-deck
failure mode.

| Slide purpose | Visual type | Not |
|---|---|---|
| Compare 2–4 options | side-by-side / two-cols | bullets (lose the comparison) |
| Sequence / steps | numbered list or arrow flow | 2-column |
| One big number / fact | hero statement (number large) | bullet with number buried |
| Evidence for a claim | one annotated figure | 3 bullets restating the title |
| Process / pipeline | flow diagram | bullets (lose direction) |
| Small set of equal items | bullets — *only here* | — |

## Figures

- **Image nugget assigned** → place it: use its `asset` path, an image-bearing layout
  (`image-right`, `two-cols`), and a one-line caption/attribution from the nugget's
  nearest-text context. Reference only assets that exist.
- **A figure would help but none is assigned** → leave `<!-- FIGURE NEEDED: ... -->`.
  Never invent an image path.
- Choose the `layout:` from the theme capabilities you were given, matched to the modality:
  text-only → plain; image+text → two-column; image-only → figure layout.

## Named slots — fill by role, emit physical names

A theme's layouts often expose **named slots** (a cover with `title`/`subtitle`/`meta`, a
two-column with `left`/`right`). Where the theme ships a `semantic-layouts.json`, the layout
you were given carries a **`roles` map** (role → *physical* slot name), an **`intent`**, and
**`defaults`**. Fill slots **by role**, then write each into its physical slot:

- **Emit physical slot names only.** Slidev fills a named slot with an MDC block
  `::<physical-slot>::` after the frontmatter; anything not in a block goes to the default slot.
  Use the *physical* name from the `roles` map (`::body-26::`, `::ph-1::`, `::meta::`) — **never**
  a semantic alias (`::cover::`, `::title-role::`). Physical names are the only ones Slidev
  renders (ADR-0001). A single blank line separates blocks; no blank line *inside* an image
  slot (it breaks MDC parsing).
- **Follow the layout's `intent`.** It says what each slot is for and what must *not* go there
  (a cover title is a short noun phrase, never a formula; a closing title is "Thank you", never
  recap). Respect the slot's size budget when the intent states one.
- **Use `defaults` for empty role slots**, and the **deck metadata** for structural slots:
  cover/closing `title` from `defaults`; author·date into the `meta` slot; institution/contact
  into the closing's address/contact slots; the running footer from the deck's `FOOTER`.
- **No roles map?** The layout has only bare physical slots (or just a default slot) — put the
  body in the default slot and pick the closest layout by name.

Example — a cryptic-slot cover (roles `title→body-26`, `subtitle→body-25`, `course→body-19`,
`meta→body-12`), authored from deck metadata:

```markdown
---
layout: slide1
---

::body-26::
Object Tracking

::body-19::
DLMAIEFSCVAS02

::body-12::
Dr. Jane Roe · 2026-07-18
```

## Write through the script (never write the slide file directly)

Write the complete markdown (frontmatter + body) to a temp file, then:

```
python "<KM>" --deck "<DECK-ROOT>" set-content --slide <SLIDE-ID> --body-file <tempfile>
```

The script validates frontmatter, layout, and asset paths, then writes. Passing the body
as a file (not a CLI argument) is required — a shell argument silently truncates multi-line
markdown. On `{"ok": true}` you are done; return a one-line summary.

## Self-check before you write

1. Body ≤ 40 words? Bullets ≤ 6, each ≤ 8 words? No paragraph?
2. Title a concept name; assertion in `# H1`?
3. Every bullet concrete and non-restating?
4. One message a novice gets from title + lead?
5. Every claim traceable to a nugget?

If any answer is no, cut before calling set-content.
