"""The three designer templates render with their exact placeholder set and
leave no leftover placeholder (the leftover guard is the real contract)."""
from __future__ import annotations

import re

import pytest

from slidecraft.scripts import km

TEXT_VALUES = {"AUDIENCE": "students", "DECK-TYPE": "lecture", "LANGUAGE": "en",
               "STYLE-CONTRACT": "…", "CORE-MESSAGE": "msg", "SECTION-ROLE": "left",
               "INSTRUCTIONS": "Make a table.", "NUGGETS": "n-raw",
               "RAW-MATERIAL": "all raw"}
DIAGRAM_VALUES = {**TEXT_VALUES, "COMPONENT-CATALOG": "- **FlowDiagram** …"}
IMAGE_VALUES = {"AUDIENCE": "students", "DECK-TYPE": "lecture", "LANGUAGE": "en",
                "CORE-MESSAGE": "msg", "SECTION-ROLE": "body",
                "INSTRUCTIONS": "Render X.", "NUGGETS": "n-raw",
                "RAW-MATERIAL": "all raw", "EXACT-TEXT": "Predict\nUpdate",
                "ASPECT-RATIO": "16:9"}


@pytest.mark.parametrize("name,values", [
    ("text-designer", TEXT_VALUES),
    ("diagram-designer", DIAGRAM_VALUES),
    ("image-designer", IMAGE_VALUES)])
def test_designer_template_renders_clean(name, values):
    out = km.render_template(km.load_template(name), values)
    assert not re.search(r"%[A-Z][A-Z_-]*%", out)
    assert values["INSTRUCTIONS"] in out          # instruction reaches the designer


def test_diagram_template_carries_the_component_catalog():
    out = km.render_template(km.load_template("diagram-designer"), DIAGRAM_VALUES)
    assert "FlowDiagram" in out


def test_image_template_states_aspect_and_exact_text():
    out = km.render_template(km.load_template("image-designer"), IMAGE_VALUES)
    assert "16:9" in out and "Predict" in out
