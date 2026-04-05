import os
from flask import Blueprint, request, send_from_directory, session
import face_recognition
from db import db
import cv2
import numpy as np
import base64
import bcrypt
import os
from util import *

api = Blueprint('api', __name__)


@api.route('/register', methods=['POST'])
def register():
  name = request.form.get('name')
  voter_id = request.form.get('voter_id')
  password = request.form.get('password')

  # Check if user already exists
  if db.users.find_one({"_id": voter_id}):
        return {"success": False, "message": "User already exists."}, 400

  # Get face image from uploaded file
  if 'face_image' not in request.files:
        return {"success": False, "message": "Face image is required."}, 400

  file = request.files['face_image']
  if file.filename == '':
        return {"success": False, "message": "No selected file."}, 400

  face_encoding = None
  try:
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
      return {"success": False, "message": "Invalid face image."}

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_loc = face_recognition.face_locations(img_rgb)
    if len(face_loc) == 0:
      return {"success": False, "message": "No face detected in the image."}
    if len(face_loc) > 1:
      return {"success": False, "message": "Multiple faces detected in the image."}

    face_encoding = face_recognition.face_encodings(img_rgb, face_loc)[0]
    # Convert to list for JSON serialization
    face_encoding = face_encoding.tolist()
  except Exception as e:
    print(f"Error processing face image: {e}")
    return {"success": False, "message": "Error processing face image"}

  password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
  user_data = {
      "_id": voter_id,
      "name": name,
      "password": password_hash,
      "face_encoding": face_encoding,
      "voted": False,
      "is_admin": False  # enforce voter role for all registrations
  }
  try:
    db.users.insert_one(user_data)
    return {"success": True, "message": "User registered successfully."}
  except Exception as e:
    print(f"Error registering user: {e}")
    return {"success": False, "message": "Error registering user"}


@api.route('/login', methods=['POST'])
def login():
  voter_id = request.form.get('voter_id')
  password = request.form.get('password')

  user = db.users.find_one({"_id": voter_id})

  if not user:
    return {"success": False, "message": "User not found."}

  if user.get('is_admin', False):
    # Admin login only allowed from local machine or tunneled environment.
    if request.remote_addr not in ('127.0.0.1', '::1') and 'localhost' not in request.host and 'devtunnels.ms' not in request.host:
      return {"success": False, "message": "Admin login is only allowed from local machine or trusted tunnel."}, 403

  if not bcrypt.checkpw(password.encode('utf-8'), user['password']):
    return {"success": False, "message": "Invalid password."}

  session['status'] = True
  session['voter_id'] = voter_id
  session['is_admin'] = user.get('is_admin', False)
  session['name'] = user.get('name')
  return {"success": True, "message": "Login successful.", "is_admin": user.get('is_admin', False)}


@api.route('/logo')
def logo():
  file = request.args.get('file', '').strip()
  try:
    # Ensure the filename is safe
    if '..' in file or file.startswith('/'):
      return {"success": False, "message": "Invalid filename"}, 400

    # fallback to favicon if logo not found
    filepath = os.path.join('static', file)
    if not os.path.exists(filepath) or not file:
      file = 'favicon.ico'

    return send_from_directory("static", file)

  except Exception as e:
    print(f"Error serving logo: {e}")
    return {"success": False, "message": "Error serving logo."}, 500


@api.route('/delete', methods=['POST'])
def delete_candidate():
  if not session.get('is_admin'):
    return {"success": False, "message": "Unauthorized access."}, 403

  data = request.get_json()
  candidate_logo = data.get('logo')

  if not candidate_logo:
    return {"success": False, "message": "Candidate logo is required."}, 400

  result = db.candidates.find_one({"logo": candidate_logo})
  if not result:
    return {"success": False, "message": "Candidate not found."}, 404

  candidate_id = result.get('_id')
  try:
    # Remove the logo file from the static directory
    if candidate_logo and os.path.exists(os.path.join("static", candidate_logo)):
      os.remove(os.path.join("static", candidate_logo))
    db.candidates.delete_one({"_id": candidate_id})
  except Exception as e:
    print(f"Error deleting candidate: {e}")
    return {"success": False, "message": "Error deleting candidate."}, 500
  return {"success": True, "message": "Candidate deleted successfully."}



@api.route('/init', methods=['POST'])
def init_system():
    # Creates an admin account + status placeholder automatically if missing.
    admin_user = db.users.find_one({"is_admin": True})
    if not admin_user:
        password = "admin"
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        try:
            db.users.insert_one({
                "_id": "admin",
                "name": "Admin",
                "password": hashed,
                "is_admin": True,
                "voted": False
            })
        except Exception as e:
            print(f"Error creating default admin: {e}")
            return {"success": False, "message": "Could not create default admin."}, 500

    status_doc = db.meta.find_one({"_id": "status"})
    if not status_doc:
        db.meta.update_one({"_id": "status"}, {"$set": {"value": "Not Started"}}, upsert=True)

    # Optional seeding for candidates
    seed_auto = False
    if request.is_json:
        seed_auto = request.json.get('seed_candidates', False)
    else:
        seed_auto = request.form.get('seed_candidates', 'false').lower() in ('1', 'true', 'yes')

    if seed_auto:
        default_candidates = [
            {"_id": "AAP", "logo": "favicon.ico", "votes": 0},
            {"_id": "BJP", "logo": "favicon.ico", "votes": 0},
            {"_id": "TRS", "logo": "favicon.ico", "votes": 0}
        ]
        for candidate in default_candidates:
            if not db.candidates.find_one({"_id": candidate['_id']}):
                db.candidates.insert_one(candidate)

    return {
        "success": True,
        "message": "System initialized",
        "admin": "admin",
        "password": "admin",
        "seeded_candidates": seed_auto
    }


@api.route('/add_candidate', methods=['POST'])
def add_candidate():
    if not session.get('is_admin'):
        return {"success": False, "message": "Unauthorized access."}, 403
    if 'logo' not in request.files:
        return {"success": False, "message": "No logo file uploaded"}, 400

    name = request.form.get('name').upper().strip()
    logo = request.files['logo']

    if not name or not logo.filename:
        return {"success": False, "message": "Missing name or logo"}, 400

    if db.candidates.find_one({"_id": name}):
        return {"success": False, "message": "Candidate already exists"}, 400

    # Save image with unique name
    ext = os.path.splitext(logo.filename)[1]
    filename = f"{name}{ext}"  # e.g., "JOHN_DOE.png"
    logo.save(os.path.join("static", filename))

    db.candidates.insert_one({
        "_id": name,
        "logo": filename,
        "votes": 0,
    })

    return {
        "success": True,
        "message": "Candidate added successfully!"
    }

@api.route('/start_voting', methods=['POST'])
def start_voting():
    if not session.get('is_admin'):
        return {"success": False, "message": "Unauthorized access."}, 403

    # Check if voting is already running
    if db.meta.find_one({"_id": "status", "value": "Running"}):
        return {"success": False, "message": "Voting is already in progress."}, 400
    # Start the voting process
    db.meta.update_one({"_id": "status"}, {"$set": {"value": "Running"}}, upsert=True)
    return {"success": True, "message": "Voting started successfully."}


@api.route('/stop_voting', methods=['POST'])
def stop_voting():
    if not session.get('is_admin'):
        return {"success": False, "message": "Unauthorized access."}, 403

    # Check if voting is already stopped
    if db.meta.find_one({"_id": "status", "value": "Stopped"}):
        return {"success": False, "message": "Voting is already stopped."}, 400

    # Stop the voting process
    db.meta.update_one({"_id": "status"}, {"$set": {"value": "Stopped"}}, upsert=True)
    return {"success": True, "message": "Voting stopped successfully."}

@api.route('/reset_voting', methods=['POST'])
def reset_voting():
    if not session.get('is_admin'):
        return {"success": False, "message": "Unauthorized access."}, 403

    # Check if voting is already stopped
    if db.meta.find_one({"_id": "status", "value": "Not Started"}):
        return {"success": False, "message": "Voting is not started yet."}, 400

    # Reset the voting process
    db.meta.update_one({"_id": "status"}, {"$set": {"value": "Not Started"}}, upsert=True)
    db.users.update_many({}, {"$set": {"voted": False}})
    db.candidates.update_many({}, {"$set": {"votes": 0}})
    return {"success": True, "message": "Voting reset successfully."}
  

@api.route('/verify_face', methods=['POST'])
def verify_face():
  status = session.get('status')
  if not status:
    return {"success": False, "message": "User not logged in."}, 401
  if 'face_image' not in request.files:
    return {"success": False, "message": "No face image provided."}, 400

  face_image = request.files['face_image']
  voter_id = session.get('voter_id')
  
  user = db.users.find_one({"_id": voter_id})

  if not user:
    return {"success": False, "message": "User not found."}, 404

  try:
    # Read image from uploaded file
    img_bytes = face_image.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"success": False, "message": "Invalid face image."}, 400

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    face_loc = face_recognition.face_locations(img_rgb)

    if len(face_loc) == 0:
        return {"success": False, "message": "No face detected in the image."}, 400
    if len(face_loc) > 1:
        return {"success": False, "message": "Multiple faces detected in the image."}, 400

    face_encoding = face_recognition.face_encodings(
        img_rgb, face_loc)[0]  # still a numpy array here ✅

    if voting_status() != "Running":
        return {"success": False, "message": "Voting is not currently running."}, 403
    if user.get('voted'):
        return {"success": False, "message": "You have already voted."}, 403

    stored_data = db.users.find_one({"_id": session.get('voter_id')})
    stored_encoding = stored_data.get(
        'face_encoding')  # should be a list from DB

    # Convert stored_encoding (list) back to numpy array
    stored_encoding_np = np.array(stored_encoding)  # ✅ convert to numpy array

    # face_encoding is already a numpy array from face_recognition
    match = face_recognition.compare_faces(
        [stored_encoding_np], face_encoding, tolerance=0.6)

    if match[0]:
        return {"success": True, "message": "Face verified successfully."}
    else:
        return {"success": False, "message": "Face verification failed."}, 401


  except Exception as e:
      print(f"Error verifying face: {e}")
      return {"success": False, "message": "Error verifying face."}, 500


@api.route('/vote', methods=['POST'])
def vote():
  status = session.get('status')
  if not status:
    return {"success": False, "message": "User not logged in."}, 401
  if session.get('is_admin'):
    return {"success": False, "message": "Admins cannot vote."}, 403
  if voting_status() != "Running":
    return {"success": False, "message": "Voting is not currently running."}, 403

  voter_id = session.get('voter_id')
  candidate = request.get_json().get('candidate_id')

  if not candidate:
    return {"success": False, "message": "Candidate is required."}, 400

  voter = db.users.find_one({"_id": voter_id})
  if not voter:
    session.clear()
    return {"success": False, "message": "Voter session expired."}, 401

  if voter.get('voted', False):
    return {"success": False, "message": "You have already voted."}, 403

  candidate_doc = db.candidates.find_one({"_id": candidate})
  if not candidate_doc:
    return {"success": False, "message": "Invalid candidate selected."}, 400

  # Cast vote atomically.
  db.users.update_one({"_id": voter_id}, {"$set": {"voted": True}})
  db.candidates.update_one({"_id": candidate}, {"$inc": {"votes": 1}})

  return {"success": True, "message": "Vote cast successfully."}
