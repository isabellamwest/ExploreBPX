"""The app's one type scale.

Every font size, weight and family in the Qt frontend comes from here. Before
this module the app carried eight absolute sizes, four relative schemes and
four different spellings of "bold", spread across a global stylesheet,
seventeen inline stylesheets and a scatter of ``QFont`` mutations -- so 12px
and 13px text sat side by side doing the same job, and ``setBold(True)``
(weight 700) sat beside the stylesheet's ``font-weight: 600``.

The scale is four rungs, deliberately far enough apart to be told apart:

===========  ======  ==============================================
Rung         Size    Carries
===========  ======  ==============================================
``TITLE``    15      Card titles
``BODY``     13      The global base: inputs, buttons, rows, cells
``META``     11      Caps section headings, and quiet secondary text
``MICRO``    10      Count badges and tags
===========  ======  ==============================================

``META`` serves both the caps eyebrow tier and plain secondary text; caps plus
:data:`CAPS_LETTER_SPACING` already separates the two, so they do not also need
separate sizes. Sizes are device-independent pixels -- Qt scales them with the
display, so they must never be mixed with *points* (see :func:`points`).

Weight is one decision, not two: text is either regular or
:data:`SEMIBOLD`. Qt's ``QFont.setBold`` is weight 700 and must not be used --
:func:`semibold` is the only emphasis in the app.

``tests/test_typography.py`` enforces all of this: no font literal may appear
in ``app/ui_qt/`` outside this module.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QWidget

# ---------------------------------------------------------------------------
# Families
# ---------------------------------------------------------------------------

#: True on macOS. The families below are the one part of this module that
#: cannot be a single cross-platform list: Qt picks the first *installed*
#: family, so a shared list would work -- but naming a family the machine does
#: not have makes Qt populate its alias table to prove the absence, which it
#: reports as ``Populating font family aliases took 54 ms``. Asking each
#: platform only for faces it actually ships skips that entirely.
_MACOS = sys.platform == "darwin"

#: The UI face, most-preferred first.
#:
#: On Windows, ``Segoe UI Variable Text`` is Windows 11's own refreshed Segoe,
#: optically sized for text rather than display, so it is the better face at
#: the small sizes this app lives at; ``Segoe UI`` is the Windows 10 fallback
#: (and what VS Code itself asks for).
#:
#: On macOS the counterpart is the system UI face itself. ``.AppleSystemUIFont``
#: is the name Qt resolves ``GeneralFont`` to, and naming it explicitly gives
#: byte-identical metrics to letting the stack fall through (cap height 9.16 at
#: 13px either way) while keeping the family pinned rather than accidental.
#:
#: Pinning the family matters even though nothing set one before: the app was
#: consistent only by luck, since anything constructing a bare ``QFont()``
#: picked up the *application* default rather than the widget's.
UI_FAMILIES: tuple[str, ...] = (
    (".AppleSystemUIFont", "Helvetica Neue")
    if _MACOS
    else ("Segoe UI Variable Text", "Segoe UI", "system-ui")
)

#: The monospace face, most-preferred first, chosen to *optically match*
#: :data:`UI_FAMILIES` rather than merely to be fixed-width.
#:
#: ``QFontDatabase.systemFont(FixedFont)`` -- what nine call sites used to ask
#: for -- resolves to Courier New on Windows, whose cap height at 13px is 7.4
#: against Segoe UI's 9.1, so mono text read as visibly weedier and older than
#: everything beside it. Cascadia Mono measures 9.0 at the same size.
#:
#: The same trap had swallowed macOS, where it was the *whole* list that missed:
#: no Cascadia Mono, no Consolas, so every Source view fell through to Courier
#: New at cap height 7.4 against the system face's 9.2 -- a 19% shortfall, and
#: the reason mono text read as a different, older typeface than the rest of the
#: app. Menlo measures 9.47 there: within 3%, the same near-exact match Cascadia
#: gives on Windows. So monospace still simply sits on :data:`BODY` with no
#: optical fudge (the old code carried a ``-1px`` correction and a floor).
#: Menlo rather than SF Mono deliberately: SF Mono ships with macOS but is not
#: registered under that name in Qt's font database, so naming it buys nothing
#: and costs the alias-table scan described above. Menlo is on every macOS.
MONO_FAMILIES: tuple[str, ...] = (
    ("Menlo", "Courier New")
    if _MACOS
    else ("Cascadia Mono", "Consolas", "Courier New")
)

# ---------------------------------------------------------------------------
# The scale
# ---------------------------------------------------------------------------

#: Card titles -- the only text in the app larger than the base.
TITLE = 15
#: The global base size, set on ``QWidget`` and inherited by everything that
#: does not deliberately step off it: inputs, buttons, list rows, tree rows,
#: table cells, diagnostics rows.
BODY = 13
#: Quiet text: caps section headings, counts, hints, citations, provenance,
#: error notes, empty states.
META = 11
#: Badges and tags only -- text that is a marker rather than a sentence.
MICRO = 10

#: Every rung, for the guard test and for callers that need to validate a size.
SCALE: tuple[int, ...] = (TITLE, BODY, META, MICRO)

# ---------------------------------------------------------------------------
# Weight
# ---------------------------------------------------------------------------

REGULAR = 400
#: The app's one emphasis weight. Qt's ``setBold`` is 700 and disagrees with
#: this by a visible step, so use :func:`semibold` rather than the Qt call.
SEMIBOLD = 600

# ---------------------------------------------------------------------------
# Caps tier
# ---------------------------------------------------------------------------

#: Letter-spacing every caps-title label shares (percentage of the font's
#: normal advance). Qt's stylesheets have no ``letter-spacing`` or
#: ``text-transform``, so the caps tier is half QSS (size, colour) and half
#: code (spacing, uppercasing) -- both halves live in this module so they
#: cannot drift apart the way they once did.
CAPS_LETTER_SPACING = 108


def apply_caps_spacing(font: QFont) -> QFont:
    """Set *font*'s letter-spacing to :data:`CAPS_LETTER_SPACING`, in place,
    and return it for chaining."""
    font.setLetterSpacing(QFont.PercentageSpacing, CAPS_LETTER_SPACING)
    return font


def panel_title(
    text: str, object_name: str = "PanelTitle", parent: QWidget | None = None
) -> QLabel:
    """A caps panel-title label.

    Every *fixed* panel/section label the app owns renders as this one tier.
    Data-derived text (document names, run names, section paths) must never
    pass through here -- caps are for chrome the app authors, not for content
    it displays; those labels use the content-heading tier
    (``QLabel#Heading``) instead.

    ``object_name`` defaults to the shared ``PanelTitle`` rule (MUTED); a
    caller with its own colour identity (the reference box's purple
    ``ReferenceHeading``) passes its objectName so QSS keeps the hue while the
    tier treatment stays identical.
    """
    label = QLabel(text.upper(), parent)
    label.setObjectName(object_name)
    label.setFont(apply_caps_spacing(label.font()))
    return label


# ---------------------------------------------------------------------------
# QFont helpers -- for painted/delegate text, which QSS cannot reach
# ---------------------------------------------------------------------------


def ui_font(size: int = BODY, *, weight: int = REGULAR) -> QFont:
    """A UI-face font at rung *size*."""
    font = QFont()
    font.setFamilies(list(UI_FAMILIES))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


@lru_cache(maxsize=32)
def _mono(size: int, weight: int, slanted: bool) -> QFont:
    font = QFont()
    font.setFamilies(list(MONO_FAMILIES))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    font.setItalic(slanted)
    return font


def mono(size: int = BODY, *, weight: int = REGULAR, slanted: bool = False) -> QFont:
    """The app's monospace font -- values, the Source page, reference grids.

    Cached, because the Source page builds one per painted text segment; a
    fresh copy is returned so a caller mutating it cannot poison the cache.
    """
    return QFont(_mono(size, weight, slanted))


def apply_application_font() -> None:
    """Pin :data:`UI_FAMILIES` as the application font.

    Called once by ``MainWindow``, beside the global stylesheet it already
    installs -- the same seam, so tests that construct a ``MainWindow``
    directly get the same type as the real app. Setting it on the
    *application* rather than only in QSS is what makes a bare ``QFont()``
    (QtCharts axis labels, for one) inherit the right family.
    """
    app = QApplication.instance()
    if app is not None:
        app.setFont(ui_font())


def sized(font: QFont, size: int) -> QFont:
    """A copy of *font* at rung *size* (pixels).

    Delegates paint with ``option.font``, which already carries the app's
    family; stepping only its size keeps painted text in the same family as
    the widget text around it.
    """
    stepped = QFont(font)
    stepped.setPixelSize(size)
    return stepped


def semibold(font: QFont) -> QFont:
    """A copy of *font* at :data:`SEMIBOLD`.

    Use instead of ``QFont.setBold(True)``, which is weight 700 -- a visibly
    heavier step than the 600 the stylesheet uses everywhere else.
    """
    weighted = QFont(font)
    weighted.setWeight(QFont.Weight(SEMIBOLD))
    return weighted


def italic(font: QFont) -> QFont:
    """A copy of *font* in italic -- the app's one "absent/placeholder" cue."""
    slanted = QFont(font)
    slanted.setItalic(True)
    return slanted


# ---------------------------------------------------------------------------
# Stylesheet tokens
# ---------------------------------------------------------------------------


def qss_tokens() -> dict[str, str]:
    """Substitution values for ``style.STYLESHEET``'s ``string.Template``.

    A ``Template`` rather than an f-string because the stylesheet is full of
    literal ``{``/``}`` that an f-string would need escaped at every brace.
    """
    return {
        "title": str(TITLE),
        "body": str(BODY),
        "meta": str(META),
        "micro": str(MICRO),
        "regular": str(REGULAR),
        "semibold": str(SEMIBOLD),
    }


def size_qss(size: int) -> str:
    """``font-size`` declaration for an inline stylesheet."""
    return f"font-size: {size}px;"


def semibold_qss() -> str:
    """``font-weight`` declaration for an inline stylesheet."""
    return f"font-weight: {SEMIBOLD};"


# ---------------------------------------------------------------------------
# Rendered maths
# ---------------------------------------------------------------------------

#: Points per device-independent pixel at Qt's 96 dpi reference (1pt = 1/72
#: inch, 1px = 1/96 inch).
_POINTS_PER_PIXEL = 0.75

#: Nudge for rendered maths against the widget text beside it, should the two
#: ever need to disagree. One constant, one place: matplotlib's mathtext sets
#: its own face, so cap heights are not guaranteed to line up the way the UI
#: and mono faces do.
SYMBOL_OPTICAL_SCALE = 1.0


def points(pixels: int) -> float:
    """Convert a rung to the *points* matplotlib's mathtext renderer wants.

    Symbols used to be sized in points while every other size in the app was
    in pixels, so a card header's symbol asked for 13.0pt -- 17.3px -- beside
    a 15px title, a third too large, and the two scales would have drifted
    further apart at any other DPI. Callers now pass a rung and never see a
    point size.
    """
    return pixels * _POINTS_PER_PIXEL * SYMBOL_OPTICAL_SCALE
