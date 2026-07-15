# BibTeX Guide (for authoring agents)

Every deck has ONE citation database: `<deck>/references.bib`. Slides never contain hand-written
citations — only cite MARKERS (`[@key]`). The deterministic renderer
(`python -m slidecraft.scripts.render_references --deck <deck>`) turns markers into styled short
forms and generates the paginated References / Image-sources slides. The citation style (CSL) is a
render-time choice, never baked into slide text.

## Markers in slides

| You write | Renderer produces (apa-7th, narrative) |
|---|---|
| `Source: [@martin2022]` | `Source: Martin (2022)` |
| `[@fritz2018, pp. 133-135]` | `Fritz (2018, pp. 133-135)` |
| `Source: [@din8580] (redrawn for legibility)` | `Source: DIN 8580 (2003) (redrawn for legibility)` |

Rules: the key MUST exist in `references.bib` (the renderer fails loudly on unknown keys — never
invent one). Locators go inside the marker after a comma. Never write `Author (Year)` by hand.

## Key naming

`surnameYEAR` lowercased (`martin2022`, `fritz2018`); standards use their number (`din8580`,
`din1910-100`); no-author web pages use `orgYEAR` or `slugYEAR` (`wikimedia2017`). One entry per
source; check the bib for an existing entry before adding a duplicate.

## Choosing the entry type (decision table)

| Source | Type | Required fields | Recommended |
|---|---|---|---|
| Journal article | `@article` | author, title, journal, year | volume, number, pages, doi |
| Book | `@book` | author/editor, title, publisher, year | edition, address |
| Book chapter | `@incollection` | author, title, booktitle, publisher, year | editor, pages |
| Standard (DIN/ISO/EN) | `@misc` | author = {{DIN}} (issuing body, double-braced), title, year, organization | full designation in title (`DIN 8580:2003-09: Fertigungsverfahren`); without an author the CSL renderer prints the title twice |
| Course book / script | `@book` | author, title, publisher, year | version/module code in `note` |
| Web page | `@online` | title, url, urldate, year | author (see n.a. rule), organization |
| Image / photograph | `@misc` + `keywords = {image}` | author (creator), title, url, year | see Image entries |
| AI-generated asset | `@misc` + `keywords = {image, ai-generated}` | title, year, howpublished | filename in `note` |

## Correctness rules (non-negotiable)

1. **Academic sources: import, do not transcribe.** Prefer downloading the publisher's RIS/BibTeX
   export (or resolving the DOI) and importing it:
   `python -m slidecraft.scripts.import_ris --deck <deck> --ris <file.ris>` appends a correctly
   mapped entry. Only hand-write an academic entry when no RIS/DOI exists, and then copy fields
   verbatim from the publication itself. NEVER invent DOIs, page ranges, publishers, or editions —
   when unsure, cite the course book instead (its reference list is the verified fallback).
2. **Web pages:** `urldate` (access date, `YYYY-MM-DD`) is mandatory. If no personal author is
   named, use the publishing organization as author; if neither exists, use `author = {{n.a.}}`
   (double braces, so it renders literally). Never leave `author` empty.
3. **Every field you fill must be verifiable** from the source itself or the course book's printed
   reference list. Fields you cannot verify stay absent — the renderer handles missing optional
   fields gracefully; a wrong field is worse than a missing one.
4. **Umlauts/diacritics:** write UTF-8 directly (`Kürten`, not `K{\"u}rten`).

## Image entries (photos, diagrams, AI assets)

Tag with `keywords = {image}` — the renderer routes these to the Image-sources slides instead of
References. Include the license and the deck filename:

```bibtex
@misc{cjp24calender,
  author       = {Cjp24},
  title        = {Calender machine},
  year         = {2011},
  url          = {https://commons.wikimedia.org/wiki/File:Calender_machine.jpg},
  urldate      = {2026-07-07},
  organization = {Wikimedia Commons},
  note         = {License: CC BY-SA 3.0. Used as /figures/pm_calendering.jpg},
  keywords     = {image},
}

@misc{mindmapch2,
  author       = {{Google Imagen 3}},
  title        = {Mind map of the six DIN 8580 manufacturing groups},
  year         = {2026},
  howpublished = {AI-generated via IU OpenWebUI},
  note         = {Content verified against the course book. File mindmap_ch2_v2.png},
  keywords     = {image, ai-generated},
}
```

License is MANDATORY for third-party images (PD / CC0 / CC BY / CC BY-SA with version; never NC).
AI-redrawn book figures cite the course book AND carry an `ai-generated` keyword entry naming the
original figure number.

## What the renderer does (so you know what NOT to do)

- Replaces `[@key]`/`[@key, locator]` with the rendered short form, idempotently (re-runnable when
  the style changes) — so never edit rendered citation text by hand.
- Generates `slides/references*.md` and `slides/image-sources*.md` with automatic page breaks and
  keeps the manifest imports in sync. Never hand-edit those generated files.
- Warns on: unknown keys, bib entries never cited, `<img>` files with no image entry. Fix causes
  in the bib or slides, not in the generated output.
