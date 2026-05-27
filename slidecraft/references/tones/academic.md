# Academic Lecture Tone

Use this tone for university-level lecture decks (master's, upper-undergraduate). NOT for school/intro-level teaching; NOT for research talks (those are persuasion / novelty defenses — see `keynote.md`-style for the latter).

The instructions below are grounded in pedagogy literature (Ausubel, Bligh, Sweller, Mazur, Freeman 2014, Alley) and practitioner advice from CMU Math, Harvard Bok Center, Brown Sheridan, UNB CETL. Cite-tracked in the slidecraft research notes — pointers in the relevant sections below.

---

## Voice and register

- **Intimate conversation, not declaration.** Harvard Bok: "an intimate conversation regardless of the dozens or hundreds of other people". Address the student, not the auditorium. Use "we" sparingly — "you'll notice", "think about" are stronger than "we observe".
- **Reasoning aloud beats assertion.** CMU Jacobson: *"explain why you are doing things in a particular way"*. The deck's job is to walk through reasoning, not to publish conclusions. Prefer "Because the principal point can drift, K must be calibrated" over "K must be calibrated".
- **Hedge contested claims, assert uncontested ones.** Don't hedge facts ("water is wet" doesn't need "arguably"); do hedge contested numbers, dates, attributions. Use "appears to", "current consensus is", "Smith argues" for the contested cases.
- **Authoritative without arrogance.** Avoid hype ("revolutionary", "game-changing"). Avoid hedging the obvious. The reader should feel they're being taught by someone who knows the material and respects their time.

## What the deck should NEVER do

- **Slide-as-script.** Brown Sheridan: *"Slides should not be verbatim repetition of lecture content."* Slides are scaffold; the speaker is the script.
- **Title-bullet pattern.** Alley's controlled studies (peer-reviewed) show assertion-evidence beats title-bullet for comprehension AND delayed recall. Topic-label titles like "Performance" or "Calibration" are weaker than full-sentence assertions.
- **Skating over hard parts.** CMU Jacobson explicit: *"never attempt to skate over [difficult] parts; instead, draw the audience's attention to them and explain why they are tricky."* If a slide is hard, label it as hard and slow down.
- **Fact-dump.** Bligh's central empirical result: lectures are good for *information transmission* but poor for *changing thinking*. Don't try to cram the textbook — pick 3–5 ideas worth *teaching* and route the rest to the reading.
- **Math without intuition.** A bare formula slide forces the speaker to read each symbol aloud. Annotate every symbol on the slide; reserve the speaker notes for the derivation.

## Citations on academic slides

Lectures cite *less* than research talks. The convention:

- **Bottom-right inline citation** for any non-original claim or specific number, format `(Author Year)`. E.g. *"the calibration matrix has 5 degrees of freedom (Hartley & Zisserman 2003)"*.
- **Full bibliographic detail only on the References slide** at the end (one slide, alphabetised, hanging indent).
- **Reading-path hint in speaker notes**, not on the slide: *"For Tsai's method see Szeliski §11.1.4 or the 1987 paper directly"*.
- A literature-pointer slide (e.g. "Further reading") is OK if the deck is recap-style and the goal is to nudge students toward the bibliography.

## Notation and definitions

Following the math-lecture tradition (CMU):

- **Underline / bold a term on first appearance**, with the definition immediately after.
- **Distinct symbols**: never use two letters that differ only by font.
- **One symbol introduced per slide.** A slide that introduces K *and* [R|t] *and* X *and* x makes the audience juggle four new symbols in working memory.
- **Stable typographic convention across the deck** — e.g. **bold** for definitions, framed boxes for theorems, *italic header* for examples, grey for remarks. Pick one system and hold to it.
- **Number everything chapter-prefixed** if the deck is a chapter recap (e.g. *"Definition 1.3 (Pinhole projection)"*); makes self-reference and student note-taking easier.

## Worked examples — placement and density

Sweller's worked-example effect (replicated robustly for novice learners): studying worked solutions outperforms problem-solving while cognitive load is high.

- **One worked example immediately after each definition**, before any theorem uses it in earnest.
- **Integrate text into the diagram** — split-attention (text below, diagram above, eye saccades) is a measurable performance drag. Put labels ON the figure.
- **Fade examples**: a series of three (full worked → partial → ask audience to solve) is more effective than three independent full examples.
- **Small step distance**: don't make the student invent a linking move. If you'd write *"applying eq. 3, we get…"*, that "applying" had better be a substitution the student can see.

## Active-learning beats

The evidence is uneven — claims about "attention dies after 10–15 min" have been challenged (Bligh, PLOS ONE 2019) — but the *intervention*, not the spacing, is what matters.

- **2–3 active beats per 30-minute deck**. One is too few; mechanically every 10 min is folklore.
- **Pause-and-predict** before revealing a result. ("What do you think happens to depth precision when the baseline doubles?")
- **Peer Instruction** (Mazur): conceptual question → individual think → peer discussion → revote. Best for ideas with a single correct answer that's commonly mistaken.
- **Pause procedure**: 60 seconds of silent processing after a hard slide. Cheap; doesn't require a question.
- Mark active-learning slides in the deck so they're skippable if running long.

## Pacing for chapter-recap decks

- **0.33 slides/min as the default** (≈ 10 slides for 30 min), not 0.5/min.
- **Equation slides count double** for pacing purposes — a slide with three symbols to digest needs ~2 minutes.
- Better fewer slides, deeper, than more slides, shallower. Bligh's transmission-not-transformation result is the load-bearing argument.

## Skeleton: Ausubel advance-organiser + Definition→Theorem→Example→Remark

The skeleton this tone pairs with (also documented in the authoring SKILL Step 3a):

1. **Advance organiser** (1 slide): an abstract conceptual scaffold one level *above* the chapter — how this chapter relates to the larger course, what frame to bring to it. NOT a TOC.
2. **Expository core**: Definition → Worked example → Theorem (or principle) → Worked example → Remark, repeated for 3–5 such cycles per chapter.
3. **Integrative reconciliation** (1–2 slides): how the new material connects back to the advance organiser; explicit contrasts with neighbouring chapters or alternative frameworks.
4. **Consolidation cue**: a slide that nudges the student to the assessment / problem set / reading.

## Practitioner sources

- Alley, *The Craft of Scientific Presentations* + assertion-evidence research papers.
- Bligh, *What's the Use of Lectures?* — empirical synthesis of lecture effectiveness.
- Sweller — cognitive-load theory and worked-example effect.
- Mazur — Peer Instruction protocol.
- Freeman et al. (2014) PNAS — 0.47 SD active-learning gain across 225 STEM studies.
- CMU Jacobson — concrete pre-class / during / post-class lecture advice for math.
- Harvard Bok Center — *Interactive Lecture* design.
- Brown Sheridan / UNB CETL — slide-design specific cautions.

Citations and URLs are tracked in slidecraft research notes (delivered 2026-05-27). When in doubt about a specific recommendation, the SKILL points back here, and here points back to these sources.
