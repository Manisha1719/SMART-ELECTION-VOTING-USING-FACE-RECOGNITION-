from db import db
import bcrypt

admin_data = {
    "_id": "admin",
    "name": "Admin",
    "password": bcrypt.hashpw("admin".encode('utf-8'), bcrypt.gensalt()),
    "is_admin": True
}

try:
  db.users.insert_one(admin_data)
  print("Admin user created successfully.")
except Exception as e:
  print(f"Error creating admin user: {e}")
