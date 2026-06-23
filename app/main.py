"""Explore_BPX — Streamlit entry point.

This module only wires the frontend-agnostic core/state to the Streamlit UI.
It contains no BPX or business logic.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import export
from core.bpx_gateway import BPX_VERSION
from state.app_state import AppState
from ui import inspector_panel, tree_panel, upload_panel, validation_panel


def _get_state() -> AppState:
    if "app_state" not in st.session_state:
        st.session_state["app_state"] = AppState()
    return st.session_state["app_state"]


def _render_document_header(state: AppState) -> None:
    document = state.document
    name, status, json_btn, yaml_btn = st.columns([3, 1, 1, 1])
    name.markdown(f"**{document.filename}**")
    if document.is_valid:
        status.success("Valid")
    else:
        status.error("Invalid")

    stem = Path(document.filename).stem
    json_btn.download_button(
        "JSON",
        data=export.to_json(document.raw),
        file_name=f"{stem}.json",
        mime="application/json",
        use_container_width=True,
    )
    yaml_btn.download_button(
        "YAML",
        data=export.to_yaml(document.raw),
        file_name=f"{stem}.yaml",
        mime="application/x-yaml",
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title="Explore_BPX", layout="wide")
    state = _get_state()

    st.title("Explore_BPX")
    st.caption(f"A BPX explorer · using bpx {BPX_VERSION}")

    upload_panel.render(state)

    if not state.has_document:
        st.info("Open a BPX file to begin.")
        return

    _render_document_header(state)

    issue_count = state.document.error_count + state.document.warning_count
    explorer_tab, validation_tab = st.tabs(
        ["Explorer", f"Validation ({issue_count})"]
    )
    with explorer_tab:
        tree_column, inspector_column = st.columns([1, 2])
        with tree_column:
            tree_panel.render(state)
        with inspector_column:
            inspector_panel.render(state)
    with validation_tab:
        validation_panel.render(state)


main()
