"""Per-``ParameterKind`` editing cards.

One card per kind, reused wherever that kind appears. Cards are dumb input
widgets: they expose a draft value and emit ``draft_changed`` while editing;
the inspector validates the draft (live) and commits on Apply.
"""
