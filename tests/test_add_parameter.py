"""Tests for the add-parameter feature: the "+ Add parameter" header entry
point (W2), the custom-add workflow, and BPX-alias suggestions layered into
the same popup (W1).

Covers the popup in isolation (custom-add, suggestion rows, coexistence and
the electrode/unresolvable-section suggestion degrade), the Parameter-list
pane's header eligibility rule and wiring (including how the section path and
declared model reach the popup), and end-to-end passes through the real
window via ``AppDriver``.
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
_NEGATIVE_ELECTRODE = ("Parameterisation", "Negative electrode")

#: The Cell section's schema-expected aliases actually present in the SPM
#: example file (see examples/spm_example_valid.json), so suggestion tests can
#: reliably pick an alias the schema expects but the section does not yet have.
_CELL_PRESENT_ALIASES = {
    "Reference temperature [K]",
    "Electrode area [m2]",
    "External surface area [m2]",
    "Volume [m3]",
    "Number of electrode pairs connected in parallel to make a cell",
    "Nominal cell capacity [A.h]",
    "Lower voltage cut-off [V]",
    "Upper voltage cut-off [V]",
}


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
# AddParameterPopup: BPX-alias suggestions (W1)
# ---------------------------------------------------------------------------


def test_suggestion_row_appears_for_expected_but_absent_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")  # exact match: no separate custom row
    assert popup._list.count() == 1
    text = popup._list.item(0).text()
    assert "Density [kg.m-3]" in text
    assert "kg.m-3" in text  # honest unit hint from the alias itself
    assert "Number" in text  # honest kind hint from FieldMeta flags


def test_suggestion_row_shows_required_marker(popup, anchor):
    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    popup._input.setText("Electrode area [m2]")  # exact match: no separate custom row
    assert popup._list.count() == 1
    assert "Required" in popup._list.item(0).text()


def test_suggestion_row_omits_required_marker_when_not_required(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")
    assert "Required" not in popup._list.item(0).text()


def test_no_suggestion_for_alias_already_present_in_section(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Nominal cell capacity [A.h]")
    assert popup._list.count() == 0  # excluded as suggestion AND as custom row


def test_custom_fallback_omitted_when_typed_text_exactly_matches_a_suggestion(
    popup, anchor
):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")
    assert popup._list.count() == 1  # the suggestion row only, no separate custom row


def test_custom_fallback_coexists_with_a_partial_suggestion_match(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Densit")
    assert popup._list.count() == 2
    assert "Density [kg.m-3]" in popup._list.item(0).text()  # suggestions first
    assert "Create custom parameter" in popup._list.item(1).text()  # custom last


def test_selecting_a_suggestion_emits_its_known_alias(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density")
    item = popup._list.item(0)
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._list.itemClicked.emit(item)
    assert blocker.args[0] == "Density [kg.m-3]"


def test_electrode_section_degrades_to_no_suggestions_but_custom_still_works(
    popup, anchor, qtbot
):
    popup.open_for_section(anchor, "Negative electrode", set(), _NEGATIVE_ELECTRODE, "SPM")
    assert popup._hint_label.isVisible() is True

    popup._input.setText("A brand new field")
    assert popup._list.count() == 1  # custom fallback only, no suggestion rows
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._activate()
    assert blocker.args[0] == "A brand new field"


def test_hint_hidden_once_a_resolvable_section_is_opened(popup, anchor):
    popup.open_for_section(anchor, "Negative electrode", set(), _NEGATIVE_ELECTRODE, "SPM")
    assert popup._hint_label.isVisible() is True

    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    assert popup._hint_label.isVisible() is False


# ---------------------------------------------------------------------------
# AddParameterPopup: empty-input full expected list, other-BPX-alias grey
# tier, and the bounded/scrolling suggestion list
# ---------------------------------------------------------------------------


def test_empty_input_lists_all_expected_but_absent_aliases(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    # Cell's schema expects 10 aliases; _CELL_PRESENT_ALIASES already has 8,
    # leaving "Density [kg.m-3]" and "Specific heat capacity [J.K-1.kg-1]".
    assert popup._list.count() == 2
    shown = {popup._list.item(i).data(popup._ALIAS_ROLE) for i in range(2)}
    assert shown == {"Density [kg.m-3]", "Specific heat capacity [J.K-1.kg-1]"}
    for i in range(2):
        assert popup._list.item(i).data(popup._TIER_ROLE) == "expected"


def test_electrode_section_empty_input_shows_hint_and_no_rows(popup, anchor):
    popup.open_for_section(anchor, "Negative electrode", set(), _NEGATIVE_ELECTRODE, "SPM")
    assert popup._hint_label.isVisible() is True
    assert popup._list.count() == 0


def test_typed_search_shows_expected_then_other_bpx_aliases_as_grey_tier(popup, anchor):
    # Exclude "Reference temperature [K]" (Cell-expected, optional) from the
    # present set so it surfaces as an expected match; three other BPX
    # aliases containing "temperature" exist but aren't Cell-expected.
    present = _CELL_PRESENT_ALIASES - {"Reference temperature [K]"}
    popup.open_for_section(anchor, "Cell", present, _CELL, "SPM")
    popup._input.setText("temperature")

    assert popup._list.count() == 5  # 1 expected + 3 other + 1 custom
    rows = [popup._list.item(i) for i in range(5)]

    # Expected tier first.
    assert rows[0].data(popup._ALIAS_ROLE) == "Reference temperature [K]"
    assert rows[0].data(popup._TIER_ROLE) == "expected"

    # Other-BPX tier next, in a stable (alphabetical) order, no Required marker.
    other_aliases = [rows[i].data(popup._ALIAS_ROLE) for i in range(1, 4)]
    assert other_aliases == [
        "Ambient temperature [K]",
        "Initial temperature [K]",
        "Temperature [K]",
    ]
    for row in rows[1:4]:
        assert row.data(popup._TIER_ROLE) == "other"
        assert "Required" not in row.text()

    # Custom-create row last.
    assert rows[4].data(popup._TIER_ROLE) == "custom"
    assert "Create custom parameter" in rows[4].text()


def test_grey_tier_excludes_expected_and_already_present_aliases(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    # "Density [kg.m-3]" is Cell-expected (and absent): an exact-alias search
    # must surface it exactly once, as the "expected" row -- not a second
    # time as a "grey" duplicate, since it's excluded from the other-BPX
    # tier by membership in the section's expected set.
    popup._input.setText("Density [kg.m-3]")
    assert popup._list.count() == 1
    assert popup._list.item(0).data(popup._TIER_ROLE) == "expected"

    # "Nominal cell capacity [A.h]" is both Cell-expected and already
    # present: excluded from the expected tier (present) and the grey tier
    # (expected-set membership), leaving only the custom-create fallback.
    popup._input.setText("Nominal cell capacity [A.h]")
    assert popup._list.count() == 0  # already present -> custom row also withheld


def test_electrode_section_typed_search_surfaces_grey_matches_while_custom_still_works(
    popup, anchor, qtbot
):
    popup.open_for_section(anchor, "Negative electrode", set(), _NEGATIVE_ELECTRODE, "SPM")
    popup._input.setText("temperature")

    # No expected tier (unresolvable section, so nothing is excluded as
    # "expected" either) -- every BPX alias matching "temperature" surfaces
    # as a grey "other" row, plus the custom fallback.
    assert popup._list.count() == 5  # 4 grey matches + 1 custom
    other_aliases = [popup._list.item(i).data(popup._ALIAS_ROLE) for i in range(4)]
    assert other_aliases == [
        "Ambient temperature [K]",
        "Initial temperature [K]",
        "Reference temperature [K]",
        "Temperature [K]",
    ]
    tiers = [popup._list.item(i).data(popup._TIER_ROLE) for i in range(5)]
    assert tiers == ["other", "other", "other", "other", "custom"]

    popup._list.setCurrentRow(4)  # the custom-create row
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._activate()
    assert blocker.args[0] == "temperature"


def test_grey_row_is_visually_distinguished_from_expected_row(popup, anchor):
    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")  # Cell-expected: only row shown
    expected_item = popup._list.item(0)
    assert expected_item.data(popup._TIER_ROLE) == "expected"
    expected_color = expected_item.foreground().color().name()

    popup._input.setText("Porosity")  # not Cell-expected: grey row
    grey_item = popup._list.item(0)
    assert grey_item.data(popup._TIER_ROLE) == "other"
    assert grey_item.foreground().color().name() != expected_color


def test_suggestion_list_scrolls_when_content_exceeds_visible_row_cap(popup, anchor):
    from ui_qt.add_parameter_popup import _MAX_VISIBLE_ROWS

    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    popup._input.setText("a")  # broad match: well over the visible-row cap
    assert popup._list.count() > _MAX_VISIBLE_ROWS

    row_height = popup._list.sizeHintForRow(0)
    expected_cap = row_height * _MAX_VISIBLE_ROWS + 2 * popup._list.frameWidth()
    assert popup._list.maximumHeight() == expected_cap
    # The popup itself must not grow taller than the (capped) list allows.
    assert popup.sizeHint().height() < 2000


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


def test_reveal_forwards_model_to_show_node(panel):
    panel.reveal(_section_node(), None, "SPM")
    assert panel._model == "SPM"


def test_popup_receives_section_path_and_model_for_suggestions(panel):
    panel.show_node(_section_node(), model="SPM")
    panel._open_add_popup()
    panel._popup._input.setText("Density [kg.m-3]")
    assert panel._popup._list.count() == 1
    assert "Density [kg.m-3]" in panel._popup._list.item(0).text()


def test_popup_degrades_for_electrode_node_via_panel(panel):
    node = _section_node(label="Negative electrode", path=_NEGATIVE_ELECTRODE)
    panel.show_node(node, model="SPM")
    panel._open_add_popup()
    assert panel._popup._hint_label.isVisible() is True

    panel._popup._input.setText("New field")
    assert panel._popup._list.count() == 1  # custom fallback only


# ---------------------------------------------------------------------------
# End-to-end: header -> popup -> AddParameter command -> editor card, via AppDriver
# ---------------------------------------------------------------------------


def test_add_custom_parameter_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    assert d.add_parameter_button_enabled() is True

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("My custom parameter")
    d.activate_selected_add_parameter_row()

    # The command wrote an honest empty value (None -> classifies UNKNOWN),
    # so the new row opens in the editable RawCard fallback.
    assert d.inspector_title() == "My custom parameter"
    assert d.card_is_editable() is True
    assert d.field_value() == ""
    assert any("My custom parameter" in label for label in d.parameter_labels())


def test_add_known_alias_suggestion_end_to_end(app_driver, spm_workfile):
    """Selecting a suggestion routes through the same AddParameter path as
    the custom row, but a known alias resolves its FieldMeta on rebuild and
    opens the proper metadata-driven editor rather than the RawCard fallback."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("Density [kg.m-3]")
    assert d.add_parameter_row_count() == 1
    d.activate_selected_add_parameter_row()

    assert d.inspector_title() == "Density [kg.m-3]"
    assert d.editor_kind() == "ScalarCard"
    assert d.card_is_editable() is True
    assert any("Density" in label for label in d.parameter_labels())


def test_add_grey_other_bpx_alias_suggestion_end_to_end(app_driver, spm_workfile):
    """Selecting a grey ("other BPX alias") row -- a known alias the Cell
    section doesn't itself expect -- routes through the same AddParameter
    path and still resolves its proper metadata-driven editor on rebuild,
    since metadata resolves by leaf alias regardless of section."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("Porosity")  # a real BPX alias, not Cell-expected
    assert d.add_parameter_row_count() == 1
    d.activate_selected_add_parameter_row()

    assert d.inspector_title() == "Porosity"
    assert d.editor_kind() == "ScalarCard"
    assert d.card_is_editable() is True
    assert any("Porosity" in label for label in d.parameter_labels())


def test_electrode_section_suggestions_degrade_but_custom_add_still_works_end_to_end(
    app_driver, spm_workfile
):
    """An electrode section has no resolvable single/blended schema definition
    without content, so `expected_fields` raises; the popup must catch that
    and keep the custom-add path fully functional."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_NEGATIVE_ELECTRODE)

    d.open_add_parameter_popup()
    assert d.add_parameter_hint_text() != ""

    d.type_new_parameter_alias("My hand-typed field")
    assert d.add_parameter_row_count() == 1  # custom fallback only, no suggestions
    d.activate_selected_add_parameter_row()

    assert d.inspector_title() == "My hand-typed field"
    assert d.card_is_editable() is True


def test_add_parameter_button_disabled_with_no_document(app_driver):
    assert app_driver.add_parameter_button_enabled() is False
