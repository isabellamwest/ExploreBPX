"""Tests for TextCard: the auto-growing editor for ``ParameterKind.TEXT``.

TEXT is the one kind whose editor must never numeric-coerce -- e.g.
``Header.Title = "2024"`` must stay the string ``"2024"``, unlike the lenient
Scalar/Function/Raw convention. These tests also cover the Shift+Enter
multi-line contract added to ``EditorCard`` for this card.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.text import TextCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _param(value=None) -> ParameterItem:
    return ParameterItem(label="Title", path=("Header", "Title"), kind=ParameterKind.TEXT, value=value)


def test_numeric_looking_text_is_never_coerced():
    """The whole point of TEXT: a value that looks numeric stays a string."""
    _app()
    card = TextCard(_param(), None)
    card._edit.setPlainText("2024")
    assert card.value() == "2024"
    assert isinstance(card.value(), str)


def test_empty_text_commits_empty_string_not_none():
    """TEXT is the one kind where empty input commits an empty string, not
    null (the only nullable field is UserDefined.description, which is
    unreachable)."""
    _app()
    card = TextCard(_param(), None)
    assert card.value() == ""
    assert card._edit.toPlainText() == ""


def test_value_is_never_stripped():
    _app()
    card = TextCard(_param(), None)
    card._edit.setPlainText("  padded  ")
    assert card.value() == "  padded  "


def test_format_none_original_renders_empty():
    _app()
    card = TextCard(_param(value=None), None)
    assert card._edit.toPlainText() == ""


def test_format_non_string_original_renders_str():
    """A TEXT-kind field can hold an invalid non-string original (e.g. a
    number saved into a text field); it must still render, not crash."""
    _app()
    card = TextCard(_param(value=42), None)
    assert card._edit.toPlainText() == "42"


def test_plain_enter_commits():
    _app()
    card = TextCard(_param(value="hello"), None)
    received = []
    card.commit_requested.connect(lambda: received.append(True))
    key_event = _key_press(Qt.Key_Return, Qt.NoModifier)
    card.eventFilter(card._edit, key_event)
    assert received == [True]


def test_shift_enter_inserts_newline_and_does_not_commit():
    _app()
    card = TextCard(_param(value="hello"), None)
    card._edit.setPlainText("hello")
    cursor = card._edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    card._edit.setTextCursor(cursor)

    received = []
    card.commit_requested.connect(lambda: received.append(True))
    key_event = _key_press(Qt.Key_Return, Qt.ShiftModifier)
    consumed = card.eventFilter(card._edit, key_event)

    assert consumed is True
    assert received == []
    assert card.value() == "hello\n"


def test_insert_newline_is_a_literal_backslash_n():
    _app()
    card = TextCard(_param(value=""), None)
    card._insert_newline()
    assert card.value() == "\n"


def test_placeholder_from_first_example():
    _app()
    meta = FieldMeta(alias="Title", examples=("Parameterisation example", "other"))
    card = TextCard(_param(), meta)
    assert card._edit.placeholderText() == "Parameterisation example"


def test_no_placeholder_without_examples():
    _app()
    card = TextCard(_param(), FieldMeta(alias="Title"))
    assert card._edit.placeholderText() == ""


def test_pattern_hint_shows_verbatim_regex():
    _app()
    meta = FieldMeta(alias="BPX", pattern=r"^\d+\.\d+\.\d+$")
    card = TextCard(ParameterItem(label="BPX", path=("Header", "BPX"), kind=ParameterKind.TEXT, value="1.0.0"), meta)
    from PySide6.QtWidgets import QLabel

    hints = [w.text() for w in card.findChildren(QLabel)]
    assert r"pattern: ^\d+\.\d+\.\d+$" in hints


def test_no_pattern_hint_when_pattern_absent():
    _app()
    from PySide6.QtWidgets import QLabel

    card = TextCard(_param(), FieldMeta(alias="Title"))
    assert card.findChildren(QLabel) == []


def test_grows_then_caps_at_max_lines():
    _app()
    card = TextCard(_param(value=""), None)
    height_1_line = card._edit.height()

    card._edit.setPlainText("\n".join(["line"] * 3))
    height_3_lines = card._edit.height()
    assert height_3_lines > height_1_line

    card._edit.setPlainText("\n".join(["line"] * 6))
    height_6_lines = card._edit.height()
    assert height_6_lines > height_3_lines

    card._edit.setPlainText("\n".join(["line"] * 20))
    height_20_lines = card._edit.height()
    assert height_20_lines == height_6_lines  # capped at ~6 lines, then scrolls


def test_long_wrapped_line_grows_box():
    """A single logical line that word-wraps must grow the box by its
    *visual* line count, not stay at one line (the wrap-blindness bug)."""
    app = _app()
    card = TextCard(_param(value=""), None)
    card.setFixedWidth(300)
    card.show()
    app.processEvents()
    height_1_line = card._edit.height()

    card._edit.setPlainText(
        "This is one long logical line with no newlines that must wrap "
        "across several visual lines inside a narrow inspector card"
    )
    app.processEvents()
    assert card._edit.document().blockCount() == 1
    assert card._edit.height() > height_1_line
    card.close()


def test_wrapped_lines_share_the_max_lines_cap():
    """Wrapped visual lines hit the same 6-line cap as logical lines."""
    app = _app()
    card = TextCard(_param(value=""), None)
    card.setFixedWidth(300)
    card.show()
    app.processEvents()

    card._edit.setPlainText("\n".join(["line"] * 6))
    app.processEvents()
    height_capped = card._edit.height()

    card._edit.setPlainText("wrap " * 200)
    app.processEvents()
    assert card._edit.height() == height_capped
    card.close()


def test_widening_the_card_refits_wrapped_height():
    """Re-wrap driven by a width change (no textChanged) still re-fits."""
    app = _app()
    card = TextCard(_param(value=""), None)
    card.setFixedWidth(220)
    card.show()
    app.processEvents()
    card._edit.setPlainText("a moderately long value that wraps at a narrow width only")
    app.processEvents()
    height_narrow = card._edit.height()

    card.setFixedWidth(800)
    app.processEvents()
    assert card._edit.height() < height_narrow
    card.close()


def test_escape_reverts_via_reset():
    _app()
    card = TextCard(_param(value="original"), None)
    card._edit.setPlainText("changed")
    card.reset()
    assert card.value() == "original"


def _key_press(key, modifiers):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    return QKeyEvent(QEvent.KeyPress, key, modifiers)
