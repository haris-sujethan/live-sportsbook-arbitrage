import requests
import sqlite3
import os
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY     = os.getenv("ODDSPAPI_KEY")
BASE_URL    = "https://api.oddspapi.io/v4"
FIXTURES_DB = "oddspapi.db"
ODDS_DB     = "odds_history.db"

# 7 Ontario soft books in chunks of 3 (API max per call)
SOFT_BOOKS = [
    "bet365",
    "betmgm",
    "888sport.ca",
    "betway",
    "draftkings",
    "fanduel",
    "thescore",
]

BOOK_CHUNKS = [
    SOFT_BOOKS[i:i+3]
    for i in range(0, len(SOFT_BOOKS), 3)
]

RATE_LIMIT_SECONDS = 5.5

MONEYLINE_MARKET_IDS = {
    10: "101",   # Soccer - Full Time Result
    11: "111",   # Basketball - Winner incl. overtime
    12: "121",   # Tennis - Winner
    13: "131",   # Baseball - Winner incl. extra innings
    15: "151",   # Ice Hockey - Winner incl. overtime and penalties
    20: "201",   # MMA - Winner
}


def init_odds_db():
    conn = sqlite3.connect(ODDS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS odds_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id    TEXT    NOT NULL,
            sport_id      INTEGER,
            sport_slug    TEXT,
            tournament    TEXT,
            category      TEXT,
            home_team     TEXT,
            away_team     TEXT,
            start_time    TEXT,
            bookmaker     TEXT    NOT NULL,
            market_id     TEXT,
            outcome_id    TEXT,
            price         REAL,
            timestamp     TEXT,
            active        INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fetch_log (
            fixture_id  TEXT NOT NULL,
            bookmaker   TEXT NOT NULL,
            fetched_at  TEXT,
            rows_saved  INTEGER,
            status      TEXT,
            PRIMARY KEY (fixture_id, bookmaker)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fixture   ON odds_history(fixture_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmaker ON odds_history(bookmaker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sport     ON odds_history(sport_slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON odds_history(timestamp)")
    conn.commit()
    return conn


def get_tennis_fixtures():
    conn = sqlite3.connect(FIXTURES_DB)
    rows = conn.execute("""
        SELECT fixture_id, sport_id, sport_slug,
               tournament_name, category_name,
               home_team, away_team, start_time
        FROM fixtures
        WHERE priority = 1
        AND sport_id = 12
        ORDER BY start_time
    """).fetchall()
    conn.close()
    print(f"Tennis fixtures   : {len(rows)}")
    return rows


def already_fetched(odds_conn, fixture_id, bookmaker):
    row = odds_conn.execute("""
        SELECT fixture_id FROM fetch_log
        WHERE fixture_id = ?
        AND bookmaker = ?
        AND status IN ('ok', 'empty')
    """, (fixture_id, bookmaker)).fetchone()
    return row is not None


def fetch_historical(fixture_id, bookmakers_str):
    resp = requests.get(
        f"{BASE_URL}/historical-odds",
        params={
            "apiKey":     API_KEY,
            "fixtureId":  fixture_id,
            "bookmakers": bookmakers_str,
        }
    )

    if resp.status_code == 429:
        wait = 6.0
        try:
            msg  = resp.json().get("error", {}).get("details", "")
            wait = float(msg.split("wait ")[-1].split(" ")[0]) + 1
        except:
            pass
        print(f"      Rate limited -- waiting {wait:.1f}s")
        time.sleep(wait)
        return fetch_historical(fixture_id, bookmakers_str)

    if resp.status_code == 304:
        return {}

    if resp.status_code != 200:
        return None

    return resp.json()


def parse_and_save(odds_conn, data, fixture_meta, target_books):
    fixture_id, sport_id, sport_slug, \
    tournament, category, home, away, start_time = fixture_meta

    if not data or "bookmakers" not in data:
        return {}

    moneyline_id = str(MONEYLINE_MARKET_IDS.get(sport_id, ""))
    if not moneyline_id:
        return {}

    rows_per_book = {book: 0 for book in target_books}
    bookmakers    = data["bookmakers"]

    for book_slug, book_data in bookmakers.items():

        if book_slug not in target_books:
            continue

        markets = book_data.get("markets", {})

        for market_id, market_data in markets.items():

            if market_id != moneyline_id:
                continue

            outcomes = market_data.get("outcomes", {})
            for outcome_id, outcome_data in outcomes.items():
                players = outcome_data.get("players", {})
                for player_id, entries in players.items():
                    if not isinstance(entries, list):
                        entries = [entries]
                    for entry in entries:
                        price     = entry.get("price")
                        timestamp = entry.get("createdAt")
                        active    = 1 if entry.get("active") else 0

                        if price is None or timestamp is None:
                            continue
                        if price < 1.01 or price > 50.0:
                            continue

                        odds_conn.execute("""
                            INSERT INTO odds_history
                            (fixture_id, sport_id, sport_slug,
                             tournament, category, home_team, away_team,
                             start_time, bookmaker, market_id,
                             outcome_id, price, timestamp, active)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            fixture_id, sport_id, sport_slug,
                            tournament, category, home, away,
                            start_time, book_slug, market_id,
                            outcome_id, price, timestamp, active
                        ))
                        rows_per_book[book_slug] += 1

    odds_conn.commit()
    return rows_per_book


def log_fetch(odds_conn, fixture_id, bookmaker, rows_saved, status):
    odds_conn.execute("""
        INSERT OR REPLACE INTO fetch_log
        (fixture_id, bookmaker, fetched_at, rows_saved, status)
        VALUES (?, ?, datetime('now'), ?, ?)
    """, (fixture_id, bookmaker, rows_saved, status))
    odds_conn.commit()


def main():
    odds_conn = init_odds_db()
    print(f"Odds database     : {ODDS_DB}")
    print(f"Sport             : Tennis only (sport_id=12)")
    print(f"Books             : {SOFT_BOOKS}")
    print(f"Chunks            : {BOOK_CHUNKS}")
    print(f"Rate limit        : {RATE_LIMIT_SECONDS}s between calls")
    print()

    fixtures = get_tennis_fixtures()
    total    = len(fixtures)

    # Count how many still need fetching
    odds_conn2 = sqlite3.connect(ODDS_DB)
    remaining = sum(
        1 for f in fixtures
        if any(
            not already_fetched(odds_conn2, f[0], book)
            for book in SOFT_BOOKS
        )
    )
    odds_conn2.close()
    print(f"Fixtures remaining: {remaining}/{total}")
    print()

    processed  = 0
    skipped    = 0
    total_rows = 0
    empty      = 0
    errors     = 0

    for i, fixture_meta in enumerate(fixtures):
        fixture_id = fixture_meta[0]
        home       = fixture_meta[5]
        away       = fixture_meta[6]

        fixture_rows = 0
        fixture_skipped = 0

        for chunk in BOOK_CHUNKS:
            # Only fetch books in this chunk that haven't been fetched yet
            books_to_fetch = [
                b for b in chunk
                if not already_fetched(odds_conn, fixture_id, b)
            ]

            if not books_to_fetch:
                fixture_skipped += len(chunk)
                continue

            bookmakers_str = ",".join(books_to_fetch)
            data = fetch_historical(fixture_id, bookmakers_str)
            time.sleep(RATE_LIMIT_SECONDS)

            if data is None:
                errors += len(books_to_fetch)
                for book in books_to_fetch:
                    log_fetch(odds_conn, fixture_id, book, 0, "error")
                continue

            rows_per_book = parse_and_save(
                odds_conn, data, fixture_meta, books_to_fetch
            )

            for book, rows in rows_per_book.items():
                fixture_rows += rows
                if rows == 0:
                    empty += 1
                    log_fetch(odds_conn, fixture_id, book, 0, "empty")
                else:
                    log_fetch(odds_conn, fixture_id, book, rows, "ok")

        if fixture_skipped == len(SOFT_BOOKS):
            skipped += 1
            continue

        total_rows += fixture_rows
        processed  += 1

        if processed % 25 == 0 or processed == 1:
            pct = (i + 1) / total * 100
            print(
                f"[{i+1}/{total}] {pct:.1f}% | "
                f"{home} vs {away} | "
                f"rows this fixture: {fixture_rows} | "
                f"total: {total_rows:,}"
            )

    odds_conn.close()

    print()
    print("=" * 50)
    print(f"Processed : {processed}")
    print(f"Skipped   : {skipped} (all books already fetched)")
    print(f"Empty     : {empty} (book had no data)")
    print(f"Errors    : {errors}")
    print(f"Total rows: {total_rows:,}")
    print("=" * 50)


if __name__ == "__main__":
    main()