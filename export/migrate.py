import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK (update the path to your service account key)
if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

YEAR = "2025"

# Retrieve all documents from the old 'submissions' collection
old_collection = db.collection("submissions")
new_collection = db.collection("submissions").document(YEAR).collection("entries")

docs = old_collection.stream()

# Migrate each document to the new nested collection
count = 0
for doc in docs:
    data = doc.to_dict()
    new_collection.document(doc.id).set(data)
    count += 1

print(f"Migration complete! {count} submissions migrated to submissions/{YEAR}/entries")