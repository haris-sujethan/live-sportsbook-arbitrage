"""
analyze_pinnacle.py

Analyzes Pinnacle line movement data to identify:
1. Most volatile sports
2. Best time windows for arb
3. Most volatile tournaments
4. Biggest line movers (individual fixtures)
5. Day of week patterns
"""

import sqlite3
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH      = "odds_history.db"
FIXTURE_DB   = "oddspapi.db"

SPORT_NAMES = {
    "soccer":     "Soccer",
    "basketball": "Basketball",
    "tennis":     "Tennis",
    "baseball":   "Baseball",
    "ice-hockey": "Ice Hockey",
    "mma":        "MMA",
}

def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)

def fmt(val, width=8, decimals=3):
    if val is None:
        return " " * width
    return f"{val:>{width}.{decimals}f}"

def main():
    conn  = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ----------------------------------------------------------------
    # 0. Overview
    # ----------------------------------------------------------------
    section("0. DATASET OVERVIEW")

    total_rows = conn.execute(
        "SELECT COUNT(*) FROM odds_history"
    ).fetchone()[0]

    total_fixtures = conn.execute(
        "SELECT COUNT(DISTINCT fixture_id) FROM odds_history"
    ).fetchone()[0]

    date_range = conn.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM odds_history"
    ).fetchone()

    print(f"  Total rows        : {total_rows:,}")
    print(f"  Total fixtures    : {total_fixtures:,}")
    print(f"  Date range        : {date_range[0][:10]} to {date_range[1][:10]}")
    print(f"  Bookmaker         : Pinnacle (moneyline only)")

    sport_counts = conn.execute("""
        SELECT sport_slug, COUNT(*) as cnt,
               COUNT(DISTINCT fixture_id) as fixtures
        FROM odds_history
        GROUP BY sport_slug
        ORDER BY cnt DESC
    """).fetchall()

    print()
    print(f"  {'Sport':<20} {'Rows':>12} {'Fixtures':>10}")
    print(f"  {'-'*20} {'-'*12} {'-'*10}")
    for row in sport_counts:
        print(f"  {SPORT_NAMES.get(row['sport_slug'], row['sport_slug']):<20} "
              f"{row['cnt']:>12,} {row['fixtures']:>10,}")

    # ----------------------------------------------------------------
    # 1. Line movement per fixture
    #    For each fixture+outcome: open price, close price, num changes
    #    close  = latest row with active=1, or latest row overall
    #    open   = earliest row
    # ----------------------------------------------------------------
    section("1. BUILDING LINE MOVEMENT STATS (may take a moment...)")
    print("  Loading data...", flush=True)

    rows = conn.execute("""
        SELECT fixture_id, sport_slug, tournament,
               outcome_id, price, timestamp, active
        FROM odds_history
        ORDER BY fixture_id, outcome_id, timestamp
    """).fetchall()

    print(f"  Loaded {len(rows):,} rows. Computing stats...", flush=True)

    # Group by fixture + outcome
    fixture_outcome = defaultdict(list)
    fixture_meta    = {}

    for row in rows:
        key = (row["fixture_id"], row["outcome_id"])
        fixture_outcome[key].append({
            "price":     row["price"],
            "timestamp": row["timestamp"],
            "active":    row["active"],
        })
        if row["fixture_id"] not in fixture_meta:
            fixture_meta[row["fixture_id"]] = {
                "sport_slug": row["sport_slug"],
                "tournament": row["tournament"],
            }

    # Compute per-fixture stats
    fixture_stats = defaultdict(lambda: {
        "total_move":   0.0,
        "max_move":     0.0,
        "num_changes":  0,
        "open_ts":      None,
        "close_ts":     None,
        "open_price":   None,
        "close_price":  None,
        "sport_slug":   None,
        "tournament":   None,
    })

    for (fixture_id, outcome_id), entries in fixture_outcome.items():
        if len(entries) < 2:
            continue

        prices     = [e["price"]     for e in entries]
        timestamps = [e["timestamp"] for e in entries]

        open_price  = prices[0]
        close_price = prices[-1]
        total_move  = abs(close_price - open_price)
        num_changes = len(entries) - 1
        max_single  = max(
            abs(prices[i] - prices[i-1])
            for i in range(1, len(prices))
        )

        fs = fixture_stats[fixture_id]
        fs["total_move"]  += total_move
        fs["max_move"]     = max(fs["max_move"], max_single)
        fs["num_changes"] += num_changes
        fs["open_ts"]      = fs["open_ts"] or timestamps[0]
        fs["close_ts"]     = timestamps[-1]
        fs["sport_slug"]   = fixture_meta[fixture_id]["sport_slug"]
        fs["tournament"]   = fixture_meta[fixture_id]["tournament"]

    print(f"  Computed stats for {len(fixture_stats):,} fixtures.")

    # ----------------------------------------------------------------
    # 2. Most volatile sports
    # ----------------------------------------------------------------
    section("2. MOST VOLATILE SPORTS (Avg Line Movement)")

    sport_moves = defaultdict(list)
    sport_changes = defaultdict(list)

    for fid, fs in fixture_stats.items():
        sport_moves[fs["sport_slug"]].append(fs["total_move"])
        sport_changes[fs["sport_slug"]].append(fs["num_changes"])

    sport_summary = []
    for sport, moves in sport_moves.items():
        avg_move    = sum(moves) / len(moves)
        avg_changes = sum(sport_changes[sport]) / len(sport_changes[sport])
        max_move    = max(moves)
        sport_summary.append((sport, avg_move, avg_changes, max_move, len(moves)))

    sport_summary.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  {'Sport':<20} {'Avg Move':>10} {'Avg Changes':>13} "
          f"{'Max Move':>10} {'Fixtures':>10}")
    print(f"  {'-'*20} {'-'*10} {'-'*13} {'-'*10} {'-'*10}")
    for sport, avg_move, avg_changes, max_move, n in sport_summary:
        print(f"  {SPORT_NAMES.get(sport, sport):<20} "
              f"{fmt(avg_move, 10, 3)} {fmt(avg_changes, 13, 1)} "
              f"{fmt(max_move, 10, 3)} {n:>10,}")

    print()
    print("  INTERPRETATION:")
    print("  Higher avg move = Pinnacle moves more = soft books lag more = more arb")
    print("  Higher avg changes = more line updates = more arb windows")

    # ----------------------------------------------------------------
    # 3. Most volatile tournaments
    # ----------------------------------------------------------------
    section("3. MOST VOLATILE TOURNAMENTS (Top 20)")

    tournament_moves = defaultdict(list)
    tournament_sport = {}

    for fid, fs in fixture_stats.items():
        t = fs["tournament"]
        tournament_moves[t].append(fs["total_move"])
        tournament_sport[t] = fs["sport_slug"]

    tournament_summary = []
    for t, moves in tournament_moves.items():
        if len(moves) < 5:
            continue
        avg_move = sum(moves) / len(moves)
        tournament_summary.append((t, avg_move, len(moves),
                                   tournament_sport[t]))

    tournament_summary.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  {'Tournament':<35} {'Sport':<14} {'Avg Move':>10} {'Fixtures':>10}")
    print(f"  {'-'*35} {'-'*14} {'-'*10} {'-'*10}")
    for t, avg_move, n, sport in tournament_summary[:20]:
        print(f"  {t[:35]:<35} "
              f"{SPORT_NAMES.get(sport, sport)[:14]:<14} "
              f"{fmt(avg_move, 10, 3)} {n:>10,}")

    # ----------------------------------------------------------------
    # 4. Time of day analysis
    #    Using open_ts (when the line first opened) hour
    # ----------------------------------------------------------------
    section("4. TIME OF DAY — When Do Lines Move Most? (UTC)")

    hour_moves = defaultdict(list)

    for fid, fs in fixture_stats.items():
        if not fs["open_ts"]:
            continue
        try:
            ts = fs["open_ts"]
            hour = int(ts[11:13])
            hour_moves[hour].append(fs["total_move"])
        except:
            continue

    print(f"\n  {'Hour (UTC)':>12} {'Avg Move':>10} {'Fixtures':>10}  Bar")
    print(f"  {'-'*12} {'-'*10} {'-'*10}  {'-'*30}")

    max_avg = max(
        (sum(m)/len(m) for m in hour_moves.values() if m),
        default=1
    )

    for hour in range(24):
        moves = hour_moves.get(hour, [])
        if not moves:
            continue
        avg = sum(moves) / len(moves)
        bar_len = int((avg / max_avg) * 30)
        bar = "#" * bar_len
        print(f"  {f'{hour:02d}:00':>12} {fmt(avg, 10, 3)} {len(moves):>10,}  {bar}")

    # ----------------------------------------------------------------
    # 5. Day of week analysis
    # ----------------------------------------------------------------
    section("5. DAY OF WEEK — When Is Movement Highest?")

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]
    day_moves = defaultdict(list)

    for fid, fs in fixture_stats.items():
        if not fs["open_ts"]:
            continue
        try:
            dt = datetime.fromisoformat(
                fs["open_ts"].replace("Z", "+00:00")
            )
            day_moves[dt.weekday()].append(fs["total_move"])
        except:
            continue

    print(f"\n  {'Day':<12} {'Avg Move':>10} {'Fixtures':>10}  Bar")
    print(f"  {'-'*12} {'-'*10} {'-'*10}  {'-'*30}")

    max_avg = max(
        (sum(m)/len(m) for m in day_moves.values() if m),
        default=1
    )

    for day_idx in range(7):
        moves = day_moves.get(day_idx, [])
        if not moves:
            continue
        avg = sum(moves) / len(moves)
        bar_len = int((avg / max_avg) * 30)
        bar = "#" * bar_len
        print(f"  {day_names[day_idx]:<12} {fmt(avg, 10, 3)} "
              f"{len(moves):>10,}  {bar}")

    # ----------------------------------------------------------------
    # 6. Top 25 most volatile individual fixtures
    # ----------------------------------------------------------------
    section("6. TOP 25 MOST VOLATILE FIXTURES")

    sorted_fixtures = sorted(
        fixture_stats.items(),
        key=lambda x: x[1]["total_move"],
        reverse=True
    )[:25]

    # Get team names from oddspapi.db
    try:
        fix_conn = sqlite3.connect(FIXTURE_DB)
        fix_conn.row_factory = sqlite3.Row
    except:
        fix_conn = None

    print(f"\n  {'Teams':<40} {'Sport':<12} {'Tournament':<25} "
          f"{'Move':>8} {'Changes':>8}")
    print(f"  {'-'*40} {'-'*12} {'-'*25} {'-'*8} {'-'*8}")

    for fid, fs in sorted_fixtures:
        teams = fid
        if fix_conn:
            row = fix_conn.execute(
                "SELECT home_team, away_team FROM fixtures WHERE fixture_id=?",
                (fid,)
            ).fetchone()
            if row and row["home_team"]:
                teams = f"{row['home_team']} vs {row['away_team']}"

        teams_str = teams[:40]
        sport     = SPORT_NAMES.get(fs["sport_slug"], fs["sport_slug"])[:12]
        tourney   = (fs["tournament"] or "")[:25]

        print(f"  {teams_str:<40} {sport:<12} {tourney:<25} "
              f"{fmt(fs['total_move'], 8, 3)} "
              f"{fs['num_changes']:>8,}")

    if fix_conn:
        fix_conn.close()

    # ----------------------------------------------------------------
    # 7. Pre-game vs in-game movement
    # ----------------------------------------------------------------
    section("7. PRE-GAME vs IN-GAME LINE MOVEMENT")

    print()
    print("  Classifying line changes by timing relative to start_time...")
    print("  (Requires start_time in odds_history — loading...)", flush=True)

    rows_with_time = conn.execute("""
        SELECT o.fixture_id, o.sport_slug, o.price, o.timestamp,
               o.start_time
        FROM odds_history o
        WHERE o.start_time IS NOT NULL
          AND o.start_time != ''
        ORDER BY o.fixture_id, o.timestamp
        LIMIT 500000
    """).fetchall()

    pre_moves  = []
    live_moves = []

    prev = {}
    for row in rows_with_time:
        fid  = row["fixture_id"]
        ts   = row["timestamp"]
        st   = row["start_time"]
        price = row["price"]

        try:
            dt_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            dt_st = datetime.fromisoformat(st.replace("Z", "+00:00"))
            minutes_to_start = (dt_ts - dt_st).total_seconds() / 60
        except:
            continue

        key = (fid, row["fixture_id"])
        if key in prev:
            move = abs(price - prev[key])
            if move > 0:
                if minutes_to_start < 0:
                    pre_moves.append((abs(minutes_to_start), move))
                else:
                    live_moves.append((minutes_to_start, move))

        prev[key] = price

    # Bucket pre-game moves
    buckets_pre = {
        "120+ min before": [],
        "60-120 min before": [],
        "30-60 min before": [],
        "0-30 min before": [],
    }
    for mins, move in pre_moves:
        if mins >= 120:
            buckets_pre["120+ min before"].append(move)
        elif mins >= 60:
            buckets_pre["60-120 min before"].append(move)
        elif mins >= 30:
            buckets_pre["30-60 min before"].append(move)
        else:
            buckets_pre["0-30 min before"].append(move)

    buckets_live = {
        "0-30 min in-game":  [],
        "30-60 min in-game": [],
        "60-90 min in-game": [],
        "90+ min in-game":   [],
    }
    for mins, move in live_moves:
        if mins < 30:
            buckets_live["0-30 min in-game"].append(move)
        elif mins < 60:
            buckets_live["30-60 min in-game"].append(move)
        elif mins < 90:
            buckets_live["60-90 min in-game"].append(move)
        else:
            buckets_live["90+ min in-game"].append(move)

    all_buckets = {**buckets_pre, **buckets_live}
    max_avg = max(
        (sum(m)/len(m) for m in all_buckets.values() if m),
        default=1
    )

    print(f"\n  {'Window':<22} {'Avg Move':>10} {'# Changes':>12}  Bar")
    print(f"  {'-'*22} {'-'*10} {'-'*12}  {'-'*30}")

    for label, moves in all_buckets.items():
        if not moves:
            print(f"  {label:<22} {'no data':>10}")
            continue
        avg     = sum(moves) / len(moves)
        bar_len = int((avg / max_avg) * 30)
        bar     = "#" * bar_len
        print(f"  {label:<22} {fmt(avg, 10, 4)} {len(moves):>12,}  {bar}")

    print()
    print("  INTERPRETATION:")
    print("  The window with highest avg move = when soft books lag most = best arb window")

    # ----------------------------------------------------------------
    # 8. Summary recommendations
    # ----------------------------------------------------------------
    section("8. RECOMMENDATIONS FOR SOFT BOOK DATA COLLECTION")

    top_sport = sport_summary[0][0] if sport_summary else "unknown"
    top_tourney = tournament_summary[0][0] if tournament_summary else "unknown"

    print(f"""
  Based on Pinnacle line movement analysis:

  PRIORITY SPORT     : {SPORT_NAMES.get(top_sport, top_sport)}
                       Highest average line movement = most arb opportunity

  PRIORITY TOURNAMENT: {top_tourney}
                       Most volatile individual competition

  NEXT STEPS:
  1. Fetch soft book data for top 2 sports first
  2. Focus on fixtures with total_move > 0.5 (most volatile)
  3. Use the pre-game vs in-game window analysis to
     set the live alert system polling schedule
  4. Compare Pinnacle closing line vs soft book closing line
     to quantify how much each soft book lags
    """)

    conn.close()
    print("=" * 70)
    print("  ANALYSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()