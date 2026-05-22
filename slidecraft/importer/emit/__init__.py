"""Emit pipeline: Presentation → theme folder + deck folder."""

from .theme import emit_theme
from .layout import emit_layouts
from .slide import emit_deck

__all__ = ["emit_theme", "emit_layouts", "emit_deck"]
