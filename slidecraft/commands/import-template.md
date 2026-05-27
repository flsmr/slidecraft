---
description: Import a PowerPoint (.pptx) template and convert it into a Slidev theme + demo deck
argument-hint: <path-to-pptx>
---

# Import Template

Convert a corporate PowerPoint template into a Slidev theme plus a demo deck
that exercises every layout, so the user can preview the conversion in the
browser.

## Steps

1. **Locate the PPTX file**: If the user provided a path as an argument, use it. Otherwise ask which .pptx file to convert.

2. **Choose output base directory**: Ask the user where to save the conversion output. Suggest `~/slidev-themes/<company-name>/` as a default. Two sub-directories will be created inside it:
   - `slidev-theme-<name>/` — the importable Slidev theme (layouts, assets, package.json)
   - `deck/` — a demo deck (`slides.md` + `package.json`) that consumes the theme via a `file:` dependency, so the user can preview every layout immediately.

3. **Choose theme name**: Ask the user for a short slug (e.g., "iu", "corporate", "brand"). It becomes the npm package name `slidev-theme-<name>` and lands in the deck's `theme:` frontmatter.

   **Normalize the slug to a valid npm package name before passing it to `convert()`.** npm (and therefore Slidev's startup check) rejects anything that isn't lowercase letters / digits / hyphens / underscores / dots, with no leading dot or underscore. Apply these transforms silently to whatever the user typed:
   - Lowercase everything (`ILSE` → `ilse`, `Corporate` → `corporate`)
   - Replace spaces and other invalid characters with hyphens (`my brand` → `my-brand`)
   - Strip leading dots and underscores

   If the result is still empty or invalid (e.g. user entered `!!!`), ask them for a different slug rather than guessing. The Python entry point validates again and will raise `ValueError` with an actionable hint if anything slips through — but normalizing here avoids the user seeing that error.

4. **Install Python dependencies** (if not already present):
   ```bash
   pip install python-pptx lxml Pillow --break-system-packages -q
   ```

5. **Run the conversion**: Invoke the importer's `convert()` entry point directly. It parses the .pptx, extracts and deduplicates picture assets (with crop/duotone derivatives), writes per-slide `.vue` layouts, generates the theme `package.json`, and emits the demo `slides.md`:

   ```bash
   python -c "
   from pathlib import Path
   from slidecraft.importer.convert import convert

   base = Path(r'<output-base>')
   r = convert(
       pptx_path=Path(r'<pptx-path>'),
       theme_dir=base / 'slidev-theme-<name>',
       deck_dir=base / 'deck',
       theme_name='slidev-theme-<name>',
   )
   print(r)
   "
   ```

   The call returns a `ConvertResult` dataclass with `slides_count`, `typefaces_total`, `typefaces_substituted`, `sans_families`, `alias_font_faces`, and `warnings`.

   Note: this command currently has no CLI shim — it calls the Python API directly. A `python -m slidecraft.importer` entry point may be added later; until then, prefer the `python -c` invocation above.

6. **Install deck npm dependencies**: The theme itself declares no npm deps (Slidev provides UnoCSS transitively via `@slidev/cli`), so the install must happen in the **deck** directory, not the theme:

   ```bash
   cd "<output-base>/deck"
   npm install
   ```

   This pulls in `@slidev/cli` and links the local theme via the `file:../slidev-theme-<name>` dependency that the deck's `package.json` declares.

7. **Review results**: Report what landed on disk and what `ConvertResult` returned:
   - `slides_count` — number of layouts emitted as `<theme-dir>/layouts/slide<N>.vue` (one per slide in the source PPTX)
   - `sans_families` — fonts the theme references via Google Fonts (or local @font-face if substituted)
   - `typefaces_substituted` — count of MS-proprietary fonts (Calibri, Cambria, …) auto-remapped to open-source metric-compatible families (Carlito, Caladea, …)
   - `alias_font_faces` — count of weight-suffix aliases (e.g. "Source Sans Pro Bold" → ("Source Sans Pro", 700))
   - Extracted assets — list `<theme-dir>/assets/` (SHA1-deduplicated images plus any crop/duotone derivatives)
   - `warnings` — any per-picture or per-slide warnings (unsupported color spaces, missing media references, derivative failures)

8. **Slot naming hint**: When the user wants to override placeholder content in the deck's `slides.md`, the slot names follow the semantic OOXML type — not numeric indices. Show a quick example so they know what to type:
   ```markdown
   ::title::
   My custom title

   ::body-19::
   My custom body text

   ::picture-22::
   ![](/my-photo.jpg)
   ```
   Singletons (`title`, `footer`, `date`, `slide-number`, `subtitle`) emit a bare name; repeatable types use `{type}-{ooxml-idx}` so names stay stable across re-imports. See `slidecraft/importer/emit/naming.py` for the full mapping.

9. **Map layouts to semantic roles** (interactive): The importer produces one bespoke layout per source slide (`slide1.vue` … `slideN.vue`), positionally named. The `authoring` skill, however, drafts content by **role** (`cover`, `default`, `section`, `two-cols`, …). Bridging the two is the job of this step — write a `<theme-dir>/semantic-layouts.json` that maps each role to (a) one of the numbered layouts and (b) which slot inside that layout holds the title / body / image / etc.

    This step is idempotent: if `<theme-dir>/semantic-layouts.json` already exists, offer keep / update / replace (see 9c).

    ### 9a. Inventory the layouts

    List every `<theme-dir>/layouts/slide*.vue`. For each, discover its slot names by scanning the file:

    ```bash
    grep -oE 'slot name="[^"]+"' <theme-dir>/layouts/slide<N>.vue | sed -E 's/slot name="([^"]+)"/\1/' | sort -u
    ```

    Build an in-memory inventory like `slide1 → title, body-12, body-19, body-20, body-21`. You'll show this to the user when they're picking which slot serves which semantic function.

    ### 9b. Prompt for a preview

    Tell the user:

    > Your theme is built. To map the bespoke layouts to semantic roles, you'll need to see what they look like. Run `cd <output-base>/deck && npx slidev` in another terminal, page through the gallery, and note which `slideN` you'd want as cover / default content / section break / etc. Tell me when you're ready.

    Wait for them to confirm.

    ### 9c. Handle existing mapping

    If `<theme-dir>/semantic-layouts.json` already exists, read it and ask:

    > A `semantic-layouts.json` already exists with these aliases: `cover → slide1`, `default → slide3`, … Do you want to (K) keep it as is, (U) update only specific roles, or (R) replace from scratch?

    - **K** — print existing config and skip to step 10.
    - **U** — load existing as working draft; only ask about roles the user wants to change or add.
    - **R** — start fresh from step 9d.

    ### 9d. Walk through the semantic roles

    Present this table to the user, with required vs optional:

    | Role | Required? | Description |
    |---|---|---|
    | `cover` | **yes** | Presentation title slide |
    | `default` | **yes** | Standard content slide (title + body/bullets) |
    | `section` | **yes** | Section break / chapter divider |
    | `end` | **yes** | Closing slide (thank-you / contact) |
    | `two-cols` | optional | Side-by-side two-column comparison |
    | `three-cols` | optional | Three-column layout |
    | `quote` | optional | Pull-quote / testimonial |
    | `divider` | optional | Visual divider between major parts |
    | `accent` | optional | High-emphasis accent statement |
    | `fact` / `fact-light` | optional | Big statistic / key number |
    | `section-gray` / `section-overview` | optional | Section break variants |
    | `side-note` | optional | Sidebar annotation |
    | `content-image` | optional | Content slide with a primary figure |

    For each role, ask: *"Which numbered layout serves as `<role>`? (e.g. `slide3`, or `skip` for optional roles with no good match)"*. Validate that the chosen layout exists in the inventory. If the same layout is picked for two different roles, warn but allow.

    ### 9e. Map slots per role

    For each role the user mapped, look up that layout's slots from the 9a inventory and ask which slot serves which semantic function.

    Required slot mappings per role:

    | Role | Slots to map |
    |---|---|
    | `cover` | `title` (required), `subtitle` (optional), `body` (optional) |
    | `default` | `title` (required), `body` (required) |
    | `section` | `title` (required), `body` (optional) |
    | `end` | `title` (required), `body` (optional) |
    | `two-cols` | `title`, `col1`, `col2` |
    | `three-cols` | `title`, `col1`, `col2`, `col3` |
    | `quote` | `quote`, `attribution` |
    | `content-image` | `title`, `body`, `image` |
    | `fact` / `fact-light` | `value`, `label` |
    | `divider` / `accent` / `section-gray` / `section-overview` / `side-note` | `title`, `body` |

    For each slot, propose a default and let the user confirm or override:
    - If the layout has a slot literally named `title`, propose it as the `title` default.
    - Likewise for `subtitle`, `footer`, `date`.
    - For `body` in PPTX-derived layouts, propose the largest-numbered `body-NN` slot (often the main content block) — but **always** confirm, don't auto-pick.

    Example prompt: *"`slide3` exposes these slots: `title`, `body-12`, `body-19`, `body-20`, `body-25`, `body-26`. Which holds the main title? (default: `title`) Which holds the main body content? (default: `body-26`)"*

    ### 9f. Capture each role's *intent* and *defaults*

    For each role the user mapped, ask two follow-up questions. These produce the `intent` and `defaults` fields that downstream tooling (authoring skill, slide-critic) reads to respect the layout's design purpose — without these, a deck author can put recap content in a "Thank you" slide or a formula in a cover title, and the renderer will faithfully obey.

    **Intent** — a one-paragraph English description of what this layout is FOR and what should NOT go in it. Prompt:

    > *"For the `<role>` role you mapped to `<slideN>`: what is this layout for, and what should NOT go on it? (E.g. for cover: 'deck name, short noun phrase, never a formula'. For end: 'closing word like Thank you or Questions, never recap content'.)"*

    If the user passes ("don't know"), you may write the intent yourself based on the layout's visual properties (large/small fonts, picture slots, etc.) and confirm — *don't* leave intent blank, because the authoring skill relies on it.

    **Defaults** (optional) — content that should appear by default when the deck author leaves a slot empty. Most often used for `end` ("Thank you") and `section-overview` templates. Prompt:

    > *"Are there any slots that should auto-fill with default content when the deck author leaves them empty? (E.g. for the `end` role's title: 'Thank you'.) Say 'none' to skip."*

    Skip silently if the user says 'none'. Defaults are keyed by the SEMANTIC slot name (`title`, `body`, `subtitle`, etc.), not the physical PowerPoint slot.

    ### 9g. Write `semantic-layouts.json`

    Build the config (schema **v1.1**):

    ```json
    {
      "version": "1.1",
      "theme": "slidev-theme-<name>",
      "generated": "<ISO-8601 timestamp>",
      "aliases": {
        "cover": {
          "layout": "slide1",
          "slots": { "title": "body-26", "subtitle": "body-25", "body": "body-12" },
          "intent": "Deck cover. Title is the deck's name — short noun phrase, never a formula. Subtitle is a one-line tagline. Body holds location/date/audience.",
          "defaults": {}
        },
        "end": {
          "layout": "slide49",
          "slots": { "title": "title", "body": "body-13" },
          "intent": "Closing slide. Title is a fixed closing word ('Thank you', 'Questions?') — NEVER recap content. Body holds contact / next-session info.",
          "defaults": { "title": "Thank you", "body": "Questions welcome." }
        }
      },
      "unmapped_layouts": ["slide2", "slide6", "slide7"]
    }
    ```

    `intent` is free-form English; the authoring skill and slide-critic both read it. `defaults` is keyed by semantic slot name. Either field may be empty (`""` for intent, `{}` for defaults) but the field MUST be present so consumers don't have to handle the missing-key case.

    `unmapped_layouts` = every `slideN.vue` that wasn't picked. Useful for diagnostics; those layouts remain usable by their literal name (`layout: slide17`).

    Write with 2-space indentation, UTF-8, trailing newline. If overwriting (paths 9c U or R), back up the previous version to `<theme-dir>/.history/semantic-layouts-<YYYYMMDD-HHMMSS>.json` first.

    ### 9h. Report

    Print a summary table:

    ```
    Wrote <theme-dir>/semantic-layouts.json with 7 aliases:
      cover         → slide1   (title=title, subtitle=body-21, body=body-19)
      default       → slide3   (title=body-26, body=body-19)
      …
    42 layouts remain unmapped — still usable by their literal name.
    ```

10. **Offer next steps**:
    - Preview the deck in the browser: `cd <output-base>/deck && npx slidev` (defaults to `slides.md` — no need to name it explicitly)
    - If corporate fonts aren't on Google Fonts, explain how to add .woff2 files under `<theme-dir>/styles/` and add `@font-face` declarations
    - Suggest creating a fresh presentation that consumes this theme via `/slidecraft:new-deck`
