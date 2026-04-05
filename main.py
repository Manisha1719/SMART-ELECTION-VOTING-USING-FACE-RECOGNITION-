from flask import Blueprint, render_template, session, redirect, request
from db import db
from util import *
import bcrypt

main = Blueprint('main', __name__)


def is_local_admin_request():
  host = request.host.lower() if request.host else ''
  remote = request.remote_addr
  return remote in ('127.0.0.1', '::1') and ('localhost' in host or host.startswith('127.0.0.1'))


@main.route('/')
def home():
  # Auto-init system if no admin exists
  if db.users.count_documents({'is_admin': True}) == 0:
    password = "admin"
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
      db.users.insert_one({
        '_id': 'admin',
        'name': 'Admin',
        'password': hashed,
        'is_admin': True,
        'voted': False
      })
    except Exception as e:
      print(f"Error initializing admin user: {e}")

  # No auto-login: always require credentials before entering the system.


  if session.get('status'):
    status = voting_status()

    # Prevent non-local sessions from retaining admin view.
    if session.get('is_admin') and not is_local_admin_request():
      session.clear()
      return redirect('/')

    if session.get('is_admin'):
      return render_template('admin.html', candidates=list(db.candidates.find()), voting_status=status)

    # Non-admin users should always get voter flow
    user = db.users.find_one({'_id': session.get('voter_id')})
    if not user:
      session.clear()
      return render_template('index.html')

    user_voted = user.get('voted', False)
    return render_template('user.html', name=session.get('name'), voting_status=status,
                           user_status=user_voted)

  return render_template('index.html')


@main.route('/login')
def login_page():
  return redirect('/')


@main.route('/logout', methods=['GET', 'POST'])
def logout():
  session.clear()
  return redirect('/')


@main.route('/vote')
def vote():
  status = session.get('status')
  if not status:
    return redirect('/')

  # Admin users should not use voter UI; send admin back to dashboard.
  if session.get('is_admin'):
    return redirect('/')

  status = voting_status()
  user = db.users.find_one({"_id": session.get('voter_id')})
  if not user:
    session.clear()
    return redirect('/')

  user_status = user.get('voted', False)
  candidates = list(db.candidates.find())
  return render_template(
      'vote.html',
      candidates=candidates,
      voting_status=status,
      user_status=user_status,
      is_admin=False
  )


@main.route('/results')
def results():
  if not session.get('status'):
    return redirect('/')

  status = voting_status()
  results = []

  if status == 'Stopped':
    candidates = list(db.candidates.find().sort('votes', -1))
    total_votes = db.users.count_documents({"voted": True})
    for c in candidates:
      c['percentage'] = round((c.get('votes', 0) / total_votes) * 100, 2) if total_votes > 0 else 0
    ordered = sorted(candidates, key=lambda x: x.get('votes', 0), reverse=True)
    results = [(ix, rs) for ix, rs in enumerate(ordered, 1)]
    max_votes = ordered[0].get('votes', 0) if ordered else 0
  else:
    total_votes = db.users.count_documents({"voted": True})
    max_votes = 0

  return render_template(
      'results.html',
      results={
          'results': results,
          'total_votes': total_votes,
          'max_votes': max_votes
      },
      voting_status=status
  )