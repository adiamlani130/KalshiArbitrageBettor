"""Pull a broad sample of settled Kalshi markets outside sports, with their daily bid and ask over their whole
life, for the Strategy zoo (analysis/zoo.py). No API key needed. Resumable (cached in data/universe_cache/).

    python scripts/pull_universe.py              # about 20-40 minutes
    python scripts/pull_universe.py --list       # just count what would be pulled

What it saves, per market: category, series, event, title, outcome, open/close time, volume, and one row per day
[day-end timestamp, yes bid, yes ask, last trade] in cents. Markets are sampled evenly: at most PER_SERIES of the
busiest settled markets from each series, so no single series (say, daily bitcoin ranges) dominates.

For events whose outcomes are mutually exclusive (exactly one market resolves YES), every market in the event is
pulled, so the zoo can check for a Dutch book: buying every outcome for less than $1, or selling all for more.
"""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "universe_cache")
SINCE = "2024-09-01"
CATS = {"Economics", "Financials", "Politics", "Elections", "Crypto", "Companies", "Science and Technology",
        "Entertainment", "Climate and Weather", "Mentions", "World", "Commodities", "Health", "Social", "Transportation"}
SKIP_FREQ = {"daily", "hourly", "fifteen_min", "weekly"}     # high-frequency series would swamp the sample
PER_SERIES, MIN_VOLUME, MAX_SERIES_PER_CAT = 3, 5000, 260

_local, _lock, _next = threading.local(), threading.Lock(), [0.0]
def get(path, **p):
    s = getattr(_local, "s", None) or requests.Session(); _local.s = s
    for attempt in range(7):
        with _lock:
            wait = _next[0] - time.time(); _next[0] = max(time.time(), _next[0]) + 0.075
        if wait > 0: time.sleep(wait)
        try:
            r = s.get(BASE + path, params={k: v for k, v in p.items() if v is not None}, timeout=30)
            if r.status_code in (429, 500, 502, 503): time.sleep(1.5 * (attempt + 1)); continue
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return {}
def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def ts(iso): return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
vol = lambda m: float(m.get("volume_fp") or m.get("volume") or 0)

def cached(name, fn):
    path = os.path.join(CACHE, name + ".json")
    if os.path.exists(path):
        try: return json.load(open(path))
        except Exception: pass
    v = fn(); json.dump(v, open(path, "w")); return v

def series_list():
    def fetch():
        out, cur = [], None
        while True:
            r = get("/series", cursor=cur); out += r.get("series", []); cur = r.get("cursor")
            if not cur or not r.get("series"): return [{k: x.get(k) for k in ("ticker", "title", "category", "frequency")} for x in out]
    return cached("series", fetch)

def markets(series):
    out = {}
    for path, extra in (("/markets", {"status": "settled"}), ("/historical/markets", {})):
        cur = None
        while True:
            r = get(path, series_ticker=series, limit=1000, cursor=cur, **extra)
            for m in r.get("markets", []): out.setdefault(m["ticker"], m)
            cur = r.get("cursor")
            if not cur or not r.get("markets") or len(out) > 4000: break
    # expected/latest expiration are set when the market is listed; close_time can move earlier when the event
    # happens, so "days left" must come from the scheduled times, never from close_time
    keep = ("ticker event_ticker title yes_sub_title result open_time close_time expected_expiration_time "
            "latest_expiration_time expiration_time can_close_early volume_fp volume").split()
    return [{k: m.get(k) for k in keep} for m in out.values() if m.get("result") in ("yes", "no")]

def daily(series, tk, a, b):
    for path in (f"/series/{series}/markets/{tk}/candlesticks", f"/historical/markets/{tk}/candlesticks"):
        got = []
        t = a
        while t < b:
            e = min(b, t + 4000 * 86400)
            got += get(path, start_ts=t, end_ts=e, period_interval=1440).get("candlesticks") or []
            t = e
        if got: break
    rows = []
    for c in sorted(got, key=lambda c: c["end_period_ts"]):
        f = lambda k: (lambda v: None if v is None else round(float(v) * 100))((c.get(k) or {}).get("close_dollars", (c.get(k) or {}).get("close")))
        rows.append([c["end_period_ts"], f("yes_bid"), f("yes_ask"), f("price")])
    return rows

def main():
    os.makedirs(CACHE, exist_ok=True)
    S = [s for s in series_list() if s["category"] in CATS and s["frequency"] not in SKIP_FREQ]
    by = {}
    for s in S: by.setdefault(s["category"], []).append(s)
    import random
    rnd = random.Random(7); chosen = []
    for c, xs in by.items():
        rnd.shuffle(xs); chosen += xs[:MAX_SERIES_PER_CAT]
    log(len(S), "eligible series;", len(chosen), "sampled across", len(by), "categories")
    if "--list" in sys.argv: return
    def one_series(s):
        ms = cached("mk_" + s["ticker"], lambda: markets(s["ticker"]))
        ms = [m for m in ms if vol(m) >= MIN_VOLUME and (m.get("close_time") or "") >= SINCE]
        return s, sorted(ms, key=lambda m: -vol(m))
    with ThreadPoolExecutor(8) as ex: lists = list(ex.map(one_series, chosen))
    todo, events = [], {}
    for s, ms in lists:
        for m in ms[:PER_SERIES]: todo.append((s, m))
        for m in ms: events.setdefault((s["ticker"], m["event_ticker"]), []).append(m)
    # mutually exclusive events: all outcomes present, exactly one YES, 3+ outcomes; keep the busiest few per series
    me, per = [], {}
    for (ser, et), ms in sorted(events.items(), key=lambda kv: -sum(vol(m) for m in kv[1])):
        if len(ms) >= 3 and sum(m["result"] == "yes" for m in ms) == 1 and per.get(ser, 0) < 2:
            per[ser] = per.get(ser, 0) + 1; me.append((ser, et, ms))
    me = me[:400]
    have = {m["ticker"] for _, m in todo}
    s_of = {s["ticker"]: s for s in chosen}
    for ser, et, ms in me:
        for m in ms:
            if m["ticker"] not in have: todo.append((s_of[ser], m)); have.add(m["ticker"])
    log(len(todo), "markets to pull (", len(me), "mutually exclusive events )")
    def pull(x):
        s, m = x
        a, b = ts(m["open_time"]), ts(m["close_time"]) + 86400
        return cached("d_" + m["ticker"], lambda: daily(s["ticker"], m["ticker"], max(a, ts(SINCE + "T00:00:00Z") - 120 * 86400), b))
    done = 0
    with ThreadPoolExecutor(8) as ex:
        for _ in ex.map(pull, todo):
            done += 1
            if done % 500 == 0: log(done, "of", len(todo))
    json.dump([dict(cat=s["category"], series=s["ticker"], **m) for s, m in todo], open(os.path.join(CACHE, "index.json"), "w"))
    json.dump([[ser, et, [m["ticker"] for m in ms]] for ser, et, ms in me], open(os.path.join(CACHE, "events.json"), "w"))
    log("done")

if __name__ == "__main__":
    main()
