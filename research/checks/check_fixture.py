import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

# Grab one fixture ID from our database
import sqlite3
conn = sqlite3.connect("oddspapi.db")
fixture_id = conn.execute(
    "SELECT fixture_id FROM fixtures WHERE priority = 1 LIMIT 1"
).fetchone()[0]
conn.close()

print(f"Checking fixture: {fixture_id}")

resp = requests.get(
    f"{BASE_URL}/fixture",
    params={
        "apiKey":    API_KEY,
        "fixtureId": fixture_id,
    }
)

print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2))