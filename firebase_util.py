import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import json
import streamlit as st

# Load Firebase credentials from Streamlit secrets or a local file.
if "textkey" in st.secrets:
    key_dict = json.loads(st.secrets["textkey"])
    cred = credentials.Certificate(key_dict)
else:
    cred = credentials.Certificate("firestore-key.json")

# Initialize Firebase if not already initialized.
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Connect to Firestore.
db = firestore.client()

def tournament_data_exists(year: str):
    doc_ref = db.collection("tournament_data").document(year)
    return doc_ref.get().exists

def save_player_data(year: str, players: list):
    """
    Save player data to Firestore under the tournament_data collection.
    Each player dictionary is expected to include fields such as:
      - "Player": Name
      - "Team": Team name
      - "Seed": Seed value
      - "Region": Region name
      - "Position": Player position
      - "active": Boolean indicating if the player is active
      - Other stats: "Games", "Points", "PPG", "FG%", "3P%", etc.
    """
    tournament_doc = db.collection("tournament_data").document(year)
    players_collection = tournament_doc.collection("players")
    for player in players:
        players_collection.add(player)
    tournament_doc.set({"data_uploaded": True, "year": year}, merge=True)

def get_tournament_data_from_firestore(year: str):
    tournament_doc = db.collection("tournament_data").document(year)
    players_collection = tournament_doc.collection("players")
    docs = players_collection.stream()
    players = []
    for doc in docs:
        d = doc.to_dict()
        d["doc_id"] = doc.id   # Add the document id for reference lookup
        players.append(d)
    return players


def get_submissions():
    """
    Retrieve all submissions, ordered by total_points (descending).
    Each submission is expected to include:
      - "team_name"
      - "participant"
      - "players": a list of player objects (with fields like name, team, seed, position, active, etc.)
      - "total_points"
    """
    docs = db.collection("submissions").order_by("total_points", direction=firestore.Query.DESCENDING).stream()
    return [doc.to_dict() for doc in docs]

def save_submission(submission):
    """
    Save a team submission to Firestore.
    The submission dictionary may include:
      - "team_name"
      - "participant"
      - "payment_type"
      - "players": a list of detailed player objects
      - "total_points"
    """
    participant = submission.get("participant", "").strip()
    team_name = submission.get("team_name", "").strip()
    if participant and team_name:
        doc_id = f"{participant.replace(' ', '_')}_{team_name.replace(' ', '_')}"
        db.collection("submissions").document(doc_id).set(submission)
    elif participant:
        doc_id = participant.replace(" ", "_")
        db.collection("submissions").document(doc_id).set(submission)
    else:
        db.collection("submissions").add(submission)

def get_net_rankings(year: str):
    """Retrieve the NET rankings document for a given year."""
    doc_ref = db.collection("net_rankings").document(year)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return None

def save_net_rankings(year: str, top16: list):
    """Save the top 16 teams (with fields like team_id, team_name, rank) and a timestamp."""
    doc_ref = db.collection("net_rankings").document(year)
    data = {
        "top16": top16,
        "last_updated": datetime.datetime.now().isoformat()
    }
    doc_ref.set(data)

def get_top16_player_data(year: str):
    """
    Retrieve the top 16 player data for the given year.
    Each player document should now include the new fields (e.g. active, Region, etc.)
    """
    doc_ref = db.collection("top16_player_data").document(year)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("players", [])
    return None

def save_top16_player_data(year: str, players: list):
    """
    Save the top 16 player data to Firestore.
    Each player object may include fields like:
      - "Player", "Team", "Seed", "Region", "Position", "active", etc.
      - Other stats: "Games", "Points", "PPG", "FG%", "3P%"
    """
    doc_ref = db.collection("top16_player_data").document(year)
    data = {
        "players": players,
        "last_updated": datetime.datetime.now().isoformat()
    }
    doc_ref.set(data)
