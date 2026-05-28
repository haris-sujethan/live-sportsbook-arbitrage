import sqlite3

conn = sqlite3.connect("oddspapi.db")

print("=== TOP TOURNAMENTS BY SPORT ===\n")

sports = {
    10: "soccer",
    11: "basketball",
    12: "tennis",
    13: "baseball",
    15: "ice-hockey",
    20: "mma"
}

for sport_id, sport_name in sports.items():
    print(f"\n── {sport_name.upper()}")
    rows = conn.execute("""
        SELECT tournament_name, COUNT(*) as cnt
        FROM fixtures
        WHERE sport_id = ?
        GROUP BY tournament_name
        ORDER BY cnt DESC
        LIMIT 30
    """, (sport_id,)).fetchall()

    for name, cnt in rows:
        print(f"   {cnt:>5}  {name}")

conn.close()