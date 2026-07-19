#!/usr/bin/env python
"""Knowledge-manager scripts (prototype).

Deterministic deck-state operations. Scripts move files and associations;
they never write slide prose — that is always the Composer's job.

Subcommands:
  create-nugget   --file PATH                               -> {"nugget_id": ...}
  persist-nuggets --source SLUG --file PATH                 -> {"nugget_ids": [...]}
  mine-brief      --source SLUG --out PATH                  -> {"ok": true, ...}
  mark-mined      --source SLUG                             -> {"ok": true, ...}
  create-slide  --title T --nuggets a,b --after ID|end     -> {"slide_id": ...}
  merge-slides  --slides a,b [--title T]                    -> {"slide_id": ...}
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
    """Slide IDs in slides.md order (by src includes)."""
    md = (root / "slides.md")
    if not md.exists():
        return []
    ids = re.findall(r"src:\s*\./slides/(.+?)\.md", md.read_text(encoding="utf-8"))
    return ids

def write_order(root: Path, ids: list[str]):
    c = ctx(root)
    theme_ref = (c.get("theme") or {}).get("source") or "default"
    title = c["deck"].get("topic", "Deck")
    # Import the first slide via the headmatter's own ``src`` rather than as a
    # separate ``---`` block. A standalone headmatter block followed by the first
    # ``src:`` import leaves the deck opening on an empty slide (the headmatter
    # renders as a blank slide 1); folding the first import into the headmatter
    # makes slide 1 the real cover.
    if ids:
        head = (f"---\ntheme: {theme_ref}\ntitle: {title}\n"
                f"src: ./slides/{ids[0]}.md\n---\n")
        body = "".join(f"\n---\nsrc: ./slides/{i}.md\n---\n" for i in ids[1:])
    else:
        head = f"---\ntheme: {theme_ref}\ntitle: {title}\n---\n"
        body = ""
    (root / "slides.md").write_text(head + body, encoding="utf-8")

def skeleton(title: str, nugget_ids: list[str]) -> str:
    return (f"---\nlayout: default\ntitle: {title}\n---\n\n"
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


def write_brief(root: Path, out: str, brief: str):
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(brief, encoding="utf-8")


def cmd_mine_brief(root: Path, a):
    """Render the self-contained text-miner brief (D40/D42): role craft +
    injection values + the full source text inline. The miner needs no file
    access, no scripts, no IDs — everything is in the brief."""
    src = source_record(root, a.source)
    c = ctx(root)
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


# ---------- nugget validation + persist core ----------

class Rejection(Exception):
    """A retryable validation rejection (exit 1 at the CLI — the invoke
    shim's convention for 'the model can fix this', D44)."""


def check_nugget(root: Path, n: dict):
    """Validate one enriched nugget dict; raise :class:`Rejection` on any
    schema or verbatim-guard failure. Writes nothing."""
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
        src_path = root / "sources" / f"{slug}.json"
        if not src_path.exists():
            raise Rejection(f"source {n['source']} not converted "
                            f"(expected sources/{slug}.json)")
        src = json.loads(src_path.read_text(encoding="utf-8"))
        source_text = "\n".join(pg.get("text", "") for pg in src.get("pages", []))
        if normalize(n["raw_text"]) not in normalize(source_text):
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
        n = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: nugget file is not valid JSON: {exc}")
    try:
        check_nugget(root, n)
    except Rejection as exc:
        sys.exit(f"ERROR: {exc}")
    st = persist_nugget(root, n)
    print(json.dumps({"nugget_id": st}))


def cmd_persist_nuggets(root: Path, a):
    """Fan-out persist wrapper for a miner's batch output (ticket 13).

    The miner returns ``{"nuggets": [...]}`` whose items carry no ``kind``/
    ``source`` — the orchestrator knows the source; the miner must not invent
    it. This wrapper enriches every item, validates the WHOLE batch (schema +
    verbatim guard) before writing anything — so a shim retry after a
    rejection can never duplicate already-persisted nuggets — then persists
    each item.
    """
    src = source_record(root, a.source)
    p = Path(a.file)
    if not p.exists():
        sys.exit(f"ERROR: batch file {a.file} does not exist")
    try:
        batch = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: miner output is not valid JSON: {exc}")
    if not isinstance(batch, dict) or not isinstance(batch.get("nuggets"), list):
        sys.exit('ERROR: miner output must be an object of the form '
                 '{"nuggets": [...]}')

    enriched = []
    errors = []
    for i, item in enumerate(batch["nuggets"], start=1):
        if not isinstance(item, dict):
            errors.append(f"nugget #{i}: not an object")
            continue
        n = dict(item)
        n["kind"] = "text"                      # text-miner slice: forced,
        n["source"] = src["original_file"]      # never miner-invented
        try:
            check_nugget(root, n)
        except Rejection as exc:
            errors.append(f"nugget #{i} ({n.get('title', '?')}): {exc}")
        enriched.append(n)
    if errors:
        # Atomic rejection: nothing was written; the whole corrected batch
        # comes back through the shim retry.
        sys.exit("ERROR: " + "; ".join(errors))

    ids = [persist_nugget(root, n) for n in enriched]
    log(root, "km", "persist-nuggets", source=a.source, count=len(ids))
    print(json.dumps({"nugget_ids": ids, "count": len(ids),
                      "source": a.source}))

def cmd_create(root: Path, a):
    c = ctx(root)
    budget = int(c["deck"]["max_slides"])
    cur = len(slide_files(root))
    if cur >= budget:
        print(json.dumps({"error": "budget_full", "current": cur, "max": budget}))
        sys.exit(3)
    nugs = [x for x in (a.nuggets or "").split(",") if x]
    for nid in nugs:
        if not (root / "nuggets" / f"{nid}.json").exists():
            sys.exit(f"ERROR: nugget {nid} does not exist")
    st = stamp(root)
    sid = f"{slugify(a.title)}--{st}"
    (root / "slides" / f"{sid}.md").write_text(skeleton(a.title, nugs), encoding="utf-8")
    (root / "slides" / f"{sid}.json").write_text(json.dumps(
        {"slide_id": sid, "state": "draft", "title": a.title,
         "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2), encoding="utf-8")
    A = assoc(root); A[sid] = nugs; write_assoc(root, A)
    ids = order(root)
    if a.after in (None, "", "end") or a.after not in ids:
        ids.append(sid)
    else:
        ids.insert(ids.index(a.after) + 1, sid)
    write_order(root, ids)
    log(root, "storyteller", "create-slide", slide=sid, nuggets=nugs, title=a.title)
    print(json.dumps({"slide_id": sid, "nuggets": nugs}))

def cmd_merge(root: Path, a):
    parts = [x for x in (a.slides or "").split(",") if x]
    if len(parts) < 2:
        sys.exit("ERROR: merge needs >=2 slide ids")
    A = assoc(root)
    for sid in parts:
        if sid not in A:
            sys.exit(f"ERROR: slide {sid} not found in associations")
    merged_nugs, seen = [], set()
    for sid in parts:
        for nid in A[sid]:
            if nid not in seen:
                seen.add(nid); merged_nugs.append(nid)
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
    inner = ("Source material (verbatim) — presenter reference:\n\n"
             + "\n\n".join(blocks))
    # A literal comment terminator in the verbatim text would close the note
    # early; neutralise only that exact sequence (keeps the text otherwise intact).
    inner = inner.replace("-->", "-- >")
    return f"<!--\n{inner}\n-->\n"

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
    if not sp.exists():
        sys.exit(f"ERROR: slide {a.slide} does not exist")
    body = Path(a.body_file).read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", body, re.S)
    if not fm:
        sys.exit("ERROR: body has no frontmatter block")
    layout = re.search(r"layout:\s*(\S+)", fm.group(1))
    caps = [l["name"] for l in ctx(root)["theme"]["capabilities"]["layouts"]]
    if layout and layout.group(1) not in caps:
        sys.exit(f"ERROR: layout '{layout.group(1)}' not in theme capabilities {caps}")
    # Slidev serves public/ at the site root, so a slide references an asset by
    # a root-absolute URL (e.g. /extracted/x.png -> public/extracted/x.png).
    for asset in re.findall(r'src=["\'](/[^"\']+)["\']', body):
        if not (root / "public" / asset.lstrip("/")).exists():
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
    stp = root / "slides" / f"{a.slide}.json"
    stj = json.loads(stp.read_text(encoding="utf-8")); stj["state"] = "composed"
    stp.write_text(json.dumps(stj, indent=2), encoding="utf-8")
    log(root, "composer", "set-content", slide=a.slide, chars=len(body),
        notes_added=notes_added)
    print(json.dumps({"ok": True, "slide": a.slide, "notes_added": notes_added}))

def cmd_validate(root: Path, a):
    errs = []
    ids = order(root)
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
    if sorted(ids) != sorted(files):
        errs.append(f"slides.md order {ids} != files {sorted(files)}")
    if len(ids) != len(set(ids)):
        errs.append("slides.md has duplicates")
    budget = int(ctx(root)["deck"]["max_slides"])
    if len(files) > budget:
        errs.append(f"budget exceeded: {len(files)} > {budget}")
    print(json.dumps({"ok": not errs, "slides": len(files), "errors": errs}, indent=2))

# ---------- dispatch ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cn = sub.add_parser("create-nugget"); cn.add_argument("--file", required=True)
    pn = sub.add_parser("persist-nuggets"); pn.add_argument("--source", required=True); pn.add_argument("--file", required=True)
    mb = sub.add_parser("mine-brief"); mb.add_argument("--source", required=True); mb.add_argument("--out", required=True)
    mm = sub.add_parser("mark-mined"); mm.add_argument("--source", required=True)
    c = sub.add_parser("create-slide"); c.add_argument("--title", required=True); c.add_argument("--nuggets", default=""); c.add_argument("--after", default="end")
    m = sub.add_parser("merge-slides"); m.add_argument("--slides", required=True); m.add_argument("--title", default="")
    s = sub.add_parser("set-content"); s.add_argument("--slide", required=True); s.add_argument("--body-file", required=True)
    sub.add_parser("validate")
    a = ap.parse_args()
    root = find_deck_root(a.deck)
    {"create-nugget": cmd_create_nugget, "persist-nuggets": cmd_persist_nuggets,
     "mine-brief": cmd_mine_brief, "mark-mined": cmd_mark_mined,
     "create-slide": cmd_create, "merge-slides": cmd_merge,
     "set-content": cmd_set_content, "validate": cmd_validate}[a.cmd](root, a)

if __name__ == "__main__":
    main()
