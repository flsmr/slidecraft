# Placeholder Background Fill Investigation

## Findings

### Which placeholders carry fills?

In the test template's slide 1 layout, the layout's `<p:spTree>` has five
`<p:ph>` shapes with the following fill patterns:

| idx | hasCustomPrompt | spPr fill in layout | Slide-level spPr |
|-----|----------------|---------------------|------------------|
| 12  | 1              | *(none — xfrm only)* | empty          |
| 19  | 1              | `<a:solidFill><a:schemeClr val="bg1"/>` (`#FFFFFF`) | empty |
| 20  | 1              | `<a:solidFill><a:schemeClr val="bg2"/>` (`#C2C2C8`) | xfrm only |
| 25  | 1              | `<a:solidFill><a:schemeClr val="bg1"/>` (`#FFFFFF`) | xfrm only |
| 26  | 1              | `<a:solidFill><a:schemeClr val="bg1"/>` (`#FFFFFF`) | xfrm only |

Color resolution: `bg2 → lt2 → C2C2C8` (light gray), `bg1 → lt1 → FFFFFF` (white), via
`clrMap bg1="lt1" bg2="lt2"` on the slide master and the theme's
`<a:clrScheme>` (with `lt2 = C2C2C8`).

### Root cause

`_resolve_fill` in `parse.py` only inspected the slide-level `<p:spPr>`, which for these
placeholders had no fill element at all (just an `<a:xfrm>` or was completely empty).
The OOXML spec requires that a missing fill directive on the slide placeholder cascades to the
layout placeholder's `<p:spPr>` fill.

### What was NOT the source

- `<a:custGeom>` outline-fill — ph_19 has a custom geometry but its fill comes from `<a:solidFill>` in `<p:spPr>`, not from the geometry path data.
- `<a:ln>` / `<a:effectLst>` — ph_19 has no `<a:ln>` in its spPr; rectangle shape (ph_17) in the layout has `<a:noFill>` and only `<a:ln>` for the border outline.
- `<p:style><a:fillRef>` — only the non-placeholder decorative rectangle (id=17) has a `<p:style>`, not any of the `<p:ph>` shapes.  Style-list resolution was therefore not needed.

### Fix implemented

`_resolve_fill(sp_el, theme_el, clr_map, layout_sp=None)` now performs a two-level cascade:
1. Read fill from slide-level `<p:spPr>` — if an explicit directive (solidFill, gradFill, noFill) is found, stop.
2. If no directive, read fill from `layout_sp.<p:spPr>` the same way.

`<a:noFill>` on the slide still terminates the cascade (it is an explicit "no fill" directive,
not a missing one), ensuring authors can override layout fills intentionally.

### Result on the test template's slide 1 after fix

```
idx=12  fill=NoFill                (layout ph has no fill either — correct, text only)
idx=19  fill=SolidFill(#FFFFFF)    (bg1 white from layout)
idx=20  fill=SolidFill(#C2C2C8)    (bg2 light gray from layout — was transparent)
idx=25  fill=SolidFill(#FFFFFF)    (bg1 white from layout — was transparent)
idx=26  fill=SolidFill(#FFFFFF)    (bg1 white from layout — was transparent)
```

The faint gray/white bounding boxes that PowerPoint draws for these placeholders
now render correctly in the Slidev output.
