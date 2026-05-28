import requests
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

resp = requests.get(
    f"{BASE_URL}/fixtures",
    params={
        "apiKey":  API_KEY,
        "sportId": 10,
        "from":    "2026-04-01",
        "to":      "2026-04-10",
    }
)

data = resp.json()

combos = set()
for f in data:
    tournament = f.get("tournamentName", "")
    category   = f.get("categoryName", "")
    combos.add((tournament, category))

print(f"=== SOCCER ===")
for tournament, category in sorted(combos):
    print(f"  {tournament} | {category}")