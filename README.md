# slidecraft

Multi-agent presentation pipeline that transforms raw material into polished Slidev decks — with corporate template import, iterative improvement, and intelligent visualization suggestions. Ships as a Claude Code plugin.

## Features

- **Template Import**: Convert corporate PowerPoint (.pptx) templates into Slidev themes — extracting colors, fonts, logos, and layouts automatically
- **Authoring Pipeline** *(planned)*: Analyze raw material, draft storylines, split into slides with speaker notes
- **Visual Enrichment** *(planned)*: Per-slide visualization suggestions (Mermaid, D3.js, Excalidraw, mind maps, code blocks)
- **Interactive Review** *(planned)*: Accept, discard, or modify suggestions one by one before rendering
- **Multi-Agent Improvement** *(planned)*: Content, layout, style, narrative, and anti-slop agents iteratively refine decks

## Installation

```bash
# In Claude Code:
/plugin marketplace add flsmr/slidecraft
/plugin install slidecraft@slidecraft-marketplace
```

### Python dependencies

The plugin's helper scripts run under your local Python (3.10+). Install
the core runtime deps once per machine:

```bash
pip install -r slidecraft/requirements.txt
```

Additionally, if you plan to use `/slidecraft:import-template` to convert
PPTX templates into Slidev themes, install the importer's extras:

```bash
pip install -r slidecraft/importer/requirements.txt
```

## Usage

```bash
# Import a corporate PowerPoint template as a Slidev theme
/slidecraft:import-template path/to/company-template.pptx

# Start a new presentation (Phase 2)
/slidecraft:start
```

## Recommended Directory Layout

Slidecraft uses a three-component split — **plugin**, **themes**, **decks** —
that lets each piece be versioned, shared, and shipped independently. The
commands (`/slidecraft:import-template`, `/slidecraft:new-theme`,
`/slidecraft:new-deck`) prompt you for every location, so the components
can live anywhere you like; the layout below is just the recommended
convention.

```
<your-workspace>/
├── slidecraft/                    ← THIS REPO (cloned once; the plugin source)
├── slidev-theme-<brand>/          ← one folder per brand/template
│   └── …                          ← created by /slidecraft:import-template
└── decks/
    └── <deck-name>/               ← one folder per presentation
        └── …                      ← created by /slidecraft:new-deck
```

`<your-workspace>` can be `~/projects/`, `D:\Work\`, `/Users/me/`, or anywhere
else — none of the commands hard-code the path. They prompt for the base
location and resolve everything relative to your answer.

**Why split it three ways?**
- Themes are versioned independently of decks (a theme bugfix doesn't bump every deck).
- Decks can be shared/shipped without the plugin source.
- New corporate templates get their own theme directory — run `/slidecraft:new-theme` or `/slidecraft:import-template`.

**Note for existing users:** earlier revisions of this README documented a
hard-coded `D:\Archive\03_Freizeit\Projects\…` layout. That was the original
author's local setup, not a requirement. Any layout works as long as the
deck's `package.json` `file:` dependency resolves to a directory that
contains a Slidev theme.

## Repository Structure

```
slidecraft/
├── .claude-plugin/
│   └── marketplace.json          # Marketplace catalog
├── slidecraft/                   # The plugin
│   ├── .claude-plugin/
│   │   └── plugin.json           # Plugin manifest
│   ├── skills/
│   │   ├── theme-import/         # PPTX → Slidev theme conversion
│   │   ├── authoring/            # Storyline drafting & slide splitting
│   │   └── visual-enrichment/    # Per-slide visualization suggestions
│   ├── commands/
│   │   ├── import-template.md    # /slidecraft:import-template
│   │   └── start.md              # /slidecraft:start
│   ├── agents/
│   │   ├── content-reviewer.md   # Content quality reviewer
│   │   └── anti-slop.md          # Generic filler detector
│   ├── scripts/                  # Python/JS helper scripts
│   ├── references/               # Design guidelines & rules
│   └── templates/                # Base Slidev project scaffolding
├── docs/                         # Project documentation
├── .gitignore
├── LICENSE                       # MIT
└── README.md
```

## Roadmap

- **Phase 1**: Template import (PPTX → Slidev theme) ← *current*
- **Phase 2**: Authoring pipeline (content analysis → storyline → slide drafts)
- **Phase 3**: Multi-agent improvement loop
- **Phase 4**: ComfyUI integration for AI-generated visuals
- **Phase 5**: Interactive editing and refinement

## License

MIT
