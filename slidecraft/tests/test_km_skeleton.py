"""Rich skeletons (2026-07-22 live-drafting-preview): a created-but-uncomposed
slide shows the distilled nugget information + a 'drafting' banner, and still
trips needs_composition(). digest_body keeps byte-identical output via the
shared nugget_info_section helper."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.conftest import deck  # noqa: F401  (pytest fixture)


def _seed_nugget(deck: Path, nid: str, title: str, info: str,
                 raw: str = "verbatim source line") -> str:
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps({
        "nugget_id": nid, "kind": "text", "title": title,
        "information": info, "raw_text": raw, "source": "chapter_4.md",
        "page": 1,
    }), encoding="utf-8")
    return nid


def test_skeleton_shows_banner_and_info_and_trips_needs_composition(deck):
    n1 = _seed_nugget(deck, "n-1", "Tracking", "- estimates object state")
    body = km.skeleton(deck, "Core idea", [n1])
    assert km.needs_composition(body) is True          # marker preserved
    assert "Composer is drafting" in body              # visible banner
    assert "estimates object state" in body            # distilled info shown
    assert km.DIGEST_MARK not in body                  # NOT a parked digest
    assert body.lstrip().startswith("---")             # valid Slidev frontmatter


def test_skeleton_with_no_nuggets_is_still_a_valid_placeholder(deck):
    body = km.skeleton(deck, "Cover", [])
    assert km.needs_composition(body) is True
    assert "# Cover" in body


def test_nugget_info_section_is_the_shared_source_of_truth(deck):
    n1 = _seed_nugget(deck, "n-1", "A", "- alpha")
    n2 = _seed_nugget(deck, "n-2", "B", "- beta")
    section = km.nugget_info_section(deck, "T", [n1, n2])
    # digest_body embeds the same section verbatim.
    assert section in km.digest_body(deck, "T", [n1, n2])
    assert "alpha" in section and "beta" in section
    assert "## A" in section and "## B" in section     # subtitles when multi
