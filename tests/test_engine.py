"""Checks on the betting engine, the statistics and the published data. Run: python -m unittest discover tests"""
import json, math, os, subprocess, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
import engine as E

def game(path_a, win=0, step=2, pre=(60, 61)):
    """A two-outcome game from team A's mid prices (1¢ spread), A the favorite unless pre says otherwise."""
    bid = [p - 0.5 for p in path_a]; ask = [p + 0.5 for p in path_a]
    preB = [100 - pre[1], 100 - pre[0]]
    return dict(step=step, n=len(path_a), fav=0 if sum(pre) >= sum(preB) else 1, home=0, win=win, pre=[list(pre), preB], h1=None,
                bid=[bid, [100 - a for a in ask]], ask=[ask, [100 - b for b in bid]])

class Fees(unittest.TestCase):
    def test_fee_rounds_up_to_the_cent(self):
        self.assertEqual(E.fee(0.5, 20), 0.35)            # 0.07 x 20 x 0.25 = 0.35 exactly
        self.assertEqual(E.fee(0.9, 11.111), 0.07)        # 0.0699... rounds up
        self.assertEqual(E.fee(0.01, 1), 0.01)            # never free
    def test_pnl(self):
        self.assertAlmostEqual(E.pnl(0.5, True), 10 - 0.35)
        self.assertAlmostEqual(E.pnl(0.5, False), -10 - 0.35)
    def test_fair_price_loses_only_the_fee(self):
        p = 0.7; ev = p * E.pnl(p, True) + (1 - p) * E.pnl(p, False)
        self.assertAlmostEqual(ev, -E.fee(p, 10 / p))

class Triggers(unittest.TestCase):
    def test_below_needs_a_crossing_and_fills_one_sample_later(self):
        g = game([60, 55, 45, 28, 35, 50, 70, 99], win=0)
        self.assertEqual(E.find(g, "below", x=30, w="fav"), (3, 0))
        price, won, side = E.bet(g, "below", "trig", x=30, w="fav")
        self.assertAlmostEqual(price, 0.355); self.assertTrue(won); self.assertEqual(side, 0)   # ask at sample 4, not 3
    def test_no_bet_if_already_below_at_the_start(self):
        self.assertIsNone(E.find(game([25, 20, 15, 10, 5, 1]), "below", x=30, w="fav"))
    def test_crash_window(self):
        g = game([60, 54, 48, 42, 41, 42, 43, 44])         # 18¢ over 3 samples (6 minutes), 6¢ per sample
        self.assertEqual(E.find(g, "crash", x=15, m=10, w="fav")[0], 3)
        self.assertIsNone(E.find(g, "crash", x=15, m=2, w="fav"))
    def test_other_side_is_the_complement(self):
        g = game([60, 62, 91, 93, 95, 97, 99, 99], win=0)
        price, won, side = E.bet(g, "above", "other", x=90, w="either")
        self.assertEqual(side, 1); self.assertFalse(won); self.assertAlmostEqual(price, 0.075)
    def test_no_fill_after_the_last_sample(self):
        self.assertIsNone(E.bet(game([60, 60, 60, 20]), "below", "trig", x=30, w="fav"))
    def test_empty_book_is_not_a_price(self):
        bid, ask = [40, 0, 41], [41, 100, 42]; E.clean(bid, ask)
        self.assertEqual((bid[1], ask[1]), (40, 41))

class NoPeeking(unittest.TestCase):
    def test_early_bet_uses_the_favorite_at_that_moment(self):
        g = game([70] * 5, pre=(70, 71)); g["h1"] = [[40, 41], [59, 60]]     # A was the underdog an hour out, favorite at the start
        price, _, side = E.bet(g, "h1", "fav")
        self.assertEqual(side, 1); self.assertAlmostEqual(price, 0.60)

class Stats(unittest.TestCase):
    def test_benjamini_hochberg(self):
        self.assertEqual(E.benjamini_hochberg([0.001, 0.8, 0.02, 0.5], q=0.10), [0, 2])
        self.assertEqual(E.benjamini_hochberg([0.2, 0.3, 0.9], q=0.10), [])
    def test_summary(self):
        s = E.summary([1.0, -1.0] * 50); self.assertAlmostEqual(s["roi"], 0); self.assertAlmostEqual(s["p"], 0.5)
        self.assertLess(E.summary([1.0, 0.8] * 50)["p"], 1e-6)

class PublishedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.idx = E.index(); cls.nfl = E.load("nfl", cls.idx)
    def test_every_league_file_matches_the_index(self):
        for lg, meta in self.idx["leagues"].items(): self.assertEqual(len(E.load(lg, self.idx)), meta["n"], lg)
    def test_final_price_agrees_with_the_result(self):
        agree = sum((g["ask"][0][-1] > 50) == (g["win"] == 0) for g in self.nfl)
        self.assertGreater(agree / len(self.nfl), 0.97)
    def test_in_game_prices_are_calibrated(self):
        """Teams priced 60-80¢ an hour in should win about 70% of the time: the data is not garbage, and not leaking."""
        hits = [g["win"] == 0 for g in self.nfl if g["n"] > 31 and 60 <= g["ask"][0][30] < 80]
        self.assertGreater(len(hits), 50); self.assertAlmostEqual(sum(hits) / len(hits), 0.70, delta=0.10)
    def test_browser_engine_matches_python(self):
        """Run app/paths.js in Node on the NFL file and compare bet counts and profit with this engine."""
        js = r'''
          const fs=require("fs"),vm=require("vm"),d=process.argv[1]; const w={DATASETS:{},PRESETS:[]}; w.window=w;
          const ctx=vm.createContext({window:w,Intl,Date,Math,Float32Array,Object,document:{}});
          for(const f of ["data/sports_index.js","data/sports_nfl.js"]) vm.runInContext(fs.readFileSync(d+"/"+f,"utf8"),ctx);
          let src=fs.readFileSync(d+"/paths.js","utf8").replace("const loaded = {}, loading = {};","const loaded = {}, loading = {}; window.__build = (l) => build(l);");
          vm.runInContext(src,ctx); const rows=w.__build("nfl"),ds=w.DATASETS.paths;
          const fee=(p,c)=>Math.ceil(0.07*c*p*(1-p)*100-1e-9)/100, pnl=(p,won)=>{const c=10/p;return (won?c-10:-10)-fee(p,c)};
          const run=(m,s,p)=>{let n=0,t=0;for(const r of rows){const b=ds.bet(r,m,s,p,{});if(!b||!(b.p>0.009&&b.p<0.991))continue;n++;t+=pnl(b.p,b.won)}return [n,+t.toFixed(2)]};
          console.log(JSON.stringify([run("pre","fav",{}),run("crash","trig",{w:"fav",x:15,m:10}),run("above","other",{w:"either",x:90}),run("t","leader",{t:60})]));'''
        try: out = subprocess.run(["node", "-e", js, os.path.join(E.ROOT, "app")], capture_output=True, text=True, timeout=120)
        except FileNotFoundError: self.skipTest("node is not installed")
        self.assertEqual(out.returncode, 0, out.stderr[-400:])
        rules = [("pre", "fav", {}), ("crash", "trig", dict(w="fav", x=15, m=10)), ("above", "other", dict(w="either", x=90)), ("t", "leader", dict(t=60))]
        for (n, total), (mo, side, p) in zip(json.loads(out.stdout), rules):
            bets = [b for g in self.nfl for b in [E.bet(g, mo, side, **p)] if b]
            self.assertEqual(n, len(bets), mo); self.assertAlmostEqual(total, sum(E.pnl(b[0], b[1]) for b in bets), delta=0.05, msg=mo)

if __name__ == "__main__":
    unittest.main()
