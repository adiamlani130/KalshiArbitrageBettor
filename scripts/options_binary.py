"""Price a Kalshi "will X close above K?" market a second way: with a tight call spread from the live
options chain, then compare the two. This is the real version of the Strategies page's "Options vs
Kalshi" tab, which has to rebuild option prices from a volatility index.

A call spread that buys the K1 call and sells the K2 call pays K2 - K1 if the stock finishes above K2
and nothing below K1. Its price divided by (K2 - K1) is therefore the options market's chance of
finishing above the middle of that range (the Breeden-Litzenberger idea, one strike pair at a time).

    export ALPACA_KEY=...  ALPACA_SECRET=...     # Alpaca keys with options data (paper keys work)
    python scripts/options_binary.py SPY 2026-12-31 700 KXINXPOS-26DEC31H1900-T6845.5

Arguments: underlying, option expiry (YYYY-MM-DD), strike in the underlying's own units, Kalshi ticker.
For an index market, use the ETF and convert the level yourself (S&P 500 at 7,000 is roughly SPY 700).

Read-only: it places no orders. It has not been run against a live Alpaca account in this project, so
check its first output against a broker screen before relying on it. Not investment advice.
"""
import os, sys, time
import requests

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
DATA = "https://data.alpaca.markets"

def chain(underlying, expiry):
    key, secret = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
    if not key or not secret: raise SystemExit("Set ALPACA_KEY and ALPACA_SECRET first.")
    out, token = {}, None
    while True:
        r = requests.get(f"{DATA}/v1beta1/options/snapshots/{underlying}", timeout=30,
                         headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                         params={"expiration_date": expiry, "type": "call", "limit": 1000, "page_token": token})
        if r.status_code >= 400: raise SystemExit(f"Alpaca said {r.status_code}: {r.text[:200]}")
        j = r.json()
        for sym, snap in (j.get("snapshots") or {}).items():
            q = snap.get("latestQuote") or {}
            if q.get("bp") and q.get("ap"): out[int(sym[-8:]) / 1000] = (q["bp"], q["ap"])      # strike -> (bid, ask)
        token = j.get("next_page_token")
        if not token: return dict(sorted(out.items()))

def kalshi(ticker):
    r = requests.get(f"{KALSHI}/markets/{ticker}", timeout=30).json().get("market")
    if not r: raise SystemExit(f"Kalshi has no market {ticker}.")
    return float(r["yes_bid_dollars"]) * 100, float(r["yes_ask_dollars"]) * 100, r.get("title", "")

def main():
    if len(sys.argv) != 5: raise SystemExit(__doc__)
    und, expiry, strike, ticker = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    calls = chain(und, expiry)
    below = [k for k in calls if k < strike][-3:]; above = [k for k in calls if k > strike][:3]
    if not below or not above: raise SystemExit(f"No {und} calls on both sides of {strike} for {expiry}.")
    k1, k2 = below[-1], above[0]
    mid = lambda k: sum(calls[k]) / 2
    fair = (mid(k1) - mid(k2)) / (k2 - k1) * 100
    # what you would really pay or receive: buy the spread at the asks/bids against you, or sell it
    buy = (calls[k1][1] - calls[k2][0]) / (k2 - k1) * 100
    sell = (calls[k1][0] - calls[k2][1]) / (k2 - k1) * 100
    yb, ya, title = kalshi(ticker)
    print(f"{title}\n  Kalshi Yes: bid {yb:.0f}c, ask {ya:.0f}c")
    print(f"{und} {expiry} call spread {k1:g}/{k2:g}: implies {fair:.1f}% (buy at {buy:.1f}, sell at {sell:.1f})")
    if yb > buy + 2: print(f"GAP: sell Kalshi Yes at {yb:.0f}c (buy No) and buy the call spread at {buy:.1f}: about {yb - buy:.1f} points locked in before fees.")
    elif ya < sell - 2: print(f"GAP: buy Kalshi Yes at {ya:.0f}c and sell the call spread at {sell:.1f}: about {sell - ya:.1f} points locked in before fees.")
    else: print("No gap wide enough to cover both bid/ask spreads.")
    print("Check that the two contracts settle on the same price, date and time before trading: an index market and an ETF option do not match exactly.")

if __name__ == "__main__":
    main()
