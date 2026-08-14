"""Optical normalisation of the activity-bar icon set.

The three rail icons (Workspace, Editor, Diagnostics) are meant to read as
one family: each glyph's drawn ink should sit inside, and be centred on, a
common optical box. These tests measure the actual rendered alpha bounding
box of each icon's ink -- not the SVG source coordinates -- so a future
edit that quietly drifts the geometry is caught rather than only being
visible on inspection.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt import icons

_ICON_SIZE = 24


def _ink_bbox(svg: str, size: int = _ICON_SIZE) -> tuple[int, int, int, int]:
    """The alpha bounding box (x_min, x_max, y_min, y_max) of *svg*'s ink."""
    QApplication.instance() or QApplication([])
    image = icons._render_pixmap(svg, "#000000", size).toImage()

    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 10:
                xs.append(x)
                ys.append(y)

    assert xs, "icon rendered no visible ink"
    assert ys, "icon rendered no visible ink"
    return min(xs), max(xs), min(ys), max(ys)


@pytest.mark.parametrize(
    ("name", "svg"), [("WORKSPACE", icons.WORKSPACE), ("EDITOR", icons.EDITOR), ("DIAGNOSTICS", icons.DIAGNOSTICS)]
)
def test_icon_ink_is_optically_centred_and_sized(name, svg):
    x_min, x_max, y_min, y_max = _ink_bbox(svg)
    width = x_max - x_min
    height = y_max - y_min
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    centre = _ICON_SIZE / 2

    assert abs(cx - centre) <= 1.0, f"{name}: horizontal centre {cx} not within 1px of {centre}"
    assert abs(cy - centre) <= 1.0, f"{name}: vertical centre {cy} not within 1px of {centre}"
    assert 13 <= height <= 18, f"{name}: ink height {height} outside [13, 18]"
    assert width <= 18, f"{name}: ink width {width} exceeds 18"
