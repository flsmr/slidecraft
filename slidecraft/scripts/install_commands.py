"""Regenerate the user-local slidecraft slash-command wrappers.

The active `/slidecraft:<name>` commands are thin *wrapper* files under
`~/.claude/commands/slidecraft/`. Each wrapper delegates to the canonical
instructions in this repo (`slidecraft/commands/<name>.md`), which are read live
at invocation time. Only the *set* of wrappers (and their frontmatter) can drift
from the repo — this script rebuilds them so the installed commands always match
the repo's `commands/` folder.

Idempotent: adds missing wrappers, updates changed ones, prunes wrappers whose
repo command no longer exists, and leaves unchanged ones alone.

    python -m slidecraft.scripts.install_commands            # sync
    python -m slidecraft.scripts.install_commands --dry-run  # show what would change

New commands only load in a fresh Claude Code session.
"""
from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "slidecraft" / "commands"
DEST_DIR = Path.home() / ".claude" / "commands" / "slidecraft"


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Return the top YAML frontmatter as a flat key->value dict (no yaml dep)."""
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
    return out


def _wrapper_for(command_file: Path) -> str:
    """Build the wrapper markdown that delegates to *command_file*."""
    fm = _parse_frontmatter(command_file.read_text(encoding="utf-8"))
    desc = fm.get("description", f"Run the {command_file.stem} command")
    hint = fm.get("argument-hint")

    header = ["---", f"description: {desc}"]
    if hint:
        header.append(f"argument-hint: {hint}")
    header.append("---")

    body = [
        "",
        "Read and follow the canonical command instructions, passing along the arguments:",
        "",
        f"- Instructions: `{command_file}`",
        "- Arguments: $ARGUMENTS",
        "- Plugin root (for relative references and python -m slidecraft.scripts.*, run from here):",
        f"  `{REPO_ROOT}`",
        "",
    ]
    return "\n".join(header + body)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="show changes without writing")
    args = ap.parse_args()

    if not SRC_DIR.is_dir():
        print(f"! no commands dir at {SRC_DIR}")
        return 1

    commands = sorted(SRC_DIR.glob("*.md"))
    stems = {c.stem for c in commands}
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    added, updated, unchanged, pruned = [], [], [], []

    for cmd in commands:
        dest = DEST_DIR / cmd.name
        want = _wrapper_for(cmd)
        have = dest.read_text(encoding="utf-8") if dest.exists() else None
        if have is None:
            added.append(cmd.stem)
        elif have != want:
            updated.append(cmd.stem)
        else:
            unchanged.append(cmd.stem)
            continue
        if not args.dry_run:
            dest.write_text(want, encoding="utf-8")

    for existing in sorted(DEST_DIR.glob("*.md")):
        if existing.stem not in stems:
            pruned.append(existing.stem)
            if not args.dry_run:
                existing.unlink()

    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}slidecraft command wrappers -> {DEST_DIR}")
    print(f"  added:     {', '.join(added) or '-'}")
    print(f"  updated:   {', '.join(updated) or '-'}")
    print(f"  pruned:    {', '.join(pruned) or '-'}")
    print(f"  unchanged: {', '.join(unchanged) or '-'}")
    if added or updated or pruned:
        print("  -> start a new Claude Code session for changes to load.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
