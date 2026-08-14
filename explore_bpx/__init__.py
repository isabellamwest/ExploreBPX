"""ExploreBPX - desktop app for exploring, validating and editing BPX files.

The public surface is deliberately small: :func:`main` launches the desktop
app, and ``__version__`` reports the installed version. Everything else
(``core``, ``state``, ``ui_qt``) is internal and may change without notice.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("explore-bpx")
except PackageNotFoundError:  # a source tree that has not been installed
    __version__ = "0.0.0.dev0"


def main() -> None:
    """Launch the ExploreBPX desktop app (the console entry point).

    Imports Qt lazily so that ``import explore_bpx`` stays cheap and
    UI-free for anything that only wants ``__version__``.
    """
    from explore_bpx.main_qt import main as run

    run()


__all__ = ["__version__", "main"]
