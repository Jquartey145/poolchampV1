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
submissions = [doc.to_dict() for doc in docs]

# Convert the list of dictionaries to a pandas DataFrame
df = pd.DataFrame(submissions)

# Optionally, flatten nested fields here if needed

# Export the DataFrame to CSV
df.to_csv("submissions_export.csv", index=False)

print("Export complete! Data saved to submissions_export.csv")
