# NBA pull (run after 01_setup.py). Outputs: nba_markets.csv, nba_prices.csv (Kalshi),
# nba_games.csv, nba_plays.csv (ESPN play-by-play). The ESPN part can run in a separate notebook.
t0, t1 = pd.Timestamp("2025-10-20", tz="UTC"), pd.Timestamp("2026-06-30", tz="UTC")
nba = all_mk("KXNBAGAME", n=10000) + all_mk("KXNBAGAME", hist=True, n=10000)
nba = [m for m in nba if t0 <= pd.Timestamp(m["close_time"]) <= t1 and m.get("result") in ("yes", "no")]
one = {}
for m in nba: one.setdefault(m.get("event_ticker", m["ticker"].rsplit("-", 1)[0]), m)  # one side per game
pd.json_normalize(list(one.values()))[["ticker", "title", "yes_sub_title", "result", "close_time"]].to_csv("nba_markets.csv", index=False)
rows = []
for m in one.values():
    T = int(pd.Timestamp(m["close_time"]).timestamp())
    for x in cdl("KXNBAGAME", m["ticker"], T - 5*3600, T):
        b, a = f(x, "yes_bid"), f(x, "yes_ask")
        if not (np.isnan(b) and np.isnan(a)): rows.append((m["ticker"], x["end_period_ts"], b, a))
pd.DataFrame(rows, columns=["ticker", "ts", "bid", "ask"]).to_csv("nba_prices.csv", index=False)

# ---- ESPN play-by-play ----
E = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
games, plays = [], []
for d in pd.date_range("2025-10-21", "2026-06-25"):
    try: evs = requests.get(f"{E}/scoreboard", params={"dates": d.strftime("%Y%m%d")}, timeout=20).json().get("events", [])
    except Exception: continue
    for e in evs:
        try: j = requests.get(f"{E}/summary", params={"event": e["id"]}, timeout=20).json()
        except Exception: continue
        t = {c["homeAway"]: c for c in j["header"]["competitions"][0]["competitors"]}
        games.append(dict(gid=e["id"], date=d.date(), home=t["home"]["team"]["abbreviation"], away=t["away"]["team"]["abbreviation"],
                          home_id=t["home"]["team"]["id"], away_id=t["away"]["team"]["id"],
                          home_pts=t["home"].get("score"), away_pts=t["away"].get("score")))
        for p in j.get("plays", []):
            if p.get("shootingPlay") or p.get("scoringPlay"):
                plays.append((e["id"], p.get("wallclock"), p["period"]["number"], p["clock"]["displayValue"],
                              p.get("homeScore"), p.get("awayScore"), (p.get("team") or {}).get("id"),
                              "three point" in p.get("text", "").lower(), bool(p.get("scoringPlay"))))
pd.DataFrame(games).to_csv("nba_games.csv", index=False)
pd.DataFrame(plays, columns=["gid", "wallclock", "period", "clock", "home", "away", "team_id", "is3", "made"]).to_csv("nba_plays.csv", index=False)
