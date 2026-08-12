"""Editor page flush-pane layout: single-hairline seams and the parameter
list's section-header wash.

Covers the editor splitter's 1px handle width and ``#EditorSplitter``
objectName (the QSS scoping hook), the tree/parameter-list child views'
stripped borders, the section header's "+ Add" suffix action, and a guard
against the specificity trap called out in the design: the add-parameter
popup's card border must survive the new
``QTreeView#StructureTree, QListWidget#ParameterListView`` rule. (The
Inspector once had an internal splitter needing its own scoping guard; it
retired with the secondary-workspace drawer.)
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QFrame

from ui_qt import style

_CELL = ("Parameterisation", "Cell")


def _editor_splitter(app_driver):
    """The editor page's tree/params/inspector splitter (stack index 0)."""
    return app_driver._w._editor_page._stack.widget(0)


# --- structure ---------------------------------------------------------


def test_editor_splitter_handle_width_and_object_name(app_driver):
    splitter = _editor_splitter(app_driver)
    assert splitter.objectName() == "EditorSplitter"
    assert splitter.handleWidth() == 1


def test_tree_and_parameter_list_views_are_named_for_qss_binding(app_driver):
    d = app_driver
    assert d._w._tree._view.objectName() == "StructureTree"
    assert d._w._params._list.objectName() == "ParameterListView"


def test_parameter_list_header_is_the_pane_s_first_widget_with_zero_spacing(app_driver):
    params = app_driver._w._params
    assert params.layout().spacing() == 0
    assert params.layout().itemAt(0).widget() is params._header


def test_add_parameter_button_object_name_and_flat_style(app_driver):
    button = app_driver._w._params._add_button
    assert button.objectName() == "AddParameterButton"
    assert button.isFlat() is True


# --- painted chrome ------------------------------------------------------


def test_editor_splitter_handle_paints_the_hairline_colour(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)

    splitter = _editor_splitter(app_driver)
    handle = splitter.handle(1)
    image = handle.grab().toImage()
    pixel = image.pixelColor(image.width() // 2, image.height() // 2).name()
    assert pixel == style.BORDER, (
        f"Editor splitter handle pixel was {pixel}, not {style.BORDER} -- check the "
        "QSplitter#EditorSplitter::handle rule in style.py."
    )


def test_add_parameter_popup_card_border_is_unaffected_by_the_new_view_rule(
    app_driver, valid_spm_path
):
    """Guards the specificity trap: the new
    ``QTreeView#StructureTree, QListWidget#ParameterListView { border: none; }``
    rule must be scoped by explicit objectName only, and must not strip the
    add-parameter popup card's own border via a broader (accidentally more
    specific) descendant selector."""
    d = app_driver
    d.open(valid_spm_path)
    d.select_object(_CELL)
    d.open_add_parameter_popup()

    popup = d._w._params._popup
    card = popup.findChild(QFrame, "AddParameterCard")
    assert card is not None
    image = card.grab().toImage()
    pixel = image.pixelColor(0, image.height() // 2).name()
    assert pixel == style.BORDER, (
        f"AddParameterCard border pixel was {pixel}, not {style.BORDER} -- the "
        "QFrame#AddParameterCard border rule was overridden. Check that the "
        "new StructureTree/ParameterListView border rule uses explicit "
        "objectName selectors only, not a descendant selector that could "
        "out-specify it."
    )

    # This popup is a floating top-level window merely parented to the
    # panel; it does not close with the main window at teardown. Close it
    # here so this test is self-contained (see conftest.main_window for the
    # fixture-level guard against the general case).
    popup.close()
