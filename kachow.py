import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase (use your existing initialization logic)
if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")  # Replace with your credentials
    firebase_admin.initialize_app(cred)

# Connect to Firestore
db = firestore.client()

def get_regular_season_data(year: str):
    """Retrieve regular season data for a specific year."""
    year = "2024"
    doc_ref = db.collection("regular_season_data_b").document(year)
    doc = doc_ref.get()

    if not doc.exists:
        print(f"⚠️ No data found for year: {year}")
        return None

    # Fetch players from the subcollection
    players_ref = doc_ref.collection("players")
    players = [player.to_dict() for player in players_ref.stream()]

    return {
        "last_updated": doc.to_dict().get("last_updated"),
        "players": players
    }

def test_get_regular_season_data():
    """Test the get_regular_season_data function."""
    year = "2024"  # Replace with the year you want to test
    print(f"🔍 Testing get_regular_season_data for year: {year}")

    data = get_regular_season_data(year)

    if data:
        print(f"✅ Data retrieved successfully for year: {year}")
        print(f"📅 Last Updated: {data['last_updated']}")
        print(f"👤 Number of Players: {len(data['players'])}")

        # Print the first 3 players (for debugging)
        for i, player in enumerate(data["players"][:3]):
            print(f"\nPlayer {i + 1}:")
            for key, value in player.items():
                print(f"{key}: {value}")
    else:
        print(f"⚠️ No data found for year: {year}")

if __name__ == "__main__":
    test_get_regular_season_data()