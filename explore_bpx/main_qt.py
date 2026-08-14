"""ExploreBPX - PySide6 desktop entry point.

Wires the frontend-agnostic state/core layers to the Qt frontend. No BPX or
business logic lives here.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from explore_bpx.state.workspace_history import WorkspaceHistory
from explore_bpx.ui_qt.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    # Named before the config path is asked for, so the workspace history
    # lands in a stable per-app directory rather than one derived from the
    # interpreter's name.
    app.setApplicationName("ExploreBPX")
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    window = MainWindow(history=WorkspaceHistory(config_dir / "workspace_history.json"))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
