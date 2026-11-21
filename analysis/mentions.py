"""Does the Strategy zoo's Mentions finding replicate on markets it was never found on?

The zoo found that Kalshi "Mentions" markets (will someone say a word at an event) priced 70-80c a day before their
scheduled end resolved YES only ~49% of the time, so buying NO paid. That came from the 3 busiest markets per series.
This test was written BEFORE looking at the new data, and its rules are fixed here:

  Markets   a random sample of all settled Mentions markets (scripts/pull_mentions.py), minus every event the zoo
            already saw. No market is chosen by volume or outcome.
  Entry     the last live two-sided quote (spread <= 10c) at least a day before the scheduled end and an hour before
            the market actually closed; buy NO at 100 - bid, hold to settlement, Kalshi's fee paid.
  Primary   price 70-80c. Passes if the return, averaged per event (words on one call move together), is positive
            with t >= 2. Secondary rows (other bands, kinds of event, halves of time) are reported, not cherry-picked.

    python analysis/mentions.py      # writes results/mentions.json
"""
import json, os, re
import numpy as np
import zoo as Z

def kind(m):
    t = (m["series"] + " " + m["title"]).upper()
    if "EARNINGS" in t: return "Earnings calls"
    if re.search(r"POWELL|FED|FOMC|BESSENT|LAGARDE", t): return "Fed and central banks"
    if re.search(r"NFL|NBA|MLB|NHL|NCAA|SNF|MNF|TNF|GAME|SUPER ?BOWL|ANNOUNCER|BROADCAST|COLLINSWORTH|ROMO", t): return "Sports broadcasts"
    if re.search(r"TRUMP|BIDEN|VANCE|HARRIS|PRESS|LEAVITT|DEBATE|SPEECH|ADDRESS|RALLY|MAMDANI|NEWSOM", t): return "Politicians and press briefings"
    return "Other"

def entry(m):
    if not m["sched"]: return None
    ks = [k for k, t in enumerate(m["T"]) if t <= m["sched"] - 86400 and t <= m["close"] - 3600 and m["ask"][k] is not None]
    return ks[-1] if ks else None

def row(name, picks):
    ev = {}
    for m, k in picks: ev.setdefault(m["event"], []).append(Z.buy_hold(100 - m["bid"][k], 100 - m["settle"]))
    per = [float(np.mean(v)) for v in ev.values()]
    s = Z.stats(per) if len(per) >= 2 else dict(n=len(per), roi=None, t=None, p=None)
    won = sum(m["settle"] == 100 for m, k in picks) / len(picks) if picks else None
    imp = sum(m["mid"][k] for m, k in picks) / len(picks) / 100 if picks else None
    return dict(test=name, markets=len(picks), events=len(per), yes_won=won and round(won, 3), price_said=imp and round(imp, 3), buy_no=s)

def main():
    seen = {m["event_ticker"] for m in json.load(open(os.path.join(Z.UC, "index.json")))}
    U = [m for m in Z.load_universe("mentions_index.json") if m["event"] not in seen]
    picks = [(m, k) for m in U for k in [entry(m)] if k is not None]
    Z.log(len(U), "new Mentions markets;", len(picks), "with a live quote a day out")
    band = lambda lo, hi: [(m, k) for m, k in picks if lo <= m["mid"][k] < hi]
    prim = band(70, 80)
    times = sorted(m["T"][k] for m, k in picks); mid = times[len(times) // 2] if times else 0
    out = dict(primary=row("70-80c (the zoo's finding)", prim),
               bands=[row(f"{lo}-{lo + 10}c", band(lo, lo + 10)) for lo in range(0, 100, 10)],
               wide=row("30-80c", band(30, 80)),
               kinds=[row(f"70-80c, {k}", [x for x in prim if kind(x[0]) == k]) for k in ("Earnings calls", "Fed and central banks", "Sports broadcasts", "Politicians and press briefings", "Other")],
               halves=[row("70-80c, earlier half", [x for x in prim if x[0]["T"][x[1]] < mid]), row("70-80c, later half", [x for x in prim if x[0]["T"][x[1]] >= mid])])
    p = out["primary"]["buy_no"]; out["replicates"] = bool(p.get("roi") and p["roi"] > 0 and p["t"] >= 2)
    json.dump(out, open(os.path.join(Z.ROOT, "results", "mentions.json"), "w"), indent=1, default=float)
    for r in [out["primary"], out["wide"], *out["bands"], *out["kinds"], *out["halves"]]:
        b = r["buy_no"]; print(f'{r["test"]:42} mk {r["markets"]:5} ev {r["events"]:4} yes {r["yes_won"]} px {r["price_said"]}  NO roi {b.get("roi")} t {b.get("t")}')
    print("replicates:", out["replicates"])

if __name__ == "__main__":
    main()
