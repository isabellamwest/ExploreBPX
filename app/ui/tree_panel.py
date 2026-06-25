"""Tree navigation panel: drill through BPX objects and select one to inspect."""

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
    if node.children:
        _render_section(node, state)
    else:
        _render_leaf(node, state)


def _render_section(node: TreeNode, state: AppState) -> None:
    label = f"{node.icon} {node.label}"
    if node.has_errors:
        label += "  ❗"
    with st.expander(label, expanded=False):
        _render_leaf(node, state, prefix="Open")
        if node.parameters:
            st.caption(f"{len(node.parameters)} parameter(s)")
        for child in node.children:
            _render_node(child, state)


def _render_leaf(node: TreeNode, state: AppState, prefix: str = "") -> None:
    marker = " ❗" if node.has_errors else ""
    key = "nav::" + "/".join(node.path)
    selected = state.selected_path == node.path
    label = f"{node.icon} {node.label}{marker}"
    if prefix:
        label = f"{prefix} {label}"
    if st.button(
        label,
        key=key,
        use_container_width=True,
        type="primary" if selected else "secondary",
    ):
        state.select(node.path)
