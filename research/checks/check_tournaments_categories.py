import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

# Check each sport we care about
TARGET_SPORTS = {
    11: ("basketball", "2026-04-01", "2026-04-10"),
    12: ("tennis",     "2026-04-01", "2026-04-10"),
    13: ("baseball",   "2026-04-01", "2026-04-10"),
    15: ("ice-hockey", "2026-04-01", "2026-04-10"),
    20: ("mma",        "2026-04-01", "2026-04-10"),
}

for sport_id, (sport_slug, date_from, date_to) in TARGET_SPORTS.items():
    resp = requests.get(
        f"{BASE_URL}/fixtures",
        params={
            "apiKey":  API_KEY,
            "sportId": sport_id,
            "from":    date_from,
            "to":      date_to,
        }
    )
    data = resp.json()
    if not isinstance(data, list):
        print(f"{sport_slug}: unexpected response - {data}")
        continue

    # Get unique tournament + category combinations
    combos = set()
    for f in data:
        tournament = f.get("tournamentName", "")
        category   = f.get("categoryName", "")
        combos.add((tournament, category))

    print(f"\n=== {sport_slug.upper()} ===")
    for tournament, category in sorted(combos):
        print(f"  {tournament} | {category}")

    import time
    time.sleep(2)