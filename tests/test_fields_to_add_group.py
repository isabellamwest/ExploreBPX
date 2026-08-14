"""Tests for the parameter list's "fields to add" group.

The group is synthetic: appended to the parameter list's underlying
QListWidget after the real parameter rows, derived at render time from
core.completion.completion_for and never written into TreeNode.parameters.
Covers the panel in isolation (rendering, expansion state, activation, the
synthetic-row guards, the new reveal_missing_alias seam) and the end-to-end
add flow through the real MainWindow via AppDriver.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core.tree_model import TreeNode
from ui_qt import style
from ui_qt.parameter_list import ParameterListPanel

_CELL = ("Parameterisation", "Cell")

_CELL_FULL = {
    "Electrode area [m2]": 1.0,
    "External surface area [m2]": 1.0,
    "Volume [m3]": 1.0,
    "Number of electrode pairs connected in parallel to make a cell": 1,
    "Lower voltage cut-off [V]": 3.0,
    "Upper voltage cut-off [V]": 4.2,
    "Nominal cell capacity [A.h]": 5.0,
    "Reference temperature [K]": 298.15,
    "Density [kg.m-3]": 1000.0,
    "Specific heat capacity [J.K-1.kg-1]": 900.0,
}

_CELL_MISSING_TWO_OPTIONAL = {
    key: value
    for key, value in _CELL_FULL.items()
    if key not in {"Density [kg.m-3]", "Specific heat capacity [J.K-1.kg-1]"}
}


def _section_node(path=_CELL, label="Cell", value=None, parameters=None) -> TreeNode:
    return TreeNode(label=label, path=path, value=value, parameters=list(parameters or []))


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    qtbot.addWidget(p._popup)
    return p


def _group_header(panel):
    lst = panel._list
    for i in range(lst.count()):
        item = lst.item(i)
        if item.data(panel._GROUP_ROW_KIND_ROLE) == "header":
            return item
    return None


def _suggestion_items(panel):
    lst = panel._list
    return [lst.item(i) for i in range(lst.count()) if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"]


# ---------------------------------------------------------------------------
# Rendering: header count + suppression
# ---------------------------------------------------------------------------


def test_group_header_renders_after_real_rows_with_correct_count(panel):
    from core.parameter_types import ParameterKind
    from core.tree_model import ParameterItem

    real = [
        ParameterItem(label=alias, path=_CELL + (alias,), kind=ParameterKind.SCALAR)
        for alias in _CELL_MISSING_TWO_OPTIONAL
    ]
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL, parameters=real), model="SPM")

    assert panel._list.count() == len(real) + 1  # real rows, then one header row
    header = panel._list.item(len(real))
    assert header.data(panel._GROUP_ROW_KIND_ROLE) == "header"
    assert header.text() == "▸ 2 fields to add"


def test_group_is_suppressed_for_a_validation_run_node(panel):
    """A run's ExperimentCard already renders every schema column (required
    ones as typable columns, Temperature behind its own "+"), so the run
    node gets no "fields to add" group: its "+ Time [s]" suggestion used to
    write [] while the card looked identical before and after."""
    from core.parameter_types import ParameterKind
    from core.tree_model import ParameterItem

    run_path = ("Validation", "My run")
    real = [ParameterItem(label="Time [s]", path=run_path + ("Time [s]",), kind=ParameterKind.SERIES)]
    panel.show_node(
        _section_node(path=run_path, label="My run", value={"Time [s]": [0, 1]}, parameters=real),
        model="SPM",
    )

    assert _group_header(panel) is None


def test_group_absent_when_no_missing_fields(panel):
    panel.show_node(_section_node(value=_CELL_FULL), model="SPM")
    assert _group_header(panel) is None
    assert panel._list.count() == 0


def test_group_absent_when_node_is_none(panel):
    panel.show_node(None)
    assert panel._list.count() == 0


@pytest.mark.parametrize("model", [None, "banana", "flux-capacitor"])
def test_group_absent_for_undeclared_or_garbage_model(panel, model):
    panel.show_node(_section_node(value={}), model=model)
    assert _group_header(panel) is None
    assert panel._list.count() == 0


# ---------------------------------------------------------------------------
# Expansion: collapsed by default, toggles, survives same-section rebuilds,
# resets on navigation to a different section.
# ---------------------------------------------------------------------------


def test_group_collapsed_by_default(panel):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    assert panel._list.count() == 1
    assert _group_header(panel).text().startswith("▸")


def test_toggling_header_expands_and_collapses(panel):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    header = _group_header(panel)

    panel._list.itemClicked.emit(header)
    assert panel._list.count() == 3  # header + 2 suggestion rows
    header = _group_header(panel)
    assert header.text() == "▾ 2 fields to add"
    assert {item.data(panel._GROUP_ROW_ALIAS_ROLE) for item in _suggestion_items(panel)} == {
        "Density [kg.m-3]",
        "Specific heat capacity [J.K-1.kg-1]",
    }

    panel._list.itemClicked.emit(_group_header(panel))
    assert panel._list.count() == 1
    assert _group_header(panel).text() == "▸ 2 fields to add"


def test_expansion_survives_rebuild_of_the_same_section(panel):
    node = _section_node(value=_CELL_MISSING_TWO_OPTIONAL)
    panel.show_node(node, model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    assert _group_header(panel).text().startswith("▾")

    panel.show_node(node, model="SPM")  # simulates the post-add rebuild

    assert _group_header(panel).text().startswith("▾"), "expansion must survive a rebuild of the same section's path"


def test_navigating_to_a_different_section_resets_expansion_to_collapsed(panel):
    cell = _section_node(value=_CELL_MISSING_TWO_OPTIONAL)
    other = _section_node(path=("Parameterisation", "Negative electrode"), label="Negative electrode", value={})

    panel.show_node(cell, model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    assert _group_header(panel).text().startswith("▾")

    panel.show_node(other, model="SPM")

    assert _group_header(panel).text().startswith("▸")


# ---------------------------------------------------------------------------
# Activation: suggestion click/Enter -> add_parameter_requested; header click
# -> toggle only (no add, no parameter_selected).
# ---------------------------------------------------------------------------


def test_suggestion_click_emits_add_parameter_requested(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    row = next(
        item for item in _suggestion_items(panel) if item.data(panel._GROUP_ROW_ALIAS_ROLE) == "Density [kg.m-3]"
    )

    with qtbot.waitSignal(panel.add_parameter_requested) as blocker:
        panel._list.itemClicked.emit(row)
    assert blocker.args == [_CELL, "Density [kg.m-3]", None]


def test_enter_on_current_suggestion_row_emits_add_parameter_requested(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    row = next(
        item for item in _suggestion_items(panel) if item.data(panel._GROUP_ROW_ALIAS_ROLE) == "Density [kg.m-3]"
    )
    panel._list.setCurrentItem(row)

    with qtbot.waitSignal(panel.add_parameter_requested) as blocker:
        qtbot.keyClick(panel._list, Qt.Key_Return)
    assert blocker.args == [_CELL, "Density [kg.m-3]", None]


def test_enter_on_current_header_row_does_not_add(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.setCurrentItem(_group_header(panel))

    with qtbot.assertNotEmitted(panel.add_parameter_requested):
        qtbot.keyClick(panel._list, Qt.Key_Return)


# ---------------------------------------------------------------------------
# Required tags: present under a concrete model, absent under Partial.
# ---------------------------------------------------------------------------


def test_required_tag_present_under_concrete_model(panel):
    panel.show_node(_section_node(value={}), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    row = next(
        item for item in _suggestion_items(panel) if item.data(panel._GROUP_ROW_ALIAS_ROLE) == "Electrode area [m2]"
    )
    from ui_qt import parameter_row

    html = row.data(parameter_row.HTML_ROLE)
    assert "Required" in html
    assert f"color:{style.REQUIRED}" in html


def test_required_tag_absent_under_partial(panel):
    panel.show_node(_section_node(value={}), model="Partial")
    panel._list.itemClicked.emit(_group_header(panel))
    from ui_qt import parameter_row

    for row in _suggestion_items(panel):
        html = row.data(parameter_row.HTML_ROLE)
        assert "Required" not in html


# ---------------------------------------------------------------------------
# Synthetic-row guards: not a parameter row.
# ---------------------------------------------------------------------------


def test_clicking_header_does_not_select_a_parameter(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    with qtbot.assertNotEmitted(panel.parameter_selected):
        panel._list.itemClicked.emit(_group_header(panel))


def test_clicking_suggestion_does_not_select_a_parameter(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    row = _suggestion_items(panel)[0]
    with qtbot.assertNotEmitted(panel.parameter_selected):
        panel._list.itemClicked.emit(row)


def test_delete_on_header_row_is_a_noop(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.setCurrentItem(_group_header(panel))
    with qtbot.assertNotEmitted(panel.remove_parameter_requested):
        qtbot.keyClick(panel._list, Qt.Key_Delete)


def test_delete_on_suggestion_row_is_a_noop(panel, qtbot):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    panel._list.setCurrentItem(_suggestion_items(panel)[0])
    with qtbot.assertNotEmitted(panel.remove_parameter_requested):
        qtbot.keyClick(panel._list, Qt.Key_Delete)


def test_right_click_on_header_row_opens_no_menu(panel):
    from PySide6.QtWidgets import QApplication

    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    header = _group_header(panel)
    pos = panel._list.visualItemRect(header).center()

    panel._on_context_menu_requested(pos)

    assert QApplication.instance().activePopupWidget() is None


def test_right_click_on_suggestion_row_opens_no_menu(panel):
    from PySide6.QtWidgets import QApplication

    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    panel._list.itemClicked.emit(_group_header(panel))
    row = _suggestion_items(panel)[0]
    pos = panel._list.visualItemRect(row).center()

    panel._on_context_menu_requested(pos)

    assert QApplication.instance().activePopupWidget() is None


# ---------------------------------------------------------------------------
# reveal_missing_alias: the new seam.
# ---------------------------------------------------------------------------


def test_reveal_missing_alias_expands_selects_and_scrolls(panel):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")
    assert _group_header(panel).text().startswith("▸")

    found = panel.reveal_missing_alias("Density [kg.m-3]")

    assert found is True
    assert _group_header(panel).text().startswith("▾")
    current = panel._list.currentItem()
    assert current.data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
    assert current.data(panel._GROUP_ROW_ALIAS_ROLE) == "Density [kg.m-3]"


def test_reveal_missing_alias_returns_false_for_unknown_alias(panel):
    panel.show_node(_section_node(value=_CELL_MISSING_TWO_OPTIONAL), model="SPM")

    assert panel.reveal_missing_alias("Not a real field") is False


def test_reveal_missing_alias_returns_false_with_no_node(panel):
    panel.show_node(None)
    assert panel.reveal_missing_alias("Density [kg.m-3]") is False


# ---------------------------------------------------------------------------
# End-to-end: two adds in a row, through the real MainWindow -- the
# state-survival regression this whole group exists to avoid.
# ---------------------------------------------------------------------------


def test_add_two_suggestions_in_a_row_keeps_group_expanded_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    assert d.fields_to_add_header_text() == "▸ 2 fields to add"
    d.toggle_fields_to_add_group()
    assert d.fields_to_add_header_text() == "▾ 2 fields to add"
    assert set(d.fields_to_add_suggestion_aliases()) == {
        "Density [kg.m-3]",
        "Specific heat capacity [J.K-1.kg-1]",
    }

    d.click_fields_to_add_suggestion("Density [kg.m-3]")
    assert d.inspector_title() == "Density [kg.m-3]"
    assert d.card_is_editable() is True
    assert d.fields_to_add_header_text() == "▾ 1 field to add"
    assert d.fields_to_add_suggestion_aliases() == ["Specific heat capacity [J.K-1.kg-1]"]

    d.click_fields_to_add_suggestion("Specific heat capacity [J.K-1.kg-1]")
    assert d.inspector_title() == "Specific heat capacity [J.K-1.kg-1]"
    assert d.card_is_editable() is True
    assert d.fields_to_add_header_text() is None
    assert any("Density" in label for label in d.parameter_labels())
    assert any("Specific heat capacity" in label for label in d.parameter_labels())


def test_fields_to_add_group_absent_for_undeclared_model_end_to_end(app_driver, tmp_path):
    import json

    from core import document_factory

    raw = document_factory.create("SPM", title="probe")
    del raw["Header"]["Model"]
    path = tmp_path / "no_model.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    d = app_driver
    d.open(path)
    d.select_object(_CELL)

    assert d.fields_to_add_header_text() is None


def test_fields_to_add_group_present_with_no_required_tags_under_partial_end_to_end(app_driver, tmp_path):
    import json

    from core import document_factory

    raw = document_factory.create("Partial", title="probe")
    # The Partial skeleton scaffolds no sections at all (Parameterisation is
    # `{}`) -- a Cell tree node must exist for select_object to resolve one,
    # and an empty Cell immediately suggests every expected field.
    raw["Parameterisation"]["Cell"] = {}
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    d = app_driver
    d.open(path)
    d.select_object(_CELL)

    assert d.fields_to_add_header_text() is not None
    d.toggle_fields_to_add_group()
    assert "Required" not in "".join(d.parameter_labels())


def test_opening_a_different_document_resets_expansion_end_to_end(app_driver, spm_workfile, tmp_path):
    """The panel's expansion dict is keyed by section path only, so a
    previous document's expanded "Cell" group must not leak into a freshly
    opened document's same-named "Cell" section -- "closed by default"
    applies per document, not just per section path."""
    import json
    import shutil

    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    d.toggle_fields_to_add_group()
    assert d.fields_to_add_header_text() == "▾ 2 fields to add"

    other_path = tmp_path / "second_document.json"
    shutil.copy(spm_workfile, other_path)
    raw = json.loads(other_path.read_text(encoding="utf-8"))
    raw["Header"]["Title"] = "A different document"
    other_path.write_text(json.dumps(raw), encoding="utf-8")

    d.open(other_path)
    d.select_object(_CELL)

    assert d.fields_to_add_header_text() == "▸ 2 fields to add"
