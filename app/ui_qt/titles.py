"""Panel-title vocabulary.

Every *fixed* panel/section label the app owns renders as one tier: 11px
uppercase MUTED caps with the same letter-spacing ``PageHeader`` introduced,
so panel chrome reads distinctly from content. Data-derived text (document
names, run names, section paths) must never pass through here -- caps are for
chrome the app authors, not for content it displays; those labels use the
content-heading tier (``QLabel#Heading``) instead.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QWidget

#: Letter-spacing every caps-title label in the app shares (percentage of the
#: font's normal advance) -- named once so ``panel_title`` below and
#: ``PageHeader`` (which titles a different surface, hence its own QSS
#: object name/size, but must still read as the same caps tier) never drift
#: apart the way they once did.
CAPS_LETTER_SPACING = 108


def apply_caps_spacing(font: QFont) -> QFont:
    """Set *font*'s letter-spacing to :data:`CAPS_LETTER_SPACING`, in place,
    and return it for chaining -- the one place that spacing value lives,
    since Qt's stylesheets have no ``letter-spacing`` property."""
    font.setLetterSpacing(QFont.PercentageSpacing, CAPS_LETTER_SPACING)
    return font


def panel_title(
    text: str, object_name: str = "PanelTitle", parent: QWidget | None = None
) -> QLabel:
    """A caps panel-title label.

    ``object_name`` defaults to the shared ``PanelTitle`` rule (MUTED); a
    caller with its own colour identity (the reference box's purple
    ``ReferenceHeading``) passes its objectName so QSS keeps the hue while
    the tier treatment stays identical. Qt's stylesheets have no
    ``text-transform``/``letter-spacing``, hence the uppercased text and
    font spacing set here in code, exactly as ``PageHeader`` does.
    """
    label = QLabel(text.upper(), parent)
    label.setObjectName(object_name)
    label.setFont(apply_caps_spacing(label.font()))
    return label
