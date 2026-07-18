# ILSE Deck Recipe — reusable playbook for IU "Intensive Live Session" lecture decks

Distilled from the first full ILSE authoring run (§4.5 Object Tracking, course
DLMDSEAAD02, 2026-06-25). The *topic* changes every time; the *shape* below is
what made this deck work and should be reused. Treat this as a checklist that
sits on top of the `authoring` SKILL + `academic` tone — it does not replace them.

## What an ILSE lecture deck is

- 20-minute live teaching slot, master's level → **textbook-recap** deck mode,
  `academic.md` tone, pacing ≈ 0.5 slides/min → **15–20 slides incl. front/back**.
- Source is usually **one IU course-book chapter section** that is *thin* on the
  modern/applied side. The job is to **teach the section's concepts and enrich
  them with verified external academic literature**, not to mirror the book.
- Theme is always `slidev-theme-ilse` (the latest ILSE theme). Author against the
  theme's `semantic-layouts.json` + the actual `layouts/*.vue`, never the stale
  demo `slides.md` (slot names drift between theme revisions — verify per run).

## The fixed narrative skeleton (Ausubel advance-organiser)

1. **Cover** (slide1) — title + 2nd line + course code + author·date.
2. **Agenda** (slide2) — 4–5 rows; title is baked "Agenda", fill `agenda-N-name`
   / `agenda-N-time` (+ optional `agenda-N-subitem` on rows 2,4,5).
3. **Mind map / advance organiser** (slide5 with an SVG in `picture-14`) — the
   *signature ILSE opener the user asks for*: one diagram showing how the
   section's sub-topics connect. Animate the connectors drawing in (CSS
   `stroke-dashoffset`). This is the "what frame to bring" slide, NOT a TOC.
4. **Problem framing** (slide4) — why the topic matters; the central difficulty.
5. **Section dividers** (slide3) — big red number (`body-22` = "01"), `title`,
   `body-21` second line. 2–4 of them to chunk the deck.
6. **Expository core** (slide5 / slide4) — Definition → worked visual → principle,
   3–5 cycles. Lead with the *visual type* (Step 3c matrix); reach for bullets last.
7. **Integrative reconciliation** (slide4) — tie back to the mind map and to
   neighbouring course sections (here: Kalman/EKF → tracking → planning).
8. **References** (slide4, reduced font) — 1–2 alphabetised APA-7 slides.
9. **Thank you** (slide9) — `body-13` address, `body-14` contact.

## Research + citation procedure (the part that earns trust)

- **Fan out one research subagent per topic cluster** (`general-purpose`,
  run_in_background). 4–6 agents covering: foundations, representations, the
  core algorithms, the failure modes (occlusion/association), and the modern
  practice. Launch them first — they are the long pole — then build front/back
  matter and SVGs while they run.
- **Mandate Crossref verification in every agent prompt.** Each source must be
  checked against `https://api.crossref.org/works?query.bibliographic=<terms>&rows=5`;
  the agent returns the resolved DOI, exact authors/year/title/venue, an APA-7
  string, and a BibTeX entry. Books without a DOI are verified via publisher/ISBN
  and flagged. Discard anything unverifiable. (This run: 25/26 sources had a live
  DOI; only MOT16 was arXiv-only.)
- Agents also return **3–8 slide-ready "teachable facts"** (≤20 words, concrete,
  each tagged with citekey + locator). These map ~1:1 onto body bullets.
- Maintain `<deck>/references.bib` (APA-7-ready BibTeX) and put an inline
  `(Author Year)` in each slide's `body-13`/`body-16` footer citation slot.

## Visuals & animation (the image-in-slot rules — learned the hard way)

Authoring figures into a `picture-14` slot has exactly ONE reliable form. The
others all fail on Windows / under Slidev's compiler:

- ✅ **DO**: author each diagram as an SVG file in `public/figures/` and reference
  it with a **relative** path: `<img src="/figures/x.svg" style="width:100%;height:100%;object-fit:fill;display:block" />`.
  Slidev resolves this relative to `slides.md`, bundles it as an asset (the build
  inlines it as a data URI), and the SVG's own SMIL/CSS animations play. Same for
  raster: `<img src="/figures/photo.jpg" .../>`.
- ❌ **DON'T inline raw `<svg>…</svg>` into the slot.** Slidev's markdown→Vue
  compiler mangles it — class-styled elements survive but the structure/centre
  breaks (text overlaps, fills invert). It LOOKS right standalone, wrong embedded.
- ❌ **DON'T use `<img src="/figures/x.svg">` (absolute) or markdown `![](/…)`.**
  Slidev's slide-import-guard rewrites it to an `import`; on Windows the leading
  `/` resolves to the drive root (`C:\figures`) → "outside fs.allow", server crash.
- Match the SVG `viewBox` aspect to the box (`picture-14` ≈ 738×496, ~3:2) or
  `object-fit: fill` stretches it. AI rasters come back 1024×1024 — center-crop
  to 3:2 with PIL before use.
- **Animations** = declarative SMIL (`<animateMotion>`) or CSS (`@keyframes` in the
  SVG's own `<style>`) *inside the SVG file*; they play through `<img>`. The token
  travelling the predict→associate→update→manage loop is the reliable hero
  animation. Slidev `v-click` reveals work for *bullets* (`body-16`) but not for
  parts of an `<img>`-embedded SVG.

## Launching the dev server on Windows (non-ASCII OneDrive paths)

- Add a deck-level **`vite.config.ts`** with `server.fs.strict = false`. Without it,
  launching via the 8.3 short path while the theme is linked from a long
  `ä`-containing path makes Vite's `fs.allow` reject the theme AND its own client.
- In `.claude/launch.json` use the **8.3 short path** for `cd /d` (cmd mangles the
  `ä`) and call the **deck-local** `node_modules\.bin\slidev` (never bare `npx`).
- The MCP dev-preview server is flaky for this setup (dep re-optimization on a
  config change drops it). For reliable verification, `slidev build --out dist`
  then serve with `vite preview` — a static server that won't crash — and confirm
  every figure with a DOM check (`img.naturalWidth>0`) rather than only screenshots.
- **AI imagery** via the `owui` skill works end-to-end: `owui_ask` to model
  `nano-banana` / `nano-banana-pro` returns a hosted PNG URL → `curl` it into
  `public/figures/`. Output is 1024×1024 (square) — use for atmospheric/contextual
  scenes where some stretch is OK; prefer hand-authored SVG for anything that must
  be technically correct. (Confirmed working 2026-06-25.)

## Pre-flight before showing the user

- `python -m slidecraft.scripts.lint_slides --deck <deck>` must be clean on L1–L5
  (render-breaking). Fold L6–L12 warnings into a self-critique pass.
- Start the deck with the preview server and screenshot the `/overview/` grid to
  verify every slide actually renders on the theme before declaring done.

## Per-theme slot cheat-sheet (slidev-theme-ilse, as of 2026-05-27)

- **slide1 cover**: `body-26` title · `body-25` 2nd line · `body-19` course code
  (folder tab) · `body-12` author·date. `body-20` ("INTENSIVE LIVE SESSION") is
  BAKED — do not fill. Dark background, 72px white title blocks.
- **slide2 agenda**: title baked "Agenda"; `agenda-1..5-name`, `agenda-1..5-time`,
  `agenda-{2,4,5}-subitem`; red number chips are baked.
- **slide3 section**: `body-22` huge red number · `title` · `body-21` 2nd line.
- **slide4 default**: `title` (32px UPPERCASE) · `ph-1` (body, markdown bullets ok)
  · `body-13` citation footer (10.67px) · `footer`/`slide-number`/`date`.
- **slide5 content-image**: `title` · `body-16` left text column (~393px) ·
  `picture-14` right image/SVG box (738×496) · `body-13` citation footer.
- **slide9 end**: `title` (baked-style) · `body-13` address · `body-14` contact.
- No formulae / lone capitals / operator chars in any `title` or section body
  (lint L6 / critic Rule 12 & 13). Math goes in the body, annotated.
