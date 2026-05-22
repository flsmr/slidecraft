---
name: authoring
description: >
  Transform raw material into a complete slide deck. Use when the user wants to
  create a new presentation, draft slides, build a deck from raw material,
  structure a talk, or turn notes into slides. Triggers on phrases like
  "create presentation", "draft slides", "build a deck", "make slides from
  these notes", "turn this into a presentation", "structure my talk",
  "write a deck about", "create slides for", "build a presentation from".
---

# Authoring Skill

You transform raw material from the `assets/` folder into a fully rendered Slidev presentation. The CIF (`.slidecraft/cif.json`) is the sole source of truth — you always write the CIF first and render `slides.md` from it. You never edit `slides.md` directly.

Before starting, read `references/best-practices.md` for presentation design rules and apply them throughout.

---

## Step 1 — Asset Analysis

Read all files in the `assets/` folder of the workspace.

For this MVP, handle the following file types:
- **Markdown files** (`.md`): read and parse as text
- **Plain text files** (`.txt`): read as text

Skip any other file types for now and note them to the user.

After reading, summarize to yourself:
- What topics and arguments appear in the material?
- What data points, quotes, or examples are present?
- What structure does the material suggest (e.g., problem → solution, timeline, comparison)?
- What does the user most likely want to communicate?

---

## Step 2 — Briefing & Clarification

Based on the assets and any instructions the user has already given, confirm the following with the user — but only ask about what is genuinely unclear. If the assets make something obvious, state your assumption and proceed.

Key questions to cover:
- **Target audience**: Who will see this? (e.g., executives, technical team, students, customers)
- **Length**: How many slides, or how many minutes? Use ~1 slide per minute as a default.
- **Key message**: What is the single most important takeaway?
- **Tone**: Formal, casual, technical, or inspirational?

If the user's instructions already answer these, skip the question and state your assumption briefly. Do not interrogate the user with a long checklist if the material is clear.

---

## Step 3 — Storyline Drafting

Create a narrative arc. Every good presentation follows a clear flow:

1. **Opening hook** — Grab attention. State why this matters.
2. **Problem or context** — Frame the challenge or situation.
3. **Key points** — Present the main ideas, one per slide.
4. **Conclusion or call to action** — What should the audience do or believe now?

Apply these rules when designing each slide:

- **One idea per slide.** If a slide has two ideas, split it.
- **Assertion-style titles.** Write what the slide proves, not just its topic. Use "Users prefer faster load times" instead of "Performance". Use "Three risks threaten the Q3 launch" instead of "Risks".
- **Maximum 7 bullet points per slide.** Prefer 3–5. Fewer is better.
- **Speaker notes are mandatory for every slide.** Write what the presenter would say out loud — not a repeat of the slide text. The notes should be a script or talking-point guide, including transitions, emphasis cues, and elaborations.

Before writing the CIF, draft the outline as a simple list:

```
Slide 01 [cover]      — "Title of the deck"
Slide 02 [default]    — "First assertion about the topic"
Slide 03 [section]    — "Section break: Part 2"
...
Slide N  [end]        — "Thank you / contact"
```

Present this outline to the user and ask for a quick thumbs-up or any structural changes before generating the full CIF. This prevents wasted work on a wrong structure.

---

## Step 4 — CIF Generation

Write the complete `cif.json`. The CIF structure is:

```json
{
  "meta": {
    "title": "Presentation Title",
    "subtitle": "Optional subtitle",
    "author": "Author Name",
    "date": "YYYY-MM-DD",
    "theme": "iu",
    "themePath": "../slidev-theme-iu"
  },
  "slides": [
    {
      "id": "slide-01",
      "layout": "cover",
      "title": "Slide Title",
      "content": "Main content text or markdown",
      "slots": {},
      "notes": "What the presenter says here...",
      "meta": {}
    }
  ]
}
```

> **Important**: The CIF uses `meta.theme` (string name) and `meta.themePath` (relative path), NOT a nested object. See `references/cif-schema.md` for the full specification.

### Layout selection guide

Choose layouts based on the purpose of each slide:

| Situation | Layout |
|---|---|
| First slide / title slide | `cover` |
| Regular content with bullets | `default` |
| Section break / chapter divider | `section` |
| Section break with gray background | `section-gray` |
| Section with overview list | `section-overview` |
| Two-column comparison | `two-cols` |
| Three-column layout | `three-cols` |
| Pull quote or testimonial | `quote` |
| Last slide (thank you / contact) | `end` |
| Divider between major parts | `divider` |
| High-emphasis accent statement | `accent` |
| Sidebar note or annotation | `side-note` |
| Key statistic or number | `fact` |
| Key statistic, light background | `fact-light` |

### Before writing the CIF

Check whether a CIF already exists at `.slidecraft/cif.json`. If it does, save a timestamped copy to `.slidecraft/history/` before overwriting:

```
.slidecraft/history/cif-YYYYMMDD-HHMMSS.json
```

Use the current date and time for the timestamp.

### Writing the file

Write the completed CIF to `.slidecraft/cif.json`. Ensure:
- Every slide has a unique `id` (e.g., `slide-01`, `slide-02`, ...)
- Every slide has non-empty `notes`
- Titles follow assertion style where the layout supports it
- Content uses markdown formatting where appropriate (bold, lists, etc.)

---

## Step 5 — Rendering

After writing the CIF, run the renderer to produce `slides.md`.

First, read `.slidecraft.json` in the workspace root to find the plugin directory (`pluginDir`). Then run:

```bash
python <plugin-dir>/scripts/render-cif.py --input .slidecraft/cif.json --output slides.md
```

The renderer uses Python standard library only — no dependencies need to be installed.

If the render fails, report the error to the user and do not leave a broken `slides.md`.

---

## Step 6 — Review & Edit Loop

After a successful render, present the slide outline to the user:

```
Deck: "Title of the Presentation"
25 slides

01 [cover]    — Title of the deck
02 [default]  — First assertion
03 [section]  — Section break: Part 2
...
25 [end]      — Thank you
```

Ask the user if they want to make any changes.

### Accepted edit commands

Handle these natural-language edit requests:

- **"Change slide 3"** or **"Rewrite slide 3"** — Ask what should change, update that slide's entry in the CIF.
- **"Add a slide about X"** — Determine the best position, create a new slide entry, renumber IDs if needed.
- **"Remove slide 5"** or **"Delete the quote slide"** — Remove the entry from the CIF and renumber.
- **"Swap slides 4 and 5"** — Exchange the two entries in the `slides` array.
- **"Show me slide 7"** — Display the full content, notes, and layout of that slide.
- **"Change the title of slide 2 to X"** — Update just the `title` field.
- **"Add speaker notes to slide 4"** — Update the `notes` field.
- **"Change the layout of slide 6 to two-cols"** — Update the `layout` field.

### For every edit

1. Save the current CIF to `.slidecraft/history/cif-YYYYMMDD-HHMMSS.json`
2. Apply the edit to `.slidecraft/cif.json`
3. Re-run the renderer
4. Confirm the change to the user

Continue the loop until the user is satisfied with the deck.

---

## Key rules (always follow these)

- **Never edit `slides.md` directly.** All changes go through the CIF.
- **Always save to history before overwriting the CIF.**
- **Speaker notes are mandatory** — every slide must have them.
- **One idea per slide** — split any slide that tries to say two things.
- **Assertion titles** — slides should state a conclusion, not just name a topic.
- **Maximum 7 bullet points per slide.** Prefer fewer.
- **Read `references/best-practices.md`** at the start and apply its guidance throughout.
