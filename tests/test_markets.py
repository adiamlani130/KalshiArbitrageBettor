"""Leakage tests for the Markets vs stocks and Strategies pages (app/stocks.js, app/strategies.js).
Runs tests/markets_harness.js in Node: every trade decision is computed, all prices after a cutoff day are
scrambled, and the decisions made up to the cutoff must be identical."""
import json, os, subprocess, unittest

class NoFutureDataInMarketStrategies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try: out = subprocess.run(["node", os.path.join(os.path.dirname(__file__), "markets_harness.js")], capture_output=True, text=True, timeout=600)
        except FileNotFoundError: raise unittest.SkipTest("node is not installed")
        if out.returncode: raise AssertionError(out.stderr[-600:])
        cls.r = json.loads(out.stdout.strip().splitlines()[-1])

    def check(self, k, minimum):
        self.assertGreaterEqual(self.r[k]["n"], minimum, f"too few {k} decisions to be a real test")
        self.assertTrue(self.r[k]["same"], f"{k}: a decision changed when only future prices changed")

    def test_lag_trade(self): self.check("lag", 200)                 # Kalshi moves, trade the stock at the next open
    def test_stock_first_then_kalshi(self): self.check("rev", 200)    # stock moves, trade the contract at 5pm
    def test_second_order_basket(self): self.check("basket", 20)      # basket chosen from earlier days only
    def test_walk_forward_hedge(self): self.check("hedge", 1000)      # hedge size from earlier days only
    def test_options_model(self): self.check("options", 500)          # options-implied odds from prices up to that day
    def test_the_harness_can_see_a_leak(self):
        self.assertGreater(self.r["canary"]["n"], 0); self.assertFalse(self.r["canary"]["same"], "scrambling did not touch the future")

if __name__ == "__main__":
    unittest.main()
