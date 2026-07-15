# -*- coding: utf-8 -*-
"""Split a monolithic slides.md into per-slide files + a src-import manifest.

Migration tool for workflow-design.md decision 8 (per-slide files). Produces:

    <deck>/slides/<descriptive-name>.md    one file per slide (own frontmatter, verbatim content)
    <deck>/slides.md                       ordered manifest: first entry carries deck frontmatter
                                           (theme/title/...) + src; later entries are src-only

Safety: the original slides.md is backed up to <deck>/.slidecraft/history/, and the split is
verified by re-parsing the outputs and comparing every slide's content byte-for-byte plus every
frontmatter key/value against the original. Exits non-zero if verification fails.

Usage:
    python -m slidecraft.scripts.split_deck --deck <deck-dir> [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys
import time

# Frontmatter keys that belong to the DECK (go to the manifest's first entry),
# not to an individual slide file.
DECK_KEYS = ("theme", "title", "titleTemplate", "author", "info", "download",
             "exportFilename", "highlighter", "lineNumbers", "colorSchema",
             "aspectRatio", "canvasWidth", "favicon", "fonts", "css", "mdc")

# Fixed names for scaffold slides recognizable by layout.
LAYOUT_NAMES = {
    "slide1": "title",
    "agenda": "agenda",
    "slide3": "divider",
    "slide9": "thank-you",
}


def parse_monolith(text: str):
    """Parse slides.md into [(frontmatter_lines, content_str), ...].

    A separator is a line '---' whose next line looks like a frontmatter key
    ('key: ...'). Anything else stays content. Conservative: refuses files it
    cannot account for byte-by-byte.
    """
    lines = text.split("\n")
    n = len(lines)
    if not lines or lines[0].strip() != "---":
        raise SystemExit("slides.md does not start with '---' frontmatter")

    key_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")
    blocks = []
    i = 0
    while i < n:
        assert lines[i].strip() == "---", f"expected '---' at line {i+1}"
        # collect frontmatter until closing ---
        j = i + 1
        fm = []
        while j < n and lines[j].strip() != "---":
            fm.append(lines[j])
            j += 1
        if j >= n:
            raise SystemExit(f"unterminated frontmatter starting line {i+1}")
        # content until next separator ('---' followed by a key line)
        k = j + 1
        content_start = k
        while k < n:
            if lines[k].strip() == "---" and k + 1 < n and key_re.match(lines[k + 1] or ""):
                break
            k += 1
        content = "\n".join(lines[content_start:k])
        blocks.append((fm, content))
        i = k
    return blocks


def fm_get(fm_lines, key):
    for ln in fm_lines:
        m = re.match(rf"^{re.escape(key)}\s*:\s*(.*)$", ln)
        if m:
            return m.group(1).strip()
    return None


def slug_for(fm_lines, content, used):
    layout = fm_get(fm_lines, "layout") or "default"
    base = LAYOUT_NAMES.get(layout)
    if base is None:
        m = re.search(r"^::title::\s*\n(.+)$", content, re.MULTILINE)
        raw = m.group(1).strip() if m else layout
        base = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")[:48] or layout
    slug = base
    idx = 2
    while slug in used:
        slug = f"{base}-{idx}"
        idx += 1
    used.add(slug)
    return slug


def split(deck: str, dry_run: bool = False) -> int:
    slides_path = os.path.join(deck, "slides.md")
    original = io.open(slides_path, encoding="utf-8").read()
    blocks = parse_monolith(original)

    # account for every byte: rebuild and compare
    rebuilt = "\n".join(
        "---\n" + "\n".join(fm) + "\n---\n" + content
        for fm, content in blocks
    ).replace("\n---\n", "\n---\n")  # no-op; kept for clarity
    joined = ""
    for idx, (fm, content) in enumerate(blocks):
        joined += "---\n" + "\n".join(fm) + "\n---\n" + content
        if idx < len(blocks) - 1:
            joined += "\n"
    if joined != original:
        raise SystemExit("parse is not byte-faithful to the original; aborting (nothing written)")

    used = set()
    slides = []  # (slug, slide_fm_lines, content)
    deck_fm = []  # deck-level lines from block 0
    for idx, (fm, content) in enumerate(blocks):
        slide_fm = []
        for ln in fm:
            key = ln.split(":", 1)[0].strip() if ":" in ln else ""
            if idx == 0 and key in DECK_KEYS:
                deck_fm.append(ln)
            else:
                slide_fm.append(ln)
        slug = slug_for(fm, content, used)
        slides.append((slug, slide_fm, content))

    print(f"parsed {len(slides)} slides; deck keys: {[l.split(':')[0] for l in deck_fm]}")
    for slug, fm, _ in slides:
        print(f"  {slug:32s} [{fm_get(fm, 'layout') or 'default'}]")
    if dry_run:
        return 0

    # backup
    hist = os.path.join(deck, ".slidecraft", "history")
    os.makedirs(hist, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(slides_path, os.path.join(hist, f"slides-monolith-{stamp}.md"))

    # write slide files
    outdir = os.path.join(deck, "slides")
    os.makedirs(outdir, exist_ok=True)
    for slug, fm, content in slides:
        body = "---\n" + "\n".join(fm) + "\n---\n" + content
        if not body.endswith("\n"):
            body += "\n"
        io.open(os.path.join(outdir, f"{slug}.md"), "w", encoding="utf-8", newline="\n").write(body)

    # write manifest
    first_slug = slides[0][0]
    parts = ["---\n" + "\n".join(deck_fm) + f"\nsrc: ./slides/{first_slug}.md\n---\n"]
    for slug, _, _ in slides[1:]:
        parts.append(f"---\nsrc: ./slides/{slug}.md\n---\n")
    io.open(slides_path, "w", encoding="utf-8", newline="\n").write("\n".join(parts))

    # ---- verification: re-parse outputs, compare against original blocks ----
    errors = []
    for i, (slug, fm, content) in enumerate(slides):
        written = io.open(os.path.join(outdir, f"{slug}.md"), encoding="utf-8").read()
        wblocks = parse_monolith(written)
        if len(wblocks) != 1:
            errors.append(f"{slug}: file parses into {len(wblocks)} blocks, expected 1")
            continue
        wfm, wcontent = wblocks[0]
        if wcontent.rstrip("\n") != content.rstrip("\n"):
            errors.append(f"{slug}: content mismatch")
        orig_keys = {ln.split(':', 1)[0].strip(): ln for ln in blocks[i][0]}
        new_keys = {ln.split(':', 1)[0].strip(): ln for ln in list(wfm) + (deck_fm if i == 0 else [])}
        for k, ln in orig_keys.items():
            if k not in new_keys or new_keys[k].strip() != ln.strip():
                errors.append(f"{slug}: frontmatter key '{k}' lost or changed")
    if errors:
        print("VERIFICATION FAILED:")
        for e in errors:
            print("  -", e)
        print(f"original preserved at .slidecraft/history/slides-monolith-{stamp}.md")
        return 1
    print(f"OK: {len(slides)} slide files + manifest written; round-trip verified; "
          f"backup at .slidecraft/history/slides-monolith-{stamp}.md")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(split(a.deck, a.dry_run))


if __name__ == "__main__":
    main()
