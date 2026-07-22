"""serve_deck decision logic (2026-07-22 live-drafting-preview). The npx-slidev
spawn is not exercised here; the readiness + reuse decisions are."""
from __future__ import annotations

import json
from pathlib import Path

from slidecraft.scripts import serve_deck


def _mk_deck(tmp_path: Path) -> Path:
    (tmp_path / "logs").mkdir()
    (tmp_path / "slides.md").write_text("---\ntheme: default\n---\n",
                                        encoding="utf-8")
    return tmp_path


def _make_bin(root: Path) -> Path:
    d = root / "node_modules" / ".bin"
    d.mkdir(parents=True)
    b = d / ("slidev.cmd" if serve_deck.IS_WINDOWS else "slidev")
    b.write_text("", encoding="utf-8")
    return b


def test_ready_when_bin_present(tmp_path):
    root = _mk_deck(tmp_path)
    _make_bin(root)
    calls = []
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: calls.append("sleep"),
        runner=lambda *a, **k: calls.append("run")) == "ready"
    assert calls == []                                  # no poll, no install


def test_polls_then_ready_when_install_in_flight(tmp_path):
    root = _mk_deck(tmp_path)
    (root / "node_modules").mkdir()                     # npm started; no bin yet
    seq = [None, None, root / "node_modules" / ".bin" / "slidev"]
    it = iter(seq)
    ran = []
    status = serve_deck.ensure_ready(
        root, poll_attempts=5, sleep=lambda _s: None,
        bin_check=lambda _r: next(it),
        runner=lambda *a, **k: ran.append(a) or _Rc(0))
    assert status == "ready"
    assert ran == []                                    # never installed ourselves


def test_installs_when_no_node_modules(tmp_path):
    root = _mk_deck(tmp_path)

    def fake_run(cmd, **k):
        _make_bin(root)                                 # the install "succeeds"
        return _Rc(0)

    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None,
        npm_lookup=lambda: "npm", runner=fake_run) == "ready"


def test_no_npm_returns_no_npm(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None, npm_lookup=lambda: None,
        runner=lambda *a, **k: _Rc(0)) == "no-npm"


def test_install_failure_returns_install_failed(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None, npm_lookup=lambda: "npm",
        runner=lambda *a, **k: _Rc(1)) == "install-failed"


def test_server_status_none_stale_live(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.server_status(root)[0] == "none"

    serve_deck.write_pidfile(root, 4242, 3030)
    assert serve_deck.server_status(
        root, alive=lambda _p: False)[0] == "stale"
    assert serve_deck.server_status(
        root, alive=lambda _p: True, is_port_open=lambda *a, **k: True
    )[0] == "live"


class _Rc:
    def __init__(self, code): self.returncode = code
