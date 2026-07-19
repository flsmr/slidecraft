"""Ticket 13 — text-miner pure-function slice, tested at the pre-agreed seams.

Seam 1 (km CLI): ``mine-brief`` field routing (the brief carries the miner
craft + injection values + the full source text and nothing else — no script
instructions, no paths, no IDs to chase), the atomic fan-out persist wrapper
``persist-nuggets`` (validate the whole batch before writing anything; enrich
``kind``/``source`` — the miner must not invent them), and the ``mark-mined``
bookkeeping (source stamped + input moved only when the orchestrator says so).

Seam 2 (invoke shim, fake executor): the mine step end to end — brief →
cmd-executor → persist — including the verbatim-guard rejection driving the
shim's retry and the cap-2 → drop+flag terminal. No test touches a live LLM.
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import invoke_shim, km
from slidecraft.tests.conftest import SOURCE_FILE, SOURCE_SLUG

# A verbatim passage from conftest.SOURCE_TEXT (guard-clean).
VERBATIM = ("the material from which the prototypes are created is generally "
            "not an issue")


def _mine_brief(deck: Path, out: Path, source: str = SOURCE_SLUG) -> str:
    km.cmd_mine_brief(deck, Namespace(source=source, out=str(out)))
    return out.read_text(encoding="utf-8")


def _nugget(**over) -> dict:
    n = {"title": "Prototype material relevance",
         "information": "- material choice is secondary at prototype stage",
         "raw_text": VERBATIM,
         "page": 1}
    n.update(over)
    return n


def _persist(deck: Path, batch: dict, source: str = SOURCE_SLUG):
    f = deck / "logs" / "miner-batch.json"
    f.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    km.cmd_persist_nuggets(deck, Namespace(source=source, file=str(f)))


def _nugget_files(deck: Path) -> list[Path]:
    return sorted((deck / "nuggets").glob("*.json"))


# ---------------------------------------------------------------------------
# mine-brief — field routing (seam 1)
# ---------------------------------------------------------------------------

def test_mine_brief_carries_craft_injection_and_source_text(converted_deck,
                                                            tmp_path, capsys):
    brief = _mine_brief(converted_deck, tmp_path / "brief.md")

    # Injection values resolved (FOCUS-TOPIC, LANGUAGE)…
    assert "Object Tracking" in brief
    # …with no unresolved %PLACEHOLDER% left anywhere.
    assert not re.search(r"%[A-Z][A-Z-]*%", brief)
    # The tuned granularity craft survives the rework.
    assert "A list in the source is ONE nugget" in brief
    assert "6–12" in brief
    # The full source text rides inline, with page markers for the page field.
    assert "material from which the prototypes are created" in brief
    assert "<!-- page 1 -->" in brief
    # CLI reports the brief location.
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True and out["source"] == SOURCE_SLUG


def test_mine_brief_is_self_contained_no_scripts_paths_or_ids(converted_deck,
                                                              tmp_path):
    brief = _mine_brief(converted_deck, tmp_path / "brief.md")

    # No script instructions, no file paths to read, no IDs to chase.
    for needle in ("km.py", "--deck", "python ", "create-nugget",
                   "sources/", "nuggets/"):
        assert needle not in brief, f"brief leaks {needle!r}"
    assert str(converted_deck) not in brief
    assert SOURCE_SLUG not in brief  # the miner never sees source ids


def test_mine_brief_unknown_source_fails_loudly(converted_deck, tmp_path):
    with pytest.raises(SystemExit) as ei:
        _mine_brief(converted_deck, tmp_path / "b.md", source="nope")
    assert "nope" in str(ei.value)


# ---------------------------------------------------------------------------
# persist-nuggets — atomic fan-out persist wrapper (seam 1)
# ---------------------------------------------------------------------------

def test_persist_enriches_kind_and_source_and_persists(converted_deck, capsys):
    _persist(converted_deck, {"nuggets": [_nugget()]})

    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] == 1
    nid = out["nugget_ids"][0]
    n = json.loads((converted_deck / "nuggets" / f"{nid}.json")
                   .read_text(encoding="utf-8"))
    # The wrapper enriched what the miner must not invent.
    assert n["kind"] == "text"
    assert n["source"] == SOURCE_FILE
    assert n["raw_text"] == VERBATIM


def test_persist_overrides_miner_invented_kind_and_source(converted_deck,
                                                          capsys):
    _persist(converted_deck,
             {"nuggets": [_nugget(kind="image", source="invented.pdf")]})
    nid = json.loads(capsys.readouterr().out.strip())["nugget_ids"][0]
    n = json.loads((converted_deck / "nuggets" / f"{nid}.json")
                   .read_text(encoding="utf-8"))
    assert n["kind"] == "text"
    assert n["source"] == SOURCE_FILE


def test_persist_rejects_verbatim_violation_atomically(converted_deck):
    batch = {"nuggets": [
        _nugget(),                                    # valid
        _nugget(title="Invented claim",
                raw_text="Rapid prototyping cures all diseases."),
    ]}
    with pytest.raises(SystemExit) as ei:
        _persist(converted_deck, batch)

    assert "verbatim" in str(ei.value)
    assert "#2" in str(ei.value)              # error names the failing item
    # Atomic: the valid first nugget was NOT written either — a shim retry
    # re-sends the whole batch and must not duplicate anything.
    assert _nugget_files(converted_deck) == []


def test_persist_rejects_missing_fields_naming_the_item(converted_deck):
    batch = {"nuggets": [_nugget(), {"title": "no substance"}]}
    with pytest.raises(SystemExit) as ei:
        _persist(converted_deck, batch)
    msg = str(ei.value)
    assert "#2" in msg and "missing" in msg
    assert _nugget_files(converted_deck) == []


def test_persist_rejects_non_batch_shape(converted_deck):
    with pytest.raises(SystemExit) as ei:
        _persist(converted_deck, {"nugget": "not a list"})
    assert "nuggets" in str(ei.value)


def test_persist_empty_batch_is_ok(converted_deck, capsys):
    _persist(converted_deck, {"nuggets": []})
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] == 0 and out["nugget_ids"] == []


# ---------------------------------------------------------------------------
# mark-mined — bookkeeping only after persist (seam 1)
# ---------------------------------------------------------------------------

def test_mark_mined_stamps_source_and_moves_input(converted_deck, capsys):
    km.cmd_mark_mined(converted_deck, Namespace(source=SOURCE_SLUG))

    src = json.loads((converted_deck / "sources" / f"{SOURCE_SLUG}.json")
                     .read_text(encoding="utf-8"))
    assert src["mined_at"]
    assert not (converted_deck / "input" / SOURCE_FILE).exists()
    assert (converted_deck / "input" / "processed" / SOURCE_FILE).exists()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True and out["input_moved"] is True


def test_mark_mined_is_idempotent(converted_deck, capsys):
    km.cmd_mark_mined(converted_deck, Namespace(source=SOURCE_SLUG))
    first = json.loads(capsys.readouterr().out.strip())["mined_at"]
    km.cmd_mark_mined(converted_deck, Namespace(source=SOURCE_SLUG))
    again = json.loads(capsys.readouterr().out.strip())
    assert again["ok"] is True
    assert again["mined_at"] == first          # stamp not overwritten


# ---------------------------------------------------------------------------
# The mine step end to end over the shim (seam 2, fake cmd executor)
# ---------------------------------------------------------------------------

FAKE_EXECUTOR = textwrap.dedent("""\
    import pathlib, sys
    d = pathlib.Path(sys.argv[1])
    counter = d / "count"
    i = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(i + 1))
    files = sorted(d.glob("resp-*.txt"))
    sys.stdout.write(files[min(i, len(files) - 1)]
                     .read_text(encoding="utf-8"))
""")


def _wire_fake_executor(deck: Path, tmp_path: Path, responses: list[str]):
    """Point the deck's knowledge-miner at a scripted cmd executor."""
    respdir = tmp_path / "responses"
    respdir.mkdir()
    for i, resp in enumerate(responses):
        (respdir / f"resp-{i}.txt").write_text(resp, encoding="utf-8")
    script = tmp_path / "fake_executor.py"
    script.write_text(FAKE_EXECUTOR, encoding="utf-8")
    ctx_path = deck / "deck-context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    ctx["executors"] = {"knowledge-miner": {
        "executor": "cmd", "command": [sys.executable, str(script),
                                       str(respdir)]}}
    ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
    return respdir


def _run_mine_step(deck: Path, tmp_path: Path) -> tuple[int, dict]:
    brief = tmp_path / "brief.md"
    km.cmd_mine_brief(deck, Namespace(source=SOURCE_SLUG, out=str(brief)))
    result = tmp_path / "invoke-result.json"
    rc = invoke_shim.main([
        "--role", "knowledge-miner", "--brief-file", str(brief),
        "--deck", str(deck), "--out", str(result), "--",
        sys.executable, str(Path(km.__file__)), "--deck", str(deck),
        "persist-nuggets", "--source", SOURCE_SLUG, "--file", "{out}",
    ])
    return rc, json.loads(result.read_text(encoding="utf-8"))


def test_mine_step_persists_nuggets_and_logs(converted_deck, tmp_path, capsys):
    good = json.dumps({"nuggets": [_nugget()]})
    _wire_fake_executor(converted_deck, tmp_path, [good])

    rc, result = _run_mine_step(converted_deck, tmp_path)

    assert rc == 0
    assert result["status"] == "ok" and result["attempts"] == 1
    files = _nugget_files(converted_deck)
    assert len(files) == 1
    persisted = json.loads(files[0].read_text(encoding="utf-8"))
    assert persisted["kind"] == "text" and persisted["source"] == SOURCE_FILE
    # Demoable action log: nugget creation + the invoke itself are recorded.
    log = (converted_deck / "logs" / "actions.jsonl").read_text(encoding="utf-8")
    assert '"create-nugget"' in log and '"invoke"' in log


def test_mine_step_retries_on_verbatim_reject_then_succeeds(converted_deck,
                                                            tmp_path, capsys):
    bad = json.dumps({"nuggets": [_nugget(raw_text="Invented sentence.")]})
    good = json.dumps({"nuggets": [_nugget()]})
    respdir = _wire_fake_executor(converted_deck, tmp_path, [bad, good])

    rc, result = _run_mine_step(converted_deck, tmp_path)

    assert rc == 0
    assert result["status"] == "ok" and result["attempts"] == 2
    assert any("verbatim" in e for e in result["errors"])
    assert len(_nugget_files(converted_deck)) == 1
    assert (respdir / "count").read_text() == "2"


def test_mine_step_cap2_drops_and_flags_source_stays_unmined(converted_deck,
                                                             tmp_path, capsys):
    bad = json.dumps({"nuggets": [_nugget(raw_text="Invented sentence.")]})
    respdir = _wire_fake_executor(converted_deck, tmp_path, [bad, bad, bad])

    rc, result = _run_mine_step(converted_deck, tmp_path)

    assert rc == 3                              # shim: exhausted
    assert result["status"] == "exhausted"
    assert result["terminal"] == "drop"         # miner terminal (D44)
    assert result["attempts"] == 3
    assert all("verbatim" in e for e in result["errors"])
    # Flagged in the run report, nothing persisted, source left unmined.
    assert _nugget_files(converted_deck) == []
    src = json.loads((converted_deck / "sources" / f"{SOURCE_SLUG}.json")
                     .read_text(encoding="utf-8"))
    assert "mined_at" not in src
    assert (converted_deck / "input" / SOURCE_FILE).exists()
    assert (respdir / "count").read_text() == "3"
