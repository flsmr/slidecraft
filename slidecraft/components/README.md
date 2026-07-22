# Slidecraft components

The **canonical** reusable Vue component set. This folder (`slidecraft/components/`) is the
single source of truth; each Slidev theme's `components/` directory is a **junction** back to
here, so Slidev auto-imports every `.vue` (unprefixed) in any deck built on any theme, and one
edit propagates to all themes. Use them instead of hand-drawing SVG: they carry the palette,
labels, and enter animation, so every figure is on-style by construction and future figures
stay consistent.

**Colours are baked literals, not CSS variables.** These files were derived from
`slidev-theme-general` with its design tokens (`--gen-accent` → `#28527A`, `--gen-ink` →
`#1C2530`, `--gen-sans` → Inter, …) substituted for their literal values, so a component renders
identically regardless of which theme hosts it. They are therefore **templates**: when a new
theme is created, copy this set and re-tint the literals to the new palette (rather than relying
on a per-theme token contract). During development we keep one shared version and iterate on it.

## SlideFooter
Running footer (`date · author · page`) rendered in-flow at the bottom of the content
layouts. Not used directly in slides; the layouts place it.

## Charts

Both chart components take **data, not geometry**, and animate on slide-enter (bars grow
from the baseline; donut slices sweep from 0 to their share). Both respect
`prefers-reduced-motion`. Place them in a `::figure::` slot (they render a single `<svg>`
sized to the frame) or anywhere in a slide.

### BarChart
```md
<BarChart :data="[['Q1',21],['Q2',35],['Q3',50],['Q4',64]]" unit="%" title="Adoption by quarter" />
```
| Prop | Type | Default | Notes |
|---|---|---|---|
| `data` | `Array` | required | `[label, value]` pairs or `{ label, value }` objects |
| `unit` | `String` | `''` | suffix on value labels (and the title) |
| `max` | `Number` | auto | fix the y-max instead of a nice-rounded auto max |
| `title` | `String` | `''` | optional heading inside the chart |

Single navy series, value labels drawn directly on the bars, one hairline baseline.

### PieChart (donut)
```md
<PieChart :data="[['Lecture',45],['Lab',30],['Self-study',25]]" />
```
| Prop | Type | Default | Notes |
|---|---|---|---|
| `data` | `Array` | required | `[label, value]` pairs or `{ label, value }` objects |
| `colors` | `Array` | navy/ochre/teal… | override the default palette |
| `donut` | `Boolean` | `true` | `false` renders a full pie |

Shares shown as percentages in a right-hand legend.

## Diagram component library

A large set of reusable, on-style diagram components ships alongside the charts. Every one
follows the same contract as the charts (**data in, geometry out**; theme tokens only; one
scalable root; a toggleable enter animation via `:animate="false"`), so they drop into a
`::figure::` slot or anywhere in a slide and stay on the house style by construction. All of
them render with sensible baked-in example data when called with **no props** — see the
"Component library" section at the end of the `testing-visuals` deck for a live gallery of
every component with its default data.

Each component's own file header documents its full prop list with a copy-paste example.

### Numerical data
`LineChart` · `AreaChart` · `GroupedBarChart` · `StackedBarChart` · `HorizontalBarChart` ·
`ScatterPlot` · `SlopeChart` · `RadarChart` · `Histogram` · `BoxPlot` · `Heatmap` ·
`WaterfallChart` · `Treemap` · `SankeyDiagram` · `GanttChart` (plus `BarChart`, `PieChart` above).

### Structural / SmartArt
`FlowDiagram` · `IPODiagram` · `CycleDiagram` · `ControlLoop` · `HierarchyTree` ·
`TieredArchitecture` · `PyramidDiagram` · `FunnelDiagram` · `HubSpoke` · `RadialConcept` ·
`VennDiagram` · `MatrixQuadrant` · `TwoColumnCompare` · `BeforeAfter` · `CauseMechanismEffect` ·
`Fishbone` · `DecisionTree` · `Roadmap` · `Swimlane` · `NestedBox` · `Staircase` ·
`BridgeDiagram` · `AnnotatedArchitecture` · `GroupedCards`.

Conventions worth knowing when editing them:
- **One canonical card: `GenBox`.** Every box/card across the diagrams (and the FlowDiagram
  reference) uses the same look — paper fill, 8px corner radius, 1px hairline frame on the
  top/right/bottom, and a 3px accent that **hugs the rounded corners on the left**. The
  SVG-based diagrams render this through the shared `GenBox.vue` component
  (`<GenBox :x :y :w :h :accent />`, plus `:fill` and `:emphasis` for a root/current/primary
  card); the HTML/CSS diagrams get the identical result from CSS `border-left: 3px` +
  `border-radius: 8px`. GenBox draws the left bar as a **clipped fill** (the SVG equivalent of
  `border-left` under `border-radius`) so it sits flush inside the outline rather than as a
  detached stroked bracket. When adding or editing a boxed diagram, route its boxes through
  `GenBox` (or the matching CSS) rather than hand-rolling a rect + accent, so they stay
  consistent.
- **Colours** come from the theme tokens (`--gen-accent` navy, `--gen-accent-2` ochre,
  `--gen-accent-3` teal) with tints (`#7FA8CF`, `#9AA7B5`, `#C9A66B`) for a 4th+ series;
  never hard-code a themable hex.
- **Animation** uses the shared `progress` ref (0→1, easeOutCubic) started on mount and on
  slide re-entry, guarded by `prefers-reduced-motion` and the `animate` prop. Static PNG/PDF
  export captures the final frame, so the animation is always purely additive.
- **Structural diagrams** use inline SVG for precise geometry and HTML+CSS (flexbox/grid) for
  text-heavy box/card layouts, whichever renders cleanest.
- **Component names must not begin with an Iconify collection prefix.** Slidev's icon
  auto-resolver (`unplugin-icons`, `prefix: ""`) claims any component whose lowercased name
  starts with a real collection code and tries to load it as an icon — e.g. `Fe…` → the
  `fe` (Feather) collection, `La…` → `la` (Line Awesome) — which crashes the dev transform.
  This is why `FeedbackLoop` and `LayeredArchitecture` are named `ControlLoop` and
  `TieredArchitecture`. Avoid names starting with `fe`, `la`, `mi`, `bi`, `ph`, `ic`, etc.

## Nested-list authoring (structural diagrams)

Every **structural / SmartArt** diagram above can be authored two ways, and you can mix them:

1. **Props** — pass the data object/array (`:cards`, `:steps`, `:root`, …). Best when the data
   is generated or lives elsewhere. Each component's file header shows the prop shape.
2. **A nested markdown bullet list in the default slot** — write the content *in the slide*.
   When the slot contains a list it **wins**; otherwise the props/defaults are used. This is
   the readable, quick-to-edit path, and the graphic re-lays-out reactively as you add/remove
   bullets (HMR + a `MutationObserver` keep it live). The shared parser lives in
   [`_slotAuthoring.js`](./_slotAuthoring.js).

```md
<GroupedCards>

- 🔎 Discover | Explore
  - Interview users
  - Map constraints
- 🎯 Define | Align
  - Frame the problem

</GroupedCards>
```

Encodings inside a bullet's label text:
- a **leading emoji** → the item icon (where the component has one),
- ` | ` splits the label into segments — `label | badge`, `label | desc`, or
  `criterion | left | right` depending on the component,
- a trailing **`[navy|ochre|teal|#hex]`** → a per-item colour (maps to `--gen-accent` /
  `--gen-accent-2` / `--gen-accent-3`, or a literal hex).

Per-component mapping (top-level `<li>` unless noted):

| Component | Nested-list shape |
|---|---|
| `GroupedCards` | card = `icon Label \| badge`; nested = items |
| `FlowDiagram` | step = `title \| desc` |
| `IPODiagram` | exactly 3 li (Input / Process / Output); nested = items |
| `CycleDiagram` | stage = `label \| desc` |
| `ControlLoop` | node = `label \| desc` (feedback from/to stay props) |
| `HierarchyTree` | the nested list **is** the tree (`label \| desc`, recurse) |
| `NestedBox` | nested list = containment (recurse) |
| `TieredArchitecture` | layer = `name \| desc`; nested = item chips. A `Cross-cutting` (or `Sidebars`) li → its children become the right-hand sidebars |
| `PyramidDiagram` | level = `label \| desc`, top→bottom |
| `FunnelDiagram` | stage = `label \| value` (or `label: value`); optional 3rd segment `\| note` = custom right callout (else auto conversion rate) |
| `HubSpoke` | 1st li = hub; its children = spokes (`label \| desc`) |
| `RadialConcept` | 1st li = centre; children = branches; grandchildren = items |
| `CauseMechanismEffect` | 3 li = cause / mechanism / effect (`label \| desc`) |
| `Fishbone` | optional childless 1st li = effect; each other li = category, nested = causes |
| `DecisionTree` | nested list = tree; label ending `?` = decision; child `Yes:`/`No:` sets the edge |
| `Roadmap` | milestone = `date \| title \| desc`; leading `[x]` = done |
| `Staircase` | level = `label \| desc`, lowest→highest (`current` stays a prop) |
| `BeforeAfter` | 2 li ("Before", "After"), each nested = points |
| `TwoColumnCompare` | row = `criterion \| left \| right`; a leading `= Left title \| Right title` li sets the two column headings |
| `BridgeDiagram` | 1st li = from, last li = to (`label \| desc`); middle li = enabler pillars |

**Prop-only (no list authoring):** `Swimlane`, `AnnotatedArchitecture`, `MatrixQuadrant`,
`VennDiagram`. These are graph/position-shaped (x/y coordinates, set overlaps), not
list-shaped, so they keep prop-based authoring. The numerical charts also stay prop-based
(they already take `:data`).

## Adding a new chart type (line, stacked bar, …)

Copy an existing component and keep the same three conventions, so agents and readers can
predict how it works:
1. **Data in, geometry out.** Props carry data; the component computes coordinates and pulls
   colours from the theme tokens (`var(--gen-accent)`, `--gen-accent-2`, `--gen-accent-3`).
   Inline SVG can read CSS custom properties, so never hard-code hexes for the series colours.
2. **Enter animation via a shared `progress` ref** (0 → 1, easeOutCubic), started when
   `useNav().currentPage === useSlideContext().$page`, guarded by `prefers-reduced-motion`.
   Do not re-declare `$slidev` / `$page` / `$nav` in setup (they are auto-injected); read them
   off the object returned by `useSlideContext()`.
3. **One `<svg>` root, `width:100%`,** so it drops into a `::figure::` slot and scales.

Note: static PNG/PDF export captures the final frame (animation only plays live and in the
browser exporter). Export the demo with `slidev export --format png --wait 1200` so the
animation has completed before capture.
