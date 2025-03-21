import firebase_admin
from firebase_admin import credentials, firestore
import time

# Initialize Firebase Admin with your service account key
cred = credentials.Certificate("firestore-key.json")  # Update with your credentials path
firebase_admin.initialize_app(cred)

db = firestore.client()

BATCH_SIZE = 500  # Firestore batch write limit

def reset_submissions():
    """Reset total_points field to 0 on all submissions."""
    submissions_ref = db.collection("submissions")
    docs = list(submissions_ref.stream())

    print(f"Found {len(docs)} submissions to update.")

    batch = db.batch()
    count = 0
    for doc in docs:
        doc_ref = submissions_ref.document(doc.id)
        batch.update(doc_ref, {"total_points": 0})
        count += 1

        if count % BATCH_SIZE == 0:
            batch.commit()
            print(f"Committed {count} submission updates...")
            batch = db.batch()
            time.sleep(1)  # slight pause to avoid rate limits

    # Commit any remaining operations
    if count % BATCH_SIZE != 0:
        batch.commit()
    print(f"✅ Reset total_points to 0 on {count} submissions.")


def reset_players(tournament_year="2024"):
    """
    Reset total_points field to 0 on all players in the specified tournament.
    Assumes players are stored under: tournament_data/{tournament_year}/players.
    """
    players_ref = db.collection("tournament_data").document(tournament_year).collection("players")
    docs = list(players_ref.stream())

    print(f"Found {len(docs)} players to update for tournament {tournament_year}.")

    batch = db.batch()
    count = 0
    for doc in docs:
        doc_ref = players_ref.document(doc.id)
        batch.update(doc_ref, {"total_points": 0})
        count += 1

        if count % BATCH_SIZE == 0:
            batch.commit()
            print(f"Committed {count} player updates...")
            batch = db.batch()
            time.sleep(1)

    # Commit any remaining operations
    if count % BATCH_SIZE != 0:
        batch.commit()
    print(f"✅ Reset total_points to 0 on {count} players.")


if __name__ == "__main__":
    reset_submissions()
    reset_players("2024")  # Change the tournament year if needed
