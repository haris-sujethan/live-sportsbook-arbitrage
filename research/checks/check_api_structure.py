import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

resp = requests.get(
    f"{BASE_URL}/fixtures",
    params={
        "apiKey":  API_KEY,
        "sportId": 11,
        "from":    "2026-05-01",
        "to":      "2026-05-05",
    }
)

data = resp.json()
print(f"Status: {resp.status_code}")
print(f"Fixtures returned: {len(data)}")
print()
print("First fixture full structure:")
print(json.dumps(data[0], indent=2))
print()
print("Second fixture full structure:")
print(json.dumps(data[1], indent=2))