"""
cleanup_submissions.py
----------------------
The submissions collection is structured as:

  submissions/                  ← flat legacy docs (to delete)
  submissions/2025/entries/     ← nested 2025 docs (to KEEP)

This script deletes all FLAT documents directly in the submissions
collection, leaving the submissions/2025/entries subcollection untouched.

DRY_RUN = True  → prints what would be deleted without touching anything
DRY_RUN = False → actually deletes

Run from project root:
    python cleanup_submissions.py
"""

import firebase_admin
from firebase_admin import credentials, firestore
import time

# ── Config ────────────────────────────────────────────────────────────────────

KEEP_YEAR  = "2025"
DRY_RUN    = False    # ← flip to False when ready
BATCH_SIZE = 400

# ── Init ──────────────────────────────────────────────────────────────────────

if not firebase_admin._apps:
    cred = credentials.Certificate("firestore-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n🧹 Submissions Cleanup")
    print(f"   Keeping:  submissions/{KEEP_YEAR}/entries  (untouched)")
    print(f"   Deleting: all flat docs directly in submissions/")
    print(f"   DRY_RUN = {DRY_RUN}")
    if DRY_RUN:
        print("   ⚠️  DRY RUN — nothing will be deleted.\n")

    docs = list(db.collection("submissions").stream())
    print(f"   Flat docs found in submissions/: {len(docs)}\n")

    # Skip the year document itself (e.g. "2025") — it's just a container
    to_delete = [d for d in docs if d.id != KEEP_YEAR]
    skipped   = [d for d in docs if d.id == KEEP_YEAR]

    if skipped:
        print(f"   Skipping document '{KEEP_YEAR}' (container for nested entries)\n")

    if not to_delete:
        print("   ✅  Nothing to delete.")
    else:
        batch = db.batch()
        count = 0
        for doc in to_delete:
            data = doc.to_dict()
            print(f"   {'[DRY RUN] ' if DRY_RUN else ''}delete: {doc.id}"
                  f"  (participant={data.get('participant', 'N/A')}, "
                  f"team={data.get('team_name', 'N/A')})")
            if not DRY_RUN:
                batch.delete(doc.reference)
            count += 1
            if not DRY_RUN and count % BATCH_SIZE == 0:
                batch.commit()
                batch = db.batch()
                time.sleep(0.5)

        if not DRY_RUN and count % BATCH_SIZE != 0:
            batch.commit()

        print(f"\n   {'[DRY RUN] Would delete' if DRY_RUN else '✅  Deleted'} "
              f"{count} flat submission(s).")

    # Confirm 2025 entries are intact
    entries = list(
        db.collection("submissions").document(KEEP_YEAR).collection("entries").stream()
    )
    print(f"\n   submissions/{KEEP_YEAR}/entries — {len(entries)} docs (untouched)")
    print()