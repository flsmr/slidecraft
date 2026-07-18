---
name: example-generator
description: >
  Scan a presentation's CIF for abstract or conceptual slides and generate
  worked examples, mini case studies, analogies, or counter-examples to make
  ideas tangible. Triggers on "add examples", "make it concrete", "add case
  studies", "illustrate with examples", "give examples for these concepts",
  "ground the abstract ideas".
---

# Example Generator Skill

You analyze a slide deck's CIF, identify slides whose content is abstract or conceptual, propose a concrete illustration for each candidate slide (worked example, case study, analogy, or counter-example), generate the content with strict word and structure limits, enforce cognitive-load rules, and write the updated CIF back to disk before re-rendering.

Before starting, read `references/best-practices.md` for design rules and apply them throughout. In particular, the one-idea-per-slide rule governs whether an example belongs on the original slide or on a new sibling slide.

---

## Step 1 — Read the CIF and Classify Each Slide for Example Candidacy

Read `.slidecraft/cif.json`. For every slide, examine the `title`, `content`, `layout`, `slots`, and `meta` fields together. Decide whether the slide is a candidate for example enrichment using the rules below.

### Candidacy heuristic — apply in order

A slide is an **example candidate** if **all** of the following are true:

1. Its `layout` is one of: `default`, `fact`, `concept`, `side-note`.
2. Its `meta.exampleAdded` is not `true`. (If already true, this skill has processed the slide before — skip.)
3. At least one of these content signals is present:
   - The title is an **abstract noun** (one or two words referring to a concept, e.g. "Resilience", "Convexity", "Encapsulation").
   - The `content` or relevant slot **defines a term, principle, method, or rule** without showing it applied (look for phrases like "is defined as", "refers to", "means that", "the principle of", "a method for").
   - The slide names a **named theory, model, framework, or law** (e.g. "Conway's Law", "the SOLID principles") with no scenario attached.

Otherwise, the slide is **not a candidate**.

**Skip list:** Regardless of candidacy heuristics, do not propose examples for slides with any of these layouts: `cover`, `section`, `section-gray`, `end`, `divider`, `accent`, `quote`. Mark them as `skip`.

### Example-type classification

For each candidate, choose the example type that best fits the slide's content:

| Example Type     | When to use                                                                                  | Risk profile       |
|---|---|---|
| `worked-example` | The concept is procedural — a method, algorithm, formula, or code pattern that can be walked through step by step. | Medium — must be calculation-correct. |
| `case-study`     | The concept is organisational, strategic, or applied — best shown through a real or representative scenario. | High — easy to invent facts. Use representative scenarios when no real one is at hand. |
| `analogy`        | The concept is abstract and universal (a principle, a property, a quality) and resists numeric or scenario treatment. | Low — no factual claims, just a comparison. |
| `counter-example`| The concept is frequently misapplied; showing where it *fails* clarifies its scope.          | Medium — requires accurate boundary knowledge. |

**Tie-breaker:** When two types fit equally, prefer the lower-risk option. `analogy` beats `case-study` beats `worked-example` beats `counter-example` only on tie.

---

## Step 2 — Build and Present the Proposal Table

After classifying every slide, build a proposal table and present it to the user **before generating any example content**.

Format:

```
Example Generator Proposals
============================

Slide | Title (truncated)                          | Type             | Proposed Example
------|-------------------------------------------|------------------|-----------------------------------------------
01    | [cover] Why Slidecraft Saves Time          | skip             | —
02    | [section] Core Principles                  | skip             | —
03    | Encapsulation                              | analogy          | A car's pedals hide engine internals
04    | Conway's Law                               | case-study       | Acme Corp's micro-frontend split mirrors team structure
05    | The exponential moving average smooths data | worked-example  | 3-day EMA computed across 5 sample prices
06    | Loose coupling reduces blast radius        | counter-example  | When tight coupling is actually safer (single-team monolith)
07    | Resilience                                 | analogy          | Bamboo bends in storm, oak snaps
08    | Manual formatting wastes 3 h per deck      | skip             | — (already concrete)
09    | [end] Thank You                            | skip             | —

Candidates: 5 slides. Skip-listed: 4. Already concrete: 1.

Apply all proposals? Or list slide numbers to skip/change:
```

Wait for the user's response. Accept:

- **"yes" / "all" / "apply all"** → proceed with all non-skip slides.
- A list of slide numbers → apply only those slides.
- **"skip N"** or **"change N to <type>"** → adjust before proceeding.
- **"none"** → exit the skill without modifying the CIF.

Do not proceed until the user has responded.

---

## Step 3 — Generate Example Content

For each approved slide, generate concrete example content according to its type. Rules for every type follow.

### 3a. Worked example

A worked example walks the audience through one concrete instance of applying the concept.

**Rules:**
- Begin with **one short setup sentence** (≤ 20 words) introducing the scenario.
- Follow with an **ordered list of steps** (numbered 1., 2., 3., …).
- Maximum **5 steps**.
- Maximum **60 words total** including setup and all steps.
- Use numerals (5, 12, 0.3) rather than spelled-out numbers.
- Show intermediate values where they matter — never skip from setup to answer.

**Example — exponential moving average (3-day window):**

```markdown
Compute a 3-day EMA over prices 10, 12, 11, 13, 14 (smoothing factor α = 0.5).

1. EMA₁ = 10 (seed with first price)
2. EMA₂ = 0.5 × 12 + 0.5 × 10 = 11.0
3. EMA₃ = 0.5 × 11 + 0.5 × 11.0 = 11.0
4. EMA₄ = 0.5 × 13 + 0.5 × 11.0 = 12.0
5. EMA₅ = 0.5 × 14 + 0.5 × 12.0 = 13.0
```

### 3b. Case study

A case study grounds the concept in a real or representative scenario.

**Rules:**
- **2–3 sentences**, under **50 words total**.
- Name the actor (a company, team, product, or person) — real if you are certain of the facts, representative ("a regional bank", "a 50-person engineering team") otherwise.
- State the scenario in sentence 1, the action or failure in sentence 2, the outcome or lesson in sentence 3.
- Tie the closing sentence back to the concept on the slide.

**Example — Conway's Law:**

```markdown
Acme Corp organised its checkout platform across three vertically siloed teams in 2024. Their resulting architecture also split into three loosely coupled services with brittle interfaces between them. The system's shape mirrored the org chart — exactly as Conway's Law predicts.
```

**Important:** Do **not** invent attributable statistics ("revenue rose 40 %") or quote named real individuals saying things they did not say. If you cannot verify, use a representative scenario instead.

### 3c. Analogy

An analogy compares the abstract idea to something concrete and universally familiar.

**Rules:**
- **Exactly one sentence**, under **25 words**.
- The comparison target must be drawn from **everyday physical experience** (objects, weather, body, kitchen, transport, nature).
- Avoid analogies that themselves require specialist knowledge (no "it's like a Kalman filter for…").
- Use the form: *"<Concept> is like <familiar thing> — <one shared property>."* or a natural variation.

**Example — Encapsulation:**

```markdown
Encapsulation is like a car's pedals — you press them to control the engine without ever needing to know how the engine works inside.
```

**Example — Resilience:**

```markdown
Resilience is like bamboo in a storm — it bends under pressure and returns to shape, where a rigid oak would snap.
```

### 3d. Counter-example

A counter-example shows a situation where the concept does *not* apply, or where applying it would be wrong.

**Rules:**
- **One scenario**, 1–2 sentences.
- Follow immediately with **one line explaining why** the concept fails in this scenario.
- Under **45 words total**.
- The counter-example must be plausible — do not pick an absurd edge case the audience will dismiss.

**Example — Loose coupling:**

```markdown
A single team of four engineers maintains a 2,000-line monolith with no plans to grow.

Why it fails: the coordination cost loose coupling solves does not exist here — splitting into services would add latency, deployment overhead, and on-call complexity with no organisational benefit.
```

---

## Step 4 — Apply Cognitive-Load Limits

Before writing any example to the CIF, check these hard limits. If a limit is exceeded, apply the specified remediation.

| Limit                                                   | Rule                                              | Remediation                                                                                                                                                            |
|---|---|---|
| Examples per slide                                      | Maximum **1** example per slide.                  | If two example types both seem strong, pick the lower-risk one (see Step 1 tie-breaker) and discard the other.                                                          |
| Total slide body word count                             | After adding the example, the slide body (existing text + example) must stay **≤ 60 words**. | **Split** the slide: keep the concept on the original, push the example to a new sibling slide.                                                                          |
| Worked-example step count                               | Maximum **5** steps.                              | Collapse adjacent mechanical steps into one composite step; note skipped intermediate algebra in speaker notes.                                                         |
| Case-study sentence count                               | Maximum **3** sentences.                          | Drop the weakest sentence (usually the lead-up).                                                                                                                        |
| Analogy length                                          | Maximum **25 words**, **1 sentence**.             | Rewrite tighter; if the analogy resists tightening it is probably the wrong analogy — pick a different familiar object.                                                  |
| Counter-example length                                  | Maximum **45 words** including the "why".         | Trim the scenario sentence; the "why" line is load-bearing and must stay.                                                                                               |

### Split rule (when the example pushes body past 60 words)

If the example does not fit, create a new sibling slide:

1. Keep the original slide (`slide-NN`) with its concept text unchanged.
2. Create a new slide with `id = "slide-NN-ex"` (the `-ex` suffix marks it as an example sibling). Do **not** renumber other slides.
3. The new slide gets `layout: "default"` and a title that frames the example. Suggested patterns:
   - For worked-example: *"<Concept> in practice — a worked example"*
   - For case-study: *"<Concept> at <Actor>"*
   - For analogy: *"<Concept>, made concrete"*
   - For counter-example: *"When <concept> does not apply"*
4. The new slide's `notes` should walk the speaker through the example out loud.
5. Set `meta.exampleAdded: true` on the **original** slide (it has had an example added, even though the content lives on the sibling). Also set `meta.exampleAdded: true` on the new sibling.
6. Note the split clearly in the Step-6 completion summary.

---

## Step 5 — Save History and Write the Updated CIF

### 5a. Save history

Before overwriting, copy the current CIF to the history folder:

```
.slidecraft/history/cif-YYYYMMDD-HHMMSS.json
```

Use the current date and time (UTC). Create `.slidecraft/history/` if it does not exist.

### 5b. Update each approved slide

For each approved slide, update the CIF object as follows.

**For slides where the example fits within the 60-word body limit** (most analogies, most counter-examples):

- Append the example content to the slide's `content` field with a blank line separating the original concept text from the example.
- For `concept`-layout slides whose body is intentionally minimal, the example can replace the body if the original was just a one-line restatement of the title.
- If the slide uses `slots` (e.g. `side-note`), append the example to the primary slot (`default`) — keep the `note` slot for its original purpose.

**For slides where the example forces a split:**

- Follow the Split rule in Step 4. The original slide is unchanged; the new sibling slide carries the example.

**Always update speaker notes:**

- Add a sentence to the `notes` field explaining what the example shows and how the speaker should walk through it. Notes are the speaker's script — write them in that voice ("Walk through each EMA step on screen, pausing on step 3 to highlight the smoothing effect.").

### 5c. Set the `meta.exampleAdded` flag

In each modified slide's `meta` object (and each new sibling slide), set:

```json
"exampleAdded": true
```

This lets other skills and agents know the slide has already been processed by example-generator.

### 5d. Write the file

Write the updated object back to `.slidecraft/cif.json` with two-space indentation and UTF-8 encoding. Preserve key order where possible.

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
Example Generator Complete
==========================

Modified slides : 4
New sibling slides added: 1 (slide-05-ex — worked example split from slide-05)
Skipped slides  : 4 (cover, section, end, already-concrete)

Changes:
  slide-03  analogy         → "Encapsulation is like a car's pedals…" (22 words)
  slide-04  case-study      → Acme Corp Conway's Law scenario (47 words)
  slide-05  worked-example  → Split: example moved to slide-05-ex (5 steps)
  slide-06  counter-example → Single-team monolith scenario (38 words)
  slide-07  analogy         → "Resilience is like bamboo…" (20 words)

CIF saved to .slidecraft/cif.json
History copy: .slidecraft/history/cif-20260526-143200.json
slides.md re-rendered successfully.
```

---

## Worked-Example Math — Technical Notes

When generating worked examples that include calculations, the numbers must actually check out. Errors here destroy credibility faster than any other slide defect.

- Recompute every intermediate value before writing it. Do not trust mental shortcuts on EMAs, percentages, compound interest, statistical formulae, or unit conversions.
- Show units on every numeric step (`€`, `%`, `kg`, `users/day`). Mixing implicit units across steps is a common failure.
- When using example parameters (α, β, smoothing factors, learning rates), state them in the setup sentence so the audience can follow.
- Prefer round inputs (10, 12, 100, 0.5) so the audience can verify arithmetic in their head while you talk.

---

## Case-Study Sourcing — Technical Notes

Case studies are the highest-risk example type because they make claims about reality that the audience may already know to be false.

- For named real organisations, only use facts you are confident are public and stable (e.g. "Netflix runs on AWS", "GitHub uses pull-request workflows"). Anything time-sensitive (revenue, headcount, recent strategy) should be omitted or generalised.
- When in doubt, switch to a **representative scenario**: "A regional retail bank with 200 branches…". This is honest and adds no fact-risk.
- Never invent direct quotations.
- Never invent monetary figures, dates, or named individuals.

If, while drafting, you realise the case study requires facts you cannot verify, downgrade the slide's example type to `analogy` and inform the user in the completion summary.

---

## Key Rules (Always Follow)

- **Never edit `slides.md` directly.** All changes go through the CIF.
- **Always save to history before overwriting the CIF.**
- **Never propose an example for skip-layout slides** (`cover`, `section`, `section-gray`, `end`, `divider`, `accent`, `quote`).
- **Never invent statistics, monetary figures, dates, or quotations.** When tempted to make one up, switch to a representative scenario or a different example type.
- **Never invent named real people.** Roles ("the CTO", "a senior engineer") are fine; specific identities are not.
- **When uncertain about facts, prefer `analogy`** — it has the lowest fact-risk and often produces the most memorable result.
- **Maximum 1 example per slide.** Two examples on one slide is two ideas — split into two slides instead.
- **Always update speaker notes** on any slide whose content changes. The notes are the script for delivering the example aloud.
- **Always present the proposal table and wait for user approval before generating any example content.**
- **Read `references/best-practices.md`** at the start and apply its one-idea-per-slide rule: if the example forces the slide past 60 words, split rather than cram.
