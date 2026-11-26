"""Pull a random sample of every settled Kalshi "Mentions" market (will someone say a word at an event), whatever its volume, with daily
quotes, to test the Strategy zoo's Mentions finding on markets it was never found on. Shares the universe cache.

    python scripts/pull_mentions.py        # resumable, about an hour for a random 15,000

The zoo sampled the 3 busiest markets per series by lifetime volume, which a trader can't know in advance. Here no
market is chosen by volume or outcome: the replication keeps a market only if it had a two-sided quote a day before its
scheduled end, which is known at the time.
"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
import pull_universe as U
SAMPLE = 15000

def main():
    os.makedirs(U.CACHE, exist_ok=True)
    S = [s for s in U.series_list() if s["category"] == "Mentions"]
    U.log(len(S), "Mentions series")
    def one(s):
        return s, [m for m in U.cached("mk_" + s["ticker"], lambda: U.markets(s["ticker"])) if (m.get("close_time") or "") >= U.SINCE]
    with ThreadPoolExecutor(8) as ex: lists = list(ex.map(one, S))
    todo = [(s, m) for s, ms in lists for m in ms]
    U.log(len(todo), "settled Mentions markets")
    # a random sample, chosen without looking at volume or outcome, keeps the test fair and the pull to about an hour
    import random
    random.Random(11).shuffle(todo); todo = todo[:SAMPLE]
    def pull(x):
        s, m = x
        a, b = U.ts(m["open_time"]), U.ts(m["close_time"]) + 86400
        return U.cached("d_" + m["ticker"], lambda: U.daily(s["ticker"], m["ticker"], a, b))
    done = 0
    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(pull, todo):
            done += 1
            if done % 1000 == 0: U.log(done, "of", len(todo))
    json.dump([dict(cat=s["category"], series=s["ticker"], **m) for s, m in todo], open(os.path.join(U.CACHE, "mentions_index.json"), "w"))
    U.log("done")

if __name__ == "__main__":
    main()
