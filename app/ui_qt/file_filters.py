"""File-dialog filter strings, derived from what the app can actually open.

Every Open/Export dialog and the Workspace's drop target used to spell the
extension list out by hand -- five copies of ``"BPX (*.json *.yaml *.yml)"``
plus a separate tuple in ``workspace_panel``, kept in step only by a comment
asking the next person to remember. Adding a format meant finding them all.

Here they are built once from ``core.bpx_gateway.SUPPORTED_EXTENSIONS``, the
same tuple that decides how a loaded file is *parsed*, so a dialog can never
offer a format the loader does not read, or hide one it does.
"""

from __future__ import annotations

from core.bpx_gateway import SUPPORTED_EXTENSIONS, YAML_EXTENSIONS


def _patterns(extensions: tuple[str, ...]) -> str:
    return " ".join(f"*{extension}" for extension in extensions)


#: Every BPX file the app opens: the Open, Pin-as-reference and
#: New-from-existing-file dialogs.
BPX_FILTER = f"BPX ({_patterns(SUPPORTED_EXTENSIONS)})"

#: The same, with the escape hatch a user needs when their file carries an
#: unexpected extension.
BPX_FILTER_WITH_ALL = f"BPX files ({_patterns(SUPPORTED_EXTENSIONS)});;All files (*)"


def export_filter(fmt: str) -> str:
    """The Save-As filter for one export format -- narrowed to that format
    alone, since the format is already chosen by the time the dialog opens
    and offering the other one would let the name and the content disagree.
    """
    if fmt == "yaml":
        return f"YAML ({_patterns(YAML_EXTENSIONS)})"
    return "JSON (*.json)"
