"""Ticket 15 — storyteller planner slice, tested at the pre-agreed seams.

Seam 1 (km CLI): the D34 park mechanics (park/unpark/create --parked, the
active-only budget gate), ``plan-brief`` field routing (every nugget's digest
fields, provably no ``raw_text``/``visible_text``/asset paths, deck state
incl. the parked block on a re-run), the planner-only storyteller template,
and ``write-plan``'s deterministic validation (nugget ids, decision types,
budget arithmetic, ``intended_function`` enum, locked slides untouchable).

Seam 2 (invoke shim, fake executor): cap-2 exhaustion on plan validation
aborts the run with a flagged error and composes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import invoke_shim, km


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_nugget(deck: Path, nid: str, kind: str = "text", **over) -> str:
    n = {"nugget_id": nid, "kind": kind, "source": "chapter_4.md", "page": 1,
         "title": f"Topic {nid}", "information": f"- digest bullet for {nid}"}
    if kind == "text":
        n["raw_text"] = f"Verbatim passage backing {nid}."
    else:
        n.update({"figure_type": "chart",
                  "visible_text": ["Axis label", "Series name"],
                  "description": f"A chart described for {nid}.",
                  "asset": "/extracted/fig1.png",
                  "context_text": "Nearest caption text block."})
    n.update(over)
    (deck / "nuggets" / f"{nid}.json").write_text(
        json.dumps(n, ensure_ascii=False), encoding="utf-8")
    return nid


def _create(deck: Path, title: str, nuggets: str = "", **kw) -> str:
    km.cmd_create(deck, Namespace(title=title, nuggets=nuggets,
                                  after="end", **kw))
    assoc = json.loads((deck / "associations.json").read_text(encoding="utf-8"))
    want = [n for n in nuggets.split(",") if n]
    matches = [sid for sid, nugs in assoc.items() if nugs == want]
    return matches[-1]


def _state(deck: Path, sid: str) -> dict:
    return json.loads((deck / "slides" / f"{sid}.json")
                      .read_text(encoding="utf-8"))


def _set_state(deck: Path, sid: str, state: str):
    stj = _state(deck, sid)
    stj["state"] = state
    (deck / "slides" / f"{sid}.json").write_text(
        json.dumps(stj, indent=2), encoding="utf-8")


def _plan_brief(deck: Path, out: Path) -> str:
    km.cmd_plan_brief(deck, Namespace(out=str(out)))
    return out.read_text(encoding="utf-8")


def _write_plan(deck: Path, plan: dict, tmp_path: Path):
    f = tmp_path / "plan-in.json"
    f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    km.cmd_write_plan(deck, Namespace(file=str(f)))


# ---------------------------------------------------------------------------
# Park mechanics (D34)
# ---------------------------------------------------------------------------

def test_park_moves_include_to_parked_block_and_frees_budget(deck, capsys):
    for i in range(6):                      # budget (6) full
        _create(deck, f"Slide {i}")
    victims = km.order(deck)
    with pytest.raises(SystemExit):         # gate closed
        _create(deck, "Overflow")
    capsys.readouterr()

    km.cmd_park(deck, Namespace(slide=victims[0], reason="off-storyline"))

    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert victims[0] not in km.order(deck)          # out of the active order
    assert "<!-- parked" in md and victims[0] in md  # …but still referenced
    stj = _state(deck, victims[0])
    assert stj["state"] == "parked"
    assert stj["parked_reason"] == "off-storyline"
    capsys.readouterr()
    _create(deck, "Newcomer")                        # slot freed
    assert len(km.order(deck)) == 6


def test_park_refuses_locked_slide(deck, capsys):
    sid = _create(deck, "User slide")
    _set_state(deck, sid, "locked")
    with pytest.raises(SystemExit) as ei:
        km.cmd_park(deck, Namespace(slide=sid, reason=""))
    assert "locked" in str(ei.value)


def test_unpark_restores_state_and_needs_free_slot(deck, capsys):
    a = _create(deck, "A")
    _set_state(deck, a, "composed")
    km.cmd_park(deck, Namespace(slide=a, reason="make room"))
    for i in range(6):
        _create(deck, f"Fill {i}")
    capsys.readouterr()

    with pytest.raises(SystemExit):          # no free active slot
        km.cmd_unpark(deck, Namespace(slide=a))
    assert json.loads(capsys.readouterr().out.strip())["error"] == "budget_full"

    fills = km.order(deck)
    km.cmd_park(deck, Namespace(slide=fills[0], reason=""))
    km.cmd_unpark(deck, Namespace(slide=a))

    assert a in km.order(deck)
    assert _state(deck, a)["state"] == "composed"    # pre-park state restored
    assert "parked_reason" not in _state(deck, a)


def test_create_parked_uses_no_active_slot(deck, capsys):
    for i in range(6):
        _create(deck, f"Fill {i}")
    capsys.readouterr()
    sid = _create(deck, "Triage", parked=True)
    assert _state(deck, sid)["state"] == "parked"
    assert sid not in km.order(deck)
    assert sid in (deck / "slides.md").read_text(encoding="utf-8")


def test_validate_green_with_parked_and_reports_them(deck, capsys):
    a = _create(deck, "A")
    _create(deck, "B")
    km.cmd_park(deck, Namespace(slide=a, reason="r"))
    capsys.readouterr()
    km.cmd_validate(deck, Namespace())
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
    assert out["parked"] == [a]
    assert out["slides"] == 1               # active only


# ---------------------------------------------------------------------------
# plan-brief — field routing (seam 1)
# ---------------------------------------------------------------------------

def test_plan_brief_carries_digests_and_constraints(deck, tmp_path, capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")
    _add_nugget(deck, "img1", kind="image")

    brief = _plan_brief(deck, tmp_path / "brief.md")

    for nid in ("n1", "n2", "img1"):
        assert nid in brief
        assert f"- digest bullet for {nid}" in brief      # information digest
        assert f"Topic {nid}" in brief                    # title
    assert "chart" in brief                               # figure_type
    assert "A chart described for img1." in brief         # description
    # Deck constraints injected, no unresolved placeholders.
    assert "Object Tracking" in brief
    assert "6" in brief and "students" in brief and "lecture" in brief
    assert not re.search(r"%[A-Z][A-Z-]*%", brief)
    # Fresh draft → full plan; nothing placed yet.
    assert "fresh draft" in brief and "FULL plan" in brief
    assert "placed: no" in brief


def test_plan_brief_never_leaks_raw_fields_or_assets(deck, tmp_path):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "img1", kind="image")

    brief = _plan_brief(deck, tmp_path / "brief.md")

    assert "Verbatim passage backing n1." not in brief    # raw_text
    assert "Axis label" not in brief                      # visible_text
    assert "/extracted/" not in brief                     # asset path
    assert "fig1.png" not in brief
    assert "Nearest caption text block." not in brief     # context_text
    # No script mechanics either — the planner runs as a pure function.
    for needle in ("km.py", "--deck", "python ", "spawn", "Agent tool"):
        assert needle not in brief, f"brief leaks {needle!r}"
    assert str(deck) not in brief


def test_plan_brief_rerun_lists_deck_state_and_parked_block(deck, tmp_path,
                                                           capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")
    cover = _create(deck, "Cover")
    placed = _create(deck, "Placed topic", nuggets="n1")
    parked = _create(deck, "Side topic", nuggets="n2")
    km.cmd_park(deck, Namespace(slide=parked, reason="off-storyline"))
    capsys.readouterr()

    brief = _plan_brief(deck, tmp_path / "brief.md")

    for sid in (cover, placed, parked):
        assert sid in brief
    assert "off-storyline" in brief                       # parked block + reason
    assert "DELTA plan" in brief                          # re-run wording
    # Both nuggets are placed on slides — the digests must say so.
    assert "placed:" in brief and "placed: no" not in brief


def test_plan_brief_inlines_storytelling_skill_when_present(deck, tmp_path,
                                                            monkeypatch):
    skills = tmp_path / "skills" / "academic-storytelling"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: academic-storytelling\n---\n\nOpen with a question.",
        encoding="utf-8")
    monkeypatch.setattr(km, "SKILLS_DIR", tmp_path / "skills")

    brief = _plan_brief(deck, tmp_path / "brief.md")
    assert "Open with a question." in brief


# ---------------------------------------------------------------------------
# Storyteller template — planner-only (seam 1)
# ---------------------------------------------------------------------------

def test_storyteller_template_is_planner_only():
    tpl = (km.AGENTS_DIR / "storyteller.md").read_text(encoding="utf-8")
    for needle in ("spawn", "Spawn", "km.py", "%KM%", "%DECK-ROOT%",
                   "%COMPOSER%", "create-slide", "merge-slides",
                   "set-content", "python", "Agent tool", "subagent"):
        assert needle not in tpl, f"storyteller template still has {needle!r}"
    low = tpl.lower()
    assert "locked" in low and "propose" in low            # skip-and-propose
    assert "delta" in low                                  # re-run behavior
    assert "intended_function" in tpl
    assert '"action"' in tpl                               # plan contract shown


# ---------------------------------------------------------------------------
# write-plan — deterministic validation (seam 1)
# ---------------------------------------------------------------------------

def _valid_plan():
    return {"plan": [
        {"action": "create", "structural": True, "title": "Cover"},
        {"action": "create", "title": "Definitions", "nuggets": ["n1"],
         "intended_function": "define"},
        {"action": "create", "title": "Comparison", "nuggets": ["n2"],
         "intended_function": "compare"},
    ], "notes": ""}


def test_write_plan_accepts_valid_plan_and_returns_steps(deck, tmp_path,
                                                         capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")

    _write_plan(deck, _valid_plan(), tmp_path)

    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True
    ops = [s["op"] for s in out["steps"]]
    assert ops == ["create-slide", "create-slide", "create-slide"]
    assert out["steps"][0]["structural"] is True
    assert out["steps"][1]["intended_function"] == "define"
    assert out["steps"][1]["nuggets"] == ["n1"]
    # The accepted plan is recorded on disk.
    recorded = json.loads((deck / "plan.json").read_text(encoding="utf-8"))
    assert recorded["plan"] == _valid_plan()["plan"]


@pytest.mark.parametrize("mutate, fragment", [
    (lambda p: p["plan"][1].__setitem__("nuggets", ["ghost"]), "ghost"),
    (lambda p: p["plan"][1].__setitem__("action", "explode"), "explode"),
    (lambda p: p["plan"][1].__setitem__("intended_function", "poetry"),
     "poetry"),
    (lambda p: p["plan"][0].__setitem__("nuggets", ["n1"]), "structural"),
])
def test_write_plan_rejects_bad_plans_with_structured_errors(deck, tmp_path,
                                                             mutate, fragment):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")
    plan = _valid_plan()
    mutate(plan)
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert fragment in str(ei.value)
    assert not (deck / "plan.json").exists()          # rejected → not recorded


def test_write_plan_rejects_budget_overflow(deck, tmp_path):
    for i in range(7):
        _add_nugget(deck, f"n{i}")
    plan = {"plan": [{"action": "create", "title": f"S{i}",
                      "nuggets": [f"n{i}"]} for i in range(7)]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "budget" in str(ei.value)


def test_write_plan_park_frees_budget_in_simulation(deck, tmp_path, capsys):
    sids = [_create(deck, f"Fill {i}", nuggets="") for i in range(6)]
    _add_nugget(deck, "n1")
    capsys.readouterr()

    overflow = {"plan": [
        {"action": "create", "title": "New", "nuggets": ["n1"]}]}
    with pytest.raises(SystemExit):
        _write_plan(deck, overflow, tmp_path)

    ok = {"plan": [
        {"action": "park", "slide": sids[0], "reason": "least distinct"},
        {"action": "create", "title": "New", "nuggets": ["n1"]}]}
    _write_plan(deck, ok, tmp_path)
    assert json.loads(capsys.readouterr().out.strip())["ok"] is True


def test_write_plan_rejects_touching_locked_slides(deck, tmp_path, capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")
    a = _create(deck, "Locked one", nuggets="n1")
    _set_state(deck, a, "locked")
    capsys.readouterr()
    plan = {"plan": [{"action": "park", "slide": a, "reason": "nope"}]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "locked" in str(ei.value)
    # n2 exists but is unplaced — and that must also be a rejection…
    plan2 = {"plan": []}
    with pytest.raises(SystemExit) as ei2:
        _write_plan(deck, plan2, tmp_path)
    assert "n2" in str(ei2.value) and "unplaced" in str(ei2.value)


def test_write_plan_rejects_merge_of_structural_slides(deck, tmp_path, capsys):
    _add_nugget(deck, "n1")
    cover = _create(deck, "Cover")
    content = _create(deck, "Content", nuggets="n1")
    capsys.readouterr()
    plan = {"plan": [
        {"action": "merge", "slides": [cover, content], "title": "Bad"}]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "structural" in str(ei.value)


# ---------------------------------------------------------------------------
# Cap-2 exhaustion on plan validation aborts the run (seam 2)
# ---------------------------------------------------------------------------

from slidecraft.tests.conftest import wire_fake_executor  # noqa: E402


def test_plan_cap2_exhaustion_aborts_flagged_nothing_composed(deck, tmp_path,
                                                              capsys):
    _add_nugget(deck, "n1")
    bad_plan = json.dumps({"plan": [
        {"action": "create", "title": "X", "nuggets": ["ghost"]}]})
    wire_fake_executor(deck, tmp_path, "storyteller", [bad_plan])

    brief = tmp_path / "brief.md"
    km.cmd_plan_brief(deck, Namespace(out=str(brief)))
    result = tmp_path / "invoke-result.json"
    rc = invoke_shim.main([
        "--role", "storyteller", "--brief-file", str(brief),
        "--deck", str(deck), "--out", str(result), "--",
        sys.executable, str(Path(km.__file__)), "--deck", str(deck),
        "write-plan", "--file", "{out}",
    ])

    assert rc == 3
    res = json.loads(result.read_text(encoding="utf-8"))
    assert res["status"] == "exhausted"
    assert res["terminal"] == "abort"                 # storyteller terminal
    assert res["attempts"] == 3
    assert any("ghost" in e for e in res["errors"])   # flagged error
    # Nothing was composed or created; no plan was recorded.
    assert list((deck / "slides").glob("*")) == []
    assert not (deck / "plan.json").exists()


# ---------------------------------------------------------------------------
# Review fixes: plan simulation retires merged slides; one figure per slide;
# YAML-safe titles; headmatter preservation; persist gates
# ---------------------------------------------------------------------------

def test_write_plan_rejects_reference_to_merged_away_slide(deck, tmp_path,
                                                           capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "n2")
    a = _create(deck, "A", nuggets="n1")
    b = _create(deck, "B", nuggets="n2")
    capsys.readouterr()
    plan = {"plan": [
        {"action": "merge", "slides": [a, b], "title": "AB"},
        {"action": "park", "slide": a, "reason": "freed"}]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "merged away" in str(ei.value)


def test_write_plan_rejects_duplicate_merge_ids(deck, tmp_path, capsys):
    _add_nugget(deck, "n1")
    a = _create(deck, "A", nuggets="n1")
    capsys.readouterr()
    plan = {"plan": [{"action": "merge", "slides": [a, a], "title": "AA"}]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "duplicate" in str(ei.value)


def test_write_plan_rejects_two_figures_on_one_slide(deck, tmp_path):
    _add_nugget(deck, "img1", kind="image")
    _add_nugget(deck, "img2", kind="image")
    plan = {"plan": [
        {"action": "create", "title": "Two figures",
         "nuggets": ["img1", "img2"]}]}
    with pytest.raises(SystemExit) as ei:
        _write_plan(deck, plan, tmp_path)
    assert "ONE image" in str(ei.value)


def test_associate_refuses_second_figure_at_km_level(deck, capsys):
    _add_nugget(deck, "n1")
    _add_nugget(deck, "img1", kind="image")
    _add_nugget(deck, "img2", kind="image")
    sid = _create(deck, "Figure slide", nuggets="n1,img1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as ei:
        km.cmd_associate(deck, Namespace(slide=sid, nuggets="img2"))
    assert "ONE figure" in str(ei.value)


def test_colon_title_is_yaml_quoted_in_skeleton(deck, capsys):
    sid = _create(deck, "Definition: Objekt-Tracking")
    md = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")
    assert 'title: "Definition: Objekt-Tracking"' in md


def test_write_order_preserves_user_headmatter_keys(deck, capsys):
    _create(deck, "First")
    md_path = deck / "slides.md"
    text = md_path.read_text(encoding="utf-8")
    # User hand-adds a headmatter key…
    text = text.replace("---\ntheme:", "---\nfonts: my-font\ntheme:", 1)
    md_path.write_text(text, encoding="utf-8")
    _create(deck, "Second")
    after = md_path.read_text(encoding="utf-8")
    assert "fonts: my-font" in after            # …and it survives a rewrite
    assert after.count("theme:") == 1


def test_write_plan_missing_file_is_a_gate_not_a_retry(deck):
    with pytest.raises(SystemExit) as ei:
        km.cmd_write_plan(deck, Namespace(file=str(deck / "nope.json")))
    assert ei.value.code == 2                   # shim gate, no LLM retries
