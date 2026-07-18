# Using your existing theme *packs* with the new plain-theme model

Your theme folders under `…/slidecraft-themes/` (`ILSE-theme/`, `general-theme-pack/`, …) are old
**theme packs** from the sprint/theme-pack era. A pack is an outer wrapper containing:

```
<slug>-theme-pack/            (or <Name>-theme/)
├── slidev-theme-<slug>/      ← the REAL theme (plain Slidev theme — still valid)
│   ├── package.json  layouts/*.vue  components/*.vue
│   ├── semantic-layouts.json  styles/  public/  assets/
│   └── (maybe) styleguide.md   example.md
├── skeletons/                ← DEAD under the agentic framework (deck shape moved out)
├── pack.json                 ← DEAD (no packs anymore)
└── styleguide.md             ← at the PACK root in old packs; the theme now owns this
```

Under `docs/adr/0003-theme-is-a-plain-slidev-theme.md`, a theme is just the inner
`slidev-theme-<slug>/`; skeletons and `pack.json` are abolished (D19).

## Use a pack today — no migration needed

Point `/init-deck` at the **inner** `slidev-theme-<slug>/` folder (theme type: **local**), not at
the pack wrapper:

```
theme.type   = local
theme.source = …/slidecraft-themes/general-theme-pack/slidev-theme-general
```

`scan_theme.py` reads that inner theme correctly (layouts, `semantic-layouts.json` roles/intents/
defaults, components). This has been verified on the ILSE (cryptic-slot) and general themes.

**One gap:** in the old packs the `styleguide.md` sometimes lives at the **pack root**, not inside
`slidev-theme-<slug>/`. `scan_theme.py` only detects a `styleguide.md` at the **theme root**, so
the deck's `STYLE-GUIDE` injection will be empty until you copy it in:

```bash
cp …/general-theme-pack/styleguide.md …/general-theme-pack/slidev-theme-general/styleguide.md
```

(New themes created by `/slidecraft:new-theme` already write `styleguide.md` at the theme root.)

## Clean up when convenient (optional, non-destructive first)

The sibling `skeletons/` folder and `pack.json` are dead and can be deleted whenever you like —
nothing reads them. To flatten a pack into a standalone theme repo you can safely **copy** the
inner theme out with the helper (dry-run by default, never deletes the original):

```bash
# preview
python slidecraft/scripts/flatten_theme_pack.py --pack …/general-theme-pack
# copy the inner theme to a sibling standalone dir
python slidecraft/scripts/flatten_theme_pack.py --pack …/general-theme-pack --dest …/slidev-theme-general --apply
```

Then delete the old pack folder by hand once you've confirmed the copy. The helper never removes
your originals — deletion stays a manual, deliberate step.
