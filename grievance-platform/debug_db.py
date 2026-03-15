import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_FILE = 'grievance.db'

def check():
    if not os.path.exists(DB_FILE):
        print(f"DB file {DB_FILE} not found!")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("--- Users ---")
    cursor.execute("SELECT id, username, role, fullname FROM users")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Complaints ---")
    cursor.execute("SELECT id, title, citizen_name, citizen_contact, status FROM complaints")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()

if __name__ == "__main__":
    check()
