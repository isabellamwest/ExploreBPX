import warnings

import streamlit as st
from pydantic import ValidationError

from bpx.schema_utils import BPXSchemaError
from services.bpx_validator import validate_bpx_bytes

st.title("BPX Validator")

uploaded_file = st.file_uploader(
    "Upload a BPX JSON or YAML file",
    type=["json", "yaml", "yml"],
)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    file_name = uploaded_file.name

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")

        try:
            validate_bpx_bytes(file_bytes, file_name)
        except (ValidationError, BPXSchemaError) as validation_error:
            st.error("BPX validation failed.")
            st.exception(validation_error)
        except ValueError as value_error:
            st.error("Invalid BPX file content.")
            st.exception(value_error)
        except Exception as other_error:
            st.error("An unexpected error occurred during BPX validation.")
            st.exception(other_error)
        else:
            st.success("BPX file validated successfully.")
            if caught_warnings:
                st.warning("Validation completed with warnings:")
                for warning in caught_warnings:
                    st.write(f"- {warning.message}")
