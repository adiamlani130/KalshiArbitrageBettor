"""Shared pieces of the forward-testing pipeline: turning freshly settled Kalshi games and markets into the
same dicts the backtests use, filling bets, and the automatic leak check every bet goes through.

A hypothesis is a file in forward/hypotheses/ with:

    TITLE = "Buy the team priced 85-95c in the 4th quarter"
    DOMAIN = "games"             # or "markets"
    LEAGUES = ["nba", "nfl"]      # games only; "all" for every league
    CATEGORIES = "all"            # markets only; or a list such as ["Economics", "Mentions"]
    def decide(x):                # x is one game or one market
        return [dict(i=..., side=...)]   # games: i = sample index, or "h24" / "h1" / "pre"; side = 0 (team A) or 1
                                         # markets: k = daily quote index; side = "yes" or "no"

A hypothesis file must be self-contained (no imports from other hypothesis files), so its fingerprint covers
everything it does.

decide() may return any number of decisions; only the first one per game or market is bet. It must only look at
prices at or before the decision point. The runner checks this on every single item: it scrambles everything after
the decision and flips the result, and if the decision moves, the hypothesis is disqualified for good.
"""
import copy, os, random, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in ("analysis", "scripts"): sys.path.insert(0, os.path.join(ROOT, p))
import engine as E

STAKE = E.STAKE
MOMENTS = {"h24": -3, "h1": -2, "pre": -1}       # pre-game decision points, in time order before sample 0

# ------------------------------------------------------------------ games
def carry(xs):
    out, last = [], None
    for x in xs:
        if x is not None: last = x
        out.append(last)
    return out

def to_game(lg, r, step, three):
    """A raw row from scripts/pull_sports.game() -> the engine's game dict (same as engine.load builds)."""
    ab, aa = carry(r["b"]), carry(r["a"]); la = E.clean(ab, aa)
    if three:
        bb, ba = carry(r["Bb"]), carry(r["Ba"]); lb = E.clean(bb, ba)
    else:
        bb, ba = [None if v is None else 100 - v for v in aa], [None if v is None else 100 - v for v in ab]; lb = la
    def pair(k):
        a = r.get(k)
        if not a or a[0] is None or a[1] is None: return None
        if three:
            b = r.get("B" + k)
            return [a, b] if b and b[0] is not None and b[1] is not None else None
        return [a, [100 - a[1], 100 - a[0]]]
    pre = pair("pre")
    if not pre: return None
    mid = lambda p: (p[0] + p[1]) / 2
    from datetime import datetime, timezone, timedelta
    et = datetime.fromtimestamp(r["sched"], timezone.utc) - timedelta(hours=5)
    return dict(id=r["ev"], league=lg, step=step, date=et.strftime("%Y-%m-%d"), ts=r["sched"], names=[r["A"], r["B"]],
                home=0 if r["home"] else None, win=-1 if r["draw"] else (0 if r["won"] else 1), pre=pre, h1=pair("h1"), h24=pair("h24"),
                fav=0 if mid(pre[0]) >= mid(pre[1]) else 1, bid=[ab, bb], ask=[aa, ba], live=[la, lb], n=len(aa), pvol=r.get("pvol"))

def game_time(g, i):
    if isinstance(i, str): return g["ts"] - {"h24": 86400, "h1": 3600, "pre": 300}[i]
    return g["ts"] + i * g["step"] * 60

def fill_game(g, d):
    """Price paid (cents) for a decision, or None. Pre-game: that moment's ask. In-game: the ask of the first live
    quote 1-3 samples after the decision, never a stale or empty book (the backtests' rule)."""
    i, s = d["i"], d["side"]
    if isinstance(i, str):
        q = g.get(i)
        p = q[s][1] if q else None
    else:
        e = next((j for j in range(i + 1, min(g["n"], i + 4)) if g["live"][s][j]), None)
        p = g["ask"][s][e] if e is not None else None
    return p if p is not None and 2 <= p <= 98 else None

def scramble_game(g, i, rnd):
    """Everything after decision point i replaced by noise, and the result flipped."""
    h = copy.deepcopy(g)
    h["win"] = 1 - g["win"] if g["win"] in (0, 1) else 0
    order = MOMENTS.get(i, i) if isinstance(i, str) else i
    if order < MOMENTS["h1"] and h.get("h1"): h["h1"] = [[rnd.randint(1, 49), rnd.randint(51, 99)] for _ in range(2)]
    if order < MOMENTS["pre"]: h["pre"] = [[rnd.randint(1, 49), rnd.randint(51, 99)] for _ in range(2)]
    start = max(0, order + 1) if order >= 0 else 0
    for s in (0, 1):
        for j in range(start, h["n"]):
            b = rnd.randint(1, 95); h["bid"][s][j], h["ask"][s][j], h["live"][s][j] = b, b + rnd.randint(1, 4), rnd.random() < .9
    return h

# ------------------------------------------------------------------ markets
def market_time(m, k): return m["T"][k]

def fill_market(m, d):
    k, side = d["k"], d["side"]
    if side == "yes": p = m["ask"][k]
    else: p = None if m["bid"][k] is None else 100 - m["bid"][k]
    return p if p is not None and 2 <= p <= 98 else None

def scramble_market(m, k, rnd):
    h = copy.deepcopy(m)
    h["settle"] = 100 - m["settle"]
    for j in range(k + 1, len(h["T"])):
        b = rnd.randint(1, 95); h["bid"][j], h["ask"][j] = b, b + rnd.randint(1, 9); h["mid"][j] = b + 2
    h["close"] = h["T"][k] + 86400 * rnd.randint(1, 60)        # when it really closed is also the future
    return h

# ------------------------------------------------------------------ one hypothesis on one item
def key(d): return (d.get("i", d.get("k")), d["side"])

def first(ds, domain):
    if not ds: return None
    order = (lambda d: MOMENTS.get(d["i"], d["i"]) if isinstance(d["i"], str) else d["i"]) if domain == "games" else (lambda d: d["k"])
    return min(ds, key=order)

def evaluate(h, x, rnd):
    """(bet or None, leak) for hypothesis module h on item x. The leak check reruns decide() on a copy whose future
    (after the decision) is scrambled and whose result is flipped; the first decision must not change."""
    games = h.DOMAIN == "games"
    d = first(h.decide(x), h.DOMAIN)
    if d is None: return None, False
    at = d["i"] if games else d["k"]
    y = scramble_game(x, at, rnd) if games else scramble_market(x, at, rnd)
    d2 = first(h.decide(y), h.DOMAIN)
    if d2 is None or key(d2) != key(d): return None, True
    p = fill_game(x, d) if games else fill_market(x, d)
    if p is None: return None, False
    won = (x["win"] == d["side"]) if games else ((x["settle"] == 100) == (d["side"] == "yes"))
    t = game_time(x, at) if games else market_time(x, at)
    return dict(item=x["id"], event=x["id"] if games else x["event"], t=int(t), price=p, side=d["side"], won=bool(won),
                pnl=round(E.pnl(p / 100, won), 4)), False

def wanted(h, x):
    if h.DOMAIN == "games":
        lg = getattr(h, "LEAGUES", "all"); return lg == "all" or x["league"] in lg
    c = getattr(h, "CATEGORIES", "all"); return c == "all" or x["cat"] in c
