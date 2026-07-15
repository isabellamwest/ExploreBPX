"""Value preview in the parameter list (docs/03-features.md §3).

Rows carry a right-aligned, delegate-elided preview of the committed value:
raw-verbatim for simple kinds, a ghosted "—" for committed null, a ghosted
derived summary for Inspector-only kinds. Editing stays in the Inspector —
the preview replaced the once-planned inline quick inputs (user decision,
2026-07-15): scanning was the value; the Inspector already edits well.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from core.parameter_types import ParameterKind
from ui_qt import parameter_row
from ui_qt.parameter_row import value_preview, value_tooltip

_CELL = ("Parameterisation", "Cell")


# --- the pure helper ----------------------------------------------------


def test_null_is_a_ghosted_dash():
    assert value_preview(None, ParameterKind.SCALAR) == ("—", True)


def test_numbers_render_json_verbatim():
    text, ghost = value_preview(5.86e-06, ParameterKind.SCALAR)
    assert text == json.dumps(5.86e-06)
    assert not ghost


def test_twenty_decimal_mantissa_is_returned_in_full():
    """Elision is the delegate's visual concern; the preview string keeps
    every digit so the tooltip can carry the full committed value."""
    value = 0.12345678901234567890
    text, _ = value_preview(value, ParameterKind.SCALAR)
    assert text == json.dumps(value)


def test_booleans_render_json_spelling():
    assert value_preview(True, ParameterKind.BOOLEAN) == ("true", False)


def test_strings_render_verbatim_first_line():
    assert value_preview("SPM", ParameterKind.ENUM) == ("SPM", False)
    text, _ = value_preview("line one\nline two", ParameterKind.TEXT)
    assert text == "line one…"


def test_interpolated_table_summarises_point_count():
    value = {"x": [0, 0.1, 1], "y": [1.72, 1.2, 0.06]}
    assert value_preview(value, ParameterKind.TABLE) == ("table · 3 points", True)


def test_map_summarises_entry_count():
    value = {"Primary": 0.7, "Secondary": 0.3}
    assert value_preview(value, ParameterKind.MAP) == ("2 entries", True)


def test_series_summarises_value_count():
    assert value_preview([0, 100, 200], ParameterKind.SERIES) == ("series · 3 values", True)


def test_tooltip_caps_long_values_with_ellipsis():
    text = value_tooltip(list(range(1000)))
    assert len(text) == parameter_row._TOOLTIP_MAX
    assert text.endswith("…")


# --- rows in the live list ----------------------------------------------


def test_parameter_rows_carry_value_roles_and_tooltip(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    d._w.navigate_to(_CELL)
    lst = d._w._params._list
    row_values = {}
    for i in range(lst.count()):
        item = lst.item(i)
        if item.data(256):  # real parameter rows only, not group/suggestions
            row_values[item.text()] = (
                item.data(parameter_row.VALUE_ROLE),
                item.toolTip(),
            )
    preview, tooltip = row_values["Nominal cell capacity [A.h]"]
    assert preview == "5"
    assert tooltip == "5"


def test_null_valued_row_shows_ghost_dash_and_no_tooltip(app_driver, valid_spm_path, tmp_path):
    import json as _json

    doc = _json.loads(valid_spm_path.read_text("utf-8"))
    doc["Parameterisation"]["Cell"]["Electrode area [m2]"] = None
    work = tmp_path / "null_area.json"
    work.write_text(_json.dumps(doc), encoding="utf-8")

    d = app_driver
    d.open(work)
    d._w.navigate_to(_CELL)
    lst = d._w._params._list
    for i in range(lst.count()):
        item = lst.item(i)
        if item.text().startswith("Electrode area"):
            assert item.data(parameter_row.VALUE_ROLE) == "—"
            assert item.data(parameter_row.VALUE_GHOST_ROLE) is True
            assert item.toolTip() == ""
            return
    raise AssertionError("Electrode area row not found")


def test_long_value_row_paints_without_growing_taller(app_driver, valid_spm_path, tmp_path):
    """A 20-decimal value must elide into the value column, not wrap the row:
    with the name short and the value capped at its width share, the row's
    height matches its siblings'."""
    import json as _json

    doc = _json.loads(valid_spm_path.read_text("utf-8"))
    doc["Parameterisation"]["Cell"]["Volume [m3]"] = 0.12345678901234567890123
    work = tmp_path / "long_decimal.json"
    work.write_text(_json.dumps(doc), encoding="utf-8")

    d = app_driver
    d.open(work)
    d._w.navigate_to(_CELL)
    lst = d._w._params._list
    heights = {}
    for i in range(lst.count()):
        item = lst.item(i)
        if item.data(256):
            heights[item.text()] = lst.sizeHintForRow(i)
    assert heights["Volume [m3]"] == heights["Reference temperature [K]"]
