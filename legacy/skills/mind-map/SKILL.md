---
name: mind-map
description: >
  Generate a beautiful mind map / concept map for a slide. Use when the user wants
  to "create a mind map", "generate a mind map", "make a concept map", "show how
  topics connect", "map out the topics", "add a mind map", or wants an
  advance-organiser opener that links a deck's themes. Produces a live, brand-themed
  simple-mind-map component (curved links, cross-branch associations, multiple
  layouts) — or a baked static SVG when needed.
---

# Mind-Map Skill

Turn a topic or outline into a polished mind map on the deck's theme. This skill is
thin: it gathers a few inputs and **delegates the real work to the
[`mind-map-expert`](../../agents/mind-map-expert.md) agent**, then helps the user
preview the result.

It exists because a mind map is a distinct visual with its own engine
(`simple-mind-map`) and quality bar — richer than the Mermaid `mindmap` stub in the
`visual-enrichment` skill. `visual-enrichment` should **delegate here** whenever a
slide is a genuine concept map rather than a flowchart/chart.

---

## Step 1 — Gather inputs (only what's unclear)

- **Outline** — the nodes and structure. Accept an indented markdown outline; if the
  user just names a topic, draft an outline from the deck's section/title slots and
  show it for a quick ok. Cross-links are written as `~ Source -> Target` lines or
  inline `[ref: TargetName]`.
- **Layout** — `radial` (default), `logical-right`, `logical-left`, `org`,
  `fishbone`, or `timeline`. If the user said "left to right" → `logical-right`;
  "radial/around a centre" → `radial`; "cause/effect" → `fishbone`.
- **Placement** — which deck + slide. Default to a **dedicated opener slide** (the
  advance organiser) unless the user points at an existing slot. A full slide gives
  the map room to breathe; a 738×496 theme slot can feel cramped for >8 nodes.
- **Mode** — `live` (default; interactive Vue component) or `static` (baked SVG for
  PDF-only export). Most ILSE lecture decks want `live`.

Don't over-ask: if the user already gave the outline and "left to right", just go.

## Step 2 — Delegate to the mind-map-expert agent

Invoke the agent via the Task tool with the gathered inputs (deck dir, outline,
layout, mode, placement, palette). The agent: builds the tree model, wires
cross-links, ensures `components/MindMap.vue` + the `simple-mind-map` dependency,
writes the data file, and inserts the component (or bakes the SVG). See
[`mind-map-expert.md`](../../agents/mind-map-expert.md) for its full protocol.

## Step 3 — Install check & preview

- The agent installs `simple-mind-map` if missing; confirm it ran (`npm i` in the
  deck). **First use in a deck must be previewed** — the live component renders in
  the browser, so verify it on the theme before declaring done.
- Start the deck (`npm run dev`) and page to the mind-map slide. Check: nodes legible,
  curves clean, cross-links land on the right nodes, colours on-brand, nothing
  clipped. If cramped in a slot, move it to a dedicated opener slide (Step 1).

## Step 4 — Iterate

Common tweaks the user will ask for, all routed back through the agent:
- "make it radial / left-to-right / fishbone" → change `layout`.
- "link X to Y" → add a `~ X -> Y` cross-link.
- "too busy" → group leaves under a new parent (keep ≤ 12 leaves).
- "different colours" → pass `accent`/`ink` props.

---

## Engine choice (for maintainers)

Primary: **`simple-mind-map`** — the only library that simultaneously gives curved
organic lines, cross-branch association links, and many layouts (radial, logical
L/R, org, fishbone, timelines) with full theming. Rendered live as a Vue component
(no headless browser needed to present).

Fallbacks, by situation:
- **Static SVG without a browser** (pure-Node bake): `d3-hierarchy` +
  `d3.linkRadial`/`linkHorizontal` (+ `d3-dag` for cross-links via jsdom), or
  ECharts `renderToSVGString`. Use when a deck must export headlessly and a live
  component isn't acceptable.
- **Mermaid `mindmap`**: only for a quick throwaway tree with no cross-links — kept
  in `visual-enrichment` as the low-fidelity path.

## Key rules
- Legibility cap: ≤ 6 first-level branches, ≤ 12 leaves, ≤ 4 cross-links.
- Live component in a slot, never inlined `<svg>` or absolute `/figures` `<img>`.
- Brand palette + transparent background so the theme shows through.
- Preview on first use in a deck before calling it done.
