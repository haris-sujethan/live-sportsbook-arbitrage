import requests
import sqlite3
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY   = os.getenv("ODDSPAPI_KEY")
BASE_URL  = "https://api.oddspapi.io/v4"
DB_PATH   = "oddspapi.db"
CHUNK_DAYS = 9

TARGET_SPORTS = {
    10: "soccer",
    11: "basketball",
    12: "tennis",
    13: "baseball",
    15: "ice-hockey",
    20: "mma",
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id      TEXT PRIMARY KEY,
            sport_id        INTEGER,
            sport_slug      TEXT,
            tournament_id   INTEGER,
            tournament_name TEXT,
            category_name   TEXT,
            home_team       TEXT,
            away_team       TEXT,
            start_time      TEXT,
            status_id       INTEGER,
            priority        INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn

def date_chunks(date_from, date_to, chunk_days):
    chunks = []
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end   = datetime.strptime(date_to,   "%Y-%m-%d")
    while start < end:
        chunk_end = min(start + timedelta(days=chunk_days), end)
        chunks.append((
            start.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d")
        ))
        start = chunk_end + timedelta(days=1)
    return chunks

def fetch_chunk(sport_id, sport_slug, date_from, date_to):
    resp = requests.get(
        f"{BASE_URL}/fixtures",
        params={
            "apiKey":  API_KEY,
            "sportId": sport_id,
            "from":    date_from,
            "to":      date_to,
        }
    )

    if resp.status_code == 429:
        wait = 6.0
        try:
            msg  = resp.json().get("error", {}).get("details", "")
            wait = float(msg.split("wait ")[-1].split(" ")[0]) + 1
        except:
            pass
        print(f"    Rate limited - waiting {wait:.1f}s")
        time.sleep(wait)
        return fetch_chunk(sport_id, sport_slug, date_from, date_to)

    if resp.status_code == 404:
        return []

    if resp.status_code != 200:
        print(f"    Error {resp.status_code}: {resp.text[:150]}")
        return []

    data = resp.json()
    if isinstance(data, list):
        return data
    return []

def save_fixtures(conn, fixtures, sport_id, sport_slug):
    saved = 0
    for f in fixtures:
        try:
            fixture_id = f.get("fixtureId")
            if not fixture_id:
                continue

            conn.execute("""
                INSERT OR IGNORE INTO fixtures
                (fixture_id, sport_id, sport_slug, tournament_id,
                 tournament_name, category_name, home_team, away_team,
                 start_time, status_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(fixture_id),
                sport_id,
                sport_slug,
                f.get("tournamentId"),
                f.get("tournamentName")   or "",
                f.get("categoryName")     or "",
                f.get("participant1Name") or "",
                f.get("participant2Name") or "",
                f.get("startTime")        or "",
                f.get("statusId")         or 0,
            ))
            saved += 1
        except Exception as e:
            print(f"    Row error: {e}")
    conn.commit()
    return saved

def main():
    conn = init_db()

    date_to   = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    chunks    = date_chunks(date_from, date_to, CHUNK_DAYS)

    print(f"Date range      : {date_from} to {date_to}")
    print(f"Chunks per sport: {len(chunks)}")
    print(f"Total requests  : {len(TARGET_SPORTS) * len(chunks)}")
    print()

    total_requests = 0
    total_fixtures = 0

    for sport_id, sport_slug in TARGET_SPORTS.items():
        print(f"-- {sport_slug} (sportId={sport_id})")
        sport_total = 0

        for chunk_from, chunk_to in chunks:
            fixtures = fetch_chunk(sport_id, sport_slug, chunk_from, chunk_to)
            total_requests += 1
            saved = save_fixtures(conn, fixtures, sport_id, sport_slug)
            sport_total += saved
            print(f"   {chunk_from} to {chunk_to} : {len(fixtures)} returned, {saved} saved")
            time.sleep(2)

        total_fixtures += sport_total
        print(f"   Subtotal: {sport_total} fixtures")
        print()

    conn.close()

    print("=" * 50)
    print(f"Requests used  : {total_requests}")
    print(f"Fixtures saved : {total_fixtures}")
    print("=" * 50)

if __name__ == "__main__":
    main()