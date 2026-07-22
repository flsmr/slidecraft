#!/usr/bin/env python
"""Scaffold a fresh Slidecraft deck in the current working directory.

``/init-deck`` runs this after the interview. The deck root is the CWD (D25):
the user creates the target folder, launches Claude inside it, and this script
lays down the empty deck skeleton — folders, ``deck-context.json`` (interview
answers + derived per-agent injection blocks + scanned theme capabilities),
``slides.md`` headmatter, a minimal npm project so Slidev can render it, and the
double-click launchers.

Deterministic, no LLM. Refuses to clobber an existing deck (a
``deck-context.json`` already in CWD).

Two phases (D38 — cut the first-view wait):

* ``--prewarm`` runs the parts that only need **topic + theme**, as early in the
  interview as possible: create folders, **copy a local theme into the deck's
  ``theme/`` subfolder** (self-containment), write ``package.json`` + ``.gitignore``
  + the launchers. ``/init-deck`` then kicks off ``npm install`` **in the
  background** while the rest of the interview runs, so Slidev is already
  installed by the time the user previews.
* the default (full) phase writes everything: ``deck-context.json``,
  ``slides.md``, ``associations.json`` (and re-runs the prewarm steps
  idempotently, so a standalone full run still produces a complete deck).

CLI:  python scaffold_deck.py --answers PATH [--prewarm]

``answers`` JSON:
  {topic, audience, language, deck_type, setting, max_duration_minutes,
   max_slides?, theme,
   presenter?, institution?, course?, date?}
where ``theme`` = {type: "builtin"|"local"|"npm"|"github",
                   source: "<name-or-path-or-url>"}.

``max_slides`` is **optional** (D38): when absent it is derived from
``max_duration_minutes`` via the deck's slide-to-time pacing (default
1.5 min/slide; per-deck-type table below). An explicit ``max_slides`` always
wins, so the user can override the estimate.

``presenter``/``institution``/``course``/``date`` are optional deck metadata
(ticket 10, T6): the fields the old skeleton substituted into cover / footer /
thank-you slots. They land in ``deck-context.deck`` and are exposed to the
slide-composer so structural slides can be authored; a ``FOOTER`` is derived as
``presenter · date``. Absent fields become empty strings.
"""
import argparse, json, shutil, sys
from pathlib import Path

# Same-directory import (scripts are referenced by absolute path, D27/D33).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_theme  # noqa: E402

# 0.5: prewarm phase + local-theme localization to ``theme/`` + duration→slides
# pacing (D38). 0.4 added theme.styleguide + enriched slot-role capabilities +
# composer STYLE-GUIDE injection + optional deck metadata (T3/T6).
SCHEMA_VERSION = "0.5"

FOLDERS = [
    "input/processed",
    "sources",
    "slides",
    "nuggets",
    "public/extracted",
    "public/generated",
    "assets",
    "logs",
]

# The interview fields the *full* scaffold needs. ``max_slides`` is intentionally
# absent — it is derived from ``max_duration_minutes`` when not supplied (D38).
REQUIRED_ANSWER_FIELDS = [
    "topic", "audience", "language", "deck_type", "setting",
    "max_duration_minutes", "theme",
]
# The prewarm phase only needs enough to lay down the npm project + theme copy.
REQUIRED_PREWARM_FIELDS = ["topic", "theme"]

# ---------------------------------------------------------------------------
# Slide-to-time pacing (D38)
# ---------------------------------------------------------------------------
# Minutes of speaking time per slide, used to turn the interview's *duration*
# answer into a slide budget. Default 1.5 min/slide (user preference,
# 2026-07-18) — also the academic/lecture value. The per-deck-type table is
# derived from the legacy "Slide-to-Time Ratios" (best-practices.md): the
# min/slide figure is 1 / slides-per-minute for each deck kind. Unknown types
# fall back to the 1.5 default.
MINUTES_PER_SLIDE_DEFAULT = 1.5
MINUTES_PER_SLIDE_BY_TYPE = {
    "lecture": 1.5, "academic": 1.5, "academic lecture": 1.5,
    "pitch": 0.75, "keynote": 0.75,
    "executive meeting": 1.25, "executive": 1.25,
    "status report": 1.25, "business": 1.25,
    "conference talk": 1.0,
    "workshop": 2.0,
    "technical": 2.5,
}

# Local themes are copied here so the deck is self-contained (D38).
THEME_SUBDIR = "theme"
# Don't drag a theme's build detritus into the deck when copying it in.
_THEME_COPY_IGNORE = shutil.ignore_patterns(
    "node_modules", ".git", ".hg", ".svn", "dist", ".cache", "*.log")


def minutes_per_slide(deck_type: str) -> float:
    """Speaking minutes per slide for a deck type (default 1.5, D38)."""
    return MINUTES_PER_SLIDE_BY_TYPE.get(
        (deck_type or "").strip().lower(), MINUTES_PER_SLIDE_DEFAULT)


def derive_max_slides(ans: dict) -> int:
    """The slide budget: an explicit ``max_slides`` wins; else duration ÷ pace.

    A duration answer (minutes) is converted with the deck-type pace
    (``minutes_per_slide``), rounded to the nearest whole slide, floored at 1.
    """
    explicit = ans.get("max_slides")
    if explicit not in (None, "", 0, "0"):
        return int(explicit)
    dur = ans.get("max_duration_minutes")
    if dur in (None, "", 0, "0"):
        sys.exit("ERROR: answers need either max_slides or max_duration_minutes")
    try:
        dur = float(dur)
    except (TypeError, ValueError):
        sys.exit(f"ERROR: max_duration_minutes must be a number, got {dur!r}")
    pace = minutes_per_slide(ans.get("deck_type", ""))
    return max(1, round(dur / pace))


def load_answers(path: str, *, prewarm: bool = False) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"ERROR: answers file {path} does not exist")
    try:
        ans = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"ERROR: answers file is not valid JSON: {exc}")
    required = REQUIRED_PREWARM_FIELDS if prewarm else REQUIRED_ANSWER_FIELDS
    missing = [f for f in required if f not in ans]
    if missing:
        sys.exit(f"ERROR: answers missing field(s): {', '.join(missing)}")
    theme = ans["theme"]
    if not isinstance(theme, dict) or "type" not in theme or "source" not in theme:
        sys.exit('ERROR: theme must be {"type": ..., "source": ...}')
    if theme["type"] not in ("builtin", "local", "npm", "github"):
        sys.exit('ERROR: theme.type must be builtin|local|npm|github')
    return ans


# ---------------------------------------------------------------------------
# Theme handling
# ---------------------------------------------------------------------------

def localize_theme(root: Path, theme: dict) -> tuple[dict, str]:
    """Make a *local* theme part of the deck so the deck is self-contained (D38).

    Copies the theme folder into ``<deck>/theme/`` and returns a theme dict
    rewritten to reference it by the deck-relative path ``./theme`` (which is
    what ``slides.md`` and the deck context record, so the deck folder is
    portable). ``builtin`` / ``npm`` / ``github`` themes are returned unchanged
    — they resolve via Slidev's registry / ``node_modules`` and are already
    portable after ``npm install``.

    Returns ``(portable_theme, scan_source)``: ``scan_source`` is the path to
    hand to ``scan_theme`` — the **absolute** path of the copied folder for a
    local theme (so the scan is CWD-independent), else the original source.

    Idempotent: if ``theme/`` already exists (prewarm ran, or a re-run), the
    copy is skipped and the existing copy is reused.
    """
    if theme.get("type") != "local":
        return dict(theme), theme["source"]
    dest = root / THEME_SUBDIR
    if not dest.exists():
        src = Path(theme["source"]).expanduser()
        if not src.is_dir():
            sys.exit(f"ERROR: local theme path is not a directory: {theme['source']}")
        shutil.copytree(src, dest, ignore=_THEME_COPY_IGNORE)
    portable = {"type": "local", "source": f"./{THEME_SUBDIR}"}
    return portable, str(dest.resolve())


def theme_name(theme: dict) -> str:
    """Value for ``theme:`` in slides.md headmatter.

    Source for builtin/npm/github; the local ``./theme`` path for a (localized)
    local theme (Slidev resolves ``./`` | ``../`` | ``/`` paths directly).
    """
    return theme["source"]


def theme_package(theme: dict):
    """(pkg_name, version) to add to package.json dependencies, or None.

    * builtin  -> the @slidev/theme-<name> package (default -> theme-default).
    * npm      -> the npm package name as given.
    * local    -> None (resolved by path in slides.md; nothing to install).
    * github   -> None offline (best-effort; add by hand if needed).
    """
    t = theme["type"]
    if t == "builtin":
        return (f"@slidev/theme-{theme['source']}", "latest")
    if t == "npm":
        return (theme["source"], "latest")
    return None


def local_theme_deps(root: Path) -> dict:
    """Runtime dependencies a localized local theme declares in its own
    ``theme/package.json``, so the deck's ``npm install`` pulls what the theme
    needs to render — completing the self-containment (D38(c)).

    Best-effort: returns ``{}`` when the theme ships no ``package.json`` / no
    ``dependencies``. Skips the theme's self-reference and any non-registry
    specifier (``workspace:`` / ``file:`` / ``link:``) that a plain deck install
    couldn't resolve.
    """
    pkg = root / THEME_SUBDIR / "package.json"
    if not pkg.is_file():
        return {}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    deps = data.get("dependencies")
    if not isinstance(deps, dict):
        return {}
    self_name = data.get("name")
    out = {}
    for name, spec in deps.items():
        if name == self_name:
            continue
        if isinstance(spec, str) and spec.split(":", 1)[0] in ("workspace", "file", "link"):
            continue
        out[name] = spec
    return out


# ---------------------------------------------------------------------------
# Injection / deck blocks
# ---------------------------------------------------------------------------

def derive_footer(presenter: str, date: str) -> str:
    """A running-footer string from deck metadata: ``presenter · date``.

    Either part may be empty; the separator only appears when both are present.
    """
    parts = [p for p in (presenter.strip(), date.strip()) if p]
    return " · ".join(parts)


def build_injection(ans: dict, styleguide: str = "") -> dict:
    """Per-agent placeholder values derived from the interview (SPEC §4/§7.1).

    ``ans`` must already carry the resolved ``max_slides`` (see
    ``derive_max_slides``). ``styleguide`` is the theme's ``styleguide.md`` path
    (empty if none); it is injected as ``STYLE-GUIDE`` into both composers so
    figures + structural slides respect the theme's visual contract (T3).
    """
    topic = ans["topic"]
    miner = {"FOCUS-TOPIC": topic}
    presenter = str(ans.get("presenter", ""))
    institution = str(ans.get("institution", ""))
    course = str(ans.get("course", ""))
    date = str(ans.get("date", ""))
    return {
        "knowledge-miner": dict(miner),
        "image-miner": dict(miner),
        "storyteller": {
            "MAX-SLIDES": str(ans["max_slides"]),
            "MAX-DURATION-MINUTES": str(ans.get("max_duration_minutes", "")),
            "DECK-TYPE": ans["deck_type"],
            "AUDIENCE": ans["audience"],
            "SETTING": ans["setting"],
            "LANGUAGE": ans["language"],
            "TOPIC": topic,
        },
        "slide-composer": {
            "AUDIENCE": ans["audience"],
            "DECK-TYPE": ans["deck_type"],
            "LANGUAGE": ans["language"],
            "STYLE-GUIDE": styleguide,
            # Deck metadata for structural slides (cover / footer / thank-you), T6.
            "PRESENTER": presenter,
            "INSTITUTION": institution,
            "COURSE": course,
            "DATE": date,
            "FOOTER": derive_footer(presenter, date),
        },
        "image-composer": {
            "AUDIENCE": ans["audience"],
            "DECK-TYPE": ans["deck_type"],
            "LANGUAGE": ans["language"],
            "STYLE-GUIDE": styleguide,
            "MAX-ATTEMPTS": 3,
        },
    }


def build_deck_block(ans: dict) -> dict:
    return {
        "topic": ans["topic"],
        "type": ans["deck_type"],
        "audience": ans["audience"],
        "setting": ans["setting"],
        "language": ans["language"],
        "max_slides": ans["max_slides"],
        "max_duration_minutes": ans.get("max_duration_minutes", None),
        # Optional deck metadata (T6); empty string when not captured.
        "presenter": str(ans.get("presenter", "")),
        "institution": str(ans.get("institution", "")),
        "course": str(ans.get("course", "")),
        "date": str(ans.get("date", "")),
    }


# ---------------------------------------------------------------------------
# Idempotent scaffold steps
# ---------------------------------------------------------------------------

def _guard(root: Path):
    """Refuse to clobber an already-initialized deck."""
    if (root / "deck-context.json").exists():
        sys.exit("ERROR: deck-context.json already exists in "
                 f"{root} — refusing to clobber an existing deck.")


def ensure_folders(root: Path, created: list):
    for rel in FOLDERS:
        d = root / rel
        if not d.exists():
            created.append(rel + "/")
        d.mkdir(parents=True, exist_ok=True)


def write_package_json(root: Path, ans: dict, theme: dict, created: list):
    deps = {"@slidev/cli": "latest"}
    pkg = theme_package(theme)
    if pkg:
        deps[pkg[0]] = pkg[1]
    # A localized local theme may need its own deps to render; fold them in
    # (without overriding the deck's own @slidev/cli pin).
    if theme.get("type") == "local":
        for name, spec in local_theme_deps(root).items():
            deps.setdefault(name, spec)
    package = {
        "name": scan_theme_slug(ans["topic"]),
        "private": True,
        "type": "module",
        "dependencies": deps,
    }
    (root / "package.json").write_text(
        json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")
    created.append("package.json")


def write_gitignore(root: Path, created: list):
    # node_modules/ is heavy and reinstallable; the local theme copy (theme/)
    # IS part of the deck, so it is deliberately NOT ignored (D38).
    (root / ".gitignore").write_text(
        "node_modules/\ndist/\n.draft-status.json\nlogs/serve_deck.json\n",
        encoding="utf-8")
    created.append(".gitignore")


def write_launchers(root: Path, created: list):
    """Copy the double-click launchers from the templates dir next to this script.

    Windows (.cmd) + macOS/Linux (.sh) so a deck is viewable on any platform.
    """
    tpl_dir = Path(__file__).resolve().parent.parent / "templates"
    for name in ("show_slide_deck.cmd", "show_slide_deck.sh"):
        tpl = tpl_dir / name
        if tpl.exists():
            dest = root / name
            shutil.copyfile(tpl, dest)
            if name.endswith(".sh"):
                # Make the POSIX launcher executable (double-click / ./ on mac/linux).
                dest.chmod(dest.stat().st_mode | 0o111)
            created.append(name)
        else:
            # Non-fatal: the deck is still usable, just missing this launcher.
            created.append(f"(WARNING: launcher template not found at {tpl}; {name} not copied)")


def write_associations(root: Path, created: list):
    (root / "associations.json").write_text("{}", encoding="utf-8")
    created.append("associations.json")


def write_slides_md(root: Path, ans: dict, theme: dict, created: list):
    # json.dumps = YAML-safe scalar: a topic containing a colon must not
    # break the headmatter parse (same rule as km.write_order).
    title = json.dumps(str(ans["topic"]), ensure_ascii=False)
    slides_md = (f"---\ntheme: {theme_name(theme)}\n"
                 f"title: {title}\n---\n")
    (root / "slides.md").write_text(slides_md, encoding="utf-8")
    created.append("slides.md")


def write_deck_context(root: Path, ans: dict, theme: dict, scan_source: str,
                       created: list) -> dict:
    capabilities = scan_theme.scan(theme["type"], scan_source)
    # The theme's style-guide path (empty if the theme ships none) is recorded
    # on the theme block and injected into both composers (ticket 10, T3).
    styleguide = capabilities.get("styleguide", "")
    context = {
        "schema_version": SCHEMA_VERSION,
        "deck": build_deck_block(ans),
        "theme": {
            "type": theme["type"],
            "source": theme["source"],
            "styleguide": styleguide,
            "capabilities": capabilities,
        },
        "injection": build_injection(ans, styleguide=styleguide),
    }
    (root / "deck-context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")
    created.append("deck-context.json")
    return capabilities


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

def prewarm(root: Path, ans: dict) -> dict:
    """Lay down everything that only needs topic + theme, so ``/init-deck`` can
    start ``npm install`` in the background during the interview (D38).

    Creates folders, localizes a local theme into ``theme/``, and writes
    ``package.json`` / ``.gitignore`` / the launchers. Does **not** write
    ``deck-context.json`` — that waits for the full interview.
    """
    _guard(root)
    created: list = []
    ensure_folders(root, created)
    theme, _scan_source = localize_theme(root, ans["theme"])
    write_package_json(root, ans, theme, created)
    write_gitignore(root, created)
    write_launchers(root, created)
    return {
        "phase": "prewarm",
        "deck_root": str(root),
        "theme": theme,
        "node_modules_present": (root / "node_modules").is_dir(),
        "created": created,
    }


def scaffold(root: Path, ans: dict) -> dict:
    """Full scaffold. Idempotent over ``prewarm`` — safe to run standalone or
    after a prewarm (it re-does the prewarm steps, all of which are no-ops when
    already present)."""
    _guard(root)
    ans = dict(ans)
    ans["max_slides"] = derive_max_slides(ans)
    created: list = []

    ensure_folders(root, created)
    theme, scan_source = localize_theme(root, ans["theme"])
    write_associations(root, created)
    capabilities = write_deck_context(root, ans, theme, scan_source, created)
    write_slides_md(root, ans, theme, created)
    write_package_json(root, ans, theme, created)
    write_gitignore(root, created)
    write_launchers(root, created)

    return {
        "phase": "full",
        "deck_root": str(root),
        "max_slides": ans["max_slides"],
        "max_duration_minutes": ans.get("max_duration_minutes"),
        "minutes_per_slide": minutes_per_slide(ans.get("deck_type", "")),
        "theme": {"type": theme["type"], "source": theme["source"],
                  "layouts": len(capabilities.get("layouts", []))},
        "created": created,
    }


def scan_theme_slug(name: str) -> str:
    """npm-safe package name from the deck topic (lowercase, hyphenated)."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "slidecraft-deck")[:60]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--prewarm", action="store_true",
                    help="phase 1: folders + theme copy + package.json only "
                         "(so npm install can start during the interview)")
    a = ap.parse_args()
    ans = load_answers(a.answers, prewarm=a.prewarm)
    fn = prewarm if a.prewarm else scaffold
    summary = fn(Path.cwd(), ans)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
