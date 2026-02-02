
import os
import requests
import json

# Setup
SUPABASE_URL = "https://zlkhsxacfyxsctqpvbsh.supabase.co"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpsa2hzeGFjZnl4c2N0cXB2YnNoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEyMDE5ODksImV4cCI6MjA3Njc3Nzk4OX0.5-3lCx69vAPUARZNVlk_WMl4Gz0PDZvUg7OXp0zEvm8"
HEADERS = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# Payload
payload = {
    "cabinet_id": "6d64c3d9-5797-46bd-a5d9-b68ab887a0a4",
    "name": "Street Fighter Cab (Basement)",
    "location": "Basement",
    "status": "online",
    "mac_address": "50-ED-3C-36-DD-45"
}

# Execution
print(f"Registering cabinet: {payload['name']} ({payload['cabinet_id']})...")
try:
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/cabinet",
        headers=HEADERS,
        json=payload
    )
    
    if response.status_code in [200, 201, 204]:
        print("✅ SUCCESS: Cabinet registered.")
    else:
        print(f"❌ FAILED: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"❌ EXCEPTION: {e}")
