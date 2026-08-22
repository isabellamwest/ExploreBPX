"""WrappedHelp geometry: the wrapped-height pin must never go negative.

``WrappedHelp.resizeEvent`` pins the label's minimum height to its wrapped
height so stacked layouts honour multi-line text. ``QLabel.heightForWidth``
returns -1 ("no preference") for an empty label -- and the cards build one
empty ``WrappedHelp`` up front (the error note) -- so an unclamped pin asks
Qt for ``setMinimumHeight(-1)``, which Qt rejects with a console warning on
every resize. These tests pin the clamp and the pin itself.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from ui_qt.cards.hint import WrappedHelp


def test_empty_help_never_requests_a_negative_minimum(qtbot, qtlog):
    label = WrappedHelp("")
    qtbot.addWidget(label)
    label.show()
    label.resize(240, 30)
    qtbot.wait(10)

    # The contract is non-negative, not exactly zero: a platform style may
    # give even an empty label a positive wrapped height. The regression
    # itself is the rejected setMinimumHeight(-1) and its Qt warning.
    assert label.minimumHeight() >= 0
    assert not [r for r in qtlog.records if "Negative sizes" in r.message]


def test_help_still_pins_its_minimum_to_the_wrapped_height(qtbot):
    label = WrappedHelp("wrap " * 40)
    qtbot.addWidget(label)
    label.show()
    label.resize(160, 10)
    qtbot.wait(10)

    wrapped = label.heightForWidth(label.width())
    assert wrapped > 0
    assert label.minimumHeight() == wrapped
