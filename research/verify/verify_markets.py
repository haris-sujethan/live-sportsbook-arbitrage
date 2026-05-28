import requests
import sqlite3
import os
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

MONEYLINE_MARKET_IDS = {
    10: "101",
    11: "111",
    12: "121",
    13: "131",
    15: "151",
    20: "201",
}

conn = sqlite3.connect("oddspapi.db")

sports = {10: "soccer", 11: "basketball", 12: "tennis", 13: "baseball", 15: "ice-hockey", 20: "mma"}

for sport_id, sport_slug in sports.items():
    row = conn.execute("""
        SELECT fixture_id, home_team, away_team
        FROM fixtures
        WHERE sport_id = ?
        AND priority = 1
        LIMIT 1
    """, (sport_id,)).fetchone()

    if not row:
        continue

    fixture_id, home, away = row
    moneyline_id = MONEYLINE_MARKET_IDS[sport_id]

    resp = requests.get(
        f"{BASE_URL}/historical-odds",
        params={
            "apiKey":     API_KEY,
            "fixtureId":  fixture_id,
            "bookmakers": "pinnacle",
        }
    )

    data = resp.json()
    found_moneyline = False
    rows_would_save = 0

    if data and "bookmakers" in data:
        pinnacle = data["bookmakers"].get("pinnacle", {})
        markets  = pinnacle.get("markets", {})
        if moneyline_id in markets:
            found_moneyline = True
            outcomes = markets[moneyline_id].get("outcomes", {})
            for outcome_id, outcome_data in outcomes.items():
                players = outcome_data.get("players", {})
                for player_id, entries in players.items():
                    if isinstance(entries, list):
                        rows_would_save += len(entries)

    status = "OK" if found_moneyline else "NO MONEYLINE DATA"
    print(f"{status} | {sport_slug} | {home} vs {away} | market {moneyline_id} | rows: {rows_would_save}")
    time.sleep(6)

conn.close()