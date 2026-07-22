#!/usr/bin/env python
"""The atomic expert unit (design §7): build ONE content area of a slide.

  km design-brief  →  the designer's OWUI executor  →  (image: download)  →
  km place-design

Idempotent and independently runnable — the human-in-the-loop re-generates a
single image / redoes a single diagram by re-running this. Every attempt's
prompt + response is logged under the deck's logs/prompts/ (§7.1). The script
owns the OWUI loop (D7); the lead never hand-loops a designer.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from slidecraft.scripts import invoke_shim

KM = str(Path(__file__).resolve().parent / "km.py")

_DATA_URI_RE = re.compile(r"data:(image/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=\s]+)", re.I)
_MD_IMG_RE = re.compile(r"!\[[^\]]*\]\((\S+?)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")


def download_image(reply: str, dest: Path) -> Path:
    """Write an image from a designer reply: a data: URI, a markdown ![](url)
    link, or a bare URL. Raises ValueError when nothing image-like is found."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    m = _DATA_URI_RE.search(reply)
    if m:
        dest.write_bytes(base64.b64decode(re.sub(r"\s+", "", m.group(2))))
        return dest
    url_m = _MD_IMG_RE.search(reply) or _BARE_URL_RE.search(reply)
    if url_m:
        import requests
        url = url_m.group(1) if url_m.re is _MD_IMG_RE else url_m.group(0)
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    raise ValueError("designer reply carried no data URI, markdown image, or URL")


def _run_km(deck: Path, *args) -> dict:
    proc = subprocess.run([sys.executable, KM, "--deck", str(deck), *args],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip()
                           or f"km {args[0]} exited {proc.returncode}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def design_one(deck: Path, slide: str, section: str, *, run_label=None,
               retry: int = 2) -> dict:
    """Build one content area end-to-end. Returns a status dict; on exhaustion
    leaves the wireframe visible and returns status 'failed' (§10)."""
    deck = Path(deck)
    with tempfile.TemporaryDirectory(prefix="design-") as td:
        tmp = Path(td)
        brief_out = tmp / "brief.md"
        info = _run_km(deck, "design-brief", "--slide", slide,
                       "--section", section, "--out", str(brief_out))
        stype, role = info["type"], info["role"]
        brief = brief_out.read_text(encoding="utf-8-sig")
        spec = invoke_shim.resolve_executor_spec(role, deck)
        executor = invoke_shim.build_executor(spec)

        errors = []
        for attempt in range(1, retry + 2):
            try:
                reply = executor.run(brief, image=None)
            except Exception as exc:                       # transport/infra
                errors.append(f"executor failure: {exc}")
                invoke_shim.log_prompt_record(
                    deck, slide=slide, section=section, role=role,
                    model=spec.get("model"), executor=spec.get("executor"),
                    attempt=attempt, status="error", prompt=brief,
                    response=f"<{exc}>", run_label=run_label)
                break
            invoke_shim.log_prompt_record(
                deck, slide=slide, section=section, role=role,
                model=spec.get("model"), executor=spec.get("executor"),
                attempt=attempt, status="attempt", prompt=brief,
                response=reply, run_label=run_label)
            reply_file = tmp / "reply.txt"
            reply_file.write_text(reply, encoding="utf-8")
            place = ["place-design", "--slide", slide, "--section", section,
                     "--type", stype, "--file", str(reply_file)]
            try:
                if stype == "image":
                    ext = "png"
                    asset_rel = f"/gen/{slide}_{section}.{ext}"
                    download_image(reply, deck / "public" / "gen"
                                   / f"{slide}_{section}.{ext}")
                    place += ["--asset", asset_rel]
                out = _run_km(deck, *place)
                return {"ok": True, "slide": slide, "section": section,
                        "type": stype, "status": "placed",
                        "attempts": attempt, "errors": errors,
                        "slide_state": out.get("slide_state")}
            except (RuntimeError, ValueError) as exc:      # retryable placement
                errors.append(str(exc))
                continue
        return {"ok": False, "slide": slide, "section": section, "type": stype,
                "status": "failed", "attempts": retry + 1, "errors": errors}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slide", required=True)
    ap.add_argument("--section", required=True)
    ap.add_argument("--run-label", dest="run_label", default=None)
    a = ap.parse_args(argv)
    res = design_one(Path(a.deck), a.slide, a.section, run_label=a.run_label)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
