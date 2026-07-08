"""Tests for Step 1 of the add-parameter feature: the "+ Add parameter" header
entry point and the custom-add workflow (roadmap item W2).

BPX-alias suggestions (W1) are out of scope here; the add-parameter popup
offers only the "Create custom parameter" row. Covers the popup in isolation,
the Parameter-list pane's header eligibility rule and wiring, and one
end-to-end pass through the real window via ``AppDriver``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from ui_qt.add_parameter_popup import AddParameterPopup
from ui_qt.parameter_list import ParameterListPanel

_CELL = ("Parameterisation", "Cell")


def _section_node(label: str = "Cell", path=_CELL, parameters=None) -> TreeNode:
    return TreeNode(label=label, path=path, parameters=list(parameters or []))


# ---------------------------------------------------------------------------
# AddParameterPopup: isolated popup behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def anchor(qtbot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def popup(qtbot) -> AddParameterPopup:
    p = AddParameterPopup()
    qtbot.addWidget(p)
    return p


def test_no_row_when_text_empty(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    assert popup._list.count() == 0


def test_row_appears_for_new_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("My custom parameter")
    assert popup._list.count() == 1
    assert "My custom parameter" in popup._list.item(0).text()


def test_no_row_for_alias_already_present(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases={"Existing"})
    popup._input.setText("Existing")
    assert popup._list.count() == 0


def test_row_reappears_once_text_diverges_from_existing_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases={"Existing"})
    popup._input.setText("Existing!")
    assert popup._list.count() == 1


def test_click_activates_custom_row(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("New Param")
    item = popup._list.item(0)
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._list.itemClicked.emit(item)
    assert blocker.args[0] == "New Param"
    assert popup.isVisible() is False


def test_enter_activates_custom_row(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("New Param")
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._activate()
    assert blocker.args[0] == "New Param"


def test_staged_escape_clears_text_then_closes(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("partial")

    popup._on_escape()  # first stage: clear typed text
    assert popup._input.text() == ""
    assert popup.isVisible() is True

    popup._on_escape()  # second stage: close the popup
    assert popup.isVisible() is False


def test_focus_out_dismisses_popup(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    assert popup.isVisible() is True
    popup._input.focus_lost.emit()
    assert popup.isVisible() is False


def test_reopening_for_a_new_section_clears_stale_state(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("Leftover")
    assert popup._list.count() == 1

    popup.open_for_section(anchor, "Electrolyte", existing_aliases={"Leftover"})
    assert popup._input.text() == ""
    assert popup._list.count() == 0


# ---------------------------------------------------------------------------
# ParameterListPanel: header eligibility rule + popup wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    return p


def test_add_button_disabled_with_no_node(panel):
    assert panel._add_button.isEnabled() is False


def test_add_button_enabled_for_a_selected_section(panel):
    panel.show_node(_section_node())
    assert panel._add_button.isEnabled() is True


def test_add_button_disabled_again_once_selection_clears(panel):
    panel.show_node(_section_node())
    panel.show_node(None)
    assert panel._add_button.isEnabled() is False


def test_custom_parameter_activation_carries_section_path_and_alias(panel, qtbot):
    panel.show_node(_section_node())
    panel._open_add_popup()
    panel._popup._input.setText("New Param")
    with qtbot.waitSignal(panel.add_parameter_requested) as blocker:
        panel._popup._activate()
    assert blocker.args == [_CELL, "New Param"]


def test_existing_parameter_alias_is_excluded_from_custom_row(panel):
    existing = ParameterItem(
        label="Existing [unit]",
        path=_CELL + ("Existing [unit]",),
        kind=ParameterKind.SCALAR,
    )
    panel.show_node(_section_node(parameters=[existing]))
    panel._open_add_popup()
    panel._popup._input.setText("Existing [unit]")
    assert panel._popup._list.count() == 0


# ---------------------------------------------------------------------------
# End-to-end: header -> popup -> AddParameter command -> RawCard, via AppDriver
# ---------------------------------------------------------------------------


def test_add_custom_parameter_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    assert d.add_parameter_button_enabled() is True

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("My custom parameter")
    d.activate_custom_parameter_row()

    # The command wrote an honest empty value (None -> classifies UNKNOWN),
    # so the new row opens in the editable RawCard fallback.
    assert d.inspector_title() == "My custom parameter"
    assert d.card_is_editable() is True
    assert d.field_value() == ""
    assert any("My custom parameter" in label for label in d.parameter_labels())


def test_add_parameter_button_disabled_with_no_document(app_driver):
    assert app_driver.add_parameter_button_enabled() is False
