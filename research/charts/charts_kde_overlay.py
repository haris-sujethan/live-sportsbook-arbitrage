import os, sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "Arial"
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from scipy.ndimage import gaussian_filter

os.makedirs("charts", exist_ok=True)
DB = os.path.join(os.path.dirname(__file__), "../odds_history.db")

print("Loading...", flush=True)
conn = sqlite3.connect(DB)
df = pd.read_sql_query("""
    SELECT fixture_id, outcome_id, price, timestamp, start_time
    FROM   odds_history
    WHERE  sport_slug  = 'tennis'
    AND    bookmaker   = 'pinnacle'
    AND    start_time IS NOT NULL AND start_time != ''
    ORDER  BY fixture_id, outcome_id, timestamp
""", conn)
conn.close()

df["ts"]      = pd.to_datetime(df["timestamp"],  utc=True, errors="coerce")
df["st"]      = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
df["minutes"] = (df["ts"] - df["st"]).dt.total_seconds() / 60.0
df = df.sort_values(["fixture_id", "outcome_id", "timestamp"])
df["prev"]   = df.groupby(["fixture_id", "outcome_id"])["price"].shift(1)
df["change"] = (df["price"] - df["prev"]).abs()

df = df[
    (df["change"]  > 0)     &
    df["minutes"].notna()   &
    (df["minutes"] >= -120) &
    (df["minutes"] <=  180) &
    (df["price"]   >= 1.01) &
    (df["price"]   <= 12.0)
].copy()

Y_CAP = 0.45
df = df[df["change"] <= Y_CAP].copy()

x_all = df["minutes"].values
y_all = df["change"].values

pre  = df[df["minutes"] < 0]
live = df[df["minutes"] >= 0]
print(f"Pre: {len(pre):,}   Live: {len(live):,}   Total: {len(df):,}", flush=True)

print("Computing density...", flush=True)

X_BINS = np.linspace(-120, 180, 500)
Y_BINS = np.linspace(0, Y_CAP, 300)

counts, xedges, yedges = np.histogram2d(x_all, y_all, bins=[X_BINS, Y_BINS])
counts = gaussian_filter(counts, sigma=1)

xi = np.clip(np.searchsorted(xedges, x_all) - 1, 0, len(X_BINS) - 2)
yi = np.clip(np.searchsorted(yedges, y_all) - 1, 0, len(Y_BINS) - 2)
density = counts[xi, yi]

order    = density.argsort()
x_sorted = x_all[order]
y_sorted = y_all[order]
d_sorted = density[order]

np.random.seed(42)
y_sorted = np.clip(y_sorted + np.random.normal(0, 0.003, len(y_sorted)), 0, Y_CAP)

cmap = LinearSegmentedColormap.from_list(
    "heat",
    ["#dddddd", "#ffdd00", "#ff6600", "#ff0000", "#cc0077"],
    N=512,
)
norm = LogNorm(
    vmin=max(d_sorted[d_sorted > 0].min(), 1.5),
    vmax=d_sorted.max(),
)

print("Plotting...", flush=True)
fig, ax = plt.subplots(figsize=(18, 8), facecolor="white")
ax.set_facecolor("white")

sc = ax.scatter(
    x_sorted, y_sorted,
    c=d_sorted,
    cmap=cmap,
    norm=norm,
    s=1.1,
    alpha=0.13,
    linewidths=0,
    rasterized=True,
    zorder=2,
)

ax.axvline(x=0, color="#888888", linewidth=0.9, linestyle="--", alpha=0.6, zorder=3)

ax.set_xlim(-120, 180)
ax.set_ylim(0, Y_CAP)

ax.set_xticks([-120, -90, -60, -30, 0, 30, 60, 90, 120, 150, 180])
ax.set_xticklabels(
    ["-120", "-90", "-60", "-30", "0", "30", "60", "90", "120", "150", "180"],
    fontsize=9, color="#333333",
)
ax.set_yticks([0, 0.1, 0.2, 0.3, 0.4])
ax.set_yticklabels(["0", "0.10", "0.20", "0.30", "0.40"],
                   fontsize=9, color="#333333")

ax.tick_params(length=3, colors="#555555")
for spine in ax.spines.values():
    spine.set_edgecolor("#bbbbbb")

ax.set_xlabel("minutes relative to match start", fontsize=10, color="#333333", labelpad=8)
ax.set_ylabel("price move (decimal odds)",        fontsize=10, color="#333333", labelpad=8)
ax.grid(False)

ax.text(-118, Y_CAP * 0.97, f"pre-match  ({len(pre):,} changes)",
        fontsize=9, color="#555555", va="top", ha="left")
ax.text(2, Y_CAP * 0.97, f"in-play  ({len(live):,} changes)",
        fontsize=9, color="#cc4400", va="top", ha="left")

ax.set_title(
    f"Pinnacle · tennis · every price move · Feb–May 2026",
    fontsize=10, color="#333333", pad=10, loc="left",
)

plt.tight_layout()
out = "charts/kde_overlay.png"
plt.savefig(out, dpi=220, bbox_inches="tight", facecolor="white")
print(f"Saved → {out}")
