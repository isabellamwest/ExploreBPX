"""Inspector panel: read-only detail view for the selected parameter."""

from __future__ import annotations

import streamlit as st

from core.parameter_types import ParameterKind
from core.tree_model import TreeNode
from core.validation import Severity
from state.app_state import AppState


def render(state: AppState) -> None:
    node = state.selected_node()
    if node is None:
        st.info("Select a parameter from the structure to inspect it.")
        return

    st.subheader(f"{node.icon} {node.label}")
    st.caption(" → ".join(node.path))

    if node.description:
        st.write(node.description)

    columns = st.columns(2)
    columns[0].metric("Type", node.kind.value)
    columns[1].metric("Unit", node.unit or "—")

    _render_value(node)
    _render_examples(node)
    _render_issues(node)


def _render_value(node: TreeNode) -> None:
    st.markdown("**Value**")
    if node.kind == ParameterKind.TABLE:
        _render_table(node.value)
    elif node.kind == ParameterKind.FUNCTION:
        st.code(str(node.value), language="text")
    elif node.kind == ParameterKind.SECTION:
        st.caption(f"{len(node.children)} item(s) in this section.")
    else:
        st.write(node.value)


def _render_table(value: object) -> None:
    if isinstance(value, dict) and "x" in value and "y" in value:
        st.dataframe({"x": value["x"], "y": value["y"]}, use_container_width=True)
    elif isinstance(value, list):
        st.dataframe({"value": value}, use_container_width=True)
    else:
        st.write(value)


def _render_examples(node: TreeNode) -> None:
    if node.examples:
        with st.expander("Examples from the BPX schema"):
            for example in node.examples:
                st.write(example)


def _render_issues(node: TreeNode) -> None:
    if not node.issues:
        return
    st.divider()
    for issue in node.issues:
        if issue.severity == Severity.ERROR:
            st.error(issue.message)
        else:
            st.warning(issue.message)
