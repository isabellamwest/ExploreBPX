"""ReferenceLibraryDialog: the bundled reference library's chooser.

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

from PySide6.QtWidgets import QApplication, QLabel

from explore_bpx.core.document import BPXDocument
from explore_bpx.core.reference_library import PROVENANCE, list_reference_sets, load_reference_raw
from explore_bpx.ui_qt.reference_library_dialog import ReferenceLibraryDialog


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


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
    document = BPXDocument.from_raw(load_reference_raw(flagship.id), filename=flagship.id, fmt="json")
    assert f"{document.section_count} sections · {document.parameter_count} parameters" in dialog._detail_meta.text()
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
    assert second.references in dialog._detail_citation.text()


# Transparency: a derived artifact under someone else's licence has to say
# so on screen, because NOTICE.md does not ship anywhere a user can reach.


def test_the_citation_is_shown_as_its_own_line_not_only_inside_the_description():
    dialog = ReferenceLibraryDialog()
    flagship = list_reference_sets()[0]

    assert flagship.references  # the catalog must carry it in the first place
    assert dialog._detail_citation.text() == f"Source: {flagship.references}"
    assert not dialog._detail_citation.isHidden()


def test_the_footer_states_the_origin_and_licence():
    dialog = ReferenceLibraryDialog()
    footer = dialog.findChild(QLabel, "ReferenceLibraryProvenance")

    assert footer is not None
    assert footer.text() == PROVENANCE
    # The old text pointed at a repo file instead of saying anything.
    assert "NOTICE.md" not in footer.text()


def test_accept_reports_the_chosen_set():
    dialog = ReferenceLibraryDialog()
    chosen = list_reference_sets()[2]

    dialog._rows[chosen.id].clicked.emit()
    dialog.accept()

    assert dialog.selected_set_id() == chosen.id
