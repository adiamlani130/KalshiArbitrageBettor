"""The Edge Lab's betting engine in Python: the same rules as app/paths.js, so results can be
checked outside the browser and swept in bulk (see discover.py). Reads the published data in app/data/.

A game is a dict: date, league, names, fav (0/1), win (0/1, or -1 for a draw), step (minutes per sample),
pre [[bidA, askA], [bidB, askB]] in cents, and bid/ask price paths for both sides.
"""
import json, math, os
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "app", "data")
STAKE = 10.0

def fee(price, contracts):
    """Kalshi taker fee in dollars: 7% x contracts x price x (1 - price), rounded up to the cent."""
    return math.ceil(0.07 * contracts * price * (1 - price) * 100 - 1e-9) / 100

def pnl(price, won, stake=STAKE):
    """Profit on `stake` dollars of contracts bought at `price` (0-1) and held to the result."""
    c = stake / price
    return (c - stake if won else -stake) - fee(price, c)

def _js(path):
    with open(path, encoding="utf-8") as f: text = f.read()
    return json.loads(text[text.index("=", text.index("=") + 1 if text.startswith("(") else 0) + 1:].rstrip().rstrip(";"))

def index():
    return _js(os.path.join(DATA, "sports_index.js"))

def decode(s, code):
    """One character per price; '~' (or anything unknown) repeats the last real price."""
    out, last = [], None
    for ch in s:
        v = code.get(ch)
        if v is not None: last = v
        out.append(last)
    return out

def clean(bid, ask):
    """An empty book (bid 0, ask 100) is not a price: carry the last real quote forward."""
    for i in range(1, len(bid)):
        if bid[i] is None or ask[i] is None or ask[i] - bid[i] > 30: bid[i], ask[i] = bid[i - 1], ask[i - 1]

def load(league, idx=None):
    idx = idx or index(); meta = idx["leagues"][league]
    code = {ch: i for i, ch in enumerate(idx["alphabet"])}
    t = _js(os.path.join(DATA, f"sports_{league}.js")); ix = {c: i for i, c in enumerate(t["cols"])}
    games = []
    for r in t["rows"]:
        g = lambda k: r[ix[k]]
        ab, aa = decode(g("b"), code), decode(g("a"), code); clean(ab, aa)
        if meta["three"]:
            bb, ba = decode(g("Bb"), code), decode(g("Ba"), code); clean(bb, ba)
        else:
            bb, ba = [None if v is None else 100 - v for v in aa], [None if v is None else 100 - v for v in ab]
        def pair(k):
            a = g(k)
            if not a: return None
            b = g("B" + k) if meta["three"] else [100 - a[1], 100 - a[0]]
            return [a, b] if b else None
        pre = pair("pre")
        if not pre: continue
        mid = lambda p: (p[0] + p[1]) / 2
        et = datetime.fromtimestamp(g("ts"), timezone.utc) - timedelta(hours=5)      # close enough to New York for a date
        games.append(dict(league=league, sport=meta["sport"], step=meta["step"], date=et.strftime("%Y-%m-%d"), ts=g("ts"),
                          names=[g("A"), g("B")], home=0 if g("home") else None, win=-1 if g("draw") else (0 if g("won") else 1),
                          pre=pre, h1=pair("h1"), fav=0 if mid(pre[0]) >= mid(pre[1]) else 1, bid=[ab, bb], ask=[aa, ba], n=len(aa)))
    return games

def mid_at(g, s, i):
    b, a = g["bid"][s][i], g["ask"][s][i]
    return None if b is None or a is None else (b + a) / 2

def watch_sides(g, w):
    return {"fav": [g["fav"]], "dog": [1 - g["fav"]], "home": [0] if g["home"] == 0 else [], "away": [1] if g["home"] == 0 else []}.get(w, [0, 1])

def find(g, moment, x=None, m=10, w="fav", t=None):
    """First sample where the rule is seen: (index, side that triggered), or None. Same logic as paths.js."""
    if moment == "t":
        i = round(t / g["step"]); return (i, g["fav"]) if 0 <= i < g["n"] - 1 else None
    k = max(1, round(m / g["step"])); hi, lo = [0, 0], [100, 100]
    sides = watch_sides(g, w)
    for i in range(g["n"] - 1):
        for s in sides:
            v = mid_at(g, s, i)
            if v is None: continue
            hi[s], lo[s] = max(hi[s], v), min(lo[s], v)
            if i == 0: continue
            v0 = mid_at(g, s, 0)
            if v0 is None: continue
            if moment == "below" and v0 > x and v <= x: return i, s
            if moment == "above" and v0 < x and v >= x: return i, s
            if moment == "drop" and hi[s] - v >= x: return i, s
            if moment == "rise" and v - lo[s] >= x: return i, s
            if moment in ("crash", "spike"):
                b = mid_at(g, s, max(0, i - k))
                if b is not None and (v - b <= -x if moment == "crash" else v - b >= x): return i, s
    return None

def bet(g, moment, side, **p):
    """One bet under a rule: (price 0-1, won, side index), or None if the rule never fires. Fill is one sample later."""
    if moment in ("pre", "h1"):
        q = g[moment]
        if q is None or side not in ("fav", "dog", "home", "away"): return None
        fav = 0 if sum(q[0]) >= sum(q[1]) else 1      # the favorite at THAT moment, not later: no peeking at the closing line
        s = fav if side == "fav" else 1 - fav if side == "dog" else (0 if side == "home" else 1) if g["home"] == 0 else None
        if s is None: return None
        price = q[s][1]
    else:
        hit = find(g, moment, **p)
        if not hit: return None
        i, trig = hit; e = i + 1
        if e >= g["n"]: return None
        if side in ("leader", "trailer"):
            a, b = mid_at(g, 0, i), mid_at(g, 1, i)
            if a is None or b is None or a == b: return None
            s = 0 if (a > b) == (side == "leader") else 1
        else:
            s = {"trig": trig, "other": 1 - trig, "fav": g["fav"], "dog": 1 - g["fav"]}[side]
        price = g["ask"][s][e]
    if price is None or not 2 <= price <= 98: return None
    return price / 100, g["win"] == s, s

def summary(nets):
    """Mean return per $1 staked, its t-statistic and a one-sided p-value (normal approximation)."""
    n = len(nets)
    if n < 2: return dict(n=n, roi=0.0, t=0.0, p=1.0)
    m = sum(nets) / n; sd = math.sqrt(sum((x - m) ** 2 for x in nets) / (n - 1)); t = m / (sd / math.sqrt(n)) if sd else 0.0
    return dict(n=n, roi=m / STAKE, t=t, p=0.5 * math.erfc(t / math.sqrt(2)))

def benjamini_hochberg(pvals, q=0.10):
    """Indexes of the hypotheses that survive a false-discovery rate of q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i]); keep = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / len(pvals): keep = rank
    return sorted(order[:keep])
