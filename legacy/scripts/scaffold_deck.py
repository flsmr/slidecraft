# -*- coding: utf-8 -*-
"""Scaffold a new deck from a THEME-PACK SKELETON (ADR-0001/0002).

Reads a theme pack (pack.json + skeletons/<name>/skeleton.json), renders the
skeleton's framing-slide templates with @@KEY@@ placeholders from recipe.json,
copies the deck-files (package.json, vite config, deck-local layouts, launcher),
writes the slides.md manifest with a CONTENT insertion marker, copies the
skeleton's author-guide.md + diagram-style.md into <deck>/resources/, and
records full provenance in <deck>/resources/recipe.json.

Usage:
  python -m slidecraft.scripts.scaffold_deck --recipe <recipe.json> \
      [--pack <path-or-registered-name>] [--skeleton sprint] [--force]

Pack resolution order: --pack as a path; --pack as a name in the user-local
registry ~/.slidecraft/packs.json; recipe["provenance"]["pack_path"].
The deck target is <recipe.deck_location>/<recipe.deck_name>. resources/ may
already exist (extraction runs before scaffolding); slides/ must not, unless
--force is given.
"""
import argparse
import datetime
import io
import json
import os
import re
import shutil
import sys

REGISTRY = os.path.expanduser("~/.slidecraft/packs.json")
MARKER = "<!-- ===== CONTENT SECTIONS (inserted by the build workflow) ===== -->"


def fail(msg: str) -> None:
    print("ERROR:", msg)
    sys.exit(2)


def load_json(path: str) -> dict:
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_pack(pack_arg: str | None, recipe: dict) -> str:
    candidates = []
    if pack_arg:
        if os.path.isdir(pack_arg):
            return os.path.abspath(pack_arg)
        candidates.append(pack_arg)
    prov = recipe.get("provenance") or {}
    if prov.get("pack_path") and os.path.isdir(prov["pack_path"]):
        return os.path.abspath(prov["pack_path"])
    if os.path.isfile(REGISTRY):
        reg = load_json(REGISTRY)
        packs = reg.get("packs", [])
        if candidates:
            for p in packs:
                if p.get("name") == candidates[0]:
                    return os.path.abspath(p["path"])
            fail(f"pack '{candidates[0]}' not in {REGISTRY}")
        if len(packs) == 1:
            return os.path.abspath(packs[0]["path"])
        if packs:
            fail(f"several packs registered in {REGISTRY}; pass --pack <name>")
    fail("no theme pack found: pass --pack <path> or register one in ~/.slidecraft/packs.json")


SCALAR = (str, int, float, bool)


def build_values(recipe: dict) -> dict:
    """Placeholder values for @@KEY@@ substitution.

    Skeleton-agnostic by design (ADR-0002: the plugin owns control flow, the
    skeleton owns structure). Every top-level scalar in the recipe becomes
    @@UPPER_SNAKE@@, so a skeleton declares whatever placeholders it needs and the
    recipe supplies them; `recipe["placeholders"]` is an explicit escape hatch that
    wins over everything. Only deck_name/deck_location are structurally required --
    render() reports any unresolved @@KEY@@ by name, which is the real (and more
    useful) validation. Chapter-shaped recipes additionally get the derived sprint
    placeholders, so existing sprint decks scaffold exactly as before.
    """
    req = ["deck_name", "deck_location"]
    missing = [k for k in req if not recipe.get(k)]
    if missing:
        fail("recipe is missing required keys: " + ", ".join(missing))

    values: dict = {}

    def put(key: str, val) -> None:
        """Set only when not already provided by a more specific source."""
        if not values.get(key):
            values[key] = str(val)

    # 1. generic: every scalar recipe key -> @@KEY@@
    for k, v in recipe.items():
        if isinstance(v, SCALAR):
            values[str(k).upper()] = str(v)
    values["DECK_SLUG"] = re.sub(r"[^a-z0-9_]+", "_", str(recipe["deck_name"]).lower()).strip("_")

    # 2. chapter-shaped (sprint) recipes: derived placeholders, unchanged semantics
    if recipe.get("chapter_number") not in (None, ""):
        ch = int(recipe["chapter_number"])
        short = str(recipe.get("chapter_title_short") or "").strip()
        parts = short.split(" ", 1)
        divider = recipe.get("divider") or {}
        agenda = recipe.get("agenda") or {}
        chapters = agenda.get("chapters") or []
        values["CHAPTER_NUMBER"] = str(ch)
        values["CHAPTER_NUMBER_2D"] = f"{ch:02d}"
        values["CHAPTER_TITLE_SHORT"] = short
        values["PREFIX"] = (recipe.get("sources") or {}).get("prefix", f"ch{ch}")
        values["AGENDA_CHAPTERS_JS"] = "\n".join(
            "  '{}',".format(str(c).replace("\\", "\\\\").replace("'", "\\'")) for c in chapters)
        values["AGENDA_ACTIVE"] = str(agenda.get("active", ch))
        values["DIVIDER_LINE1"] = divider.get("line1") or parts[0]
        values["DIVIDER_LINE2"] = divider.get("line2") or (parts[1] if len(parts) > 1 else "")
        if recipe.get("course") and recipe.get("module"):
            put("FOOTER", f"{recipe['course']}, {recipe['module']}")
        if recipe.get("course"):
            put("DECK_TITLE", f"{recipe['course']}: Sprint {ch}")
        put("INSTITUTION", "IU International University of Applied Sciences")

    # 3. explicit per-recipe overrides win
    for k, v in (recipe.get("placeholders") or {}).items():
        if isinstance(v, SCALAR):
            values[str(k).upper()] = str(v)
    return values


def render(text: str, values: dict, origin: str) -> str:
    out = text
    for k, v in values.items():
        out = out.replace(f"@@{k}@@", v)
    left = sorted(set(re.findall(r"@@([A-Z0-9_]+)@@", out)))
    if left:
        fail(f"{origin}: unresolved placeholders {left}")
    return out


def write_placeholder_png(path: str, label: str) -> None:
    """Neutral 16:9 placeholder so the deck builds before enrichment runs."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1792, 1024), "#F2F4F5")
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=44)
        except TypeError:  # older Pillow: no size kwarg
            font = ImageFont.load_default()
        box = d.textbbox((0, 0), label, font=font)
        d.text(((1792 - box[2]) / 2, (1024 - box[3]) / 2), label, fill="#575E62", font=font)
        img.save(path)
    except Exception:
        import base64  # 1x1 light-grey PNG, keeps the build green without Pillow
        io.open(path, "wb").write(base64.b64decode(
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4"
            b"//79fwAJewN9tuKfZQAAAABJRU5ErkJggg=="))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--pack", default=None, help="theme-pack path or registered name")
    ap.add_argument("--skeleton", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    recipe_path = os.path.abspath(args.recipe)
    recipe = load_json(recipe_path)
    pack_dir = resolve_pack(args.pack, recipe)
    pack = load_json(os.path.join(pack_dir, "pack.json"))
    skel_name = args.skeleton or (recipe.get("provenance") or {}).get("skeleton") \
        or (pack["skeletons"][0] if len(pack.get("skeletons", [])) == 1 else None)
    if not skel_name:
        fail("several skeletons in pack; pass --skeleton <name>: " + ", ".join(pack.get("skeletons", [])))
    skel_dir = os.path.join(pack_dir, "skeletons", skel_name)
    skel = load_json(os.path.join(skel_dir, "skeleton.json"))

    values = build_values(recipe)
    deck = os.path.join(recipe["deck_location"], recipe["deck_name"])
    slides_dir = os.path.join(deck, "slides")
    if os.path.isdir(slides_dir) and os.listdir(slides_dir) and not args.force:
        fail(f"{slides_dir} already has slides; use --force to overwrite the framing slides")

    theme_pkg_dir = os.path.join(pack_dir, pack["theme"]["path"])
    if not os.path.isdir(theme_pkg_dir):
        fail(f"theme package not found at {theme_pkg_dir}")
    try:
        theme_path = os.path.relpath(theme_pkg_dir, deck).replace("\\", "/")
    except ValueError:  # different drive
        theme_path = theme_pkg_dir.replace("\\", "/")
    values["THEME_PATH"] = theme_path

    optouts = set(recipe.get("slide_optouts") or [])
    known = {f["id"] for f in skel["framing_slides"] if not f.get("insertion_point")}
    bad = optouts - known
    if bad:
        fail(f"unknown slide_optouts {sorted(bad)}; known framing ids: {sorted(known)}")
    fixed = {f["id"] for f in skel["framing_slides"] if f.get("optout") is False}
    refused = optouts & fixed
    if refused:
        fail(f"these framing slides cannot be opted out: {sorted(refused)}")

    os.makedirs(slides_dir, exist_ok=True)
    os.makedirs(os.path.join(deck, "resources"), exist_ok=True)
    os.makedirs(os.path.join(deck, "public", "figures", "gallery"), exist_ok=True)

    # 1. deck-files (package.json, vite config, layouts, launcher, .gitignore)
    df_dir = os.path.join(skel_dir, "deck-files")
    if not os.path.isdir(df_dir):
        fail(f"skeleton '{skel_name}' has no deck-files/ at {df_dir}; it must ship at least a "
             "package.json.tmpl (and usually vite.config.ts + gitignore) or the deck cannot run")
    copied = []
    for root, _dirs, files in os.walk(df_dir):
        rel_root = os.path.relpath(root, df_dir)
        for fn in files:
            src = os.path.join(root, fn)
            out_name = fn[:-5] if fn.endswith(".tmpl") else fn
            if out_name == "gitignore":
                out_name = ".gitignore"
            dst_dir = os.path.join(deck, rel_root) if rel_root != "." else deck
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, out_name)
            if fn.endswith(".tmpl"):
                text = io.open(src, encoding="utf-8").read()
                io.open(dst, "w", encoding="utf-8", newline="\n").write(render(text, values, fn))
            else:
                shutil.copyfile(src, dst)
            copied.append(os.path.relpath(dst, deck))

    # 2. framing slides + manifest
    manifest = []
    skipped = []
    for f in skel["framing_slides"]:
        if f.get("insertion_point"):
            manifest.append(MARKER)
            continue
        if f.get("autogen"):
            continue  # generated later by render_references
        if f["id"] in optouts:
            skipped.append(f["id"])
            continue
        tpl = io.open(os.path.join(skel_dir, f["template"]), encoding="utf-8").read()
        out = render(tpl, values, f["template"])
        io.open(os.path.join(slides_dir, f["file"]), "w", encoding="utf-8", newline="\n").write(out)
        manifest.append(f["file"])

    # The skeleton's FIRST framing slide carries the deck frontmatter (it is always
    # optout:false). Which file that is belongs to the skeleton, not to the plugin.
    if not manifest or manifest[0] == MARKER:
        fail("skeleton must start with a framing slide (it carries the deck frontmatter)")
    deck_title = values.get("DECK_TITLE") or str(recipe["deck_name"])
    head = ["theme: {}".format(skel["theme"]),
            "title: {}".format(json.dumps(deck_title, ensure_ascii=False))]
    # A skeleton may declare recipe keys that belong in the deck-level headmatter
    # (e.g. themes whose running footer reads `author`/`date` from config). Opt-in,
    # so skeletons that don't declare it (sprint) keep byte-identical output.
    for key in skel.get("deck_headmatter", []):
        val = recipe.get(key)
        if isinstance(val, SCALAR) and str(val) != "":
            head.append("{}: {}".format(key, json.dumps(str(val), ensure_ascii=False)))
    head.append("src: ./slides/{}".format(manifest[0]))
    blocks = ["---\n{}\n---\n".format("\n".join(head))]
    for entry in manifest[1:]:
        if entry == MARKER:
            blocks.append(MARKER + "\n")
        else:
            blocks.append(f"---\nsrc: ./slides/{entry}\n---\n")
    io.open(os.path.join(deck, "slides.md"), "w", encoding="utf-8", newline="\n").write(
        "\n".join(blocks))

    # 2b. placeholder for images referenced by framing slides but produced later
    #     (a Slidev production build fails on unresolved /figures/... imports)
    has_mindmap = any(f.get("id") == "mindmap" for f in skel["framing_slides"])
    if has_mindmap and "mindmap" not in optouts and values.get("PREFIX"):
        ph = os.path.join(deck, "public", "figures", f"mindmap_{values['PREFIX']}.png")
        if not os.path.exists(ph):
            write_placeholder_png(ph, "Mind map: generated in the enrichment step")

    # 3. skeleton guides -> deck resources (decks are self-contained artifacts)
    for guide_key, fname in (("author_rules", "author-guide.md"), ("diagram_style", "diagram-style.md")):
        src = os.path.join(skel_dir, skel["workflow"].get(guide_key, fname))
        shutil.copyfile(src, os.path.join(deck, "resources", fname))

    # 4. provenance + workflow config back into the deck's recipe.json
    wf = dict(skel["workflow"])
    wf.update(recipe.get("workflow") or {})
    recipe["workflow"] = wf
    recipe["house_style"] = "resources/author-guide.md"
    recipe["diagram_style"] = "resources/diagram-style.md"
    recipe["improve_passes"] = recipe.get("improve_passes") or wf.get("polish_passes", [])
    recipe["provenance"] = {
        "theme_pack": pack["name"],
        "pack_version": pack.get("version"),
        "pack_path": pack_dir.replace("\\", "/"),
        "skeleton": skel_name,
        "skeleton_version": skel.get("version"),
        "slide_optouts": sorted(optouts),
        "scaffolded": datetime.date.today().isoformat(),
        "answers": {k: v for k, v in recipe.items()
                    if isinstance(v, SCALAR) and k not in ("deck_location",)},
    }
    io.open(os.path.join(deck, "resources", "recipe.json"), "w",
            encoding="utf-8", newline="\n").write(json.dumps(recipe, indent=2, ensure_ascii=False) + "\n")

    print(f"scaffolded: {deck}")
    print(f"  pack={pack['name']} skeleton={skel_name} v{skel.get('version')}")
    print(f"  framing slides: {[m for m in manifest if m != MARKER]}")
    if skipped:
        print(f"  opted out: {skipped}")
    print(f"  deck files: {copied}")
    print("next: npm install, then run the build workflow (content sections replace the manifest marker)")


if __name__ == "__main__":
    main()
