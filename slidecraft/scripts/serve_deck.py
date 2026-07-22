#!/usr/bin/env python
"""Background live Slidev server for /draft-deck — ensure-ready, then serve.

Launched in the background at the start of /draft-deck, concurrently with mining
(2026-07-22 live-drafting-preview). It:

  1. Reuses an already-running server for this deck (pidfile + port check) so a
     re-draft never starts a second one.
  2. Ensures node_modules is installed: if the slidev binary is present, serve;
     if an install looks in-flight (node_modules/ exists but no binary yet, i.e.
     /init-deck's background `npm install`), poll for the binary; otherwise run
     `npm install` here. If Node/npm is unavailable, report 'no-preview' so
     /draft-deck skips live preview and drafts normally.
  3. Serves `npx slidev slides.md --open` and records logs/serve_deck.json.

Decision logic (readiness, reuse) is pure and unit-tested; the spawn is a thin
documented tail.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PIDFILE = "logs/serve_deck.json"
DEFAULT_PORT = 3030


def slidev_bin(root: Path) -> Path | None:
    name = "slidev.cmd" if IS_WINDOWS else "slidev"
    p = root / "node_modules" / ".bin" / name
    return p if p.exists() else None


def npm_executable() -> str | None:
    return shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")


def ensure_ready(root: Path, *, poll_attempts: int = 120, poll_interval: float = 1.0,
                 sleep=time.sleep, bin_check=slidev_bin,
                 npm_lookup=npm_executable, runner=subprocess.run) -> str:
    """Return 'ready' | 'no-npm' | 'install-failed'. Waits for an in-flight
    install (node_modules present, binary not yet), else installs here."""
    if bin_check(root):
        return "ready"
    if (root / "node_modules").is_dir():
        for _ in range(poll_attempts):
            sleep(poll_interval)
            if bin_check(root):
                return "ready"
        # install stalled/never finished — fall through and repair below.
    npm = npm_lookup()
    if not npm:
        return "no-npm"
    proc = runner([npm, "install", "--no-audit", "--no-fund"],
                  cwd=str(root))
    if getattr(proc, "returncode", 1) != 0:
        return "install-failed"
    return "ready" if bin_check(root) else "install-failed"


def read_pidfile(root: Path) -> dict | None:
    p = root / PIDFILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_pidfile(root: Path, pid: int, port: int) -> None:
    (root / "logs").mkdir(exist_ok=True)
    (root / PIDFILE).write_text(json.dumps(
        {"pid": pid, "port": port, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
        encoding="utf-8")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="ignore")
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def server_status(root: Path, *, alive=pid_alive, is_port_open=port_open):
    """('live'|'stale'|'none', pidfile_or_None). Live iff the recorded pid is
    running AND its port answers."""
    info = read_pidfile(root)
    if not info:
        return "none", None
    pid, port = int(info.get("pid", 0)), int(info.get("port", 0))
    if alive(pid) and port and is_port_open(port):
        return "live", info
    return "stale", info


def _spawn_slidev(root: Path, port: int, open_browser: bool) -> int:
    """Start `npx slidev slides.md --open --port <port>` detached. Returns pid.
    This is the untested tail — verified by a live /draft-deck run."""
    cmd = ["npx", "slidev", "slides.md", "--port", str(port)]
    if open_browser:
        cmd.append("--open")
    if IS_WINDOWS:
        cmd[0] = "npx.cmd"
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        proc = subprocess.Popen(cmd, cwd=str(root), creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc = subprocess.Popen(cmd, cwd=str(root), start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", default=".")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--ready-timeout", type=int, default=120,
                    help="seconds to wait for an in-flight npm install")
    a = ap.parse_args(argv)
    root = Path(a.deck).resolve()

    state, info = server_status(root)
    if state == "live":
        _emit({"status": "reused", "port": info.get("port")})
        return 0

    ready = ensure_ready(root, poll_attempts=max(1, a.ready_timeout))
    if ready != "ready":
        _emit({"status": "no-preview", "reason": ready})
        return 1

    pid = _spawn_slidev(root, a.port, open_browser=not a.no_open)
    write_pidfile(root, pid, a.port)
    _emit({"status": "served", "pid": pid, "port": a.port})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
