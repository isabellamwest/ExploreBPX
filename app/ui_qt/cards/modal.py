"""``ModalCard``: a card whose value has more than one legal representation.

A union-typed BPX field (``FloatFunctionTable``, ``FloatInt | dict[str,
FloatInt]``) can hold several shapes. The *kind* is declared by the schema; the
*mode* is chosen by the user. A mode strip names each legal representation and
swaps the editor beneath it.

Vocabulary is verbatim ``bpx.schema``: ``FloatInt``, ``Function``,
``InterpolatedTable``, ``dict[str, FloatInt]``. Modellers want the schema's own
words, never a translation. ``Raw`` is the sole non-schema label, because it is
an app concept rather than a BPX type.

Rules that make the strip safe to use:

* **Bodies are built eagerly and kept alive**, so each mode holds its own draft.
  Going ``FloatInt`` → ``Function`` → ``FloatInt`` still shows the number.
* **Only the initial mode is seeded.** Switching mode completely changes the
  value, so ``3.7`` → ``InterpolatedTable`` gives an *empty* grid rather than a
  one-row table -- the card never invents data.
* **Switching mode alone is not an edit.** It does not mark the card touched,
  does not emit ``draft_changed``, and so never kicks the live-validation
  debounce. A bare Enter after a mode switch commits nothing, and the badge
  does not flash "Invalid" at an empty new mode.
* **The strip never mutates under the cursor.** Whether a ``Raw`` mode exists is
  decided once, at construction, from the committed value.
* **Every mode stays clickable.** Clicking ``FloatInt`` while looking at
  unrepresentable JSON just shows an empty numeric editor; nothing is destroyed
  until the user commits.
* **Escape reverts value and mode**, restoring every body and the initial mode.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .base import EditorCard
from .bodies import ModeBody, RawJsonBody

#: The label of the app's one non-schema mode. Kept here so cards, the registry
#: and tests all name it once.
RAW_MODE = "Raw"


@dataclass(frozen=True)
class Mode:
    """One entry in the strip: its verbatim label and the body that edits it."""

    label: str
    body: ModeBody


class ModeStrip(QWidget):
    """A row of segmented, mutually exclusive mode buttons."""

    def __init__(self, labels: tuple[str, ...], on_change) -> None:
        super().__init__()
        self.setObjectName("ModeStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QToolButton] = []
        for index, label in enumerate(labels):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setObjectName("ModeButton")
            button.setAccessibleName(f"{label} mode")
            self._group.addButton(button, index)
            layout.addWidget(button)
            self._buttons.append(button)
        layout.addStretch(1)
        self._group.idClicked.connect(on_change)

    def select(self, index: int) -> None:
        """Check the button at *index* without emitting ``idClicked``."""
        self._buttons[index].setChecked(True)

    def current_index(self) -> int:
        return self._group.checkedId()


class ModalCard(EditorCard):
    """Owns a mode strip over a stack of live, independently-drafted bodies."""

    def __init__(self, parameter, meta, modes: list[Mode], initial: int) -> None:
        super().__init__(parameter, meta)
        self._modes = modes
        self._initial = initial

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # A single-representation kind shows no strip -- there is nothing to
        # choose between.
        self._strip = None
        if len(modes) > 1:
            self._strip = ModeStrip(tuple(m.label for m in modes), self._on_mode_clicked)
            layout.addWidget(self._strip)

        self._stack = QStackedWidget()
        for mode in modes:
            self._stack.addWidget(mode.body)
        self._stack.currentChanged.connect(self._sync_page_heights)
        layout.addWidget(self._stack)

        # Seed the initial body *before* wiring any ``changed`` signal, or
        # construction would mark the card touched and a bare Enter would
        # commit. Every other body stays empty: no seeding across modes.
        modes[initial].body.set_value(self._original)
        for mode in modes:
            mode.body.changed.connect(self.draft_changed)
            mode.body.expand_toggled.connect(self.expand_toggled)
            self._install_keyboard_handler(mode.body.focus_widget())
            # Every grid-bearing body gets the card-level "Unsaved edits"
            # bar: dirtiness is a property of the *card* (its active draft
            # vs the committed value), so all bars mirror the same state --
            # only the visible body's bar can be seen at any moment.
            grid = mode.body.pending_grid()
            if grid is not None:
                self._bind_grid_pending(grid)

        self._stack.setCurrentIndex(initial)
        # Explicit call: setCurrentIndex emits currentChanged only on a real
        # change, and the stack starts at index 0.
        self._sync_page_heights(initial)
        if self._strip is not None:
            self._strip.select(initial)

    # --- modes ----------------------------------------------------------
    @property
    def mode_labels(self) -> tuple[str, ...]:
        return tuple(mode.label for mode in self._modes)

    @property
    def current_mode(self) -> str:
        return self._modes[self._stack.currentIndex()].label

    def select_mode(self, label: str) -> None:
        """Switch to the mode named *label* (a no-op for an unknown label)."""
        for index, mode in enumerate(self._modes):
            if mode.label == label:
                self._on_mode_clicked(index)
                if self._strip is not None:
                    self._strip.select(index)
                return

    def _on_mode_clicked(self, index: int) -> None:
        """Swap the visible body. Deliberately silent: no ``draft_changed``, no
        ``_touched``, so a mode switch alone is never a pending edit."""
        self._stack.setCurrentIndex(index)

    def _sync_page_heights(self, index: int) -> None:
        """Let only the visible body shape the stack's height.

        ``QStackedLayout`` sizes itself to its *tallest* page -- and imposes
        that as a minimum through the layout chain, past any widget-level
        ``sizeHint`` override -- so the one-line ``Function`` editor inherited
        the table page's height and its hint label floated mid-pane. A hidden
        page's vertical policy drops to ``Ignored``, which ``QStackedLayout``
        explicitly zeroes in both its size hint and its minimum; the visible
        page's is restored to ``Preferred``. Size policies only: bodies'
        drafts and change signals are never touched.
        """
        for i in range(self._stack.count()):
            body = self._stack.widget(i)
            policy = body.sizePolicy()
            policy.setVerticalPolicy(
                QSizePolicy.Preferred if i == index else QSizePolicy.Ignored
            )
            body.setSizePolicy(policy)

    @property
    def _body(self) -> ModeBody:
        return self._modes[self._stack.currentIndex()].body

    def focus_widget(self) -> QWidget:
        """The active body's input widget -- what Enter and Escape act on."""
        return self._body.focus_widget()

    # --- EditorCard contract --------------------------------------------
    def value(self) -> object:
        return self._body.value()

    def reset(self) -> None:
        """Escape restores every body's draft *and* returns to the initial mode."""
        for mode in self._modes:
            mode.body.reset()
        self._stack.setCurrentIndex(self._initial)
        if self._strip is not None:
            self._strip.select(self._initial)

    def commit_blocked_reason(self) -> str | None:
        return self._body.commit_blocked_reason()

    def set_cell_issues(self, issues) -> None:
        """Only the active body is showing the value the diagnostics describe;
        tinting a hidden body's grid from them would be nonsense."""
        self._body.set_cell_issues(issues)

    @property
    def accepts_multiline_input(self) -> bool:
        return self._body.accepts_multiline_input

    def _insert_newline(self) -> None:
        self._body.insert_newline()


class RawValueCard(ModalCard):
    """A single-mode ``Raw`` JSON editor for an unrepresentable value of an
    otherwise single-representation kind (``SERIES``, ``TABLE``).

    A single-representation kind shows no mode strip: there is nothing to choose
    between. When its stored value cannot be shown structurally (a series that
    is not a flat list, a ragged x/y table), the registry hands it this card
    rather than a read-only view -- so the value stays editable -- and rather
    than a free-text editor, which would commit a dict's Python ``repr`` and
    corrupt it. The JSON body refuses to commit unparseable text.

    With one mode, :class:`ModalCard` draws no strip, so the user sees only the
    JSON editor and its notice.
    """

    def __init__(self, parameter, meta, notice: str = "") -> None:
        super().__init__(parameter, meta, [Mode(RAW_MODE, RawJsonBody(notice))], 0)
