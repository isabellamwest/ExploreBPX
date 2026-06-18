import streamlit as st
import json

st.title("BPX Validator")

uploaded_file = st.file_uploader(
    "Upload BPX JSON File",
    type=["json"]
)

if uploaded_file is not None:

    data = json.load(uploaded_file)

    st.success("BPX file loaded")

    st.subheader("Raw BPX Contents")

    st.json(data) # Display the raw JSON data in a formatted way
    