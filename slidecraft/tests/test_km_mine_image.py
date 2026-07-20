"""Ticket 14 — image-miner per-image slice, tested at the pre-agreed seams.

Seam 1 (km CLI): ``mine-brief --image`` renders a self-contained vision brief
for exactly one extracted image (role craft + focus value, no source text, no
id or path leaked — the figure itself rides to the executor via the shim); the
reworked image-miner template (conceptual ``information``, content-first
``description``); ``persist-nuggets --image-source`` denormalizes ``asset`` +
``context_text`` + ``page`` from the source's image record onto the nugget
(D45), never trusting the model for those; a missing image source is rejected.

Seam 2 (invoke shim, fake executor): the image mine step end to end — vision
brief + the image passed as an ``{image}`` arg → persist → an image nugget on
disk. No test touches a live LLM.
"""
from __future__ import annotations

import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import invoke_shim, km
from slidecraft.tests.conftest import wire_fake_executor

IMG_SLUG = "figures"
IMG_FILE = "figures.pdf"
IMG_ID = "figures-p2-img1"
IMG_PNG = "figures-p2-img1.png"
CONTEXT = "Figure 2: prototyping approaches compared."


def _add_image_source(deck: Path) -> str:
    """A converted PDF source carrying one extracted image record + its asset,
    mirroring what source_converter emits (page text + images[] with
    image_source_id / path / page / context_text)."""
    (deck / "public" / "extracted").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "extracted" / IMG_PNG).write_bytes(b"\x89PNG fake-bytes")
    (deck / "sources" / f"{IMG_SLUG}.json").write_text(json.dumps({
        "source_id": "s1", "original_file": IMG_FILE, "type": "pdf",
        "pages": [{"page": 2, "text": "Body text around the figure."}],
        "images": [{"image_source_id": IMG_ID, "path": f"/extracted/{IMG_PNG}",
                    "page": 2, "context_text": CONTEXT}],
    }, ensure_ascii=False), encoding="utf-8")
    return IMG_ID


def _mine_brief_image(deck: Path, out: Path, image=IMG_ID):
    km.cmd_mine_brief(deck, Namespace(source=None, image=image, out=str(out)))


def _img_nugget(**over) -> dict:
    n = {"title": "Prototyping approaches compared",
         "figure_type": "chart",
         "information": "- rapid prototyping reaches a quality level soonest",
         "visible_text": ["Product quality", "Development time"],
         "description": "Compares three prototyping approaches by time and "
                        "quality. A line chart with three rising curves."}
    n.update(over)
    return n


def _persist_image(deck: Path, batch: dict, tmp_path: Path,
                   source=IMG_SLUG, image_source=IMG_ID):
    f = tmp_path / "img-batch.json"
    f.write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
    km.cmd_persist_nuggets(deck, Namespace(source=source,
                                           image_source=image_source,
                                           file=str(f)))


def _nugget_files(deck: Path) -> list[Path]:
    return sorted((deck / "nuggets").glob("*.json"))


# ---------------------------------------------------------------------------
# mine-brief --image — field routing (seam 1)
# ---------------------------------------------------------------------------

def test_mine_brief_image_carries_craft_and_focus(deck, tmp_path, capsys):
    _add_image_source(deck)
    brief_path = tmp_path / "brief.md"
    _mine_brief_image(deck, brief_path)
    brief = brief_path.read_text(encoding="utf-8")

    # Image-miner craft is present, focus injected, no leftover placeholder.
    assert "provenance anchor" in brief
    assert "Decorative images" in brief
    assert "Object Tracking" in brief                 # FOCUS-TOPIC resolved
    assert not re.search(r"%[A-Z][A-Z-]*%", brief)
    # The CLI reports where the image file lives so the shim can pass --image.
    out = json.loads(capsys.readouterr().out.strip())
    assert out["ok"] is True and out["image_source"] == IMG_ID
    assert out["asset"].endswith(IMG_PNG)
    assert Path(out["asset"]).exists()


def test_mine_brief_image_is_conceptual_no_source_text_ids_or_paths(deck,
                                                                    tmp_path,
                                                                    capsys):
    _add_image_source(deck)
    brief_path = tmp_path / "brief.md"
    _mine_brief_image(deck, brief_path)
    capsys.readouterr()
    brief = brief_path.read_text(encoding="utf-8")

    # The figure travels as a data-URL via the shim, never inlined here; and
    # the miner never sees the id, the asset path, or the source text (D45).
    assert IMG_ID not in brief
    assert "/extracted/" not in brief and IMG_PNG not in brief
    assert "Body text around the figure." not in brief
    assert CONTEXT not in brief
    for needle in ("km.py", "--deck", "python ", "create-nugget",
                   "sources/", "nuggets/"):
        assert needle not in brief, f"brief leaks {needle!r}"
    assert str(deck) not in brief


def test_mine_brief_image_unknown_id_gates(deck, tmp_path):
    _add_image_source(deck)
    with pytest.raises(SystemExit) as ei:
        _mine_brief_image(deck, tmp_path / "b.md", image="ghost-p9-img9")
    assert ei.value.code == 2                          # wiring gate, no retry


def test_mine_brief_requires_exactly_one_mode(deck, tmp_path):
    _add_image_source(deck)
    with pytest.raises(SystemExit) as neither:
        km.cmd_mine_brief(deck, Namespace(source=None, image=None,
                                          out=str(tmp_path / "b.md")))
    assert neither.value.code == 2
    with pytest.raises(SystemExit) as both:
        km.cmd_mine_brief(deck, Namespace(source=IMG_SLUG, image=IMG_ID,
                                          out=str(tmp_path / "b.md")))
    assert both.value.code == 2


def test_image_miner_template_description_is_content_first():
    tpl = (km.AGENTS_DIR / "image-miner.md").read_text(encoding="utf-8")
    assert "content first" in tpl.lower()
    assert "label inventory" in tpl.lower()            # the anti-pattern named
    # The craft that must survive the rework.
    assert "visible_text" in tpl and "Decorative images" in tpl


# ---------------------------------------------------------------------------
# persist-nuggets --image-source — denormalization (seam 1, D45)
# ---------------------------------------------------------------------------

def test_persist_image_denormalizes_asset_context_and_page(deck, tmp_path,
                                                           capsys):
    _add_image_source(deck)
    _persist_image(deck, {"nuggets": [_img_nugget()]}, tmp_path)

    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] == 1
    n = json.loads(_nugget_files(deck)[0].read_text(encoding="utf-8"))
    assert n["kind"] == "image"
    assert n["source"] == IMG_FILE
    assert n["page"] == 2
    assert n["asset"] == f"/extracted/{IMG_PNG}"       # from the record
    assert n["context_text"] == CONTEXT                # from the record
    assert n["visible_text"] == ["Product quality", "Development time"]


def test_persist_image_overrides_model_supplied_facts(deck, tmp_path, capsys):
    _add_image_source(deck)
    # A miner that invents asset / page / context_text — all overridden (D45).
    _persist_image(deck, {"nuggets": [_img_nugget(
        asset="/extracted/wrong.png", page=99,
        context_text="hallucinated caption")]}, tmp_path)
    n = json.loads(_nugget_files(deck)[0].read_text(encoding="utf-8"))
    assert n["asset"] == f"/extracted/{IMG_PNG}"
    assert n["page"] == 2
    assert n["context_text"] == CONTEXT


def test_persist_image_missing_image_source_is_a_gate(deck, tmp_path):
    _add_image_source(deck)
    with pytest.raises(SystemExit) as ei:
        _persist_image(deck, {"nuggets": [_img_nugget()]}, tmp_path,
                       image_source="ghost-p9-img9")
    assert ei.value.code == 2
    assert _nugget_files(deck) == []


def test_persist_image_rejects_missing_visible_text_atomically(deck, tmp_path):
    _add_image_source(deck)
    batch = {"nuggets": [_img_nugget(),
                         _img_nugget(title="No anchor", visible_text=None)]}
    with pytest.raises(SystemExit) as ei:
        _persist_image(deck, batch, tmp_path)
    assert "#2" in str(ei.value) and "visible_text" in str(ei.value)
    assert _nugget_files(deck) == []                   # atomic: nothing written


def test_persist_image_empty_batch_ok_for_decorative(deck, tmp_path, capsys):
    _add_image_source(deck)
    _persist_image(deck, {"nuggets": []}, tmp_path)    # decorative → nothing
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] == 0 and _nugget_files(deck) == []


# ---------------------------------------------------------------------------
# The image mine step end to end over the shim (seam 2, fake vision executor)
# ---------------------------------------------------------------------------

def test_image_mine_step_persists_image_nugget(deck, tmp_path, capsys):
    _add_image_source(deck)
    good = json.dumps({"nuggets": [_img_nugget()]})
    wire_fake_executor(deck, tmp_path, "image-miner", [good], image_arg=True)

    brief = tmp_path / "brief.md"
    km.cmd_mine_brief(deck, Namespace(source=None, image=IMG_ID, out=str(brief)))
    asset = json.loads(capsys.readouterr().out.strip())["asset"]

    result = tmp_path / "invoke-result.json"
    rc = invoke_shim.main([
        "--role", "image-miner", "--brief-file", str(brief),
        "--image", asset, "--deck", str(deck), "--out", str(result), "--",
        sys.executable, str(Path(km.__file__)), "--deck", str(deck),
        "persist-nuggets", "--source", IMG_SLUG, "--image-source", IMG_ID,
        "--file", "{out}",
    ])

    assert rc == 0
    res = json.loads(result.read_text(encoding="utf-8"))
    assert res["status"] == "ok" and res["attempts"] == 1
    files = _nugget_files(deck)
    assert len(files) == 1
    n = json.loads(files[0].read_text(encoding="utf-8"))
    assert n["kind"] == "image" and n["asset"] == f"/extracted/{IMG_PNG}"
