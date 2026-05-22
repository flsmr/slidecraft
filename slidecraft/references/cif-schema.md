# CIF — Common Intermediate Format

The CIF (Common Intermediate Format) is the single source of truth for every presentation in slidecraft. `slides.md` is always **generated** from `cif.json`; never edit the Slidev markdown directly.

---

## Top-Level Structure

```json
{
  "meta": { ... },
  "slides": [ ... ]
}
```

---

## `meta` Object

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes | Presentation title |
| `subtitle` | string | no | Subtitle shown on cover slide |
| `author` | string | no | Speaker / author name |
| `date` | string | no | ISO date string, e.g. `"2026-05-18"` |
| `theme` | string | yes | Theme name as it appears in `package.json`, e.g. `"iu"` |
| `themePath` | string | yes | Relative path from `slides.md` to the theme root, e.g. `"../../themes/iu-theme"` |

---

## `slides` Array

Each element is a **slide object**:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique slug, e.g. `"slide-01"`. Use zero-padded numbers. |
| `layout` | string | yes | Slidev layout name. Must match a `.vue` file in the theme's `layouts/` folder. |
| `title` | string | yes | Slide headline. Write as a full assertion sentence (see Rules). |
| `content` | string | no | Markdown body for the default slot. |
| `slots` | object | no | Named slot content. Keys match the slot names expected by the layout (e.g. `col1`, `col2`). Values are markdown strings. |
| `notes` | string | yes | Speaker notes in markdown. Mandatory on every slide. |
| `meta` | object | no | Per-slide frontmatter overrides merged into the YAML block (e.g. `class`, `transition`, `background`). |

---

## Available Layouts (IU Theme)

| Layout | Slots | Typical use |
|---|---|---|
| `cover` | default | Title slide |
| `default` | default | General content |
| `section` | default | Section divider with dark background |
| `section-gray` | default | Section divider with gray background |
| `section-overview` | default | Agenda / overview |
| `two-cols` | `col1`, `col2` | Side-by-side content |
| `three-cols` | `col1`, `col2`, `col3` | Three-column layout |
| `quote` | default | Pull quote |
| `end` | default | Closing / thank-you slide |
| `divider` | default | Visual break |
| `accent` | default | Highlighted statement |
| `side-note` | default, `note` | Main content + margin note |
| `fact` | default | Large stat or key fact |
| `fact-light` | default | Fact on light background |
| `statement` | default | Bold single-sentence statement |

---

## Rules for Claude when populating the CIF

### Titles (Assertion-Evidence)
- Every title MUST be a full declarative sentence, not a topic label.
- Bad: `"Performance Results"` — Good: `"Load time under 2 s increases conversion by 30 %"`
- Exception: `cover`, `section`, `end` slides may use short labels.

### Content density
- Maximum 40 words of body content per slide (academic decks); 25 words (keynote/executive).
- Maximum 4 bullet points; maximum 7 words per bullet.
- One core message per slide. If you need to say two things, use two slides.

### Speaker notes
- `notes` is **mandatory** on every slide, including cover and section dividers.
- Notes should capture what the speaker says aloud — the verbal story — not a repeat of the slide text.
- Minimum 1 sentence; no upper limit.

### Layout selection
- Use `cover` only for the opening title slide.
- Use `section` / `section-gray` to open each major chapter.
- Use `two-cols` or `three-cols` for comparisons; never put columns in `default`.
- Use `fact` or `statement` for single high-impact numbers or assertions.
- Avoid more than 5 consecutive `default` slides — vary with a visual break or section.

### Slots
- Only populate `slots` when the chosen layout actually uses named slots.
- For `two-cols`: use keys `col1` and `col2`.
- For `three-cols`: use keys `col1`, `col2`, and `col3`.
- When using named slots, leave `content` empty (or omit it).

### IDs
- Use zero-padded two-digit numbers: `"slide-01"`, `"slide-02"`, …
- IDs must be unique within the file.
- Do not reuse or reorder IDs when editing — append new slides at the end and assign the next number.

### Meta overrides
- Only add `meta` when you need to override a specific Slidev frontmatter key.
- Common uses: `"transition": "slide-left"`, `"class": "text-center"`, `"background": "#1a1a2e"`.

---

## Complete Example — "Hello World" (5 slides, IU Theme)

```json
{
  "meta": {
    "title": "Why Slidecraft Saves Time",
    "subtitle": "Automated Slidev Decks from Structured Content",
    "author": "Florian Simroth",
    "date": "2026-05-18",
    "theme": "iu",
    "themePath": "../../themes/iu-theme"
  },
  "slides": [
    {
      "id": "slide-01",
      "layout": "cover",
      "title": "Why Slidecraft Saves Time",
      "content": "Automated Slidev Decks from Structured Content",
      "slots": {},
      "notes": "Welcome everyone. Today I'll show you how the slidecraft pipeline turns structured JSON into a polished Slidev deck in seconds.",
      "meta": {}
    },
    {
      "id": "slide-02",
      "layout": "section",
      "title": "The Problem",
      "content": "",
      "slots": {},
      "notes": "Let's start with the pain point every presenter knows: maintaining slide decks is a manual, error-prone chore.",
      "meta": {}
    },
    {
      "id": "slide-03",
      "layout": "fact",
      "title": "Presenters waste 3 h per deck on formatting alone",
      "content": "Source: internal survey, n = 42",
      "slots": {},
      "notes": "Three hours. That's the median time lost just reformatting slides after content changes. Slidecraft eliminates that entirely by separating content from rendering.",
      "meta": {
        "transition": "slide-left"
      }
    },
    {
      "id": "slide-04",
      "layout": "two-cols",
      "title": "CIF separates content from presentation",
      "content": "",
      "slots": {
        "col1": "**Before**\n- Edit slides.md directly\n- Formatting breaks on every change\n- No version history",
        "col2": "**After**\n- Edit cif.json only\n- slides.md is always regenerated\n- Full history in `.slidecraft/history/`"
      },
      "notes": "The key insight is the CIF. Think of it like a database record for your talk. The renderer turns it into beautiful Slidev markdown every time.",
      "meta": {}
    },
    {
      "id": "slide-05",
      "layout": "end",
      "title": "Thank You",
      "content": "Questions? your.email@example.com",
      "slots": {},
      "notes": "That's a wrap. Happy to take questions — especially about the theme extraction pipeline we built in Phase 1.",
      "meta": {}
    }
  ]
}
```
