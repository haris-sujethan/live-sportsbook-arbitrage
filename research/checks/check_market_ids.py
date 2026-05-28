import requests
import sqlite3
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

conn = sqlite3.connect("oddspapi.db")

sports = {
    10: "soccer",
    11: "basketball",
    12: "tennis",
    13: "baseball",
    15: "ice-hockey",
    20: "mma",
}

for sport_id, sport_slug in sports.items():
    row = conn.execute("""
        SELECT fixture_id, home_team, away_team, tournament_name
        FROM fixtures
        WHERE sport_id = ?
        AND priority = 1
        LIMIT 1
    """, (sport_id,)).fetchone()

    if not row:
        print(f"\n{sport_slug}: no priority fixtures found")
        continue

    fixture_id, home, away, tournament = row

    print(f"\n{'='*60}")
    print(f"Sport      : {sport_slug}")
    print(f"Game       : {home} vs {away}")
    print(f"Tournament : {tournament}")
    print(f"Fixture ID : {fixture_id}")

    resp = requests.get(
        f"{BASE_URL}/historical-odds",
        params={
            "apiKey":     API_KEY,
            "fixtureId":  fixture_id,
            "bookmakers": "pinnacle",
        }
    )

    if resp.status_code != 200:
        print(f"Error: {resp.status_code} - {resp.text[:100]}")
        continue

    data = resp.json()

    if not data or "bookmakers" not in data:
        print("No data returned - Pinnacle had no odds on this fixture")
        continue

    pinnacle = data["bookmakers"].get("pinnacle", {})
    markets  = pinnacle.get("markets", {})

    if not markets:
        print("No markets found for Pinnacle on this fixture")
        continue

    print(f"Markets found: {len(markets)}")
    for market_id, market_data in markets.items():
        outcomes  = market_data.get("outcomes", {})
        num_outcomes = len(outcomes)

        # Get a sample price to help identify the market
        sample_prices = []
        for outcome_id, outcome_data in outcomes.items():
            players = outcome_data.get("players", {})
            for player_id, entries in players.items():
                if isinstance(entries, list) and entries:
                    price = entries[-1].get("price")
                    if price:
                        sample_prices.append(price)
                elif isinstance(entries, dict):
                    price = entries.get("price")
                    if price:
                        sample_prices.append(price)

        print(f"  market_id: {market_id} | outcomes: {num_outcomes} | sample prices: {sample_prices[:3]}")

    import time
    time.sleep(6)

conn.close()