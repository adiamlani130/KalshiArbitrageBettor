"""Leakage tests for the strategy zoo (analysis/zoo.py). Run: python -m unittest discover tests"""
import copy, os, random, sys, unittest
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
import zoo as Z

def market(path, settle=100, sched_days=None, close_days=None, seed=0):
    T = [1_700_000_000 + 86400 * k for k in range(len(path))]
    return dict(id="X", cat="Test", settle=settle, T=T, mid=np.array(path, float),
                bid=[max(1, round(p) - 1) for p in path], ask=[min(99, round(p) + 1) for p in path],
                sched=T[0] + 86400 * (sched_days if sched_days is not None else len(path)),
                close=T[0] + 86400 * (close_days if close_days is not None else len(path)))

class KalshiFamiliesUseOnlyThePast(unittest.TestCase):
    def test_every_decision_ignores_later_prices(self):
        rnd = random.Random(5); checked = 0
        for _ in range(60):
            path = [50.0]
            for _ in range(70): path.append(min(97, max(3, path[-1] + rnd.choice([-12, -5, -2, 0, 2, 5, 12]))))
            for name, (desc, grid, maker) in Z.FAMILIES_A.items():
                for P in grid[:4]:
                    m = market(path); f = maker(P)
                    for i in range(1, len(path) - 1):
                        a = f(m, i)
                        h = market(path[:i + 1] + [rnd.uniform(3, 97) for _ in path[i + 1:]]); g = maker(P)
                        b = g(h, i)
                        self.assertEqual(None if a is None else a[0], None if b is None else b[0], f"{name} {P} day {i}")
                        checked += 1
        self.assertGreater(checked, 50000)

    def test_days_left_comes_from_the_schedule_not_the_close(self):
        """A market that closed early (the event happened) must look the same as one that ran to its scheduled end."""
        path = [80, 85, 88, 92, 94, 95, 96, 97, 97, 97]
        for fam in ("favorite", "longshot"):
            desc, grid, maker = Z.FAMILIES_A[fam]
            for P in grid:
                early, full = market(path, sched_days=20, close_days=6), market(path, sched_days=20, close_days=20)
                f1, f2 = maker(P), maker(P)
                self.assertEqual([f1(early, i) for i in range(5)], [f2(full, i) for i in range(5)], fam)

    def test_fills_come_after_the_signal(self):
        m = market([50, 50, 70, 75, 80, 90]); tr = Z.trade(m, 2, "yes", None, 0)
        self.assertEqual(tr["t"], m["T"][3]); self.assertEqual(tr["px"], m["ask"][3])

class SportsIndicatorsUseOnlyThePast(unittest.TestCase):
    def test_rewriting_the_rest_of_the_game_never_moves_a_trigger(self):
        import engine as E
        idx = E.index(); rnd = random.Random(9)
        games = [g for lg in ("nfl", "nba", "nhl") for g in rnd.sample(E.load(lg, idx), 30)]
        for g in games:
            g["m"] = [np.array([np.nan if g["bid"][s][i] is None else (g["bid"][s][i] + g["ask"][s][i]) / 2 for i in range(g["n"])]) for s in (0, 1)]
        # rebuild the family makers exactly as section_d does, by running it on these games only
        makers = Z.sports_makers()
        checked = 0
        for name, (desc, grid, maker) in makers.items():
            for P in grid:
                for g in games:
                    g["_memo"] = {}; hit = maker(P)(g)
                    if not hit: continue
                    s, i = hit; h = copy.deepcopy(g); h["_memo"] = {}
                    for side in (0, 1):
                        h["m"][side][i + 1:] = np.array([rnd.uniform(2, 98) for _ in range(g["n"] - i - 1)])
                    self.assertEqual(maker(P)(h), hit, f"{name} {P}"); checked += 1
        self.assertGreater(checked, 300)

if __name__ == "__main__":
    unittest.main()
