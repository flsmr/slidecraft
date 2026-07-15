# Sprint-deck setup (per machine)

The sprint-deck pipeline is portable via the `slidecraft` plugin, but three things are machine-local
and must be configured once on each machine (they cannot be committed).

## 1. Prerequisites
- **Node.js + npm** (Slidev builds).
- **Python 3** with: `pip install pymupdf pillow requests` (extraction, gallery downscale, HTTP).
- A **Claude Code build that has the Workflow tool** (the `sprint_deck.js` / `improve_deck.js` engines run
  through it). Check `/workflows` exists. Without it, the commands still work but you run the agent phases
  manually.

## 2. The theme pack (theme + skeletons)
Decks are created from a **theme pack**: a folder holding `pack.json`, the Slidev theme package, and
`skeletons/<name>/` (skeleton.json + framing templates + author-guide + diagram-style — see
`/CONTEXT.md` and ADR-0001/0002). Register the pack once in the user-local registry:

```json
// ~/.slidecraft/packs.json
{ "packs": [ { "name": "iu-theme-pack",
               "path": "<...>/Präsentationen/slidecraft-themes/ILSE-theme" } ] }
```

`scaffold_deck.py` resolves the theme dependency path automatically (relative when possible,
absolute across drives). CSL citation styles live in `~/.slidecraft/csl/` on the same convention.

## 3. OWUI credentials (mind map / Imagen)
The mind-map step calls the IU Open WebUI. The client + secrets live at `~/.claude/skills/owui/` with a `.env`
(base URL + session token). On a new machine, copy that skill folder and create its `.env` (see `.env.example`),
or point `OWUI_SKILL_DIR` at it. Secrets are never committed. If OWUI is unreachable the build still completes;
the mind-map slide is just skipped and flagged in the DONE report.

## Triggering
Same machine:
- `/slidecraft:new-deck <deck-name>` — **the front door for new decks**: pack + skeleton interview,
  derive-first confirm round, deterministic scaffold, then the autonomous build.
- `/slidecraft:sprint-deck <deck-name>` — build from an existing `recipe.json` (re-runs).
- `/slidecraft:improve-deck <deck-name>` — polish passes over an existing deck.
- Or invoke an engine directly: `Workflow({ scriptPath: "slidecraft/workflows/sprint_deck.js", args: recipe })`.

Another machine: clone `flsmr/slidecraft` + the theme, do steps 1-3, then trigger as above.

## What is proven vs new
- **Proven on SPRINT_1/SPRINT_2:** scaffold, `extract_chapter.py`, the parallel `section-author` phase,
  `gen_mindmap.py`, assembly, build/verify.
- **New / test on the next chapter:** `gallery_search.py` (real Wikimedia search — SPRINT_2 reused SPRINT_1's
  photos because it shared the six DIN groups; a genuinely new topic exercises the search path for the first
  time). Run it, eyeball the picked images and licences before trusting the gallery.

## Grounding invariant
Nothing reaches a slide that is not in the chapter notes. The `grounding-critic` (build) and `grounding-critic`
pass (improve) are the backstop. A beautiful but ungrounded slide is a failure, not a success.
