"""Platform truths the suite has to assert around, each measured, not assumed.

Kept in one place so the reason is written once rather than restated at every
call site, and so a wrong assumption is corrected in one edit.
"""

from __future__ import annotations

import sys

#: macOS alerts have no title bar. Apple's HIG gives them none, so Qt's cocoa
#: plugin drops the window title rather than rendering it, and
#: ``QMessageBox.windowTitle()`` reads ``""`` however it was set.
ALERTS_SHOW_A_TITLE = sys.platform != "darwin"


def assert_alert_title(actual: str, expected: str) -> None:
    """Assert a ``QMessageBox``'s window title on platforms that show one.

    The words still matter where they are rendered, so the assertion is not
    weakened -- it simply has nothing to read on macOS. Every alert this suite
    checks also states its point in ``text``/``informativeText``, which is
    asserted unconditionally, so a dropped title costs a macOS user no
    information. Do not move a fact a person needs into a title alone.
    """
    if ALERTS_SHOW_A_TITLE:
        assert actual == expected
    else:
        assert actual == ""
