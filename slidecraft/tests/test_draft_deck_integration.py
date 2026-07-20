"""Ticket 17 — /draft-deck orchestrator end-to-end, at the CLI seams.

The v1 orchestrator IS the ``/draft-deck`` command (an LLM lead running the
deterministic scripts); its target form is a Workflow over the same seams. This
test drives that documented phase sequence — convert -> mine (one invoke per
text source + per extracted image) -> plan -> execute-plan (create/associate/
merge/park; compose after every create and merge) -> validate — over a fixture
deck with a **fake executor** (canned miner/storyteller/composer outputs), and
asserts the deck reaches a green ``validate``. No test touches a live LLM.

``draft_deck`` below is the test harness that mirrors the command doc: it calls
the real km CLI and the real invoke shim, only the executor is faked. It also
collects the per-role terminals (drop/park/abort) into a run report, so the
"flagged, never silent" behavior is asserted at the seam the orchestrator owns.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import invoke_shim, km, source_converter
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


def _compose(layout, concept, content, image=None) -> str:
    obj = {"layout": layout, "concept_type": concept, "content": content}
    if image:
        obj["image"] = image
    return json.dumps(obj)


COVER = _compose("cover", "structural",
                 {"title": "Object Tracking", "meta": "Dr. Jane Roe · 2026"})
CONTENT = _compose("content", "define",
                   {"title": "Tracking estimates state",
                    "body": "- estimate state over time\n- from measurements"})
FIGURE = _compose("figure", "process", {"title": "The tracking loop"},
                  image={"asset": IMG_ASSET, "alt": "predict-update loop"})
CLOSING = _compose("closing", "structural", {})
BAD_COMPOSE = _compose("no-such-layout", "define", {"title": "T"})


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


def draft_deck(deck: Path, scratch: Path, *, text_responses, image_responses,
               build, park_reason="composition failed after 3 attempts") -> dict:
    """Drive the documented /draft-deck sequence with fake executors.

    ``text_responses`` / ``image_responses`` are the canned miner outputs (in
    invocation order). ``build(deck, nuggets_by_kind) -> {"plan", "composer"}``
    supplies the storyteller plan (referencing the real, just-mined nugget ids)
    and the composer outputs in step order.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    report = {"dropped": [], "parked": [], "created": [], "aborted": False,
              "abort_errors": [], "validate": None, "validate_ok": False}

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
    wire_fake_executor(deck, scratch, "slide-composer", built["composer"])

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

    # 4. Execute the plan + compose after every create and merge
    steps = json.loads((deck / "plan.json").read_text(encoding="utf-8"))["steps"]

    def compose(sid):
        cbrief = scratch / f"compose-{sid}.md"
        _cap(lambda: km.cmd_compose_brief(
            deck, Namespace(slide=sid, out=str(cbrief))))
        cres = scratch / f"compose-{sid}.result.json"
        rc = _invoke("slide-composer", cbrief, deck, cres,
                     ["write-slide", "--slide", sid, "--file", "{out}"])
        if rc != 0:                                   # composer terminal: park
            _cap(lambda: km.cmd_park(
                deck, Namespace(slide=sid, reason=park_reason)))
            report["parked"].append(sid)

    for step in steps:
        op = step["op"]
        if op == "create-slide":
            out = _cap(lambda s=step: km.cmd_create(deck, Namespace(
                title=s["title"], nuggets=",".join(s["nuggets"]),
                after=s["after"], parked=s["parked"],
                intended_function=s["intended_function"])))
            sid = out["slide_id"]
            report["created"].append(sid)
            if not step["parked"]:
                compose(sid)
        elif op == "associate-nuggets":
            _cap(lambda s=step: km.cmd_associate(deck, Namespace(
                slide=s["slide"], nuggets=",".join(s["nuggets"]))))
        elif op == "merge-slides":
            out = _cap(lambda s=step: km.cmd_merge(deck, Namespace(
                slides=",".join(s["slides"]), title=s["title"])))
            compose(out["slide_id"])
        elif op == "park-slide":
            _cap(lambda s=step: km.cmd_park(deck, Namespace(
                slide=s["slide"], reason=s["reason"])))
        elif op == "unpark-slide":
            _cap(lambda s=step: km.cmd_unpark(deck, Namespace(slide=s["slide"])))

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
    return {"plan": plan, "composer": [COVER, CONTENT, FIGURE, CLOSING]}


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
    assert report["aborted"] is False
    assert len(report["created"]) == 4

    # Every content slide traces to its nuggets (structural ones hold none).
    A = _assoc(deck)
    placed = sorted(nid for nugs in A.values() for nid in nugs)
    all_nuggets = sorted(p.stem for p in (deck / "nuggets").glob("*.json"))
    assert placed == all_nuggets                       # nothing left unplaced
    assert len(all_nuggets) == 3                       # 2 text + 1 image

    # The composed content slide carries verbatim presenter notes (D39) and
    # its assertion body; the figure slide places the real asset.
    content_sid = [s for s, n in A.items() if len(n) == 2][0]
    content_md = (deck / "slides" / f"{content_sid}.md").read_text(encoding="utf-8")
    assert RAW_1 in content_md and RAW_2 in content_md      # verbatim notes
    assert "::heading::" in content_md                      # physical slot
    figure_sid = [s for s, n in A.items()
                  if any((km.load_nugget(deck, x) or {}).get("kind") == "image"
                         for x in n)][0]
    figure_md = (deck / "slides" / f"{figure_sid}.md").read_text(encoding="utf-8")
    assert IMG_ASSET in figure_md
    assert "Predict" in figure_md                           # image visible_text notes


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
        return {"plan": plan, "composer": [COVER, FIGURE]}

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


def test_composer_park_terminal_keeps_deck_green(deck, tmp_path):
    """A slide the composer cannot produce is parked + flagged; validate stays
    green with the failed slide in the parked block."""
    _seed_inputs(deck)

    def plan_with_doomed_last(deck, by_kind):
        t1, t2 = by_kind["text"][:2]
        (img1,) = by_kind["image"]
        plan = {"plan": [
            {"action": "create", "structural": True, "title": "Cover"},
            {"action": "create", "title": "Core", "nuggets": [t1, t2]},
            # The figure slide is composed LAST; its bad output repeats through
            # the cap-2 retries and exhausts to the park terminal.
            {"action": "create", "title": "Doomed figure", "nuggets": [img1]},
        ], "notes": ""}
        return {"plan": plan, "composer": [COVER, CONTENT, BAD_COMPOSE]}

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=plan_with_doomed_last)

    assert len(report["parked"]) == 1
    doomed = report["parked"][0]
    assert report["validate_ok"] is True
    assert report["validate"]["parked"] == [doomed]
    assert report["validate"]["slides"] == 2           # cover + core active
    stj = km.load_state(deck, doomed)
    assert stj["state"] == "parked" and "composition failed" in stj["parked_reason"]


def test_storyteller_abort_composes_nothing(deck, tmp_path):
    """An invalid plan aborts the run with a flagged error; no slide exists."""
    _seed_inputs(deck)

    def bad_plan(deck, by_kind):
        plan = {"plan": [
            {"action": "create", "title": "Ghost", "nuggets": ["no-such-id"]}],
            "notes": ""}
        return {"plan": plan, "composer": [CONTENT]}

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
        return {"plan": plan, "composer": [
            _compose("content", "finding",
                     {"title": "Deep trackers", "body": "- deep networks"})]}

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
