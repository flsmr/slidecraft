# -*- coding: utf-8 -*-
"""Append entries from a publisher RIS export to the deck's references.bib.

Academic sources should be IMPORTED, not transcribed (bibtex-guide.md rule 1):
download the RIS from the publisher / DOI resolver, then run

    python -m slidecraft.scripts.import_ris --deck <deck-dir> --ris <file.ris>

Field data comes verbatim from the RIS, so the metadata is as correct as the
publisher's own export. Prints the generated cite key(s) for use in slides.

Requires ``rispy`` (pip install rispy) — fails with that instruction if absent.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RIS_TYPE_TO_BIBTEX = {
    "JOUR": "article", "EJOUR": "article", "MGZN": "article",
    "BOOK": "book", "EBOOK": "book", "EDBOOK": "book",
    "CHAP": "incollection", "CONF": "inproceedings", "CPAPER": "inproceedings",
    "RPRT": "techreport", "THES": "phdthesis", "STAND": "misc",
    "ELEC": "online", "WEB": "online", "GEN": "misc",
}


def slug_key(entry: dict, existing: set[str]) -> str:
    authors = entry.get("authors") or entry.get("first_authors") or []
    surname = (authors[0].split(",")[0] if authors else
               entry.get("title", "anon").split()[0])
    year = str(entry.get("year") or entry.get("publication_year") or "n.d.")
    year = re.sub(r"[^0-9]", "", year)[:4] or "nd"
    base = re.sub(r"[^a-z0-9]", "", surname.lower()) + year
    key, i = base, 0
    while key in existing:
        key, i = f"{base}{chr(97 + i)}", i + 1  # martin2022a, martin2022b, ...
    return key


def to_bibtex(entry: dict, key: str) -> str:
    btype = RIS_TYPE_TO_BIBTEX.get(entry.get("type_of_reference", "GEN"), "misc")
    f: dict[str, str] = {}
    authors = entry.get("authors") or entry.get("first_authors") or []
    if authors:
        f["author"] = " and ".join(authors)
    for ris, bib in [("title", "title"), ("primary_title", "title"),
                     ("secondary_title", "journal" if btype == "article" else "booktitle"),
                     ("year", "year"), ("publication_year", "year"),
                     ("volume", "volume"), ("number", "number"),
                     ("publisher", "publisher"), ("doi", "doi"),
                     ("url", "url"), ("issn", "issn"), ("isbn", "isbn"),
                     ("edition", "edition"), ("place_published", "address")]:
        v = entry.get(ris)
        if v and bib not in f:
            f[bib] = str(v).strip()
    sp, ep = entry.get("start_page"), entry.get("end_page")
    if sp:
        f["pages"] = f"{sp}--{ep}" if ep else str(sp)
    if "year" in f:
        f["year"] = re.sub(r"[^0-9]", "", f["year"])[:4]
    body = "".join(f"  {k:<12} = {{{v}}},\n" for k, v in f.items())
    return f"@{btype}{{{key},\n{body}}}\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, type=Path)
    ap.add_argument("--ris", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        import rispy
    except ImportError:
        print("rispy is required: pip install rispy")
        return 1
    bib = a.deck / "references.bib"
    existing_text = bib.read_text(encoding="utf-8") if bib.is_file() else ""
    existing_keys = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", existing_text))

    with open(a.ris, encoding="utf-8-sig") as fh:
        entries = rispy.load(fh)
    if not entries:
        print("no entries found in", a.ris)
        return 1
    added = []
    out = existing_text
    if out and not out.endswith("\n"):
        out += "\n"
    for e in entries:
        key = slug_key(e, existing_keys)
        existing_keys.add(key)
        out += "\n" + to_bibtex(e, key)
        added.append(key)
    bib.write_text(out, encoding="utf-8", newline="\n")
    print("appended", len(added), "entr(y/ies) to", bib)
    for k in added:
        print("  cite as: [@" + k + "]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
