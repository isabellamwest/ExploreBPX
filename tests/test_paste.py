"""Paste parser: raw clipboard text -> grid rows, no coercion, header skipped."""

from __future__ import annotations

from core.paste import detect_delimiter, parse_clipboard


def test_detects_tab_comma_semicolon_whitespace_and_single():
    assert detect_delimiter("1\t2\n3\t4") == "tab"
    assert detect_delimiter("1,2\n3,4") == "comma"
    assert detect_delimiter("1;2\n3;4") == "semicolon"
    assert detect_delimiter("1  2\n3  4") == "whitespace"
    assert detect_delimiter("1\n2\n3") == "single column"
    assert detect_delimiter("") == "single column"


def test_single_column_series_paste():
    result = parse_clipboard("0.0\n3.7\n4\n", columns=1)
    assert result.rows == [[0.0], [3.7], [4]]
    assert result.rejected == 0
    assert result.header is None


def test_two_column_table_paste_with_header_skipped():
    text = "x,y\n0.0,3.70\n0.1,3.71\n0.2,3.72\n"
    result = parse_clipboard(text, columns=2)
    assert result.header == "x,y"
    assert result.rows == [[0.0, 3.70], [0.1, 3.71], [0.2, 3.72]]
    assert result.delimiter == "comma"
    assert result.rejected == 0


def test_non_numeric_cells_are_kept_as_text_and_counted_not_zeroed():
    text = "0.0\toops\n0.1\t3.7\n"
    result = parse_clipboard(text, columns=2)
    assert result.rows == [[0.0, "oops"], [0.1, 3.7]]
    assert result.rejected == 1  # "oops" reported, never turned into 0


def test_blank_cells_stay_none_never_coerced():
    result = parse_clipboard("0.0\t\n\t3.7\n", columns=2)
    assert result.rows == [[0.0, None], [None, 3.7]]
    assert result.rejected == 0  # a blank cell is not a rejected value


def test_extra_columns_beyond_target_are_dropped_and_reported():
    result = parse_clipboard("0.0,1.0,9.9\n0.1,2.0,8.8\n", columns=2)
    assert result.rows == [[0.0, 1.0], [0.1, 2.0]]
    assert result.dropped_columns == 2


def test_a_single_data_line_is_not_mistaken_for_a_header():
    result = parse_clipboard("42\n", columns=1)
    assert result.header is None
    assert result.rows == [[42]]


def test_whitespace_aligned_table():
    result = parse_clipboard("time  volt\n0.0   3.7\n0.1   3.8\n", columns=2)
    assert result.header == "time  volt"
    assert result.rows == [[0.0, 3.7], [0.1, 3.8]]
    assert result.delimiter == "whitespace"


def test_empty_paste_yields_no_rows():
    result = parse_clipboard("   \n\n", columns=2)
    assert result.rows == []
    assert result.row_count == 0
