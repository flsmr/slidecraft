"""Deterministic scaffolding entry points (deck/theme bootstrapping).

These are the operations that don't need an LLM — pure mkdir + template
render + npm install. Slash commands like /slidecraft:new-deck delegate
to this package so the LLM only handles input gathering, not mechanics.

Import the entry points from their submodules directly, e.g.

    from slidecraft.scaffold.new_deck import scaffold_deck

Avoiding eager re-exports here keeps `python -m slidecraft.scaffold.new_deck`
free of the "module-in-sys.modules-after-import" RuntimeWarning.
"""
