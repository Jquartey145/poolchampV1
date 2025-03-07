import streamlit as st
from side_channel_app.side_channel import fetch_player_stats
from google.cloud import firestore
import json
from google.oauth2 import service_account

# Authenticate Firestore
key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds)

<<<<<<< Updated upstream
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
=======
# Display data from Firestore
st.title("Player Stats and Firestore Example")
doc_ref = db.collection("players").document("8TJffLlxrseUjYWgqBpF")
doc = doc_ref.get()

if doc.exists:
    st.write("Firestore Document Contents:", doc.to_dict())
else:
    st.error("Document not found in Firestore!")

# Fetch and display player stats
SDIO_API_KEY = '4fa3622c0f8a6b4c9b72adfe2dbb8ad2'
SEASON = 2023
st.subheader(f"Player Stats for Season {SEASON}")
player_stats = fetch_player_stats(SDIO_API_KEY, SEASON)

if isinstance(player_stats, str):  # Error message
    st.error(player_stats)
else:
    st.json(player_stats[:5])  # Display first 5 records
>>>>>>> Stashed changes
