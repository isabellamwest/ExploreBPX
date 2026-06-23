"""Tree navigation panel: drill through sections and select a parameter."""

from __future__ import annotations

import streamlit as st

from core.tree_model import TreeNode
from state.app_state import AppState


def render(state: AppState) -> None:
    document = state.document
    if document is None:
        return

    st.subheader("Structure")
    for child in document.tree.children:
        _render_node(child, state)


def _render_node(node: TreeNode, state: AppState) -> None:
    if node.is_section:
        _render_section(node, state)
    else:
        _render_leaf(node, state)


def _render_section(node: TreeNode, state: AppState) -> None:
    label = f"{node.icon} {node.label}"
    if _descendant_has_error(node):
        label += "  ❗"
    with st.expander(label, expanded=False):
        if not node.children:
            st.caption("(empty)")
        for child in node.children:
            _render_node(child, state)


def _render_leaf(node: TreeNode, state: AppState) -> None:
    marker = " ❗" if node.has_errors else ""
    key = "nav::" + "/".join(node.path)
    selected = state.selected_path == node.path
    if st.button(
        f"{node.icon} {node.label}{marker}",
        key=key,
        use_container_width=True,
        type="primary" if selected else "secondary",
    ):
        state.select(node.path)


def _descendant_has_error(node: TreeNode) -> bool:
    if node.has_errors:
        return True
    return any(_descendant_has_error(child) for child in node.children)
