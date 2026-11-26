"""Join Kalshi's in-game NFL prices with nflverse play-by-play (every play time-stamped), so rules can use the game's
stats (yards, turnovers, shooting...) and not just the score. Data: data/pbp/nfl_YYYY.csv.gz from
github.com/nflverse/nflverse-data (release "pbp").

A game's state at Kalshi sample i (wall-clock ts + i*step minutes) uses only plays whose time_of_day is at least
LAG seconds earlier, a buffer for the feed delay. Nothing after that moment is read.
"""
import os
from datetime import datetime, timezone, timedelta
import numpy as np, pandas as pd
import engine as E

LAG = 60
PBP = os.path.join(E.ROOT, "data", "pbp")
ABBR = {"Arizona": "ARI", "Atlanta": "ATL", "Baltimore": "BAL", "Buffalo": "BUF", "Carolina": "CAR", "Chicago": "CHI", "Cincinnati": "CIN",
        "Cleveland": "CLE", "Dallas": "DAL", "Denver": "DEN", "Detroit": "DET", "Green Bay": "GB", "Houston": "HOU", "Indianapolis": "IND",
        "Jacksonville": "JAX", "Kansas City": "KC", "Los Angeles C": "LAC", "Los Angeles R": "LA", "Las Vegas": "LV", "Miami": "MIA",
        "Minnesota": "MIN", "New England": "NE", "New Orleans": "NO", "New York G": "NYG", "New York J": "NYJ", "Philadelphia": "PHI",
        "Pittsburgh": "PIT", "Seattle": "SEA", "San Francisco": "SF", "Tampa Bay": "TB", "Tennessee": "TEN", "Washington": "WAS"}
ABBR.update({"LA Rams": "LA", "LA Chargers": "LAC", "JAC Jaguars": "JAX", "NY Giants": "NYG", "NY Jets": "NYJ", "WAS Commanders": "WAS"})
def abbr(name): return ABBR.get(name) or name.split()[0]

COLS = ["game_id", "season_type", "home_team", "away_team", "game_date", "time_of_day", "posteam", "defteam", "qtr", "game_seconds_remaining",
        "total_home_score", "total_away_score", "yards_gained", "play_type", "interception", "fumble_lost", "first_down", "sack", "penalty",
        "penalty_team", "penalty_yards", "third_down_converted", "third_down_failed", "yardline_100", "home_wp", "epa", "pass_attempt", "rush_attempt"]

def plays():
    d = pd.concat([pd.read_csv(os.path.join(PBP, f), usecols=COLS, low_memory=False) for f in sorted(os.listdir(PBP)) if f.startswith("nfl_")])
    d = d.dropna(subset=["time_of_day"])
    d["t"] = (pd.to_datetime(d["time_of_day"], utc=True, format="ISO8601") - pd.Timestamp(0, tz="UTC")).dt.total_seconds().astype("int64")
    return d.sort_values(["game_id", "t"])

def match(games, d):
    """Kalshi game -> nflverse game, by teams and a kickoff within 6 hours."""
    first = d.groupby("game_id").agg(home=("home_team", "first"), away=("away_team", "first"), t0=("t", "min"))
    by = {}
    for gid, r in first.iterrows(): by.setdefault(frozenset((r.home, r.away)), []).append((r.t0, gid, r.home))
    out = []
    for g in games:
        key = frozenset(abbr(n) for n in g["names"])
        c = [x for x in by.get(key, []) if abs(x[0] - g["ts"]) < 6 * 3600]
        if c: out.append((g, min(c, key=lambda x: abs(x[0] - g["ts"]))[1]))
    return out

def states(g, pl):
    """Cumulative stats for both Kalshi sides at every sample, from plays at least LAG seconds old. Arrays [n] per stat per side."""
    names = [abbr(x) for x in g["names"]]
    home = pl["home_team"].iloc[0]
    t = pl["t"].to_numpy(); n = g["n"]
    times = g["ts"] + np.arange(n) * g["step"] * 60 - LAG
    upto = np.searchsorted(t, times, side="right")          # plays known by each sample
    S = {}
    for s, tm in enumerate(names):
        off, de = (pl["posteam"] == tm).to_numpy(), (pl["defteam"] == tm).to_numpy()
        scrim = pl["play_type"].isin(["pass", "run"]).to_numpy()
        yg = pl["yards_gained"].fillna(0).to_numpy()
        f = {
            "yards": off & scrim, "plays": off & scrim, "turnovers": off & ((pl["interception"] == 1) | (pl["fumble_lost"] == 1)).to_numpy(),
            "first_downs": off & (pl["first_down"] == 1).to_numpy(), "sacks_taken": off & (pl["sack"] == 1).to_numpy(),
            "explosive": off & scrim & (yg >= 20), "third_conv": off & (pl["third_down_converted"] == 1).to_numpy(),
            "third_fail": off & (pl["third_down_failed"] == 1).to_numpy(), "penalty_yds": (pl["penalty_team"] == tm).to_numpy(),
            "epa": off & scrim, "pass_att": off & (pl["pass_attempt"] == 1).to_numpy(), "rush_att": off & (pl["rush_attempt"] == 1).to_numpy()}
        w = {"yards": yg, "penalty_yds": pl["penalty_yards"].fillna(0).to_numpy(), "epa": pl["epa"].fillna(0).to_numpy()}
        S[s] = {k: np.concatenate([[0], np.cumsum(np.where(m, w.get(k, 1), 0))])[upto] for k, m in f.items()}
        sc = (pl["total_home_score"] if tm == home else pl["total_away_score"]).to_numpy()
        S[s]["score"] = np.concatenate([[0], sc])[upto]
        S[s]["has_ball"] = np.concatenate([[False], off])[upto]
        wp = pl["home_wp"].to_numpy(); wp = wp if tm == home else 1 - wp
        S[s]["model_wp"] = np.concatenate([[np.nan], wp])[upto]
    S["secs_left"] = np.concatenate([[3600], pl["game_seconds_remaining"].fillna(0).to_numpy()])[upto]
    S["qtr"] = np.concatenate([[1], pl["qtr"].fillna(1).to_numpy()])[upto]
    S["started"] = upto > 0
    return S

def load():
    d = plays(); games = E.load("nfl", E.index())
    out = []
    for g, gid in match(games, d):
        pl = d[d["game_id"] == gid]
        g["pbp_id"] = gid; g["S"] = states(g, pl); g["season"] = int(gid[:4]); out.append(g)
    return out
