import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase (use your existing initialization logic)
if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")  # Replace with your credentials
    firebase_admin.initialize_app(cred)

# Connect to Firestore
db = firestore.client()

def reset_submission_totals():
    """Reset total_points to 0 for all submissions."""
    submissions_ref = db.collection("submissions")
    submissions = submissions_ref.stream()

    batch = db.batch()
    batch_count = 0
    MAX_BATCH_SIZE = 500  # Firestore batch limit

    for doc in submissions:
        # Add update operation to batch
        doc_ref = submissions_ref.document(doc.id)
        batch.update(doc_ref, {"total_points": 0})
        batch_count += 1

        # Commit batch when reaching limit
        if batch_count >= MAX_BATCH_SIZE:
            batch.commit()
            print(f"✅ Updated {batch_count} submissions.")
            batch = db.batch()
            batch_count = 0

    # Commit remaining operations
    if batch_count > 0:
        batch.commit()
        print(f"✅ Updated {batch_count} submissions.")

    print("🎉 All submissions updated successfully.")

if __name__ == "__main__":
    reset_submission_totals()