"""ReferenceLibraryDialog: the Phase B chooser (Concept A, signed 2026-07-31).

Constructed directly and inspected, never through ``.exec()`` -- it is a
pure chooser holding no app state; accepting only reports
``selected_set_id`` back to the caller, so a real blocking modal loop adds
nothing here (the DatabaseExamplesDialog test idiom). Expected texts are
read back from the catalog and the raw documents, never hand-written.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from core.document import BPXDocument
from core.reference_library import list_reference_sets, load_reference_raw
from ui_qt.reference_library_dialog import ReferenceLibraryDialog


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def test_rows_follow_the_curated_catalog_order():
    dialog = ReferenceLibraryDialog()
    assert list(dialog._rows) == [s.id for s in list_reference_sets()]


def test_the_flagship_is_preselected_with_its_detail_filled():
    dialog = ReferenceLibraryDialog()
    flagship = list_reference_sets()[0]

    assert dialog.selected_set_id() == flagship.id
    assert not dialog._rows[flagship.id]._tick.isHidden()
    # The detail pane is the file's own Header, verbatim.
    assert dialog._detail_heading.text() == flagship.short_title
    assert dialog._detail_title.text() == flagship.title
    assert dialog._detail_description.text() == flagship.description
    # Counts derive through BPXDocument -- the same derivation the docked
    # tile uses -- so the meta line restates that, not an invented number.
    document = BPXDocument.from_raw(
        load_reference_raw(flagship.id), filename=flagship.id, fmt="json"
    )
    assert (
        f"{document.section_count} sections · {document.parameter_count} parameters"
        in dialog._detail_meta.text()
    )
    assert f"Model {flagship.model}" in dialog._detail_meta.text()


def test_clicking_a_row_moves_the_selection_and_the_detail():
    dialog = ReferenceLibraryDialog()
    first, second = list_reference_sets()[0], list_reference_sets()[1]

    dialog._rows[second.id].clicked.emit()

    assert dialog.selected_set_id() == second.id
    assert not dialog._rows[second.id]._tick.isHidden()
    assert dialog._rows[first.id]._tick.isHidden()
    assert dialog._detail_heading.text() == second.short_title
    assert dialog._detail_description.text() == second.description


def test_accept_reports_the_chosen_set():
    dialog = ReferenceLibraryDialog()
    chosen = list_reference_sets()[2]

    dialog._rows[chosen.id].clicked.emit()
    dialog.accept()

    assert dialog.selected_set_id() == chosen.id
