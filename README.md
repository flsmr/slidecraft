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

## Usage

```bash
# Import a corporate PowerPoint template as a Slidev theme
/slidecraft:import-template path/to/company-template.pptx

# Start a new presentation (Phase 2)
/slidecraft:start
```

## Three-Repo Architecture

As of T-07 the slidecraft project is split into three independent repositories
that live side-by-side under `D:\Archive\03_Freizeit\Projects\`:

```
D:\Archive\03_Freizeit\Projects\
├── slidecraft\                    ← THIS REPO — plugin, scripts, skills, commands
├── slidev-theme-iu\               ← IU Group corporate theme (git repo, flat)
├── slidev-theme-<name>\           ← future theme repos, one per brand
└── slidecraft-slide-decks\        ← all presentation decks (one subfolder per deck)
    └── slidecraft-IUG-test-deck\
```

**Why three repos?**
- Themes are versioned independently of decks (a theme bugfix doesn't bump every deck).
- Decks can be shared/shipped without the plugin source.
- New corporate templates get their own theme repo — run `/slidecraft:new-theme`.

**Relevant paths**

| Repo | Purpose | Location |
|------|---------|----------|
| slidecraft | Plugin scripts, skills, commands | `D:\archive\03_freizeit\projects\slidecraft\` |
| slidev-theme-iu | IU Group Slidev theme | `D:\Archive\03_Freizeit\Projects\slidev-theme-iu\` |
| slidecraft-slide-decks | All authored decks | `D:\Archive\03_Freizeit\Projects\slidecraft-slide-decks\` |

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
