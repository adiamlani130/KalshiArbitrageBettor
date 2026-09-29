"""Pull every dataset in data/ from Kalshi's public API and ESPN. No API key needed.
Same logic as the Colab scripts in colab/, but runs on any computer in one go.

    python scripts/pull_data.py              # everything (about 45 minutes)
    python scripts/pull_data.py tennis nba   # just some steps

Outputs:
  data/tennis/set1_all.csv        - ATP matches: match price ~1 min after set 1 ends, pre-match price, result
  data/tennis/set_markets.csv     - every settled set-winner market (who won each set, when it ended)
  data/tennis/match_markets.csv   - every settled match-winner market (who won, when it ended)
  data/nba/nba_markets.csv        - one Kalshi game-winner market per game (2025-26 season)
  data/nba/nba_prices.csv         - 1-minute bid/ask for those markets, 5 hours before close
  data/nba/nba_games.csv, nba_plays.csv - ESPN scores and shooting/scoring play-by-play
"""
import os, re, sys, time
import numpy as np, pandas as pd, requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T_OUT, N_OUT = os.path.join(ROOT, "data", "tennis"), os.path.join(ROOT, "data", "nba")
os.makedirs(T_OUT, exist_ok=True); os.makedirs(N_OUT, exist_ok=True)
S = requests.Session()

def get(path, **p):
    for attempt in range(5):
        time.sleep(0.1)  # stay under rate limits
        try:
            r = S.get(BASE + path, params={k: v for k, v in p.items() if v is not None}, timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** attempt); continue
            return r.json()
        except Exception:
            time.sleep(2 ** attempt)
    return {}

def all_mk(series, hist=False, n=6000):
    out, cur = [], None
    while True:
        r = get("/historical/markets" if hist else "/markets", series_ticker=series, limit=1000,
                cursor=cur, status=None if hist else "settled")
        out += r.get("markets", []); cur = r.get("cursor")
        if not cur or len(out) >= n: return out

def cdl(series, tk, a, b):
    for path in [f"/series/{series}/markets/{tk}/candlesticks", f"/historical/markets/{tk}/candlesticks"]:
        c = get(path, start_ts=a, end_ts=b, period_interval=1).get("candlesticks")
        if c: return c
    return []

# live and historical endpoints use different field names (close_dollars/volume_fp vs close/volume)
def f(c, k):
    v = c.get(k) or {}; v = v.get("close_dollars", v.get("close"))
    return float(v) if v is not None else np.nan
vf = lambda x: float(x.get("volume_fp") or x.get("volume") or 0)

def log(*a): print(*a, flush=True)

def tennis():
    match = {m["ticker"]: m for m in all_mk("KXATPMATCH") + all_mk("KXATPMATCH", hist=True, n=6000)}
    s1 = [m for m in all_mk("KXATPSETWINNER") + all_mk("KXATPSETWINNER", hist=True, n=15000)
          if m["ticker"].split("-")[2] == "1" and m.get("result") == "yes"]
    log(len(match), "match markets,", len(s1), "set-1 results")
    rows = []
    for n_done, s in enumerate(s1):
        if n_done % 200 == 0: log("tennis", n_done, "checked,", len(rows), "saved")
        code, side = s["ticker"].split("-")[1], s["ticker"].split("-")[3]
        T = int(pd.Timestamp(s["close_time"]).timestamp())
        tk = f"KXATPMATCH-{code}-{side}"; flip = tk not in match
        if flip:
            tk = next((t for t in match if t.startswith(f"KXATPMATCH-{code}-")), None)
            if not tk: continue
        c = cdl("KXATPMATCH", tk, T - 4*3600, T + 600)
        if not c: continue
        ts = np.array([x["end_period_ts"] for x in c]); vol = np.array([vf(x) for x in c])
        bid = np.array([f(x, "yes_bid") for x in c]); ask = np.array([f(x, "yes_ask") for x in c])
        j = int(np.argmax(ts >= T + 60))
        if ts[j] < T + 60: continue
        rv = pd.Series(vol).rolling(10, min_periods=1).sum().values
        i = int(np.argmax(rv > 0.25 * rv.max()))
        with np.errstate(all="ignore"):
            pre = np.nanmedian(((bid + ask) / 2)[max(0, i-20):max(1, i-2)])
        won = match[tk]["result"] == ("no" if flip else "yes")
        b, a = (1 - ask[j], 1 - bid[j]) if flip else (bid[j], ask[j])
        rows.append(dict(code=code, player=s.get("yes_sub_title"), bid=b, ask=a, won=won,
                         pre=1 - pre if flip else pre, lag=ts[j] - T, start=int(ts[i]), t_end=T))
    pd.DataFrame(rows).to_csv(f"{T_OUT}/set1_all.csv", index=False); log(len(rows), "tennis matches saved")

def markets():
    """Metadata for every settled ATP set-winner and match-winner market (no prices)."""
    cols = ["ticker", "event_ticker", "yes_sub_title", "result", "open_time", "close_time",
            "occurrence_datetime", "volume_fp", "rules_primary"]
    for series, name in [("KXATPSETWINNER", "set_markets"), ("KXATPMATCH", "match_markets")]:
        ms = all_mk(series, n=20000) + all_mk(series, hist=True, n=20000)
        df = pd.json_normalize(ms).drop_duplicates("ticker")
        df = df[df.result.isin(["yes", "no"])]
        df[[c for c in cols if c in df]].to_csv(f"{T_OUT}/{name}.csv", index=False)
        log(len(df), series, "markets saved")

def nba():
    ms = all_mk("KXNBAGAME", n=10000) + all_mk("KXNBAGAME", hist=True, n=10000)
    t0, t1 = pd.Timestamp("2025-10-20", tz="UTC"), pd.Timestamp("2026-06-30", tz="UTC")
    ms = [m for m in ms if t0 <= pd.Timestamp(m["close_time"]) <= t1 and m.get("result") in ("yes", "no")]
    one = {}
    for m in ms: one.setdefault(m.get("event_ticker", m["ticker"].rsplit("-", 1)[0]), m)
    log(len(ms), "NBA markets,", len(one), "games")
    pd.json_normalize(list(one.values()))[["ticker", "title", "yes_sub_title", "result", "close_time"]] \
        .to_csv(f"{N_OUT}/nba_markets.csv", index=False)
    rows = []
    for k, m in enumerate(one.values()):
        if k % 200 == 0: log("nba", k, "games done")
        T = int(pd.Timestamp(m["close_time"]).timestamp())
        for x in cdl("KXNBAGAME", m["ticker"], T - 5*3600, T):
            b, a = f(x, "yes_bid"), f(x, "yes_ask")
            if not (np.isnan(b) and np.isnan(a)): rows.append((m["ticker"], x["end_period_ts"], b, a))
    pd.DataFrame(rows, columns=["ticker", "ts", "bid", "ask"]).to_csv(f"{N_OUT}/nba_prices.csv", index=False)
    log(len(rows), "NBA price rows saved")

def espn():
    E = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    games, plays = [], []
    for d in pd.date_range("2025-10-21", "2026-06-25"):
        try: evs = S.get(f"{E}/scoreboard", params={"dates": d.strftime("%Y%m%d")}, timeout=20).json().get("events", [])
        except Exception: continue
        for e in evs:
            try: j = S.get(f"{E}/summary", params={"event": e["id"]}, timeout=20).json()
            except Exception: continue
            t = {c["homeAway"]: c for c in j["header"]["competitions"][0]["competitors"]}
            games.append(dict(gid=e["id"], date=d.date(), home=t["home"]["team"]["abbreviation"],
                              away=t["away"]["team"]["abbreviation"], home_id=t["home"]["team"]["id"],
                              away_id=t["away"]["team"]["id"], home_pts=t["home"].get("score"),
                              away_pts=t["away"].get("score"),
                              season_type=j["header"].get("season", {}).get("type")))
            for p in j.get("plays", []):
                if p.get("shootingPlay") or p.get("scoringPlay"):
                    plays.append((e["id"], p.get("wallclock"), p["period"]["number"], p["clock"]["displayValue"],
                                  p.get("homeScore"), p.get("awayScore"), (p.get("team") or {}).get("id"),
                                  "three point" in p.get("text", "").lower(), bool(p.get("scoringPlay"))))
        if d.day == 1: log("espn", d.date(), len(games), "games so far")
    pd.DataFrame(games).to_csv(f"{N_OUT}/nba_games.csv", index=False)
    pd.DataFrame(plays, columns=["gid", "wallclock", "period", "clock", "home", "away", "team_id", "is3", "made"]) \
        .to_csv(f"{N_OUT}/nba_plays.csv", index=False)
    log(len(games), "games,", len(plays), "plays saved")

if __name__ == "__main__":
    for step in (sys.argv[1:] or ["tennis", "markets", "nba", "espn"]):
        globals()[step]()
