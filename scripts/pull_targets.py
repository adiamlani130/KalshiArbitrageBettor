"""Pull the data behind the Strategies page's "Options vs Kalshi" test.

Kalshi lists hundreds of price-target markets ("Will the S&P 500 reach 7,000 this year?", "Bitcoin on
Jan 1 between 75,000 and 80,000?"). Each is a binary option, so it can be priced a second way: from the
underlying's price and the options market's own volatility gauge (VIX for the S&P 500, VXN for the
Nasdaq-100, OVX for oil; 30-day realized volatility for bitcoin and ether, which have no free gauge).

    python scripts/pull_targets.py          # a few minutes; run pull_stocks.py first
    python scripts/pull_targets.py --build

Output: app/data/targets.js
  under   - daily close, high, low and volatility for each underlying, on the stocks lab's trading days
  targets - one row per Kalshi target market: type, strikes, dates, result, and its price each day
            (p starts at trading-day index s)
  ladder  - every macro-announcement market: Kalshi's price the evening before, and the result
"""
import json, math, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pull_stocks as P

OUT = os.path.join(P.ROOT, "app", "data", "targets.js")
# underlying: (label, Yahoo price symbol, Yahoo volatility-index symbol or None, yearly drift used in the model)
UNDER = {"spx": ("S&P 500", "^GSPC", "^VIX", 0.03), "ndx": ("Nasdaq-100", "^NDX", "^VXN", 0.03),
         "wti": ("WTI oil", "CL=F", "^OVX", 0.0), "btc": ("Bitcoin", "BTC-USD", None, 0.0), "eth": ("Ether", "ETH-USD", None, 0.0)}
# Kalshi series -> (underlying, kind). end = price at expiry; max / min = highest / lowest price reached before expiry
SERIES = {"KXINXY": ("spx", "end"), "KXINXPOS": ("spx", "end"), "KXINXMAXY": ("spx", "max"), "KXINXMINY": ("spx", "min"),
          "KXNASDAQ100Y": ("ndx", "end"), "KXNASDAQ100MAXY": ("ndx", "max"), "KXNASDAQ100MINY": ("ndx", "min"),
          "KXWTIMAX": ("wti", "max"), "KXWTIMIN": ("wti", "min"),
          "KXBTCY": ("btc", "end"), "KXBTCMAXY": ("btc", "max"), "KXBTCMINY": ("btc", "min"),
          "KXETHY": ("eth", "end"), "KXETHMAXY": ("eth", "max"), "KXETHMINY": ("eth", "min")}
MIN_VOLUME = 5000

def ohlc(sym):
    r = P.get(P.YAHOO + sym, period1=P.ts(P.START + "T00:00:00Z") - 60 * 86400, period2=int(time.time()), interval="1d")
    try:
        r = r["chart"]["result"][0]; q = r["indicators"]["quote"][0]
        return [[t, h, l, c] for t, h, l, c in zip(r["timestamp"], q["high"], q["low"], q["close"]) if c]
    except Exception:
        return []

def pick():
    out = []
    for s, (u, kind) in SERIES.items():
        for m in P.cached("mk_" + s, lambda: P.markets(s)):
            if P.fv(m) >= MIN_VOLUME and m["close_time"] > P.START and m.get("strike_type") in ("greater", "less", "between"):
                out.append((s, m))
    return out

def pull():
    for u, (_, sym, vol, _) in UNDER.items():
        P.cached("ohlc_" + u, lambda: ohlc(sym))
        if vol: P.cached("vol_" + u, lambda: ohlc(vol))
    todo = pick()
    P.log(len(todo), "target markets")
    one = lambda x: P.cached("t1d_" + x[1]["ticker"], lambda: P.candles(x[0], x[1]["ticker"], max(P.ts(x[1]["open_time"]), P.ts(P.START + "T00:00:00Z")),
                                                                    min(P.ts(x[1]["close_time"]), int(time.time())) + 86400, 1440))
    with ThreadPoolExecutor(6) as ex: list(ex.map(one, todo))
    P.log("candles done")

def build():
    load = lambda n: json.load(open(os.path.join(P.CACHE, n + ".json")))
    day = lambda t: datetime.fromtimestamp(t, P.ET).strftime("%Y-%m-%d")
    dates = [day(r[0]) for r in load("px_1d_SPY") if day(r[0]) >= P.START]; di = {d: i for i, d in enumerate(dates)}
    under = {}
    for u, (label, sym, vol, drift) in UNDER.items():
        rows = load("ohlc_" + u); n = len(dates)
        c, h, l, v = [None] * n, [None] * n, [None] * n, [None] * n
        closes = [(day(t), cl) for t, _, _, cl in rows]
        for k, (t, hi, lo, cl) in enumerate(rows):
            i = di.get(day(t))
            if i is None: continue
            c[i], h[i], l[i] = round(cl, 2), round(hi or cl, 2), round(lo or cl, 2)
            if not vol and k >= 30:     # 30-day realized volatility, annualized (crypto trades every day)
                rs = [math.log(closes[j][1] / closes[j - 1][1]) for j in range(k - 29, k + 1)]
                m = sum(rs) / 30; v[i] = round(math.sqrt(sum((x - m) ** 2 for x in rs) / 29 * 365) * 100, 1)
        if vol:
            for t, _, _, cl in load("vol_" + u):
                i = di.get(day(t))
                if i is not None: v[i] = round(cl, 2)
        under[u] = dict(label=label, drift=drift, vol_from=vol or "30-day realized", c=c, h=h, l=l, v=v)
    targets = []
    for s, m in pick():
        cs = load("t1d_" + m["ticker"])
        if len(cs) < 8: continue
        u, kind = SERIES[s]
        p = [None] * len(dates)
        for t, price in cs:
            i = di.get(day(t - 3600))          # a daily candle ends at midnight New York time: it belongs to the day before
            if i is not None: p[i] = round(price * 100, 1)
        if sum(x is not None for x in p) < 8: continue
        st, lo, hi = m["strike_type"], m.get("floor_strike"), m.get("cap_strike")
        if st == "greater": lo, hi = lo if lo is not None else hi, None
        if st == "less": lo, hi = None, hi if hi is not None else lo
        if kind == "max" and lo is None: continue
        if kind == "min" and hi is None: continue
        targets.append(dict(id=m["ticker"], u=u, kind=kind, lo=lo, hi=hi, title=(m.get("yes_sub_title") or m["title"])[:60],
                            open=day(P.ts(m["open_time"])), exp=day(P.ts(m["close_time"]) - 3600), vol=round(P.fv(m)),
                            result=m.get("result") or None, s=(a := next(i for i, x in enumerate(p) if x is not None)),
                            p=p[a:len(p) - next(i for i, x in enumerate(reversed(p)) if x is not None)]))
    ladder = []
    for s, m in load("events"):
        cs = load("c1d_" + m["ticker"]); tc = P.ts(m["close_time"])
        before = [c for c in cs if c[0] <= tc - 6 * 3600]
        if before and 0.005 < before[-1][1] < 0.995:
            ladder.append([P.SCHEDULED[s], day(tc), round(before[-1][1] * 100, 1), int(m["result"] == "yes")])
    with open(OUT, "w") as f:
        f.write("window.TARGET_DATA="); json.dump(dict(built=time.strftime("%Y-%m-%d"), under=under, targets=targets, ladder=ladder), f, separators=(",", ":")); f.write(";\n")
    P.log(len(targets), "targets,", len(ladder), "ladder markets ->", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")

if __name__ == "__main__":
    if "--build" not in sys.argv: pull()
    build()
