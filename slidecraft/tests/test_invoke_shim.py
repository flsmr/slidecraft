"""Tests for the invoke shim (ticket 12, SPEC D44) at the pre-agreed seam:
the shim's Python API driven by a fake executor. No test touches a network
or a live model.

The shim is the one deliberately nondeterministic seam of the D40 pipeline:
``run_role(role, brief, ...)`` sends a self-contained brief to an executor,
parses the structured output, hands it to a persist callback, and wraps the
bounded rejection loop (re-invoke with the error appended, cap 2, then the
per-role terminal: miner → drop, composer → park, storyteller → abort).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from slidecraft.scripts import invoke_shim


class FakeExecutor:
    """Scripted executor: returns canned outputs in order, records prompts."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []  # list of (prompt, image)

    def run(self, prompt, image=None):
        self.calls.append((prompt, image))
        return self.outputs.pop(0)


def _persist_recorder(record, reject_first=0):
    """A persist callback that rejects the first *reject_first* payloads."""
    state = {"n": 0}

    def persist(payload):
        state["n"] += 1
        if state["n"] <= reject_first:
            raise invoke_shim.PersistRejection(f"rejected #{state['n']}")
        record.append(payload)

    return persist


def test_valid_output_persists_once_and_returns_ok():
    executor = FakeExecutor([json.dumps({"nuggets": []})])
    persisted = []

    result = invoke_shim.run_role(
        role="knowledge-miner",
        brief="MINE THIS",
        persist=_persist_recorder(persisted),
        executor=executor,
    )

    assert result.status == "ok"
    assert result.terminal is None
    assert result.attempts == 1
    assert persisted == [{"nuggets": []}]
    assert executor.calls[0][0] == "MINE THIS"


def test_rejection_reinvokes_with_error_appended_then_succeeds():
    good = json.dumps({"nuggets": [{"title": "t"}]})
    executor = FakeExecutor([json.dumps({"nuggets": "bad"}), good])
    persisted = []

    result = invoke_shim.run_role(
        role="knowledge-miner",
        brief="MINE THIS",
        persist=_persist_recorder(persisted, reject_first=1),
        executor=executor,
    )

    assert result.status == "ok"
    assert result.attempts == 2
    assert persisted == [{"nuggets": [{"title": "t"}]}]
    # The retry prompt is the original brief plus the rejection error.
    retry_prompt = executor.calls[1][0]
    assert "MINE THIS" in retry_prompt
    assert "rejected #1" in retry_prompt


@pytest.mark.parametrize("role, terminal", [
    ("knowledge-miner", "drop"),
    ("image-miner", "drop"),
    ("slide-composer", "park"),
    ("storyteller", "abort"),
])
def test_cap_exhaustion_resolves_to_per_role_terminal(role, terminal):
    bad = json.dumps({"x": 1})
    executor = FakeExecutor([bad, bad, bad])   # initial + 2 re-invokes
    persisted = []

    result = invoke_shim.run_role(
        role=role,
        brief="B",
        persist=_persist_recorder(persisted, reject_first=99),
        executor=executor,
    )

    assert result.status == "exhausted"
    assert result.terminal == terminal
    assert result.attempts == 3
    assert persisted == []
    assert len(result.errors) == 3
    assert all("rejected" in e for e in result.errors)


def test_unparseable_output_counts_as_rejection():
    executor = FakeExecutor(["this is not json", json.dumps({"ok": 1})])
    persisted = []

    result = invoke_shim.run_role(
        role="knowledge-miner",
        brief="B",
        persist=_persist_recorder(persisted),
        executor=executor,
    )

    assert result.status == "ok"
    assert result.attempts == 2
    assert persisted == [{"ok": 1}]
    # The parse failure travels back to the model as the rejection error.
    assert "JSON" in executor.calls[1][0] or "json" in executor.calls[1][0]


def test_code_fenced_json_is_accepted_without_retry():
    fenced = "```json\n" + json.dumps({"nuggets": []}) + "\n```"
    executor = FakeExecutor([fenced])
    persisted = []

    result = invoke_shim.run_role(
        role="knowledge-miner",
        brief="B",
        persist=_persist_recorder(persisted),
        executor=executor,
    )

    assert result.status == "ok"
    assert result.attempts == 1
    assert persisted == [{"nuggets": []}]


def test_unknown_role_is_an_error():
    with pytest.raises(ValueError, match="unknown role"):
        invoke_shim.run_role(
            role="mystery",
            brief="B",
            persist=lambda p: None,
            executor=FakeExecutor([]),
        )


def test_image_is_passed_through_to_the_executor():
    executor = FakeExecutor([json.dumps({"nuggets": []})])

    invoke_shim.run_role(
        role="image-miner",
        brief="B",
        image="C:/deck/public/extracted/fig1.png",
        persist=lambda p: None,
        executor=executor,
    )

    assert executor.calls[0][1] == "C:/deck/public/extracted/fig1.png"


# ---------- executor config resolution (D44: toolkit defaults, deck override) ----------


def test_toolkit_default_executors_per_role():
    for role in ("knowledge-miner", "image-miner", "slide-composer"):
        spec = invoke_shim.resolve_executor_spec(role, deck=None)
        assert spec["executor"] == "owui"
        assert spec["model"] == "gdpr.gpt-5.6-sol"

    spec = invoke_shim.resolve_executor_spec("storyteller", deck=None)
    assert spec["executor"] == "claude-subagent"


def test_deck_context_executor_block_overrides_default(tmp_path):
    (tmp_path / "deck-context.json").write_text(json.dumps({
        "deck": {"topic": "t"},
        "executors": {"slide-composer": {"executor": "owui", "model": "gpt-5.5"}},
    }), encoding="utf-8")

    overridden = invoke_shim.resolve_executor_spec("slide-composer", deck=tmp_path)
    assert overridden["model"] == "gpt-5.5"

    # Roles without an override keep the toolkit default.
    untouched = invoke_shim.resolve_executor_spec("knowledge-miner", deck=tmp_path)
    assert untouched["model"] == "gdpr.gpt-5.6-sol"


def test_resolve_executor_spec_rejects_unknown_role():
    with pytest.raises(ValueError, match="unknown role"):
        invoke_shim.resolve_executor_spec("mystery", deck=None)


# ---------- OWUI adapter message construction (no network) ----------


def test_owui_messages_text_only():
    ex = invoke_shim.OwuiExecutor(model="gdpr.gpt-5.6-sol", token="jwt")
    messages = ex.build_messages("compose it", image=None)
    assert messages == [{"role": "user", "content": "compose it"}]


def test_owui_messages_with_image_data_url(tmp_path):
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfakebytes")
    ex = invoke_shim.OwuiExecutor(model="gdpr.gpt-5.6-sol", token="jwt")

    messages = ex.build_messages("mine this figure", image=png)

    (msg,) = messages
    text_part, image_part = msg["content"]
    assert text_part == {"type": "text", "text": "mine this figure"}
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_claude_subagent_command_shape_and_no_image():
    ex = invoke_shim.ClaudeSubagentExecutor(model="opus")
    assert ex.build_command() == ["claude", "-p", "--output-format", "json",
                                  "--model", "opus"]
    assert invoke_shim.ClaudeSubagentExecutor().build_command() == [
        "claude", "-p", "--output-format", "json"]
    with pytest.raises(ValueError, match="no image"):
        ex.run("brief", image="x.png")


def test_build_executor_resolves_kinds():
    owui = invoke_shim.build_executor(
        {"executor": "owui", "model": "gdpr.gpt-5.6-sol"})
    assert isinstance(owui, invoke_shim.OwuiExecutor)
    claude = invoke_shim.build_executor({"executor": "claude-subagent"})
    assert isinstance(claude, invoke_shim.ClaudeSubagentExecutor)
    with pytest.raises(ValueError, match="unknown executor kind"):
        invoke_shim.build_executor({"executor": "carrier-pigeon"})


# ---------- error containment (transport failures stay inside the seam) ----------


class ExplodingExecutor:
    def run(self, prompt, image=None):
        raise RuntimeError("OWUI HTTP 502: bad gateway")


def test_executor_failure_becomes_status_error_not_a_crash():
    result = invoke_shim.run_role(
        role="knowledge-miner",
        brief="B",
        persist=lambda p: None,
        executor=ExplodingExecutor(),
    )
    assert result.status == "error"
    assert result.terminal is None
    assert any("502" in e for e in result.errors)


def test_persist_gate_is_not_retried():
    """A non-retryable persist failure (km exit 3 = budget_full, infra crash)
    must not burn LLM re-invokes — no model output can fix it."""
    executor = FakeExecutor([json.dumps({"ok": 1})] * 3)

    def gate(payload):
        raise invoke_shim.PersistGate('{"error": "budget_full"}')

    result = invoke_shim.run_role(
        role="slide-composer", brief="B", persist=gate, executor=executor)
    assert result.status == "error"
    assert result.attempts == 1          # exactly one invoke, no retries
    assert any("budget_full" in e for e in result.errors)


def test_non_dict_output_counts_as_rejection():
    executor = FakeExecutor([json.dumps([1, 2]), json.dumps({"ok": 1})])
    result = invoke_shim.run_role(
        role="knowledge-miner", brief="B",
        persist=lambda p: None, executor=executor)
    assert result.status == "ok"
    assert result.attempts == 2


def test_fence_with_surrounding_prose_is_accepted():
    reply = ('Here is the corrected output:\n```json\n'
             + json.dumps({"nuggets": []}) + '\n```\nLet me know!')
    executor = FakeExecutor([reply])
    result = invoke_shim.run_role(
        role="knowledge-miner", brief="B",
        persist=lambda p: None, executor=executor)
    assert result.status == "ok"
    assert result.attempts == 1


def test_fence_without_trailing_newline_and_bom_are_tolerated():
    executor = FakeExecutor([
        "﻿```json\n" + json.dumps({"a": 1}) + "```",
    ])
    result = invoke_shim.run_role(
        role="knowledge-miner", brief="B",
        persist=lambda p: None, executor=executor)
    assert result.status == "ok"


# ---------- spec merge semantics (kind change replaces, never leaks) ----------


def test_kind_change_override_does_not_inherit_default_model(tmp_path):
    (tmp_path / "deck-context.json").write_text(json.dumps({
        "executors": {"knowledge-miner": {"executor": "claude-subagent"}},
    }), encoding="utf-8")
    spec = invoke_shim.resolve_executor_spec("knowledge-miner", deck=tmp_path)
    assert spec["executor"] == "claude-subagent"
    assert spec.get("model") != "gdpr.gpt-5.6-sol"   # no leak across kinds


def test_cmd_override_without_command_fails_with_config_error(tmp_path):
    (tmp_path / "deck-context.json").write_text(json.dumps({
        "executors": {"slide-composer": {"executor": "cmd"}},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="deck-context"):
        invoke_shim.resolve_executor_spec("slide-composer", deck=tmp_path)


def test_missing_deck_context_fails_loudly():
    with pytest.raises(ValueError, match="deck-context.json"):
        invoke_shim.resolve_executor_spec(
            "knowledge-miner", deck=Path("Z:/no/such/deck"))


def test_deck_context_with_bom_is_accepted(tmp_path):
    body = json.dumps({"executors": {
        "slide-composer": {"executor": "owui", "model": "gpt-5.5"}}})
    (tmp_path / "deck-context.json").write_bytes(
        b"\xef\xbb\xbf" + body.encode("utf-8"))
    spec = invoke_shim.resolve_executor_spec("slide-composer", deck=tmp_path)
    assert spec["model"] == "gpt-5.5"


def test_spec_timeout_is_plumbed_into_the_executor():
    ex = invoke_shim.build_executor(
        {"executor": "owui", "model": "m", "timeout": 42})
    assert ex.timeout == 42


def test_role_registry_views_agree():
    assert set(invoke_shim.ROLE_TERMINALS) == set(invoke_shim.DEFAULT_EXECUTORS)


def test_designer_roles_have_default_executors():
    for role in ("text-designer", "diagram-designer", "image-designer"):
        assert role in invoke_shim.ROLES
    assert invoke_shim.DEFAULT_EXECUTORS["text-designer"]["model"] == "gdpr.gpt-5.6-sol"
    assert invoke_shim.DEFAULT_EXECUTORS["diagram-designer"]["model"] == "gdpr.gpt-5.6-sol"
    assert invoke_shim.DEFAULT_EXECUTORS["image-designer"]["model"] == "nano-banana-pro"


def test_deck_overrides_designer_model(tmp_path):
    ctx = tmp_path / "deck-context.json"
    ctx.write_text(json.dumps({"executors": {
        "image-designer": {"executor": "owui", "model": "some-other-image-model"}}}),
        encoding="utf-8")
    spec = invoke_shim.resolve_executor_spec("image-designer", tmp_path)
    assert spec["model"] == "some-other-image-model"


# ---------- image capability is declared, not discovered by crashing ----------


def test_supports_image_declarations():
    assert invoke_shim.OwuiExecutor(model="m", token="t").supports_image
    assert not invoke_shim.ClaudeSubagentExecutor().supports_image
    assert not invoke_shim.CmdExecutor(["tool"]).supports_image
    assert invoke_shim.CmdExecutor(["tool", "{image}"]).supports_image


def test_last_fence_wins_when_a_reply_quotes_an_example_first():
    reply = ("The problem was this output:\n```json\n"
             + json.dumps({"nuggets": "WRONG-EXAMPLE"})
             + "\n```\nHere is the corrected output:\n```json\n"
             + json.dumps({"nuggets": []}) + "\n```")
    assert invoke_shim.parse_structured(reply) == {"nuggets": []}


def test_non_dict_deck_context_override_is_a_clean_config_error(tmp_path):
    (tmp_path / "deck-context.json").write_text(json.dumps({
        "executors": {"knowledge-miner": "claude-subagent"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="must be an object"):
        invoke_shim.resolve_executor_spec("knowledge-miner", deck=tmp_path)


def test_mutating_default_executors_view_does_not_poison_registry():
    invoke_shim.DEFAULT_EXECUTORS["knowledge-miner"]["model"] = "poisoned"
    try:
        spec = invoke_shim.resolve_executor_spec("knowledge-miner", deck=None)
        assert spec["model"] == "gdpr.gpt-5.6-sol"
    finally:
        invoke_shim.DEFAULT_EXECUTORS["knowledge-miner"]["model"] = \
            "gdpr.gpt-5.6-sol"


def test_cmd_executor_with_placeholder_requires_an_image():
    ex = invoke_shim.CmdExecutor(["tool", "{image}"])
    with pytest.raises(ValueError, match="no.*image was given"):
        ex.run("prompt")


def test_cmd_executor_substitutes_image_placeholder(tmp_path):
    marker = tmp_path / "seen.txt"
    cmd = [sys.executable, "-c",
           "import sys, pathlib; pathlib.Path(sys.argv[2]).write_text(sys.argv[1]); "
           "print('{}')",
           "{image}", str(marker)]
    ex = invoke_shim.CmdExecutor(cmd)
    ex.run("prompt", image="C:/x/fig.png")
    assert marker.read_text() == "C:/x/fig.png"


# ---------- CLI (what the /draft-deck orchestrator calls) ----------

SHIM = Path(__file__).resolve().parents[1] / "scripts" / "invoke_shim.py"


def _cli_deck(tmp_path, canned_output):
    """A deck whose knowledge-miner runs a canned `cmd` executor (no network)."""
    echo = f"import sys; sys.stdout.write({canned_output!r})"
    (tmp_path / "deck-context.json").write_text(json.dumps({
        "deck": {"topic": "t"},
        "executors": {"knowledge-miner": {
            "executor": "cmd", "command": [sys.executable, "-c", echo]}},
    }), encoding="utf-8")
    return tmp_path


def _run_cli(deck, brief, persist_argv, out):
    return subprocess.run(
        [sys.executable, str(SHIM), "--role", "knowledge-miner",
         "--deck", str(deck), "--brief-file", str(brief), "--out", str(out),
         "--", *persist_argv],
        capture_output=True, text=True, encoding="utf-8")


def test_cli_ok_path_runs_persist_and_writes_result(tmp_path):
    deck = _cli_deck(tmp_path, json.dumps({"nuggets": [{"title": "t"}]}))
    brief = tmp_path / "brief.md"
    brief.write_text("MINE", encoding="utf-8")
    out = tmp_path / "result.json"
    marker = tmp_path / "persisted.json"
    # Persist command: copy {out} to marker, exit 0 (accepted).
    persist = [sys.executable, "-c",
               "import shutil,sys; shutil.copy(sys.argv[1], sys.argv[2])",
               "{out}", str(marker)]

    proc = _run_cli(deck, brief, persist, out)

    assert proc.returncode == 0, proc.stderr
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert result["attempts"] == 1
    # The parsed output must survive in the result JSON — a validate-only
    # persist command must not lose the model's output with the temp dir.
    assert result["output"] == {"nuggets": [{"title": "t"}]}
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "nuggets": [{"title": "t"}]}


def test_cli_requires_out_placeholder_in_persist_cmd(tmp_path):
    deck = _cli_deck(tmp_path, json.dumps({"ok": 1}))
    brief = tmp_path / "brief.md"
    brief.write_text("MINE", encoding="utf-8")
    out = tmp_path / "result.json"

    proc = _run_cli(deck, brief, [sys.executable, "-c", "pass"], out)

    assert proc.returncode == 2          # argparse-level config error
    assert "{out}" in proc.stderr


def test_cli_persist_gate_exits_4_with_result_file(tmp_path):
    deck = _cli_deck(tmp_path, json.dumps({"ok": 1}))
    brief = tmp_path / "brief.md"
    brief.write_text("MINE", encoding="utf-8")
    out = tmp_path / "result.json"
    # Persist exits 3 (km's budget_full convention) → non-retryable gate.
    persist = [sys.executable, "-c",
               "import sys; sys.stdout.write('{\"error\": \"budget_full\"}'); "
               "sys.exit(3)", "{out}"]

    proc = _run_cli(deck, brief, persist, out)

    assert proc.returncode == 4
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "error"
    assert result["attempts"] == 1       # no retries on a gate
    assert any("budget_full" in e for e in result["errors"])


def test_cli_rejects_image_for_non_image_executor(tmp_path):
    deck = _cli_deck(tmp_path, json.dumps({"ok": 1}))
    brief = tmp_path / "brief.md"
    brief.write_text("PLAN", encoding="utf-8")
    out = tmp_path / "result.json"

    proc = subprocess.run(
        [sys.executable, str(SHIM), "--role", "storyteller",
         "--deck", str(tmp_path), "--brief-file", str(brief),
         "--image", "fig.png", "--out", str(out),
         "--", sys.executable, "-c", "pass", "{out}"],
        capture_output=True, text=True, encoding="utf-8")

    assert proc.returncode == 2
    assert "image" in proc.stderr.lower()


def test_cli_exhaustion_exits_3_with_terminal(tmp_path):
    deck = _cli_deck(tmp_path, json.dumps({"bad": True}))
    brief = tmp_path / "brief.md"
    brief.write_text("MINE", encoding="utf-8")
    out = tmp_path / "result.json"
    # Persist command: always reject (exit 1 = retryable) with a message.
    persist = [sys.executable, "-c",
               "import sys; sys.stderr.write('verbatim guard failed'); sys.exit(1)",
               "{out}"]

    proc = _run_cli(deck, brief, persist, out)

    assert proc.returncode == 3
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["status"] == "exhausted"
    assert result["terminal"] == "drop"
    assert result["attempts"] == 3
    assert any("verbatim guard failed" in e for e in result["errors"])
