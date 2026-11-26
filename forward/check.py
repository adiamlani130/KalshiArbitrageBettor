"""Check hypothesis files before they are registered: they load, run, and pass the leak check on past data.
The numbers it prints are history the idea may have been drawn from, so they are NOT evidence; only the daily
forward test counts.

    python forward/check.py forward/hypotheses/my_idea.py [more files]
"""
import json, os, random, sys, time
import lib as L, run as R

def past_games(leagues, cap=400):
    import engine as E
    idx = E.index(); out = []
    for lg in idx["leagues"]:
        if leagues != "all" and lg not in leagues: continue
        for g in E.load(lg, idx)[:cap]:
            g["league"], g["id"] = lg, f'{lg}-{g["ts"]}-{g["names"][0]}'; out.append(g)
    return out

def past_markets(cap=None):
    uc = os.path.join(L.ROOT, "data", "universe_cache", "index.json")
    if os.path.exists(uc):
        import zoo as Z
        return Z.load_universe()[:cap]
    R.MAX_MARKETS = 300
    return R.pull_markets(int(time.time()) - 5 * 86400, random.Random(1))

def main(paths):
    rnd = random.Random(7); ok = True
    cache = {}
    for p in paths:
        h = R.module(p)
        items = cache.get(h.DOMAIN) or cache.setdefault(h.DOMAIN, past_games("all") if h.DOMAIN == "games" else past_markets())
        bets, leaks, errors = [], 0, 0
        for x in items:
            if not L.wanted(h, x): continue
            try: b, leak = L.evaluate(h, x, rnd)
            except Exception as ex: errors += 1; err = repr(ex); continue
            leaks += leak
            if b: bets.append(b["pnl"])
        s = R.stats(bets)
        good = not leaks and not errors and s["n"] > 0
        ok &= good
        print(f'{"OK  " if good else "FAIL"} {os.path.basename(p)}: {s["n"]} past bets, {s["roi"] * 100:+.1f}% (history, not evidence), '
              f'{leaks} leaks, {errors} errors' + (f' (last: {err[:200]})' if errors else '') + ("" if s["n"] else " -- never fires"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main(sys.argv[1:])
