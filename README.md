# slidecraft

A Claude Code **toolkit** that turns source material into structured, traceable, and reusable
[Slidev](https://sli.dev) **decks** via a workflow of agents whose file and state mutations run
through deterministic scripts. It also generates the Slidev **themes** those decks render with —
including converting corporate PowerPoint templates.

Two pillars:

- **Theme generation** *(working today)* — `/slidecraft:import-template` converts a corporate
  `.pptx` template into a Slidev theme (colors, fonts, logos, layouts); `/slidecraft:new-theme`
  builds a theme from any blueprint (PPTX, an existing theme, images, a website, or a plain
  description). A theme is a plain, visuals-only `slidev-theme-<slug>/` npm package that carries
  its own **style guide**, a **slot-role map** (`semantic-layouts.json`), and a **standard demo
  deck** (`example.md`) — no theme packs, no skeletons (see
  [ADR-0003](docs/adr/0003-theme-is-a-plain-slidev-theme.md); using older packs:
  [migration note](docs/theme-pack-migration.md)).
- **Agentic deck building** *(in development — see `SPEC.md`)* — users drop inputs (PDF,
  Markdown, URLs) into a deck's `input/` folder; the toolkit **converts them into sources**,
  mines atomic **knowledge nuggets** with verbatim evidence, and a workflow of agents
  (knowledge miners, a storyteller, slide composers) assembles a deck in which **every content
  slide stays traceable to its sources**. Deck shape comes from a per-deck-type **storytelling
  skill** (academic lecture, pitch, …); constraints (topic, audience, language, length, …) are
  captured once in the `/init-deck` interview.

Review agents (image-critic, didactic-critic, anti-slop) guard figure correctness, teaching
quality, and filler-free prose.

## Installation

The theme-generation pillar installs today as a Claude Code plugin:

```bash
# In Claude Code:
/plugin marketplace add flsmr/slidecraft
/plugin install slidecraft@slidecraft-marketplace
```

*(The agentic deck-building pillar, in development, is moving to an `npx` skill-repo
installer — no plugin required. See `SPEC.md` D33.)*

### Python dependencies

The helper scripts run under your local Python (3.10+). Install the core runtime deps once
per machine:

```bash
pip install -r slidecraft/requirements.txt
```

If you plan to use `/slidecraft:import-template` to convert PPTX templates into Slidev themes,
also install the importer's extras:

```bash
pip install -r slidecraft/importer/requirements.txt
```

### Viewing a deck (Slidev)

A deck is a minimal npm project: `/init-deck` scaffolds a `package.json` declaring
`@slidev/cli` + the chosen theme (Slidev resolves the theme from a local `node_modules/`). To
view a deck, from its folder run:

```bash
npm install        # first time only — creates node_modules/
npx slidev slides.md --open
```

Every deck also contains double-clickable launchers — **`show_slide_deck.cmd`** (Windows) and
**`show_slide_deck.sh`** (macOS/Linux; on macOS rename to `.command` for Finder double-click) —
that do both: install on first run, print the clickable `http://localhost:3030/` link, and open
the deck in your default browser. Requires [Node.js](https://nodejs.org) (18+). Servable images live under the deck's `public/` folder and are referenced with
root-absolute `/…` paths (Slidev serves `public/` at the site root). `node_modules/` is heavy
and is git-ignored / should be excluded from cloud sync — the deck's *data* travels, its build
deps don't.

## Usage

```bash
# Import a corporate PowerPoint template as a Slidev theme
/slidecraft:import-template path/to/company-template.pptx

# Build a Slidev theme from any blueprint (PPTX, images, website, description)
/slidecraft:new-theme my-brand
```

Deck building (`/init-deck` → `/draft-deck` → `/improve-deck`) is under construction; the design
is in `SPEC.md` (the how) and `architecture_proposal.md` (the what/why), with the domain
vocabulary in `CONTEXT.md`.

## Recommended Directory Layout

Slidecraft uses a three-component split — **toolkit**, **themes**, **decks** — that lets each
piece be versioned, shared, and shipped independently. A deck is the working directory you
launch Claude in (`/init-deck` scaffolds it in place).

```
<your-workspace>/
├── slidecraft/                    ← THIS REPO (the toolkit source)
├── slidev-theme-<brand>/          ← one theme repo per brand/template
│   └── …                          ← created by /slidecraft:import-template or new-theme
└── decks/
    └── <deck-name>/               ← one folder per presentation (launch Claude here)
```

**Why split it three ways?**
- A theme is its own repository, versioned independently of decks (a theme bugfix doesn't bump every deck).
- Decks are self-contained data folders that can be shared without the toolkit source (Slidev is fetched via `npx`).
- The toolkit stays generic: no visuals, no theme-specific content, no course content.

## Deck folder (what `/init-deck` scaffolds)

```
<deck-name>/                       # = the working directory; holds deck-context.json
├── deck-context.json             # interview answers + injection blocks + theme capabilities
├── input/                        # drop PDFs / Markdown / text here  (processed/ once mined)
├── sources/                      # converted sources: paged text + image-source records
├── slides/                       # one <title>--<stamp>.md + .json (state) per slide
├── nuggets/                      # one JSON per knowledge nugget (verbatim-anchored)
├── associations.json             # slide → nuggets
├── public/                       # Slidev-served assets: extracted/ (PDF images), generated/ (figures)
├── assets/                       # non-served provenance store (if any)
├── logs/                         # deterministic action + pipeline logs
├── slides.md                     # the Slidev entry point (order + theme headmatter)
├── package.json                  # @slidev/cli + theme (node_modules/ created on first view)
├── show_slide_deck.cmd           # double-click to view (Windows)
└── show_slide_deck.sh            # double-click to view (macOS/Linux)
```

`node_modules/` (created on first view) is git-ignored and should be excluded from cloud sync.

## Repository Structure

```
slidecraft/                        # repo root
├── slidecraft/                    # The toolkit
│   ├── commands/                  # /slidecraft:import-template, /slidecraft:new-theme
│   ├── skills/
│   │   ├── theme-import/          # PPTX → Slidev theme conversion
│   │   └── compose-slide/         # per-slide craft (density, layout, figures)
│   ├── agents/                    # knowledge-miner, image-miner, storyteller, slide-composer,
│   │                              #   image-composer, image-critic, didactic-critic, anti-slop
│   ├── scripts/                   # km.py (knowledge manager), source_converter.py, helpers
│   ├── importer/                  # PPTX parsing/emission package (+ tests)
│   ├── references/                # slop blocklist, CSL styles, bibtex guide, schemas
│   └── tests/
├── legacy/                        # Quarantined previous-generation pipeline (NOT loaded)
├── SPEC.md                        # Implementation spec (the how)
├── architecture_proposal.md       # The agentic framework design (the what/why)
├── CONTEXT.md                     # Domain glossary (ubiquitous language)
├── docs/                          # ADRs, source-conversion-limitations, project docs
├── LICENSE                        # MIT
└── README.md
```

## License

MIT
