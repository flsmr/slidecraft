"""Dynamic diagram-component catalog (D14): per-component <catalog> metadata,
extracted + rendered for the diagram designer's %COMPONENT-CATALOG%."""
from __future__ import annotations

from pathlib import Path

from slidecraft.scripts import km


def _write_component(d: Path, name: str, catalog: str | None) -> None:
    block = f"<catalog>\n{catalog}\n</catalog>\n" if catalog else ""
    (d / f"{name}.vue").write_text(
        block + "<script setup></script>\n<template><slot/></template>\n",
        encoding="utf-8")


def test_parse_catalog_block_reads_three_fields():
    text = ("<catalog>\n"
            "use: Linear process with one direction of flow.\n"
            "looks: Left-to-right boxes joined by single arrows.\n"
            "fill: bullet list; each item is a step, 'title | desc'.\n"
            "</catalog>\n<script setup></script>")
    parsed = km.parse_catalog_block(text)
    assert parsed["use"].startswith("Linear process")
    assert parsed["looks"].startswith("Left-to-right")
    assert parsed["fill"].startswith("bullet list")


def test_parse_catalog_block_absent_returns_none():
    assert km.parse_catalog_block("<script setup></script>") is None


def test_component_catalog_renders_present_and_flags_missing(tmp_path):
    d = tmp_path / "components"
    d.mkdir()
    _write_component(d, "FlowDiagram",
                     "use: Linear pipeline.\nlooks: L-to-R boxes.\n"
                     "fill: step = 'title | desc'.")
    _write_component(d, "DecisionTree", None)          # no catalog block
    _write_component(d, "GenBox",                       # infra — never listed
                     "use: internal.\nlooks: x.\nfill: x.")
    (d / "_slotAuthoring.js").write_text("// helper", encoding="utf-8")

    table, missing = km.component_catalog(d)

    assert "FlowDiagram" in table
    assert "Linear pipeline." in table and "L-to-R boxes." in table
    assert "DecisionTree" in table                      # listed name-only
    assert "GenBox" not in table                        # infra excluded
    assert "_slotAuthoring" not in table
    assert missing == ["DecisionTree"]
