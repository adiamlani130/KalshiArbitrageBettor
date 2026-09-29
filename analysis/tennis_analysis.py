"""Tennis: does betting on (or against) the ATP set-1 winner make money on Kalshi?
Run from the repo root:
    python analysis/tennis_analysis.py                                         # fresh data
    python analysis/tennis_analysis.py data/original_run results/original_run  # original Colab run"""
import os, sys
import pandas as pd, numpy as np
from common import summarize

DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = sys.argv[2] if len(sys.argv) > 2 else "results"
os.makedirs(OUT, exist_ok=True)
DISCOVERY_START = "2026-07-22"   # the months the chat first found the pattern in (Jul 22 - Sep 28)

def with_date(df):
    df = df.copy()
    df["date"] = pd.to_datetime(df.code.str[:7], format="%y%b%d").dt.strftime("%Y-%m-%d")
    return df

if os.path.exists(f"{DATA}/tennis/set1_hist.csv"):
    # Original run: newer matches (set1_all) and archive matches (set1_hist) came from separate pulls.
    hist = pd.read_csv(f"{DATA}/tennis/set1_hist.csv")   # Jan - late Jul 2026 (Kalshi archive)
    live = pd.read_csv(f"{DATA}/tennis/set1_all.csv")    # late Jul - Sep 2026 rows with prices
    live = live[live.ask.notna()]
    hist = hist[~hist.code.isin(live.code)]
    live["sample"] = "Jul-Sep (discovery)"; hist["sample"] = "Jan-Jul (test)"
    o = with_date(pd.concat([hist, live]))
    allres = with_date(pd.concat([pd.read_csv(f"{DATA}/tennis/set1_hist.csv"),
                                  pd.read_csv(f"{DATA}/tennis/set1_all.csv")]).drop_duplicates("code"))
else:
    # Fresh pull: one file covers the whole year, so split the same way by date.
    o = with_date(pd.read_csv(f"{DATA}/tennis/set1_all.csv"))
    o["sample"] = np.where(o.date >= DISCOVERY_START, "Jul-Sep (discovery)", "Jan-Jul (test)")
    allres = o.copy()
o = o[(o.ask > 0.02) & (o.ask < 0.99) & o.bid.notna()].copy()
o["won"] = o.won.astype(bool)

# Grand Slam main draws are best-of-5; everything else is best-of-3.
slams = [("2026-01-18", "2026-02-01"), ("2026-05-24", "2026-06-07"), ("2026-06-29", "2026-07-12"), ("2026-08-31", "2026-09-13")]
o["best_of_5"] = False
for a, b in slams: o.loc[o.date.between(a, b), "best_of_5"] = True

print("Set-1 winner match win rate (all matches with results, incl. unpriced):")
allres["bo5"] = False
for a, b in slams: allres.loc[allres.date.between(a, b), "bo5"] = True
print(allres.groupby("bo5").won.agg(["size", "mean"]).rename(index={False: "best-of-3", True: "best-of-5"}))

b3 = o[~o.best_of_5]
rows = []
def add(x, price, win, label):
    r = summarize(label, price, win, x.date, "2026-07-15", "Tennis (best-of-3)")
    if r: rows.append(r)
back, fade = b3.ask, 1 - b3.bid                      # fade = buy the set-1 LOSER's contract
add(b3, back, b3.won, "Bet every set-1 winner")
m = b3.ask >= 0.8;  add(b3[m], back[m], b3.won[m], "Bet set-1 winner at -400 or shorter")
m = b3.ask >= 0.9;  add(b3[m], back[m], b3.won[m], "Bet set-1 winner at -900 or shorter")
add(b3, fade, ~b3.won, "Bet against every set-1 winner")
m = (b3.ask >= 0.7) & (b3.ask < 0.9)
for s in ["Jul-Sep (discovery)", "Jan-Jul (test)"]:
    mm = m & (b3["sample"] == s); add(b3[mm], fade[mm], ~b3.won[mm], f"Bet against set-1 winner at -233 to -900: {s}")
m = (b3.ask >= 0.7) & (b3.ask < 0.8); add(b3[m], fade[m], ~b3.won[m], "Bet against set-1 winner at -233 to -400")
bo5 = o[o.best_of_5]; add(bo5, bo5.ask, bo5.won, "Best-of-5: bet every set-1 winner")

res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/tennis_strategies.csv", index=False)
print(res[["strategy", "bets", "won_pct", "typical_odds", "net", "return_pct"]].to_string(index=False))
