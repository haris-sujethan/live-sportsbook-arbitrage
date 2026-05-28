import requests
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

# Pull just 2 days of NBA data
resp = requests.get(
    f"{BASE_URL}/fixtures",
    params={
        "apiKey":  API_KEY,
        "sportId": 11,
        "from":    "2026-04-01",
        "to":      "2026-04-03",
    }
)

data = resp.json()
print(f"Returned: {len(data)} fixtures")
print()

# Verify every field we need is present and correct
for f in data[:5]:
    print(f"fixture_id      : {f.get('fixtureId')}")
    print(f"tournament_name : {f.get('tournamentName')}")
    print(f"category_name   : {f.get('categoryName')}")
    print(f"home_team       : {f.get('participant1Name')}")
    print(f"away_team       : {f.get('participant2Name')}")
    print(f"start_time      : {f.get('startTime')}")
    print(f"status_id       : {f.get('statusId')}")
    print()