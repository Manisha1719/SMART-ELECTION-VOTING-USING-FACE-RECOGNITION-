import warnings
warnings.filterwarnings("ignore", category=UserWarning)

from db import db


def voting_status():
    status_doc = db.meta.find_one({"_id": "status"})
    if not status_doc:
        # Initialize default status in DB to avoid server errors when collection is empty
        db.meta.update_one({"_id": "status"}, {"$set": {"value": "Not Started"}}, upsert=True)
        return "Not Started"
    return status_doc.get('value', 'Not Started')