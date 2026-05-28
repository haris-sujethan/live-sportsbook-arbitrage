#!/usr/bin/env python3

import os, sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Arial"
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

os.makedirs("charts", exist_ok=True)
ODDS_DB = os.path.join(os.path.dirname(__file__), "odds_history.db")

SOFT_BOOKS = ["draftkings", "betmgm", "thescore", "betway", "fanduel"]
OUTCOME_1  = "121"
OUTCOME_2  = "122"

BOOK_COLORS = {
    "draftkings": "#1a7fc4",
    "betmgm":     "#e07b00",
    "thescore":   "#c41a3a",
    "betway":     "#1aad4a",
    "fanduel":    "#7b3dc4",
}
BOOK_LABELS = {
    "draftkings": "DraftKings",
    "betmgm":     "BetMGM",
    "thescore":   "theScore",
    "betway":     "Betway",
    "fanduel":    "FanDuel",
}

print("Loading...", flush=True)
conn   = sqlite3.connect(ODDS_DB)
df_all = pd.read_sql_query("""
    SELECT fixture_id, bookmaker, outcome_id, price, timestamp
    FROM   odds_history WHERE sport_slug = 'tennis'
    ORDER  BY fixture_id, bookmaker, outcome_id, timestamp
""", conn)
conn.close()

pin_fix = set(df_all[df_all["bookmaker"] == "pinnacle"]["fixture_id"].unique())

def get_price_at(tl, ts):
    p = None
    for rt, rp in tl:
        if rt <= ts: p = rp
        else: break
    return p

all_windows = []
for book in SOFT_BOOKS:
    print(f"  {BOOK_LABELS[book]}...", flush=True)
    bfix  = set(df_all[df_all["bookmaker"] == book]["fixture_id"].unique())
    flist = list(pin_fix & bfix)
    mask  = df_all["fixture_id"].isin(flist) & df_all["bookmaker"].isin(["pinnacle", book])
    df_p  = df_all[mask].copy()

    for fid in flist:
        fd  = df_p[df_p["fixture_id"] == fid]
        pd_ = fd[fd["bookmaker"] == "pinnacle"]
        sd  = fd[fd["bookmaker"] == book]
        po1 = sorted([(r.timestamp, r.price) for r in pd_[pd_["outcome_id"]==OUTCOME_1].itertuples()], key=lambda x: x[0])
        po2 = sorted([(r.timestamp, r.price) for r in pd_[pd_["outcome_id"]==OUTCOME_2].itertuples()], key=lambda x: x[0])
        so1 = sorted([(r.timestamp, r.price) for r in sd[sd["outcome_id"]==OUTCOME_1].itertuples()], key=lambda x: x[0])
        so2 = sorted([(r.timestamp, r.price) for r in sd[sd["outcome_id"]==OUTCOME_2].itertuples()], key=lambda x: x[0])
        if not (po1 and po2 and so1 and so2): continue

        all_ts = sorted(set([r[0] for r in po1+po2+so1+so2]))
        arb_open = False; arb_start = None; arb_peak = 0.0

        for ts in all_ts:
            p1=get_price_at(po1,ts); p2=get_price_at(po2,ts)
            s1=get_price_at(so1,ts); s2=get_price_at(so2,ts)
            if not all([p1,p2,s1,s2]) or min(p1,p2,s1,s2)<1.01: continue
            best = max(1-(1/p1+1/s2), 1-(1/p2+1/s1))
            if best > 0:
                if not arb_open: arb_open=True; arb_start=ts; arb_peak=best
                else: arb_peak=max(arb_peak,best)
            else:
                if arb_open:
                    try:
                        dur = (datetime.fromisoformat(ts.replace("Z","+00:00")) -
                               datetime.fromisoformat(arb_start.replace("Z","+00:00"))).total_seconds()
                    except: dur = 0
                    if dur > 0:
                        all_windows.append({"book": book, "margin": arb_peak*100, "duration": dur})
                    arb_open=False; arb_start=None; arb_peak=0.0

wdf = pd.DataFrame(all_windows)
wdf = wdf[(wdf["margin"] <= 10.0) & (wdf["duration"] >= 1) & (wdf["duration"] <= 180)].copy()
wdf["log_dur"] = np.log10(wdf["duration"])
total = len(wdf)
print(f"\n{total:,} windows.\n", flush=True)

X_MIN, X_MAX = np.log10(1), np.log10(180)
Y_MIN, Y_MAX = 0, 10
TICK_SECS   = [1, 5, 10, 30, 60, 180]
TICK_LOG    = [np.log10(s) for s in TICK_SECS]
TICK_LABELS = ["1s", "5s", "10s", "30s", "1 min", "3 min"]

def style_panel(ax, book, n, ylabel):
    ax.set_facecolor("white")
    ax.set_xlim(X_MIN, X_MAX)
    ax.set_ylim(Y_MIN, Y_MAX)
    ax.set_xticks(TICK_LOG)
    ax.set_xticklabels(TICK_LABELS, fontsize=9, color="#444444")
    ax.set_yticks([0, 2, 4, 6, 8, 10])
    if ylabel:
        ax.set_yticklabels(["0%","2%","4%","6%","8%","10%"], fontsize=9, color="#444444")
        ax.set_ylabel("Arbitrage %", fontsize=10, color="#333333", labelpad=6)
    else:
        ax.set_yticklabels([])
    ax.set_xlabel("Window Duration", fontsize=10, color="#333333", labelpad=5)
    ax.set_title(f"{BOOK_LABELS[book]}\n{n:,} windows",
                 fontsize=11, color="#111111", pad=6, fontweight="bold")
    ax.grid(True, color="#eeeeee", linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_edgecolor("#dddddd")

print("Generating scatter PNG...", flush=True)

fig, axes = plt.subplots(1, 5, figsize=(22, 6), facecolor="white",
                         constrained_layout=True)

for i, (book, ax) in enumerate(zip(SOFT_BOOKS, axes)):
    sub = wdf[wdf["book"] == book]
    ax.scatter(
        sub["log_dur"], sub["margin"],
        s=2,
        color=BOOK_COLORS[book],
        alpha=0.18,
        linewidths=0,
        rasterized=True,
        zorder=3,
    )
    style_panel(ax, book, len(sub), ylabel=(i == 0))

fig.suptitle(
    f"Pinnacle vs Soft Books — Arb Windows (Individual Dots)  ·  "
    f"{total:,} windows  ·  Tennis  ·  Feb–May 2026",
    fontsize=13, color="#111111",
)

plt.savefig("charts/books_scatter.png", dpi=200,
            bbox_inches="tight", facecolor="white")
plt.close()
print("Saved → charts/books_scatter.png", flush=True)

print("Generating hexbin PNG...", flush=True)

fig, axes = plt.subplots(1, 5, figsize=(22, 6), facecolor="white",
                         constrained_layout=True)

for i, (book, ax) in enumerate(zip(SOFT_BOOKS, axes)):
    sub   = wdf[wdf["book"] == book]
    color = BOOK_COLORS[book]
    cmap  = LinearSegmentedColormap.from_list(book, ["#f8f8f8", color], N=256)

    ax.hexbin(
        sub["log_dur"], sub["margin"],
        gridsize=30,
        cmap=cmap,
        mincnt=1,
        linewidths=0.15,
        zorder=3,
    )
    style_panel(ax, book, len(sub), ylabel=(i == 0))

fig.suptitle(
    f"Pinnacle vs Soft Books — Arb Windows (Density Hexbin)  ·  "
    f"{total:,} windows  ·  Tennis  ·  Feb–May 2026",
    fontsize=13, color="#111111",
)

plt.savefig("charts/books_hexbin.png", dpi=200,
            bbox_inches="tight", facecolor="white")
plt.close()
print("Saved → charts/books_hexbin.png", flush=True)
