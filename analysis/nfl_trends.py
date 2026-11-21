"""Thousands of in-game NFL "trend" rules that use the game's stats, not just the score, against Kalshi's live price.
Example: "a team trailing by 1-8 in the 2nd half that has out-gained its opponent by 100+ yards: buy it."

Honest by construction:
  * State at each 2-minute sample uses only plays at least a minute old (nfl_state.py); the price moves before the
    play-by-play shows a score, never after (checked in tests).
  * Fill at the ask of the first live quote 1-3 samples after the rule fires; one bet per game per rule; Kalshi fee.
  * Thresholds are quantiles of the 2025 season only. Rules are picked on the 2025 season (281 games) and graded once
    on the 2026 season so far (135 games), with a false-discovery correction across everything carried forward.

    python analysis/nfl_trends.py       # writes results/nfl_trends.json
"""
import json, os, itertools
import numpy as np
import engine as E, nfl_state as N

STATS = ["yards", "turnover_margin", "ypp", "first_downs", "explosive", "epa", "sacks_margin", "penalty_margin", "third_rate", "plays"]
SCORE = {"trailing 9-16": (-16, -9), "trailing 1-8": (-8, -1), "tied": (0, 0), "leading 1-8": (1, 8), "leading 9+": (9, 99)}
WHEN = {"1st half": (1, 2), "3rd quarter": (3, 3), "4th quarter": (4, 9)}

def features(g):
    S = g["S"]; F = {}
    for s in (0, 1):
        a, b = S[s], S[1 - s]
        ypp = lambda x: np.where(x["plays"] > 0, x["yards"] / np.maximum(x["plays"], 1), 0)
        rate = lambda x: np.where(x["third_conv"] + x["third_fail"] > 0, x["third_conv"] / np.maximum(x["third_conv"] + x["third_fail"], 1), .4)
        F[s] = dict(score=a["score"] - b["score"], yards=a["yards"] - b["yards"], turnover_margin=b["turnovers"] - a["turnovers"],
                    ypp=ypp(a) - ypp(b), first_downs=a["first_downs"] - b["first_downs"], explosive=a["explosive"] - b["explosive"],
                    epa=a["epa"] - b["epa"], sacks_margin=b["sacks_taken"] - a["sacks_taken"], penalty_margin=b["penalty_yds"] - a["penalty_yds"],
                    third_rate=rate(a) - rate(b), plays=a["plays"] - b["plays"], wp=a["model_wp"])
        F[s]["price"] = np.array([np.nan if E.mid_at(g, s, i) is None else E.mid_at(g, s, i) for i in range(g["n"])])
    F["qtr"] = S["qtr"]; F["ok"] = S["started"] & (S["secs_left"] > 120)
    return F

def rules(G):
    """Every rule is (name, function F,s -> bool array). Thresholds from the 2025 season's moments only."""
    train = [g for g in G if g["season"] == 2025]
    pool = {k: np.concatenate([g["F"][s][k][g["F"]["ok"]] for g in train for s in (0, 1)]) for k in STATS}
    q = {k: [float(np.quantile(pool[k][pool[k] > 0], x)) if (pool[k] > 0).any() else 1 for x in (.5, .8)] for k in STATS}
    R = []
    for (sn, (lo, hi)), (wn, (q0, q1)) in itertools.product(SCORE.items(), WHEN.items()):
        base = lambda F, s, lo=lo, hi=hi, q0=q0, q1=q1: F["ok"] & (F[s]["score"] >= lo) & (F[s]["score"] <= hi) & (F["qtr"] >= q0) & (F["qtr"] <= q1)
        for k in STATS:
            for j, th in enumerate(q[k]):
                lab = ["clearly", "far"][j]
                R.append((f"{sn}, {wn}, {lab} ahead on {k}: buy it", lambda F, s, b=base, k=k, th=th: b(F, s) & (F[s][k] >= th)))
                R.append((f"{sn}, {wn}, {lab} behind on {k}: buy it", lambda F, s, b=base, k=k, th=th: b(F, s) & (F[s][k] <= -th)))
        for k1, k2 in itertools.combinations(STATS, 2):
            R.append((f"{sn}, {wn}, ahead on {k1} and {k2}: buy it", lambda F, s, b=base, k1=k1, k2=k2: b(F, s) & (F[s][k1] >= q[k1][0]) & (F[s][k2] >= q[k2][0])))
            R.append((f"{sn}, {wn}, behind on {k1} and {k2}: buy it", lambda F, s, b=base, k1=k1, k2=k2: b(F, s) & (F[s][k1] <= -q[k1][0]) & (F[s][k2] <= -q[k2][0])))
    # the nflfastR win-probability model (fit on seasons before these) against Kalshi's price
    for x, (wn, (q0, q1)) in itertools.product((4, 8, 12, 16), WHEN.items()):
        R.append((f"{wn}, model win chance {x}+ points above the price: buy it", lambda F, s, x=x, q0=q0, q1=q1: F["ok"] & (F["qtr"] >= q0) & (F["qtr"] <= q1) & (F[s]["wp"] * 100 - F[s]["price"] >= x)))
        R.append((f"{wn}, model win chance {x}+ points below the price: buy it", lambda F, s, x=x, q0=q0, q1=q1: F["ok"] & (F["qtr"] >= q0) & (F["qtr"] <= q1) & (F[s]["price"] - F[s]["wp"] * 100 >= x)))
    return R

def run(g, fn):
    """First moment either side triggers (time on the outside); fill 1-3 samples later at a live ask."""
    a, b = fn(g["F"], 0), fn(g["F"], 1)
    hits = np.flatnonzero(a | b)
    if not len(hits): return None
    i = hits[0]; s = 0 if a[i] else 1
    e = next((j for j in range(i + 1, min(g["n"], i + 4)) if g["live"][s][j]), None)
    if e is None: return None
    p = g["ask"][s][e]
    if p is None or not 2 <= p <= 98: return None
    return E.pnl(p / 100, g["win"] == s)

def main():
    G = N.load()
    for g in G: g["F"] = features(g)
    R = rules(G); E_ = lambda r, season: [x for g in G if g["season"] == season for x in [run(g, r[1])] if x is not None]
    E.log = getattr(E, "log", print)
    rows = []
    for name, fn in R:
        tr = E.summary(E_((name, fn), 2025))
        rows.append(dict(rule=name, train=tr, fn=fn))
    picked = [r for r in rows if r["train"]["n"] >= 25 and r["train"]["t"] >= 2]
    for r in picked: r["test"] = E.summary(E_((r["rule"], r["fn"]), 2026))
    ok = E.benjamini_hochberg([r["test"]["p"] if r["test"]["n"] >= 10 else 1 for r in picked])
    for i, r in enumerate(picked): r["works"] = bool(i in ok and r["test"]["roi"] > 0)
    clean = lambda r: {k: (dict((a, round(b, 4)) for a, b in v.items()) if isinstance(v, dict) else v) for k, v in r.items() if k != "fn"}
    out = dict(games={"2025": sum(g["season"] == 2025 for g in G), "2026": sum(g["season"] == 2026 for g in G)}, rules_tried=len(R),
               picked=len(picked), works=sum(r["works"] for r in picked), luck_expected=round(len(R) * 0.0228, 1),
               test_mean_roi_of_picked=round(float(np.mean([r["test"]["roi"] for r in picked if r["test"]["n"] >= 10] or [0])), 4),
               picked_rules=sorted([clean(r) for r in picked], key=lambda r: -r["test"]["t"]),
               best_train=[clean(r) for r in sorted(rows, key=lambda r: -r["train"]["t"])[:15]])
    json.dump(out, open(os.path.join(E.ROOT, "results", "nfl_trends.json"), "w"), indent=1, default=float)
    print({k: v for k, v in out.items() if k not in ("picked_rules", "best_train")})
    for r in out["picked_rules"][:25]: print(f'{r["rule"][:85]:86} train {r["train"]["n"]:3.0f} {r["train"]["roi"]:+.3f}  test {r["test"]["n"]:3.0f} {r["test"]["roi"]:+.3f} t {r["test"]["t"]:+.2f} {"WORKS" if r["works"] else ""}')

if __name__ == "__main__":
    main()
