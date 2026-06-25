"""Inspector (right panel): breadcrumb + swapping body (parameter list/detail).

The right panel has a persistent top section (a clickable BPX-path breadcrumb)
and a body that swaps in place:

* an object is selected, no parameter -> the object's **parameter list**;
* a parameter is selected -> that parameter's **detail view**.

V1 is read-only: the detail shows values (simple or expandable) and a disabled
"Advanced display" placeholder for future graphs. Editing and plotting are later
versions; this panel only renders and navigates.
"""

from __future__ import annotations

import streamlit as st

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from core.validation import Severity
from state.app_state import AppState


def render(state: AppState) -> None:
    node = state.selected_node()
    if node is None:
        st.info("Select an object from the structure to inspect it.")
        return

    parameter = state.selected_parameter()

    _render_breadcrumb(node, parameter, state)

    if parameter is None:
        _render_object_error_banner(node)
        _render_parameter_list(node, state)
    else:
        _render_parameter_detail(parameter)


def _render_breadcrumb(
    node: TreeNode, parameter: ParameterItem | None, state: AppState
) -> None:
    """Persistent top section: clickable path that navigates back up.

    Object segments re-select their object (showing its parameter list); the
    final parameter segment, when present, is the current view and is inert.
    """
    object_path = node.path
    columns = st.columns(len(object_path) + (1 if parameter else 0) + 1)

    columns[0].markdown("**📂**")
    for index in range(len(object_path)):
        segment_path = object_path[: index + 1]
        label = object_path[index]
        is_current = parameter is None and segment_path == object_path
        if is_current:
            columns[index + 1].markdown(f"**{label}**")
        elif columns[index + 1].button(label, key="crumb::" + "/".join(segment_path)):
            state.select(segment_path)
            st.rerun()

    if parameter is not None:
        columns[-1].markdown(f"**{parameter.label}**")

    st.divider()


def _render_object_error_banner(node: TreeNode) -> None:
    """Object-level issues have no parameter row, so surface them here."""
    for issue in node.issues:
        if issue.severity == Severity.ERROR:
            st.error(issue.message)
        else:
            st.warning(issue.message)


def _render_parameter_list(node: TreeNode, state: AppState) -> None:
    if node.children:
        st.caption(
            "Child objects (navigate via the tree): "
            + ", ".join(child.label for child in node.children)
        )

    if not node.parameters:
        st.caption("No direct parameters in this object.")
        return

    st.markdown("**Parameters**")
    for parameter in node.parameters:
        marker = " ❗" if parameter.has_errors else ""
        key = "param::" + "/".join(parameter.path)
        if st.button(
            f"{parameter.icon} {parameter.label}{marker}",
            key=key,
            use_container_width=True,
        ):
            state.select_parameter(parameter.path)
            st.rerun()


def _render_parameter_detail(parameter: ParameterItem) -> None:
    st.subheader(f"{parameter.icon} {parameter.label}")

    if parameter.description:
        st.write(parameter.description)

    columns = st.columns(2)
    columns[0].metric("Type", parameter.kind.value)
    columns[1].metric("Unit", parameter.unit or "—")

    _render_value(parameter)
    _render_examples(parameter)
    _render_full_issues(parameter)
    _render_advanced_display(parameter)


def _render_value(parameter: ParameterItem) -> None:
    st.markdown("**Value**")
    if parameter.kind == ParameterKind.TABLE:
        _render_table(parameter.value)
    elif parameter.kind == ParameterKind.FUNCTION:
        with st.expander("Expression", expanded=True):
            st.code(str(parameter.value), language="text")
    else:
        st.write(parameter.value)


def _render_table(value: object) -> None:
    if isinstance(value, dict) and "x" in value and "y" in value:
        st.dataframe({"x": value["x"], "y": value["y"]}, use_container_width=True)
    elif isinstance(value, list):
        st.dataframe({"value": value}, use_container_width=True)
    else:
        st.write(value)


def _render_examples(parameter: ParameterItem) -> None:
    if parameter.examples:
        with st.expander("Examples from the BPX schema"):
            for example in parameter.examples:
                st.write(example)


def _render_full_issues(parameter: ParameterItem) -> None:
    """The detail view is the single home for full validation text."""
    if not parameter.issues:
        return
    st.divider()
    for issue in parameter.issues:
        if issue.severity == Severity.ERROR:
            st.error(issue.message)
        else:
            st.warning(issue.message)


def _render_advanced_display(parameter: ParameterItem) -> None:
    """Placeholder entry point for future display features (graphs, V3)."""
    st.divider()
    st.button(
        "📈 Advanced display",
        key="advanced::" + "/".join(parameter.path),
        disabled=True,
        help="Coming soon: graphs and plots for functions and tables.",
    )
