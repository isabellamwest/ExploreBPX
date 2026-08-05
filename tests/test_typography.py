"""The type scale has exactly one definition, and stays that way.

The app once carried eight absolute font sizes, four relative schemes and
four spellings of "bold" across a global stylesheet, seventeen inline
stylesheets and a scatter of ``QFont`` mutations. Consolidating that was the
easy half; this file is the half that keeps it consolidated, in the spirit of
``test_boundaries.py``. If one of these fails, the fix is almost always to
reach for a rung in ``ui_qt.typography`` rather than to relax the test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ui_qt import typography

UI_QT = Path(__file__).resolve().parents[1] / "app" / "ui_qt"
#: The one module allowed to spell a font literal.
HOME = "typography.py"


def _sources() -> list[Path]:
    return sorted(p for p in UI_QT.rglob("*.py") if p.name != HOME)


def _offences(pattern: str) -> list[str]:
    """Every ``file:line: text`` in ui_qt (bar the home module) matching
    *pattern*, skipping comment and docstring-ish lines -- prose is allowed
    to name what code may not spell."""
    found = []
    for path in _sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("#", "#:", '"""', "*", "``")):
                continue
            if re.search(pattern, line):
                found.append(f"{path.relative_to(UI_QT)}:{number}: {stripped}")
    return found


def test_no_font_size_literals_outside_typography():
    """No ``font-size`` with a hardcoded number -- in QSS, an inline
    stylesheet, or a rich-text span. ``${token}`` placeholders and
    ``typography.size_qss(...)`` calls are how a size is spelled."""
    assert _offences(r"font-size:\s*[\d.]+\s*(px|pt|%)") == []


def test_no_font_weight_literals_outside_typography():
    assert _offences(r"font-weight:\s*\d") == []


def test_no_qfont_size_or_weight_mutation_outside_typography():
    """``setPixelSize``/``setPointSize``/``setBold``/``setWeight`` all bypass
    the scale. ``typography.sized`` and ``typography.semibold`` are the
    supported ways to step a painted or delegate font."""
    assert _offences(r"\.(setPixelSize|setPointSizeF?|setBold|setWeight)\(") == []


def test_no_font_family_chosen_outside_typography():
    """Including ``QFontDatabase.systemFont``, which resolves to Courier New
    on Windows -- nine call sites used to ask for it independently."""
    assert _offences(r"QFontDatabase\.systemFont|setFamil(y|ies)\(|font-family:") == []


def test_stylesheet_only_ever_states_a_rung():
    """Every size the global stylesheet substitutes is on the scale, so the
    sheet cannot quietly grow a fifth rung."""
    sizes = {
        int(value)
        for key, value in typography.qss_tokens().items()
        if key not in ("regular", "semibold")
    }
    assert sizes == set(typography.SCALE)


def test_stylesheet_substitutes_every_placeholder():
    """A ``${name}`` with no token would render literally into the QSS and be
    silently ignored by Qt, leaving that widget at whatever it inherited."""
    from string import Template

    from ui_qt import style

    assert "${" not in style.STYLESHEET
    template = Template(style._STYLESHEET_TEMPLATE)
    assert set(template.get_identifiers()) <= set(typography.qss_tokens())


@pytest.mark.parametrize("rung", typography.SCALE)
def test_every_rung_is_a_distinct_whole_pixel_size(rung):
    assert isinstance(rung, int) and rung > 0
    assert typography.SCALE.count(rung) == 1


def test_points_conversion_matches_qt_reference_dpi():
    """Rendered maths is sized from a rung, not from its own point scale --
    13px of text and a 13px symbol must be the same size."""
    assert typography.points(16) == pytest.approx(12.0)
    assert typography.points(typography.TITLE) == pytest.approx(11.25)
