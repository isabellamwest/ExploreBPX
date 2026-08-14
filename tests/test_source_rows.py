"""core.source_rows: the pure aligned row model behind the Source page
(multi-file track M5, decision 13)."""

from __future__ import annotations

from explore_bpx.core.compare import RowState
from explore_bpx.core.source_rows import RowKind, SourceRow, build_rows, format_value


def _params(rows: list[SourceRow]) -> list[SourceRow]:
    return [row for row in rows if row.kind is RowKind.PARAM]


def _sections(rows: list[SourceRow]) -> list[SourceRow]:
    return [row for row in rows if row.kind is RowKind.SECTION]


def _paths(rows: list[SourceRow]) -> list[tuple[str, ...]]:
    return [row.path for row in rows]


def test_document_order_preserved_with_interleaved_sections_and_leaves():
    """Rows follow the raw dict's own order: leaves and subsections
    interleaved exactly as the JSON file has them, never leaves-first."""
    main_raw = {
        "Section": {
            "A": 1,
            "Nested": {"C": "hello"},
            "B": 2.0,
        },
    }

    rows = build_rows(main_raw)

    assert _paths(rows) == [
        ("Section",),
        ("Section", "A"),
        ("Section", "Nested"),
        ("Section", "Nested", "C"),
        ("Section", "B"),
    ]
    assert rows[0].kind is RowKind.SECTION
    assert rows[2].kind is RowKind.SECTION


def test_single_pane_mode_has_no_states_and_no_reference_side():
    main_raw = {"Section": {"A": 1}}

    rows = build_rows(main_raw, None)

    assert all(row.state is None for row in rows)
    assert all(row.in_reference is False for row in rows)
    assert all(row.in_main is True for row in rows)
    assert not any(row.is_difference for row in rows)


def test_states_come_from_the_shared_diff_engine():
    main_raw = {"Section": {"Equal": 1, "Differs": 2, "Fillable": None, "Mine": 3}}
    ref_raw = {"Section": {"Equal": 1, "Differs": 9, "Fillable": 4, "Extra": 5}}

    rows = {row.key: row for row in _params(build_rows(main_raw, ref_raw))}

    assert rows["Equal"].state is RowState.EQUAL
    assert rows["Differs"].state is RowState.DIFFERS
    assert rows["Fillable"].state is RowState.FILLABLE
    assert rows["Mine"].state is RowState.MAIN_ONLY
    assert rows["Extra"].state is RowState.REF_ONLY
    assert rows["Extra"].in_main is False
    assert rows["Extra"].in_reference is True
    assert rows["Mine"].in_reference is False


def test_ref_only_keys_align_after_nearest_preceding_shared_key():
    """A reference-only key slots in after the shared key that precedes it
    in the reference's own order, so the panes stay row-aligned."""
    main_raw = {"Section": {"A": 1, "B": 2, "C": 3}}
    ref_raw = {"Section": {"First": 0, "A": 1, "AfterA": 9, "C": 3, "Last": 9}}

    keys = [row.key for row in _params(build_rows(main_raw, ref_raw))]

    assert keys == ["First", "A", "AfterA", "B", "C", "Last"]


def test_ref_only_section_appears_as_ghost_header_with_ref_only_rows():
    main_raw = {"Kept": {"A": 1}}
    ref_raw = {"Kept": {"A": 1}, "Extra": {"X": 1, "Y": 2}}

    rows = build_rows(main_raw, ref_raw)

    ghost = next(row for row in _sections(rows) if row.path == ("Extra",))
    assert ghost.in_main is False
    assert ghost.in_reference is True
    assert ghost.is_difference is True
    ghost_rows = [row for row in _params(rows) if row.path[0] == "Extra"]
    assert [row.key for row in ghost_rows] == ["X", "Y"]
    assert all(row.state is RowState.REF_ONLY for row in ghost_rows)


def test_main_only_section_is_present_but_never_a_difference():
    main_raw = {"Mine": {"A": 1}}
    ref_raw = {"Other": {"B": 2}}

    rows = build_rows(main_raw, ref_raw)

    mine = next(row for row in _sections(rows) if row.path == ("Mine",))
    assert mine.in_main is True
    assert mine.in_reference is False
    assert mine.is_difference is False
    mine_rows = [row for row in _params(rows) if row.path[0] == "Mine"]
    assert all(row.state is RowState.MAIN_ONLY for row in mine_rows)
    assert not any(row.is_difference for row in mine_rows)


def test_difference_flags_for_stepper_targets():
    main_raw = {"Section": {"Equal": 1, "Differs": 2, "Fillable": None, "Mine": 3}}
    ref_raw = {"Section": {"Equal": 1, "Differs": 9, "Fillable": 4, "Extra": 5}}

    rows = {row.key: row for row in _params(build_rows(main_raw, ref_raw))}

    assert rows["Equal"].is_difference is False
    assert rows["Mine"].is_difference is False
    assert rows["Differs"].is_difference is True
    assert rows["Fillable"].is_difference is True
    assert rows["Extra"].is_difference is True


def test_closable_marks_dict_and_list_leaves_only():
    """Tables (dict/list leaf values) render whole and closable (decision
    15); scalars and function strings never do."""
    main_raw = {
        "Section": {
            "Table": {"x": [1, 2], "y": [3, 4]},
            "Series": [1, 2, 3],
            "Scalar": 1.5,
            "Function": "2 * x",
        },
    }

    rows = {row.key: row for row in _params(build_rows(main_raw))}

    assert rows["Table"].closable is True
    assert rows["Series"].closable is True
    assert rows["Scalar"].closable is False
    assert rows["Function"].closable is False


def test_closable_when_only_the_reference_side_is_a_table():
    main_raw = {"Section": {"K": 1.0}}
    ref_raw = {"Section": {"K": {"x": [1], "y": [2]}}}

    row = _params(build_rows(main_raw, ref_raw))[0]

    assert row.closable is True
    assert row.state is RowState.DIFFERS


def test_key_and_depth_properties():
    main_raw = {"Section": {"Nested": {"Leaf": 1}}}

    rows = {row.path: row for row in build_rows(main_raw)}

    assert rows[("Section",)].depth == 0
    assert rows[("Section", "Nested")].depth == 1
    assert rows[("Section", "Nested")].key == "Nested"
    assert rows[("Section", "Nested", "Leaf")].depth == 2
    assert rows[("Section", "Nested", "Leaf")].key == "Leaf"


def test_section_on_one_side_leaf_on_the_other_yields_both_rows():
    """Same key, object node in the main but a scalar in the reference:
    compare classifies the leaf side within the parent, so both a section
    header (gap on the reference side) and a leaf row must render."""
    main_raw = {"Section": {"K": {"Inner": 1}}}
    ref_raw = {"Section": {"K": 5}}

    rows = build_rows(main_raw, ref_raw)

    section = next(row for row in _sections(rows) if row.path == ("Section", "K"))
    assert section.in_main is True
    assert section.in_reference is False
    leaf = next(row for row in _params(rows) if row.path == ("Section", "K"))
    assert leaf.state is RowState.REF_ONLY
    assert leaf.ref_value == 5


def test_values_carried_verbatim_per_side():
    main_raw = {"Section": {"K": 1.0}}
    ref_raw = {"Section": {"K": 2.5}}

    row = _params(build_rows(main_raw, ref_raw))[0]

    assert row.main_value == 1.0
    assert row.ref_value == 2.5


def test_inputs_never_mutated():
    main_raw = {"Section": {"A": 1}}
    ref_raw = {"Section": {"A": 2, "B": 3}}
    main_copy = {"Section": {"A": 1}}
    ref_copy = {"Section": {"A": 2, "B": 3}}

    build_rows(main_raw, ref_raw)

    assert main_raw == main_copy
    assert ref_raw == ref_copy


def test_format_value_is_one_line_json():
    assert format_value(1.5) == "1.5"
    assert format_value(True) == "true"
    assert format_value(None) == "null"
    assert format_value("2 * x") == '"2 * x"'
    assert format_value("Thickness [µm]") == '"Thickness [µm]"'
    assert format_value({"x": [1, 2]}) == '{"x": [1, 2]}'
