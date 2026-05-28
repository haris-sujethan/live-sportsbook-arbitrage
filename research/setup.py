import requests
import sqlite3
import json
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"
DB_PATH = "oddspapi.db"

ONTARIO_BOOKS = [
    "pinnacle", "bet365", "draftkings", "fanduel", "betmgm",
    "caesars", "betrivers", "betway", "thescore", "sportsinteraction",
    "bet99", "betano.ca", "888sport.ca", "bwin", "pokerstars",
    "tonybet", "unibet", "powerplay", "ballybet", "leovegas", "fanatics"
]

# Sports we care about
TARGET_SPORTS = {
    "soccer": None,
    "basketball": None,
    "tennis": None,
    "baseball": None,
    "hockey": None,
    "americanfootball": None,
    "mma": None,
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sports (
            sport_id INTEGER PRIMARY KEY,
            slug TEXT,
            name TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id TEXT PRIMARY KEY,
            sport_id INTEGER,
            sport_slug TEXT,
            tournament_id INTEGER,
            tournament_name TEXT,
            home_team TEXT,
            away_team TEXT,
            start_time TEXT,
            status_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id TEXT,
            bookmaker TEXT,
            market_id TEXT,
            outcome_id TEXT,
            price REAL,
            timestamp TEXT,
            active INTEGER
        )
    """)
    conn.commit()
    return conn

def get_sports():
    print("Fetching sports list... (1 request)")
    resp = requests.get(f"{BASE_URL}/sports", params={"apiKey": API_KEY})
    sports = resp.json()
    print(f"Total sports returned: {len(sports)}")
    for s in sports:
        print(json.dumps(s, indent=2))
    return sports

def main():
    conn = init_db()
    print("Database initialized.")
    sports = get_sports()
    
    # Save sports to DB
    for s in sports:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO sports (sport_id, slug, name) VALUES (?, ?, ?)",
                (s.get("id") or s.get("sportId"), 
                 s.get("slug") or s.get("sportSlug"),
                 s.get("name") or s.get("sportName"))
            )
        except Exception as e:
            print(f"Error saving sport: {e}, data: {s}")
    conn.commit()
    print("Sports saved to database.")

if __name__ == "__main__":
    main()