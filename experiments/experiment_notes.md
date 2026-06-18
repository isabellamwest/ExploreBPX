# Streamlit Investigation

## Current Architecture

Input File 
 - Parser 
 - Pydantic validation
 - Validation output 

### Pydantic validation example:

Define data structure and rules 

    class User(BaseModel):
    username: str
    age: int
Provide data

    try: 
    valid_user = User(username="isabella393", age=19)
    print("Success:, valid_user")

## Test 0: Basic Streamlit App 

Successfully launched a Streamlit web application :))

## Test 1: BPX File Upload

Used Streamlit's built-in file uploader restricted to JSON files. 

Successful. Saved as test 1. 

## Test 2: Read BPX JSON File

Uploaded a BPX JSON file and loaded it using Python's json module. Successfully displayed the BPX contents in the browser. 

Saved as test 2. 


