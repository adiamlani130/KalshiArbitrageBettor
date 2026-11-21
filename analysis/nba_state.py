"""Join Kalshi's in-game NBA prices with ESPN play-by-play (sportsdataverse release "espn_nba_pbp", every play
wall-clock stamped), so rules can use shooting, turnovers, rebounds and fouls, not just the score.
Files: data/pbp/nba_YYYY.parquet, YYYY = the season's end year.

As for the NFL, a game's state at a Kalshi sample uses only plays at least LAG seconds old.
"""
import os
import numpy as np, pandas as pd
import engine as E

LAG = 60
PBP = os.path.join(E.ROOT, "data", "pbp")
ESPN = {"Atlanta": "ATL", "Boston": "BOS", "Brooklyn": "BKN", "Charlotte": "CHA", "Chicago": "CHI", "Cleveland": "CLE", "Dallas": "DAL",
        "Denver": "DEN", "Detroit": "DET", "Golden State": "GS", "Houston": "HOU", "Indiana": "IND", "Los Angeles C": "LAC",
        "Los Angeles L": "LAL", "Memphis": "MEM", "Miami": "MIA", "Milwaukee": "MIL", "Minnesota": "MIN", "New Orleans": "NO",
        "New York": "NY", "New York K": "NY", "Oklahoma City": "OKC", "Orlando": "ORL", "Philadelphia": "PHI", "Phoenix": "PHX",
        "Portland": "POR", "Sacramento": "SAC", "San Antonio": "SA", "Toronto": "TOR", "Utah": "UTAH", "Washington": "WSH"}
AMBIG = {"LA": {"LAC", "LAL"}, "Los Angeles": {"LAC", "LAL"}}

def plays():
    d = pd.concat([pd.read_parquet(os.path.join(PBP, f)) for f in sorted(os.listdir(PBP)) if f.startswith("nba_")])
    d = d.dropna(subset=["wallclock"])
    d["t"] = (pd.to_datetime(d["wallclock"], utc=True, format="ISO8601") - pd.Timestamp(0, tz="UTC")).dt.total_seconds().astype("int64")
    return d.sort_values(["game_id", "t", "sequence_number"])

def options(name):
    return AMBIG.get(name) or ({ESPN[name]} if name in ESPN else set())

def match(games, d):
    first = d.groupby("game_id").agg(h=("home_team_abbrev", "first"), a=("away_team_abbrev", "first"), t0=("t", "min"))
    rows = list(first.itertuples())
    by_t = sorted(rows, key=lambda r: r.t0); T = np.array([r.t0 for r in by_t])
    out = []
    for g in games:
        o = [options(n) for n in g["names"]]
        if not all(o): continue
        lo, hi = np.searchsorted(T, g["ts"] - 3 * 3600), np.searchsorted(T, g["ts"] + 3 * 3600)
        c = [r for r in by_t[lo:hi] if (r.h in o[0] and r.a in o[1]) or (r.a in o[0] and r.h in o[1])]
        if len(c) == 1: out.append((g, c[0]))
    return out

def states(g, pl, r):
    side_home = [r.h in options(g["names"][0]) and not (r.a in options(g["names"][0]) and r.h in options(g["names"][1])), None]
    side_home[1] = not side_home[0]
    t = pl["t"].to_numpy(); n = g["n"]
    upto = np.searchsorted(t, g["ts"] + np.arange(n) * g["step"] * 60 - LAG, side="right")
    home_id = pl["home_team_id"].iloc[0]
    typ = pl["type_text"].fillna("").str.lower().to_numpy(); txt = pl["text"].fillna("").str.lower().to_numpy()
    pa = pl["points_attempted"].fillna(0).to_numpy(); made = pl["scoring_play"].fillna(False).to_numpy().astype(bool)
    shoot = pl["shooting_play"].fillna(False).to_numpy().astype(bool)
    team_home = (pl["team_id"] == home_id).to_numpy(); team_away = (pl["team_id"].notna() & (pl["team_id"] != home_id)).to_numpy()
    is_tov = np.array(["turnover" in x for x in typ])
    cum = lambda m, w=1: np.concatenate([[0], np.cumsum(np.where(m, w, 0))])[upto]
    S = {}
    for s in (0, 1):
        me = team_home if side_home[s] else team_away
        fg = me & shoot & (pa >= 2)
        S[s] = dict(fga=cum(fg), fgm=cum(fg & made), tpa=cum(fg & (pa == 3)), tpm=cum(fg & (pa == 3) & made),
                    fta=cum(me & shoot & (pa == 1)), ftm=cum(me & shoot & (pa == 1) & made),
                    tov=cum(me & is_tov),
                    oreb=cum(me & (typ == "offensive rebound")), dreb=cum(me & (typ == "defensive rebound")),
                    fouls=cum(me & (np.char.find(typ.astype(str), "foul") >= 0)))
        sc = (pl["home_score"] if side_home[s] else pl["away_score"]).ffill().fillna(0).to_numpy()
        S[s]["score"] = np.concatenate([[0], sc])[upto]
    S["secs_left"] = np.concatenate([[2880], pl["end_game_seconds_remaining"].fillna(0).to_numpy()])[upto]
    S["qtr"] = np.concatenate([[1], pl["period"].fillna(1).to_numpy()])[upto]
    S["started"] = upto > 0
    return S

def features(g):
    S = g["S"]; F = {}
    for s in (0, 1):
        a, b = S[s], S[1 - s]
        efg = lambda x: np.where(x["fga"] > 0, (x["fgm"] + 0.5 * x["tpm"]) / np.maximum(x["fga"], 1), .5)
        tp = lambda x: np.where(x["tpa"] > 0, x["tpm"] / np.maximum(x["tpa"], 1), .35)
        ft = lambda x: np.where(x["fta"] > 0, x["ftm"] / np.maximum(x["fta"], 1), .75)
        poss = lambda x: x["fga"] + 0.44 * x["fta"] + x["tov"] - x["oreb"]
        F[s] = dict(score=a["score"] - b["score"], efg=efg(a) - efg(b), three_pct=tp(a) - tp(b), ft_pct=ft(a) - ft(b),
                    shots=a["fga"] - b["fga"], fta=a["fta"] - b["fta"], tov_margin=b["tov"] - a["tov"], oreb=a["oreb"] - b["oreb"],
                    reb=(a["oreb"] + a["dreb"]) - (b["oreb"] + b["dreb"]), foul_margin=b["fouls"] - a["fouls"],
                    threes_made=a["tpm"] - b["tpm"], poss=poss(a) - poss(b))
        F[s]["price"] = np.array([np.nan if E.mid_at(g, s, i) is None else E.mid_at(g, s, i) for i in range(g["n"])])
    F["qtr"] = S["qtr"]; F["ok"] = S["started"] & (S["secs_left"] > 60)
    return F

def load():
    d = plays(); games = [g for g in E.load("nba", E.index())]
    G = []
    for g, r in match(games, d):
        pl = d[d["game_id"] == r.Index]
        g["S"] = states(g, pl, r); g["season"] = int(pl["season"].iloc[0]); g["F"] = features(g); G.append(g)
    return G
