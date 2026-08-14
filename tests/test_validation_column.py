"""Validation parameter-column coherence.

The middle column over a Validation run now shows the same schema-first
order as the run's grid, lists missing schema arrays as muted placeholder
rows (ghost rows win when a pinned reference supplies the array), summarises
series tooltips instead of dumping JSON, and turns the bare ``("Validation",)``
container into navigable run rows whose "+ Add" creates an experiment.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from ui_qt import main_window as main_window_module

_RUN = ("Validation", "C/20 discharge")


def _write_doc(tmp_path, valid_spm_dict, validation, name="doc.json"):
    doc = dict(valid_spm_dict)
    doc["Validation"] = validation
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _write_reference(tmp_path, valid_spm_dict, validation, name="reference.json"):
    """A pinnable reference file whose Validation mirrors *validation*.

    ``BPX: 1.0.0`` deliberately -- a 0.x header is detectably legacy and the
    real open-intent prompt would hang the offscreen suite.
    """
    doc = dict(valid_spm_dict)
    doc["Validation"] = validation
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _pin(app_driver, monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(path), ""),
    )
    app_driver.click_workspace_open_reference()


# ---------------------------------------------------------------------------
# Schema-first row order, Move up/down gating
# ---------------------------------------------------------------------------


def test_run_rows_render_schema_arrays_first_then_customs_in_file_order(app_driver, tmp_path, valid_spm_dict):
    """The file interleaves customs and schema arrays; the column shows the
    grid's own schema order, then customs in file order."""
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Notes": "first custom",
                "Voltage [V]": [4.1, 4.0],
                "Time [s]": [0, 100],
                "Impedance [Ohm]": [0.01, 0.02],
                "Current [A]": [-0.6, -0.6],
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    rows = d.parameter_list_rows()
    assert [text for kind, text in rows if kind == ""] == [
        "Time [s]",
        "Current [A]",
        "Voltage [V]",
        "Notes",
        "Impedance [Ohm]",
    ]
    # Temperature is absent from the file: it renders as the one placeholder,
    # in its schema position (after Voltage, before the customs).
    assert rows[3] == ("placeholder", "Temperature [K]")


def test_schema_arrays_offer_no_move_actions_customs_keep_them(app_driver, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Alpha": "one",
                "Beta": "two",
            }
        },
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    time_actions = [text for text, _enabled in d.row_menu_actions("Time [s]")]
    assert "Move up" not in time_actions
    assert "Move down" not in time_actions

    alpha_actions = dict(d.row_menu_actions("Alpha"))
    beta_actions = dict(d.row_menu_actions("Beta"))
    # Positioned among the custom keys the list displays: Alpha is first
    # (up disabled), Beta last (down disabled).
    assert alpha_actions["Move up"] is False
    assert alpha_actions["Move down"] is True
    assert beta_actions["Move up"] is True
    assert beta_actions["Move down"] is False


def test_rows_outside_validation_keep_move_actions(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path).go_to(("Parameterisation", "Cell"))

    rows = [text for kind, text in d.parameter_list_rows() if kind == ""]
    actions = [text for text, _enabled in d.row_menu_actions(rows[0])]
    assert "Move up" in actions
    assert "Move down" in actions


# ---------------------------------------------------------------------------
# Placeholder rows
# ---------------------------------------------------------------------------


def test_placeholder_rows_anatomy_and_click_focuses_the_column(app_driver, tmp_path, valid_spm_dict):
    from ui_qt import parameter_row

    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {"C/20 discharge": {"Time [s]": [0, 100]}},
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    rows = d.parameter_list_rows()
    assert ("placeholder", "Current [A]") in rows
    assert ("placeholder", "Voltage [V]") in rows
    assert ("placeholder", "Temperature [K]") in rows

    # Anatomy: muted meta, no reference bar.
    panel = d._w._params
    lst = panel._list
    item = next(
        lst.item(i)
        for i in range(lst.count())
        if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "placeholder" and lst.item(i).text() == "Voltage [V]"
    )
    assert item.data(parameter_row.VALUE_ROLE) == "not in file"
    assert item.data(parameter_row.REF_BAR_ROLE) is None

    d.click_placeholder_row("Voltage [V]")
    assert d.experiment_focused_column() == "Voltage [V]"


def test_placeholder_click_writes_nothing(app_driver, main_window, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {"C/20 discharge": {"Time [s]": [0, 100]}},
    )
    d = app_driver
    d.open(workfile).go_to(_RUN)

    d.click_placeholder_row("Voltage [V]")

    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert "Voltage [V]" not in run
    assert d.undo_enabled() is False


def test_a_ghost_row_wins_over_a_placeholder_for_the_same_key(app_driver, monkeypatch, tmp_path, valid_spm_dict):
    """When a pinned reference supplies the missing array, the purple ghost
    row shows and the placeholder is suppressed -- one row per key, never
    both."""
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    reference = _write_reference(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Temperature [K]": [298.0, 298.5],
            }
        },
    )
    d = app_driver
    d.open(workfile)
    _pin(d, monkeypatch, reference)
    d.go_to(_RUN)

    rows = d.parameter_list_rows()
    kinds = {text: kind for kind, text in rows}
    assert kinds["Temperature [K]"] == "ghost"
    assert ("placeholder", "Temperature [K]") not in rows
    # And it holds its schema position: directly after Voltage [V].
    texts = [text for _kind, text in rows]
    assert texts.index("Temperature [K]") == texts.index("Voltage [V]") + 1


def test_ghost_temperature_use_pulls_the_whole_array_in_one_undo_step(
    app_driver, main_window, monkeypatch, tmp_path, valid_spm_dict
):
    """PC-e: the ghost card's "Use" copies the reference array verbatim as
    one undo step."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    reference = _write_reference(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Temperature [K]": [298.0, 298.5],
            }
        },
    )
    d = app_driver
    d.open(workfile)
    _pin(d, monkeypatch, reference)
    d.go_to(_RUN)
    d.select_ghost_row("Temperature [K]")

    card = main_window._inspector._card
    use = card.findChild(QPushButton, "PullButton")
    assert use is not None, "Ghost card offers no Use button."
    d._qtbot.mouseClick(use, Qt.LeftButton)

    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert run["Temperature [K]"] == [298.0, 298.5]

    d.undo()
    run = main_window._state.active.document.raw["Validation"]["C/20 discharge"]
    assert "Temperature [K]" not in run
    assert d.undo_enabled() is False


# ---------------------------------------------------------------------------
# Series tooltips summarise
# ---------------------------------------------------------------------------


def test_series_row_tooltip_is_a_summary_not_a_dump(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_RUN)

    assert d.parameter_row_tooltip("Time [s]") == "series · 3 values"


def test_differs_tooltip_reference_lines_are_summaries(app_driver, monkeypatch, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    reference = _write_reference(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100, 200],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            }
        },
    )
    d = app_driver
    d.open(workfile)
    _pin(d, monkeypatch, reference)
    d.go_to(_RUN)

    tooltip = d.parameter_row_tooltip("Time [s]")
    lines = tooltip.split("\n")
    assert lines[0] == "series · 2 values"
    assert lines[1].endswith(": series · 3 values")
    assert "[0, 100" not in tooltip  # no JSON dumps anywhere in it


# ---------------------------------------------------------------------------
# The ("Validation",) container
# ---------------------------------------------------------------------------


def test_container_lists_navigable_run_rows_and_count_matches(app_driver, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
            },
            "1C discharge": {"Time [s]": [0, 10]},
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation",))

    rows = d.parameter_list_rows()
    assert rows == [("run", "C/20 discharge"), ("run", "1C discharge")]
    assert d.parameter_list_count_text() == "2"

    d.click_container_run_row("1C discharge")
    assert d.experiment_title() == "Experiment · 1C discharge"


def test_container_run_row_meta_counts_its_arrays(app_driver, tmp_path, valid_spm_dict):
    from ui_qt import parameter_row

    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {
            "C/20 discharge": {
                "Time [s]": [0, 100],
                "Current [A]": [-0.6, -0.6],
                "Voltage [V]": [4.1, 4.0],
                "Notes": "a string, not an array",
            },
            "1C discharge": {"Time [s]": [0, 10]},
        },
    )
    d = app_driver
    d.open(workfile).go_to(("Validation",))

    panel = d._w._params
    lst = panel._list
    values = [lst.item(i).data(parameter_row.VALUE_ROLE) for i in range(lst.count())]
    assert values == ["3 arrays", "1 array"]


def test_container_add_opens_the_experiment_popup_and_creates_a_run(app_driver, main_window, tmp_path, valid_spm_dict):
    workfile = _write_doc(
        tmp_path,
        valid_spm_dict,
        {"C/20 discharge": {"Time [s]": [0, 100]}},
    )
    d = app_driver
    d.open(workfile).go_to(("Validation",))

    d.add_experiment_via_container_popup("2C discharge")

    raw = main_window._state.active.document.raw
    assert "2C discharge" in raw["Validation"]
    assert raw["Validation"]["2C discharge"] == {}


def test_empty_container_lists_no_rows_and_keeps_the_guided_empty_state(app_driver, tmp_path, valid_spm_dict):
    """A zero-run container has no run rows, count 0, and the inspector's
    guided empty state is unchanged."""
    workfile = _write_doc(tmp_path, valid_spm_dict, {})
    d = app_driver
    d.open(workfile).go_to(("Validation",))

    assert d.parameter_list_rows() == []
    assert d.parameter_list_count_text() == "0"
