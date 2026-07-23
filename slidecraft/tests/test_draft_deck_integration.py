"""Ticket 17 / Task 14 — /draft-deck orchestrator end-to-end, at the CLI seams.

The v1 orchestrator IS the ``/draft-deck`` command (an LLM lead running the
deterministic scripts); its target form is a Workflow over the same seams. This
test drives that documented phase sequence — convert -> mine (one invoke per
text source + per extracted image) -> plan -> execute-plan (create/associate/
merge/park; NO per-create compose) -> **two-stage compose** (compose_deck: plan
every slide -> write-skeleton -> designers per section -> place) -> validate —
over a fixture deck with a **fake executor** (canned miner / storyteller /
planner / designer outputs), and asserts the deck reaches a green ``validate``.
No test touches a live LLM.

``draft_deck`` below is the test harness that mirrors the command doc: it calls
the real km CLI, the real invoke shim, and the real ``compose_deck`` driver —
only the executor is faked. It also collects the per-role terminals (miner drop,
planner park, storyteller abort, designer failure) into a run report, so the
"flagged, never silent" behavior is asserted at the seam the orchestrator owns.

Two-stage determinism: ``compose_deck`` runs Stage-2 designers concurrently, and
``wire_fake_executor`` replays canned replies by a global per-role counter, so
the reply a section gets depends on designer-call ORDER. The harness passes
``max_workers=1`` to force job order = deck order (to-compose slides) then
section order, and the canned lists are ordered to match; assertions still
prefer "reply present in the right slide's md" over global ordering to stay
robust.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import compose_deck, invoke_shim, km, source_converter
from slidecraft.scripts import draft_deck as dd   # the real driver (A2/A3)
from slidecraft.tests.conftest import wire_fake_executor

KM = str(Path(km.__file__))

# --- fixture inputs -------------------------------------------------------

TEXT_INPUT = "chapter_9.md"
TEXT_SLUG = "chapter-9"
TEXT_BODY = (
    "# Object Tracking\n\n"
    "A tracker estimates the state of a moving object over time from noisy "
    "measurements.\n\n"
    "The Kalman filter fuses a motion model with measurements to reduce "
    "estimation error.\n")

RAW_1 = ("A tracker estimates the state of a moving object over time from "
         "noisy measurements.")
RAW_2 = ("The Kalman filter fuses a motion model with measurements to reduce "
         "estimation error.")

IMG_SLUG = "figures"
IMG_FILE = "figures.pdf"
IMG_ID = "figures-p2-img1"
IMG_PNG = "figures-p2-img1.png"
IMG_ASSET = f"/extracted/{IMG_PNG}"
IMG_VISIBLE = ["Predict", "Update"]

# Delta re-run input.
TEXT2_INPUT = "chapter_10.md"
TEXT2_SLUG = "chapter-10"
TEXT2_BODY = ("Recent trackers use deep neural networks for appearance "
              "modeling.\n")
RAW_3 = "Recent trackers use deep neural networks for appearance modeling."


# --- canned role outputs (a real executor would return these) -------------

def _text_batch(*items) -> str:
    return json.dumps({"nuggets": list(items)})


CH9_MINE = _text_batch(
    {"title": "Tracking estimates object state",
     "information": "- a tracker estimates object state over time",
     "raw_text": RAW_1, "page": 1},
    {"title": "Kalman filter fuses model and measurement",
     "information": "- fuses a motion model with measurements",
     "raw_text": RAW_2, "page": 1})

EMPTY_MINE = _text_batch()   # a source page with no minable text

IMG_MINE = json.dumps({"nuggets": [
    {"title": "The tracking loop", "figure_type": "diagram",
     "information": "- predict then update cycle",
     "visible_text": IMG_VISIBLE,
     "description": "Shows the predict-update cycle of a tracker. A block "
                    "diagram with two boxes."}]})

CH10_MINE = _text_batch(
    {"title": "Deep appearance models",
     "information": "- recent trackers use deep networks",
     "raw_text": RAW_3, "page": 1})


# --- canned two-stage outputs: planner plan-JSON + designer replies --------
#
# Stage-1 (slide-composer / planner) returns ONE plan-JSON per to-compose slide.
# Stage-2 designers return ONE prose/markup reply per pending content section.
# A *structural* slide (empty sections) renders title + layout defaults only —
# write-skeleton promotes it to composed with NO designer call. A *source-image*
# section is PLACED by write-skeleton (the figure asset), also no designer.

def _plan(layout, concept, title, sections) -> str:
    return json.dumps({"layout": layout, "concept_type": concept,
                       "title": title, "sections": sections})


def _plan_structural(title) -> str:
    return _plan("content", "structural", title, {})


def _plan_text(title, nuggets, concept="define", instructions="define it") -> str:
    return _plan("content", concept, title,
                 {"body": {"type": "text", "instructions": instructions,
                           "nuggets": list(nuggets)}})


def _plan_source_image(title, nuggets, concept="process",
                       instructions="place the loop figure") -> str:
    return _plan("content", concept, title,
                 {"body": {"type": "source-image", "instructions": instructions,
                           "nuggets": list(nuggets)}})


# The text-designer's built body for the "Core idea" slide (Stage-2).
DESIGN_CORE_BODY = "- estimate state over time\n- from measurements"


# --- deck fixture seeding -------------------------------------------------

def _seed_inputs(deck: Path):
    """A text input (convert will process it) + a pre-converted image source
    (as if a PDF had already been converted: image record + extracted asset)."""
    (deck / "input" / TEXT_INPUT).write_text(TEXT_BODY, encoding="utf-8")
    (deck / "sources").mkdir(exist_ok=True)
    (deck / "public" / "extracted").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "extracted" / IMG_PNG).write_bytes(b"\x89PNG fake")
    (deck / "sources" / f"{IMG_SLUG}.json").write_text(json.dumps({
        "source_id": "s-img", "original_file": IMG_FILE, "type": "pdf",
        "pages": [{"page": 2, "text": ""}],
        "images": [{"image_source_id": IMG_ID, "path": IMG_ASSET,
                    "page": 2, "context_text": "The predict-update loop."}],
    }, ensure_ascii=False), encoding="utf-8")


# --- capture + orchestration harness --------------------------------------

def _cap(fn) -> dict:
    """Run a km command function, returning its printed JSON report."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn()
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


def _invoke(role, brief, deck, result, persist_argv, image=None) -> int:
    argv = ["--role", role, "--brief-file", str(brief), "--deck", str(deck),
            "--out", str(result)]
    if image:
        argv += ["--image", image]
    argv += ["--", sys.executable, KM, "--deck", str(deck), *persist_argv]
    return invoke_shim.main(argv)


# Roles wired from build()'s return, in (deck-context role, build key) pairs.
_DESIGNER_WIRING = (("slide-composer", "planner"),
                    ("text-designer", "text_designer"),
                    ("diagram-designer", "diagram_designer"),
                    ("image-designer", "image_designer"))


def draft_deck(deck: Path, scratch: Path, *, text_responses, image_responses,
               build) -> dict:
    """Drive the documented /draft-deck sequence with fake executors.

    ``text_responses`` / ``image_responses`` are the canned miner outputs (in
    invocation order). ``build(deck, nuggets_by_kind)`` supplies:

      - ``"plan"``: the storyteller plan (referencing the real, just-mined
        nugget ids), and
      - ``"planner"``: one Stage-1 plan-JSON per to-compose slide, in deck
        (creation) order, plus
      - ``"text_designer"`` / ``"diagram_designer"`` / ``"image_designer"``:
        one Stage-2 reply per pending section of that role, in job order.

    The create/associate/merge/park steps run first (NO per-create compose);
    then ``compose_deck`` runs the whole two-stage pass ONCE at max_workers=1
    (deterministic replay order), and its report folds into the run report.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    report = {"dropped": [], "parked": [], "created": [], "aborted": False,
              "abort_errors": [], "failed_sections": [],
              "validate": None, "validate_ok": False}

    wire_fake_executor(deck, scratch, "knowledge-miner", text_responses)
    if image_responses:
        wire_fake_executor(deck, scratch, "image-miner", image_responses,
                           image_arg=True)

    # 1. Convert
    _cap(lambda: source_converter.cmd_convert(deck, None))

    # 2. Mine — per unmined source: text (1 invoke) + per image (1 invoke each)
    for sp in sorted((deck / "sources").glob("*.json")):
        src = json.loads(sp.read_text(encoding="utf-8"))
        if src.get("mined_at"):
            continue
        slug = sp.stem
        tbrief = scratch / f"mine-{slug}.md"
        _cap(lambda: km.cmd_mine_brief(
            deck, Namespace(source=slug, image=None, out=str(tbrief))))
        tres = scratch / f"mine-{slug}.result.json"
        rc = _invoke("knowledge-miner", tbrief, deck, tres,
                     ["persist-nuggets", "--source", slug, "--file", "{out}"])
        if rc != 0:
            report["dropped"].append({"source": slug, "kind": "text"})
        for img in src.get("images", []):
            iid = img["image_source_id"]
            ibrief = scratch / f"mine-{iid}.md"
            info = _cap(lambda: km.cmd_mine_brief(
                deck, Namespace(source=None, image=iid, out=str(ibrief))))
            ires = scratch / f"mine-{iid}.result.json"
            rc = _invoke("image-miner", ibrief, deck, ires,
                         ["persist-nuggets", "--source", slug,
                          "--image-source", iid, "--file", "{out}"],
                         image=info["asset"])
            if rc != 0:
                report["dropped"].append({"image": iid, "kind": "image"})
        _cap(lambda: km.cmd_mark_mined(deck, Namespace(source=slug)))

    # 3. Plan — one storyteller invoke; abort terminal composes nothing
    by_kind = {"text": [], "image": []}
    for np_ in sorted((deck / "nuggets").glob("*.json")):
        n = json.loads(np_.read_text(encoding="utf-8"))
        by_kind.setdefault(n["kind"], []).append(n["nugget_id"])
    built = build(deck, by_kind)
    wire_fake_executor(deck, scratch, "storyteller",
                       [json.dumps(built["plan"])])

    pbrief = scratch / "plan.md"
    _cap(lambda: km.cmd_plan_brief(deck, Namespace(out=str(pbrief))))
    pres = scratch / "plan.result.json"
    rc = _invoke("storyteller", pbrief, deck, pres,
                 ["write-plan", "--file", "{out}"])
    if rc != 0:
        report["aborted"] = True
        report["abort_errors"] = json.loads(
            pres.read_text(encoding="utf-8")).get("errors", [])
        return report

    # 4. Execute the plan (NO per-create compose — the driver composes later)
    steps = json.loads((deck / "plan.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        op = step["op"]
        if op == "create-slide":
            out = _cap(lambda s=step: km.cmd_create(deck, Namespace(
                title=s["title"], nuggets=",".join(s["nuggets"]),
                after=s["after"], parked=s["parked"],
                intended_function=s["intended_function"])))
            report["created"].append(out["slide_id"])
        elif op == "associate-nuggets":
            _cap(lambda s=step: km.cmd_associate(deck, Namespace(
                slide=s["slide"], nuggets=",".join(s["nuggets"]))))
        elif op == "merge-slides":
            _cap(lambda s=step: km.cmd_merge(deck, Namespace(
                slides=",".join(s["slides"]), title=s["title"])))
        elif op == "park-slide":
            _cap(lambda s=step: km.cmd_park(deck, Namespace(
                slide=s["slide"], reason=s["reason"])))
        elif op == "unpark-slide":
            _cap(lambda s=step: km.cmd_unpark(deck, Namespace(slide=s["slide"])))

    # 4b. Two-stage compose — wire the planner + designer fakes (only the roles
    #     with canned replies), then run the batch driver ONCE. max_workers=1
    #     keeps the global-counter replay deterministic (design-call order =
    #     deck order, then section order).
    for role, key in _DESIGNER_WIRING:
        responses = built.get(key) or []
        if responses:
            wire_fake_executor(deck, scratch, role, responses)
    cd = compose_deck.compose_deck(deck, run_label="test", max_workers=1)
    report["parked"].extend(cd["parked"])
    report["failed_sections"] = cd["failed_sections"]

    # 5. Validate (non-zero exit is the gate)
    vres = scratch / "validate.result.json"
    rc = _cli_validate(deck, vres)
    report["validate"] = json.loads(vres.read_text(encoding="utf-8"))
    report["validate_ok"] = rc == 0
    return report


def _cli_validate(deck: Path, out: Path) -> int:
    """Run ``km validate`` as the orchestrator does — via the CLI, gating on the
    exit code — capturing its JSON report to *out*."""
    import subprocess
    proc = subprocess.run([sys.executable, KM, "--deck", str(deck), "validate"],
                          capture_output=True, text=True, encoding="utf-8")
    out.write_text(proc.stdout, encoding="utf-8")
    return proc.returncode


def test_validate_gate_exits_nonzero_on_broken_deck(deck, tmp_path):
    """The orchestrator gates on validate's exit code (ticket 17): a green deck
    exits 0, a broken one exits non-zero while still printing its JSON report."""
    _cap(lambda: km.cmd_create(deck, Namespace(
        title="A", nuggets="", after="end", parked=False,
        intended_function=None)))
    green = tmp_path / "green.json"
    assert _cli_validate(deck, green) == 0
    assert json.loads(green.read_text(encoding="utf-8"))["ok"] is True

    # Corrupt the deck: drop a slide's state file → validate flags + exits 1.
    for p in (deck / "slides").glob("*.json"):
        p.unlink()
    broken = tmp_path / "broken.json"
    assert _cli_validate(deck, broken) != 0
    report = json.loads(broken.read_text(encoding="utf-8"))
    assert report["ok"] is False and report["errors"]


# --- the happy-path full draft plan ---------------------------------------

def _full_plan(deck, by_kind):
    t1, t2 = by_kind["text"][:2]
    (img1,) = by_kind["image"]
    plan = {"plan": [
        {"action": "create", "structural": True, "title": "Object Tracking"},
        {"action": "create", "title": "Core idea", "nuggets": [t1, t2],
         "intended_function": "define"},
        {"action": "create", "title": "The tracking loop", "nuggets": [img1],
         "intended_function": "process"},
        {"action": "create", "structural": True, "title": "Summary"},
    ], "notes": ""}
    # Planner plans in DECK (creation) order; one text-designer reply for the
    # single pending content section (the figure is a placed source-image).
    return {"plan": plan,
            "planner": [_plan_structural("Object Tracking"),
                        _plan_text("Tracking estimates state", [t1, t2]),
                        _plan_source_image("The tracking loop", [img1]),
                        _plan_structural("Summary")],
            "text_designer": [DESIGN_CORE_BODY]}


def _assoc(deck: Path) -> dict:
    return json.loads((deck / "associations.json").read_text(encoding="utf-8"))


# ==========================================================================
# The core integration test: full first draft -> green validate
# ==========================================================================

def test_full_draft_reaches_green_validate(deck, tmp_path):
    _seed_inputs(deck)

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=_full_plan)

    assert report["validate_ok"] is True
    assert report["validate"]["ok"] is True
    assert report["validate"]["slides"] == 4
    assert report["validate"]["parked"] == []
    assert report["dropped"] == [] and report["parked"] == []
    assert report["failed_sections"] == []
    assert report["aborted"] is False
    assert len(report["created"]) == 4

    # Every content slide traces to its nuggets (structural ones hold none).
    A = _assoc(deck)
    placed = sorted(nid for nugs in A.values() for nid in nugs)
    all_nuggets = sorted(p.stem for p in (deck / "nuggets").glob("*.json"))
    assert placed == all_nuggets                       # nothing left unplaced
    assert len(all_nuggets) == 3                       # 2 text + 1 image

    # The content slide carries the Stage-2 DESIGNER's placed text in its
    # physical slot (verbatim presenter notes / composer slot markers are NOT
    # part of the two-stage path in v1 — see the plan's deferred list). The
    # figure slide places the real asset from its source-image section, no
    # designer (write-skeleton places it).
    content_sid = [s for s, n in A.items() if len(n) == 2][0]
    content_md = (deck / "slides" / f"{content_sid}.md").read_text(encoding="utf-8")
    assert "estimate state over time" in content_md    # designer-built body
    figure_sid = [s for s, n in A.items()
                  if any((km.load_nugget(deck, x) or {}).get("kind") == "image"
                         for x in n)][0]
    figure_md = (deck / "slides" / f"{figure_sid}.md").read_text(encoding="utf-8")
    assert IMG_ASSET in figure_md


# ==========================================================================
# Per-role terminals surface in the run report (never silent)
# ==========================================================================

def test_miner_drop_is_flagged_and_pipeline_continues(deck, tmp_path):
    """A text source whose miner never yields valid output is dropped+flagged;
    the image on the same converted set still mines and the draft completes."""
    _seed_inputs(deck)
    # chapter-9's text miner returns a verbatim violation every attempt.
    bad = _text_batch({"title": "Invented", "information": "- x",
                       "raw_text": "This sentence is not in the source.",
                       "page": 1})

    def plan_from_image_only(deck, by_kind):
        (img1,) = by_kind["image"]
        plan = {"plan": [
            {"action": "create", "structural": True, "title": "Cover"},
            {"action": "create", "title": "The loop", "nuggets": [img1]},
        ], "notes": ""}
        # Both slides compose without a designer: structural + placed source-image.
        return {"plan": plan,
                "planner": [_plan_structural("Cover"),
                            _plan_source_image("The loop", [img1])]}

    # chapter-9 is mined first: its three attempts (initial + cap-2 retries)
    # all get the bad output and exhaust to the drop terminal; figures' empty
    # text mine then gets the valid empty batch.
    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[bad, bad, bad, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=plan_from_image_only)

    assert report["dropped"] == [{"source": TEXT_SLUG, "kind": "text"}]
    assert report["validate_ok"] is True               # deck still green
    # The dropped source mined nothing but the figure survived.
    kinds = sorted(km.load_nugget(deck, p.stem)["kind"]
                   for p in (deck / "nuggets").glob("*.json"))
    assert kinds == ["image"]


def test_designer_failure_is_flagged(deck, tmp_path):
    """A content section whose designer never yields usable output is flagged in
    the run report and leaves its wireframe visible; the slide stays `planned`
    (NOT parked — a designer exhaustion is not a planner park) and validate stays
    green: a planned slide with a rendered wireframe is a valid slide file."""
    _seed_inputs(deck)

    def plan_with_failing_body(deck, by_kind):
        t1, t2 = by_kind["text"][:2]
        (img1,) = by_kind["image"]
        plan = {"plan": [
            {"action": "create", "structural": True, "title": "Cover"},
            {"action": "create", "title": "Core", "nuggets": [t1, t2]},
            # The figure keeps D34 satisfied (every nugget placed); it composes
            # fine as a source-image while the Core text section fails.
            {"action": "create", "title": "The loop", "nuggets": [img1]},
        ], "notes": ""}
        # The Core text-designer returns EMPTY on every attempt (the fake
        # repeats its last reply), so place-design rejects empty content and
        # design_one exhausts → compose_deck records a failed_section.
        return {"plan": plan,
                "planner": [_plan_structural("Cover"),
                            _plan_text("Core", [t1, t2]),
                            _plan_source_image("The loop", [img1])],
                "text_designer": [""]}

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=plan_with_failing_body)

    assert report["failed_sections"], "the exhausted designer must be flagged"
    fs = report["failed_sections"][0]
    assert fs["section"] == "body"
    assert report["parked"] == []                      # a designer fail never parks
    assert report["validate_ok"] is True               # deck stays green
    assert report["validate"]["slides"] == 3           # cover + core + loop active

    # The flagged slide stayed `planned` with its wireframe still visible.
    core_sid = fs["slide"]
    stj = km.load_state(deck, core_sid)
    assert stj["state"] == "planned"
    core_md = (deck / "slides" / f"{core_sid}.md").read_text(encoding="utf-8")
    assert "pending" in core_md                        # wireframe placeholder


def test_storyteller_abort_composes_nothing(deck, tmp_path):
    """An invalid plan aborts the run with a flagged error; no slide exists."""
    _seed_inputs(deck)

    def bad_plan(deck, by_kind):
        plan = {"plan": [
            {"action": "create", "title": "Ghost", "nuggets": ["no-such-id"]}],
            "notes": ""}
        return {"plan": plan}     # abort precedes compose; no planner needed

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=bad_plan)

    assert report["aborted"] is True
    assert any("no-such-id" in e for e in report["abort_errors"])
    assert report["created"] == []
    assert list((deck / "slides").glob("*.md")) == []   # nothing composed
    assert not (deck / "plan.json").exists()


# ==========================================================================
# Re-run: delta plan mines only the new input, existing slides untouched
# ==========================================================================

def test_second_run_delta_plan_mines_only_new_input(deck, tmp_path):
    _seed_inputs(deck)
    draft_deck(deck, tmp_path / "run1",
               text_responses=[CH9_MINE, EMPTY_MINE],
               image_responses=[IMG_MINE], build=_full_plan)

    before = {p.name: p.read_text(encoding="utf-8")
              for p in (deck / "slides").glob("*.md")}
    nuggets_before = {p.stem for p in (deck / "nuggets").glob("*.json")}

    # A new input arrives; run the pipeline again.
    (deck / "input" / TEXT2_INPUT).write_text(TEXT2_BODY, encoding="utf-8")

    def delta(deck, by_kind):
        placed = {nid for nugs in _assoc(deck).values() for nid in nugs}
        fresh = [nid for nid in by_kind["text"] if nid not in placed]
        assert len(fresh) == 1                          # only the new nugget
        plan = {"plan": [
            {"action": "create", "title": "Deep trackers", "nuggets": fresh,
             "intended_function": "finding"}], "notes": ""}
        # The one new content slide: a text section built by the text-designer.
        return {"plan": plan,
                "planner": [_plan_text("Deep trackers", fresh, concept="finding")],
                "text_designer": ["- deep networks"]}

    report = draft_deck(deck, tmp_path / "run2",
                        text_responses=[CH10_MINE],  # only chapter-10 unmined
                        image_responses=[], build=delta)

    assert report["validate_ok"] is True
    assert report["validate"]["slides"] == 5           # 4 + the new one

    # Only the new input was mined: exactly one new nugget, sourced to it.
    nuggets_after = {p.stem for p in (deck / "nuggets").glob("*.json")}
    new_ids = nuggets_after - nuggets_before
    assert len(new_ids) == 1
    assert km.load_nugget(deck, new_ids.pop())["source"] == TEXT2_INPUT

    # Every pre-existing slide file is byte-for-byte untouched.
    after = {p.name: p.read_text(encoding="utf-8")
             for p in (deck / "slides").glob("*.md")}
    for name, text in before.items():
        assert after.get(name) == text, f"slide {name} was modified on re-run"
    assert len(after) == len(before) + 1               # exactly one slide added


# ==========================================================================
# Status slide: threaded mid-run, cleared at the end, never budgeted
# ==========================================================================

def test_status_slide_is_threaded_and_cleared_without_costing_budget(deck, tmp_path):
    """The transient status slide appears mid-run and is removed at the end; it
    never consumes a budget slot (final active count == the plan's real slides)."""
    _seed_inputs(deck)

    # Set a status BEFORE drafting (as /draft-deck §0 does) and assert it shows
    # up uncounted, then run the normal draft which clears it at the end.
    km.cmd_set_status(deck, Namespace(phase="mine", detail="0/2",
                                      label="Mining sources…"))
    mid = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" in mid
    assert km.order(deck) == []                        # status alone counts 0

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=_full_plan)
    km.cmd_clear_status(deck, Namespace())             # as §5 does on success

    assert report["validate_ok"] is True
    assert report["validate"]["slides"] == 4           # exactly the 4 real slides
    final = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" not in final              # cleared
    assert not (deck / ".draft-status.json").exists()


# ==========================================================================
# The real driver (draft_deck.py, design §5): digest mode + fail-fast/resume
# ==========================================================================

def test_digest_mode_mines_then_stops(deck, tmp_path):
    """Digest mode runs convert + mine and STOPS — plan/compose/validate are
    null (not run at all, §5.2). A re-run mines nothing (delta, §5.3)."""
    _seed_inputs(deck)
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)

    report = dd.run(deck, mode="digest")

    assert report["status"] == "ok"
    assert report["mode"] == "digest"
    assert report["mine"]["sources_mined"] == 2
    assert report["mine"]["nuggets_created"] == 3      # 2 text + 1 image
    assert report["mine"]["dropped"] == []
    assert report["plan"] is None                      # not run at all
    assert report["compose"] is None
    assert report["validate"] is None
    assert list((deck / "slides").glob("*.md")) == []  # nothing composed

    # Re-run: every source is now marked mined → nothing to mine.
    report2 = dd.run(deck, mode="digest")
    assert report2["mine"]["sources_mined"] == 0
    assert report2["mine"]["nuggets_created"] == 0


def _count_nuggets(deck):
    return len(list((deck / "nuggets").glob("*.json")))


def _wire_boom(deck, tmp_path, role, image_arg=False):
    """Point a role at a `cmd` executor that exits non-zero → the shim records
    status='error' (an infra failure no re-invoke can fix)."""
    respdir = tmp_path / f"boom-{role}"
    respdir.mkdir(parents=True)
    script = tmp_path / "boom.py"
    script.write_text("import sys; sys.exit(1)", encoding="utf-8")
    command = [sys.executable, str(script)]
    if image_arg:
        command.append("{image}")
    ctx_path = deck / "deck-context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    ctx.setdefault("executors", {})[role] = {
        "executor": "cmd", "command": command}
    ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")


def test_mine_infra_error_stops_then_resumes(deck, tmp_path):
    """A shim `error` mid-mine stops the run at `mine` (the source stays
    unmined); a re-run with a healthy executor resumes and mines it (§5.3/§5.4)."""
    _seed_inputs(deck)
    _wire_boom(deck, tmp_path, "knowledge-miner")

    stopped = dd.run(deck, mode="digest")
    assert stopped["status"] == "error"
    assert stopped["stopped_at"] == "mine"
    assert _count_nuggets(deck) == 0                   # nothing persisted
    # chapter-9 was never marked mined → still unmined.
    unmined = [p.stem for p in (deck / "sources").glob("*.json")
               if not json.loads(p.read_text(encoding="utf-8")).get("mined_at")]
    assert TEXT_SLUG in unmined

    # Heal the executor and resume (distinct role dirs → no mkdir collision).
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    resumed = dd.run(deck, mode="digest")
    assert resumed["status"] == "ok"
    assert resumed["mine"]["sources_mined"] == 2
    assert _count_nuggets(deck) == 3


def test_mid_source_stop_does_not_duplicate_on_resume(deck, tmp_path):
    """A source with BOTH minable text and an image: text mines first (persists
    a nugget), then the image mine hits an infra error -> stop. On resume the
    source must NOT re-persist the text nugget (no duplicate). Guards the
    clear-before-remine fix; without it the resume would leave 3 nuggets."""
    (deck / "sources").mkdir(exist_ok=True)
    (deck / "public" / "extracted").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "extracted" / "combo-p1-img1.png").write_bytes(b"\x89PNG fake")
    (deck / "sources" / "combo.json").write_text(json.dumps({
        "source_id": "s-combo", "original_file": "combo.pdf", "type": "pdf",
        "pages": [{"page": 1, "text": RAW_1}],
        "images": [{"image_source_id": "combo-p1-img1",
                    "path": "/extracted/combo-p1-img1.png", "page": 1,
                    "context_text": "the loop"}],
    }, ensure_ascii=False), encoding="utf-8")

    # Text miner yields a valid nugget (raw_text is a verbatim substring of the
    # page); image miner errors on every attempt.
    text_nug = _text_batch({"title": "Tracking", "information": "- estimate",
                            "raw_text": RAW_1, "page": 1})
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [text_nug])
    _wire_boom(deck, tmp_path, "image-miner", image_arg=True)

    stopped = dd.run(deck, mode="digest")
    assert stopped["status"] == "error" and stopped["stopped_at"] == "mine"
    assert _count_nuggets(deck) == 1        # text persisted before the image boom

    # Heal the image miner and resume.
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    resumed = dd.run(deck, mode="digest")
    assert resumed["status"] == "ok"
    assert _count_nuggets(deck) == 2        # exactly one text + one image, no dup


def test_full_mode_via_real_driver_reaches_green(deck, tmp_path):
    """Digest first (mines → real nugget ids), then wire the storyteller/planner/
    designer fakes against those ids and run the REAL driver in full mode: it
    mines nothing new (all marked), plans, executes, composes, validates green."""
    _seed_inputs(deck)

    # 1. Mine everything (digest) so real nugget ids exist.
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    assert dd.run(deck, mode="digest")["mine"]["sources_mined"] == 2

    # 2. Build the plan against the just-mined ids and wire the fakes (distinct
    #    roles → distinct responses-<role> dirs under tmp_path, no collision).
    by_kind = {"text": [], "image": []}
    for np_ in sorted((deck / "nuggets").glob("*.json")):
        n = json.loads(np_.read_text(encoding="utf-8"))
        by_kind.setdefault(n["kind"], []).append(n["nugget_id"])
    built = _full_plan(deck, by_kind)
    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(built["plan"])])
    wire_fake_executor(deck, tmp_path, "slide-composer", built["planner"])
    wire_fake_executor(deck, tmp_path, "text-designer", built["text_designer"])

    # 3. Full run through the real driver (max_workers=1 → deterministic replay).
    report = dd.run(deck, mode="full", run_label="test", max_workers=1)

    assert report["status"] == "ok"
    assert report["plan"]["slides_planned"] == 4
    assert report["compose"]["parked"] == []
    assert report["validate"]["ok"] is True
    assert report["validate"]["exit_ok"] is True
    assert report["validate"]["slides"] == 4


def test_full_mode_storyteller_abort_composes_nothing(deck, tmp_path):
    """An invalid plan (unknown nugget id) → storyteller exhausted → stop at
    `plan`; nothing is composed and no plan.json survives (§5.4)."""
    _seed_inputs(deck)
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    dd.run(deck, mode="digest")

    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(
        {"plan": [{"action": "create", "title": "Ghost",
                   "nuggets": ["no-such-id"]}], "notes": ""})])

    report = dd.run(deck, mode="full")
    assert report["status"] == "error"
    assert report["stopped_at"] == "plan"
    assert list((deck / "slides").glob("*.md")) == []
    assert not (deck / "plan.json").exists()


def test_full_mode_nothing_to_do_reports_ok(deck, tmp_path):
    """A full run on a fully-composed deck re-derives clean state and reports ok
    without re-planning: plan stays null, compose composes nothing (§5.3)."""
    _seed_inputs(deck)
    # Reach a green deck first via the real driver.
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    dd.run(deck, mode="digest")
    by_kind = {"text": [], "image": []}
    for np_ in sorted((deck / "nuggets").glob("*.json")):
        n = json.loads(np_.read_text(encoding="utf-8"))
        by_kind.setdefault(n["kind"], []).append(n["nugget_id"])
    built = _full_plan(deck, by_kind)
    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(built["plan"])])
    wire_fake_executor(deck, tmp_path, "slide-composer", built["planner"])
    wire_fake_executor(deck, tmp_path, "text-designer", built["text_designer"])
    dd.run(deck, mode="full", max_workers=1)

    # Now nothing is unplaced and nothing is to-compose.
    report = dd.run(deck, mode="full", max_workers=1)
    assert report["status"] == "ok"
    assert report["plan"] is None                 # storyteller not re-invoked
    assert report["compose"] is None or report["compose"]["composed"] == []
