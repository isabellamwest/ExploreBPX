"""File upload panel: opens a BPX file into the application state."""

from __future__ import annotations

import streamlit as st

from core.bpx_gateway import LoadError
from state.app_state import AppState


def render(state: AppState) -> None:
    uploaded = st.file_uploader(
        "Open a BPX file",
        type=["json", "yaml", "yml"],
        help="JSON or YAML in the BPX format. Invalid files can still be explored.",
    )
    if uploaded is None:
        return

    signature = (uploaded.name, uploaded.size)
    if st.session_state.get("_loaded_signature") == signature:
        return

    try:
        state.load(uploaded.getvalue(), uploaded.name)
        st.session_state["_loaded_signature"] = signature
    except LoadError as exc:
        state.clear()
        st.session_state["_loaded_signature"] = None
        st.error(f"Could not open file: {exc}")
