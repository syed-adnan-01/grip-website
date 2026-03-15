import requests
import os
import time

BASE_URL = "http://localhost:5000"

def test_flow():
    # Attempt to ping first to see if server is up
    try:
        r = requests.get(f"{BASE_URL}/api/ping")
        print("Server Ping:", r.json())
    except Exception as e:
        print("Server is not running. Please start the app first.")
        return

    # 1. Register a new citizen
    print("\n1. Registering Citizen...")
    citizen_user = f"test_{int(time.time())}"
    reg_data = {
        "username": citizen_user,
        "password": "password123",
        "fullname": "Test User"
    }
    r = requests.post(f"{BASE_URL}/api/register", json=reg_data)
    print("Registration Response:", r.status_code, r.json())
    if r.status_code != 200: return

    citizen_cookies = r.cookies

    # 2. Login as the same citizen
    print("\n2. Logging in as Citizen...")
    login_data = {
        "username": citizen_user,
        "password": "password123"
    }
    r = requests.post(f"{BASE_URL}/api/login", json=login_data)
    print("Login Response:", r.status_code, r.json())
    if r.status_code != 200: return
    
    citizen_cookies = r.cookies

    # 3. Submit a complaint as citizen
    print("\n3. Submitting Complaint...")
    complaint_data = {
        "title": "Broken Street Light",
        "description": "The light at the corner of 5th and Main is dim and flickering.",
        "category": "Electricity",
        "area": "Whitefield",
        "citizen_name": "Test User",
        "citizen_contact": citizen_user
    }
    r = requests.post(f"{BASE_URL}/api/complaints", data=complaint_data, cookies=citizen_cookies)
    print("Complaint Submission Response:", r.status_code, r.json())
    if r.status_code != 200: return
    complaint_id = r.json().get('complaint_id')

    # 4. Login as Admin
    print("\n4. Logging in as Admin...")
    admin_data = {
        "username": "admin",
        "password": "admin123"
    }
    r = requests.post(f"{BASE_URL}/api/login", json=admin_data)
    print("Admin Login Response:", r.status_code, r.json())
    if r.status_code != 200: return
    admin_cookies = r.cookies

    # 5. Check Dashboard (Admin view)
    print("\n5. Checking Admin Dashboard...")
    r = requests.get(f"{BASE_URL}/api/complaints", cookies=admin_cookies)
    print("Admin Fetch Complaints Status:", r.status_code)
    complaints = r.json()
    found = any(c['id'] == complaint_id for c in complaints)
    print(f"Complaint {complaint_id} found in Admin Dashboard: {found}")

if __name__ == "__main__":
    test_flow()
