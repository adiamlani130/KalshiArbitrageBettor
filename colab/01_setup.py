# Cell 1 of every Colab session: shared helpers for Kalshi's public API (no key needed).
import requests, pandas as pd, numpy as np, time
from datetime import datetime, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"

def get(path, **p):
    time.sleep(0.1)  # stay under rate limits
    return requests.get(BASE + path, params={k: v for k, v in p.items() if v is not None}).json()

def all_mk(series, hist=False, n=6000):
    """Settled markets for a series. Older markets live under /historical/."""
    out, cur = [], None
    while True:
        r = get("/historical/markets" if hist else "/markets", series_ticker=series, limit=1000,
                cursor=cur, status=None if hist else "settled")
        out += r.get("markets", []); cur = r.get("cursor")
        if not cur or len(out) >= n: return out

def cdl(series, tk, a, b, interval=1):
    """1-minute candles; tries the live endpoint, then the historical archive."""
    for path in [f"/series/{series}/markets/{tk}/candlesticks", f"/historical/markets/{tk}/candlesticks"]:
        c = get(path, start_ts=a, end_ts=b, period_interval=interval).get("candlesticks")
        if c: return c
    return []

def f(c, k):
    """Read a close price. Live data uses 'close_dollars', the archive uses 'close'."""
    v = c.get(k) or {}; v = v.get("close_dollars", v.get("close"))
    return float(v) if v is not None else np.nan

vf = lambda x: float(x.get("volume_fp") or x.get("volume") or 0)

# Look up series tickers, e.g.:
# series = pd.json_normalize(get("/series", category="Sports")["series"])
# print(series[series.title.str.contains("ATP|NBA", case=False)][["ticker", "title"]])
