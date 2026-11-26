"""The forward test's safeguards (forward/): leaky ideas are caught, nothing counts from before registration, and an
idea edited after registration is disqualified. Run: python -m unittest discover tests"""
import glob, json, os, random, sys, tempfile, types, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "forward"))
import lib as L, run as R, check as C

def hyp(domain, decide, **kw):
    return types.SimpleNamespace(DOMAIN=domain, decide=decide, TITLE="t", **kw)

GAMES = [g for g in C.past_games(["nba", "nfl", "nhl"], cap=60)]
HAVE_MARKETS = os.path.exists(os.path.join(ROOT, "data", "universe_cache", "index.json"))
needs_markets = unittest.skipUnless(HAVE_MARKETS, "run scripts/pull_universe.py first")

class LeakCheck(unittest.TestCase):
    def test_a_rule_that_peeks_at_the_winner_is_caught(self):
        peek = hyp("games", lambda g: [dict(i=10, side=g["win"] if g["win"] in (0, 1) else 0)])
        leaks = sum(L.evaluate(peek, g, random.Random(1))[1] for g in GAMES if g["n"] > 20)
        self.assertGreater(leaks, 0.9 * sum(g["n"] > 20 for g in GAMES))

    def test_a_rule_that_peeks_at_later_prices_is_caught(self):
        def later(g):
            s = 0 if (g["bid"][0][-1] or 0) > 50 else 1        # who is ahead at the END of the game
            return [dict(i=5, side=s)]
        leaks = sum(L.evaluate(hyp("games", later), g, random.Random(2))[1] for g in GAMES if g["n"] > 20)
        self.assertGreater(leaks, 0.3 * len(GAMES))

    @needs_markets
    def test_a_market_rule_that_reads_the_close_time_or_result_is_caught(self):
        M = C.past_markets(cap=400)
        early = hyp("markets", lambda m: [dict(k=max(0, len([t for t in m["T"] if t <= m["close"] - 86400]) - 1), side="yes")])
        result = hyp("markets", lambda m: [dict(k=0, side="yes" if m["settle"] == 100 else "no")])
        for h in (early, result):
            self.assertGreater(sum(L.evaluate(h, m, random.Random(3))[1] for m in M), 0.3 * len(M))

    def test_the_seed_ideas_are_clean(self):
        M = C.past_markets(cap=1500) if HAVE_MARKETS else []
        for p in sorted(glob.glob(os.path.join(ROOT, "forward", "hypotheses", "[!_]*.py"))):
            h = R.module(p)
            items = GAMES if h.DOMAIN == "games" else M
            self.assertEqual(sum(L.evaluate(h, x, random.Random(4))[1] for x in items if L.wanted(h, x)), 0, p)

class Registration(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        R.HYP, R.BETS = os.path.join(self.d, "h"), os.path.join(self.d, "b")
        R.LEDGER, R.STATE = os.path.join(self.d, "ledger.json"), os.path.join(self.d, "state.json")
        os.makedirs(R.HYP); os.makedirs(R.BETS)
        with open(os.path.join(R.HYP, "x.py"), "w") as f: f.write('DOMAIN = "games"\nTITLE = "x"\ndef decide(g):\n    return [dict(i="pre", side=0)]\n')

    def test_only_decisions_after_registration_count(self):
        g = next(g for g in GAMES if g["pre"])
        ledger = R.register(g["ts"])               # registered at the scheduled start: the pre-game bet came 5 min before
        R.evaluate(ledger, {"games": [g], "markets": []}, random.Random(5))
        self.assertFalse(os.path.exists(os.path.join(R.BETS, "x.jsonl")) and open(os.path.join(R.BETS, "x.jsonl")).read().strip())
        ledger = R.register(g["ts"]); ledger["x"]["registered"] = g["ts"] - 86400; R.save_json(R.LEDGER, ledger)
        R.evaluate(json.load(open(R.LEDGER)), {"games": [g], "markets": []}, random.Random(5))
        self.assertEqual(len(open(os.path.join(R.BETS, "x.jsonl")).read().strip().splitlines()), 1)

    def test_registration_time_is_when_the_runner_first_sees_it_and_edits_disqualify(self):
        a = R.register(1000)["x"]["registered"]
        self.assertEqual(R.register(2000)["x"]["registered"], a)
        with open(os.path.join(R.HYP, "x.py"), "a") as f: f.write("# tweak\n")
        self.assertEqual(R.register(3000)["x"]["status"], "disqualified")

if __name__ == "__main__":
    unittest.main()
