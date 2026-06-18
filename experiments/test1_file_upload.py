import streamlit as st

st.title("BPX Validator")

# File uploader for BPX JSON file
uploaded_file = st.file_uploader(
    "Select BPX JSON file",
    type=["json"]
)

if uploaded_file is not None:
    st.success("BPX file selected")

    st.write(f"Filename: {uploaded_file.name}")
    