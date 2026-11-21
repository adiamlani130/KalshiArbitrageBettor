"""In-game NBA trend rules using shooting, turnovers, rebounds and fouls against Kalshi's live price.
Example: "the game is within 3 points but one team has shot far better (eFG%): buy the better-shooting team."

Same safeguards as nfl_trends.py: state from plays at least a minute old, fill at a live ask 1-3 samples later,
one bet per game per rule, thresholds and picks from the 2025-26 season only, graded once on 2026-27 so far,
with a false-discovery correction. Also asks the direct question: do these stats help forecast the winner once
you know Kalshi's price?

    python analysis/nba_trends.py       # writes results/nba_trends.json
"""
import json, os
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
import engine as E, nba_state as N, nfl_trends as T

STATS = ["efg", "three_pct", "ft_pct", "shots", "fta", "tov_margin", "oreb", "reb", "foul_margin", "threes_made", "poss"]
SCORE = {"trailing 10-20": (-20, -10), "trailing 4-9": (-9, -4), "within 3": (-3, 3), "leading 4-9": (4, 9), "leading 10-20": (10, 20)}
WHEN = {"1st half": (1, 2), "3rd quarter": (3, 3), "4th quarter": (4, 9)}
SEARCH, TEST = 2026, 2027

def model_test(G):
    def X(season):
        xs, ys = [], []
        for g in G:
            if g["season"] != season: continue
            F = g["F"]
            for i in range(0, g["n"], 5):
                p = F[0]["price"][i]
                if not F["ok"][i] or np.isnan(p) or not 3 <= p <= 97: continue
                xs.append([np.log(p / (100 - p))] + [F[0][k][i] for k in STATS + ["score"]]); ys.append(g["win"] == 0)
        return np.array(xs, float), np.array(ys)
    Xa, ya = X(SEARCH); Xb, yb = X(TEST); mu, sd = Xa.mean(0), Xa.std(0) + 1e-9
    out = {}
    for name, cols in (("price only", [0]), ("price + every stat", list(range(Xa.shape[1])))):
        m = LogisticRegression(max_iter=3000).fit((Xa[:, cols] - mu[cols]) / sd[cols], ya)
        out[name] = round(log_loss(yb, m.predict_proba((Xb[:, cols] - mu[cols]) / sd[cols])[:, 1]), 4)
    out["moments"] = len(yb)
    return out

def main():
    G = N.load()
    R = T.rules(G, STATS, SCORE, WHEN, train_season=SEARCH, model=False)
    bets = lambda fn, season: [x for g in G if g["season"] == season for x in [T.run(g, fn)] if x is not None]
    rows = [dict(rule=name, train=E.summary(bets(fn, SEARCH)), fn=fn) for name, fn in R]
    picked = [r for r in rows if r["train"]["n"] >= 40 and r["train"]["t"] >= 2]
    for r in picked: r["test"] = E.summary(bets(r["fn"], TEST))
    ok = E.benjamini_hochberg([r["test"]["p"] if r["test"]["n"] >= 15 else 1 for r in picked])
    for i, r in enumerate(picked): r["works"] = bool(i in ok and r["test"]["roi"] > 0)
    clean = lambda r: {k: (dict((a, round(b, 4)) for a, b in v.items()) if isinstance(v, dict) else v) for k, v in r.items() if k != "fn"}
    tested = [r for r in picked if r["test"]["n"] >= 15]
    out = dict(games={str(SEARCH): sum(g["season"] == SEARCH for g in G), str(TEST): sum(g["season"] == TEST for g in G)}, rules_tried=len(R),
               picked=len(picked), luck_expected=round(len(R) * 0.0228, 1), works=sum(r["works"] for r in picked),
               picked_positive_on_test=sum(r["test"]["roi"] > 0 for r in tested), picked_tested=len(tested),
               test_mean_roi_of_picked=round(float(np.mean([r["test"]["roi"] for r in tested] or [0])), 4),
               forecast=model_test(G), picked_rules=sorted([clean(r) for r in picked], key=lambda r: -r["test"]["t"]))
    json.dump(out, open(os.path.join(E.ROOT, "results", "nba_trends.json"), "w"), indent=1, default=float)
    print({k: v for k, v in out.items() if k != "picked_rules"})
    for r in out["picked_rules"][:25]: print(f'{r["rule"][:80]:81} train {r["train"]["n"]:4.0f} {r["train"]["roi"]:+.3f} t{r["train"]["t"]:+.1f}  test {r["test"]["n"]:3.0f} {r["test"]["roi"]:+.3f} t {r["test"]["t"]:+.2f} {"WORKS" if r["works"] else ""}')

if __name__ == "__main__":
    main()
