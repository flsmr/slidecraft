"""Ticket 16 — composer semantic slice, tested at the pre-agreed seams.

Seam 1 (km CLI): ``compose-brief`` field routing per slide type (D42 —
``raw_text`` + ``source``/``page`` where owed; ``information`` and
``visible_text`` never; image-only carries ``context_text`` + the
headline-only instruction; structural carries metadata + defaults only; the
LLM never sees a physical slot name), the unified composer template, and
``write-slide`` (semantic role-keyed JSON → physical Slidev markdown:
roles map, defaults, asset/layout validation, D39 notes fill, concept_type
stamped, FIGURE NEEDED marker; structured rejections).

Seam 2 (invoke shim, fake executor): cap-2 exhaustion resolves to the
composer's park terminal; the parked slide is visibly flagged.
"""
from __future__ import annotations

import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import invoke_shim, km
from slidecraft.tests.conftest import wire_fake_executor
from slidecraft.tests.test_km_plan import (_add_nugget, _create, _set_state,
                                           _state)

PHYSICAL_SLOTS = ("body-26", "body-12", "heading", "body-1", "body-2",
                  "col-a", "col-b", "fig-1", "fig-2")


def _compose_brief(deck: Path, sid: str, out: Path) -> str:
    km.cmd_compose_brief(deck, Namespace(slide=sid, out=str(out)))
    return out.read_text(encoding="utf-8")


def _write_slide(deck: Path, sid: str, payload: dict, tmp_path: Path):
    f = tmp_path / "composer-out.json"
    f.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    km.cmd_write_slide(deck, Namespace(slide=sid, file=str(f)))


def _slide_md(deck: Path, sid: str) -> str:
    return (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")


def _add_asset(deck: Path, name: str = "fig1.png"):
    (deck / "public" / "extracted" / name).write_bytes(b"\x89PNG fake")


# ---------------------------------------------------------------------------
# compose-brief — field routing per slide type (seam 1)
# ---------------------------------------------------------------------------

def test_text_only_brief_routes_raw_text_and_citations(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="First verbatim passage.", page=2)
    _add_nugget(deck, "n2", raw_text="Second verbatim passage.", page=5)
    sid = _create(deck, "Definitions", nuggets="n1,n2",
                  intended_function="define")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # Verbatim raw knowledge + citation locators, per nugget.
    assert "First verbatim passage." in brief
    assert "Second verbatim passage." in brief
    assert "chapter_4.md" in brief and "p. 2" in brief and "p. 5" in brief
    # The digest and the miner's title never reach the composer (D42).
    assert "digest bullet" not in brief
    # The hint from the plan is offered, not imposed.
    assert "define" in brief
    # Layout capabilities ride along by ROLE — never physical slot names.
    assert "image-split" in brief and "two-cols" in brief
    for slot in PHYSICAL_SLOTS:
        assert slot not in brief, f"brief leaks physical slot {slot!r}"
    assert not re.search(r"%[A-Z][A-Z-]*%", brief)
    for needle in ("km.py", "--deck", "python ", "set-content"):
        assert needle not in brief, f"brief leaks {needle!r}"


def test_image_text_brief_places_figure_composes_from_text(deck, tmp_path,
                                                           capsys):
    _add_nugget(deck, "n1", raw_text="Supporting text passage.", page=3)
    _add_nugget(deck, "img1", kind="image", page=4)
    sid = _create(deck, "Figure with text", nuggets="n1,img1")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    assert "Supporting text passage." in brief          # co-nugget raw_text
    assert "/extracted/fig1.png" in brief               # image asset
    assert "A chart described for img1." in brief       # image description
    assert "p. 3" in brief and "p. 4" in brief          # both citations
    # Body from the text nuggets only; the figure is placed, never retold.
    assert "text excerpts" in brief
    # The image's label dump and digest stay out (D42).
    assert "Axis label" not in brief                    # visible_text
    assert "digest bullet" not in brief                 # information
    assert "Nearest caption text block." not in brief   # context_text


def test_image_only_brief_headline_only_with_context(deck, tmp_path, capsys):
    _add_nugget(deck, "img1", kind="image", page=4)
    sid = _create(deck, "The figure", nuggets="img1")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    assert "/extracted/fig1.png" in brief
    assert "A chart described for img1." in brief
    assert "Nearest caption text block." in brief       # context_text (D42)
    assert "chapter_4.md" in brief and "p. 4" in brief  # citation locator
    assert "HEADLINE ONLY" in brief.upper()             # the instruction
    assert "no body text" in brief.lower()
    assert "Axis label" not in brief                    # never visible_text


def test_structural_brief_carries_metadata_and_defaults_only(deck, tmp_path,
                                                             capsys):
    _add_nugget(deck, "n1", raw_text="Content passage.")
    sid = _create(deck, "Cover")                        # no nuggets
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    assert "structural" in brief
    # Deck metadata for the cover/closing slots…
    assert "Dr. Jane Roe" in brief and "IU" in brief
    assert "DLMAIE02" in brief and "2026-07-19" in brief
    # …plus layout defaults ("Thank you" from the closing layout).
    assert "Thank you" in brief
    # And no source material at all — not even other slides' raw text.
    assert "Content passage." not in brief
    assert "Raw source material" not in brief


# ---------------------------------------------------------------------------
# Unified composer template (seam 1)
# ---------------------------------------------------------------------------

def test_unified_composer_template_craft_kept_mechanics_removed():
    tpl = (km.AGENTS_DIR / "slide-composer.md").read_text(encoding="utf-8")
    # Dead mechanics gone: no script calls, disk reads, or physical slots.
    for needle in ("set-content", "km.py", "%KM%", "%DECK-ROOT%", "%SKILL%",
                   "%SLIDE-ID%", "::body", "python", "tempfile", "Read "):
        assert needle not in tpl, f"composer template still has {needle!r}"
    # The craft survived the merge…
    assert "30–55" in tpl                       # density budget
    assert "assertion" in tpl.lower()           # assertion titles
    assert "visual type" in tpl.lower()         # visual-type-first
    assert "provenance" in tpl.lower()          # the one rule
    # …and the output contract is stated in the template.
    for field in ('"layout"', '"concept_type"', '"content"', '"image"',
                  '"figure_needed"', '"notes"'):
        assert field in tpl, f"output contract misses {field}"


# ---------------------------------------------------------------------------
# write-slide — semantic JSON → physical Slidev markdown (seam 1)
# ---------------------------------------------------------------------------

def test_write_slide_maps_roles_to_physical_slots_and_stamps_concept(
        deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="The verbatim backing passage.")
    sid = _create(deck, "Definitions", nuggets="n1")
    capsys.readouterr()

    _write_slide(deck, sid, {
        "layout": "content",
        "concept_type": "define",
        "content": {"title": "Tracking estimates object state",
                    "body": "- one bullet\n- another bullet"},
        "notes": "",
    }, tmp_path)

    md = _slide_md(deck, sid)
    assert "layout: content" in md
    assert "::heading::" in md and "::body-1::" in md   # physical names
    assert "::title::" not in md and "::body::" not in md
    assert "Tracking estimates object state" in md
    # D39: empty notes filled verbatim from the nugget's raw knowledge.
    assert "The verbatim backing passage." in md
    assert md.rstrip().endswith("-->")
    # State: composed + concept_type stamped.
    stj = _state(deck, sid)
    assert stj["state"] == "composed"
    assert stj["concept_type"] == "define"
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True and out["notes_added"] is True


def test_write_slide_structural_uses_defaults_and_own_notes(deck, tmp_path,
                                                            capsys):
    sid = _create(deck, "Closing")
    capsys.readouterr()

    _write_slide(deck, sid, {
        "layout": "closing",
        "concept_type": "structural",
        "content": {},                       # empty → defaults apply
        "notes": "Thank the guest lecturer.",
    }, tmp_path)

    md = _slide_md(deck, sid)
    assert "::body-26::" in md and "Thank you" in md    # default applied
    assert "Thank the guest lecturer." in md            # authored notes kept
    assert _state(deck, sid)["concept_type"] == "structural"


def test_write_slide_places_image_in_image_slot(deck, tmp_path, capsys):
    _add_asset(deck)
    _add_nugget(deck, "n1", raw_text="Text beside the figure.")
    _add_nugget(deck, "img1", kind="image")
    sid = _create(deck, "Figure with text", nuggets="n1,img1")
    capsys.readouterr()

    _write_slide(deck, sid, {
        "layout": "image-split",
        "concept_type": "finding",
        "content": {"title": "The curve rises",
                    "body": "- evidence bullet"},
        "image": {"asset": "/extracted/fig1.png", "alt": "Rising curve"},
    }, tmp_path)

    md = _slide_md(deck, sid)
    assert "layout: media" in md                        # physical layout name
    assert "::fig-2::" in md
    assert '<img src="/extracted/fig1.png" alt="Rising curve">' in md


def test_write_slide_renders_figure_needed_marker(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Needs a figure", nuggets="n1")
    capsys.readouterr()

    _write_slide(deck, sid, {
        "layout": "content",
        "concept_type": "process",
        "content": {"title": "T", "body": "- b"},
        "figure_needed": "flow diagram of the tracking loop",
    }, tmp_path)

    md = _slide_md(deck, sid)
    assert "<!-- FIGURE NEEDED: flow diagram of the tracking loop -->" in md
    # The notes fill still lands after the marker (marker is not notes).
    assert md.rstrip().endswith("-->")
    assert "A passage." in md


@pytest.mark.parametrize("payload, fragment", [
    ({"layout": "nope", "concept_type": "define",
      "content": {"title": "T"}}, "layout"),
    ({"layout": "content", "concept_type": "poetry",
      "content": {"title": "T"}}, "concept_type"),
    ({"layout": "content", "concept_type": "define",
      "content": {"sidebar": "X"}}, "sidebar"),
    ({"layout": "image-split", "concept_type": "define",
      "content": {"title": "T"},
      "image": {"asset": "/extracted/ghost.png", "alt": ""}}, "ghost.png"),
    ({"layout": "content", "concept_type": "define",
      "content": {"title": "T"},
      "image": {"asset": "/extracted/fig1.png", "alt": ""}}, "image slot"),
])
def test_write_slide_rejects_bad_payloads(deck, tmp_path, capsys, payload,
                                          fragment):
    _add_asset(deck)
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Slide", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as ei:
        _write_slide(deck, sid, payload, tmp_path)
    assert fragment in str(ei.value)
    assert _state(deck, sid)["state"] == "draft"        # untouched


def test_write_slide_rejects_malformed_json(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Slide", nuggets="n1")
    capsys.readouterr()
    f = tmp_path / "broken.json"
    f.write_text("this is { not json", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        km.cmd_write_slide(deck, Namespace(slide=sid, file=str(f)))
    assert "JSON" in str(ei.value)


# ---------------------------------------------------------------------------
# Cap-2 exhaustion parks + flags the slide (seam 2)
# ---------------------------------------------------------------------------

def test_compose_step_cap2_parks_and_flags(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Doomed slide", nuggets="n1")
    bad = json.dumps({"layout": "nope", "concept_type": "define",
                      "content": {"title": "T"}})
    respdir = wire_fake_executor(deck, tmp_path, "slide-composer", [bad])
    capsys.readouterr()

    brief = tmp_path / "brief.md"
    km.cmd_compose_brief(deck, Namespace(slide=sid, out=str(brief)))
    result = tmp_path / "invoke-result.json"
    rc = invoke_shim.main([
        "--role", "slide-composer", "--brief-file", str(brief),
        "--deck", str(deck), "--out", str(result), "--",
        sys.executable, str(Path(km.__file__)), "--deck", str(deck),
        "write-slide", "--slide", sid, "--file", "{out}",
    ])

    assert rc == 3
    res = json.loads(result.read_text(encoding="utf-8"))
    assert res["status"] == "exhausted"
    assert res["terminal"] == "park"                    # composer terminal
    assert (respdir / "count").read_text() == "3"
    assert _state(deck, sid)["state"] == "draft"        # body untouched

    # The orchestrator resolves the terminal: park + flag, deck stays valid.
    capsys.readouterr()
    km.cmd_park(deck, Namespace(
        slide=sid, reason="composition failed after 3 attempts"))
    stj = _state(deck, sid)
    assert stj["state"] == "parked"
    assert "composition failed" in stj["parked_reason"]
    capsys.readouterr()
    km.cmd_validate(deck, Namespace())
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
    assert out["parked"] == [sid]
