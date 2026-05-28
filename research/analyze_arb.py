"""
analyze_arb.py

Compares Pinnacle vs each soft book on tennis fixtures.
Finds historical arb windows, quantifies margins, durations, and patterns.
"""

import sqlite3
from datetime import datetime
from collections import defaultdict

ODDS_DB    = "odds_history.db"
FIXTURE_DB = "oddspapi.db"

SOFT_BOOKS = [
    "draftkings",
    "betmgm",
    "thescore",
    "betway",
    "fanduel",
    "bet365",
]

# Tennis outcomes
OUTCOME_1 = "121"  # Player 1
OUTCOME_2 = "122"  # Player 2


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def implied(decimal_price):
    return 1.0 / decimal_price


def arb_margin(price_a, price_b):
    """
    Returns arb margin if arb exists, else negative number.
    price_a = one side on book A
    price_b = other side on book B
    margin > 0 means guaranteed profit exists
    """
    total = implied(price_a) + implied(price_b)
    return 1.0 - total


def kelly_stakes(price_a, price_b, bankroll=100.0):
    """
    Given arb prices, return optimal stakes for each side.
    Returns (stake_a, stake_b, profit)
    """
    imp_a = implied(price_a)
    imp_b = implied(price_b)
    total_imp = imp_a + imp_b

    stake_a = bankroll * imp_b / total_imp
    stake_b = bankroll * imp_a / total_imp
    profit  = bankroll * (1 - total_imp)

    return stake_a, stake_b, profit


def get_fixture_teams(fixture_id, fix_conn):
    row = fix_conn.execute(
        "SELECT home_team, away_team, tournament_name FROM fixtures WHERE fixture_id=?",
        (fixture_id,)
    ).fetchone()
    if row:
        return row[0], row[1], row[2]
    return "Player 1", "Player 2", "Unknown"


def build_price_timeline(rows):
    """
    Given a list of (timestamp, price) tuples sorted by timestamp,
    return a function that gives the last known price at any timestamp.
    """
    if not rows:
        return None
    sorted_rows = sorted(rows, key=lambda x: x[0])
    return sorted_rows


def get_price_at(timeline, ts):
    """Get the last known price at or before timestamp ts."""
    if not timeline:
        return None
    price = None
    for row_ts, row_price in timeline:
        if row_ts <= ts:
            price = row_price
        else:
            break
    return price


def main():
    conn     = sqlite3.connect(ODDS_DB)
    fix_conn = sqlite3.connect(FIXTURE_DB)

    # ----------------------------------------------------------------
    # 0. Overview
    # ----------------------------------------------------------------
    section("0. DATASET OVERVIEW")

    total_rows = conn.execute(
        "SELECT COUNT(*) FROM odds_history WHERE sport_slug='tennis'"
    ).fetchone()[0]

    fixtures = conn.execute(
        "SELECT COUNT(DISTINCT fixture_id) FROM odds_history WHERE sport_slug='tennis'"
    ).fetchone()[0]

    print(f"  Total tennis rows : {total_rows:,}")
    print(f"  Total fixtures    : {fixtures:,}")
    print()

    book_counts = conn.execute("""
        SELECT bookmaker, COUNT(*) as cnt,
               COUNT(DISTINCT fixture_id) as fix_cnt
        FROM odds_history
        WHERE sport_slug = 'tennis'
        GROUP BY bookmaker
        ORDER BY cnt DESC
    """).fetchall()

    print(f"  {'Book':<15} {'Rows':>12} {'Fixtures':>10}")
    print(f"  {'-'*15} {'-'*12} {'-'*10}")
    for book, cnt, fix_cnt in book_counts:
        print(f"  {book:<15} {cnt:>12,} {fix_cnt:>10,}")

    # ----------------------------------------------------------------
    # 1. Get all fixtures that have BOTH Pinnacle and soft book data
    # ----------------------------------------------------------------
    section("1. FINDING FIXTURES WITH BOTH PINNACLE AND SOFT BOOK DATA")

    pinnacle_fixtures = set(row[0] for row in conn.execute("""
        SELECT DISTINCT fixture_id FROM odds_history
        WHERE sport_slug = 'tennis'
        AND bookmaker = 'pinnacle'
    """).fetchall())

    print(f"  Fixtures with Pinnacle data: {len(pinnacle_fixtures):,}")

    book_fixtures = {}
    for book in SOFT_BOOKS:
        fixtures_for_book = set(row[0] for row in conn.execute("""
            SELECT DISTINCT fixture_id FROM odds_history
            WHERE sport_slug = 'tennis'
            AND bookmaker = ?
        """, (book,)).fetchall())
        overlap = pinnacle_fixtures & fixtures_for_book
        book_fixtures[book] = overlap
        print(f"  {book:<15} : {len(fixtures_for_book):>5} fixtures | "
              f"{len(overlap):>5} overlap with Pinnacle")

    # ----------------------------------------------------------------
    # 2. Arb analysis per book pair
    # ----------------------------------------------------------------
    section("2. ARB ANALYSIS — PINNACLE vs EACH SOFT BOOK")

    print("  Processing fixtures... this may take a few minutes.")
    print()

    # Results storage
    results = {book: {
        "arb_windows":      [],   # list of (margin, duration_secs, tournament, ts)
        "total_snapshots":  0,
        "arb_snapshots":    0,
    } for book in SOFT_BOOKS}

    tournament_arb = defaultdict(lambda: defaultdict(list))
    hour_arb       = defaultdict(lambda: defaultdict(list))

    for book in SOFT_BOOKS:
        fixtures_to_process = list(book_fixtures[book])
        print(f"  Processing {book} ({len(fixtures_to_process)} fixtures)...",
              flush=True)

        for fix_idx, fixture_id in enumerate(fixtures_to_process):

            # Get tournament name
            _, _, tournament = get_fixture_teams(fixture_id, fix_conn)

            # Load Pinnacle data for this fixture
            pin_rows = conn.execute("""
                SELECT timestamp, outcome_id, price
                FROM odds_history
                WHERE fixture_id = ?
                AND bookmaker = 'pinnacle'
                ORDER BY timestamp
            """, (fixture_id,)).fetchall()

            if not pin_rows:
                continue

            # Build Pinnacle timelines per outcome
            pin_o1 = [(r[0], r[2]) for r in pin_rows if r[1] == OUTCOME_1]
            pin_o2 = [(r[0], r[2]) for r in pin_rows if r[1] == OUTCOME_2]

            if not pin_o1 or not pin_o2:
                continue

            # Load soft book data
            soft_rows = conn.execute("""
                SELECT timestamp, outcome_id, price
                FROM odds_history
                WHERE fixture_id = ?
                AND bookmaker = ?
                ORDER BY timestamp
            """, (fixture_id, book)).fetchall()

            if not soft_rows:
                continue

            soft_o1 = [(r[0], r[2]) for r in soft_rows if r[1] == OUTCOME_1]
            soft_o2 = [(r[0], r[2]) for r in soft_rows if r[1] == OUTCOME_2]

            if not soft_o1 or not soft_o2:
                continue

            # Get all unique timestamps from both books combined
            all_timestamps = sorted(set(
                [r[0] for r in pin_rows] +
                [r[0] for r in soft_rows]
            ))

            # At each timestamp check for arb
            arb_open    = False
            arb_start   = None
            arb_margin_peak = 0.0

            for ts in all_timestamps:
                p1 = get_price_at(pin_o1,  ts)
                p2 = get_price_at(pin_o2,  ts)
                s1 = get_price_at(soft_o1, ts)
                s2 = get_price_at(soft_o2, ts)

                if not all([p1, p2, s1, s2]):
                    continue

                results[book]["total_snapshots"] += 1

                # Check both directions
                # Direction A: bet player1 on Pinnacle, player2 on soft book
                margin_a = arb_margin(p1, s2)
                # Direction B: bet player2 on Pinnacle, player1 on soft book
                margin_b = arb_margin(p2, s1)

                best_margin = max(margin_a, margin_b)

                if best_margin > 0:
                    results[book]["arb_snapshots"] += 1

                    if not arb_open:
                        arb_open        = True
                        arb_start       = ts
                        arb_margin_peak = best_margin
                    else:
                        arb_margin_peak = max(arb_margin_peak, best_margin)

                    # Track by hour
                    try:
                        hour = int(ts[11:13])
                        hour_arb[book][hour].append(best_margin)
                    except:
                        pass

                    # Track by tournament
                    tournament_arb[book][tournament].append(best_margin)

                else:
                    if arb_open:
                        # Window just closed
                        try:
                            ts_start = datetime.fromisoformat(
                                arb_start.replace("Z", "+00:00")
                            )
                            ts_end   = datetime.fromisoformat(
                                ts.replace("Z", "+00:00")
                            )
                            duration = (ts_end - ts_start).total_seconds()
                        except:
                            duration = 0

                        results[book]["arb_windows"].append({
                            "margin":     arb_margin_peak,
                            "duration":   duration,
                            "tournament": tournament,
                            "timestamp":  arb_start,
                        })

                        arb_open        = False
                        arb_start       = None
                        arb_margin_peak = 0.0

            if fix_idx % 100 == 0 and fix_idx > 0:
                print(f"    {fix_idx}/{len(fixtures_to_process)} done", flush=True)

    # ----------------------------------------------------------------
    # 3. Results — overall per book pair
    # ----------------------------------------------------------------
    section("3. ARB SUMMARY — PINNACLE vs EACH SOFT BOOK")

    print(f"\n  {'Book':<15} {'Windows':>8} {'Freq%':>8} {'Avg Margin':>12} "
          f"{'Avg Duration':>14} {'Max Margin':>12}")
    print(f"  {'-'*15} {'-'*8} {'-'*8} {'-'*12} {'-'*14} {'-'*12}")

    book_summary = []
    for book in SOFT_BOOKS:
        r       = results[book]
        windows = r["arb_windows"]
        total   = r["total_snapshots"]
        arb_ss  = r["arb_snapshots"]

        if not windows or total == 0:
            print(f"  {book:<15} {'0':>8} {'0.00%':>8} {'N/A':>12} {'N/A':>14} {'N/A':>12}")
            continue

        freq        = arb_ss / total * 100
        avg_margin  = sum(w["margin"]   for w in windows) / len(windows) * 100
        avg_dur     = sum(w["duration"] for w in windows) / len(windows)
        max_margin  = max(w["margin"]   for w in windows) * 100

        book_summary.append((book, len(windows), freq, avg_margin, avg_dur, max_margin))

        print(f"  {book:<15} {len(windows):>8,} {freq:>7.2f}% "
              f"{avg_margin:>11.3f}% {avg_dur:>12.1f}s {max_margin:>11.3f}%")

    book_summary.sort(key=lambda x: x[2], reverse=True)

    # ----------------------------------------------------------------
    # 4. Best tournaments for arb
    # ----------------------------------------------------------------
    section("4. BEST TOURNAMENTS FOR ARB (Top 10 per book)")

    for book in SOFT_BOOKS:
        t_data = tournament_arb[book]
        if not t_data:
            continue

        t_summary = []
        for tournament, margins in t_data.items():
            if len(margins) < 3:
                continue
            t_summary.append((
                tournament,
                len(margins),
                sum(margins)/len(margins)*100,
                max(margins)*100
            ))

        t_summary.sort(key=lambda x: x[1], reverse=True)

        if not t_summary:
            continue

        print(f"\n  -- Pinnacle vs {book.upper()}")
        print(f"  {'Tournament':<40} {'Windows':>8} {'Avg%':>8} {'Max%':>8}")
        print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*8}")
        for t, cnt, avg, mx in t_summary[:10]:
            print(f"  {t[:40]:<40} {cnt:>8,} {avg:>7.3f}% {mx:>7.3f}%")

    # ----------------------------------------------------------------
    # 5. Best time of day for arb
    # ----------------------------------------------------------------
    section("5. BEST TIME OF DAY FOR ARB (UTC)")

    for book in SOFT_BOOKS:
        h_data = hour_arb[book]
        if not h_data:
            continue

        print(f"\n  -- Pinnacle vs {book.upper()}")
        print(f"  {'Hour':>6} {'Arb Moments':>12} {'Avg Margin':>12}  Bar")
        print(f"  {'-'*6} {'-'*12} {'-'*12}  {'-'*30}")

        max_cnt = max(len(v) for v in h_data.values()) if h_data else 1

        for hour in range(24):
            margins = h_data.get(hour, [])
            if not margins:
                continue
            avg = sum(margins) / len(margins) * 100
            bar = "#" * int(len(margins) / max_cnt * 30)
            print(f"  {hour:>4}h  {len(margins):>12,} {avg:>11.3f}%  {bar}")

    # ----------------------------------------------------------------
    # 6. Top 20 biggest arb opportunities found
    # ----------------------------------------------------------------
    section("6. TOP 20 BIGGEST ARB OPPORTUNITIES")

    all_windows = []
    for book in SOFT_BOOKS:
        for w in results[book]["arb_windows"]:
            all_windows.append({**w, "book": book})

    all_windows.sort(key=lambda x: x["margin"], reverse=True)

    print(f"\n  {'Book':<15} {'Tournament':<35} {'Margin':>8} "
          f"{'Duration':>10} {'Timestamp'}")
    print(f"  {'-'*15} {'-'*35} {'-'*8} {'-'*10} {'-'*20}")

    for w in all_windows[:20]:
        print(f"  {w['book']:<15} {w['tournament'][:35]:<35} "
              f"{w['margin']*100:>7.3f}% "
              f"{w['duration']:>8.0f}s  "
              f"{w['timestamp'][:16]}")

    # ----------------------------------------------------------------
    # 7. Sample Kelly stakes for top opportunity
    # ----------------------------------------------------------------
    section("7. SAMPLE KELLY STAKES")

    print("""
  Formula: Given an arb between Pinnacle and a soft book,
  Kelly criterion tells you exactly how much to stake on each side
  to guarantee profit regardless of outcome.

  Example — if top arb window had:
    Pinnacle  Player A  @ 2.10
    DraftKings Player B @ 2.05

  On $200 bankroll:
  """)

    example_p = 2.10
    example_s = 2.05
    s_a, s_b, profit = kelly_stakes(example_p, example_s, 200)

    margin = arb_margin(example_p, example_s) * 100

    print(f"    Arb margin      : {margin:.2f}%")
    print(f"    Stake Pinnacle  : ${s_a:.2f}")
    print(f"    Stake DraftKings: ${s_b:.2f}")
    print(f"    Guaranteed profit: ${profit:.2f}")
    print(f"    ROI             : {profit/200*100:.2f}%")

    # ----------------------------------------------------------------
    # 8. Final recommendations
    # ----------------------------------------------------------------
    section("8. RECOMMENDATIONS")

    if book_summary:
        best_book  = book_summary[0][0]
        best_freq  = book_summary[0][2]
        best_margin = book_summary[0][3]

        print(f"""
  BEST BOOK PAIR    : Pinnacle vs {best_book}
  ARB FREQUENCY     : {best_freq:.2f}% of all price snapshots had arb
  AVG ARB MARGIN    : {best_margin:.3f}%

  NEXT STEPS:
  1. Build live tool focused on Pinnacle vs {best_book}
  2. Watch the hours identified in Section 5 most closely
  3. Focus on the tournaments identified in Section 4
  4. Start with small stakes to stay under the radar
  5. Track every bet with CLV to prove edge over time
        """)

    conn.close()
    fix_conn.close()

    print("=" * 70)
    print("  ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()