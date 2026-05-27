"""Authoring-side helper scripts.

These are runnable as ``python -m slidecraft.scripts.<name>`` and exist to
pre-compute deterministic caches that downstream skills consume without
burning LLM tokens on raw source material (e.g. multi-hundred-page PDFs).
"""
