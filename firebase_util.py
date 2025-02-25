import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase using your service account key
if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

def tournament_data_exists(year: str):
    """Check if tournament data for the given year already exists."""
    doc_ref = db.collection("tournament_data").document(year)
    return doc_ref.get().exists

def save_player_data(year: str, players: list):
    """
    Save tournament data in an alternate structure:
    Each player is stored as a document in the subcollection 'players' under document tournament_data/{year}.
    """
    tournament_doc = db.collection("tournament_data").document(year)
    players_collection = tournament_doc.collection("players")
    for player in players:
        players_collection.add(player)
    # Optionally, set a flag on the tournament document.
    tournament_doc.set({"data_uploaded": True, "year": year}, merge=True)

def get_tournament_data_from_firestore(year: str):
    """
    Retrieve tournament data (list of player dictionaries) from the subcollection 'players'
    under tournament_data/{year}.
    """
    tournament_doc = db.collection("tournament_data").document(year)
    players_collection = tournament_doc.collection("players")
    docs = players_collection.stream()
    players = [doc.to_dict() for doc in docs]
    return players

def get_submissions():
    """Retrieve team submissions ordered by total points descending."""
    docs = db.collection("submissions").order_by("total_points", direction=firestore.Query.DESCENDING).stream()
    submissions = [doc.to_dict() for doc in docs]
    return submissions

def save_submission(submission):
    participant = submission.get("participant", "").strip()
    team_name = submission.get("team_name", "").strip()

    if participant and team_name:
        # Replace spaces with underscores to create a safe document ID
        doc_id = f"{participant.replace(' ', '_')}_{team_name.replace(' ', '_')}"
        db.collection("submissions").document(doc_id).set(submission)
    elif participant:
        doc_id = participant.replace(" ", "_")
        db.collection("submissions").document(doc_id).set(submission)
    else:
        db.collection("submissions").add(submission)

