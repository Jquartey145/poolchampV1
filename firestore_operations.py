import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2 import service_account
import json

# Authenticate to Firestore with the JSON account key.
key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds)

## -------------------------------------------------------------------------------------------------
## Team functions ----------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------

def get_team(team_id):
    teams_ref = db.collection('teams')
    team_doc = teams_ref.document(team_id).get()

    if team_doc.exists:
        return team_doc.to_dict()
    else:
        return None
    
def get_players_from_team(team_id):
    teams_ref = db.collection('teams')
    document_data = teams_ref.document(team_id).get().to_dict()

    if document_data:
        # Access the 'players' array from the document data
        players_array = document_data.get('players', [])

        # Convert the dictionary to a JSON string
        # result_dict = {'players' : players_array}
        # players_array = json.dumps(result_dict, indent=2)

        return players_array
    else:
        print(f"Document with ID '{team_id}' not found.")

    
## -------------------------------------------------------------------------------------------------
## Player functions ----------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------

def get_specific_player(player_id):
    players_ref = db.collection('players')
    player_doc = players_ref.document(player_id).get()

    if player_doc.exists:
        return player_doc.to_dict()
    else:
        return None

## -------------------------------------------------------------------------------------------------
## School functions ----------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------
    
def get_school(school_id):
    schools_ref = db.collection('school')
    school_doc = schools_ref.document(school_id).get()

    if school_doc.exists:
        return school_doc.to_dict()
    else:
        return None
