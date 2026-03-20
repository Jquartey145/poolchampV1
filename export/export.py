import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd

# Initialize Firebase Admin SDK (update the path to your service account key)
if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Retrieve all documents from the 'submissions' collection
docs = db.collection("submissions").stream()
submissions = [doc.to_dict() for doc in docs if doc.id != "2025"]

# Create a list to hold flattened data
flattened_data = []

# Process each submission
for submission in submissions:
    # Extract submission details
    venmo_username = submission.get("venmo_username", "")
    email = submission.get("email_address","")
    total_points = submission.get("total_points", 0)
    participant = submission.get("participant", "")
    payment_type = submission.get("payment_type", "")
    team_name = submission.get("team_name", "")
    players = submission.get("players", [])  # Get the players as a list

    # Create a new row for each player
    for player in players:
        flattened_data.append({
            "Total Points": total_points,
            "Participant Name": participant,
            "Email Address": email,
            "team_name": team_name,
            "Player Name": player.get("name", ""),
            "Player Position": player.get("position", ""),
            "Seed": player.get("seed", ""),
            "Team": player.get("team", "")
        })

# Convert the flattened data to a pandas DataFrame
df = pd.DataFrame(flattened_data)

# Export the DataFrame to CSV
df.to_csv("submissions_export1.csv", index=False)

print("Export complete! Data saved to submissions_export.csv")