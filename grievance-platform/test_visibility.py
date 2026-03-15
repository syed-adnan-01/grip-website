import requests
import time

BASE_URL = "http://localhost:5000"

def test_citizen_visibility():
    # 1. Register a new citizen
    user_id = int(time.time())
    citizen_user = f"citizen_{user_id}"
    print(f"Registering citizen: {citizen_user}")
    
    reg_data = {
        "username": citizen_user,
        "password": "password123",
        "fullname": "Test Citizen"
    }
    r = requests.post(f"{BASE_URL}/api/register", json=reg_data)
    if r.status_code != 200:
        print("Registration failed", r.json())
        return
    cookies = r.cookies

    # 2. Submit a complaint
    print("Submitting complaint...")
    complaint_data = {
        "title": "Visibility Test",
        "description": "Can you see me?",
        "category": "Road",
        "area": "Hebbal",
        "citizen_name": "Test Citizen",
        "citizen_contact": citizen_user
    }
    r = requests.post(f"{BASE_URL}/api/complaints", data=complaint_data, cookies=cookies)
    if r.status_code != 200:
        print("Submission failed", r.json())
        return
    complaint_id = r.json().get('complaint_id')
    print(f"Complaint submitted with ID: {complaint_id}")

    # 4. Submit a complaint with coordinates
    print("\nSubmitting complaint with coordinates...")
    complaint_data_geo = {
        "title": "Geo Visibility Test",
        "description": "Can you see me with coordinates?",
        "category": "Electricity",
        "area": "Indiranagar",
        "citizen_name": "Test Citizen",
        "citizen_contact": citizen_user,
        "latitude": "12.9784",
        "longitude": "77.6408"
    }
    r = requests.post(f"{BASE_URL}/api/complaints", data=complaint_data_geo, cookies=cookies)
    if r.status_code != 200:
        print("Geo submission failed", r.json())
        return
    geo_id = r.json().get('complaint_id')
    print(f"Geo complaint submitted with ID: {geo_id}")

    # 5. Fetch complaints again
    print("Fetching complaints for citizen again...")
    r = requests.get(f"{BASE_URL}/api/complaints?contact={citizen_user}", cookies=cookies)
    complaints = r.json()
    print(f"Total complaints found: {len(complaints)}")
    
    geo_found = any(c['id'] == geo_id for c in complaints)
    if geo_found:
        print("SUCCESS: Geo complaint is visible in citizen API.")
        # Check if coordinates are returned as numbers or strings
        c = [comp for comp in complaints if comp['id'] == geo_id][0]
        print(f"Latitude type in JSON: {type(c.get('latitude'))} value: {c.get('latitude')}")
    else:
        print("FAILURE: Geo complaint NOT found in citizen API.")

if __name__ == "__main__":
    test_citizen_visibility()

if __name__ == "__main__":
    test_citizen_visibility()
