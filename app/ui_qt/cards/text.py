"""Text editing card: an auto-growing box for ``ParameterKind.TEXT`` values.

``value()`` never coerces to a number -- unlike the lenient numeric-parsing
convention shared by Scalar/Function/Raw, TEXT is a declared BPX kind whose
whole point is that a value stays a string even when it looks numeric (e.g.
``Header.Title = "2024"`` must not silently become the ``int`` 2024). The
draft is handed to the commit path verbatim, whitespace and all.

Keyboard contract (extends :class:`~.base.EditorCard`):
- Enter / Return  → emit ``commit_requested`` (unchanged).
- Shift+Enter     → insert a literal ``"\n"`` rather than committing (see
                    ``_insert_newline``).
- Escape          → restore to original value, emit ``draft_reset``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout

from ..style import MUTED
from .base import EditorCard

#: Auto-grow bounds: never shorter than one line, never taller than this many
#: lines -- beyond that the box scrolls instead of growing further.
_MIN_LINES = 1
_MAX_LINES = 6


class TextCard(EditorCard):
    """Edits a TEXT-kind value via an auto-growing ``QPlainTextEdit``."""

    accepts_multiline_input = True

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._edit = QPlainTextEdit(self._format(self._original))
        # Explicit rather than relying on the QAbstractScrollArea default:
        # a scrollbar only appears once the content actually exceeds
        # _MAX_LINES, never at the 1-line minimum size.
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._edit.setTabChangesFocus(True)
        if meta and meta.examples:
            self._edit.setPlaceholderText(str(meta.examples[0]))
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit)

        if meta and meta.pattern:
            # A hint only -- the card never gatekeeps, so this never blocks a
            # commit. The regex is shown verbatim: BPX vocabulary is never
            # translated or prettified.
            hint = QLabel(f"pattern: {meta.pattern}")
            hint.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(hint)

        self._install_keyboard_handler(self._edit)
        self._resize_to_content()

    def _on_text_changed(self) -> None:
        self._resize_to_content()
        self.draft_changed.emit()

    def _resize_to_content(self) -> None:
        """Fit the box's height to its content, from ``_MIN_LINES`` up to
        ``_MAX_LINES``; beyond that it scrolls instead of growing further."""
        line_count = max(self._edit.document().blockCount(), _MIN_LINES)
        visible_lines = min(line_count, _MAX_LINES)
        line_height = QFontMetrics(self._edit.font()).lineSpacing()
        doc_margin = self._edit.document().documentMargin()
        frame = 2 * self._edit.frameWidth()
        height = round(visible_lines * line_height + 2 * doc_margin + frame)
        self._edit.setFixedHeight(height)

    @staticmethod
    def _format(value: object) -> str:
        return "" if value is None else str(value)

    def value(self) -> object:
        """Return the text verbatim -- never stripped, never numeric-coerced."""
        return self._edit.toPlainText()

    def reset(self) -> None:
        # setPlainText triggers textChanged, which re-fits the height and
        # emits draft_changed -- the same wiring every other card's reset()
        # relies on.
        self._edit.setPlainText(self._format(self._original))

    def _insert_newline(self) -> None:
        # Inserted explicitly (rather than letting Shift+Return fall through
        # to Qt's own handling) so the character is deterministically "\n":
        # QTextEdit-family widgets otherwise insert a Unicode line separator
        # (U+2029) on Shift+Return, which is not what ``value()`` should
        # ever hand to the commit path.
        self._edit.insertPlainText("\n")
