"""The technical-descriptions dataset, its loader, and the Documentation
section.

The dataset (``app/data/parameter_descriptions.yaml``) is replaceable data:
these tests pin the loader's contract (section-scoped lookup, graceful
absence) and the dataset's own integrity (all entries well-formed and
reachable from real documents), so a future revision of the file fails loudly
here rather than silently dropping documentation.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import parameter_descriptions as descriptions

# ---------------------------------------------------------------------------
# Loader contract
# ---------------------------------------------------------------------------


def test_dataset_loads_with_source_and_entries():
    dataset = descriptions._load()
    assert dataset.source
    assert "BPX" in dataset.source
    assert len(dataset.entries) >= 30


def test_every_entry_is_well_formed():
    for entry in descriptions._load().entries:
        assert entry.alias, "entry missing alias"
        assert entry.sections, f"{entry.alias}: no sections"
        assert entry.symbol, f"{entry.alias}: no symbol"
        assert entry.content, f"{entry.alias}: no content"
        for heading, prose in entry.content:
            assert heading, f"{entry.alias}: section with no heading"
            assert prose, f"{entry.alias}: empty {heading!r} section"


def test_every_entry_matches_a_real_parameter(fixtures_dir):
    """No orphans: each entry resolves from at least one fixture document, so
    a typo in an alias or section name cannot silently strand an entry."""
    import json

    from core.document import BPXDocument

    matched: set[tuple[str, tuple[str, ...]]] = set()
    for name in (
        "spm_example_valid.json",
        "nmc_pouch_cell_BPX.json",
        "lfp_18650_cell_BPX.json",
    ):
        raw = json.loads((fixtures_dir / name).read_text("utf-8"))
        document = BPXDocument.from_raw(raw, filename=name, fmt="json")
        for path in document._parameter_path_map:
            entry = descriptions.lookup(path)
            if entry is not None:
                matched.add((entry.alias, entry.sections))

    orphans = [(e.alias, e.sections) for e in descriptions._load().entries if (e.alias, e.sections) not in matched]
    assert orphans == []


def test_lookup_is_section_scoped():
    separator = descriptions.lookup(("Parameterisation", "Separator", "Thickness [m]"))
    electrode = descriptions.lookup(("Parameterisation", "Negative electrode", "Thickness [m]"))
    assert separator is not None
    assert electrode is not None
    assert separator is not electrode
    assert separator.sections == ("Separator",)


def test_lookup_matches_blended_particle_nesting():
    entry = descriptions.lookup(("Parameterisation", "Positive electrode", "Particle", "Secondary", "OCP [V]"))
    assert entry is not None
    assert entry.symbol == r"U_{k,m,\mathrm{ref}}"


def test_lookup_rejects_user_defined_alias_reuse():
    assert descriptions.lookup(("User-defined", "Particle radius [m]")) is None


def test_lookup_rejects_unknown_and_empty_paths():
    assert descriptions.lookup(()) is None
    assert descriptions.lookup(("Parameterisation", "Cell", "No such thing")) is None


def test_missing_dataset_file_is_not_an_error(monkeypatch, tmp_path):
    """The app must run without the dataset -- documentation, not schema."""
    monkeypatch.setattr(descriptions, "_DATASET_PATH", tmp_path / "absent.yaml")
    descriptions._load.cache_clear()
    try:
        assert descriptions.lookup(("Parameterisation", "Cell", "Volume [m3]")) is None
        assert descriptions.dataset_source() is None
    finally:
        descriptions._load.cache_clear()


def test_malformed_dataset_file_raises(monkeypatch, tmp_path):
    """A broken file must fail loudly, not silently drop every description --
    that would read as 'this build lost the docs' with no cause shown."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("entries:\n  - alias: [unclosed", encoding="utf-8")
    monkeypatch.setattr(descriptions, "_DATASET_PATH", broken)
    descriptions._load.cache_clear()
    try:
        # Deliberately broad: *any* loud failure satisfies the contract; the
        # exception type is yaml's business, not this test's.
        with pytest.raises(Exception):  # noqa: B017, PT011
            descriptions.lookup(("Parameterisation", "Cell", "Volume [m3]"))
    finally:
        descriptions._load.cache_clear()


def test_same_alias_entries_keep_disjoint_section_sets():
    """First-match-wins is only safe while duplicate-alias entries can never
    both match one path. Overlapping section sets for the same alias would
    make the dataset's entry order silently decide which prose renders."""
    by_alias: dict[str, list[set[str]]] = {}
    for entry in descriptions._load().entries:
        by_alias.setdefault(entry.alias, []).append(set(entry.sections))
    for alias, section_sets in by_alias.items():
        for i, a in enumerate(section_sets):
            for b in section_sets[i + 1 :]:
                assert not (a & b), f"{alias!r}: overlapping sections {a & b}"


# ---------------------------------------------------------------------------
# LaTeX rendering
# ---------------------------------------------------------------------------


def test_every_dataset_symbol_renders_as_maths():
    """Every symbol in the dataset must parse under mathtext -- a malformed
    symbol in a future revision fails here, not in front of the user."""
    pytest.importorskip("matplotlib")
    from matplotlib import mathtext
    from matplotlib.font_manager import FontProperties

    parser = mathtext.MathTextParser("agg")
    for entry in descriptions._load().entries:
        parser.parse(f"${entry.symbol}$", dpi=96, prop=FontProperties(size=11))


def test_latex_pixmap_renders_and_caches(qtbot):
    pytest.importorskip("PySide6")
    from ui_qt.latex import latex_pixmap

    pixmap = latex_pixmap(r"\theta^\mathrm{min}_{k,m}")
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_latex_pixmap_returns_none_for_unparseable_input(qtbot):
    pytest.importorskip("PySide6")
    from ui_qt.latex import latex_pixmap

    assert latex_pixmap(r"\thisisnotlatex{") is None


# ---------------------------------------------------------------------------
# Documentation view (the Documentation section's body)
# ---------------------------------------------------------------------------


@pytest.fixture
def docs_view(qtbot):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from ui_qt.documentation_view import DocumentationView

    view = DocumentationView()
    qtbot.addWidget(view)
    return view


def _view_texts(view) -> list[str]:
    layout = view._layout
    return [layout.itemAt(i).widget().text() for i in range(layout.count()) if layout.itemAt(i).widget() is not None]


def test_docs_view_starts_empty(docs_view):
    # No "select a parameter" placeholder of its own: with nothing shown the
    # Inspector hides the whole Documentation section instead.
    assert docs_view._layout.count() == 0


def test_docs_view_renders_sections_in_dataset_order(docs_view):
    from core.parameter_metadata import ParameterMetadata

    docs_view.show_metadata(
        ParameterMetadata(
            symbol="A",
            documentation=(
                ("Physical correspondence", "First."),
                ("A brand-new heading", "Second."),
            ),
            source="Test source, v1",
        )
    )
    texts = _view_texts(docs_view)
    assert texts.index("Physical correspondence") < texts.index("A brand-new heading")
    assert "First." in texts
    assert "Second." in texts
    assert any("Test source, v1" in t for t in texts)


def test_docs_view_placeholder_when_parameter_has_no_documentation(docs_view):
    from core.parameter_metadata import ParameterMetadata

    docs_view.show_metadata(ParameterMetadata(physical_meaning="short only"))
    texts = _view_texts(docs_view)
    assert texts == ["No technical description is available for this parameter."]


def test_docs_view_clears_back_to_no_selection(docs_view):
    from core.parameter_metadata import ParameterMetadata

    docs_view.show_metadata(ParameterMetadata(documentation=(("Description", "x"),)))
    docs_view.show_metadata(None)
    assert docs_view._layout.count() == 0
