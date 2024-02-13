import streamlit as st
from google.cloud import firestore

# Authenticate to Firestore with the JSON account key.
import json
key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds, project="streamlit-reddit")

# Create a reference to the Google post.
doc_ref = db.collection("users").document("Test Account")

# Then get the data at that reference.
doc = doc_ref.get()

# Let's see what we got!
# st.write("The email is: ", doc.teams)
st.write("The contents are: ", doc.to_dict())

doc_ref = db.collection("users").document("Lani K")

# And then uploading some data to that reference
doc_ref.set({
	"name": "Apple",
	"email": "apple@gmail.com"
})