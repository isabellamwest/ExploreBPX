"""LaTeX-to-pixmap rendering for parameter symbols.

Uses matplotlib's built-in *mathtext* engine (no TeX installation required) to
rasterise a LaTeX expression into a transparent-background ``QPixmap`` that
drops into any ``QLabel``. matplotlib is imported lazily on first use: it is a
heavyweight import, and most sessions never open an info surface.

Rendering is defensive by design: a symbol comes from the replaceable
descriptions dataset, so a malformed expression in a future revision of that
file must degrade to *no pixmap* (the caller shows the raw LaTeX as text),
never to a crash.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


def latex_pixmap(latex: str, point_size: float = 11.0, color: str = "#202020") -> QPixmap | None:
    """Render *latex* (without surrounding ``$``) to a transparent pixmap.

    Returns ``None`` when matplotlib is unavailable or the expression does not
    parse — callers fall back to showing the raw LaTeX source as plain text.
    """
    png = _render_png(latex, point_size, color)
    if png is None:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(png, "PNG"):
        return None
    # Rendered at 2x DPI for crispness; scale back down in device pixels.
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


def symbol_label(latex: str, point_size: float = 11.0, color: str = "#202020") -> QLabel:
    """A ``QLabel`` showing *latex* as rendered maths, or its source text if the
    renderer is unavailable -- the symbol is never silently dropped.

    Shared by every surface that shows a parameter's symbol (the ( i ) popover,
    the Documentation tab, the card header) so they render it identically. The
    symbol is verbatim from the descriptions dataset; this function invents
    nothing, and returns an empty-but-valid label only when handed empty text.
    """
    label = QLabel()
    pixmap = latex_pixmap(latex, point_size=point_size, color=color) if latex else None
    if pixmap is not None:
        label.setPixmap(pixmap)
    else:
        label.setTextFormat(Qt.PlainText)
        label.setText(latex)
    label.setToolTip(latex)
    return label


@lru_cache(maxsize=256)
def _render_png(latex: str, point_size: float, color: str) -> bytes | None:
    """Rasterise to PNG bytes (cached — symbols repeat across popover opens)."""
    try:
        # The OO API (Figure + explicit Agg canvas) rasterises through Agg
        # regardless of the global backend, so this never sets or fights the
        # backend a future Qt-embedded Analysis view may choose.
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=(0.01, 0.01))
        figure.patch.set_alpha(0.0)
        FigureCanvasAgg(figure)
        figure.text(0, 0, f"${latex}$", fontsize=point_size, color=color)
        buffer = BytesIO()
        # bbox_inches="tight" crops the canvas to the rendered expression.
        figure.savefig(
            buffer, format="png", dpi=192, transparent=True,
            bbox_inches="tight", pad_inches=0.02,
        )
        return buffer.getvalue()
    except Exception:
        return None
