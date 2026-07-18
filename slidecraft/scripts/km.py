#!/usr/bin/env python
"""Knowledge-manager scripts (prototype).

Deterministic deck-state operations. Scripts move files and associations;
they never write slide prose — that is always the Composer's job.

Subcommands:
  create-nugget --file PATH                                 -> {"nugget_id": ...}
  create-slide  --title T --nuggets a,b --after ID|end     -> {"slide_id": ...}
  merge-slides  --slides a,b [--title T]                    -> {"slide_id": ...}
  set-content   --slide ID --body-file PATH                 -> {"ok": true}
  validate                                                  -> {"ok": bool, ...}

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
    return (s or "slide")[:60]

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
    head = f"---\ntheme: default\ntitle: {c['deck'].get('topic','Deck')}\n---\n"
    body = "".join(f"\n---\nsrc: ./slides/{i}.md\n---\n" for i in ids)
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

# ---------- commands ----------

def cmd_create_nugget(root: Path, a):
    p = Path(a.file)
    if not p.exists():
        sys.exit(f"ERROR: nugget file {a.file} does not exist")
    try:
        n = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: nugget file is not valid JSON: {exc}")

    kind = n.get("kind")
    if kind not in ("text", "image"):
        sys.exit('ERROR: nugget "kind" must be "text" or "image"')
    common = ["source", "page", "title", "information"]
    req = common + (["raw_text"] if kind == "text" else ["visible_text"])
    missing = [f for f in req if f not in n or n[f] in (None, "")]
    if missing:
        sys.exit(f"ERROR: nugget missing required field(s): {', '.join(missing)}")
    if kind == "image" and not isinstance(n["visible_text"], list):
        sys.exit('ERROR: image nugget "visible_text" must be a list')

    # ----- verbatim guard (text nuggets only) -----
    if kind == "text":
        slug = source_slug(n["source"])
        src_path = root / "sources" / f"{slug}.json"
        if not src_path.exists():
            sys.exit(f"ERROR: source {n['source']} not converted "
                     f"(expected sources/{slug}.json)")
        src = json.loads(src_path.read_text(encoding="utf-8"))
        source_text = "\n".join(pg.get("text", "") for pg in src.get("pages", []))
        if normalize(n["raw_text"]) not in normalize(source_text):
            sys.exit("ERROR: verbatim guard failed — raw_text is not a "
                     f"substring of source {n['source']} (normalized). "
                     "Fix the excerpt to match the source exactly.")

    st = stamp(root)
    n["nugget_id"] = st
    n["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    n["created_by"] = "knowledge-miner"
    (root / "nuggets").mkdir(exist_ok=True)
    (root / "nuggets" / f"{st}.json").write_text(
        json.dumps(n, indent=2, ensure_ascii=False), encoding="utf-8")
    log(root, "knowledge-miner", "create-nugget", nugget=st,
        kind=kind, source=n["source"], page=n["page"])
    print(json.dumps({"nugget_id": st}))

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
    sp.write_text(body, encoding="utf-8")
    stp = root / "slides" / f"{a.slide}.json"
    stj = json.loads(stp.read_text(encoding="utf-8")); stj["state"] = "composed"
    stp.write_text(json.dumps(stj, indent=2), encoding="utf-8")
    log(root, "composer", "set-content", slide=a.slide, chars=len(body))
    print(json.dumps({"ok": True, "slide": a.slide}))

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
    c = sub.add_parser("create-slide"); c.add_argument("--title", required=True); c.add_argument("--nuggets", default=""); c.add_argument("--after", default="end")
    m = sub.add_parser("merge-slides"); m.add_argument("--slides", required=True); m.add_argument("--title", default="")
    s = sub.add_parser("set-content"); s.add_argument("--slide", required=True); s.add_argument("--body-file", required=True)
    sub.add_parser("validate")
    a = ap.parse_args()
    root = find_deck_root(a.deck)
    {"create-nugget": cmd_create_nugget, "create-slide": cmd_create,
     "merge-slides": cmd_merge, "set-content": cmd_set_content,
     "validate": cmd_validate}[a.cmd](root, a)

if __name__ == "__main__":
    main()
