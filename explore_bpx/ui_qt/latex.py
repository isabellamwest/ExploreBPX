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

from . import typography
from .style import DEFAULT_TEXT


def latex_pixmap(latex: str, size: int = typography.BODY, color: str = DEFAULT_TEXT) -> QPixmap | None:
    """Render *latex* (without surrounding ``$``) to a transparent pixmap.

    *size* is a type rung in pixels, like every other size in the app --
    :func:`typography.points` converts to the points matplotlib wants, so a
    symbol matches the text it sits beside instead of rendering a third
    larger.

    Returns ``None`` when matplotlib is unavailable or the expression does not
    parse - callers fall back to showing the raw LaTeX source as plain text.
    """
    png = _render_png(latex, typography.points(size), color)
    if png is None:
        return None
    pixmap = QPixmap()
    if not pixmap.loadFromData(png, "PNG"):
        return None
    # Rendered at 2x DPI for crispness; scale back down in device pixels.
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


def symbol_label(latex: str, size: int = typography.BODY, color: str = DEFAULT_TEXT) -> QLabel:
    """A ``QLabel`` showing *latex* as rendered maths, or its source text if the
    renderer is unavailable -- the symbol is never silently dropped.

    Shared by every surface that shows a parameter's symbol (the ( i ) popover,
    the Documentation section, the card header) so they render it identically.
    The symbol is verbatim from the descriptions dataset; this function
    invents nothing, and returns an empty-but-valid label only when handed
    empty text.
    """
    label = QLabel()
    pixmap = latex_pixmap(latex, size=size, color=color) if latex else None
    if pixmap is not None:
        label.setPixmap(pixmap)
    else:
        label.setTextFormat(Qt.PlainText)
        label.setText(latex)
    label.setToolTip(latex)
    return label


@lru_cache(maxsize=256)
def _render_png(latex: str, point_size: float, color: str) -> bytes | None:
    """Rasterise to PNG bytes (cached - symbols repeat across popover opens).

    The ``finally`` clause is load-bearing: matplotlib's mathtext parses
    ``$...$`` through pyparsing with packrat caching enabled, and that cache
    stores ``ParseException`` instances whose ``__traceback__`` captures this
    call stack -- including the Inspector widgets in the callers' frames.
    Those exception/traceback/frame graphs are reference *cycles*, so they
    (and every widget their frames pin) can only ever die in a cyclic-GC
    pass -- which Python may run mid-``processEvents``, tearing down live
    Qt objects in the middle of event dispatch (an offscreen
    access-violation crash in practice). Clearing the cache unroots the
    cycles and the immediate ``gc.collect()`` reclaims them *here*, a safe
    point where every widget in the calling stack is still strongly
    referenced. This function's own ``lru_cache`` keeps repeat symbol
    renders cheap, so neither cost recurs per paint.
    """
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
            buffer,
            format="png",
            dpi=192,
            transparent=True,
            bbox_inches="tight",
            pad_inches=0.02,
        )
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 - any mathtext failure falls back to plain text
        return None
    finally:
        try:
            import gc

            import pyparsing

            pyparsing.ParserElement.reset_cache()
            gc.collect()
        except Exception:  # noqa: BLE001, S110 - best-effort cache guard, never fatal
            pass
