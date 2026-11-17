"""Paper-trade the "lag trade" from the Markets vs Stocks lab with an Alpaca PAPER account (fake money).

The idea: a Kalshi probability jumps (say a tariff ruling goes from 40% to 55%) but a stock that should
care has not moved yet. This script checks that rule on live prices and, if it fires, places a paper
order for the stock. Run it again later (for example once a day) and it closes positions whose holding
period is over.

    export ALPACA_KEY=...  ALPACA_SECRET=...        # keys from a PAPER account at alpaca.markets
    python scripts/alpaca_paper.py signal.json            # dry run: prints what it would do
    python scripts/alpaca_paper.py signal.json --trade    # places the paper order

signal.json comes from the lab's "Paper trade" tab. Example:
    {"kalshi_ticker": "KXFEDDECISION-26DEC-C25", "symbol": "TLT", "move_points": 5, "lookback_days": 1,
     "stock_direction_when_probability_rises": "up", "max_stock_move_pct": 0.5, "hold_days": 3,
     "dollars_per_trade": 1000, "hedge_with_spy": false}

It only ever talks to Alpaca's paper endpoint. Research tool, not investment advice.
"""
import json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
PAPER = "https://paper-api.alpaca.markets"          # paper trading only; never the live endpoint
DATA = "https://data.alpaca.markets"
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "paper_state.json")

def kalshi_probability(ticker, days):
    """Probability now and `days` trading days ago (4pm New York time), as numbers from 0 to 100."""
    series = ticker.split("-")[0]
    now = int(time.time())
    for path in (f"/series/{series}/markets/{ticker}/candlesticks", f"/historical/markets/{ticker}/candlesticks"):
        for attempt in range(5):
            r = requests.get(KALSHI + path, params=dict(start_ts=now - (days + 6) * 86400, end_ts=now, period_interval=60), timeout=30)
            if r.status_code != 429: break
            time.sleep(2 * (attempt + 1))               # Kalshi asked us to slow down
        cs = r.json().get("candlesticks") or []
        if cs: break
    if not cs: raise SystemExit(f"No Kalshi prices for {ticker}. Is the ticker right, and is the market still open?")
    def price(c):
        g = lambda k: (c.get(k) or {}).get("close_dollars", (c.get(k) or {}).get("close"))
        bid, ask, last = g("yes_bid"), g("yes_ask"), g("price")
        if bid is not None and ask is not None and 0 < float(ask) - float(bid) <= 0.06: return (float(bid) + float(ask)) / 2 * 100
        return float(last) * 100 if last is not None else None
    series = [(c["end_period_ts"], price(c)) for c in cs if price(c) is not None]
    then = now - days * 86400
    while datetime.fromtimestamp(then, timezone.utc).weekday() >= 5: then -= 86400      # step back over the weekend
    before = [p for t, p in series if t <= then]
    if not before: raise SystemExit("Not enough Kalshi history for that lookback.")
    return series[-1][1], before[-1]

class Alpaca:
    def __init__(self):
        key, secret = os.environ.get("ALPACA_KEY"), os.environ.get("ALPACA_SECRET")
        if not key or not secret: raise SystemExit("Set ALPACA_KEY and ALPACA_SECRET (paper account keys) first.")
        self.h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    def call(self, method, url, **kw):
        r = requests.request(method, url, headers=self.h, timeout=30, **kw)
        if r.status_code >= 400: raise SystemExit(f"Alpaca said {r.status_code}: {r.text[:200]}")
        return r.json() if r.text else {}
    def stock_move(self, symbol, days):
        """Percent change of the stock over the last `days` trading days."""
        start = (datetime.now(timezone.utc) - timedelta(days=days * 2 + 7)).strftime("%Y-%m-%d")
        bars = self.call("GET", f"{DATA}/v2/stocks/{symbol}/bars", params=dict(timeframe="1Day", start=start, feed="iex", limit=50)).get("bars") or []
        last = self.call("GET", f"{DATA}/v2/stocks/{symbol}/trades/latest", params=dict(feed="iex"))["trade"]["p"]
        if len(bars) < days + 1: raise SystemExit(f"Not enough price history for {symbol}.")
        return (last / bars[-days - 1]["c"] - 1) * 100, last
    def order(self, symbol, dollars, side, price):
        qty = max(1, int(dollars / price))             # whole shares, so short sales work too
        return self.call("POST", f"{PAPER}/v2/orders", json=dict(symbol=symbol, qty=qty, side=side, type="market", time_in_force="day"))
    def close(self, symbol):
        return self.call("DELETE", f"{PAPER}/v2/positions/{symbol}")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: raise SystemExit(__doc__)
    cfg, trade = json.load(open(args[0])), "--trade" in sys.argv
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"open": []}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    api = Alpaca()

    # 1. close anything whose holding period is over
    keep = []
    for pos in state["open"]:
        if today >= pos["exit_on"]:
            print(f"Closing {pos['symbol']} (opened {pos['opened']}, held {pos['hold_days']} days)")
            if trade:
                for sym in [pos["symbol"]] + (["SPY"] if pos.get("hedged") else []): api.close(sym)
            else: keep.append(pos)
        else: keep.append(pos)
    state["open"] = keep

    # 2. check the rule
    now, before = kalshi_probability(cfg["kalshi_ticker"], cfg["lookback_days"])
    move = now - before
    stock_pct, price = api.stock_move(cfg["symbol"], cfg["lookback_days"])
    sign = 1 if cfg["stock_direction_when_probability_rises"] == "up" else -1
    want = sign * (1 if move > 0 else -1)
    print(f"Kalshi {cfg['kalshi_ticker']}: {before:.1f}% -> {now:.1f}% ({move:+.1f} pts over {cfg['lookback_days']} day(s))")
    print(f"{cfg['symbol']}: {stock_pct:+.2f}% over the same days, last price ${price:.2f}")
    if abs(move) < cfg["move_points"]:
        print(f"No trade: Kalshi moved less than {cfg['move_points']} points.")
    elif cfg.get("max_stock_move_pct") is not None and stock_pct * want >= cfg["max_stock_move_pct"]:
        print("No trade: the stock has already moved that way, so there is no lag left.")
    elif any(p["symbol"] == cfg["symbol"] for p in state["open"]):
        print("No trade: already holding a position in this stock from an earlier signal.")
    else:
        side = "buy" if want > 0 else "sell"
        print(f"SIGNAL: {side.upper()} about ${cfg['dollars_per_trade']} of {cfg['symbol']}, hold {cfg['hold_days']} trading day(s)"
              + (", hedged with the opposite SPY trade" if cfg.get("hedge_with_spy") else ""))
        if trade:
            o = api.order(cfg["symbol"], cfg["dollars_per_trade"], side, price)
            print("  paper order placed:", o.get("id"), o.get("status"))
            if cfg.get("hedge_with_spy"):
                spy = api.call("GET", f"{DATA}/v2/stocks/SPY/trades/latest", params=dict(feed="iex"))["trade"]["p"]
                api.order("SPY", cfg["dollars_per_trade"], "sell" if side == "buy" else "buy", spy)
            exit_on = datetime.now(timezone.utc)
            left = cfg["hold_days"]
            while left: exit_on += timedelta(days=1); left -= exit_on.weekday() < 5
            state["open"].append(dict(symbol=cfg["symbol"], opened=today, hold_days=cfg["hold_days"], hedged=bool(cfg.get("hedge_with_spy")),
                                      exit_on=exit_on.strftime("%Y-%m-%d"), kalshi=cfg["kalshi_ticker"], side=side))
        else:
            print("  (dry run: add --trade to place the paper order)")
    if trade:
        os.makedirs(os.path.dirname(STATE), exist_ok=True); json.dump(state, open(STATE, "w"), indent=1)

if __name__ == "__main__":
    main()
