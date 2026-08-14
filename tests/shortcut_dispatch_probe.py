"""Out-of-process probe: does every registered shortcut key still dispatch?

Run as a subprocess by ``tests/test_undo.py``, never imported by the suite.
It exists because *inside* pytest-qt the window never activates offscreen --
``isActiveWindow()`` stays False and ``QApplication.focusWidget()`` stays None
even after ``show``/``raise_``/``activateWindow``/``qtbot.waitActive`` (which
returns without raising) -- so ``QTest.keySequence`` fires nothing at all and
any in-suite assertion about a key press passes vacuously. A standalone
QApplication does activate, so the check has to live out here.

Usage: ``python shortcut_dispatch_probe.py <bpx-file>``. Prints one JSON object
on stdout: ``active`` (was the window really activated -- a False makes any
result meaningless), ``keys`` (every key sequence some registration claims),
and ``dead`` (claimed keys that fired no handler, which is what a collision
looks like: Qt reports ``activatedAmbiguously`` and runs *neither* handler).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "app"))

from PySide6.QtGui import QAction, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import ui_qt.main_window as main_window_module  # noqa: E402

# Ctrl+O reaches the real Open dialog, which would block the probe forever.
main_window_module.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))


def main(document: Path) -> int:
    app = QApplication([])
    window = main_window_module.MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()

    # A document makes the document-scoped actions genuinely enabled, so their
    # keys take part rather than being skipped as disabled registrations.
    window.open_document(document)
    app.processEvents()

    fired: list[str] = []
    claims: dict[str, list[str]] = {}

    def claim(sequence: QKeySequence, name: str) -> None:
        if not sequence.isEmpty():
            claims.setdefault(sequence.toString(), []).append(name)

    for shortcut in window.findChildren(QShortcut):
        name = f"QShortcut({shortcut.key().toString()})"
        shortcut.activated.connect(lambda n=name: fired.append(n))
        # A StandardKey registration answers to every binding of that key, not
        # just the one ``.key()`` reports -- that gap is exactly what hid the
        # dead Ctrl+Shift+Z. Ask Qt for the full set rather than guessing.
        for sequence in _bindings_of(shortcut.key()):
            claim(sequence, name)

    for action in window.findChildren(QAction):
        if action.shortcut().isEmpty() or not action.isEnabled():
            continue
        name = f"QAction({action.text()})"
        action.triggered.connect(lambda *_, n=name: fired.append(n))
        for sequence in action.shortcuts():
            claim(sequence, name)

    dead: list[str] = []
    for key_text in claims:
        del fired[:]
        QTest.keySequence(window, QKeySequence(key_text))
        app.processEvents()
        if not fired:
            dead.append(key_text)

    print(
        json.dumps(
            {
                "active": window.isActiveWindow(),
                "keys": sorted(claims),
                "dead": sorted(dead),
                "claims": dict(sorted(claims.items())),
            }
        )
    )
    window._suppress_close_guard = True
    window.close()
    return 0


def _bindings_of(sequence: QKeySequence) -> list[QKeySequence]:
    """Every sequence a registration for *sequence* also answers to.

    A shortcut built from a StandardKey is matched against that key's whole
    binding list at dispatch time, so Ctrl+Y also answers Ctrl+Shift+Z on
    Windows. Recovering the standard key from the sequence is the only way to
    see those extra bindings from Python.
    """
    for standard in QKeySequence.StandardKey:
        bindings = QKeySequence.keyBindings(standard)
        if bindings and bindings[0] == sequence:
            return bindings
    return [sequence]


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
