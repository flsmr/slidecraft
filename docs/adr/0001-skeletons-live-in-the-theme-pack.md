# Skeletons live in the theme pack, written in physical names

A skeleton (deck structure: framing slides, decision points, workflow config, AI-visual
style) must reference a theme's layouts to be renderable, and Slidev only renders physical
layout/slot names (semantic aliases fail at runtime — hard May 2026 lesson). We decided
skeletons live INSIDE the theme's repo ("theme pack": `slidev-theme-<name>/` + `skeletons/`),
written directly in that theme's physical names. Compatibility is guaranteed by
construction, distribution is one download, and theme + skeletons version together.

Considered and rejected: (a) a theme-agnostic skeleton library with semantic roles +
compile-time projection through each theme's `semantic-layouts.json` — more reusable across
themes, but adds a projection/compatibility subsystem nobody needs while there is one real
theme (speculative generality); (b) agents resolving slots at authoring time — reintroduces
the render-time failures the physical-names rule fixed.

Consequences: cross-theme skeleton reuse = copy the folder and rewrite only the slide
templates (the sequence/decisions/workflow-config parts are theme-free by schema). The npm
theme package itself stays visuals-only; composition knowledge lives in the sibling
`skeletons/` folder. Supersedes decision 5 (and amends 4/11) of
`slidecraft/references/workflow-design.md`.

Status: superseded (2026-07-16) — skeletons are abolished by the agentic framework
(`architecture_proposal.md`, D19): deck shape now comes from plugin-level storytelling
skills, and a theme is its own repo carrying its style guide and visual conventions
("theme pack" culled as a term). The physical-names rule itself survives — see
`CONTEXT.md`, "Physical name".
