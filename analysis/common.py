"""Shared betting math. Every bet is $10, bought at the ask, with Kalshi's trading fee
(0.07 x contracts x price x (1 - price), rounded up to the cent) subtracted."""
import math, numpy as np, pandas as pd

STAKE = 10

def fee(price, contracts):
    return math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100

def pnl(price, win, stake=STAKE):
    price = np.asarray(price, float); win = np.asarray(win, bool)
    c = stake / price
    gross = np.where(win, c - stake, -stake)
    fees = np.array([fee(p, cc) for p, cc in zip(price, c)])
    return gross - fees

def american(p):
    """Kalshi price (0-1) -> American odds string."""
    return f"{-100*p/(1-p):+.0f}" if p >= 0.5 else f"+{100*(1-p)/p:.0f}"

def summarize(label, price, win, dates, split, group=""):
    """One results row, plus the return in each half of the sample (split = date string)."""
    x = pd.DataFrame({"p": np.asarray(price, float), "w": np.asarray(win, bool), "date": np.asarray(dates)})
    x = x[(x.p > 0.009) & (x.p < 0.991)]
    if len(x) == 0: return None
    x["net"] = pnl(x.p, x.w)
    a, b = x[x.date < split].net, x[x.date >= split].net
    return dict(group=group, strategy=label, bets=len(x), won_pct=round(100 * x.w.mean(), 1),
                typical_odds=american(x.p.median()), staked=STAKE * len(x), net=round(x.net.sum(), 2),
                return_pct=round(100 * x.net.mean() / STAKE, 1),
                first_half_return_pct=round(100 * a.mean() / STAKE, 1) if len(a) else None,
                second_half_return_pct=round(100 * b.mean() / STAKE, 1) if len(b) else None)
