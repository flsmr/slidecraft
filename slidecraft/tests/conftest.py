"""Shared fixtures for the km pipeline-seam tests (tickets 13/15/16).

Builds a real (tmp) deck the way the pipeline would see it: a local theme with
a semantic-layouts contract, a scaffolded deck, and a converted text source —
so every test asserts at the km CLI seam over genuine deck state, never over
mocks of it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scripts import scaffold_deck, source_converter


def make_theme(root: Path) -> Path:
    """A local theme with cryptic physical slots + a semantic-layouts map,
    covering the four slide types (cover/content/two-cols/figure/closing)."""
    layouts = root / "layouts"
    layouts.mkdir(parents=True)
    vues = {
        "slide1": ["body-26", "body-12"],
        "content": ["heading", "body-1"],
        "cols": ["heading", "col-a", "col-b"],
        "media": ["heading", "body-2", "fig-2"],
        "figure": ["heading", "fig-1"],
        "closing": ["body-26"],
        "plain": [],  # no semantic entry, no named slots — bare layout
    }
    for name, slots in vues.items():
        body = "".join(f'<slot name="{s}" />' for s in slots) or "<slot />"
        (layouts / f"{name}.vue").write_text(
            f"<template>{body}</template>", encoding="utf-8")
    (root / "semantic-layouts.json").write_text(json.dumps({
        "aliases": {
            "cover": {"layout": "slide1",
                      "slots": {"title": "body-26", "meta": "body-12"},
                      "intent": "Deck cover: short noun-phrase title; "
                                "author and date in the meta slot.",
                      "defaults": {}},
            "content": {"layout": "content",
                        "slots": {"title": "heading", "body": "body-1"},
                        "intent": "Standard content slide.",
                        "defaults": {}},
            "two-cols": {"layout": "cols",
                         "slots": {"title": "heading",
                                   "left": "col-a", "right": "col-b"},
                         "intent": "Comparison of two concepts.",
                         "defaults": {}},
            "image-split": {"layout": "media",
                            "slots": {"title": "heading", "body": "body-2",
                                      "image": "fig-2"},
                            "intent": "A figure beside supporting text.",
                            "defaults": {}},
            "figure": {"layout": "figure",
                       "slots": {"title": "heading", "image": "fig-1"},
                       "intent": "One figure with a headline; no body text.",
                       "defaults": {}},
            "closing": {"layout": "closing",
                        "slots": {"title": "body-26"},
                        "intent": "Closing slide.",
                        "defaults": {"title": "Thank you"}},
        }
    }), encoding="utf-8")
    return root


ANSWERS = {
    "topic": "Object Tracking",
    "audience": "students",
    "language": "en",
    "deck_type": "lecture",
    "setting": "university course",
    "max_slides": 6,
    "max_duration_minutes": 9,
    "presenter": "Dr. Jane Roe",
    "institution": "IU",
    "course": "DLMAIE02",
    "date": "2026-07-19",
}

SOURCE_TEXT = """# Rapid Prototyping

The properties of the component are usually still of little importance at this
point, thus the material from which the prototypes are created is generally
not an issue.

Rapid prototyping shortens development time considerably. Achievable
accuracies include a layer thickness of 0.05 to 0.3 mm and a manufacturing
tolerance of approximately 0.02 mm.

Additive processes are used in seven industries, including automotive,
aerospace, and medical engineering.
"""
SOURCE_SLUG = "chapter-4"
SOURCE_FILE = "chapter_4.md"


@pytest.fixture
def deck(tmp_path):
    """A freshly scaffolded deck on a local theme (budget: 6 slides)."""
    theme_dir = make_theme(tmp_path / "theme-src")
    root = tmp_path / "deck"
    root.mkdir()
    answers = dict(ANSWERS)
    answers["theme"] = {"type": "local", "source": str(theme_dir)}
    scaffold_deck.scaffold(root, answers)
    return root


@pytest.fixture
def converted_deck(deck, capsys):
    """The deck with one text input converted to a source record."""
    (deck / "input" / SOURCE_FILE).write_text(SOURCE_TEXT, encoding="utf-8")
    source_converter.cmd_convert(deck, None)
    capsys.readouterr()  # drop the converter's report from captured output
    return deck


# ---------------------------------------------------------------------------
# Scripted fake executor (seam 2 — the invoke shim's `cmd` executor)
# ---------------------------------------------------------------------------

FAKE_EXECUTOR = """\
import pathlib, sys
d = pathlib.Path(sys.argv[1])
counter = d / "count"
i = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(i + 1))
files = sorted(d.glob("resp-*.txt"))
sys.stdout.write(files[min(i, len(files) - 1)].read_text(encoding="utf-8"))
"""


def wire_fake_executor(deck: Path, tmp_path: Path, role: str,
                       responses: list[str], image_arg: bool = False) -> Path:
    """Point one role's executor at a scripted `cmd` fake that replays the
    given responses in order (last one repeats). Returns the response dir —
    its ``count`` file records how many invokes happened.

    ``image_arg=True`` appends an ``{image}`` placeholder so the fake declares
    ``supports_image`` (the shim substitutes the real path) — used to drive the
    vision (image-miner) path without a live model. The script ignores it."""
    import sys as _sys
    respdir = tmp_path / f"responses-{role}"
    respdir.mkdir()
    for i, resp in enumerate(responses):
        (respdir / f"resp-{i}.txt").write_text(resp, encoding="utf-8")
    script = tmp_path / "fake_executor.py"
    script.write_text(FAKE_EXECUTOR, encoding="utf-8")
    command = [_sys.executable, str(script), str(respdir)]
    if image_arg:
        command.append("{image}")
    ctx_path = deck / "deck-context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    executors = ctx.setdefault("executors", {})
    executors[role] = {"executor": "cmd", "command": command}
    ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")
    return respdir
