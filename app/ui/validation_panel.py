"""Validation panel: lists all issues and links each to its parameter."""

from __future__ import annotations

import streamlit as st

from core.validation import Severity, ValidationIssue
from state.app_state import AppState


def render(state: AppState) -> None:
    document = state.document
    if document is None:
        return

    _render_summary(document.is_valid, document.error_count, document.warning_count)

    for index, issue in enumerate(document.issues):
        _render_issue(index, issue, state)


def _render_summary(is_valid: bool, errors: int, warnings: int) -> None:
    if is_valid and warnings == 0:
        st.success("Valid BPX file. No issues found.")
    elif is_valid:
        st.success(f"Valid BPX file with {warnings} warning(s).")
    else:
        st.error(f"Invalid BPX file — {errors} error(s), {warnings} warning(s).")


def _render_issue(index: int, issue: ValidationIssue, state: AppState) -> None:
    icon = "❗" if issue.severity == Severity.ERROR else "⚠"
    with st.container(border=True):
        st.markdown(f"{icon} **{issue.message}**")
        st.caption(issue.path_str)

        node = state.document.find_best(issue.path) if state.document else None
        if node is not None and not node.is_section:
            if st.button("Go to parameter", key=f"goto::{index}"):
                state.select(node.path)
                st.toast(f"Selected {node.label} — see the Explorer tab.")
