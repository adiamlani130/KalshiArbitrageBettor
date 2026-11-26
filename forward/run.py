"""Daily forward test (run by .github/workflows/forward.yml; no AI involved).

1. Registers any new hypothesis file in forward/hypotheses/: its registration time is the moment THIS runner first
   sees it, and its contents are fingerprinted. A file edited after registration is disqualified (register a new
   file instead), so no idea can be backdated or quietly tuned.
2. Pulls Kalshi games (14 leagues) and non-sports markets that settled since the last run.
3. Runs every live hypothesis on them. A bet counts only if its decision came after the hypothesis was registered,
   and every bet passes the leak check in lib.evaluate (scramble the future, flip the result, decision must hold).
4. Appends bets to forward/bets/<id>.jsonl and writes forward/results.json and forward/REPORT.md.

    python forward/run.py              # pull and evaluate
    python forward/run.py --report     # just rebuild the report from saved bets
"""
import glob, hashlib, importlib.util, json, math, os, random, sys, time
from concurrent.futures import ThreadPoolExecutor
import lib as L

HERE = os.path.dirname(os.path.abspath(__file__))
HYP, BETS = os.path.join(HERE, "hypotheses"), os.path.join(HERE, "bets")
LEDGER, STATE = os.path.join(HERE, "ledger.json"), os.path.join(HERE, "state.json")
MAX_MARKETS = 1500          # newly settled non-sports markets sampled per run (at random, never by volume or result)
MIN_N, BREAK_N, Q = 30, 100, 0.05

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def load_json(p, d):
    if not os.path.exists(p): return d
    with open(p) as f: return json.load(f)
def save_json(p, v):
    with open(p, "w") as f: json.dump(v, f, indent=1, sort_keys=True)

def module(path):
    spec = importlib.util.spec_from_file_location("hyp_" + os.path.basename(path)[:-3], path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

# ------------------------------------------------------------------ 1. registry
def register(now):
    ledger = load_json(LEDGER, {})
    for path in sorted(glob.glob(os.path.join(HYP, "[!_]*.py"))):
        hid = os.path.basename(path)[:-3]
        sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
        e = ledger.get(hid)
        if e is None:
            try:
                m = module(path); assert m.DOMAIN in ("games", "markets") and callable(m.decide)
                ledger[hid] = dict(title=getattr(m, "TITLE", hid), domain=m.DOMAIN, registered=now, sha256=sha, status="live")
                log("registered", hid)
            except Exception as ex:
                ledger[hid] = dict(title=hid, registered=now, sha256=sha, status="invalid", reason=repr(ex)[:300])
        elif e["status"] == "live" and e["sha256"] != sha:
            e["status"], e["reason"] = "disqualified", "file edited after registration"
    for hid, e in ledger.items():
        if e["status"] == "live" and not os.path.exists(os.path.join(HYP, hid + ".py")): e["status"] = "retired"
    save_json(LEDGER, ledger)
    return ledger

# ------------------------------------------------------------------ 2. data
def pull_games(since):
    import pull_sports as P
    P.SINCE = time.strftime("%Y-%m-%d", time.gmtime(since - 3 * 86400))      # schedule data only for recent games
    P.CACHE = os.path.join(L.ROOT, "data", "forward_cache"); os.makedirs(P.CACHE, exist_ok=True)
    ms = P.milestones()
    out = []
    for lg, (series, _, _, _, step, three, _, _) in P.LEAGUES.items():
        mk, cur = [], None
        while True:
            r = P.get("/markets", series_ticker=series, status="settled", min_close_ts=since, limit=1000, cursor=cur)
            mk += r.get("markets", []); cur = r.get("cursor")
            if not cur or not r.get("markets"): break
        ev = {}
        for m in mk: ev.setdefault(m.get("event_ticker") or m["ticker"].rsplit("-", 1)[0], []).append(m)
        def one(x):
            try: return P.game(lg, x[0], x[1], ms.get(x[0]))
            except Exception: return None
        with ThreadPoolExecutor(8) as ex: rows = [r for r in ex.map(one, ev.items()) if r]
        gs = [g for r in rows for g in [L.to_game(lg, r, step, three)] if g]
        log(lg, len(ev), "settled games,", len(gs), "usable"); out += gs
    return out

def pull_markets(since, rnd):
    import pull_universe as U
    sers = {}
    cur = None
    while True:
        r = U.get("/series", cursor=cur)
        for s in r.get("series", []): sers[s["ticker"]] = s
        cur = r.get("cursor")
        if not cur or not r.get("series"): break
    # Kalshi's "everything settled since" listings stop after a few pages, so ask each eligible series in turn
    elig = [x for x in sers.values() if x.get("category") in U.CATS and x.get("frequency") not in U.SKIP_FREQ]
    def settled(x):
        out, cur = [], None
        while True:
            r = U.get("/markets", series_ticker=x["ticker"], status="settled", min_close_ts=since, limit=1000, cursor=cur)
            for m in r.get("markets", []):
                if m.get("result") in ("yes", "no"): m["series"], m["cat"] = x["ticker"], x["category"]; out.append(m)
            cur = r.get("cursor")
            if not cur or not r.get("markets"): return out
    with ThreadPoolExecutor(8) as ex: mk = [m for ms in ex.map(settled, elig) for m in ms]
    log(len(elig), "series checked,", len(mk), "settled markets")
    rnd.shuffle(mk); mk = mk[:MAX_MARKETS]
    import zoo as Z
    def one(m):
        try:
            rows = U.daily(m["series"], m["ticker"], U.ts(m["open_time"]), U.ts(m["close_time"]) + 86400)
            return Z.market_from(m, rows)
        except Exception: return None
    with ThreadPoolExecutor(8) as ex: out = [x for x in ex.map(one, mk) if x]
    log(len(mk), "settled non-sports markets sampled,", len(out), "usable")
    return out

# ------------------------------------------------------------------ 3. evaluate
def evaluate(ledger, items, rnd):
    for hid, e in ledger.items():
        if e["status"] != "live": continue
        h = module(os.path.join(HYP, hid + ".py"))
        path = os.path.join(BETS, hid + ".jsonl")
        seen = {json.loads(l)["item"] for l in open(path)} if os.path.exists(path) else set()
        new, leaks = [], 0
        for x in items[h.DOMAIN]:
            if x["id"] in seen or not L.wanted(h, x): continue
            try: b, leak = L.evaluate(h, x, rnd)
            except Exception as ex:
                e["errors"] = e.get("errors", 0) + 1; e["last_error"] = repr(ex)[:300]; continue
            leaks += leak
            if b and b["t"] > e["registered"]: new.append(b)
        if leaks:
            e["status"], e["reason"] = "disqualified", f"decision changed when the future was scrambled ({leaks} items)"
            log(hid, "DISQUALIFIED: leak"); continue
        with open(path, "a") as f:
            for b in new: f.write(json.dumps(b) + "\n")
        log(hid, len(new), "new bets")
    save_json(LEDGER, ledger)

# ------------------------------------------------------------------ 4. report
def stats(xs):
    n = len(xs)
    if n < 2: return dict(n=n, roi=0.0, t=0.0, p=1.0)
    m = sum(xs) / n; sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)); t = m / (sd / math.sqrt(n)) if sd else 0.0
    return dict(n=n, roi=round(m / L.STAKE, 4), t=round(t, 2), p=0.5 * math.erfc(t / math.sqrt(2)))

def report(ledger):
    rows = []
    for hid, e in sorted(ledger.items()):
        path = os.path.join(BETS, hid + ".jsonl")
        bets = [json.loads(l) for l in open(path)] if os.path.exists(path) else []
        ev = {}
        for b in bets: ev.setdefault(b["event"], []).append(b["pnl"])          # markets on one event move together
        s = stats([sum(v) / len(v) for v in ev.values()])
        rows.append(dict(id=hid, title=e["title"], domain=e.get("domain"), status=e["status"], reason=e.get("reason"),
                         registered=time.strftime("%Y-%m-%d", time.gmtime(e["registered"])), bets=len(bets), **s))
    # every hypothesis ever registered counts toward the multiple-testing correction, including failed and retired ones
    ps = sorted(r["p"] if r["n"] >= MIN_N else 1.0 for r in rows); m = len(rows)
    cut = max([p for j, p in enumerate(ps, 1) if p <= Q * j / max(m, 1)] or [-1])
    for r in rows:
        if r["status"] != "live": r["verdict"] = r["status"]
        elif r["n"] < MIN_N: r["verdict"] = "too early"
        elif r["roi"] > 0 and r["p"] <= cut and r["n"] >= BREAK_N: r["verdict"] = "BREAKTHROUGH"
        elif r["roi"] > 0 and r["p"] < 0.05: r["verdict"] = "promising"
        elif r["roi"] < 0 and r["n"] >= BREAK_N: r["verdict"] = "failing"
        else: r["verdict"] = "no edge yet"
        r["p"] = round(r["p"], 4)
    out = dict(updated=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), hypotheses=m,
               breakthroughs=[r["id"] for r in rows if r["verdict"] == "BREAKTHROUGH"], rows=rows)
    save_json(os.path.join(HERE, "results.json"), out)
    order = {"BREAKTHROUGH": 0, "promising": 1, "no edge yet": 2, "too early": 3, "failing": 4}
    lines = [f"# Forward test report", "", f"Updated {out['updated']}. {m} hypotheses registered. Bets count only if decided after "
             "registration; returns are per $1 staked after fees, averaged per event. A breakthrough needs 100+ events, a profit, "
             f"and a false-discovery-corrected p-value at q = {Q} across all {m} hypotheses.", "",
             "| Verdict | Hypothesis | Domain | Registered | Events | Return | t |", "|---|---|---|---|---:|---:|---:|"]
    for r in sorted(rows, key=lambda r: (order.get(r["verdict"], 9), -r["t"])):
        lines.append(f"| {r['verdict']} | {r['title']} (`{r['id']}`) | {r['domain']} | {r['registered']} | {r['n']} | {r['roi'] * 100:+.1f}% | {r['t']:+.2f} |")
    with open(os.path.join(HERE, "REPORT.md"), "w") as f: f.write("\n".join(lines) + "\n")
    log("report:", len(out["breakthroughs"]), "breakthroughs")
    return out

def main():
    os.makedirs(BETS, exist_ok=True)
    now = int(time.time()); rnd = random.Random(now)
    ledger = register(now)
    if "--report" not in sys.argv:
        st = load_json(STATE, {})
        since = st.get("since", now - 2 * 86400) - 6 * 3600          # small overlap; bets are de-duplicated by item
        items = {"games": pull_games(since) if any(e["domain"] == "games" and e["status"] == "live" for e in ledger.values()) else [],
                 "markets": pull_markets(since, rnd) if any(e["domain"] == "markets" and e["status"] == "live" for e in ledger.values()) else []}
        evaluate(ledger, items, rnd)
        st["since"] = now; save_json(STATE, st)
    report(ledger)

if __name__ == "__main__":
    main()
