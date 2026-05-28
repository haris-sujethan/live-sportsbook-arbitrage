import requests
import sqlite3
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

conn = sqlite3.connect("oddspapi.db")

# Get one status 3 fixture from each sport
sports = [10, 11, 12, 13, 15, 20]

for sport_id in sports:
    row = conn.execute("""
        SELECT fixture_id, sport_slug, tournament_name, home_team, away_team
        FROM fixtures
        WHERE sport_id = ?
        AND status_id = 3
        LIMIT 1
    """, (sport_id,)).fetchone()

    if not row:
        continue

    fixture_id, sport_slug, tournament, home, away = row

    resp = requests.get(
        f"{BASE_URL}/fixture",
        params={"apiKey": API_KEY, "fixtureId": fixture_id}
    )

    data = resp.json()
    print(f"Sport     : {sport_slug}")
    print(f"Game      : {home} vs {away}")
    print(f"Tournament: {tournament}")
    print(f"statusId  : {data.get('statusId')}")
    print(f"statusName: {data.get('statusName')}")
    print()

conn.close()