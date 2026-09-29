"""Build the Edge Lab's data file (app/data.js) from the raw CSVs in data/.
Run from the repo root after scripts/pull_data.py:   python app/build_data.py

Three tables, one row per thing you could bet on:
  tennis     - one ATP match: set-1 result, prices before the match and right after set 1,
               set lengths, who won each set, tournament and round
  nba_games  - one NBA game: prices before tip-off and at the end of Q1 / halftime / Q3,
               the score at each of those moments, rest days, playoff flag, first-half threes
  nba_swings - the first moment a team falls behind by 10, 15 or 20 points, with both teams'
               prices at that moment and the trailing team's recent three-point shooting
"""
import json, os, re, time
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)

def r(x, n=3):
    """Round for a compact JSON file; NaN -> None."""
    if x is None or (isinstance(x, float) and np.isnan(x)): return None
    if isinstance(x, (bool, np.bool_)): return bool(x)
    if isinstance(x, (int, np.integer)): return int(x)
    if isinstance(x, (float, np.floating)): return round(float(x), n)
    return x

# ------------------------------------------------------------------ tennis
ROUNDS = [(r"qualif", "Qualifying"), (r"round of 128", "R128"), (r"round of 64", "R64"), (r"round of 32", "R32"),
          (r"round of 16", "R16"), (r"quarter", "Quarterfinal"), (r"semi", "Semifinal"), (r"round robin", "Round robin"),
          (r"final", "Final")]
SLAMS = [("2026-01-18", "2026-02-01"), ("2026-05-24", "2026-06-07"), ("2026-06-29", "2026-07-12"), ("2026-08-31", "2026-09-13")]

def event_info(rule):
    m = re.search(r"match in the (.+?) after a ball", str(rule))
    if not m: return None, None
    text = re.sub(r"^\d{4} ", "", m.group(1))
    low = text.lower()
    rnd = next((name for pat, name in ROUNDS if re.search(pat, low)), None)
    cut = re.search(r"\s(qualif|round|quarter|semi|final|men singles)", low)
    return (text[:cut.start()] if cut else text).strip(), rnd

def tennis():
    t = pd.read_csv(D("tennis", "set1_all.csv"))
    sm = pd.read_csv(D("tennis", "set_markets.csv"))
    mm = pd.read_csv(D("tennis", "match_markets.csv"))
    for x in (sm, mm):
        x["close_ts"] = pd.to_datetime(x.close_time, utc=True, format="ISO8601").astype("int64") // 10**9
    sm["code"] = sm.ticker.str.split("-").str[1]; sm["set_no"] = sm.ticker.str.split("-").str[2].astype(int)
    mm["code"] = mm.ticker.str.split("-").str[1]
    sets = sm[sm.result == "yes"].groupby(["code", "set_no"]).agg(winner=("yes_sub_title", "first"),
                                                                  end=("close_ts", "min")).reset_index()
    sets = {c: g.set_index("set_no") for c, g in sets.groupby("code")}
    names = mm.groupby("code").yes_sub_title.apply(list).to_dict()
    mend = mm.groupby("code").close_ts.min().to_dict()
    rules = mm.groupby("code").rules_primary.first().to_dict()

    rows = []
    for x in t.itertuples():
        date = pd.to_datetime(x.code[:7], format="%y%b%d").strftime("%Y-%m-%d")
        if not (0 < x.bid < 1 and 0.02 < x.ask < 0.99): continue   # same cut as tennis_analysis.py
        s = sets.get(x.code)
        opp = [n for n in names.get(x.code, []) if n != x.player]
        tour, rnd = event_info(rules.get(x.code))
        bo5 = any(a <= date <= b for a, b in SLAMS)   # same rule as analysis/tennis_analysis.py
        set1 = (x.t_end - x.start) / 60
        row = dict(date=date, match=f"{x.player} vs {opp[0] if opp else '?'}", tour=tour or "Unknown",
                   rnd=rnd or "Other", bo5=bo5, s1w=x.player,
                   s1w_pre=x.pre, s1w_fav=bool(x.pre >= 0.5) if not np.isnan(x.pre) else None,
                   s1w_bid=x.bid, s1w_ask=x.ask, s1w_mid=(x.bid + x.ask) / 2,
                   jump=(x.bid + x.ask) / 2 - x.pre if not np.isnan(x.pre) else None,
                   set1_min=set1 if 15 <= set1 <= 150 else None, won=bool(x.won))
        if s is not None and 1 in s.index:
            # Kalshi often skips listing a set-3 market, so count sets from who won sets 1 and 2
            if 2 in s.index:
                row["s1w_set2"] = s.loc[2, "winner"] == x.player
                if not bo5: row["deciding_set"] = not row["s1w_set2"]
                d2 = (s.loc[2, "end"] - s.loc[1, "end"]) / 60
                row["set2_min"] = d2 if 15 <= d2 <= 150 else None
            if 3 in s.index:
                d3 = (s.loc[3, "end"] - s.loc[2, "end"]) / 60
                row["set3_min"] = d3 if 15 <= d3 <= 150 else None
        if x.code in mend:
            dm = (mend[x.code] - x.start) / 60
            row["match_min"] = dm if 40 <= dm <= 400 else None
        rows.append(row)
    print(len(rows), "tennis matches")
    return rows

# ------------------------------------------------------------------ NBA
KX = {"GSW": "GS", "NYK": "NY", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH"}

def nba():
    m = pd.read_csv(D("nba", "nba_markets.csv")); p = pd.read_csv(D("nba", "nba_prices.csv"))
    g = pd.read_csv(D("nba", "nba_games.csv")); pl = pd.read_csv(D("nba", "nba_plays.csv"))
    seg = m.ticker.str.split("-")
    m["date"] = pd.to_datetime(seg.str[1].str[:7], format="%y%b%d").dt.strftime("%Y-%m-%d")
    m["away"] = seg.str[1].str[7:10].map(lambda a: KX.get(a, a)); m["home"] = seg.str[1].str[10:13].map(lambda a: KX.get(a, a))
    m["yes"] = seg.str[2].map(lambda a: KX.get(a, a))
    g["date"] = g.date.astype(str)
    mg = m.merge(g, on=["date", "home", "away"], how="inner")
    mg["home_won"] = mg.home_pts > mg.away_pts
    pl["ts"] = pd.to_datetime(pl.wallclock, utc=True, format="ISO8601").astype("int64") // 10**9
    pl = pl.sort_values(["gid", "ts"])
    g2 = g.copy(); g2["d"] = pd.to_datetime(g2.date)
    lg = pd.concat([g2[["gid", "d", "home"]].rename(columns={"home": "team"}),
                    g2[["gid", "d", "away"]].rename(columns={"away": "team"})]).sort_values(["team", "d"])
    lg["rest"] = lg.groupby("team").d.diff().dt.days
    rest = lg.set_index(["gid", "team"]).rest.to_dict()
    pg = dict(tuple(p.groupby("ticker"))); plg = dict(tuple(pl.groupby("gid")))

    games, swings = [], []
    for x in mg.itertuples():
        if x.ticker not in pg or x.gid not in plg: continue
        pr = pg[x.ticker].sort_values("ts")
        if x.yes == x.home: hb, ha = pr.bid.values, pr.ask.values
        else: hb, ha = 1 - pr.ask.values, 1 - pr.bid.values
        ts = pr.ts.values
        q = plg[x.gid]; mar = (q.home - q.away).values; qts = q.ts.values; tip = qts.min()
        pre = np.where(ts <= tip - 300)[0]
        if not len(pre): continue
        i = pre[-1]
        if np.isnan(ha[i]) or np.isnan(hb[i]): continue
        pre_mid = (ha[i] + hb[i]) / 2

        def at(t):
            """Home ask / away ask at the first candle 1-5 minutes after t."""
            k = np.where((ts >= t + 60) & (ts <= t + 300))[0]
            if not len(k) or np.isnan(ha[k[0]]) or np.isnan(hb[k[0]]): return None
            return ha[k[0]], 1 - hb[k[0]]

        playoff = int(x.season_type) == 3
        row = dict(date=x.date, match=f"{x.away} @ {x.home}", home=x.home, away=x.away,
                   stage={2: "Regular season", 3: "Playoffs", 5: "Play-in"}.get(int(x.season_type), "Other"),
                   home_pre=pre_mid, pre_home_ask=ha[i], pre_away_ask=1 - hb[i],
                   home_rest=rest.get((x.gid, x.home)), away_rest=rest.get((x.gid, x.away)),
                   home_won=bool(x.home_won), final_margin=int(x.home_pts - x.away_pts))
        for k, name in [(1, "q1"), (2, "h"), (3, "q3")]:
            e = q[q.period == k]
            if not len(e): continue
            a = at(e.ts.iloc[-1])
            if a is None: continue
            row[f"{name}_margin"] = int(e.home.iloc[-1] - e.away.iloc[-1])
            row[f"{name}_home_ask"], row[f"{name}_away_ask"] = a
        fh = q[q.period <= 2]
        for side, tid in [("home", x.home_id), ("away", x.away_id)]:
            mine = fh[fh.team_id == tid]
            row[f"{side}_3pa_1h"] = int(mine.is3.sum()); row[f"{side}_3pm_1h"] = int((mine.is3 & mine.made).sum())
        games.append(row)

        for side, sign, tid in [("home", 1, x.home_id), ("away", -1, x.away_id)]:
            tm = mar * sign
            for th in (10, 15, 20):
                idx = np.where(tm <= -th)[0]
                if not len(idx): continue
                e = q.iloc[idx[0]]; a = at(e.ts)
                if a is None: continue
                trail_ask, lead_ask = (a[0], a[1]) if side == "home" else (a[1], a[0])
                w = q[(q.ts > e.ts - 600) & (q.ts <= e.ts)]
                mine = w[w.team_id == tid]; opp = w[(w.team_id != tid) & w.team_id.notna()]
                sofar = q[(q.ts <= e.ts) & (q.team_id == tid)]
                was_fav = pre_mid >= 0.5 if side == "home" else pre_mid < 0.5
                swings.append(dict(date=x.date, match=f"{x.away} @ {x.home}", stage=row["stage"], deficit=th,
                                   trailer=x.home if side == "home" else x.away,
                                   period=int(e.period), trailer_home=side == "home", trailer_was_fav=bool(was_fav),
                                   trail_ask=trail_ask, lead_ask=lead_ask,
                                   trail_won=bool(x.home_won if side == "home" else not x.home_won),
                                   tpa_10=int(mine.is3.sum()), tpm_10=int((mine.is3 & mine.made).sum()),
                                   opp_tpa_10=int(opp.is3.sum()), game_3pa=int(sofar.is3.sum()),
                                   game_3pct=(sofar.is3 & sofar.made).sum() / max(1, sofar.is3.sum())))
    print(len(games), "NBA games,", len(swings), "swing moments")
    return games, swings

def columnar(rows):
    cols = sorted({k for rr in rows for k in rr}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    return {"cols": cols, "rows": [[r(rr.get(c)) for c in cols] for rr in rows]}

if __name__ == "__main__":
    t = tennis(); g, s = nba()
    out = {"built": time.strftime("%Y-%m-%d"),
           "tennis": columnar(t), "nba_games": columnar(g), "nba_swings": columnar(s)}
    path = os.path.join(ROOT, "app", "data.js")
    with open(path, "w") as f:
        f.write("window.EDGE_DATA = "); json.dump(out, f, separators=(",", ":")); f.write(";\n")
    print(f"wrote {path} ({os.path.getsize(path) / 1e6:.2f} MB)")
