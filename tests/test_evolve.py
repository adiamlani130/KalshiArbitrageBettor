"""Leakage tests for the machine strategy search (analysis/evolve.py). Run: python -m unittest discover tests"""
import copy, os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
import engine as E
import evolve as V

class DecisionPointsUseOnlyThePast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        idx = E.index(); rnd = random.Random(3)
        cls.games = [(lg, g) for lg in ("nfl", "nba", "epl", "ufc", "atp") for g in rnd.sample(E.load(lg, idx), 25)]

    def test_rewriting_the_future_never_changes_a_decision_point(self):
        """Pick a moment i in a real game, scramble every quote after the fill window and flip the result:
        every decision point at or before i (its features and the price paid) must be unchanged."""
        rnd = random.Random(11); checked = 0
        for lg, g in self.games:
            if g["n"] < 12: continue
            i = rnd.randrange(2, g["n"] - 5)
            h = copy.deepcopy(g); h["win"] = -1 if g["win"] != -1 else 0
            for s in (0, 1):
                for j in range(i + 4, g["n"]):
                    b = rnd.randint(1, 97); h["bid"][s][j], h["ask"][s][j] = b, b + rnd.randint(1, 3); h["live"][s][j] = rnd.random() < 0.7
            before = [p for p in V.points(g, lg) if p[0] <= i]
            after = [p for p in V.points(h, lg) if p[0] <= i]
            self.assertEqual(before, after, f"{lg} game at sample {i}"); checked += len(before)
        self.assertGreater(checked, 1000)

    def test_an_hour_out_ignores_the_closing_line(self):
        """The 'one hour before' decision point must not use the line, volume or favorite from closer to the start."""
        for lg, g in self.games:
            if not g.get("h1"): continue
            h = copy.deepcopy(g); h["pre"] = [[1, 2], [97, 98]]; h["pvol"] = 10 ** 9; h["fav"] = 1 - g["fav"]
            self.assertEqual([p for p in V.points(g, lg) if p[0] == -2], [p for p in V.points(h, lg) if p[0] == -2], lg)

    def test_price_paid_is_a_later_live_ask(self):
        for lg, g in self.games:
            for order, s, feats, price in V.points(g, lg):
                if order < 0: continue
                fills = [g["ask"][s][j] for j in range(order + 1, min(g["n"], order + 4)) if g["live"][s][j]]
                self.assertTrue(fills and price == fills[0], f"{lg} sample {order}")

class SplitIsByTime(unittest.TestCase):
    def test_periods_are_in_date_order(self):
        T = V.build_table()
        last = {k: T["ts"][T["period"] == k] for k in (0, 1, 2)}
        self.assertLessEqual(last[0].max(), last[1].min()); self.assertLessEqual(last[1].max(), last[2].min())
        thr = V.Rules(T, random.Random(0)).q
        tr = T["period"] == 0
        for f, qs in thr.items():      # rule thresholds are quantiles of the search period alone
            self.assertTrue(all(T["X"][tr, V.FI[f]].min() <= q <= T["X"][tr, V.FI[f]].max() for q in qs), f)

if __name__ == "__main__":
    unittest.main()
