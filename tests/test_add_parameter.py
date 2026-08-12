"""Tests for the add-parameter feature: the "+ Add parameter" header entry
point (W2), the custom-add workflow, and the grouped BPX-parameter picker
(W1).

The popup lists the whole BPX standard for the target section up front (no
typing required) under at most two headed groups -- "Suggested" (the section's
schema-expected, still-absent fields, highlighted in accent blue) and "Other
parameters" (everything else in the standard) -- with a pinned "Create custom
parameter" footer beneath. A handful of sections still have no single schema
definition to resolve at all (a ``Particle`` container, a ``Validation`` run
instance) and simply have no suggested group; they still list the whole
standard.

Covers the popup in isolation (grouping, highlighting, filtering, custom-add,
keyboard navigation), the Parameter-list pane's header eligibility rule and
wiring, and end-to-end passes through the real window via ``AppDriver``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from ui_qt import style
from ui_qt.add_parameter_popup import (
    _OTHER_HEADER,
    _SUGGESTED_HEADER,
    _TAB_LABELS,
    AddParameterPopup,
)
from ui_qt.parameter_list import ParameterListPanel

_CELL = ("Parameterisation", "Cell")
_NEGATIVE_ELECTRODE = ("Parameterisation", "Negative electrode")
_POSITIVE_ELECTRODE = ("Parameterisation", "Positive electrode")

#: The Cell section's schema-expected aliases actually present in the SPM
#: fixture (see tests/fixtures/spm_example_valid.json), so suggestion tests can
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


# -- helpers reading the grouped list ---------------------------------------


def _rows(popup):
    """(alias, tier) for every real (non-header) row, in list order."""
    lst = popup._list
    return [
        (lst.item(i).data(popup._ALIAS_ROLE), lst.item(i).data(popup._TIER_ROLE))
        for i in range(lst.count())
        if lst.item(i).data(popup._TIER_ROLE) != "header"
    ]


def _aliases(popup, tier=None):
    return [alias for alias, t in _rows(popup) if tier is None or t == tier]


def _headers(popup):
    lst = popup._list
    return [
        lst.item(i).text()
        for i in range(lst.count())
        if lst.item(i).data(popup._TIER_ROLE) == "header"
    ]


def _row_item(popup, alias):
    lst = popup._list
    for i in range(lst.count()):
        if lst.item(i).data(popup._ALIAS_ROLE) == alias:
            return lst.item(i)
    return None


# ---------------------------------------------------------------------------
# AddParameterPopup: grouping, highlighting, filtering
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


# ---------------------------------------------------------------------------
# AddParameterPopup: Standard/Custom tab strip
# ---------------------------------------------------------------------------


def test_popup_opens_on_standard_tab_with_tab_strip_visible(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    assert popup._active_tab == _TAB_LABELS[0]
    assert popup._tab_strip.isVisible() is True
    assert popup._tab_strip.current_index() == 0
    assert popup._input.isVisible() is True
    assert popup._list.isVisible() is True
    assert popup._form.isVisible() is False


def test_clicking_custom_tab_switches_directly_without_the_footer(popup, anchor, qtbot):
    """The Custom tab is reachable on its own, not only through the pinned
    footer -- clicking it shows the form directly."""
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._tab_strip._buttons[1].click()

    assert popup._active_tab == "Custom"
    assert popup._form.isVisible() is True
    assert popup._input.isVisible() is False
    assert popup._list.isVisible() is False


def test_direct_custom_tab_add_emits_key_and_seed(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._tab_strip._buttons[1].click()  # straight to Custom, no footer involved
    popup._form_name.setText("Straight to custom")
    popup._form_unit.setText("V")

    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._form_add.click()
    assert blocker.args == ["Straight to custom [V]", 0.0]  # Scalar is the default type


def test_clicking_standard_tab_after_custom_returns_without_clearing_via_cancel(popup, anchor):
    """Clicking the Standard tab directly (not Cancel) still switches back --
    only Cancel is documented to clear the form's fields."""
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._tab_strip._buttons[1].click()
    popup._tab_strip._buttons[0].click()

    assert popup._active_tab == "Standard"
    assert popup._input.isVisible() is True
    assert popup._form.isVisible() is False


def test_empty_input_lists_the_whole_standard_in_two_groups(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")

    # Cell's schema expects 10 aliases; _CELL_PRESENT_ALIASES already has 8,
    # leaving these two as the highlighted "suggested" group -- without typing.
    assert set(_aliases(popup, "suggested")) == {
        "Density [kg.m-3]",
        "Specific heat capacity [J.K-1.kg-1]",
    }
    # The "other" group is the rest of the standard, and is substantial.
    others = _aliases(popup, "other")
    assert len(others) > 10
    assert "Porosity" in others  # a real BPX alias Cell doesn't expect

    # Nothing already present appears anywhere; suggested and other never overlap.
    all_shown = set(_aliases(popup))
    assert all_shown.isdisjoint(_CELL_PRESENT_ALIASES)
    assert set(_aliases(popup, "suggested")).isdisjoint(others)

    assert _headers(popup) == [_SUGGESTED_HEADER, _OTHER_HEADER]


def test_electrode_section_suggests_single_particle_fields_when_value_empty(popup, anchor):
    """No live value (the common case) has no ``Particle`` discriminator, so
    the electrode resolves to the single-particle shape and does suggest
    fields -- an electrode is not one of the genuinely unresolvable sections."""
    popup.open_for_section(anchor, "Negative electrode", set(), _NEGATIVE_ELECTRODE, "SPM")

    suggested = set(_aliases(popup, "suggested"))
    assert "Diffusivity [m2.s-1]" in suggested
    assert "Porosity" not in suggested  # SPM's electrode shape excludes it
    assert _headers(popup) == [_SUGGESTED_HEADER, _OTHER_HEADER]


def test_electrode_section_suggests_blended_fields_when_particle_present(popup, anchor):
    """The blended shape's only container property is ``Particle`` itself
    (a child *section*, not a parameter) -- offering it here would let
    activating the row silently overwrite the whole ``Particle`` dict (every
    material, every parameter under it) via
    ``core.editing.add_parameter``'s unconditional ``parent[key] = value``.
    The popup filters it out, leaving the section's genuine leaf field."""
    popup.open_for_section(
        anchor, "Positive electrode", set(), _POSITIVE_ELECTRODE, "SPM", {"Particle": {}}
    )

    assert set(_aliases(popup, "suggested")) == {"Thickness [m]"}


def test_container_property_is_never_offered_as_an_addable_parameter(popup, anchor):
    """Regression for the popup-destroys-a-section defect: a container-link
    schema property (identifies a child *section*, not a leaf parameter) must
    never appear in either group, whatever section is open -- activating it
    would route through ``AddParameter`` -> ``core.editing.add_parameter``'s
    unconditional ``parent[key] = value`` and silently replace the whole
    child section with ``None``."""
    popup.open_for_section(
        anchor, "Positive electrode", set(), _POSITIVE_ELECTRODE, "SPM", {"Particle": {}}
    )
    assert "Particle" not in _aliases(popup, "suggested")
    assert "Particle" not in _aliases(popup, "other")

    popup.open_for_section(anchor, "Parameterisation", set(), ("Parameterisation",), "SPM")
    assert "Cell" not in _aliases(popup, "suggested")
    assert "Cell" not in _aliases(popup, "other")


def test_unresolvable_section_still_lists_the_standard_with_no_suggested_group(popup, anchor):
    """A ``Particle`` container itself (not a named instance) has no single
    schema definition -- it is a dict-keyed collection, addressed by "Add
    material…" instead -- so it genuinely has no suggested group."""
    particle_container = ("Parameterisation", "Negative electrode", "Particle")
    popup.open_for_section(anchor, "Particle", set(), particle_container, "SPM")

    assert _aliases(popup, "suggested") == []
    assert len(_aliases(popup, "other")) > 10
    assert _headers(popup) == []  # a single ungrouped list needs no header


def test_suggested_rows_are_highlighted_distinctly_from_other_rows(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")

    suggested = _row_item(popup, "Density [kg.m-3]")
    other = _row_item(popup, "Porosity")
    assert suggested.data(popup._TIER_ROLE) == "suggested"
    assert other.data(popup._TIER_ROLE) == "other"

    # Suggested rows read in accent blue; other rows use the default text colour.
    assert suggested.foreground().color().name() == style.ACCENT
    assert suggested.foreground().color().name() != other.foreground().color().name()
    assert suggested.font().bold() is True


def test_required_row_carries_required_role_true(popup, anchor):
    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    row = _row_item(popup, "Electrode area [m2]")
    assert row.data(popup._TIER_ROLE) == "suggested"
    assert row.data(popup._REQUIRED_ROLE) is True


def test_required_colours_only_the_tag_never_the_name(popup, anchor):
    """A required field *is* a suggested one, so its name stays accent blue
    like every other suggested row; only the "Required" tag carries the
    required colour. Recolouring the name would split one group into two
    visual tiers."""
    from ui_qt import parameter_row

    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    row = _row_item(popup, "Electrode area [m2]")
    assert row.data(popup._REQUIRED_ROLE) is True

    html = row.data(parameter_row.HTML_ROLE)
    name_span, _, tail = html.partition("Electrode area")
    assert f"color:{style.ACCENT}" in name_span  # the name: blue, like its peers
    assert f"color:{style.REQUIRED}" not in name_span
    assert f"color:{style.REQUIRED}" in tail  # the tag, and only the tag
    assert "Required" in tail
    # And the plain-text fallback foreground agrees.
    assert row.foreground().color().name() == style.ACCENT


def test_non_required_suggested_row_carries_required_role_false(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    row = _row_item(popup, "Density [kg.m-3]")
    assert row.data(popup._REQUIRED_ROLE) is False


def test_other_tier_row_carries_required_role_false(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    row = _row_item(popup, "Porosity")
    assert row.data(popup._TIER_ROLE) == "other"
    assert row.data(popup._REQUIRED_ROLE) is False


def test_typing_filters_both_groups_by_substring(popup, anchor):
    # Exclude "Reference temperature [K]" (Cell-expected) from the present set so
    # it surfaces as a suggested match; three other BPX aliases contain
    # "temperature" but aren't Cell-expected.
    present = _CELL_PRESENT_ALIASES - {"Reference temperature [K]"}
    popup.open_for_section(anchor, "Cell", present, _CELL, "SPM")
    popup._input.setText("temperature")

    assert _aliases(popup, "suggested") == ["Reference temperature [K]"]
    assert _aliases(popup, "other") == [
        "Ambient temperature [K]",
        "Initial temperature [K]",
        "Temperature [K]",
    ]
    assert _headers(popup) == [_SUGGESTED_HEADER, _OTHER_HEADER]
    # The "Other" header (following a group) carries the divider marker.
    other_header = popup._list.item(2)
    assert other_header.data(popup._TIER_ROLE) == "header"
    assert other_header.data(popup._TIER_TOP_ROLE) is True

    # And the pinned custom footer coexists, since "temperature" is a fresh
    # alias. The tooltip is the full-sentence seam: the visible label elides
    # against the card width, and the offscreen fallback font makes the elide
    # point unpredictable.
    assert popup._footer_shown is True
    assert "temperature" in popup._create_button.toolTip()


def test_present_and_expected_aliases_are_excluded_everywhere(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")

    # "Density [kg.m-3]" is Cell-expected and absent: it appears once, suggested.
    popup._input.setText("Density [kg.m-3]")
    assert _aliases(popup, "suggested") == ["Density [kg.m-3]"]
    assert _aliases(popup, "other") == []  # not duplicated into the other group

    # "Nominal cell capacity [A.h]" is expected AND already present: excluded
    # from both groups and withheld from the custom footer.
    popup._input.setText("Nominal cell capacity [A.h]")
    assert _rows(popup) == []
    assert popup._footer_shown is False


# ---------------------------------------------------------------------------
# AddParameterPopup: suggestion row detail + activation
# ---------------------------------------------------------------------------


def test_suggestion_row_carries_honest_kind_and_unit_hints(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")
    text = _row_item(popup, "Density [kg.m-3]").text()
    assert "kg.m-3" in text  # honest unit hint from the alias itself
    assert "FloatInt" in text  # honest kind hint from FieldMeta flags, verbatim BPX vocabulary


def test_suggestion_row_shows_required_marker(popup, anchor):
    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    popup._input.setText("Electrode area [m2]")
    assert "Required" in _row_item(popup, "Electrode area [m2]").text()


def test_suggestion_row_omits_required_marker_when_not_required(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")
    assert "Required" not in _row_item(popup, "Density [kg.m-3]").text()


def test_selecting_a_suggestion_emits_its_known_alias(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density")
    item = _row_item(popup, "Density [kg.m-3]")
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._list.itemClicked.emit(item)
    # A suggestion row never goes through the custom-parameter form -- it
    # always seeds an honest empty value (``None``), like before.
    assert blocker.args == ["Density [kg.m-3]", None]


# ---------------------------------------------------------------------------
# _kind_label: verbatim BPX vocabulary, driven by the live schema.
#
# Each path below is chosen to isolate one FieldMeta flag combination:
#   - LAM: Negative electrode -> allows_map
#   - Validation run's Time [s] -> is_series
#   - Header.Model -> is_enum
#   - Header.Title -> is_text
#   - Cell's nominal capacity -> no flags set (the plain-FloatInt default)
#   - Negative electrode OCP -> allows_function
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, expected_label",
    [
        (("State", "Degradation", "LAM: Negative electrode"), "FloatInt | dict[str, FloatInt]"),
        (("Validation", "some_run", "Time [s]"), "list[FloatInt]"),
        (("Header", "Model"), "enum"),
        (("Header", "Title"), "str"),
        (("Parameterisation", "Cell", "Nominal cell capacity [A.h]"), "FloatInt"),
        (("Parameterisation", "Negative electrode", "OCP [V]"), "FloatFunctionTable"),
    ],
)
def test_kind_label_uses_verbatim_bpx_vocabulary(path, expected_label):
    from core.bpx_gateway import field_meta
    from ui_qt.add_parameter_popup import _kind_label

    meta = field_meta(path)
    assert meta is not None, f"no live FieldMeta resolved for {path!r}"
    assert _kind_label(meta) == expected_label


def test_kind_label_omits_hint_when_nothing_is_known():
    """An alias whose FieldMeta collapses to every flag False, no description
    and no examples (the cross-section-ambiguous case) omits the hint rather
    than guessing "FloatInt"."""
    from core.bpx_gateway import FieldMeta
    from ui_qt.add_parameter_popup import _kind_label

    meta = FieldMeta(alias="Conductivity [S.m-1]")
    assert _kind_label(meta) is None


def test_clicking_a_group_header_does_nothing(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    header = popup._list.item(0)
    assert header.data(popup._TIER_ROLE) == "header"
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._list.itemClicked.emit(header)
    assert popup.isVisible() is True


# ---------------------------------------------------------------------------
# AddParameterPopup: custom-add footer
# ---------------------------------------------------------------------------


def test_footer_appears_for_a_fresh_typed_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("My custom parameter")
    # The custom-add action is the pinned footer, not a scrolling list row, and
    # no BPX alias matches, so the list is empty.
    assert _rows(popup) == []
    assert popup._footer_shown is True
    # toolTip carries the full sentence; the visible label elides against
    # the card width (unpredictably so under the offscreen fallback font).
    assert "My custom parameter" in popup._create_button.toolTip()


def test_footer_withheld_for_an_already_present_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases={"Existing"})
    popup._input.setText("Existing")
    assert popup._footer_shown is False  # can't offer to recreate a present alias


def test_footer_reappears_once_text_diverges_from_a_present_alias(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases={"Existing"})
    popup._input.setText("Existing!")
    assert popup._footer_shown is True


def test_footer_withheld_when_typed_text_exactly_matches_a_suggestion(popup, anchor):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Density [kg.m-3]")
    assert _aliases(popup, "suggested") == ["Density [kg.m-3]"]
    assert popup._footer_shown is False  # use the suggestion, don't duplicate it


def test_click_activates_custom_footer(popup, anchor, qtbot):
    """Clicking the pinned footer switches the popup to its Custom tab --
    no new window, and nothing is created yet."""
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("New Param")
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._create_button.click()
    assert popup.isVisible() is True
    assert popup._active_tab == "Custom"
    assert popup._form.isVisible() is True
    assert popup._input.isVisible() is False  # Standard tab's own content is hidden
    assert popup._form_name.text() == "New Param"  # typed text seeds Name


def test_enter_activates_custom_footer_when_it_is_the_only_target(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("New Param")  # matches no BPX alias
    # With no rows, the footer is the default keyboard target, so Enter switches tab.
    assert popup._footer_selected is True
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._activate()
    assert popup._active_tab == "Custom"
    assert popup._form_name.text() == "New Param"


# ---------------------------------------------------------------------------
# AddParameterPopup: Custom tab form (type-at-creation)
# ---------------------------------------------------------------------------


def _expand_form(popup, anchor, typed: str = "Foo") -> None:
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText(typed)
    popup._activate()  # the footer switches to the Custom tab
    assert popup._active_tab == "Custom"


def test_form_key_composition_without_a_unit(popup, anchor, qtbot):
    _expand_form(popup, anchor)
    popup._form_name.setText("  My field  ")  # leading/trailing whitespace
    popup._form_unit.clear()
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._form_add.click()
    assert blocker.args == ["My field", 0.0]  # Scalar is the default type


def test_form_key_composition_with_a_unit(popup, anchor, qtbot):
    _expand_form(popup, anchor)
    popup._form_name.setText("My field")
    popup._form_unit.setText("  V  ")  # stripped before composing the key
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._form_add.click()
    assert blocker.args == ["My field [V]", 0.0]


@pytest.mark.parametrize(
    "type_label, expected_seed",
    [
        ("Scalar", 0.0),
        ("Text", ""),
        ("Boolean", False),
        ("Table", {"x": [], "y": []}),
        ("Series", []),
    ],
)
def test_form_type_button_picks_the_matching_seed(popup, anchor, qtbot, type_label, expected_seed):
    from ui_qt.add_parameter_popup import _CUSTOM_TYPE_LABELS

    _expand_form(popup, anchor)
    popup._form_name.setText("My field")
    popup._form_type_strip._buttons[_CUSTOM_TYPE_LABELS.index(type_label)].click()
    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._form_add.click()
    assert blocker.args == ["My field", expected_seed]


def test_add_disabled_while_name_is_empty_or_whitespace(popup, anchor):
    _expand_form(popup, anchor)
    assert popup._form_add.isEnabled() is True  # Name was pre-seeded from the typed text

    popup._form_name.setText("   ")  # whitespace only
    assert popup._form_add.isEnabled() is False

    popup._form_name.clear()
    assert popup._form_add.isEnabled() is False

    popup._form_name.setText("Real name")
    assert popup._form_add.isEnabled() is True


def test_add_is_a_no_op_when_name_is_still_empty(popup, anchor, qtbot):
    """Belt-and-braces: even a direct click while disabled creates nothing."""
    _expand_form(popup, anchor)
    popup._form_name.clear()
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._submit_custom_form()
    assert popup.isVisible() is True


def test_add_refuses_a_composed_key_that_collides_with_an_existing_parameter(popup, anchor, qtbot):
    """Regression: Name/Unit split across the two separate form fields must
    not bypass the collision guard just because neither field alone matches
    the existing alias verbatim -- ``core.editing.add_parameter`` writes
    ``parent[key] = value`` unconditionally, so composing back to an
    existing key here must refuse rather than silently overwrite it."""
    existing = {"Diffusivity constant [m2.s-1]"}
    popup.open_for_section(anchor, "Cell", existing_aliases=existing)
    popup._input.setText("Diffusivity constant")
    assert popup._footer_shown is True  # no alias matches the bare name exactly
    popup._activate()  # switches to Custom; Name pre-seeded, Unit still blank
    assert popup._active_tab == "Custom"

    popup._form_unit.setText("m2.s-1")  # now composes back to the existing key
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._form_add.click()

    assert popup._form_message.isVisible() is True
    assert popup.isVisible() is True  # refused in place -- nothing created, popup stays open
    assert popup._active_tab == "Custom"  # the form itself is untouched, ready to correct


def test_editing_name_after_a_collision_clears_the_message_and_allows_a_fresh_add(popup, anchor, qtbot):
    existing = {"Diffusivity constant [m2.s-1]"}
    popup.open_for_section(anchor, "Cell", existing_aliases=existing)
    popup._input.setText("Diffusivity constant")
    popup._activate()
    popup._form_unit.setText("m2.s-1")
    popup._form_add.click()
    assert popup._form_message.isVisible() is True

    popup._form_name.setText("Diffusivity constant 2")  # no longer collides
    assert popup._form_message.isVisible() is False  # editing Name clears the stale message

    with qtbot.waitSignal(popup.custom_parameter_requested) as blocker:
        popup._form_add.click()
    assert blocker.args == ["Diffusivity constant 2 [m2.s-1]", 0.0]


def test_editing_unit_after_a_collision_also_clears_the_message(popup, anchor, qtbot):
    existing = {"Diffusivity constant [m2.s-1]"}
    popup.open_for_section(anchor, "Cell", existing_aliases=existing)
    popup._input.setText("Diffusivity constant")
    popup._activate()
    popup._form_unit.setText("m2.s-1")
    popup._form_add.click()
    assert popup._form_message.isVisible() is True

    popup._form_unit.setText("m2.s-2")  # different unit -> no longer collides
    assert popup._form_message.isVisible() is False


def test_scalar_warning_shown_only_for_scalar_type(popup, anchor):
    from ui_qt.add_parameter_popup import _CUSTOM_TYPE_LABELS

    _expand_form(popup, anchor)
    assert popup._form_warning.isVisible() is True  # Scalar is the default type

    for label in ("Text", "Boolean", "Table", "Series"):
        popup._form_type_strip._buttons[_CUSTOM_TYPE_LABELS.index(label)].click()
        assert popup._form_warning.isVisible() is False, label

    popup._form_type_strip._buttons[_CUSTOM_TYPE_LABELS.index("Scalar")].click()
    assert popup._form_warning.isVisible() is True


def test_cancel_returns_to_standard_tab_and_clears_the_form(popup, anchor, qtbot):
    _expand_form(popup, anchor)
    popup._form_unit.setText("V")

    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._form_cancel.click()

    assert popup._active_tab == "Standard"
    assert popup._form.isVisible() is False
    assert popup._input.isVisible() is True  # Standard tab's own content is back
    assert popup._create_button.isVisible() is True  # the plain footer is back
    assert popup._form_name.text() == ""
    assert popup._form_unit.text() == ""
    assert popup.isVisible() is True  # cancelling stays in the popup, doesn't close it


# ---------------------------------------------------------------------------
# AddParameterPopup: keyboard navigation, escape, focus, sizing
# ---------------------------------------------------------------------------


def test_keyboard_navigation_skips_headers_and_reaches_the_footer(popup, anchor, qtbot):
    popup.open_for_section(anchor, "Cell", _CELL_PRESENT_ALIASES, _CELL, "SPM")
    popup._input.setText("Densit")  # 1 suggested row + custom footer, under a header

    assert _aliases(popup, "suggested") == ["Density [kg.m-3]"]
    assert popup._footer_shown is True
    rows = popup._selectable_rows()
    assert len(rows) == 1  # only the Density row is selectable (header skipped)
    assert popup._list.currentRow() == rows[0]  # first real row selected by default
    assert popup._footer_selected is False

    popup._move_selection(1)  # past the last row -> onto the footer
    assert popup._footer_selected is True
    assert popup._list.currentRow() == -1  # only one thing looks selected

    popup._move_selection(1)  # wraps back to the first real row (never a header)
    assert popup._footer_selected is False
    assert popup._list.currentRow() == rows[0]

    popup._move_selection(-1)  # wraps up onto the footer
    assert popup._footer_selected is True
    with qtbot.assertNotEmitted(popup.custom_parameter_requested):
        popup._activate()  # Enter on the footer switches to Custom, doesn't create yet
    assert popup._active_tab == "Custom"
    assert popup._form_name.text() == "Densit"


def test_staged_escape_clears_text_then_closes(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("partial")

    popup._on_escape()  # first stage: clear typed text
    assert popup._input.text() == ""
    assert popup.isVisible() is True

    popup._on_escape()  # second stage: close the popup
    assert popup.isVisible() is False


def test_focus_lost_signal_removed():
    """The click-away dismissal now goes through the shared
    ``OutsideDismissFilter`` (see test_outside_click_closes_popup below);
    the old focus-out path is dead code and must not linger."""
    from ui_qt.add_parameter_popup import _PopupInput

    assert not hasattr(_PopupInput, "focus_lost")


def test_outside_click_closes_popup_and_is_swallowed(popup, anchor, qtbot):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QPushButton

    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    assert popup.isVisible() is True

    decoy = QPushButton()
    decoy.setGeometry(2000, 2000, 50, 20)
    qtbot.addWidget(decoy)
    decoy.show()
    clicks = []
    decoy.clicked.connect(lambda: clicks.append(1))

    global_pos = decoy.mapToGlobal(decoy.rect().center())
    press = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(decoy.rect().center()), QPointF(global_pos),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    QApplication.instance().sendEvent(decoy, press)
    assert popup.isVisible() is False

    release = QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(decoy.rect().center()), QPointF(global_pos),
        Qt.LeftButton, Qt.NoButton, Qt.NoModifier,
    )
    QApplication.instance().sendEvent(decoy, release)
    assert clicks == []  # the dismissing press never reached the button beneath


def test_outside_click_on_trigger_button_closes_without_reopening(panel, qtbot):
    """The "+ Add parameter" trigger button is deliberately not registered as
    an "inside" widget, so clicking it while the popup is open reads as an
    outside press: it closes (and swallows the click) rather than toggling
    straight back open."""
    panel.show_node(_section_node())
    panel._open_add_popup()
    assert panel._popup.isVisible() is True

    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    button = panel._add_button
    local_pos = button.rect().center()
    global_pos = button.mapToGlobal(local_pos)
    press = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(local_pos), QPointF(global_pos),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )
    QApplication.instance().sendEvent(button, press)
    assert panel._popup.isVisible() is False


def test_reopening_for_a_new_section_clears_stale_state(popup, anchor):
    popup.open_for_section(anchor, "Cell", existing_aliases=set())
    popup._input.setText("Leftover")
    popup._activate()  # switches to Custom, with "Leftover" in Name
    assert popup._footer_shown is True
    assert popup._active_tab == "Custom"

    popup.open_for_section(anchor, "Electrolyte", existing_aliases={"Leftover"})
    assert popup._input.text() == ""
    assert popup._footer_shown is False  # empty input, no fresh alias to create
    assert "Leftover" not in _aliases(popup)  # fresh section, not the stale one
    assert popup._active_tab == "Standard"  # always reopens on Standard
    assert popup._form_name.text() == ""  # the Custom form's stale Name is cleared too


def test_list_scrolls_when_content_exceeds_the_visible_row_cap(popup, anchor):
    from ui_qt.add_parameter_popup import _MAX_VISIBLE_ROWS

    popup.open_for_section(anchor, "Cell", set(), _CELL, "SPM")
    popup._input.setText("a")  # broad match: well over the visible-row cap
    assert popup._list.count() > _MAX_VISIBLE_ROWS

    frame = 2 * popup._list.frameWidth()
    capped = sum(popup._list.sizeHintForRow(i) for i in range(_MAX_VISIBLE_ROWS)) + frame
    assert popup._list.maximumHeight() == capped
    # The popup itself must not grow taller than the (capped) list allows.
    assert popup.sizeHint().height() < 2000


# ---------------------------------------------------------------------------
# ParameterListPanel: header eligibility rule + popup wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    # The add-parameter popup is a floating Qt.Tool window parented (for
    # lifetime, not stacking) to the panel, so closing the panel alone would
    # not close it; register it too so a test that leaves it open doesn't
    # leak its OutsideDismissFilter registration into later tests.
    qtbot.addWidget(p._popup)
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


def test_header_hidden_with_no_node(panel):
    assert panel._header.isHidden() is True


def test_header_shows_section_title_and_parameter_count(panel):
    existing = ParameterItem(
        label="Existing [unit]",
        path=_CELL + ("Existing [unit]",),
        kind=ParameterKind.SCALAR,
    )
    panel.show_node(_section_node(label="Cell", parameters=[existing]))
    assert panel._header.isHidden() is False
    assert panel._header.title_label.text() == "CELL"
    assert panel._count_label.text() == "1"


def test_header_hides_again_once_selection_clears(panel):
    panel.show_node(_section_node())
    panel.show_node(None)
    assert panel._header.isHidden() is True


def test_custom_parameter_form_add_carries_section_path_key_and_seed(panel, qtbot):
    """The Custom tab's "Add" -- not the footer activation itself -- is what
    fires ``add_parameter_requested``, now carrying a seed (Scalar's ``0.0``,
    the default type) alongside the section path and composed key."""
    panel.show_node(_section_node())
    panel._open_add_popup()
    panel._popup._input.setText("New Param")
    panel._popup._activate()  # the footer switches to the Custom tab; doesn't emit yet
    assert panel._popup._active_tab == "Custom"
    with qtbot.waitSignal(panel.add_parameter_requested) as blocker:
        panel._popup._form_add.click()
    assert blocker.args == [_CELL, "New Param", 0.0]


def test_existing_parameter_alias_is_excluded_from_custom_footer(panel):
    existing = ParameterItem(
        label="Existing [unit]",
        path=_CELL + ("Existing [unit]",),
        kind=ParameterKind.SCALAR,
    )
    panel.show_node(_section_node(parameters=[existing]))
    panel._open_add_popup()
    panel._popup._input.setText("Existing [unit]")
    assert panel._popup._footer_shown is False


def test_reveal_forwards_model_to_show_node(panel):
    panel.reveal(_section_node(), None, "SPM")
    assert panel._model == "SPM"


def test_popup_receives_section_path_and_model_for_suggestions(panel):
    panel.show_node(_section_node(), model="SPM")
    panel._open_add_popup()
    panel._popup._input.setText("Density [kg.m-3]")
    assert _aliases(panel._popup, "suggested") == ["Density [kg.m-3]"]


def test_popup_suggests_single_particle_fields_for_electrode_node_without_value(panel):
    """No live value on the node (the common case) has no ``Particle``
    discriminator, so the electrode still resolves -- to the single-particle
    shape -- and does suggest fields."""
    node = _section_node(label="Negative electrode", path=_NEGATIVE_ELECTRODE)
    panel.show_node(node, model="SPM")
    panel._open_add_popup()
    suggested = set(_aliases(panel._popup, "suggested"))
    assert "Diffusivity [m2.s-1]" in suggested
    assert "Porosity" not in suggested  # SPM's electrode shape excludes it
    assert len(_aliases(panel._popup, "other")) > 10

    panel._popup._input.setText("New field")
    assert panel._popup._footer_shown is True  # custom footer still works


def test_popup_suggests_blended_fields_for_electrode_node_with_particle_value(panel):
    """``Particle`` itself is a container-link property (identifies the child
    ``Particle`` section, not a leaf parameter) -- it must never be offered,
    or activating it would silently overwrite the whole ``Particle`` dict."""
    node = TreeNode(
        label="Positive electrode", path=_POSITIVE_ELECTRODE, value={"Particle": {}}
    )
    panel.show_node(node, model="SPM")
    panel._open_add_popup()
    assert set(_aliases(panel._popup, "suggested")) == {"Thickness [m]"}


# ---------------------------------------------------------------------------
# ParameterListPanel: required-parameter marking (rich-row rendering)
# ---------------------------------------------------------------------------


def _find_node(root: TreeNode, path: tuple[str, ...]) -> TreeNode | None:
    if root.path == path:
        return root
    for child in root.children:
        found = _find_node(child, path)
        if found is not None:
            return found
    return None


def test_parameter_list_rows_bold_the_name_and_mute_the_unit(panel, valid_spm_dict):
    """A real document's row renders as rich text: bold bare name, muted
    unit. Requiredness is deliberately *not* coloured here -- that tint is the
    add-parameter popup's language, for choosing a field the section does not
    have yet, and a row in this list is already present."""
    from core.tree_model import build_tree

    from ui_qt import parameter_row, style

    root = build_tree(valid_spm_dict)
    electrode = _find_node(root, _NEGATIVE_ELECTRODE)
    assert electrode is not None
    panel.show_node(electrode, model="SPM")

    lst = panel._list
    thickness = next(
        lst.item(i) for i in range(lst.count()) if lst.item(i).text().startswith("Thickness")
    )
    html = thickness.data(parameter_row.HTML_ROLE)
    assert "Thickness" in html
    assert "[m]" in html
    assert f"color:{style.MUTED}" in html  # the unit
    # ``Thickness [m]`` *is* schema-required for this electrode, and is still
    # not tinted: the list never speaks the popup's required language.
    assert f"color:{style.REQUIRED}" not in html


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
    d.activate_selected_add_parameter_row()  # switches to the Custom tab
    assert d.add_parameter_custom_form_visible() is True
    d.submit_custom_parameter_form()  # Scalar is the default type

    # The command wrote the Scalar type's seed (0.0), so the new row opens
    # straight on the real ScalarCard -- not the metadata-less RawCard
    # fallback the old always-None seed produced.
    assert d.inspector_title() == "My custom parameter"
    assert d.editor_kind() == "ScalarCard"
    assert d.card_is_editable() is True
    assert d.field_value() == 0.0
    assert any("My custom parameter" in label for label in d.parameter_labels())


def test_add_refuses_a_colliding_composed_key_end_to_end(app_driver, spm_workfile):
    """Regression for the popup-overwrites-a-parameter defect: Name/Unit
    composing back to an existing alias -- via the two separate form fields,
    never matching anything the popup's own list/footer guards against on
    their own -- must not execute ``AddParameter`` and silently replace the
    existing value."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    session = d._w._state.active
    cell = session.document.raw["Parameterisation"]["Cell"]
    original = cell["Nominal cell capacity [A.h]"]

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("Nominal cell capacity")  # no exact alias match -> footer offered
    d.activate_selected_add_parameter_row()  # switches to the Custom tab
    assert d.add_parameter_custom_form_visible() is True
    d.type_custom_parameter_unit("A.h")  # composes back to the existing alias
    d.submit_custom_parameter_form()

    popup = d._w._params._popup
    assert popup.isVisible() is True  # refused in place, not closed
    assert popup._form_message.isVisible() is True
    assert cell["Nominal cell capacity [A.h]"] == original  # untouched
    assert (
        sum(1 for label in d.parameter_labels() if label.startswith("Nominal cell capacity"))
        == 1
    )  # no duplicate row either


@pytest.mark.parametrize(
    "type_label, expected_kind, expected_value",
    [
        ("Scalar", "ScalarCard", 0.0),
        ("Text", "TextCard", ""),
        ("Boolean", "BooleanCard", False),
        ("Table", "TableCard", {"x": [], "y": []}),
        ("Series", "SeriesCard", []),
    ],
)
def test_custom_parameter_type_picks_the_matching_card_end_to_end(
    app_driver, spm_workfile, type_label, expected_kind, expected_value
):
    """Each of the five type buttons seeds a value that ``classify`` (no
    schema metadata exists for a custom alias) routes to that exact card --
    the whole point of type-at-creation over the old always-None/RawCard
    fallback."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    d.open_add_parameter_popup()
    d.type_new_parameter_alias(f"My {type_label} field")
    d.activate_selected_add_parameter_row()
    d.select_custom_parameter_type(type_label)
    d.submit_custom_parameter_form()

    assert d.inspector_title() == f"My {type_label} field"
    assert d.editor_kind() == expected_kind
    assert d.field_value() == expected_value


def test_add_known_alias_suggestion_end_to_end(app_driver, spm_workfile):
    """Selecting a suggestion routes through the same AddParameter path as
    the custom footer, but a known alias resolves its FieldMeta on rebuild and
    opens the proper metadata-driven editor rather than the RawCard fallback."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("Density [kg.m-3]")
    assert any("Density" in t for t in d.add_parameter_alias_texts())
    d.activate_selected_add_parameter_row()

    assert d.inspector_title() == "Density [kg.m-3]"
    assert d.editor_kind() == "ScalarCard"
    assert d.card_is_editable() is True
    assert any("Density" in label for label in d.parameter_labels())


def test_add_other_bpx_alias_end_to_end(app_driver, spm_workfile):
    """Selecting an "other" row -- a known alias the Cell section doesn't
    itself expect -- routes through the same AddParameter path. BPX keys
    metadata by (section, alias), not alias alone, and Cell's own schema does
    not define "Porosity" (it belongs to Contact/electrode sections instead),
    so this correctly falls back to the honest, metadata-less RawCard editor
    rather than fabricating a Contact/electrode-flavoured ScalarCard for a
    field Cell's schema doesn't recognise."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)

    d.open_add_parameter_popup()
    d.type_new_parameter_alias("Porosity")  # a real BPX alias, not Cell-expected
    assert any("Porosity" in t for t in d.add_parameter_alias_texts())
    d.activate_selected_add_parameter_row()

    assert d.inspector_title() == "Porosity"
    assert d.editor_kind() == "RawCard"
    assert d.card_is_editable() is True
    assert any("Porosity" in label for label in d.parameter_labels())


def test_electrode_section_lists_standard_and_custom_add_works_end_to_end(
    app_driver, spm_workfile
):
    """An electrode section resolves (Negative electrode here has no ``Particle``
    key, so the single-particle shape) and lists the whole standard; the
    custom-add path stays fully functional regardless."""
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_NEGATIVE_ELECTRODE)

    d.open_add_parameter_popup()
    assert len(d.add_parameter_alias_texts()) > 10  # the whole standard, not a dead end

    d.type_new_parameter_alias("My hand-typed field")
    assert d.add_parameter_can_create_custom() is True
    d.activate_selected_add_parameter_row()
    assert d.add_parameter_custom_form_visible() is True
    d.submit_custom_parameter_form()

    assert d.inspector_title() == "My hand-typed field"
    assert d.card_is_editable() is True


def test_add_parameter_button_disabled_with_no_document(app_driver):
    assert app_driver.add_parameter_button_enabled() is False
