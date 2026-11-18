"""Build app/data/home.js: the small file behind the homepage's animations. Everything shown there is real:
a handful of real games replayed price by price, real Kalshi markets with their last price, and the headline
numbers from the strategy searches. Run after pull_sports.py, pull_stocks.py, discover.py and evolve.py.

    python scripts/build_home.py
"""
import glob, json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import engine as E

def js(name):
    path = os.path.join(E.DATA, name)
    if not os.path.exists(path): return None
    t = open(path, encoding="utf-8").read(); return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))

def games():
    """For each sport, the most recent high-volume game whose lead changed hands at least twice on price."""
    idx = E.index(); out = []
    for lg in ("nfl", "nba", "epl", "atp", "nhl", "mlb", "ncaaf", "ufc", "wta", "ncaab"):
        if lg not in idx["leagues"]: continue
        best = None
        for g in sorted(E.load(lg, idx), key=lambda g: -g["ts"])[:300]:
            m = [None if g["bid"][0][i] is None else (g["bid"][0][i] + g["ask"][0][i]) / 2 for i in range(g["n"])]
            m = [v for v in m if v is not None]
            if len(m) < 30: continue
            flips, side = 0, 0
            for v in m:
                z = 1 if v > 55 else -1 if v < 45 else 0
                if z and side and z != side: flips += 1
                if z: side = z
            score = flips * 10 + (g.get("pvol") or 0) / 1e6
            if flips >= 2 and (best is None or score > best[0]): best = (score, g, m)
        if not best: continue
        _, g, m = best
        step = max(1, len(m) // 140); pts = [round(v) for v in m[::step]] + [round(m[-1])]
        two = lg not in ("epl", "ucl", "laliga", "mls")
        out.append(dict(league=idx["leagues"][lg]["label"], date=g["date"], a=g["names"][0], b=g["names"][1], path=pts, two=two,
                        winner=None if g["win"] == -1 else g["names"][g["win"]], mins=g["n"] * g["step"]))
    return out

def tape():
    D = js("stocks.js")
    if not D: return [], None
    out = []
    for s in D["signals"]:
        if s.get("result"): continue
        p = [v for v in s["p"] if v is not None]
        if len(p) < 6 or not 3 <= p[-1] <= 97: continue
        out.append(dict(t=s["title"][:64], p=round(p[-1]), d=round(p[-1] - p[-6], 1), v=s["vol"], k=s["id"].split("-")[0]))
    out.sort(key=lambda x: -x["v"]); per, keep = {}, []
    for m in out:                                   # at most two markets from any one series, for variety
        per[m["k"]] = per.get(m["k"], 0) + 1
        if per[m["k"]] <= 2: keep.append({k: v for k, v in m.items() if k != "k"})
    return keep[:28], D["dates"][-1]

def chips():
    """Real market questions and prices for the homepage's flashing side columns."""
    import re
    out = []
    D = js("stocks.js") or {}
    for s in D.get("signals", []):
        p = [v for v in s["p"] if v is not None]
        if not p: continue
        t = re.sub(r"\s+", " ", s["title"].split(" — ")[0]).strip().upper()
        if len(t) > 58: t = t[:58].rsplit(" ", 1)[0]
        out.append([t, round(p[-1])])
    idx = E.index()
    for lg in idx["leagues"]:
        for g in sorted(E.load(lg, idx), key=lambda g: -g["ts"])[:14]:
            a, b = (g["names"][1], g["names"][0]) if g["home"] == 0 else g["names"]
            out.append([f"{a} VS. {b}".upper()[:52], round((g["pre"][0][0] + g["pre"][0][1]) / 2)])
    seen, keep = set(), []
    for t, p in out:
        if t not in seen: seen.add(t); keep.append([t, p])
    return keep

if __name__ == "__main__":
    F, V, idx = js("findings.js") or {}, js("evolved.js") or {}, E.index()
    S = js("stocks.js") or {}
    tests = sum(open(f).read().count("    def test_") for f in glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    t, asof = tape()
    out = dict(built=time.strftime("%Y-%m-%d"), games=games(), tape=t, asof=asof, chips=chips(),
               stats=dict(games=sum(l["n"] for l in idx["leagues"].values()), leagues=len(idx["leagues"]), markets=len(S.get("signals", [])),
                          stocks=len(S.get("px", {})), rules=(F.get("sports", {}).get("tested", 0) + V.get("funnel", {}).get("evaluated", 0)),
                          tests=tests, points=V.get("points", 0)),
               findings=dict(tested=F.get("sports", {}).get("tested"), survived=sum(1 for r in F.get("sports", {}).get("candidates", []) if r.get("ok")),
                             losers=F.get("sports", {}).get("n_losers"), same=F.get("stocks", {}).get("Same day", {}).get("replicated"),
                             lead=F.get("stocks", {}).get("Kalshi first, stock next day", {}).get("replicated"),
                             funnel=V.get("funnel"), gbm=(V.get("gbm") or {}).get("calib")))
    with open(os.path.join(E.DATA, "home.js"), "w", encoding="utf-8") as f:
        f.write("window.HOME="); json.dump(out, f, separators=(",", ":"), ensure_ascii=False); f.write(";\n")
    print("home.js:", len(out["games"]), "games,", len(out["tape"]), "markets,", out["stats"], round(os.path.getsize(os.path.join(E.DATA, "home.js")) / 1024), "KB")
