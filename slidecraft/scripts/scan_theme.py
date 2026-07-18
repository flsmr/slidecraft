#!/usr/bin/env python
"""Scan a Slidev theme for its layout/component capabilities.

Emits a ``capabilities`` JSON that ``/init-deck`` writes into
``deck-context.json`` (SPEC §7.1). Downstream, ``km set-content`` validates a
composed slide's ``layout:`` against this list, and the slide-composer's
injection carries the available layouts + slots.

Shape:
  {"layouts": [{"name": ..., "slots": [...], "props"?: [...],
                "alias"?: ..., "roles"?: {role: physical}, "intent"?: ...,
                "defaults"?: {...}}, ...],
   "components": [...], "styleguide"?: "<path>", "note"?: "..."}

The **slot-role contract** (ticket 10, T3): a local theme that ships a
``semantic-layouts.json`` maps each cryptic physical slot (``body-26``,
``ph-1``, ``slide4``) to a semantic role plus how to fill it. When present,
each physical layout is enriched with its ``alias`` name, its ``roles``
(role -> physical slot), the alias ``intent`` (what the layout is for and how
to fill each slot), and its ``defaults`` (e.g. cover ``title`` -> "Agenda",
``end`` ``title`` -> "Thank you"). Without this file a layout keeps only its
bare physical ``slots`` and the capabilities carry a ``note`` that role/intent
is unavailable — a composer can still author, but quality drops.

Theme kinds:
  * builtin  -> hard-coded Slidev default-theme layout set (no scan needed).
  * local    -> a folder: list layouts/*.vue, parse <slot name="..."> per file,
                collect components/*.vue stems, apply semantic-layouts.json,
                detect a root styleguide.md.
  * npm/github -> best-effort; if not resolvable offline, fall back to the
                builtin default set with a ``note`` (never fail hard).

Deterministic, no LLM. CLI:
  python scan_theme.py --type builtin|local|npm|github --source X
"""
import argparse, json, re, sys
from pathlib import Path

# ---------- builtin (Slidev default theme) ----------

# Known layouts of @slidev/theme-default. Each renders its slide body through
# the ``default`` slot; the multi-region layouts add named slots, and the
# image-* layouts take an ``image`` prop. Hard-coded (SPEC deliverable 2).
_BUILTIN_LAYOUTS = [
    {"name": "default", "slots": ["default"]},
    {"name": "center", "slots": ["default"]},
    {"name": "cover", "slots": ["default"]},
    {"name": "section", "slots": ["default"]},
    {"name": "image", "slots": ["default"], "props": ["image"]},
    {"name": "image-left", "slots": ["default"], "props": ["image"]},
    {"name": "image-right", "slots": ["default"], "props": ["image"]},
    {"name": "two-cols", "slots": ["default", "right"]},
    {"name": "two-cols-header", "slots": ["default", "right", "top"]},
    {"name": "full", "slots": ["default"]},
    {"name": "end", "slots": ["default"]},
    {"name": "quote", "slots": ["default"]},
    {"name": "statement", "slots": ["default"]},
    {"name": "fact", "slots": ["default"]},
    {"name": "none", "slots": ["default"]},
]


def builtin_capabilities() -> dict:
    """Deep copy of the builtin layout set (so callers can annotate freely)."""
    return {
        "layouts": [dict(l, slots=list(l["slots"]),
                         **({"props": list(l["props"])} if "props" in l else {}))
                    for l in _BUILTIN_LAYOUTS],
        "components": [],
    }


# ---------- local (folder scan) ----------

def _parse_slots(vue_text: str) -> list[str]:
    """Slot names declared in a .vue file.

    ``<slot name="right">`` -> ``right``; a bare ``<slot />`` / ``<slot>`` ->
    ``default``. Order preserved, de-duplicated, ``default`` first if present.
    """
    slots: list[str] = []
    for m in re.finditer(r"<slot\b([^>]*)>", vue_text):
        attrs = m.group(1)
        nm = re.search(r'name\s*=\s*["\']([^"\']+)["\']', attrs)
        name = nm.group(1) if nm else "default"
        if name not in slots:
            slots.append(name)
    if not slots:
        slots = ["default"]
    # Put default first for readability.
    slots.sort(key=lambda s: (s != "default", s))
    return slots


def _load_semantic(root: Path) -> tuple[dict | None, str | None]:
    """Parse ``semantic-layouts.json`` into a physical-layout -> alias-entry map.

    Returns ``(mapping, note)`` where ``mapping`` is
    ``{physical_layout_name: {"alias", "roles", "intent", "defaults"}}`` (first
    alias wins on a collision) or ``None`` if the file is absent/unreadable, and
    ``note`` is a human-readable reason to record when the contract is missing.
    """
    path = root / "semantic-layouts.json"
    if not path.is_file():
        return None, ("no semantic-layouts.json: layouts carry bare physical "
                      "slot names only, so slot roles / intents / defaults are "
                      "unavailable and authoring quality drops")
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as exc:
        return None, (f"semantic-layouts.json present but unreadable ({exc}); "
                      "falling back to bare physical slot names")
    # Guard the SHAPE explicitly (not via `assert`, which `python -O` strips):
    # a valid-JSON-but-wrong-shape file (top-level array/scalar, or a non-dict
    # `aliases`) must degrade to bare slots, never crash the scan.
    aliases = data.get("aliases") if isinstance(data, dict) else None
    if not isinstance(aliases, dict):
        return None, ("semantic-layouts.json present but has no valid 'aliases' "
                      "map; falling back to bare physical slot names")
    mapping: dict[str, dict] = {}
    for alias_name, entry in aliases.items():
        if not isinstance(entry, dict):
            continue
        physical = entry.get("layout")
        if not physical or physical in mapping:
            continue  # first alias wins on a collision
        mapping[physical] = {
            "alias": alias_name,
            "roles": dict(entry.get("slots", {})),
            "intent": entry.get("intent", ""),
            "defaults": dict(entry.get("defaults", {})),
        }
    return mapping, None


def local_capabilities(source: str) -> dict:
    root = Path(source).expanduser()
    if not root.is_dir():
        sys.exit(f"ERROR: local theme path is not a directory: {source}")
    layouts = []
    layouts_dir = root / "layouts"
    if layouts_dir.is_dir():
        for vue in sorted(layouts_dir.glob("*.vue")):
            slots = _parse_slots(vue.read_text(encoding="utf-8", errors="replace"))
            entry = {"name": vue.stem, "slots": slots}
            layouts.append(entry)
    components = []
    comp_dir = root / "components"
    if comp_dir.is_dir():
        components = [vue.stem for vue in sorted(comp_dir.glob("*.vue"))]
    caps = {"layouts": layouts, "components": components}
    if not layouts:
        # A theme with no layouts/ folder still supports Slidev's built-ins.
        caps = builtin_capabilities()
        caps["note"] = (f"no layouts/ folder under {source}; "
                        "assuming Slidev built-in layouts")
        return caps

    # ----- slot-role contract (semantic-layouts.json) -----
    semantic, note = _load_semantic(root)
    if semantic:
        for entry in layouts:
            role_map = semantic.get(entry["name"])
            if role_map:
                # Enrich in place: role->physical map, alias, intent, defaults.
                # `name`/`slots` stay for km validation + a bare-name fallback.
                entry["alias"] = role_map["alias"]
                entry["roles"] = role_map["roles"]
                entry["intent"] = role_map["intent"]
                entry["defaults"] = role_map["defaults"]
    if note:
        caps["note"] = note

    # ----- style guide (theme's visual contract, consumed by the composers) -----
    styleguide = root / "styleguide.md"
    if styleguide.is_file():
        caps["styleguide"] = str(styleguide)

    return caps


# ---------- npm / github (best-effort, offline-tolerant) ----------

def npm_github_capabilities(kind: str, source: str) -> dict:
    """Try to resolve an installed npm theme's layouts; else builtin + note.

    Never fails hard (SPEC): an unresolvable theme falls back to the builtin
    default layout set with a ``note`` recording that it was not scanned.
    """
    if kind == "npm":
        # If the package is already installed under a local node_modules, scan
        # its layouts/ like a local theme.
        for base in (Path.cwd() / "node_modules" / source,):
            if base.is_dir():
                caps = local_capabilities(str(base))
                caps["note"] = f"scanned installed npm theme at {base}"
                return caps
    caps = builtin_capabilities()
    caps["note"] = (f"{kind} theme '{source}' not scanned offline; "
                    "using Slidev built-in layout set as a placeholder")
    return caps


# ---------- dispatch ----------

def scan(kind: str, source: str) -> dict:
    if kind == "builtin":
        return builtin_capabilities()
    if kind == "local":
        return local_capabilities(source)
    if kind in ("npm", "github"):
        return npm_github_capabilities(kind, source)
    sys.exit(f"ERROR: unknown theme type '{kind}'")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--type", required=True,
                    choices=["builtin", "local", "npm", "github"])
    ap.add_argument("--source", required=True)
    a = ap.parse_args()
    print(json.dumps(scan(a.type, a.source), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
