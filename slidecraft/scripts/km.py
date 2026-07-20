#!/usr/bin/env python
"""Knowledge-manager scripts (prototype).

Deterministic deck-state operations. Scripts move files and associations;
they never write slide prose — that is always the Composer's job.

Subcommands:
  create-nugget   --file PATH                               -> {"nugget_id": ...}
  persist-nuggets --source SLUG [--image-source ID] --file PATH -> {"nugget_ids": [...]}
  mine-brief      (--source SLUG | --image ID) --out PATH   -> {"ok": true, ...}
  mark-mined      --source SLUG                             -> {"ok": true, ...}
  plan-brief    --out PATH                                  -> {"ok": true, ...}
  write-plan    --file PATH                                 -> {"ok": true, "steps": [...]}
  compose-brief --slide ID --out PATH                       -> {"ok": true, ...}
  write-slide   --slide ID --file PATH                      -> {"ok": true, ...}
  create-slide  --title T --nuggets a,b --after ID|end
                [--parked] [--intended-function F]          -> {"slide_id": ...}
  associate-nuggets --slide ID --nuggets a,b                -> {"slide_id": ...}
  merge-slides  --slides a,b [--title T]                    -> {"slide_id": ...}
  park-slide    --slide ID [--reason R]                     -> {"ok": true, ...}
  unpark-slide  --slide ID                                  -> {"ok": true, ...}
  set-content   --slide ID --body-file PATH                 -> {"ok": true, ...}
  validate                                                  -> {"ok": bool, ...}

set-content also fills empty presenter notes from the slide's nuggets' raw
knowledge, verbatim (D39) — see build_presenter_notes.

Assemble/persist stages of the pure-function pipeline (D40): ``mine-brief``
renders a fully self-contained miner brief (role template + injection values
+ the source text inline — no script instructions, no paths, no IDs);
``persist-nuggets`` is the fan-out persist wrapper for a miner's batch output
(validates the WHOLE batch before writing anything, enriches ``kind``/
``source`` — the miner must not invent them); ``mark-mined`` is the
orchestrator's bookkeeping step after a successful mine (source stamped,
input moved to processed/). Persist rejections exit 1 with the error on
stderr — the invoke shim's retryable-rejection convention (D44).

Deck root is resolved from --deck or by walking up from CWD for deck-context.json.
All mutations append one line to logs/actions.jsonl.
"""
import argparse, json, re, sys, time
from pathlib import Path

# ---------- deck root + stamp ----------

def find_deck_root(explicit: str | None) -> Path:
    start = Path(explicit).resolve() if explicit else Path.cwd()
    for p in [start, *start.parents]:
        if (p / "deck-context.json").exists():
            return p
    sys.exit("ERROR: no deck-context.json found from " + str(start))

def stamp(root: Path) -> str:
    t = time.time()
    base = time.strftime("%Y%m%d-%H%M%S-", time.localtime(t)) + f"{int((t%1)*1000):03d}"
    s, n = base, 1
    while (root / "nuggets" / f"{s}.json").exists() or list((root / "slides").glob(f"*--{s}.*")):
        s = f"{base}-{n}"; n += 1
    return s

def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    # Strip AFTER truncating: a cut at 60 chars can land on a hyphen, and a
    # trailing hyphen would join the ``--`` stamp separator into ``---``. Slidev
    # silently drops a ``src:`` import whose path contains ``---``, so the slide
    # would vanish from the deck. Keep slugs hyphen-clean at both ends.
    return (s or "slide")[:60].strip("-") or "slide"

def log(root: Path, agent: str, action: str, **payload):
    (root / "logs").mkdir(exist_ok=True)
    with (root / "logs" / "actions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "agent": agent, "action": action, **payload}) + "\n")

# ---------- state helpers ----------

def ctx(root: Path) -> dict:
    return json.loads((root / "deck-context.json").read_text(encoding="utf-8"))

def assoc(root: Path) -> dict:
    p = root / "associations.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def write_assoc(root: Path, a: dict):
    (root / "associations.json").write_text(json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")

def slide_files(root: Path) -> list[Path]:
    return sorted((root / "slides").glob("*.md"))

def order(root: Path) -> list[str]:
    """ACTIVE slide IDs in slides.md order (src includes outside comments —
    the parked block is an HTML comment, D34)."""
    md = (root / "slides.md")
    if not md.exists():
        return []
    text = re.sub(r"<!--.*?-->", "", md.read_text(encoding="utf-8"), flags=re.S)
    return re.findall(r"src:\s*\./slides/(.+?)\.md", text)

def parked_ids(root: Path) -> list[str]:
    """IDs of parked slides (state ``parked`` in the slide state file — the
    single source of truth; the slides.md parked block mirrors it)."""
    out = []
    for p in sorted((root / "slides").glob("*.json")):
        try:
            stj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if stj.get("state") == "parked":
            out.append(p.stem)
    return out

def yaml_str(value) -> str:
    """A YAML-safe scalar: a JSON string is valid YAML, so titles containing
    colons ("Sprint 4: Production Engineering") cannot break the parse."""
    return json.dumps(str(value), ensure_ascii=False)

# Headmatter keys write_order owns and regenerates; every other key a user
# added by hand (fonts:, addons:, colorSchema:, …) is preserved verbatim —
# the 2026-07-18 "theme: default" clobber generalized to all keys.
MANAGED_HEAD_KEYS = {"theme", "title", "src"}

def preserved_headmatter_lines(root: Path) -> list[str]:
    md = root / "slides.md"
    if not md.exists():
        return []
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n",
                 md.read_text(encoding="utf-8-sig"), re.S)
    if not m:
        return []
    kept = []
    for line in m.group(1).splitlines():
        key = re.match(r"^([A-Za-z0-9_-]+):", line)  # unindented keys only
        if key and key.group(1) in MANAGED_HEAD_KEYS:
            continue
        kept.append(line)
    return kept

def write_order(root: Path, ids: list[str], parked: list[str] | None = None,
                c: dict | None = None):
    c = ctx(root) if c is None else c
    theme_ref = (c.get("theme") or {}).get("source") or "default"
    title = yaml_str(c["deck"].get("topic", "Deck"))
    # Import the first slide via the headmatter's own ``src`` rather than as a
    # separate ``---`` block. A standalone headmatter block followed by the first
    # ``src:`` import leaves the deck opening on an empty slide (the headmatter
    # renders as a blank slide 1); folding the first import into the headmatter
    # makes slide 1 the real cover.
    head_lines = [f"theme: {theme_ref}", f"title: {title}"]
    head_lines += preserved_headmatter_lines(root)
    if ids:
        head_lines.append(f"src: ./slides/{ids[0]}.md")
    head = "---\n" + "\n".join(head_lines) + "\n---\n"
    body = "".join(f"\n---\nsrc: ./slides/{i}.md\n---\n" for i in ids[1:])
    # Parked slides ride in a commented block (D34): their includes are kept
    # (visible, un-parkable) but Slidev never renders them.
    if parked is None:
        parked = parked_ids(root)
    tail = ""
    if parked:
        inner = "".join(f"---\nsrc: ./slides/{i}.md\n---\n" for i in parked)
        tail = f"\n<!-- parked\n{inner}-->\n"
    (root / "slides.md").write_text(head + body + tail, encoding="utf-8")

def skeleton(title: str, nugget_ids: list[str]) -> str:
    return (f"---\nlayout: default\ntitle: {yaml_str(title)}\n---\n\n"
            f"<!-- awaiting composition; nuggets: {','.join(nugget_ids)} -->\n")

def source_slug(name: str) -> str:
    """Slug of a source FILENAME (extension stripped) — matches source_converter.py.

    A nugget names its source as a filename (e.g. ``chapter_4.pdf``); the
    converted record lives at ``sources/<source_slug>.json``.
    """
    stem = Path(name).stem
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return (s or "source")[:60]

def normalize(s: str) -> str:
    """Symmetric normalization for the verbatim guard.

    Applied to BOTH the nugget's raw_text and the source text before the
    substring check. A one-sided version produced false rejections (SPEC §5).
    Strips markdown emphasis, converts unicode quotes/dashes to ascii,
    removes ``<!-- page N -->`` markers, and collapses whitespace.
    """
    # Drop page markers (pymupdf4llm / source-conversion artefacts).
    s = re.sub(r"<!--\s*page\s+\d+\s*-->", " ", s, flags=re.I)
    # Unicode quotes/dashes -> ascii.
    s = (s.replace("‘", "'").replace("’", "'")
           .replace("“", '"').replace("”", '"')
           .replace("–", "-").replace("—", "-")
           .replace("−", "-").replace("…", "..."))
    # Strip markdown emphasis / heading / underscore markers.
    s = re.sub(r"[*#_]+", "", s)
    # Collapse all whitespace.
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ---------- brief assembly (D40: assemble stage) ----------

# Role prompt templates live next to the scripts folder (same layout in the
# repo and in the installed toolkit, D33).
AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def gate_exit(msg: str):
    """A NON-retryable failure under the invoke shim's persist convention
    (D44): exit 1 means "the model can fix this and a re-invoke is worth an
    LLM call"; anything else gates immediately. Orchestrator wiring errors
    (wrong --source slug, missing payload file, wrong slide id) exit here."""
    print(msg, file=sys.stderr)
    sys.exit(2)


# Root-absolute asset references in a slide body: HTML ``src="/…"`` and
# markdown images ``![alt](/…)`` — the two syntaxes a composer can emit.
ASSET_REF_RE = re.compile(
    r'src=["\'](/[^"\']+)["\']|!\[[^\]]*\]\((/[^)\s]+)\)')


def missing_assets(root: Path, body: str) -> list[str]:
    """Referenced ``/…`` assets that do not exist under ``public/``
    (Slidev serves public/ at the site root)."""
    out = []
    for m in ASSET_REF_RE.finditer(body):
        asset = m.group(1) or m.group(2)
        if not (root / "public" / asset.lstrip("/")).exists():
            out.append(asset)
    return out


def notes_comment(inner: str) -> str:
    """Slidev speaker-notes serialization: a trailing HTML comment. A literal
    comment terminator inside the text would close the note early —
    neutralise only that exact sequence."""
    return "<!--\n" + inner.replace("-->", "-- >") + "\n-->\n"


def save_state(root: Path, sid: str, stj: dict):
    (root / "slides" / f"{sid}.json").write_text(
        json.dumps(stj, indent=2, ensure_ascii=False), encoding="utf-8")


def strip_frontmatter(text: str) -> str:
    m = re.match(r"^---\r?\n.*?\r?\n---\r?\n", text, re.S)
    return text[m.end():].lstrip("\n") if m else text


def load_template(name: str) -> str:
    """A role's prompt template, frontmatter stripped."""
    p = AGENTS_DIR / f"{name}.md"
    if not p.is_file():
        sys.exit(f"ERROR: role template not found: {p}")
    return strip_frontmatter(p.read_text(encoding="utf-8-sig"))


def render_template(template: str, values: dict) -> str:
    """``%PLACEHOLDER%`` substitution; fails loudly on leftovers so template
    drift never ships a brief with an unresolved placeholder."""
    out = template
    for key, value in values.items():
        out = out.replace(f"%{key}%", str(value))
    leftover = sorted(set(re.findall(r"%[A-Z][A-Z-]*%", out)))
    if leftover:
        sys.exit(f"ERROR: unresolved placeholder(s) in template: {leftover}")
    return out


def source_record(root: Path, slug: str) -> dict:
    p = root / "sources" / f"{slug}.json"
    if not p.exists():
        sys.exit(f"ERROR: source {slug} not converted "
                 f"(no sources/{slug}.json)")
    return json.loads(p.read_text(encoding="utf-8"))


def source_full_text(src: dict) -> str:
    """All pages joined, each preceded by its ``<!-- page N -->`` marker so
    the miner can fill the nugget ``page`` field."""
    return "\n".join(f"<!-- page {pg.get('page')} -->\n{pg.get('text', '')}"
                     for pg in src.get("pages", []))


def find_image_record(root: Path, image_source_id: str) -> tuple[dict, dict] | None:
    """The (source record, image record) for an extracted image, found by its
    globally-unique ``image_source_id`` (``<slug>-p<page>-img<idx>``). The
    image-miner never sees or produces IDs (D45); the orchestrator holds them
    and looks the record up here. Returns ``None`` when no source carries it."""
    for p in sorted((root / "sources").glob("*.json")):
        try:
            src = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for rec in src.get("images", []):
            if rec.get("image_source_id") == image_source_id:
                return src, rec
    return None


def write_brief(root: Path, out: str, brief: str):
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brief, encoding="utf-8")


def cmd_mine_brief(root: Path, a):
    """Render the self-contained miner brief (D40/D42).

    Text mode (``--source SLUG``): knowledge-miner craft + injection values +
    the full source text inline. Image mode (``--image IMAGE-SOURCE-ID``):
    image-miner craft + injection only — the figure itself is passed to the
    executor by the invoke shim (``--image``, a base64 data-URL, D45), never
    inlined here; the brief stays conceptual and carries no id or path. Either
    way the miner needs no file access, no scripts, no IDs (D40)."""
    image_id = getattr(a, "image", None)
    if bool(a.source) == bool(image_id):
        gate_exit("ERROR: mine-brief needs exactly one of --source (text) or "
                  "--image (one extracted image)")
    c = ctx(root)
    if image_id:
        found = find_image_record(root, image_id)
        if not found:
            gate_exit(f"ERROR: no extracted image {image_id!r} in any source "
                      "(wrong image-source id, or convert did not run)")
        _src, rec = found
        inj = c.get("injection", {}).get("image-miner", {})
        values = {
            "FOCUS-TOPIC": inj.get("FOCUS-TOPIC", c["deck"].get("topic", "")),
            "LANGUAGE": inj.get("LANGUAGE", c["deck"].get("language", "")),
        }
        brief = render_template(load_template("image-miner"), values)
        # The local file the shim reads and encodes; served by Slidev as the
        # root-absolute URL rec["path"] (/extracted/<file>.png -> public/…).
        asset = str((root / "public" / rec["path"].lstrip("/")).resolve())
        write_brief(root, a.out, brief)
        log(root, "km", "mine-brief", image_source=image_id, chars=len(brief))
        print(json.dumps({"ok": True, "brief": a.out,
                          "image_source": image_id, "asset": asset,
                          "chars": len(brief)}))
        return
    src = source_record(root, a.source)
    inj = c.get("injection", {}).get("knowledge-miner", {})
    values = {
        "FOCUS-TOPIC": inj.get("FOCUS-TOPIC", c["deck"].get("topic", "")),
        "LANGUAGE": inj.get("LANGUAGE", c["deck"].get("language", "")),
    }
    brief = render_template(load_template("knowledge-miner"), values)
    brief += ("\n\n---\n\n## Source text\n\n"
              "The full text of the source follows. The `<!-- page N -->` "
              "markers give the page numbers for the `page` field.\n\n"
              + source_full_text(src) + "\n")
    write_brief(root, a.out, brief)
    log(root, "km", "mine-brief", source=a.source, chars=len(brief))
    print(json.dumps({"ok": True, "brief": a.out, "source": a.source,
                      "chars": len(brief)}))


def cmd_mark_mined(root: Path, a):
    """Bookkeeping after a successful mine step: stamp the source record and
    move its input file to ``input/processed/``. The orchestrator calls this
    only once the source's nuggets are persisted — a mid-source failure
    leaves the source unmarked. Idempotent."""
    src_path = root / "sources" / f"{a.source}.json"
    src = source_record(root, a.source)
    already = bool(src.get("mined_at"))
    if not already:
        src["mined_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        src_path.write_text(json.dumps(src, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    moved = False
    orig = src.get("original_file")
    if orig:
        inp = root / "input" / orig
        if inp.exists():
            dest_dir = root / "input" / "processed"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / orig
            if dest.exists():
                dest.unlink()
            inp.replace(dest)
            moved = True
    log(root, "km", "mark-mined", source=a.source, input_moved=moved,
        already_mined=already)
    print(json.dumps({"ok": True, "source": a.source,
                      "mined_at": src["mined_at"], "input_moved": moved}))


# ---------- plan brief + plan persist (D40/D41/D42, ticket 15) ----------

def load_state(root: Path, sid: str) -> dict:
    p = root / "slides" / f"{sid}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def storytelling_craft_section() -> str:
    """Inline a storytelling skill's craft into the brief when the toolkit
    ships one (SPEC §2; the skill itself is a later ticket — absent is fine)."""
    if not SKILLS_DIR.is_dir():
        return ""
    hits = sorted(SKILLS_DIR.glob("*storytelling*/SKILL.md"))
    if not hits:
        return ""
    bodies = [strip_frontmatter(h.read_text(encoding="utf-8-sig")).strip()
              for h in hits]
    return ("\n\n---\n\n## Storytelling craft (deck-type guidance)\n\n"
            + "\n\n".join(bodies) + "\n")


def nugget_digests(root: Path) -> str:
    """Every nugget's DIGEST fields (D42): id, kind, title, information —
    plus figure_type/description for images. Never raw_text, visible_text,
    asset paths, or context_text."""
    A = assoc(root)
    placed: dict[str, str] = {}
    for sid, nugs in A.items():
        for nid in nugs:
            placed.setdefault(nid, sid)
    lines = []
    for p in sorted((root / "nuggets").glob("*.json")):
        n = load_nugget(root, p.stem) or {}
        nid = n.get("nugget_id", p.stem)
        kind = n.get("kind", "text")
        tag = kind + (f": {n['figure_type']}"
                      if kind == "image" and n.get("figure_type") else "")
        lines.append(f'- id: {nid} [{tag}] — "{n.get("title", "")}"')
        lines.append(f"  placed: {'on ' + placed[nid] if nid in placed else 'no'}")
        if kind == "image" and n.get("description"):
            lines.append(f"  figure: {n['description']}")
        lines.append("  digest:")
        for ln in str(n.get("information", "")).splitlines():
            lines.append(f"    {ln}")
    return "\n".join(lines) if lines else "(no nuggets mined yet)"


def deck_state_section(root: Path) -> str:
    """The current deck for the planner: active order, parked block, budget —
    and whether this is a fresh draft (full plan) or a re-run (delta plan)."""
    ids = order(root)
    parked = parked_ids(root)
    A = assoc(root)
    budget = int(ctx(root)["deck"]["max_slides"])
    lines = [f"Slide budget: {len(ids)} of {budget} active slots used."]
    if not ids and not parked:
        lines.append("")
        lines.append("The deck has no slides yet — this is a fresh draft: "
                     "return a FULL plan covering the structural slides the "
                     "deck needs and every unplaced nugget.")
        return "\n".join(lines)
    lines.append("")
    lines.append("The deck already has slides — this is a re-run: return a "
                 "DELTA plan that integrates the new material into the "
                 "existing structure; do not recreate existing slides.")
    if ids:
        lines.append("")
        lines.append("Active slides, in deck order:")
        for i, sid in enumerate(ids, 1):
            stj = load_state(root, sid)
            nugs = A.get(sid, [])
            tag = "structural" if not nugs else "nuggets: " + ", ".join(nugs)
            lines.append(f'{i}. {sid} — "{stj.get("title", sid)}" '
                         f'[{stj.get("state", "draft")}] ({tag})')
    if parked:
        lines.append("")
        lines.append("Parked slides (content kept, not shown; un-parkable "
                     "when a slot frees up):")
        for sid in parked:
            stj = load_state(root, sid)
            reason = stj.get("parked_reason", "")
            lines.append(f'- {sid} — "{stj.get("title", sid)}" [parked]'
                         + (f" — reason: {reason}" if reason else ""))
    return "\n".join(lines)


def cmd_plan_brief(root: Path, a):
    """Render the self-contained storyteller brief (D40/D42): planner role
    template + deck constraints + inlined storytelling craft + all nugget
    digests + the current deck state (incl. the parked block)."""
    c = ctx(root)
    inj = c.get("injection", {}).get("storyteller", {})
    deckb = c["deck"]
    values = {
        "TOPIC": inj.get("TOPIC", deckb.get("topic", "")),
        "DECK-TYPE": inj.get("DECK-TYPE", deckb.get("type", "")),
        "AUDIENCE": inj.get("AUDIENCE", deckb.get("audience", "")),
        "SETTING": inj.get("SETTING", deckb.get("setting", "")),
        "LANGUAGE": inj.get("LANGUAGE", deckb.get("language", "")),
        "MAX-SLIDES": inj.get("MAX-SLIDES", deckb.get("max_slides", "")),
        "MAX-DURATION-MINUTES": inj.get(
            "MAX-DURATION-MINUTES", deckb.get("max_duration_minutes") or ""),
    }
    brief = render_template(load_template("storyteller"), values)
    brief += storytelling_craft_section()
    brief += ("\n\n---\n\n## Knowledge nuggets (digests)\n\n"
              + nugget_digests(root))
    brief += ("\n\n---\n\n## Current deck state\n\n"
              + deck_state_section(root) + "\n")
    write_brief(root, a.out, brief)
    log(root, "km", "plan-brief", chars=len(brief))
    print(json.dumps({"ok": True, "brief": a.out, "chars": len(brief)}))


PLAN_ACTIONS = ("create", "associate", "merge", "park", "unpark")


def cmd_write_plan(root: Path, a):
    """Validate the storyteller's returned plan deterministically (D41) —
    nugget ids exist, decision types valid, structural slides well-formed,
    budget arithmetic sound (simulated step by step over ACTIVE slides),
    hints in the enum, locked slides untouched, no nugget left unplaced
    (D34) — record it, and hand back an executable step list.

    Rejection = exit 1 with the reasons (drives the shim retry; cap-2
    exhaustion is the storyteller's abort terminal, D44)."""
    p = Path(a.file)
    if not p.exists():
        gate_exit(f"ERROR: plan file {a.file} does not exist")
    try:
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: plan output is not valid JSON: {exc}")
    if not isinstance(obj, dict) or not isinstance(obj.get("plan"), list):
        sys.exit('ERROR: plan output must be an object of the form '
                 '{"plan": [...], "notes": ""}')

    known = {q.stem for q in (root / "nuggets").glob("*.json")}
    kinds = {nid: (load_nugget(root, nid) or {}).get("kind", "text")
             for nid in known}
    A = assoc(root)
    files = {q.stem for q in slide_files(root)}
    states = {sid: load_state(root, sid) for sid in files}
    locked = {sid for sid, s in states.items() if s.get("state") == "locked"}
    structural = {sid for sid in files if not A.get(sid)}
    parked_set = {sid for sid, s in states.items()
                  if s.get("state") == "parked"}
    budget = int(ctx(root)["deck"]["max_slides"])
    n_active = len(files - parked_set)

    errors: list[str] = []
    steps: list[dict] = []
    referenced: set[str] = set()
    retired: set[str] = set()          # merged away earlier in this plan
    planned_extra: dict[str, list] = {}  # associates planned per slide

    def image_count(nugs) -> int:
        return sum(1 for n in nugs if kinds.get(n) == "image")

    def check_slide(where: str, sid) -> bool:
        if not isinstance(sid, str) or sid not in files:
            if sid in retired:
                errors.append(f"{where}: slide {sid} was merged away by an "
                              "earlier step of this plan")
            else:
                errors.append(f"{where}: slide {sid!r} does not exist")
            return False
        if sid in locked:
            errors.append(f"{where}: slide {sid} is locked — locked slides "
                          "are skip-and-propose (use notes)")
            return False
        if sid in parked_set:
            errors.append(f"{where}: slide {sid} is parked — unpark it first")
            return False
        return True

    for i, step in enumerate(obj["plan"], 1):
        where = f"step #{i}"
        if not isinstance(step, dict):
            errors.append(f"{where}: not an object")
            continue
        action = step.get("action")
        if action not in PLAN_ACTIONS:
            errors.append(f"{where}: unknown action {action!r} "
                          f"(valid: {list(PLAN_ACTIONS)})")
            continue
        where = f"{where} ({action})"

        if action == "create":
            title = step.get("title")
            if not title or not isinstance(title, str):
                errors.append(f"{where}: missing title")
                continue
            structural_flag = bool(step.get("structural"))
            nugs = step.get("nuggets") or []
            if structural_flag and nugs:
                errors.append(f"{where} '{title}': a structural slide "
                              "carries no nuggets")
            if not structural_flag:
                if not nugs:
                    errors.append(f"{where} '{title}': a content slide needs "
                                  'nuggets (or mark it "structural": true)')
                missing = [n for n in nugs if n not in known]
                if missing:
                    errors.append(f"{where} '{title}': unknown nugget id(s): "
                                  + ", ".join(str(m) for m in missing))
                if image_count(nugs) > 1:
                    errors.append(f"{where} '{title}': at most ONE image "
                                  "nugget per slide — split the figures "
                                  "across slides")
                referenced.update(nugs)
            hint = step.get("intended_function")
            if hint is not None and hint not in CONCEPT_TYPES:
                errors.append(f"{where}: intended_function {hint!r} not in "
                              f"{list(CONCEPT_TYPES)}")
            after = step.get("after")
            if after not in (None, "end") and after not in files:
                errors.append(f"{where}: after-target {after!r} does not exist")
            is_parked = bool(step.get("parked"))
            if not is_parked:
                if n_active >= budget:
                    errors.append(f"{where} '{title}': budget overflow — "
                                  f"{n_active} active slides of max {budget}; "
                                  "merge or park BEFORE this create")
                else:
                    n_active += 1
            steps.append({"op": "create-slide", "title": title,
                          "nuggets": list(nugs), "structural": structural_flag,
                          "parked": is_parked, "after": after or "end",
                          "intended_function": hint})

        elif action == "associate":
            sid = step.get("slide")
            nugs = step.get("nuggets") or []
            if not nugs:
                errors.append(f"{where}: needs at least one nugget id")
            if check_slide(where, sid):
                if sid in structural:
                    errors.append(f"{where}: slide {sid} is structural — "
                                  "structural slides hold no nuggets")
                on_slide = A.get(sid, []) + planned_extra.get(sid, [])
                if image_count(set(on_slide) | set(nugs)) > 1:
                    errors.append(f"{where}: slide {sid} would carry more "
                                  "than one image nugget — at most ONE "
                                  "figure per slide")
                planned_extra.setdefault(sid, []).extend(nugs)
            missing = [n for n in nugs if n not in known]
            if missing:
                errors.append(f"{where}: unknown nugget id(s): "
                              + ", ".join(str(m) for m in missing))
            referenced.update(nugs)
            steps.append({"op": "associate-nuggets", "slide": sid,
                          "nuggets": list(nugs)})

        elif action == "merge":
            sids = step.get("slides") or []
            if not isinstance(sids, list) or len(sids) < 2:
                errors.append(f"{where}: needs >=2 slide ids")
                continue
            if len(set(sids)) != len(sids):
                errors.append(f"{where}: duplicate slide ids in merge — "
                              "merging a slide with itself frees no slot")
                continue
            ok = True
            for sid in sids:
                if not check_slide(where, sid):
                    ok = False
                elif sid in structural:
                    errors.append(f"{where}: slide {sid} is structural — "
                                  "structural slides are never merge "
                                  "candidates")
                    ok = False
            if ok:
                union = []
                for sid in sids:
                    union.extend(A.get(sid, []))
                    union.extend(planned_extra.get(sid, []))
                if image_count(set(union)) > 1:
                    errors.append(f"{where}: the merged slide would carry "
                                  "more than one image nugget — at most ONE "
                                  "figure per slide")
                # The merge retires its inputs: later steps must not
                # reference them (cmd_merge deletes their files).
                n_active -= len(sids) - 1
                retired.update(sids)
                files -= set(sids)
                structural -= set(sids)
                for sid in sids:
                    planned_extra.pop(sid, None)
            steps.append({"op": "merge-slides", "slides": list(sids),
                          "title": step.get("title") or ""})

        elif action == "park":
            sid = step.get("slide")
            if check_slide(where, sid):
                n_active -= 1
                parked_set.add(sid)
            steps.append({"op": "park-slide", "slide": sid,
                          "reason": step.get("reason") or ""})

        elif action == "unpark":
            sid = step.get("slide")
            if not isinstance(sid, str) or sid not in files:
                errors.append(f"{where}: slide {sid!r} does not exist")
            elif sid not in parked_set:
                errors.append(f"{where}: slide {sid} is not parked")
            elif sid in locked:
                errors.append(f"{where}: slide {sid} is locked")
            elif n_active >= budget:
                errors.append(f"{where}: budget overflow — no free active "
                              f"slot for {sid} (max {budget})")
            else:
                n_active += 1
                parked_set.discard(sid)
            steps.append({"op": "unpark-slide", "slide": sid})

    # D34: every nugget always gets a slide — none may be left unplaced.
    already_placed = {nid for nugs in A.values() for nid in nugs}
    unplaced = sorted(known - already_placed - referenced)
    if unplaced:
        errors.append("nugget(s) left unplaced: " + ", ".join(unplaced)
                      + " — every nugget must end on a slide (create, "
                        'associate, or a "parked": true create)')

    if errors:
        sys.exit("ERROR: plan rejected: " + "; ".join(errors))

    record = {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "plan": obj["plan"], "notes": obj.get("notes", ""),
              "steps": steps}
    (root / "plan.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    log(root, "km", "write-plan", steps=len(steps))
    print(json.dumps({"ok": True, "plan_file": "plan.json", "steps": steps,
                      "active_after": n_active}))


# ---------- compose brief + slide persist (D42/D43, ticket 16) ----------

def offered_layouts(c: dict) -> dict[str, dict]:
    """Theme-capability layouts by their OFFERED name: the semantic alias
    when the theme ships one, else the physical layout name. The composer
    only ever sees offered names + role names; ``write-slide`` maps back to
    physical (ADR-0001)."""
    caps = c["theme"]["capabilities"]
    offered: dict[str, dict] = {}
    for entry in caps.get("layouts", []):
        name = entry.get("alias") or entry["name"]
        offered.setdefault(name, entry)
    return offered


def takes_image_prop(entry: dict) -> bool:
    """A prop-based image layout (Slidev builtins image / image-left /
    image-right): no roles map, figure travels as the ``image:`` frontmatter
    prop rather than a slot."""
    return not entry.get("roles") and "image" in (entry.get("props") or [])


def layouts_section(c: dict) -> str:
    """The layout capabilities for a composer brief: offered name, intent,
    CONTENT role names, defaults, and figure capability — never a physical
    slot name. ``image`` is not a content role (the figure travels via the
    ``image`` output field), so it is advertised separately."""
    lines = []
    for name, entry in offered_layouts(c).items():
        intent = entry.get("intent", "")
        lines.append(f"- **{name}**" + (f" — {intent}" if intent else ""))
        roles = entry.get("roles") or {}
        content_roles = [r for r in roles if r != "image"]
        if content_roles:
            lines.append("  roles: " + ", ".join(content_roles))
        else:
            lines.append("  roles: title, body (single content area)")
        if "image" in roles or takes_image_prop(entry):
            lines.append('  figure: takes one figure via the "image" '
                         "output field")
        defaults = entry.get("defaults") or {}
        if defaults:
            lines.append("  defaults: " + "; ".join(
                f'{k} = "{v}"' for k, v in defaults.items()))
    return "\n".join(lines)


def style_contract_section(c: dict) -> str:
    """Inline the theme's style guide CONTENT (a pure function cannot read
    the file the old composer was pointed at)."""
    sg = (c.get("theme") or {}).get("styleguide") or ""
    if not sg:
        return ""
    p = Path(sg)
    if not p.is_file():
        return ""
    body = strip_frontmatter(
        p.read_text(encoding="utf-8-sig", errors="replace")).strip()
    return "\n\n---\n\n## Theme style contract\n\n" + body + "\n"


def slide_type(nuggets: list[dict]) -> str:
    """The D42 slide type from the associated nuggets' kinds."""
    if not nuggets:
        return "structural"
    kinds = {n.get("kind", "text") for n in nuggets}
    if kinds == {"text"}:
        return "text-only"
    if kinds == {"image"}:
        return "image-only"
    return "image-text"


def cmd_compose_brief(root: Path, a):
    """Render the self-contained composer brief for ONE slide by slide type
    (D40/D42): unified role+craft template + theme style contract + the
    slide's routed nugget fields + layout roles/intents/defaults + deck
    metadata. The two briefs read opposite fields of the same nugget: the
    composer gets verbatim ``raw_text`` (never the ``information`` digest,
    never ``visible_text``)."""
    sid = a.slide
    stj = load_state(root, sid)
    if not stj:
        sys.exit(f"ERROR: slide {sid} does not exist")
    A = assoc(root)
    if sid not in A:
        sys.exit(f"ERROR: slide {sid} has no association entry")
    nugs = []
    for nid in A[sid]:
        n = load_nugget(root, nid)
        if not n:
            sys.exit(f"ERROR: nugget {nid} missing")
        nugs.append(n)
    stype = slide_type(nugs)

    c = ctx(root)
    inj = c.get("injection", {}).get("slide-composer", {})
    deckb = c["deck"]
    values = {
        "AUDIENCE": inj.get("AUDIENCE", deckb.get("audience", "")),
        "DECK-TYPE": inj.get("DECK-TYPE", deckb.get("type", "")),
        "LANGUAGE": inj.get("LANGUAGE", deckb.get("language", "")),
    }
    brief = render_template(load_template("slide-composer"), values)
    brief += style_contract_section(c)

    sec = ["\n\n---\n\n## Your slide\n"]
    sec.append(f'- Working title: "{stj.get("title", sid)}"')
    sec.append(f"- Slide type: {stype}")
    hint = stj.get("intended_function")
    if hint:
        sec.append(f"- Intended didactic function (hint): **{hint}** — "
                   "honor it unless the raw material clearly demands "
                   "otherwise.")

    text_nuggets = [n for n in nugs if n.get("kind", "text") == "text"]
    image_nuggets = [n for n in nugs if n.get("kind") == "image"]

    if stype == "structural":
        sec.append("")
        sec.append("This is a **structural** slide (cover, agenda, section "
                   "divider, or closing). Compose it from the deck metadata "
                   "and the layout defaults only — there is no source "
                   "material.")
        sec.append("")
        sec.append("Deck metadata:")
        sec.append(f"- Topic: {deckb.get('topic', '')}")
        for label, key in (("Presenter", "PRESENTER"),
                           ("Institution", "INSTITUTION"),
                           ("Course", "COURSE"), ("Date", "DATE"),
                           ("Footer", "FOOTER")):
            v = inj.get(key, deckb.get(key.lower(), ""))
            if v:
                sec.append(f"- {label}: {v}")

    if stype in ("text-only", "image-text"):
        sec.append("")
        sec.append("## Raw source material")
        sec.append("")
        sec.append("Compose the slide from these verbatim excerpts ONLY."
                   + (" The figure below rides alongside — place it, never "
                      "paraphrase it into body text." if stype == "image-text"
                      else ""))
        for i, n in enumerate(text_nuggets, 1):
            sec.append("")
            sec.append(f"### Excerpt {i} — {n.get('source', '?')}, "
                       f"p. {n.get('page', '?')}")
            sec.append("")
            sec.append(str(n.get("raw_text", "")).strip())

    if stype == "image-text":
        n = image_nuggets[0]
        sec.append("")
        sec.append("## Figure to place")
        sec.append("")
        sec.append(f"- asset: {n.get('asset', '')}")
        sec.append(f"- what it shows: {n.get('description', '')}")
        sec.append(f"- citation: {n.get('source', '?')}, "
                   f"p. {n.get('page', '?')}")
        sec.append("")
        sec.append('Place this figure via the "image" output field on an '
                   "image-capable layout. Compose the body from the text "
                   "excerpts above only.")

    if stype == "image-only":
        n = image_nuggets[0]
        sec.append("")
        sec.append("## Figure")
        sec.append("")
        sec.append(f"- asset: {n.get('asset', '')}")
        sec.append(f"- what it shows: {n.get('description', '')}")
        ctxt = str(n.get("context_text", "")).strip()
        if ctxt:
            sec.append(f"- nearby text in the source (headline material): "
                       f"{ctxt}")
        sec.append(f"- citation: {n.get('source', '?')}, "
                   f"p. {n.get('page', '?')}")
        sec.append("")
        sec.append("This figure speaks for itself: compose a HEADLINE ONLY "
                   "(from what the figure shows and the nearby text), place "
                   'the figure via the "image" output field, and return '
                   "**no body text**.")

    sec.append("")
    sec.append("## Layouts you may use")
    sec.append("")
    sec.append(layouts_section(c))
    brief += "\n".join(sec) + "\n"

    write_brief(root, a.out, brief)
    log(root, "km", "compose-brief", slide=sid, type=stype, chars=len(brief))
    print(json.dumps({"ok": True, "brief": a.out, "slide": sid,
                      "type": stype, "chars": len(brief)}))


def build_slide_markdown(root: Path, sid: str, obj, c: dict) -> tuple[str, dict]:
    """The composer's semantic role-keyed JSON (D43) → physical Slidev
    markdown. Raises :class:`Rejection` on every model-fixable problem."""
    if not isinstance(obj, dict):
        raise Rejection("composer output must be a single JSON object")
    offered = offered_layouts(c)
    layout = obj.get("layout")
    if not isinstance(layout, str) or layout not in offered:
        raise Rejection(f"layout {layout!r} is not one of the offered "
                        f"layouts: {sorted(offered)}")
    entry = offered[layout]
    physical_layout = entry["name"]
    concept = obj.get("concept_type")
    if concept not in CONCEPT_TYPES:
        raise Rejection(f"concept_type {concept!r} not in "
                        f"{list(CONCEPT_TYPES)}")
    content = obj.get("content") or {}
    if (not isinstance(content, dict)
            or not all(isinstance(v, str) for v in content.values())):
        raise Rejection('"content" must map role names to markdown strings')
    roles = entry.get("roles") or {}
    allowed = set(roles) - {"image"} if roles else {"title", "body"}
    unknown = sorted(set(content) - allowed)
    if unknown:
        raise Rejection(f"unknown content role(s) {unknown} for layout "
                        f"{layout!r} — allowed roles: {sorted(allowed)}"
                        + (' (a figure goes in the top-level "image" field,'
                           " not in content)" if "image" in unknown else ""))
    image = obj.get("image") or None
    if image is not None:
        if not isinstance(image, dict) or not image.get("asset"):
            raise Rejection('"image" must be an object with an "asset" path')
        if roles and "image" not in roles:
            raise Rejection(f"layout {layout!r} has no image slot — choose "
                            "an image-capable layout or return no image")
        asset = str(image["asset"])
        if not (root / "public" / asset.lstrip("/")).exists():
            raise Rejection(f"referenced asset '{asset}' does not exist "
                            f"(expected under public/: public{asset})")

    defaults = entry.get("defaults") or {}
    filled = {}
    for role in allowed:
        v = (content.get(role) or "").strip() or str(defaults.get(role, "")).strip()
        if v:
            filled[role] = v

    title = filled.get("title") or load_state(root, sid).get("title", sid)
    fm_lines = [f"layout: {physical_layout}", f"title: {yaml_str(title)}"]
    img_tag = ""
    if image is not None:
        if takes_image_prop(entry):
            # Slidev's builtin image layouts take the figure as a prop.
            fm_lines.append(f"image: {yaml_str(image['asset'])}")
        else:
            alt = str(image.get("alt", "")).replace('"', "'")
            img_tag = f'<img src="{image["asset"]}" alt="{alt}">'
    parts = ["---\n" + "\n".join(fm_lines) + "\n---\n"]
    if roles:
        for role, slot in roles.items():
            if role == "image":
                if img_tag:
                    # No blank line INSIDE an image slot (breaks MDC parsing).
                    parts.append(f"\n::{slot}::\n{img_tag}\n")
                continue
            if role in filled:
                parts.append(f"\n::{slot}::\n{filled[role]}\n")
    else:
        if "title" in filled:
            parts.append(f"\n# {filled['title']}\n")
        if "body" in filled:
            parts.append(f"\n{filled['body']}\n")
        if img_tag:
            parts.append(f"\n{img_tag}\n")

    figure_needed = str(obj.get("figure_needed") or "").strip()
    if figure_needed:
        parts.append(f"\n<!-- FIGURE NEEDED: {figure_needed} -->\n")
    body = "".join(parts)

    # Same asset rule as set-content, via the shared checker (covers HTML
    # src= AND markdown ![](…) images anywhere in the composed body).
    for asset in missing_assets(root, body):
        raise Rejection(f"referenced asset '{asset}' does not exist "
                        f"(expected under public/: public{asset})")

    notes = str(obj.get("notes") or "").strip()
    notes_added = False
    if notes:
        body = body.rstrip() + "\n\n" + notes_comment(notes)
    else:
        auto = build_presenter_notes(root, sid)      # D39 verbatim fill
        if auto:
            body = body.rstrip() + "\n\n" + auto
            notes_added = True
    return body, {"layout": physical_layout, "concept_type": concept,
                  "notes_added": notes_added}


def cmd_write_slide(root: Path, a):
    """Persist a composer's semantic output (D43): roles → physical slots
    via the theme's roles map, defaults applied, layout + assets validated,
    empty notes filled verbatim (D39), ``concept_type`` stamped into the
    slide state file, ``figure_needed`` rendered as the FIGURE NEEDED
    marker. Rejection = exit 1 (shim retry; cap-2 = park terminal, D44).
    Once the D36 hand-edit guard hook exists, this subcommand is on its
    hooked list (SPEC §5)."""
    sid = a.slide
    stp = root / "slides" / f"{sid}.json"
    sp = root / "slides" / f"{sid}.md"
    if not stp.exists() or not sp.exists():
        # Not model-fixable — a gate, not a retryable rejection.
        gate_exit(f"ERROR: slide {sid} does not exist")
    stj = load_state(root, sid)
    if stj.get("state") == "locked":
        gate_exit(f"ERROR: slide {sid} is locked — user-owned content is "
                  "never overwritten by the composer pipeline")
    if stj.get("state") == "parked":
        gate_exit(f"ERROR: slide {sid} is parked — unpark it before "
                  "composing")
    p = Path(a.file)
    if not p.exists():
        gate_exit(f"ERROR: composer output file {a.file} does not exist")
    try:
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: composer output is not valid JSON: {exc}")
    try:
        body, meta = build_slide_markdown(root, sid, obj, ctx(root))
    except Rejection as exc:
        sys.exit(f"ERROR: {exc}")
    sp.write_text(body, encoding="utf-8")
    stj["state"] = "composed"
    stj["concept_type"] = meta["concept_type"]
    save_state(root, sid, stj)
    log(root, "composer", "write-slide", slide=sid, layout=meta["layout"],
        concept_type=meta["concept_type"], notes_added=meta["notes_added"])
    print(json.dumps({"ok": True, "slide": sid, **meta}))


# ---------- nugget validation + persist core ----------

class Rejection(Exception):
    """A retryable validation rejection (exit 1 at the CLI — the invoke
    shim's convention for 'the model can fix this', D44)."""


def check_nugget(root: Path, n: dict, norm_cache: dict | None = None):
    """Validate one enriched nugget dict; raise :class:`Rejection` on any
    schema or verbatim-guard failure. Writes nothing.

    ``norm_cache`` (slug → normalized source text) lets a batch caller pay
    the source read + full-text normalization once instead of per nugget.
    """
    kind = n.get("kind")
    if kind not in ("text", "image"):
        raise Rejection('nugget "kind" must be "text" or "image"')
    common = ["source", "page", "title", "information"]
    req = common + (["raw_text"] if kind == "text" else ["visible_text"])
    missing = [f for f in req if f not in n or n[f] in (None, "")]
    if missing:
        raise Rejection(
            f"nugget missing required field(s): {', '.join(missing)}")
    if kind == "image" and not isinstance(n["visible_text"], list):
        raise Rejection('image nugget "visible_text" must be a list')

    # ----- verbatim guard (text nuggets only) -----
    if kind == "text":
        slug = source_slug(n["source"])
        norm_source = (norm_cache or {}).get(slug)
        if norm_source is None:
            src_path = root / "sources" / f"{slug}.json"
            if not src_path.exists():
                raise Rejection(f"source {n['source']} not converted "
                                f"(expected sources/{slug}.json)")
            src = json.loads(src_path.read_text(encoding="utf-8"))
            norm_source = normalize("\n".join(
                pg.get("text", "") for pg in src.get("pages", [])))
            if norm_cache is not None:
                norm_cache[slug] = norm_source
        if normalize(n["raw_text"]) not in norm_source:
            raise Rejection("verbatim guard failed — raw_text is not a "
                            f"substring of source {n['source']} (normalized). "
                            "Fix the excerpt to match the source exactly.")


def persist_nugget(root: Path, n: dict) -> str:
    """Stamp + write one validated nugget; returns its id."""
    st = stamp(root)
    n["nugget_id"] = st
    n["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    n["created_by"] = "knowledge-miner"
    (root / "nuggets").mkdir(exist_ok=True)
    (root / "nuggets" / f"{st}.json").write_text(
        json.dumps(n, indent=2, ensure_ascii=False), encoding="utf-8")
    log(root, "knowledge-miner", "create-nugget", nugget=st,
        kind=n["kind"], source=n["source"], page=n["page"])
    return st


# ---------- commands ----------

def cmd_create_nugget(root: Path, a):
    p = Path(a.file)
    if not p.exists():
        sys.exit(f"ERROR: nugget file {a.file} does not exist")
    try:
        n = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: nugget file is not valid JSON: {exc}")
    try:
        check_nugget(root, n)
    except Rejection as exc:
        sys.exit(f"ERROR: {exc}")
    st = persist_nugget(root, n)
    print(json.dumps({"nugget_id": st}))


def cmd_persist_nuggets(root: Path, a):
    """Fan-out persist wrapper for a miner's batch output (ticket 13/14).

    A miner returns ``{"nuggets": [...]}`` whose items carry no ``kind``/
    ``source`` — the orchestrator knows those; the miner must not invent them.
    This wrapper enriches every item, validates the WHOLE batch (schema +
    verbatim guard) before writing anything — so a shim retry after a
    rejection can never duplicate already-persisted nuggets — then persists
    each item.

    Text mode (``--source SLUG``): each item is forced ``kind: "text"`` and
    the verbatim guard runs against the source text.
    Image mode (``--source SLUG --image-source ID``, D45): each item is forced
    ``kind: "image"`` and the deterministic figure facts — ``asset`` (public
    ``/extracted/…`` path), ``context_text`` (nearest text block), ``page`` —
    are **denormalized from the source's image record**, never from the model.
    """
    # Wiring errors gate immediately (exit 2): the model cannot fix a wrong
    # --source slug or a missing batch file, so no re-invoke is spent on it.
    if not (root / "sources" / f"{a.source}.json").exists():
        gate_exit(f"ERROR: source {a.source} not converted "
                  f"(no sources/{a.source}.json) — wrong --source slug, or "
                  "the convert step did not run")
    src = source_record(root, a.source)
    image_id = getattr(a, "image_source", None)
    rec = None
    if image_id:
        rec = next((r for r in src.get("images", [])
                    if r.get("image_source_id") == image_id), None)
        if rec is None:
            gate_exit(f"ERROR: source {a.source} has no extracted image "
                      f"{image_id!r} — wrong image-source id, or convert did "
                      "not extract it")
    p = Path(a.file)
    if not p.exists():
        gate_exit(f"ERROR: batch file {a.file} does not exist")
    try:
        batch = json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: miner output is not valid JSON: {exc}")
    if not isinstance(batch, dict) or not isinstance(batch.get("nuggets"), list):
        sys.exit('ERROR: miner output must be an object of the form '
                 '{"nuggets": [...]}')

    enriched = []
    errors = []
    norm_cache: dict = {}   # one source read + normalize for the whole batch
    for i, item in enumerate(batch["nuggets"], start=1):
        if not isinstance(item, dict):
            errors.append(f"nugget #{i}: not an object")
            continue
        n = dict(item)
        n["source"] = src["original_file"]      # never miner-invented
        if rec is not None:
            # D45: the figure's identity is denormalized, not model-supplied.
            n["kind"] = "image"
            n["page"] = rec.get("page")
            n["asset"] = rec.get("path")
            n["context_text"] = rec.get("context_text", "")
        else:
            n["kind"] = "text"                  # text-miner slice: forced
        try:
            check_nugget(root, n, norm_cache)
        except Rejection as exc:
            errors.append(f"nugget #{i} ({n.get('title', '?')}): {exc}")
        enriched.append(n)
    if errors:
        # Atomic rejection: nothing was written; the whole corrected batch
        # comes back through the shim retry.
        sys.exit("ERROR: " + "; ".join(errors))

    ids = [persist_nugget(root, n) for n in enriched]
    log(root, "km", "persist-nuggets", source=a.source, count=len(ids),
        image_source=image_id)
    print(json.dumps({"nugget_ids": ids, "count": len(ids),
                      "source": a.source}))

# The didactic concept-type enum (D43) — shared by the storyteller's
# intended_function hint and the composer's concept_type declaration.
CONCEPT_TYPES = ("structural", "motivate", "define", "compare", "relationship",
                 "process", "cause-effect", "finding", "categories",
                 "claim-support")


def image_nugget_ids(root: Path, nugget_ids) -> list[str]:
    return [nid for nid in nugget_ids
            if (load_nugget(root, nid) or {}).get("kind") == "image"]


def cmd_create(root: Path, a):
    c = ctx(root)
    budget = int(c["deck"]["max_slides"])
    parked_flag = bool(getattr(a, "parked", False))
    hint = getattr(a, "intended_function", None)
    if hint and hint not in CONCEPT_TYPES:
        sys.exit(f"ERROR: intended_function {hint!r} not in "
                 f"{sorted(CONCEPT_TYPES)}")
    parked = parked_ids(root)
    cur = len({p.stem for p in slide_files(root)} - set(parked))
    if not parked_flag and cur >= budget:
        print(json.dumps({"error": "budget_full", "current": cur, "max": budget}))
        sys.exit(3)
    nugs = [x for x in (a.nuggets or "").split(",") if x]
    for nid in nugs:
        if not (root / "nuggets" / f"{nid}.json").exists():
            sys.exit(f"ERROR: nugget {nid} does not exist")
    imgs = image_nugget_ids(root, nugs)
    if len(imgs) > 1:
        sys.exit("ERROR: at most ONE image nugget per slide — "
                 f"got {', '.join(imgs)}; split the figures across slides")
    st = stamp(root)
    sid = f"{slugify(a.title)}--{st}"
    state = {"slide_id": sid, "state": "parked" if parked_flag else "draft",
             "title": a.title,
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if hint:
        state["intended_function"] = hint
    (root / "slides" / f"{sid}.md").write_text(skeleton(a.title, nugs), encoding="utf-8")
    save_state(root, sid, state)
    A = assoc(root); A[sid] = nugs; write_assoc(root, A)
    ids = order(root)
    if parked_flag:
        parked = parked + [sid]
    else:
        if a.after in (None, "", "end") or a.after not in ids:
            ids.append(sid)
        else:
            ids.insert(ids.index(a.after) + 1, sid)
    write_order(root, ids, parked=parked, c=c)
    log(root, "storyteller", "create-slide", slide=sid, nuggets=nugs,
        title=a.title, parked=parked_flag)
    print(json.dumps({"slide_id": sid, "nuggets": nugs, "parked": parked_flag}))


def cmd_park(root: Path, a):
    """Move a slide out of the active order into the commented parked block
    (D34): file + association preserved, budget slot freed."""
    sid = a.slide
    if not (root / "slides" / f"{sid}.json").exists():
        sys.exit(f"ERROR: slide {sid} does not exist")
    stj = load_state(root, sid)
    if stj.get("state") == "locked":
        sys.exit(f"ERROR: slide {sid} is locked — a locked slide is "
                 "user-owned and cannot be parked")
    if stj.get("state") == "parked":
        sys.exit(f"ERROR: slide {sid} is already parked")
    reason = getattr(a, "reason", "") or ""
    stj["state_before_park"] = stj.get("state", "draft")
    stj["state"] = "parked"
    stj["parked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if reason:
        stj["parked_reason"] = reason
    save_state(root, sid, stj)
    write_order(root, [i for i in order(root) if i != sid])
    log(root, "km", "park-slide", slide=sid, reason=reason)
    print(json.dumps({"ok": True, "slide": sid, "state": "parked"}))


def cmd_unpark(root: Path, a):
    """Return a parked slide to the active order (needs a free slot, D34)."""
    sid = a.slide
    if not (root / "slides" / f"{sid}.json").exists():
        sys.exit(f"ERROR: slide {sid} does not exist")
    stj = load_state(root, sid)
    if stj.get("state") != "parked":
        sys.exit(f"ERROR: slide {sid} is not parked")
    budget = int(ctx(root)["deck"]["max_slides"])
    parked = parked_ids(root)         # the slide itself is parked, not counted
    cur = len({p.stem for p in slide_files(root)} - set(parked))
    if cur >= budget:
        print(json.dumps({"error": "budget_full", "current": cur, "max": budget}))
        sys.exit(3)
    stj["state"] = stj.pop("state_before_park", "draft")
    stj.pop("parked_reason", None)
    stj.pop("parked_at", None)
    save_state(root, sid, stj)
    write_order(root, order(root) + [sid],
                parked=[p for p in parked if p != sid])
    log(root, "km", "unpark-slide", slide=sid)
    print(json.dumps({"ok": True, "slide": sid, "state": stj["state"]}))


def cmd_associate(root: Path, a):
    """Attach nuggets to an existing content slide (the plan's ``associate``
    decision, D34/D41). The slide needs recomposition afterwards — the
    orchestrator's concern."""
    sid = a.slide
    nugs = [x for x in (a.nuggets or "").split(",") if x]
    if not nugs:
        sys.exit("ERROR: associate needs at least one nugget id")
    if not (root / "slides" / f"{sid}.json").exists():
        sys.exit(f"ERROR: slide {sid} does not exist")
    stj = load_state(root, sid)
    if stj.get("state") == "locked":
        sys.exit(f"ERROR: slide {sid} is locked — propose instead of editing")
    if stj.get("state") == "parked":
        sys.exit(f"ERROR: slide {sid} is parked — unpark it first")
    A = assoc(root)
    if sid not in A:
        sys.exit(f"ERROR: slide {sid} not found in associations")
    if not A[sid]:
        sys.exit(f"ERROR: slide {sid} is structural — structural slides "
                 "hold no nuggets")
    for nid in nugs:
        if not (root / "nuggets" / f"{nid}.json").exists():
            sys.exit(f"ERROR: nugget {nid} does not exist")
    merged = A[sid] + [n for n in nugs if n not in A[sid]]
    imgs = image_nugget_ids(root, merged)
    if len(imgs) > 1:
        sys.exit(f"ERROR: slide {sid} would carry more than one image "
                 f"nugget ({', '.join(imgs)}) — at most ONE figure per slide")
    A[sid] = merged
    write_assoc(root, A)
    log(root, "storyteller", "associate-nuggets", slide=sid, nuggets=nugs)
    print(json.dumps({"slide_id": sid, "nuggets": merged}))

def cmd_merge(root: Path, a):
    parts = [x for x in (a.slides or "").split(",") if x]
    if len(parts) < 2:
        sys.exit("ERROR: merge needs >=2 slide ids")
    if len(set(parts)) != len(parts):
        sys.exit("ERROR: duplicate slide ids in merge")
    A = assoc(root)
    for sid in parts:
        if sid not in A:
            sys.exit(f"ERROR: slide {sid} not found in associations")
        state = load_state(root, sid).get("state")
        if state == "locked":
            sys.exit(f"ERROR: slide {sid} is locked — a locked slide is "
                     "user-owned and cannot be merged")
        if state == "parked":
            sys.exit(f"ERROR: slide {sid} is parked — unpark it before "
                     "merging")
    merged_nugs, seen = [], set()
    for sid in parts:
        for nid in A[sid]:
            if nid not in seen:
                seen.add(nid); merged_nugs.append(nid)
    imgs = image_nugget_ids(root, merged_nugs)
    if len(imgs) > 1:
        sys.exit("ERROR: the merged slide would carry more than one image "
                 f"nugget ({', '.join(imgs)}) — at most ONE figure per slide")
    title = a.title or "Merged: " + " + ".join(A_title(root, s) for s in parts)
    st = stamp(root)
    sid = f"{slugify(title)}--{st}"
    (root / "slides" / f"{sid}.md").write_text(skeleton(title, merged_nugs), encoding="utf-8")
    (root / "slides" / f"{sid}.json").write_text(json.dumps(
        {"slide_id": sid, "state": "draft", "title": title,
         "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "merged_from": parts}, indent=2), encoding="utf-8")
    ids = order(root)
    pos = min((ids.index(s) for s in parts if s in ids), default=len(ids))
    for s in parts:
        (root / "slides" / f"{s}.md").unlink(missing_ok=True)
        (root / "slides" / f"{s}.json").unlink(missing_ok=True)
        A.pop(s, None)
        if s in ids: ids.remove(s)
    A[sid] = merged_nugs; write_assoc(root, A)
    ids.insert(min(pos, len(ids)), sid)
    write_order(root, ids)
    log(root, "storyteller", "merge-slides", slide=sid, merged_from=parts, nuggets=merged_nugs)
    print(json.dumps({"slide_id": sid, "nuggets": merged_nugs, "retired": parts}))

def A_title(root: Path, sid: str) -> str:
    p = root / "slides" / f"{sid}.json"
    return json.loads(p.read_text(encoding="utf-8"))["title"] if p.exists() else sid

# ---------- presenter notes (raw-knowledge fallback, D39) ----------

def load_nugget(root: Path, nid: str) -> dict | None:
    p = root / "nuggets" / f"{nid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

def nugget_raw(n: dict) -> str:
    """A nugget's *raw knowledge* as plain text — its verbatim provenance anchor.

    ``raw_text`` for a text nugget; an image nugget's ``visible_text`` (the
    verbatim strings in the figure) joined by newlines; ``information`` only as
    a last resort so a nugget with neither anchor still yields a note.
    """
    raw = n.get("raw_text")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    vt = n.get("visible_text")
    if isinstance(vt, list) and vt:
        return "\n".join(str(x) for x in vt).strip()
    if isinstance(vt, str) and vt.strip():
        return vt.strip()
    info = n.get("information")
    return info.strip() if isinstance(info, str) and info.strip() else ""

def nugget_locator(n: dict) -> str:
    """A short provenance label for a note block: ``source p.N`` (``· figure``
    for an image nugget)."""
    loc = str(n.get("source") or "?")
    page = n.get("page")
    if page not in (None, ""):
        loc += f" p.{page}"
    if n.get("kind") == "image":
        loc += " · figure"
    return loc

def build_presenter_notes(root: Path, sid: str) -> str:
    """Assemble a Slidev speaker-notes comment from a slide's nuggets' raw
    knowledge (verbatim), each labelled with its source locator.

    Empty string when the slide has no associated nuggets (a structural slide)
    or none carry usable raw text — the caller then leaves notes untouched.
    """
    blocks = []
    for nid in assoc(root).get(sid, []):
        n = load_nugget(root, nid)
        if not n:
            continue
        raw = nugget_raw(n)
        if raw:
            blocks.append(f"[{nugget_locator(n)}]\n{raw}")
    if not blocks:
        return ""
    return notes_comment("Source material (verbatim) — presenter reference:"
                         "\n\n" + "\n\n".join(blocks))

def has_presenter_notes(body: str) -> bool:
    """True when a composed body already ends with speaker notes.

    Slidev treats the *last* HTML comment in a slide as its notes. We look only
    at a trailing comment, and do NOT count a ``FIGURE NEEDED`` / skeleton
    ``awaiting composition`` placeholder as notes — so those get real notes
    appended after them (the appended block then becomes the last comment).
    """
    stripped = body.rstrip()
    if not stripped.endswith("-->"):
        return False
    start = stripped.rfind("<!--")
    if start == -1:
        return False
    inner = stripped[start + 4:-3].strip().lower()
    if inner.startswith("figure needed") or inner.startswith("awaiting composition"):
        return False
    return True

def cmd_set_content(root: Path, a):
    sp = root / "slides" / f"{a.slide}.md"
    if not sp.exists() or not (root / "slides" / f"{a.slide}.json").exists():
        sys.exit(f"ERROR: slide {a.slide} does not exist")
    stj = load_state(root, a.slide)
    if stj.get("state") == "locked":
        sys.exit(f"ERROR: slide {a.slide} is locked — user-owned content; "
                 "unlock it before writing")
    if stj.get("state") == "parked":
        sys.exit(f"ERROR: slide {a.slide} is parked — unpark it before "
                 "writing")
    # utf-8-sig: tolerate the BOM PowerShell 5.1 / Notepad prepend to the
    # composer's temp file (a BOM'd body is valid, not "no frontmatter").
    body = Path(a.body_file).read_text(encoding="utf-8-sig")
    fm = re.match(r"^---\n(.*?)\n---\n", body, re.S)
    if not fm:
        sys.exit("ERROR: body has no frontmatter block")
    layout = re.search(r"layout:\s*(\S+)", fm.group(1))
    caps = [l["name"] for l in ctx(root)["theme"]["capabilities"]["layouts"]]
    if layout and layout.group(1) not in caps:
        sys.exit(f"ERROR: layout '{layout.group(1)}' not in theme capabilities {caps}")
    # Slidev serves public/ at the site root, so a slide references an asset by
    # a root-absolute URL (e.g. /extracted/x.png -> public/extracted/x.png).
    for asset in missing_assets(root, body):
        sys.exit(f"ERROR: referenced asset '{asset}' does not exist "
                 f"(expected under public/: public{asset})")
    # Presenter notes default to the nuggets' raw knowledge (D39): when the
    # composer left speaker notes empty, fill them verbatim from the slide's
    # nuggets so the presenter has the full source behind the telegraphic body.
    notes_added = False
    if not has_presenter_notes(body):
        notes = build_presenter_notes(root, a.slide)
        if notes:
            body = body.rstrip() + "\n\n" + notes
            notes_added = True
    sp.write_text(body, encoding="utf-8")
    stj["state"] = "composed"
    save_state(root, a.slide, stj)
    log(root, "composer", "set-content", slide=a.slide, chars=len(body),
        notes_added=notes_added)
    print(json.dumps({"ok": True, "slide": a.slide, "notes_added": notes_added}))

def cmd_validate(root: Path, a):
    errs = []
    ids = order(root)                      # active includes only
    parked = parked_ids(root)
    files = {p.stem for p in slide_files(root)}
    A = assoc(root)
    for sid in files:
        if not (root / "slides" / f"{sid}.json").exists():
            errs.append(f"{sid}: missing state file")
        if sid not in A:
            errs.append(f"{sid}: missing association entry")
    for sid, nugs in A.items():
        if sid not in files:
            errs.append(f"assoc {sid}: no slide file")
        for nid in nugs:
            if not (root / "nuggets" / f"{nid}.json").exists():
                errs.append(f"{sid}: nugget {nid} missing")
    active_files = sorted(files - set(parked))
    if sorted(ids) != active_files:
        errs.append(f"slides.md active order {ids} != active files "
                    f"{active_files}")
    if len(ids) != len(set(ids)):
        errs.append("slides.md has duplicates")
    budget = int(ctx(root)["deck"]["max_slides"])
    if len(active_files) > budget:
        errs.append(f"budget exceeded: {len(active_files)} > {budget}")
    print(json.dumps({"ok": not errs, "slides": len(active_files),
                      "parked": parked, "errors": errs}, indent=2))

# ---------- dispatch ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cn = sub.add_parser("create-nugget"); cn.add_argument("--file", required=True)
    pn = sub.add_parser("persist-nuggets"); pn.add_argument("--source", required=True); pn.add_argument("--image-source", dest="image_source", default=None); pn.add_argument("--file", required=True)
    mb = sub.add_parser("mine-brief"); mb.add_argument("--source", default=None); mb.add_argument("--image", default=None); mb.add_argument("--out", required=True)
    mm = sub.add_parser("mark-mined"); mm.add_argument("--source", required=True)
    pb = sub.add_parser("plan-brief"); pb.add_argument("--out", required=True)
    wp = sub.add_parser("write-plan"); wp.add_argument("--file", required=True)
    cb = sub.add_parser("compose-brief"); cb.add_argument("--slide", required=True); cb.add_argument("--out", required=True)
    ws = sub.add_parser("write-slide"); ws.add_argument("--slide", required=True); ws.add_argument("--file", required=True)
    c = sub.add_parser("create-slide"); c.add_argument("--title", required=True); c.add_argument("--nuggets", default=""); c.add_argument("--after", default="end"); c.add_argument("--parked", action="store_true"); c.add_argument("--intended-function", dest="intended_function", default=None)
    an = sub.add_parser("associate-nuggets"); an.add_argument("--slide", required=True); an.add_argument("--nuggets", required=True)
    m = sub.add_parser("merge-slides"); m.add_argument("--slides", required=True); m.add_argument("--title", default="")
    pk = sub.add_parser("park-slide"); pk.add_argument("--slide", required=True); pk.add_argument("--reason", default="")
    up = sub.add_parser("unpark-slide"); up.add_argument("--slide", required=True)
    s = sub.add_parser("set-content"); s.add_argument("--slide", required=True); s.add_argument("--body-file", required=True)
    sub.add_parser("validate")
    a = ap.parse_args()
    root = find_deck_root(a.deck)
    {"create-nugget": cmd_create_nugget, "persist-nuggets": cmd_persist_nuggets,
     "mine-brief": cmd_mine_brief, "mark-mined": cmd_mark_mined,
     "plan-brief": cmd_plan_brief, "write-plan": cmd_write_plan,
     "compose-brief": cmd_compose_brief, "write-slide": cmd_write_slide,
     "create-slide": cmd_create, "associate-nuggets": cmd_associate,
     "merge-slides": cmd_merge, "park-slide": cmd_park,
     "unpark-slide": cmd_unpark,
     "set-content": cmd_set_content, "validate": cmd_validate}[a.cmd](root, a)

if __name__ == "__main__":
    main()
