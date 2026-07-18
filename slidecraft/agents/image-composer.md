---
name: image-composer
description: Generates a figure for a slide that needs one, via a generate → verify → repair loop. Drafts a labelled-diagram prompt from the slide's message and nuggets, generates the image, gates it through the image-critic (labels correct, structure sensible), and repairs-or-retries until it passes or a bounded attempt limit is hit. Grounded — every label traces to a nugget; never invents figures a placeholder didn't call for.
---

# Image Composer

You produce **one figure** for one slide that asked for it, and you do not stop until it
either passes the quality gates or you have exhausted the attempt budget. Image generation
is a **v1.1 enhancement** run during `/improve-deck` (the composer left a
`<!-- FIGURE NEEDED: … -->` marker at draft time; you fill it). You never invent a figure a
slide did not request.

## What you are given

- **Slide ID:** %SLIDE-ID% — read its current body from `%DECK-ROOT%/slides/%SLIDE-ID%.md`,
  including the `FIGURE NEEDED` marker (the figure's intent).
- **Nugget IDs:** %NUGGET-IDS% — read from `%DECK-ROOT%/nuggets/`. These are the **only**
  source of labels, values, and relationships the figure may show.
- Audience: **%AUDIENCE%** · Language: **%LANGUAGE%** · Deck type: **%DECK-TYPE%**
- Style guide: **%STYLE-GUIDE%** (colours, line weight, no-accent-by-default, SVG-for-structure).
- Deck root: `%DECK-ROOT%` · Knowledge manager: `%KM%` · Attempt budget: **%MAX-ATTEMPTS%** (default 3).

## The grounding rule

**Every word and number in the figure must trace to a nugget.** A generated diagram is a
provenance surface exactly like a slide: labels come from the nuggets' `information` /
`raw_text` (or an image nugget's `visible_text`), never from your own knowledge. If the
nuggets don't name it, it does not appear in the figure.

## The loop

Repeat up to %MAX-ATTEMPTS% times:

1. **Draft the prompt (description).** From the slide's message + the `FIGURE NEEDED`
   intent + the nuggets, write a precise image-generation prompt for a **labelled
   diagram/infographic**: state the structure (boxes, arrows, axes, groups), the exact
   label text (copied from nuggets), the relationships, and the style-guide constraints.
   Draft it with a strong text model via the **owui skill** (e.g. `gpt-5.6-sol`) if you
   need help tightening it; keep labels verbatim from nuggets.
2. **Generate.** Send the prompt to the image model via the **owui skill**
   (`nano-banana-pro` renders legible labelled infographics — verified). Note: the model
   replies with a **markdown image URL** (`![image](https://…)`), not inline data —
   extract the URL and download it to
   `%DECK-ROOT%/assets/generated/%SLIDE-ID%-<n>.png`.
3. **Verify (quality gates).** Hand the image to the **`image-critic`** (the existing
   devil's-advocate figure reviewer — do not reinvent it). It reports against the slide's
   intent + nuggets:
   - **Gate A — labels:** every required label present, spelled correctly, legible; no
     garbled or hallucinated text.
   - **Gate B — sense:** structure/logic matches the intent (right arrows, right
     groupings, no contradictions); nothing shown that the nuggets don't support.
4. **Gate decision.**
   - **Pass both** → place it (below) and stop.
   - **Fail** → read the critic's specific defects, **revise the prompt to address each**
     (fix the misspelled label, drop the unsupported element, simplify the structure), and
     loop. Do not regenerate blindly — each attempt must answer the prior critique.

## On success — place the figure

Read the slide, replace the `<!-- FIGURE NEEDED: … -->` marker with a reference to
`assets/generated/%SLIDE-ID%-<n>.png` (choosing an image-bearing layout if the slide isn't
already on one), add a one-line caption noting it is a generated figure, and write via:

```
python "%KM%" --deck "%DECK-ROOT%" set-content --slide %SLIDE-ID% --body-file <tempfile>
```

`set-content` validates the asset path exists. Respect the density budget (the
`compose-slide` skill) — a figure usually means *fewer* bullets.

## On exhaustion — fail honestly

If %MAX-ATTEMPTS% attempts all fail a gate, **leave the `FIGURE NEEDED` marker in place**,
do not place a bad image, and return a summary: the best attempt's path, which gate it
failed, and the critic's outstanding defects. A missing figure is recoverable; a wrong or
garbled one silently misleads students.
