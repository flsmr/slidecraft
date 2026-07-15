# ILSE Author Guide (sprint-deck)

Handed to every `section-author` agent. It is course-agnostic: the concrete strings
(`{{FOOTER}}`, `{{DATE}}`, `{{PREFIX}}`) are filled from the deck's `recipe.json`.
Copied from the working SPRINT_1 / SPRINT_2 decks — match these conventions EXACTLY so the
output drops straight into `slides.md` and renders.

## Hard grounding rule
Use ONLY facts present in your section's text file (and what you can read in the figure images).
Never invent a process, number, or classification. If the notes do not say it, it does not go on
the slide. Examples and mnemonics may appear in the presenter NOTES only, never in the slide body.

## House style (non-negotiable)
- NO centre dot `·`. NO em-dash `—`. Use a colon `:` or a comma. (En-dash `–` is fine for ranges.)
  This applies EVERYWHERE, including `alt` texts and presenter notes.
- HTML attribute values (`alt="..."`) must contain NO double quotes and NO em-dashes: plain words,
  commas, parentheses only. A quote inside an attribute breaks the build.
- Every content slide body opens with ONE ~10-word intro sentence, THEN a blank line, THEN the bullets.
- Bullets are related ITEMS, telegraphic (aim ≤ 7 words), max ~5. A bullet may lead `**Term:** gloss`.
- Figure caption = a cite MARKER, not a hand-written citation: `Source: [@schmid2013]`. The key must
  exist in the deck's `references.bib` (see `references/bibtex-guide.md`). A deterministic script
  renders the marker into the styled short form (`Martin (2022)`) and builds the References slides.
  Never hand-format an APA string; never invent a key.
- Title = short concept name (1–5 words). No formula, no sentence, no lone capital letters.
- Presenter notes on EVERY slide: 3–5 say-bullets, then `- Example to tell: ...` and `- Memory hook: ...`.

## Image sourcing ladder (in this order, never skip a rung)
1. **Course-book figure as-is** — always first choice; it is licensed and already extracted.
2. **The same figure rotated or AI-redrawn** when it is portrait or unreadable on a landscape slide.
   An AI redraw must be built from a verbatim transcription of EVERY label (canonical-labels list),
   then verified label-by-label against the original. Caption gains `(redrawn for legibility)`.
3. **Wikimedia Commons — real-world PHOTOS only** (machines, parts, plants). NEVER search the web for
   labelled diagrams or schematics: results are unusable (wrong language, wrong content, wrong era).
4. **AI-generate a diagram from the section text** only when no book figure covers the concept at all.
   Credit as AI-generated on the Image-sources slide.

## Portrait figures
A portrait image (height > width) on a `slidefigure` slide renders too small to read. Before using one:
rotate it 90° if the content reads correctly rotated (trees/charts often do), or redraw it left-to-right
(landscape), or switch to `slide5` split layout. Never leave a portrait classification chart full-width.

## Reusing or deriving figures (honest framing)
If a slide reuses a figure that belongs to another concept (e.g. a shared mechanism), the bullets, alt
text, and presenter notes MUST say so explicitly and explain the relationship. Never let a student see
an unexplained mismatch between the slide topic and the figure's labels. Every AI-redrawn or AI-generated
asset is marked in its caption and credited on the Image-sources slide.

## Figure matching
Figure files are reliable by page, but the book's "Figure NN" numbers can drift. Open each figure image,
match it to the caption in your section text BY CONTENT, and use that caption + Source line exactly.
Prefer teaching figures (classification charts, process diagrams). You need not use every figure.

## Tables from the PDF
PDF table extraction interleaves columns and can lose cells. Before presenting a table: verify the
row pairing against the original PDF page (read the page image). If pairing cannot be verified, present
the columns as two independent lists side by side and say so in the presenter notes. Use a real HTML
`<table class="cmp-table">` inside `::ph-1::`, never ASCII art.

## Split vs full
- `slide5` (split: 1/3 text + 2/3 image) when bullets add teaching value beside the figure.
- `slidefigure` (full-width image) for a dense classification chart that speaks for itself.

## Templates (copy these slot structures EXACTLY)

### Split content slide — layout `slide5`
```
---
layout: slide5
---

::title::
Sand Casting

::body-16::
Sand casting forms metal parts by pouring melt into a sand mould.

- **Pattern:** makes the mould cavity
- **Core:** shapes internal hollows
- Melt poured, cooled, then mould broken

::picture-14::
<img src="/figures/{{PREFIX}}_fig_04.jpeg" alt="Process steps in sand casting" style="width:100%;height:100%;object-fit:contain;display:block" />

::body-13::
Source: [@schmid2013]

::footer::
{{FOOTER}}

::date::
{{DATE}}

<!--
Presenter notes:
- Walk the four steps: pattern, mould, pour, break out.
- Example to tell: An engine block is sand cast, then machined to final tolerance.
- Memory hook: Pattern, Pour, Part.
-->
```

### Full-width figure slide — layout `slidefigure`
```
---
layout: slidefigure
---

::title::
Casting Processes at a Glance

::picture-14::
<img src="/figures/{{PREFIX}}_fig_03.jpeg" alt="Classification of casting processes" style="width:100%;height:100%;object-fit:contain;display:block" />

::body-13::
Source: [@martin2022]

::footer::
{{FOOTER}}

::date::
{{DATE}}

<!--
Presenter notes:
- This chart sorts casting into its sub-families; orient students before the detail slides.
- Example to tell: ...
- Memory hook: ...
-->
```

## Slot reference (do not rename)
- `slide5`: `::title::`, `::body-16::` (intro + bullets), `::picture-14::` (one `<img>`), `::body-13::` (Source), `::footer::`, `::date::`
- `slidefigure`: `::title::`, `::picture-14::`, `::body-13::`, `::footer::`, `::date::`
- The image is always ONE `<img ... object-fit:contain ...>` inside `::picture-14::` (never markdown `![]()` in a slot — it breaks the build).
- Each slide block begins with its `---`/`layout:`/`---` frontmatter and ends with its `<!-- notes -->` comment.

## Scaffolding slides (authored by the runbook, not section agents)
`slide1` title, `agenda` (all chapters, active highlighted), `slide3` divider, `slide4` study-goals /
summary / exam-focus / references (`.srcref`), `slide9` thank-you, `gallery` (2-row `<div class="gallery">`
of `<figure>`). See `commands/sprint-deck.md` and the SPRINT_2 deck for the exact markup + the shared
`<style>` block.
