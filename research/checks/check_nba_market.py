import requests
import sqlite3
import os
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

conn = sqlite3.connect("oddspapi.db")

# Get several NBA games and test each one
rows = conn.execute("""
    SELECT fixture_id, home_team, away_team
    FROM fixtures
    WHERE sport_id = 11
    AND priority = 1
    AND (
        home_team LIKE '%Lakers%'
        OR home_team LIKE '%Celtics%'
        OR home_team LIKE '%Warriors%'
        OR home_team LIKE '%Knicks%'
        OR home_team LIKE '%Bulls%'
        OR away_team LIKE '%Lakers%'
        OR away_team LIKE '%Celtics%'
    )
    LIMIT 5
""").fetchall()

conn.close()

print(f"Testing {len(rows)} NBA fixtures with Pinnacle market 111\n")

for fixture_id, home, away in rows:
    resp = requests.get(
        f"{BASE_URL}/historical-odds",
        params={
            "apiKey":     API_KEY,
            "fixtureId":  fixture_id,
            "bookmakers": "pinnacle",
        }
    )

    data = resp.json()
    found = False
    row_count = 0
    all_markets = []

    if data and "bookmakers" in data:
        pinnacle = data["bookmakers"].get("pinnacle", {})
        markets  = pinnacle.get("markets", {})
        all_markets = list(markets.keys())

        if "111" in markets:
            found = True
            outcomes = markets["111"].get("outcomes", {})
            for outcome_id, outcome_data in outcomes.items():
                players = outcome_data.get("players", {})
                for player_id, entries in players.items():
                    if isinstance(entries, list):
                        row_count += len(entries)

    status = "OK" if found else "MISSING"
    print(f"{status} | {home} vs {away}")
    if not found:
        print(f"  Markets available: {all_markets[:10]}")
    else:
        print(f"  Rows: {row_count}")
    print()
    time.sleep(6)