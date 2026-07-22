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
# compose-brief — planner brief assembly (seam 1)
# ---------------------------------------------------------------------------

def test_planner_brief_routes_raw_material_and_no_physical_slots(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="First verbatim passage.", page=2)
    _add_nugget(deck, "n2", raw_text="Second verbatim passage.", page=5)
    sid = _create(deck, "Definitions", nuggets="n1,n2", intended_function="define")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # Verbatim raw material reaches the planner (it routes from it).
    assert "First verbatim passage." in brief
    assert "Second verbatim passage." in brief
    # The plan contract + section types are described.
    assert "sections" in brief
    assert "source-image" in brief and "diagram" in brief
    # The hint is offered.
    assert "define" in brief
    # Content layouts advertised by ROLE; never a physical slot; no leftover.
    assert "content" in brief and "two-cols" in brief
    for slot in PHYSICAL_SLOTS:
        assert slot not in brief, f"planner brief leaks physical slot {slot!r}"
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)
    for needle in ("km.py", "--deck", "python ", "write-skeleton"):
        assert needle not in brief


def test_planner_brief_offers_only_d4_scope_layouts(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Definitions", nuggets="n1")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # Isolate the layout-advertisement lines planner_layouts_section emits
    # (`- **<name>**`), since "content"/"two-cols" also appear in the
    # template's static prose elsewhere in the brief.
    offered = set(re.findall(r"^- \*\*([a-zA-Z][\w-]*)\*\*", brief, re.MULTILINE))
    assert offered == {"content", "two-cols"}
    for name in ("image-split", "figure", "cover", "closing"):
        assert name not in offered


def test_planner_brief_figure_block_lists_figure_nuggets(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Supporting text passage.", page=3,
                information="DIGEST-ONLY-BULLET-NEVER-PLANNER-FACING")
    _add_nugget(deck, "img1", kind="image", page=4,        # image nugget carries asset
                visible_text=["OCR-ONLY-LABEL-NEVER-PLANNER-FACING"])
    sid = _create(deck, "Figure with text", nuggets="n1,img1")
    capsys.readouterr()

    brief = _compose_brief(deck, sid, tmp_path / "brief.md")

    # The planner is told a real figure is available to PLACE (source-image).
    assert "img1" in brief
    assert "Available figures" in brief or "figure" in brief.lower()
    # The planner routes from raw_text/description only — never the miner's
    # digest (`information`) or an image nugget's OCR `visible_text` labels.
    assert "DIGEST-ONLY-BULLET-NEVER-PLANNER-FACING" not in brief
    assert "OCR-ONLY-LABEL-NEVER-PLANNER-FACING" not in brief


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


# ---------------------------------------------------------------------------
# Review fixes: writer state guards; builtin image-prop layouts; markdown
# asset check; BOM tolerance
# ---------------------------------------------------------------------------

def test_write_slide_gates_on_locked_slide(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "User slide", nuggets="n1")
    _set_state(deck, sid, "locked")
    before = _slide_md(deck, sid)
    capsys.readouterr()
    with pytest.raises(SystemExit) as ei:
        _write_slide(deck, sid, {"layout": "content",
                                 "concept_type": "define",
                                 "content": {"title": "T"}}, tmp_path)
    assert ei.value.code == 2                       # gate, not a retry
    assert _slide_md(deck, sid) == before           # content untouched
    assert _state(deck, sid)["state"] == "locked"   # lock not erased


def test_set_content_refuses_locked_slide(deck, capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "User slide", nuggets="n1")
    _set_state(deck, sid, "locked")
    body_file = deck / "logs" / "body.tmp"
    body_file.write_text("---\nlayout: content\n---\n\nX\n", encoding="utf-8")
    capsys.readouterr()
    with pytest.raises(SystemExit) as ei:
        km.cmd_set_content(deck, Namespace(slide=sid,
                                           body_file=str(body_file)))
    assert "locked" in str(ei.value)


def test_set_content_tolerates_bom_in_body_file(deck, capsys):
    sid = _create(deck, "Intro")
    body_file = deck / "logs" / "body.tmp"
    # utf-8-sig writes the BOM PowerShell 5.1's Out-File would prepend.
    body_file.write_text("---\nlayout: content\n---\n\n# Claim\n",
                         encoding="utf-8-sig")
    capsys.readouterr()
    km.cmd_set_content(deck, Namespace(slide=sid, body_file=str(body_file)))
    assert json.loads(capsys.readouterr().out.strip())["ok"] is True


def test_write_slide_rejects_missing_markdown_image_asset(deck, tmp_path,
                                                          capsys):
    _add_nugget(deck, "n1", raw_text="A passage.")
    sid = _create(deck, "Slide", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as ei:
        _write_slide(deck, sid, {
            "layout": "content", "concept_type": "define",
            "content": {"title": "T",
                        "body": "![diagram](/extracted/ghost.png)"},
        }, tmp_path)
    assert "ghost.png" in str(ei.value)


def _builtin_deck(tmp_path):
    from slidecraft.scripts import scaffold_deck
    from slidecraft.tests.conftest import ANSWERS
    root = tmp_path / "bdeck"
    root.mkdir()
    answers = dict(ANSWERS)
    answers["theme"] = {"type": "builtin", "source": "default"}
    scaffold_deck.scaffold(root, answers)
    return root


def test_write_slide_emits_image_prop_for_builtin_layouts(tmp_path, capsys):
    deck = _builtin_deck(tmp_path)
    _add_asset(deck)
    _add_nugget(deck, "n1", raw_text="Text beside the figure.")
    _add_nugget(deck, "img1", kind="image")
    sid = _create(deck, "Figure right", nuggets="n1,img1")
    capsys.readouterr()

    _write_slide(deck, sid, {
        "layout": "image-right",
        "concept_type": "finding",
        "content": {"title": "The curve rises", "body": "- evidence"},
        "image": {"asset": "/extracted/fig1.png", "alt": "Curve"},
    }, tmp_path)

    md = _slide_md(deck, sid)
    assert "layout: image-right" in md
    # Slidev builtin image layouts take the figure as a frontmatter prop…
    assert 'image: "/extracted/fig1.png"' in md
    # …never as an inline tag crammed into the text column.
    assert "<img" not in md
