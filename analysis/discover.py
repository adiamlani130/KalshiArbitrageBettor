"""Search for betting rules and market-stock links that hold up on data they were not found in.

    python analysis/discover.py        # about a minute; writes results/findings.json and app/data/findings.js

Method, fixed before looking at any result:
  1. Split every league's games by date: the first 60% is the discovery period, the last 40% is held back.
  2. Try a fixed grid of rules (when to bet, a threshold, who to bet on, an optional pre-game price band)
     in each league and across all leagues. Keep a rule only if it is clearly profitable in discovery
     (t-statistic of 2 or more, 60+ bets).
  3. Test the kept rules once on the held-back games. A rule "replicates" if it survives a
     Benjamini-Hochberg false-discovery rate of 10% across everything tested there.
  The same idea is applied to Kalshi-market / stock pairs: find the link in the first half of each
  pair's days, then check its sign and strength in the second half.
"""
import json, math, os, time
import engine as E

SPLIT, MIN_DISC, MIN_HOLD = 0.60, 60, 40
RULES = (
    [("pre", s, {}) for s in ("fav", "dog", "home", "away")] + [("h1", s, {}) for s in ("fav", "dog")]
    + [("t", s, {"t": t}) for t in (30, 60, 90) for s in ("leader", "trailer")]
    + [("below", "trig", {"w": "fav", "x": x}) for x in (40, 30, 20)]
    + [("above", s, {"w": "either", "x": x}) for x in (70, 80, 90, 95) for s in ("trig", "other")]
    + [("drop", "trig", {"w": "fav", "x": x}) for x in (15, 25)]
    + [(mo, s, {"w": "either", "x": x, "m": 10}) for mo in ("crash", "spike") for x in (10, 15, 20) for s in ("trig", "other")]
)
BANDS = [("any pre-game price", 0, 101), ("favorite 50-60¢", 50, 60), ("favorite 60-75¢", 60, 75), ("favorite 75¢+", 75, 101)]
WHO = {"fav": "the pre-game favorite", "dog": "the pre-game underdog", "home": "the home team", "away": "the away team",
       "leader": "whoever is ahead on price", "trailer": "whoever is behind on price", "trig": "that team", "other": "the other team"}
WATCH = {"fav": "the favorite", "either": "either team"}

def describe(mo, side, p):
    if mo == "pre": return f"Bet {WHO[side]} just before the start"
    if mo == "h1": return f"Bet {WHO[side]} an hour before the start"
    if mo == "t": return f"{p['t']} minutes in, bet {WHO[side]}"
    w = WATCH[p["w"]]
    when = {"below": f"falls to {p['x']}¢", "above": f"reaches {p['x']}¢", "drop": f"is {p['x']}¢ off its high",
            "crash": f"drops {p['x']}¢ in 10 minutes", "spike": f"jumps {p['x']}¢ in 10 minutes"}[mo]
    return f"When {w} first {when}, bet {WHO[side]}"

def sports():
    idx = E.index(); leagues = {lg: E.load(lg, idx) for lg in idx["leagues"]}
    for gs in leagues.values():
        gs.sort(key=lambda g: g["ts"]); cut = gs[int(len(gs) * SPLIT)]["ts"]
        for g in gs: g["hold"] = g["ts"] >= cut; g["favp"] = (g["pre"][g["fav"]][0] + g["pre"][g["fav"]][1]) / 2
    tested, rows = 0, []
    for mo, side, p in RULES:
        for gs in leagues.values():       # the price band uses the favorite's price at the moment of the bet for early bets
            for g in gs: g["band"] = max(sum(g["h1"][0]), sum(g["h1"][1])) / 2 if mo == "h1" and g["h1"] else g["favp"]
        per = {lg: [(g, b) for g in gs for b in [E.bet(g, mo, side, **p)] if b] for lg, gs in leagues.items()}
        per["all"] = [x for v in list(per.values()) for x in v]
        for lg, bets in per.items():
            for band, lo, hi in BANDS:
                d = [E.pnl(b[0], b[1]) for g, b in bets if not g["hold"] and lo <= g["band"] < hi]
                h = [E.pnl(b[0], b[1]) for g, b in bets if g["hold"] and lo <= g["band"] < hi]
                if len(d) < MIN_DISC or len(h) < MIN_HOLD: continue
                tested += 1; sd, sh = E.summary(d), E.summary(h)
                rows.append(dict(rule=describe(mo, side, p), league="All 14 leagues" if lg == "all" else idx["leagues"][lg]["label"], band=band,
                                 dn=sd["n"], droi=round(sd["roi"], 4), dt=round(sd["t"], 2), hn=sh["n"], hroi=round(sh["roi"], 4), ht=round(sh["t"], 2), hp=sh["p"]))
    cand = [r for r in rows if r["dt"] >= 2]
    for i in E.benjamini_hochberg([r["hp"] for r in cand]) if cand else []: cand[i]["ok"] = True
    losers = sorted((r for r in rows if r["dt"] <= -2 and r["ht"] <= -2), key=lambda r: r["ht"])
    for r in rows: r["hp"] = round(r["hp"], 4)
    return dict(tested=tested, games=sum(len(v) for v in leagues.values()), candidates=sorted(cand, key=lambda r: r["hp"]),
                losers=losers[:25], n_losers=len(losers),
                cloud=[[r["droi"], r["hroi"]] for r in rows], agree=sum((r["droi"] > 0) == (r["hroi"] > 0) for r in rows))

def ranks(a):
    o = sorted(range(len(a)), key=lambda i: a[i]); r = [0.0] * len(a); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and a[o[j + 1]] == a[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r

def rank_corr(x, y):
    n = len(x); rx, ry = ranks(x), ranks(y); mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry)); sxx = sum((a - mx) ** 2 for a in rx); syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy: return 0.0, 0.0
    r = sxy / math.sqrt(sxx * syy); return r, r * math.sqrt((n - 2) / max(1e-9, 1 - r * r))

def stocks():
    text = open(os.path.join(E.DATA, "stocks.js")).read(); D = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))
    out = {}
    for name, lag in (("Same day", 0), ("Kalshi first, stock next day", 1), ("Stock first, Kalshi next day", -1)):
        tested, found, rep, rows = 0, 0, 0, []
        for s in D["signals"]:
            p = s["p"]
            for tk in D["themes"][s["theme"]]["tickers"]:
                c = D["px"][tk]["c"]; x, y = [], []
                for i in range(1, len(p)):
                    j = i + lag
                    if j < 1 or j >= len(p) or p[i] is None or p[i - 1] is None or c[j] is None or c[j - 1] is None: continue
                    x.append(p[i] - p[i - 1]); y.append(c[j] / c[j - 1] - 1)
                if len(x) < 80: continue
                h = len(x) // 2; tested += 1
                r1, t1 = rank_corr(x[:h], y[:h])
                if abs(t1) < 3: continue
                found += 1; r2, t2 = rank_corr(x[h:], y[h:]); ok = r1 * r2 > 0 and abs(t2) >= 2; rep += ok
                rows.append(dict(market=s["title"][:90], stock=tk, days=len(x), r1=round(r1, 2), r2=round(r2, 2), t2=round(t2, 1), ok=bool(ok)))
        rows.sort(key=lambda r: -abs(r["t2"]))
        out[name] = dict(tested=tested, found=found, replicated=rep, by_luck=round(tested * 0.0027, 1), top=rows[:15])
    return out

if __name__ == "__main__":
    res = dict(built=time.strftime("%Y-%m-%d"), split=SPLIT, sports=sports(), stocks=stocks())
    os.makedirs(os.path.join(E.ROOT, "results"), exist_ok=True)
    json.dump(res, open(os.path.join(E.ROOT, "results", "findings.json"), "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(E.DATA, "findings.js"), "w", encoding="utf-8") as f:
        f.write("window.FINDINGS="); json.dump(res, f, separators=(",", ":"), ensure_ascii=False); f.write(";\n")
    s = res["sports"]
    print(f"sports: {s['tested']} rules tested on {s['games']} games; {len(s['candidates'])} profitable in discovery; "
          f"{sum(1 for r in s['candidates'] if r.get('ok'))} replicated; {s['n_losers']} reliable losers; sign agreement {s['agree']}/{s['tested']}")
    for r in s["candidates"][:12]: print("  ", "OK " if r.get("ok") else "   ", r["rule"], "|", r["league"], "|", r["band"], "| disc", r["dn"], f"{r['droi']:+.1%}", "| hold", r["hn"], f"{r['hroi']:+.1%}", "t", r["ht"])
    for r in s["losers"][:6]: print("   LOSE", r["rule"], "|", r["league"], "|", r["band"], f"{r['droi']:+.1%} / {r['hroi']:+.1%}", r["hn"])
    for k, v in res["stocks"].items():
        print(f"stocks [{k}]: {v['tested']} pairs, {v['found']} strong in first half (luck: {v['by_luck']}), {v['replicated']} replicated")
        for r in v["top"][:4]: print("    ", r["market"][:60], r["stock"], r["r1"], r["r2"], r["t2"], r["ok"])
