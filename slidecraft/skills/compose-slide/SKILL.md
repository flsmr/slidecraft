---
name: compose-slide
description: The craft of writing one Slidev slide body from knowledge nuggets — density limits, visual-type-first, assertion titles, evidence bullets, figure placement. Use when composing or revising a single slide's content, or when a reviewer judges a slide's form. Triggers on "compose this slide", "write the slide body", "the slide is too long / too dense", "fix this slide's content".

---
# General guidance for composing a slide
---

## Primary objective

Create a slide that is:

* understandable within a few seconds;
* precise enough for an academic presentation;
* readable when projected;
* useful as support for spoken explanation;
* compact enough to fit comfortably on a 16:9 slide.

The slide must communicate **one main teaching message**.

## 1. Determine the slide’s function

First infer what the slide should accomplish.

Typical functions include:

* distinguish two concepts;
* explain a relationship;
* show a process;
* motivate a problem;
* present a finding;
* compare alternatives;
* explain cause and effect;
* introduce a definition and its implication.

Choose exactly **one primary function**.

Do not combine several independent arguments on one slide.

## 2. Identify the core message

Reduce the input to one sentence:

> What should the audience remember from this slide?

Use this message to decide:

* the title;
* the content structure;
* which details to keep;
* which details to omit.

Prioritize conceptual understanding over completeness.

If information is secondary, repetitive, explanatory, or better delivered orally, omit it.

## 3. Write a short assertion title

The title must express the slide’s central message rather than merely name its topic.

Prefer:

* `Digitalisierung ermöglicht – Transformation verändert`
* `Automatisierung macht digitale Prozesse skalierbar`
* `Semantische Priors stabilisieren strukturlose Regionen`

Avoid:

* `Digitale Transformation`
* `Hintergrund`
* `Methodik`
* `Vorteile`
* `Definitionen`

### Title constraints

* Prefer **3–7 words**.
* Keep it to one line whenever possible.
* Do not place the entire explanation in the title.
* Use a contrast, conclusion, or relationship when appropriate.

## 4. Respect the available slide space

Assume that the slide also needs margins, visual hierarchy, and sufficient font size.

Use as a default:

* one title;
* two or three main content areas;
* approximately **30–55 visible words**;
* at most two hierarchy levels;
* no paragraph longer than two short lines;
* no more than four bullets in one section;
* no bullet that wraps across several lines.

Do not fill all available space. White space is part of the slide.

If the source contains too much information, reduce its scope. Do not solve the problem by shrinking text or creating many short bullets.

## 5. Compress by abstraction, not by truncation

Do not shorten sentences into vague keywords.

Bad:

* `Technische Aspekte`
* `Strategischer Wandel`
* `Neue Möglichkeiten`
* `Prozessoptimierung`

Better:

* `Einführung digitaler Technologien`
* `Strategische Neuausrichtung des Unternehmens`
* `Geschäftsmodelle · Organisation · Beziehungen`

Use compact phrases that retain the actual meaning.

A reader should not have to guess how the terms relate to one another.

## 6. Choose one clear content structure

Select the structure that best matches the teaching goal.

### For conceptual distinctions

Use a compact comparison:

```markdown
| **Concept A** | **Concept B** |
|---|---|
| Central characteristic | Central characteristic |
| Scope or examples | Scope or examples |
```

### For processes

Use a short sequence:

```markdown
**Input** → **Transformation** → **Outcome**
```

### For cause and effect

Use:

```markdown
**Cause**

→ mechanism

→ **effect**
```

### For a claim with support

Use:

```markdown
**Claim**

- Supporting point
- Supporting point
```

### For categories

Use two or three compact labeled groups.

Do not use a table, process chain, and bullet list simultaneously unless the content cannot otherwise be understood.

## 7. Make relationships explicit

The structure must show how the elements are connected.

Use words and symbols such as (in corresponding language):

* `ermöglicht`;
* `verändert`;
* `führt zu`;
* `wirkt als`;
* `im Gegensatz zu`;
* `→`;
* `während`.

Do not place related facts next to each other without explaining the relationship.

Avoid misleading process chains. Concepts that differ in scope or function must not be presented as consecutive phases unless the source explicitly supports that interpretation.

## 8. Preserve academic precision

Every statement must be supported by the input.

Do not:

* add external facts;
* invent examples;
* introduce unsupported causality;
* strengthen hypotheses into findings;
* simplify a concept until it becomes incorrect.

Preserve distinctions such as:

* technical versus strategic;
* enabler versus outcome;
* tool versus transformation;
* hypothesis versus result;
* correlation versus causation.

Use the terminology of the source consistently.

## 9. Treat automation, technologies, or methods according to their role

When the input describes several related concepts, do not give them equal visual status automatically.

Determine whether each concept is:

* a technical enabler;
* a strategic change;
* an operational mechanism;
* an outcome;
* an example;
* supporting evidence.

Represent this hierarchy visibly.

For example, if technologies enable a transformation and automation acts as an operational lever, do not present all three as equal consecutive stages.

## 10. Use examples economically

Keep examples only when they make an abstract concept easier to understand.

Present short example groups using separators:

```markdown
**KI, Big Data, IoT**
```

Do not create a separate bullet for every example.

Examples must remain subordinate to the main message.

## 11. Avoid redundant takeaways

Do not automatically add a separate takeaway box.

Add a takeaway only when it contributes an additional conclusion that is not already clear from the title and structure.

If the title already communicates the central message, use the available space for explanation rather than repetition.

## 12. Handle citations unobtrusively

If the input contains a source, include it as a short footer:

```markdown
*Quelle: Author, Year, p. X*
```

Do not place citations inside every content block unless specifically required.

The citation does not count as a main content element.

## 13. Output only visible slide content

The slide **content** is only Markdown that should appear on the slide. Do not mix
into it:

* your analysis;
* explanations of your decisions;
* layout commentary;
* alternative versions;
* recommendations for images;
* word counts;
* introductory or concluding remarks.

This rule governs the *content*, not the file wrapper: the frontmatter block and the
optional trailing speaker-notes comment required by the write mechanics below (*Named
slots*, *Presenter notes*, *Write through the script*) are part of the file format,
not slide content — those sections govern them.


# Compose a slide instructions

You write the body of **one** slide from its assigned knowledge nuggets. Real teaching
copy — not a paste of the nugget digest, not a wall of text.

## The one rule (provenance)

**Say only what your nuggets support.** Every claim traces to a nugget's `raw_text` or
`visible_text` anchor. No facts, numbers, or examples from your own knowledge. Thin
nuggets → short slide. That is correct, not a failure.


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

- **Image nugget assigned** → place it using its `asset` path: if the image nugget is the only assigned knowledge nugget -> show the image only, no text. If additional nuggets exist, use an image-bearing split layout
  (e.g., `image-right`, `two-cols`), and compose text from the other nuggets (if suitable). Reference only assets that exist.
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

## Presenter notes — leave them to the raw knowledge (default)

The slide body is telegraphic on purpose; the full source behind it belongs in the
**presenter notes**. **Do not hand-copy nugget text into notes** — when you leave the
speaker-notes block empty, `set-content` fills it **verbatim** from your slide's nuggets'
raw knowledge (`raw_text` / an image's `visible_text`, each with its locator). That keeps
the notes exact; an LLM paste would risk paraphrasing them.

Only write your own notes when you want something *other* than the raw source there — a
delivery cue, a transition. If you do, add a trailing `<!-- … -->` comment at the very end
of the slide; that suppresses the raw-knowledge fallback for this slide.

## Write through the script (never write the slide file directly)

Write the complete markdown (frontmatter + body) to a temp file, then:

```
python "<KM>" --deck "<DECK-ROOT>" set-content --slide <SLIDE-ID> --body-file <tempfile>
```

The script validates frontmatter, layout, and asset paths, then writes. Passing the body
as a file (not a CLI argument) is required — a shell argument silently truncates multi-line
markdown. On `{"ok": true}` you are done; return a one-line summary.

## Self-check before you write

1. Does the slide communicate exactly one main message?
2. Is the title a Concept Name, conclusion, distinction, or relationship?
3. Can the content be understood within a few seconds?
4. Does the slide fit comfortably without small text?
5. Are there no more than two or three main content areas?
6. Are relationships between concepts explicit?
7. Has unnecessary detail been omitted?
8. Is the slide conceptually accurate rather than merely concise?
9. Every claim traceable to a nugget?
10. Does the output contain only visible Markdown slide content?
11. Every bullet concrete and non-restating?

If any answer is no, cut before calling set-content.
