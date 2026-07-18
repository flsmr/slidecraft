#!/usr/bin/env python
"""Flatten an old theme *pack* into a standalone plain Slidev theme (ticket 10, T5).

An old pack wraps the real theme in `<pack>/slidev-theme-<slug>/` alongside a now-dead
`skeletons/` folder + `pack.json`, and sometimes keeps `styleguide.md` at the pack root.
Under `docs/adr/0003-theme-is-a-plain-slidev-theme.md` a theme is just the inner
`slidev-theme-<slug>/`. This helper **copies** that inner theme out to a standalone
destination and carries a pack-root `styleguide.md` in if the theme lacks one.

It is deliberately conservative: **dry-run by default, and it never deletes anything** —
removing the old pack stays a manual, deliberate step. Nice-to-have, not required: you can
equally just point `/init-deck` at the inner folder (see docs/theme-pack-migration.md).

CLI:
  python flatten_theme_pack.py --pack <pack-dir> [--dest <dir>] [--apply]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path


def find_inner_theme(pack: Path) -> Path:
    """The single ``slidev-theme-*`` subdirectory of ``pack`` (error otherwise)."""
    pack = Path(pack).expanduser()
    if not pack.is_dir():
        sys.exit(f"ERROR: pack path is not a directory: {pack}")
    candidates = sorted(p for p in pack.glob("slidev-theme-*") if p.is_dir())
    if not candidates:
        sys.exit(f"ERROR: no slidev-theme-*/ folder found under {pack}")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        sys.exit(f"ERROR: multiple slidev-theme-*/ folders under {pack} ({names}); "
                 "pass the inner theme directly to /init-deck instead")
    return candidates[0]


def flatten(pack: Path, dest: Path, *, apply: bool = False) -> dict:
    """Plan (and optionally perform) a copy-based flatten. Never deletes originals."""
    pack = Path(pack).expanduser()
    inner = find_inner_theme(pack)
    dest = Path(dest).expanduser() if dest else pack.parent / inner.name

    carried: list[str] = []
    pack_styleguide = pack / "styleguide.md"
    inner_styleguide = inner / "styleguide.md"
    if pack_styleguide.is_file() and not inner_styleguide.is_file():
        carried.append("styleguide.md")

    dead = [name for name in ("skeletons", "pack.json") if (pack / name).exists()]

    plan = {
        "inner": str(inner),
        "dest": str(dest),
        "carried": carried,      # pack-root files carried into the flattened theme
        "dead": dead,            # pack cruft left in place for manual deletion
        "applied": False,
    }
    if not apply:
        return plan

    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"ERROR: destination {dest} exists and is not empty — refusing to clobber")
    shutil.copytree(inner, dest, dirs_exist_ok=True)
    if "styleguide.md" in carried:
        shutil.copyfile(pack_styleguide, dest / "styleguide.md")
    plan["applied"] = True
    return plan


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", required=True, help="the old <slug>-theme-pack/ directory")
    ap.add_argument("--dest", default=None,
                    help="where to write the standalone theme (default: sibling of the pack)")
    ap.add_argument("--apply", action="store_true",
                    help="perform the copy (default: dry-run — plan only, nothing written)")
    a = ap.parse_args()
    plan = flatten(Path(a.pack), Path(a.dest) if a.dest else None, apply=a.apply)
    if not plan["applied"]:
        plan["note"] = "dry-run — nothing written; re-run with --apply to copy"
    print(json.dumps(plan, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
