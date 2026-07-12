"""Boolean editing card: a checkbox for ``ParameterKind.BOOLEAN`` values."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout

from .base import EditorCard


class BooleanCard(EditorCard):
    """Edits a BOOLEAN-kind value via a checkbox labelled ``true``/``false``.

    ``BOOLEAN`` is only ever produced by the value-shape fallback on an
    actual ``bool`` (see ``core.parameter_types.classify`` -- it is never
    metadata-declared), so the original is always a real ``bool``. Unlike
    :class:`~.integer.IntegerCard`, no invalid-original fallback widget is
    needed.

    Commit model: **clicking the checkbox commits immediately**. A toggle is a
    complete, discrete act -- the same rule as picking from an enum's opened
    dropdown -- so requiring a further Enter only makes the change look like it
    didn't take. ``clicked`` fires solely on user interaction (click or Space),
    never from ``setChecked``, so seeding and ``reset()`` stay silent.
    """

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._check = QCheckBox()
        self._check.setChecked(bool(self._original))
        self._sync_label(self._check.isChecked())
        self._check.toggled.connect(self._on_toggled)
        self._check.clicked.connect(lambda *_: self.commit_requested.emit())
        layout.addWidget(self._check)
        layout.addStretch(1)
        self._install_keyboard_handler(self._check)

    def _on_toggled(self, checked: bool) -> None:
        self._sync_label(checked)
        self.draft_changed.emit()

    def _sync_label(self, checked: bool) -> None:
        # JSON/BPX vocabulary, not Python's "True"/"False".
        self._check.setText("true" if checked else "false")

    def value(self) -> object:
        return self._check.isChecked()

    def reset(self) -> None:
        self._check.setChecked(bool(self._original))
