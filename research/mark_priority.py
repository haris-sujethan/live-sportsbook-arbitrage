import sqlite3

conn = sqlite3.connect("oddspapi.db")

try:
    conn.execute("ALTER TABLE fixtures ADD COLUMN priority INTEGER DEFAULT 0")
    conn.commit()
    print("Added priority column")
except:
    print("Priority column already exists")

conn.execute("UPDATE fixtures SET priority = 0")
conn.commit()
print("Reset all priorities to 0")
print()

KEEP = {
    10: [
        ("Premier League",          "England"),
        ("Championship",            "England"),
        ("League One",              "England"),
        ("League Two",              "England"),
        ("National League",         "England"),
        ("LaLiga",                  "Spain"),
        ("LaLiga 2",                "Spain"),
        ("Serie A",                 "Italy"),
        ("Serie B",                 "Italy"),
        ("Bundesliga",              "Germany"),
        ("2. Bundesliga",           "Germany"),
        ("Ligue 1",                 "France"),
        ("Ligue 2",                 "France"),
        ("UEFA Champions League",   "International Clubs"),
        ("UEFA Europa League",      "International Clubs"),
        ("UEFA Conference League",  "International Clubs"),
        ("MLS",                     "USA"),
        ("Eredivisie",              "Netherlands"),
        ("Liga Portugal",           "Portugal"),
        ("Brasileiro Serie A",      "Brazil"),
        ("Super Lig",               "Turkiye"),
        ("Ekstraklasa",             "Poland"),
        ("Allsvenskan",             "Sweden"),
        ("Pro League",              "Belgium"),
        ("Super League",            "Switzerland"),
        ("Superliga",               "Denmark"),
        ("Eliteserien",             "Norway"),
        ("Canadian Premier League", "Canada"),
    ],
    11: [
        ("NBA", "USA"),
    ],
    12: [
        ("ATP Monte Carlo, Monaco Men Singles", "ATP"),
        ("ATP Houston, USA Men Singles",        "ATP"),
        ("ATP Bucharest, Romania Men Singles",  "ATP"),
        ("ATP Marrakech, Morocco Men Singles",  "ATP"),
        ("ATP Miami, USA Men Singles",          "ATP"),
        ("ATP Indian Wells, USA Men Singles",   "ATP"),
        ("ATP Madrid, Spain Men Singles",       "ATP"),
        ("ATP Rome, Italy Men Singles",         "ATP"),
        ("WTA Bogota, Colombia Women Singles",  "WTA"),
        ("WTA Charleston, USA Women Singles",   "WTA"),
        ("WTA Linz, Austria Women Singles",     "WTA"),
        ("WTA Miami, USA Women Singles",        "WTA"),
        ("WTA Indian Wells, USA Women Singles", "WTA"),
        ("WTA Madrid, Spain Women Singles",     "WTA"),
        ("WTA Rome, Italy Women Singles",       "WTA"),
        ("WTA Dubai, UAE Women Singles",        "WTA"),
    ],
    13: [
        ("MLB", "USA"),
    ],
    15: [
        ("NHL", "USA"),
    ],
}

MMA_KEYWORDS = ["UFC", "PFL"]

total_marked = 0

for sport_id, pairs in KEEP.items():
    for tournament_name, category_name in pairs:
        result = conn.execute("""
            UPDATE fixtures
            SET priority = 1
            WHERE sport_id = ?
            AND tournament_name = ?
            AND category_name = ?
            AND status_id = 2
        """, (sport_id, tournament_name, category_name))

        marked = result.rowcount
        total_marked += marked
        if marked > 0:
            print(f"MARKED: [{category_name}] {tournament_name} - {marked} fixtures")
        else:
            print(f"NO MATCH: [{category_name}] {tournament_name}")

for keyword in MMA_KEYWORDS:
    result = conn.execute("""
        UPDATE fixtures
        SET priority = 1
        WHERE sport_id = 20
        AND tournament_name LIKE ?
        AND status_id = 2
    """, (f"%{keyword}%",))
    marked = result.rowcount
    total_marked += marked
    if marked > 0:
        print(f"MARKED: [MMA] {keyword} - {marked} fixtures")
    else:
        print(f"NO MATCH: [MMA] {keyword}")

conn.commit()
conn.close()

print()
print(f"Total priority fixtures: {total_marked}")
print("Database updated. No data deleted.")