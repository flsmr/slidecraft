# Slidecraft — Start Here (agent map)

This is the navigation map. It points at the authoritative docs; it does not
restate them. Read this first, then open only what your task needs.

## Two subsystems — know which one you're in

| Subsystem | Lives in | Entry commands |
|---|---|---|
| **Core deck pipeline** (the usual work) | `slidecraft/scripts/` (esp. `km.py`), `slidecraft/agents/`, `slidecraft/components/` | `/init-deck`, `/draft-deck` |
| **Importer / theme system** (stable, rarely edited) | `slidecraft/importer/` (92 files), `slidecraft/scripts/scan_theme.py` | `/import-template`, `/new-theme` |

> **If you are NOT doing PPTX-template / theme work, ignore `slidecraft/importer/`
> and `scan_theme.py` entirely.** They are a self-contained subsystem and pure
> noise for core-pipeline tasks.

## The core pipeline (the real one — two-stage compose)

`/draft-deck` orchestrates five phases; each owning script in parens:

1. **Convert** — `input/` → `sources/` — `scripts/source_converter.py`
2. **Mine** — sources → nuggets — `km mine-brief` + agents `knowledge-miner`, `image-miner`
3. **Plan** — nuggets → `plan.json` — `km plan-brief` / `km write-plan` + agent `storyteller`
4. **Compose (TWO-STAGE)** — `scripts/compose_deck.py` drives:
   `km write-skeleton` → `scripts/design_section.py` → `km design-brief` / `km place-design`
   + agents `diagram-designer`, `image-designer`, `text-designer`, `slide-composer`
5. **Validate** — `km validate`

Agent prompts live in `slidecraft/agents/*.md`. The role→executor registry (which
model/subagent runs each role) is `scripts/invoke_shim.py`.

> The **single-stage** composer (`km write-slide`, one big role-keyed JSON) is
> **retired**. If a doc describes it as current, that doc is stale — trust
> `docs/adr/0005-two-stage-composition.md` + `commands/draft-deck.md`.

## `km.py` — live subcommands

`km.py` is the deterministic state manager; every deck mutation goes through it.
Live subcommands:

`persist-nuggets · mine-brief · mark-mined · plan-brief · write-plan ·
compose-brief · write-skeleton · design-brief · place-design · create-slide ·
associate-nuggets · merge-slides · park-slide · unpark-slide · set-content ·
set-status · clear-status · get-variants · cycle-variant · validate`

Internally `km.py` is a thin dispatcher; implementations live in `scripts/km_lib/`
(one module per concern: `nuggets`, `plan`, `compose`, `slides`, `status`,
`validate`; shared helpers in `core.py`; primitives in `_util.py`).

## Which doc is authoritative for what

| Question | Read |
|---|---|
| Vocabulary / terms | `CONTEXT.md` |
| On-disk deck layout, `km` file/subcommand contract | `SPEC.md` §3 / §5 / §6 |
| The compose pipeline (real, two-stage) | `docs/adr/0005-two-stage-composition.md` + `commands/draft-deck.md` |
| Why a decision was made | `ARCHITECTURE.md` + `docs/adr/` |
| External intro / install | `README.md` |

## Where to change X

- Edit an agent's prompt → `slidecraft/agents/<role>.md`
- Add / change a `km` subcommand → the matching `scripts/km_lib/<concern>.py` + argparse & dispatch in `scripts/km.py`
- Shared helper used by many commands → `scripts/km_lib/core.py`
- A slide's on-disk layout / states → `SPEC.md` §3 then `scripts/km_lib/`
- Theme / PPTX import → `slidecraft/importer/` (see that subsystem only)

## Run / test

- Tests: `python -m pytest -q` (config `pytest.ini`)
- Serve a built deck: `scripts/serve_deck.py`
