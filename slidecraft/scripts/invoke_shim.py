"""Invoke shim — the one deliberately nondeterministic seam (SPEC D44, ticket 12).

Every LLM role in the D40 pipeline is a pure function: a self-contained brief
in, structured output out. This module owns the *invoke* stage between the
knowledge manager's deterministic *assemble* and *persist* stages:

    result = run_role(role, brief, persist=..., executor=...)

The shim sends the brief to an executor, parses the structured output, hands
it to the caller's persist callback, and wraps the bounded rejection loop —
on a retryable rejection it re-invokes with the error appended, cap 2
re-invokes, then resolves to the per-role terminal (miner → drop, composer →
park, storyteller → abort) and reports it. The shim never executes the
terminal action itself (parking is a knowledge-manager mutation); it stays
thin.

Failure taxonomy (each lands in ``InvokeResult.status``):

- ``ok``        — output parsed and persisted.
- ``exhausted`` — the model's output kept failing *retryable* validation
                  (``PersistRejection``); the per-role terminal applies.
- ``error``     — infrastructure/gate failure that no re-invoke can fix:
                  executor transport errors (HTTP 5xx/timeout/missing CLI),
                  a persist command that crashes or hits a non-retryable gate
                  (``PersistGate``, e.g. km's exit-3 ``budget_full``). One
                  attempt max is spent discovering it; the orchestrator
                  decides what to do.

Deliberately self-contained (no import of the personal owui skill client):
the toolkit is installed on other machines via the npx installer (D33), so
the transport lives here; the OWUI auth *file* of the skill is reused as a
fallback when present.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


def log_prompt_record(deck, *, slide, section, role, model, executor,
                      attempt, status, prompt, response, run_label=None):
    """Write one durable prompt/response record under the deck's
    logs/prompts/<slide>/ and append a reference to logs/actions.jsonl (§7.1).
    Returns the record path, or None on any I/O failure. STRICTLY best-effort:
    a locked/synced log (OneDrive) must never raise out of a completed invoke."""
    deck = Path(deck)
    slide_key = slide or "_deckwide"
    rec_path = None
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "slide": slide_key,
              "section": section, "role": role, "model": model,
              "executor": executor, "attempt": attempt, "status": status,
              "run_label": run_label, "prompt": prompt, "response": response}
    try:
        pdir = deck / "logs" / "prompts" / slide_key
        pdir.mkdir(parents=True, exist_ok=True)
        seq = len(list(pdir.glob("*.json"))) + 1
        parts = [f"{seq:03d}", role]
        if section:
            parts.append(section)
        if model:
            parts.append(str(model).replace("/", "-").replace(":", "-"))
        rec_path = pdir / ("-".join(parts) + ".json")
        rec_path.write_text(json.dumps(record, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    except OSError:
        return None
    try:
        logdir = deck / "logs"
        logdir.mkdir(exist_ok=True)
        with (logdir / "actions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": record["ts"], "agent": "invoke-shim",
                "action": "prompt-log", "role": role, "slide": slide_key,
                "section": section, "attempt": attempt, "status": status,
                "record": str(rec_path.relative_to(deck)).replace("\\", "/"),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return rec_path


class PersistRejection(Exception):
    """Raised by a persist callback when the deterministic layer rejects the
    LLM's output for a *fixable* reason (verbatim guard, layout/asset/schema
    validation). Flows through the bounded retry loop."""


class PersistGate(Exception):
    """Raised by a persist callback for a *non-retryable* failure — a gate
    (km exit 3 = ``budget_full``) or an infrastructure crash. No model output
    can fix it, so the shim spends no re-invokes on it."""


@dataclass
class InvokeResult:
    role: str
    status: str                # "ok" | "exhausted" | "error"
    attempts: int
    output: dict | None = None
    terminal: str | None = None   # None | "drop" | "park" | "abort"
    errors: list[str] = field(default_factory=list)


# ---------- role registry (single source: terminal + default executor) ----------

# One registry so the views cannot drift (adding a role touches one place).
# Terminals (D44): a rejected nugget is dropped (nothing exists to park), a
# rejected composition parks its slide, a rejected plan aborts the draft run.
ROLES = {
    "knowledge-miner": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "image-miner": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "slide-composer": {
        "terminal": "park",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "storyteller": {
        "terminal": "abort",
        "executor": {"executor": "claude-subagent", "model": None},
    },
    "text-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "diagram-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "gdpr.gpt-5.6-sol"},
    },
    "image-designer": {
        "terminal": "drop",
        "executor": {"executor": "owui", "model": "nano-banana-pro"},
    },
}

# Derived views (kept for a stable public surface). The executor dicts are
# copies — mutating a view must never poison the ROLES registry.
ROLE_TERMINALS = {name: r["terminal"] for name, r in ROLES.items()}
DEFAULT_EXECUTORS = {name: dict(r["executor"]) for name, r in ROLES.items()}

RETRY_CAP = 2  # re-invokes after the initial attempt

_RETRY_TEMPLATE = (
    "{brief}\n\n"
    "## Previous attempt rejected\n\n"
    "Your previous output was rejected by validation with this error:\n\n"
    "{error}\n\n"
    "Fix the problem and resend the complete corrected output."
)


def _validate_spec(role: str, spec: dict) -> dict:
    """Reject malformed executor specs with an error naming the config
    surface (the deck-context ``executors`` block) instead of a deep
    KeyError at build time."""
    kind = spec.get("executor")
    where = f"executor spec for role {role!r} (deck-context 'executors' block)"
    if kind == "owui" and not spec.get("model"):
        raise ValueError(f"{where}: kind 'owui' requires a 'model'")
    if kind == "cmd" and not spec.get("command"):
        raise ValueError(f"{where}: kind 'cmd' requires a 'command' argv list")
    if kind not in ("owui", "claude-subagent", "cmd"):
        raise ValueError(f"{where}: unknown executor kind {kind!r}")
    return spec


def resolve_executor_spec(role: str, deck: Path | None) -> dict:
    """The executor spec for *role*: toolkit default, overridden per role by
    the deck context's ``executors`` block.

    Merge semantics: same executor kind → key-level merge (override wins);
    a *different* kind → the override **replaces** the default outright, so
    stale keys (e.g. the OWUI model) never leak into another kind's spec.
    A given ``deck`` must contain ``deck-context.json`` (D25: fail loudly).
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")
    spec = dict(ROLES[role]["executor"])
    if deck is not None:
        ctx_path = Path(deck) / "deck-context.json"
        if not ctx_path.exists():
            raise ValueError(
                f"no deck-context.json under {deck} — not an initialized "
                "deck (run /init-deck), or a wrong --deck path")
        # utf-8-sig: tolerate the BOM that PowerShell 5.1 / Notepad write.
        ctx = json.loads(ctx_path.read_text(encoding="utf-8-sig"))
        block = ctx.get("executors", {})
        if not isinstance(block, dict):
            raise ValueError(
                "deck-context 'executors' must be an object of per-role "
                f"specs, got {type(block).__name__}")
        override = block.get(role)
        if override is not None and not isinstance(override, dict):
            raise ValueError(
                f"deck-context 'executors' entry for role {role!r} must be "
                f"an object like {{\"executor\": ..., \"model\": ...}}, got "
                f"{type(override).__name__}")
        if override:
            if override.get("executor", spec["executor"]) != spec["executor"]:
                spec = dict(override)          # kind change: replace, no leak
            else:
                spec.update(override)
    return _validate_spec(role, spec)


def parse_structured(raw: str) -> dict:
    """Parse a role's structured output into a dict, tolerating a BOM,
    a markdown code fence, and prose around the fence.

    Raises :class:`PersistRejection` on anything unparseable so a malformed
    reply flows through the same retry loop as a validation failure.
    """
    text = raw.lstrip("﻿").strip()
    # Fenced blocks, prose around them allowed, trailing newline before the
    # closing fence optional. Tried LAST fence first: a retry reply often
    # quotes the rejected example in an early fence and puts the corrected
    # payload in the final one. Whole text is the last resort.
    fences = re.findall(r"```[a-zA-Z]*[ \t]*\n(.*?)```", text, re.DOTALL)
    candidates = [f.strip() for f in reversed(fences)] + [text]
    last_exc = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
            continue
        if not isinstance(parsed, dict):
            raise PersistRejection(
                "output must be a single JSON object, got "
                f"{type(parsed).__name__}; reply with one JSON object and "
                "nothing else")
        return parsed
    raise PersistRejection(
        f"output is not valid JSON ({last_exc}); reply with a single JSON "
        "object and nothing else") from last_exc


# ---------- executors ----------

class OwuiExecutor:
    """OpenAI-compatible chat against an Open WebUI deployment.

    Auth AND endpoint reuse the owui skill's mechanism: an explicit value,
    else the environment (``OPENWEBUI_TOKEN`` / ``OPENWEBUI_BASE_URL``), else
    the skill's ``.env``. Neither is baked in — the deployment URL is
    site-specific and lives in config, never in the repo. Resolution is lazy
    (at ``run`` time) so construction is network- and auth-free for tests. An
    image travels as a base64 data-URL content part; the encoding is
    memoized so retries do not re-read/re-encode the file.
    """

    supports_image = True

    def __init__(self, model, token=None, base_url=None, timeout=300):
        self.model = model
        self._token = token
        self._base_url = base_url
        self.timeout = timeout
        self._session = None
        self._image_cache: dict[str, str] = {}

    @staticmethod
    def _env_fallback_path() -> Path:
        # Lazy: Path.home() can raise in stripped service environments —
        # confine that to the one code path that needs the fallback.
        return Path.home() / ".claude" / "skills" / "owui" / ".env"

    def _read_env_fallback(self, key: str) -> str:
        path = self._env_fallback_path()
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip().removeprefix("export ").strip()
                if stripped.startswith(f"{key}="):
                    return stripped.split("=", 1)[1].strip().strip('"').strip("'")
        return ""

    @property
    def base_url(self) -> str:
        url = (self._base_url or os.getenv("OPENWEBUI_BASE_URL")
               or self._read_env_fallback("OPENWEBUI_BASE_URL"))
        if not url:
            raise RuntimeError(
                "No OWUI base URL: pass base_url=, set OPENWEBUI_BASE_URL, or "
                f"add it to the owui skill's .env at {self._env_fallback_path()}")
        return url.rstrip("/")

    def _resolve_token(self) -> str:
        if self._token:
            return self._token
        token = (os.getenv("OPENWEBUI_TOKEN", "")
                 or self._read_env_fallback("OPENWEBUI_TOKEN"))
        if not token:
            raise RuntimeError(
                "No OWUI token: pass token=, set OPENWEBUI_TOKEN, or keep "
                f"the owui skill's .env at {self._env_fallback_path()}")
        self._token = token
        return token

    def _image_part(self, image) -> dict:
        key = str(image)
        if key not in self._image_cache:
            p = Path(image)
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            b64 = base64.b64encode(p.read_bytes()).decode()
            self._image_cache[key] = f"data:{mime};base64,{b64}"
        return {"type": "image_url", "image_url": {"url": self._image_cache[key]}}

    def build_messages(self, prompt, image=None):
        if image is None:
            return [{"role": "user", "content": prompt}]
        return [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            self._image_part(image),
        ]}]

    def run(self, prompt, image=None) -> str:
        import requests
        if self._session is None:
            self._session = requests.Session()
        resp = self._session.post(
            f"{self.base_url}/api/chat/completions",
            headers={"Authorization": f"Bearer {self._resolve_token()}",
                     "Content-Type": "application/json"},
            json={"model": self.model,
                  "messages": self.build_messages(prompt, image),
                  "stream": False},
            timeout=self.timeout,
        )
        if resp.status_code == 401:
            raise RuntimeError(
                "OWUI 401 — the JWT has expired or been revoked. Re-copy "
                "localStorage['token'] from the browser into the owui "
                "skill's .env (OPENWEBUI_TOKEN=...).")
        if not resp.ok:
            raise RuntimeError(
                f"OWUI HTTP {resp.status_code}: {resp.text[:500]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"OWUI response shape unexpected ({exc}); "
                f"body: {resp.text[:500]}") from exc
        if isinstance(content, list):  # some models return content parts
            content = "".join(part.get("text", "") for part in content
                              if isinstance(part, dict))
        return content or ""


class ClaudeSubagentExecutor:
    """Runs the brief as a fresh headless Claude session (`claude -p`).

    The storyteller is a pure planner — text in, JSON out, no tools — so a
    print-mode CLI run *is* its subagent: fresh context every invoke. The
    brief travels via stdin (never as an argv payload — D28).
    """

    supports_image = False

    def __init__(self, model=None, timeout=1200):
        self.model = model
        self.timeout = timeout
        self._exe = None

    def build_command(self) -> list[str]:
        cmd = ["claude", "-p", "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def run(self, prompt, image=None) -> str:
        import shutil
        import subprocess
        if image is not None:
            raise ValueError("claude-subagent executor takes no image")
        if self._exe is None:
            self._exe = shutil.which("claude")
            if not self._exe:
                raise RuntimeError("claude CLI not found on PATH")
        cmd = self.build_command()
        cmd[0] = self._exe
        proc = subprocess.run(cmd, input=prompt, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude -p exited {proc.returncode}: {proc.stderr[:500]}")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"claude -p stdout is not the JSON envelope ({exc}); "
                f"stdout: {proc.stdout[:500]}") from exc
        # --output-format json can exit 0 with an error envelope
        # (subtype error_max_turns / error_during_execution, no "result").
        if envelope.get("is_error") or "result" not in envelope:
            raise RuntimeError(
                "claude -p returned an error envelope "
                f"(subtype={envelope.get('subtype')!r}): "
                f"{json.dumps(envelope)[:500]}")
        return envelope["result"]


class CmdExecutor:
    """Runs an arbitrary command as the executor: the prompt goes to stdin,
    stdout is the raw output. The escape hatch for local models/tools — and
    what keeps the CLI testable without any network.

    Image capability is explicit: the command must contain an ``{image}``
    placeholder (substituted with the image path). Without one the executor
    declares ``supports_image = False`` — never silently appended argv.
    """

    def __init__(self, command: list[str], timeout=1200):
        self.command = list(command)
        self.timeout = timeout

    @property
    def supports_image(self) -> bool:
        return any("{image}" in arg for arg in self.command)

    def run(self, prompt, image=None) -> str:
        import subprocess
        if image is not None and not self.supports_image:
            raise ValueError(
                "cmd executor has no {image} placeholder but got an image")
        if image is None and self.supports_image:
            raise ValueError(
                "cmd executor command expects an {image} placeholder but no "
                "image was given")
        cmd = [arg.replace("{image}", str(image)) if image is not None else arg
               for arg in self.command]
        proc = subprocess.run(cmd, input=prompt, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"cmd executor exited {proc.returncode}: {proc.stderr[:500]}")
        return proc.stdout


def build_executor(spec: dict):
    """An executor instance from a validated spec (``resolve_executor_spec``).
    An optional ``timeout`` in the spec reaches the executor."""
    kind = spec.get("executor")
    extra = {}
    if spec.get("timeout") is not None:
        extra["timeout"] = spec["timeout"]
    if kind == "owui":
        return OwuiExecutor(model=spec["model"],
                            base_url=spec.get("base_url"), **extra)
    if kind == "claude-subagent":
        return ClaudeSubagentExecutor(model=spec.get("model"), **extra)
    if kind == "cmd":
        return CmdExecutor(command=spec["command"], **extra)
    raise ValueError(f"unknown executor kind: {kind!r}")


# ---------- the loop ----------

def run_role(role, brief, *, persist, executor, image=None, retry_cap=RETRY_CAP,
            on_attempt=None):
    """Run one role invocation through the bounded executor + persist loop.

    Each attempt is stateless: the retry prompt is the original brief with
    the rejection error appended, never a conversation. Transport failures
    and persist gates resolve to ``status="error"`` (contained, reported) —
    they never raise out of this function and never burn re-invokes.

    ``on_attempt(prompt, raw, attempt)``, when given, is called once per
    attempt (including retries) before persist — so a durable prompt/response
    log can capture every attempt, not just the terminal one (§7.1).
    """
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")
    errors: list[str] = []
    prompt = brief
    attempt = 0
    for attempt in range(1, retry_cap + 2):
        try:
            raw = executor.run(prompt, image=image)
        except Exception as exc:  # transport/infra — no re-invoke can fix it
            errors.append(f"executor failure: {exc}")
            if on_attempt:
                try:
                    on_attempt(prompt, f"<executor failure: {exc}>", attempt)
                except Exception:
                    pass  # a logging callback must never break the invoke loop
            return InvokeResult(role=role, status="error", attempts=attempt,
                                errors=errors)
        if on_attempt:
            try:
                on_attempt(prompt, raw, attempt)
            except Exception:
                pass  # a logging callback must never break the invoke loop
        try:
            output = parse_structured(raw)
            persist(output)
        except PersistRejection as exc:
            errors.append(str(exc))
            prompt = _RETRY_TEMPLATE.format(brief=brief, error=exc)
            continue
        except PersistGate as exc:
            errors.append(f"persist gate: {exc}")
            return InvokeResult(role=role, status="error", attempts=attempt,
                                errors=errors)
        return InvokeResult(role=role, status="ok", attempts=attempt,
                            output=output, errors=errors)
    return InvokeResult(role=role, status="exhausted", attempts=retry_cap + 1,
                        terminal=ROLES[role]["terminal"], errors=errors)


# ---------- CLI (the orchestrator's entry point) ----------

def _persist_via_command(argv: list[str], workdir: Path):
    """A persist callback that runs *argv* with ``{out}`` replaced by a temp
    file holding the parsed output JSON.

    Exit-code convention (mirrors km): **exit 1** = retryable validation
    rejection (stderr/stdout is the error fed back to the model); **any
    other non-zero** = non-retryable gate/infra (km exit 3 = budget_full) →
    ``PersistGate``. A missing executable or a hung command is infra too.
    """
    import subprocess

    def persist(payload):
        cmd = None
        try:
            out_file = workdir / "invoke-output.json"
            out_file.write_text(json.dumps(payload, indent=2,
                                           ensure_ascii=False),
                                encoding="utf-8")
            cmd = [arg.replace("{out}", str(out_file)) for arg in argv]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  stdin=subprocess.DEVNULL, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise PersistGate(f"persist command timed out: {exc}") from exc
        except OSError as exc:
            # FileNotFoundError, PermissionError, WinError 193 (not a valid
            # Win32 application), disk-full on the payload write — all infra.
            raise PersistGate(
                f"persist infrastructure failure ({cmd or 'payload write'}): "
                f"{exc}") from exc
        if proc.returncode == 0:
            return
        error = (proc.stderr.strip() or proc.stdout.strip()
                 or f"persist command exited {proc.returncode}")
        if proc.returncode == 1:
            raise PersistRejection(error)
        raise PersistGate(f"exit {proc.returncode}: {error}")

    return persist


def main(argv=None):
    import argparse
    import tempfile

    ap = argparse.ArgumentParser(
        description="Invoke one LLM role over a km-assembled brief (D44). "
                    "Everything after '--' is the persist command; '{out}' in "
                    "it is replaced by the path of the output-JSON temp file. "
                    "Persist exit 1 = retryable rejection; other non-zero = "
                    "non-retryable gate. Shim exit: 0 ok, 3 exhausted "
                    "(terminal applies), 4 error.")
    ap.add_argument("--role", required=True, choices=sorted(ROLES))
    ap.add_argument("--brief-file", required=True,
                    help="path to the assembled brief (D28: file, not arg)")
    ap.add_argument("--image", help="image path for vision roles")
    ap.add_argument("--deck", help="deck root (executor overrides from "
                                   "deck-context.json; must be initialized)")
    ap.add_argument("--out", required=True,
                    help="where to write the InvokeResult JSON")
    ap.add_argument("--slide", help="slide id (prompt-log grouping)")
    ap.add_argument("--section", help="section role (designer prompt-log)")
    ap.add_argument("--run-label", dest="run_label",
                    help="optional label to tag this run's prompt records")
    ap.add_argument("persist_cmd", nargs=argparse.REMAINDER,
                    help="-- persist command argv with {out} placeholder")
    a = ap.parse_args(argv)

    persist_argv = list(a.persist_cmd)
    if persist_argv[:1] == ["--"]:       # strip only the leading separator
        persist_argv = persist_argv[1:]
    if not persist_argv:
        ap.error("a persist command is required after '--'")
    if not any("{out}" in arg for arg in persist_argv):
        ap.error("the persist command must contain the {out} placeholder "
                 "(the path of the parsed-output JSON file)")

    try:
        spec = resolve_executor_spec(a.role, Path(a.deck) if a.deck else None)
        executor = build_executor(spec)
    except ValueError as exc:
        ap.error(str(exc))
    if a.image and not getattr(executor, "supports_image", False):
        ap.error(f"--image given but the {spec['executor']!r} executor for "
                 f"role {a.role!r} takes no image")

    # Fail on an unwritable --out BEFORE spending an LLM invoke: the result
    # file is the orchestrator's only record of what happened.
    out_path = Path(a.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.touch()
    except OSError as exc:
        ap.error(f"--out {a.out} is not writable: {exc}")

    brief = Path(a.brief_file).read_text(encoding="utf-8-sig")

    def _on_attempt(prompt, raw, attempt):
        if a.deck:
            log_prompt_record(
                a.deck, slide=a.slide, section=a.section, role=a.role,
                model=spec.get("model"), executor=spec.get("executor"),
                attempt=attempt, status="attempt", prompt=prompt,
                response=raw, run_label=a.run_label)

    with tempfile.TemporaryDirectory(prefix="invoke-shim-") as tmp:
        result = run_role(
            a.role, brief,
            persist=_persist_via_command(persist_argv, Path(tmp)),
            executor=executor,
            image=a.image,
            on_attempt=_on_attempt,
        )

    out_path.write_text(json.dumps({
        "role": result.role, "status": result.status,
        "attempts": result.attempts, "terminal": result.terminal,
        "errors": result.errors, "output": result.output,
        "executor": spec,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    if a.deck:  # deck audit trail (mirrors km's actions.jsonl convention)
        # Best effort: a locked/synced log file (OneDrive) must never turn a
        # completed invoke into a bogus failure exit after state mutated.
        import sys
        import time
        try:
            logdir = Path(a.deck) / "logs"
            logdir.mkdir(exist_ok=True)
            with (logdir / "actions.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "agent": "invoke-shim", "action": "invoke",
                    "role": result.role, "status": result.status,
                    "attempts": result.attempts, "terminal": result.terminal,
                    "executor": spec.get("executor"),
                    "model": spec.get("model"),
                }, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"warning: could not append to logs/actions.jsonl: {exc}",
                  file=sys.stderr)

    return {"ok": 0, "exhausted": 3, "error": 4}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
