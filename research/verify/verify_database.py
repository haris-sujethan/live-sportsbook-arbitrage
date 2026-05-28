import sqlite3

conn = sqlite3.connect("oddspapi.db")

print("=" * 60)
print("1. OVERALL SUMMARY")
print("=" * 60)

total = conn.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0]
print(f"Total fixtures in DB: {total:,}")
print()

rows = conn.execute("""
    SELECT sport_slug, COUNT(*) as cnt
    FROM fixtures
    GROUP BY sport_slug
    ORDER BY cnt DESC
""").fetchall()
for sport, cnt in rows:
    print(f"  {sport:<20} {cnt:>8,} fixtures")

print()
print("=" * 60)
print("2. TEAM NAME POPULATION CHECK")
print("=" * 60)

blank = conn.execute("""
    SELECT sport_slug, COUNT(*) as cnt
    FROM fixtures
    WHERE home_team = '' OR away_team = ''
    OR home_team IS NULL OR away_team IS NULL
    GROUP BY sport_slug
""").fetchall()

if blank:
    print("WARNING - fixtures with missing team names:")
    for sport, cnt in blank:
        print(f"  {sport:<20} {cnt:>8,} blank")
else:
    print("OK - all fixtures have team names")

print()
print("=" * 60)
print("3. CATEGORY NAME CHECK")
print("=" * 60)

blank_cat = conn.execute("""
    SELECT sport_slug, COUNT(*) as cnt
    FROM fixtures
    WHERE category_name = '' OR category_name IS NULL
    GROUP BY sport_slug
""").fetchall()

if blank_cat:
    print("WARNING - fixtures with missing category:")
    for sport, cnt in blank_cat:
        print(f"  {sport:<20} {cnt:>8,} blank")
else:
    print("OK - all fixtures have category names")

print()
print("=" * 60)
print("4. SAMPLE ROWS PER SPORT")
print("=" * 60)

sports = ["soccer", "basketball", "tennis", "baseball", "ice-hockey", "mma"]

for sport in sports:
    print(f"\n-- {sport.upper()}")
    rows = conn.execute("""
        SELECT fixture_id, tournament_name, category_name,
               home_team, away_team, start_time, status_id
        FROM fixtures
        WHERE sport_slug = ?
        ORDER BY start_time DESC
        LIMIT 3
    """, (sport,)).fetchall()
    for r in rows:
        print(f"  ID          : {r[0]}")
        print(f"  Tournament  : {r[1]} | {r[2]}")
        print(f"  Teams       : {r[3]} vs {r[4]}")
        print(f"  Start time  : {r[5]}")
        print(f"  Status      : {r[6]}")
        print()

print("=" * 60)
print("5. DATE RANGE PER SPORT")
print("=" * 60)

for sport in sports:
    row = conn.execute("""
        SELECT MIN(start_time), MAX(start_time), COUNT(*)
        FROM fixtures
        WHERE sport_slug = ?
    """, (sport,)).fetchone()
    print(f"  {sport:<20} {row[0][:10]} to {row[1][:10]}  ({row[2]:,} fixtures)")

print()
print("=" * 60)
print("6. KEY LEAGUES PRESENCE CHECK")
print("=" * 60)

KEY_LEAGUES = [
    (10, "Premier League",         "England"),
    (10, "LaLiga",                 "Spain"),
    (10, "Serie A",                "Italy"),
    (10, "Bundesliga",             "Germany"),
    (10, "Ligue 1",                "France"),
    (10, "UEFA Champions League",  "International Clubs"),
    (10, "UEFA Europa League",     "International Clubs"),
    (10, "MLS",                    "USA"),
    (10, "Eredivisie",             "Netherlands"),
    (11, "NBA",                    "USA"),
    (12, "ATP Madrid, Spain Men Singles",       "ATP"),
    (12, "WTA Madrid, Spain Women Singles",     "WTA"),
    (12, "ATP Rome, Italy Men Singles",         "ATP"),
    (12, "WTA Rome, Italy Women Singles",       "WTA"),
    (13, "MLB",                    "USA"),
    (15, "NHL",                    "USA"),
    (15, "PWHL, Women",            "USA"),
    (20, "UFC Fight Night",        "UFC"),
]

for sport_id, tournament, category in KEY_LEAGUES:
    if category == "UFC":
        cnt = conn.execute("""
            SELECT COUNT(*) FROM fixtures
            WHERE sport_id = ?
            AND tournament_name LIKE ?
        """, (sport_id, f"%UFC%")).fetchone()[0]
    else:
        cnt = conn.execute("""
            SELECT COUNT(*) FROM fixtures
            WHERE sport_id = ?
            AND tournament_name = ?
            AND category_name = ?
        """, (sport_id, tournament, category)).fetchone()[0]

    status = "OK" if cnt > 0 else "MISSING"
    print(f"  {status:<8} {tournament} [{category}] - {cnt} fixtures")

print()
print("=" * 60)
print("7. STATUS ID BREAKDOWN")
print("=" * 60)
print("(status 2 = finished, 0 = upcoming, 1 = live)")
print()

rows = conn.execute("""
    SELECT sport_slug, status_id, COUNT(*) as cnt
    FROM fixtures
    GROUP BY sport_slug, status_id
    ORDER BY sport_slug, status_id
""").fetchall()

current_sport = None
for sport, status, cnt in rows:
    if sport != current_sport:
        print(f"\n  {sport.upper()}")
        current_sport = sport
    label = {0: "upcoming", 1: "live", 2: "finished"}.get(status, f"unknown({status})")
    print(f"    status {status} ({label:<10}): {cnt:,}")

conn.close()

print()
print("=" * 60)
print("CHECK COMPLETE")
print("=" * 60)