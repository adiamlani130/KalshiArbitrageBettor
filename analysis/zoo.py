"""Strategy zoo: SharkFin's trading strategies and prediction-market strategies, tested on Kalshi, on stocks with
Kalshi odds as the signal, and on in-game sports prices. Every family's settings are chosen on an earlier period
and graded once on a later one, the same rule SharkFin's labs use.

    python analysis/zoo.py          # a few minutes; run scripts/pull_universe.py first
Writes results/zoo.json and app/data/zoo.js.

Sections
  A. Kalshi contracts as an asset: SharkFin's technical strategies (momentum, short-term reversal, RSI(2) dips as
     in Dive Zone, EMA crossover, Donchian breakout, "new high after a big fall", Bollinger fade, MACD) and
     prediction-market ones (buy the near-certain side close to expiry, fade long shots), on ~3,000 settled markets
     outside sports. Signals use day-end prices up to day t; trades fill at the next day's close quote, buying at
     the ask and selling at the bid, after Kalshi's fee.
  B. Odds as an equity signal: a Kalshi recession index and a Fed-cut index used the way SharkFin used VIX and
     GEX (regime filters, "buy the fear"), on SPY, QQQ, IWM and TLT, trading at the next open.
  C. Dutch books: on events with mutually exclusive outcomes, days when buying every outcome cost under $1
     (or selling every one paid over $1) after fees.
  D. SharkFin's indicators on in-game sports prices (RSI dip, EMA cross, Donchian, Bollinger, IBS-style range
     reversion, breakthrough), with the 55% / 20% / 25% date split used by evolve.py.
  E. Calibration: where Kalshi's prices were too high or too low, by category and price, a day before the
     scheduled end.
"""
import json, math, os, sys, time
from datetime import datetime, timezone
import numpy as np
import engine as E

ROOT = E.ROOT
UC = os.path.join(ROOT, "data", "universe_cache")
STAKE = E.STAKE
fee = E.fee

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def iso(t): return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
def ts(s): return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()) if s else None

def stats(nets):
    s = E.summary(list(nets)); s["roi"] = round(s["roi"], 4); s["t"] = round(s["t"], 2); s["p"] = round(s["p"], 4)
    return s

def bh(p, q=0.10):
    o = sorted(range(len(p)), key=lambda i: p[i]); k = 0
    for r, i in enumerate(o, 1):
        if p[i] <= q * r / len(p): k = r
    return set(o[:k])

def buy_hold(price, settle):            # $10 of contracts at `price` cents, held to a settlement of 0 or 100
    return E.pnl(price / 100, settle == 100)

def round_trip(price, sell):            # bought at `price`, sold early at `sell` (cents): Kalshi's fee both ways
    p, q = price / 100, sell / 100; c = STAKE / p
    return c * q - STAKE - fee(p, c) - fee(q, c)

# ================================================================ A. Kalshi contracts as an asset
def market_from(m, rows):
    """One settled market (an index record) plus its daily [ts, bid, ask, last] rows -> the zoo's market dict, or None.
    Only two-sided quotes with a spread of 10c or less count as tradable."""
    if len(rows) < 4: return None
    sched = ts(m.get("expected_expiration_time")) or ts(m.get("latest_expiration_time")) or ts(m.get("expiration_time"))
    close = ts(m["close_time"])
    T, bid, ask, mid = [], [], [], []
    last = None
    for t, b, a, p in rows:
        if t > close + 86400: break
        live = b is not None and a is not None and 0 < a - b <= 10 and 1 <= a <= 99
        m_ = (a + b) / 2 if live else (p if p is not None else last)
        if m_ is None: continue
        T.append(t); bid.append(b if live else None); ask.append(a if live else None); mid.append(m_); last = m_
    if len(T) < 4: return None
    return dict(id=m["ticker"], event=m.get("event_ticker") or m["ticker"], cat=m["cat"], series=m["series"], title=m.get("title") or "",
                settle=100 if m["result"] == "yes" else 0, sched=sched, close=close, early=bool(m.get("can_close_early")),
                T=T, bid=bid, ask=ask, mid=np.array(mid, float))

def load_universe(index="index.json"):
    idx = json.load(open(os.path.join(UC, index)))
    out = []
    for m in idx:
        path = os.path.join(UC, "d_" + m["ticker"].replace("/", "~") + ".json")
        if not os.path.exists(path): continue
        x = market_from(m, json.load(open(path)))
        if x: out.append(x)
    return out

def memo(m, key, fn):
    """Indicators are computed once per market and reused at every step."""
    c = m.setdefault("_memo", {})
    if key not in c: c[key] = fn()
    return c[key]

def ema(x, n):
    a = 2 / (n + 1); out = np.empty_like(x); out[0] = x[0]
    for i in range(1, len(x)): out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

def rsi(x, n):
    d = np.diff(x, prepend=x[0]); out = np.full(len(x), 50.0)
    for i in range(n, len(x)):
        up = d[i - n + 1:i + 1].clip(min=0).sum(); dn = (-d[i - n + 1:i + 1]).clip(min=0).sum()
        out[i] = 100 if dn == 0 else 100 - 100 / (1 + up / dn)
    return out

def trade(m, k, side, exit_rule, hold):
    """Signal at the end of day k; fill at day k+1's quote. side 'yes' buys YES at the ask, 'no' buys NO at 100-bid.
    exit_rule(j) -> True sells at day j's bid (for YES; 100-ask for NO); otherwise hold to settlement or `hold` days."""
    e = k + 1
    if e >= len(m["T"]): return None
    px = m["ask"][e] if side == "yes" else (None if m["bid"][e] is None else 100 - m["bid"][e])
    if px is None or not 2 <= px <= 98: return None
    j = e + 1
    while j < len(m["T"]):
        if (hold and j - e >= hold) or (exit_rule and exit_rule(j)):
            q = m["bid"][j] if side == "yes" else (None if m["ask"][j] is None else 100 - m["ask"][j])
            if q is not None and q > 0: return dict(t=m["T"][e], exit=j, net=round_trip(px, q), px=px)
        j += 1
    won = 100 if (m["settle"] == 100) == (side == "yes") else 0
    return dict(t=m["T"][e], exit=len(m["T"]), net=buy_hold(px, won), px=px)

def run_family(markets, fn):
    trades = []
    for m in markets:
        k = 0
        while k < len(m["T"]) - 1:
            hit = fn(m, k)
            if hit:
                side, ex, hold = hit
                tr = trade(m, k, side, ex, hold)
                if tr: tr["cat"] = m["cat"]; trades.append(tr); k = tr["exit"]; continue
            k += 1
    return trades

def days_left(m, k):
    return None if not m["sched"] else (m["sched"] - m["T"][k]) / 86400

FAMILIES_A = {}
def fam(name, desc, grid):
    def deco(f): FAMILIES_A[name] = (desc, grid, f); return f
    return deco

@fam("momentum", "Momentum: the probability rose (fell) {x}+ points over {k} days; buy YES (NO), hold {h}",
     [dict(k=k, x=x, h=h) for k in (3, 7, 14) for x in (5, 10, 20) for h in (3, 7, 0)])
def _(P):
    def f(m, i):
        if i < P["k"]: return None
        d = m["mid"][i] - m["mid"][i - P["k"]]
        if abs(d) >= P["x"] and 5 <= m["mid"][i] <= 95: return ("yes" if d > 0 else "no", None, P["h"])
    return f

@fam("reversal", "Short-term reversal: fade a {x}+ point one-day move, hold {h}",
     [dict(x=x, h=h) for x in (5, 10, 15, 25) for h in (1, 3, 7, 0)])
def _(P):
    def f(m, i):
        if i < 1: return None
        d = m["mid"][i] - m["mid"][i - 1]
        if abs(d) >= P["x"] and 5 <= m["mid"][i] <= 95: return ("no" if d > 0 else "yes", None, P["h"])
    return f

@fam("rsi_dip", "Dive Zone: buy YES on a 2-day RSI under {r} while above its {n}-day EMA; sell when RSI(2) > 70 or after 10 days",
     [dict(r=r, n=n) for r in (5, 10, 20) for n in (5, 10, 20)])
def _(P):
    def f(m, i):
        if i < P["n"]: return None
        r2 = memo(m, "rsi2", lambda: rsi(m["mid"], 2)); e = memo(m, ("ema", P["n"]), lambda: ema(m["mid"], P["n"]))
        if r2[i] < P["r"] and m["mid"][i] > e[i] and 5 <= m["mid"][i] <= 90:
            return ("yes", lambda j: r2[j] > 70, 10)
    return f

@fam("ema_cross", "EMA crossover: buy YES when the {a}-day EMA crosses above the {b}-day (NO when below); exit on the opposite cross",
     [dict(a=a, b=b) for a, b in ((2, 5), (3, 10), (5, 20))])
def _(P):
    def f(m, i):
        if i < P["b"]: return None
        ea = memo(m, ("ema", P["a"]), lambda: ema(m["mid"], P["a"])); eb = memo(m, ("ema", P["b"]), lambda: ema(m["mid"], P["b"]))
        up, dn = ea[i] > eb[i] and ea[i - 1] <= eb[i - 1], ea[i] < eb[i] and ea[i - 1] >= eb[i - 1]
        if (up or dn) and 5 <= m["mid"][i] <= 95:
            return ("yes" if up else "no", (lambda j: ea[j] < eb[j]) if up else (lambda j: ea[j] > eb[j]), 0)
    return f

@fam("donchian", "Donchian breakout: buy YES on a close above the prior {n}-day high (NO below the low), hold {h}",
     [dict(n=n, h=h) for n in (5, 10, 20) for h in (5, 0)])
def _(P):
    def f(m, i):
        if i < P["n"]: return None
        w = m["mid"][i - P["n"]:i]
        if m["mid"][i] > w.max() + 1 and m["mid"][i] <= 95: return ("yes", None, P["h"])
        if m["mid"][i] < w.min() - 1 and m["mid"][i] >= 5: return ("no", None, P["h"])
    return f

@fam("breakthrough", "SharkFin's breakthrough: a new {n}-day high after falling {x}+ points within it; buy YES, hold to the end",
     [dict(n=n, x=x) for n in (10, 30, 60) for x in (15, 30)])
def _(P):
    def f(m, i):
        if i < P["n"]: return None
        w = m["mid"][i - P["n"]:i]
        if m["mid"][i] > w.max() and w.max() - w.min() >= P["x"] and np.argmin(w) > np.argmax(w) and m["mid"][i] <= 95: return ("yes", None, 0)
    return f

@fam("bollinger", "Bollinger fade: buy YES under the lower band ({n} days, 2 sd), NO over the upper; exit at the middle",
     [dict(n=n) for n in (5, 10, 20)])
def _(P):
    def f(m, i):
        if i < P["n"]: return None
        w = m["mid"][i - P["n"] + 1:i + 1]; mu, sd = w.mean(), w.std()
        if sd < 1 or not 5 <= m["mid"][i] <= 95: return None
        mid = m["mid"]
        if mid[i] < mu - 2 * sd: return ("yes", lambda j: mid[j] >= mu, 10)
        if mid[i] > mu + 2 * sd: return ("no", lambda j: mid[j] <= mu, 10)
    return f

@fam("macd", "MACD: buy YES when MACD(3,10) crosses above its 3-day signal (NO below); hold {h}",
     [dict(h=h) for h in (3, 7, 0)])
def _(P):
    def f(m, i):
        if i < 12: return None
        mac, sig = memo(m, "macd", lambda: (lambda x: (x, ema(x, 3)))(ema(m["mid"], 3) - ema(m["mid"], 10)))
        if mac[i] > sig[i] and mac[i - 1] <= sig[i - 1] and m["mid"][i] <= 95: return ("yes", None, P["h"])
        if mac[i] < sig[i] and mac[i - 1] >= sig[i - 1] and m["mid"][i] >= 5: return ("no", None, P["h"])
    return f

@fam("favorite", "Near-certain favorite: buy the side priced {x}¢+ with {d} days or less to the scheduled end; hold to settlement",
     [dict(x=x, d=d) for x in (85, 90, 95) for d in (1, 3, 7, 30)])
def _(P):
    def f(m, i):
        dl = days_left(m, i)
        if dl is None or not 0 < dl <= P["d"]: return None
        if m["mid"][i] >= P["x"] and m["mid"][i] <= 97: return ("yes", None, 0)
        if m["mid"][i] <= 100 - P["x"] and m["mid"][i] >= 3: return ("no", None, 0)
    return f

@fam("longshot", "Long-shot fade: when YES is priced {x}¢ or less with {d} days or less left, buy NO; hold to settlement",
     [dict(x=x, d=d) for x in (5, 10, 20) for d in (3, 14, 60)])
def _(P):
    def f(m, i):
        dl = days_left(m, i)
        if dl is None or not 0 < dl <= P["d"]: return None
        if 2 <= m["mid"][i] <= P["x"]: return ("no", None, 0)
    return f

def section_a(markets):
    allt = sorted(t for m in markets for t in m["T"]); cut = allt[int(len(allt) * 0.6)]
    fams, pvals = [], []
    for name, (desc, grid, maker) in FAMILIES_A.items():
        best = None; tried = []
        for P in grid:
            tr = run_family(markets, maker(P))
            pick = [x["net"] for x in tr if x["t"] < cut]; grade = [x["net"] for x in tr if x["t"] >= cut]
            sp, sg = stats(pick), stats(grade); tried.append(dict(P=P, pick=sp, grade=sg))
            if sp["n"] >= 100 and (best is None or sp["t"] > best[1]["t"]): best = (P, sp, sg, tr)
        if not best: continue
        P, sp, sg, tr = best
        bycat = {}
        for x in tr:
            if x["t"] >= cut: bycat.setdefault(x["cat"], []).append(x["net"])
        fams.append(dict(family=name, rule=desc.format(**{**P, "h": f"{P['h']} days" if P.get("h") else "to the end"} if "h" in P else P),
                         params=P, pick=sp, grade=sg, tried=len(grid),
                         grade_by_cat={k: stats(v) for k, v in bycat.items() if len(v) >= 30}))
        pvals.append(sg["p"] if sg["n"] >= 40 else 1)
        log(f"A {name}: pick {sp['roi']:+.1%} ({sp['n']}) -> grade {sg['roi']:+.1%} ({sg['n']}) t={sg['t']}")
    ok = bh(pvals)
    for i, f in enumerate(fams): f["works"] = i in ok and f["grade"]["t"] >= 2 and f["pick"]["roi"] > 0
    return dict(cut=iso(cut), markets=len(markets), families=fams)

# ================================================================ E. calibration by category
def binom_p(k, n, p):
    """Two-sided exact binomial p-value of k YES out of n when each was priced at p (normal approximation for n > 400)."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    if n > 400:
        z = (k - n * p) / math.sqrt(n * p * (1 - p)); return math.erfc(abs(z) / math.sqrt(2))
    pmf = [math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(x for x in pmf if x <= pmf[k] * (1 + 1e-9)))

MON = {m: i for i, m in enumerate(("", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")) if m}
def event_day(event):
    """The event's date from its ticker (e.g. KXEARNINGSMENTIONMDT-26MAY29 -> 2026-05-29, 00:00 UTC), fixed when the
    market is listed. Kalshi's expiration fields are often the LATEST possible end, weeks or months after the event,
    and the close time is only known afterwards, so neither can say when 'a day before' is."""
    import re
    x = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", event or "")
    if not x or x.group(2) not in MON: return None
    try: return int(datetime(2000 + int(x.group(1)), MON[x.group(2)], int(x.group(3)), tzinfo=timezone.utc).timestamp())
    except ValueError: return None

def day_before(m):
    """Index of the day-end quote on the day before the event's date, if the market was trading then; else None."""
    d = event_day(m["event"])
    if d is None: return None
    ks = [k for k, t in enumerate(m["T"]) if d - 86400 < t <= d and m["ask"][k] is not None]
    return ks[-1] if ks else None

def section_e(markets):
    """Each market's price at the end of the day before its event's date (from the ticker; markets without a dated
    ticker are left out) against the result.
    An 'edge' must (1) pass an exact binomial test of win rate vs price, after a false-discovery correction across
    cells, (2) make money after fees when averaged per event (markets on the same event move together), and
    (3) make money in both halves of the period."""
    allt = sorted(m["T"][0] for m in markets); half = allt[len(allt) // 2]
    cells = {}
    for m in markets:
        k = day_before(m)
        if k is None: continue
        p = m["mid"][k]
        b = int(min(99, p) // 10) * 10
        for cat in (m["cat"], "All non-sports"):
            c = cells.setdefault((cat, b), dict(n=0, yes=0, imp=0.0, ev={}))
            c["n"] += 1; c["yes"] += m["settle"] == 100; c["imp"] += p
            e = c["ev"].setdefault(m["event"], dict(y=[], n=[], late=m["T"][k] >= half))
            e["y"].append(buy_hold(m["ask"][k], m["settle"])); e["n"].append(buy_hold(100 - m["bid"][k], 100 - m["settle"]))
    rows = []
    for (cat, b), c in sorted(cells.items()):
        if c["n"] < 25: continue
        ev = list(c["ev"].values())
        per_y, per_n = [float(np.mean(e["y"])) for e in ev], [float(np.mean(e["n"])) for e in ev]
        half_y = [float(np.mean([y for e, y in zip(ev, per_y) if e["late"] == h] or [0])) for h in (False, True)]
        half_n = [float(np.mean([y for e, y in zip(ev, per_n) if e["late"] == h] or [0])) for h in (False, True)]
        rows.append(dict(cat=cat, lo=b, hi=b + 10, n=c["n"], events=len(ev), won=round(c["yes"] / c["n"], 3), implied=round(c["imp"] / c["n"] / 100, 3),
                         p=binom_p(c["yes"], c["n"], c["imp"] / c["n"] / 100), buy_yes=stats(per_y), buy_no=stats(per_n),
                         halves_yes=[round(x / STAKE, 4) for x in half_y], halves_no=[round(x / STAKE, 4) for x in half_n]))
    ok = bh([r["p"] for r in rows])
    for i, r in enumerate(rows):
        side = "buy_yes" if r["won"] > r["implied"] else "buy_no"; hv = r["halves_yes" if side == "buy_yes" else "halves_no"]
        r["edge"] = bool(i in ok and r["events"] >= 15 and r[side]["t"] >= 2 and r[side]["roi"] > 0 and min(hv) > 0)
        r["side"] = "YES" if side == "buy_yes" else "NO"; r["p"] = round(r["p"], 5)
    return rows

# ================================================================ C. Dutch books
def section_c():
    evs = json.load(open(os.path.join(UC, "events.json")))
    found, cheap, checked, days = [], [], 0, 0
    for ser, et, tks in evs:
        series = {}
        for tk in tks:
            p = os.path.join(UC, "d_" + tk.replace("/", "~") + ".json")
            if not os.path.exists(p): series = None; break
            series[tk] = {t // 86400: (b, a) for t, b, a, _ in json.load(open(p))}
        if not series: continue
        checked += 1
        common = set.intersection(*(set(v) for v in series.values()))
        for d in sorted(common):
            q = [series[tk][d] for tk in tks]
            if any(b is None or a is None or a - b > 15 or a > 99 for b, a in q): continue
            days += 1
            n = len(q)
            # buy one YES of every outcome: exactly one pays $1
            cost = sum(a for b, a in q) / 100; f_buy = sum(fee(a / 100, 1) for b, a in q)
            # buy one NO of every outcome: n-1 of them pay $1
            cost_no = sum(100 - b for b, a in q) / 100; f_no = sum(fee((100 - b) / 100, 1) for b, a in q)
            edge_yes, edge_no = 1 - cost - f_buy, (n - 1) - cost_no - f_no
            # "exactly one outcome wins" (Kalshi's mutually_exclusive) rules out two winners, not zero: "who drops out
            # first?" can end with nobody dropping out. So buying every NO is locked in (it pays n-1, or n), but buying
            # every YES pays only if some listed outcome happens. Keeping only events where one did would be hindsight,
            # so the YES side is counted separately and never called locked in.
            if edge_no > 0.005:
                found.append(dict(event=et, day=iso(d * 86400), outcomes=n, side="buy every NO", edge=round(edge_no * 100, 1), cost=round(cost_no * 100, 1)))
            if edge_yes > 0.005:
                cheap.append(dict(event=et, day=iso(d * 86400), outcomes=n, side="buy every YES", edge=round(edge_yes * 100, 1), cost=round(cost * 100, 1)))
    found.sort(key=lambda r: -r["edge"]); cheap.sort(key=lambda r: -r["edge"])
    return dict(events=checked, event_days=days, opportunities=len(found), events_with=len({r["event"] for r in found}), top=found[:25],
                yes_days=len(cheap), yes_events=len({r["event"] for r in cheap}), yes_top=cheap[:10])

# ================================================================ B. Kalshi odds as an equity signal
def section_b():
    t = open(os.path.join(E.DATA, "stocks.js")).read(); D = json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))
    N, dates = len(D["dates"]), D["dates"]
    def index(match):
        sigs = [s for s in D["signals"] if match(s)]
        lvl, last = [], None
        for i in range(N):
            v = [s["p"][i] for s in sigs if s["p"][i] is not None]
            last = sum(v) / len(v) if v else last; lvl.append(last)
        return lvl, len(sigs)
    rec, nrec = index(lambda s: "recession" in s["title"].lower())
    cut, ncut = index(lambda s: s["theme"] == "fed" and ("cut" in s["title"].lower() or "lower" in s["title"].lower()))
    split = int(N * 0.6)
    out = dict(split=dates[split], indexes={"Recession odds": nrec, "Fed-cut odds": ncut}, rules=[])
    def daily(tk):          # next-open-to-next-open returns, so a rule decided at day i's close trades at day i+1's open
        o = D["px"][tk]["o"]; return [None if i + 2 >= N or o[i + 1] is None or o[i + 2] is None else o[i + 2] / o[i + 1] - 1 for i in range(N)]
    def sharpe(r):
        r = [x for x in r if x is not None]
        if len(r) < 30: return None
        m, sd = np.mean(r), np.std(r); return round(float(m / sd * math.sqrt(252)), 2) if sd else 0
    def ann(r):
        r = [x for x in r if x is not None]; return round(float(np.prod([1 + x for x in r]) ** (252 / max(1, len(r))) - 1), 4) if r else None
    def test(name, lvl, tk, cond, desc):
        r = daily(tk); pos = [cond(lvl, i) for i in range(N)]
        strat = [r[i] * (1 if pos[i] else 0) if r[i] is not None and pos[i] is not None else None for i in range(N)]
        bh_ = [r[i] if pos[i] is not None else None for i in range(N)]
        row = dict(rule=desc, stock=tk, signal=name)
        for k, sl in (("pick", slice(0, split)), ("grade", slice(split, N))):
            row[k] = dict(sharpe=sharpe(strat[sl]), ann=ann(strat[sl]), hold_sharpe=sharpe(bh_[sl]), hold_ann=ann(bh_[sl]),
                          in_market=round(float(np.mean([p for p in pos[sl] if p is not None])), 2) if any(p is not None for p in pos[sl]) else None)
        out["rules"].append(row)
    ma = lambda lvl, i, n: None if i < n or any(lvl[j] is None for j in range(i - n, i + 1)) else sum(lvl[i - n:i + 1]) / (n + 1)
    for tk in ("SPY", "QQQ", "IWM"):
        for n in (10, 30):
            test("Recession odds", rec, tk, lambda l, i, n=n: None if ma(l, i, n) is None else l[i] <= ma(l, i, n),
                 f"Hold only while recession odds are at or below their {n}-day average")
        for x in (2, 3):
            def fear(l, i, x=x):          # in the market for 20 trading days after recession odds rose x+ points in 2 weeks
                if i < 30: return None
                return any(l[j] is not None and l[j - 10] is not None and l[j] - l[j - 10] >= x for j in range(i - 19, i + 1))
            test("Recession odds", rec, tk, fear, f"Buy the fear: hold for 20 days after recession odds rise {x}+ points in 2 weeks")
    for tk in ("TLT", "IWM", "QQQ"):
        for n in (10, 30):
            test("Fed-cut odds", cut, tk, lambda l, i, n=n: None if ma(l, i, n) is None else l[i] >= ma(l, i, n),
                 f"Hold only while Fed-cut odds are at or above their {n}-day average")
    for r in out["rules"]:
        r["works"] = all(r[k]["sharpe"] is not None and r[k]["hold_sharpe"] is not None and r[k]["sharpe"] > r[k]["hold_sharpe"] for k in ("pick", "grade"))
    # forward returns after the biggest recession scares (descriptive, SharkFin's "buying fear" table)
    fwd = []
    for i in range(10, N - 63):
        if rec[i] is None or rec[i - 10] is None: continue
        o = D["px"]["SPY"]["o"]
        if o[i + 1] and o[min(N - 1, i + 63)]: fwd.append((rec[i] - rec[i - 10], o[min(N - 1, i + 63)] / o[i + 1] - 1))
    fwd.sort()
    q = len(fwd) // 5
    out["fear_table"] = [dict(group=g, n=len(x), spy_3m=round(float(np.mean([b for a, b in x])), 4), up=round(float(np.mean([b > 0 for a, b in x])), 3))
                         for g, x in (("Recession odds fell most (bottom fifth)", fwd[:q]), ("Middle", fwd[q:-q]), ("Recession odds rose most (top fifth)", fwd[-q:]))]
    return out

# ================================================================ D. SharkFin indicators on in-game sports prices
def sports_makers():
    """SharkFin's indicators as in-game rules. Each rule takes a game and returns (side, sample) of its first trigger."""
    fams = {}
    def rsi_dip(r, k):
        def f(g):
            s = g["fav"]; m = g["m"][s]; per = max(1, round(5 / g["step"]))
            for i in range(k * per + 1, g["n"] - 1):
                w = m[i - k * per:i + 1:per]
                if np.isnan(w).any() or m[i] < 50: continue
                d = np.diff(w); up, dn = d.clip(min=0).sum(), (-d).clip(min=0).sum()
                if dn > 0 and 100 - 100 / (1 + up / dn) < r: return s, i
        return f
    fams["rsi_dip"] = ("Dive Zone in-game: the pre-game favorite, still at 50¢+, hits an RSI({k}) under {r} on 5-minute steps; buy it",
                       [dict(r=r, k=k) for r in (10, 20, 30) for k in (2, 3, 5)], lambda P: rsi_dip(P["r"], P["k"]))
    def ema_cross(a, b):
        def f(g):
            # time on the outside, both teams checked at each step: the first trigger in the game wins.
            # (Looping over teams first would bet on team B only because team A never triggered later: look-ahead.)
            M = [np.nan_to_num(g["m"][s], nan=50.0) for s in (0, 1)]
            EA = [memo(g, ("ea", s, a), lambda s=s: ema(M[s], a)) for s in (0, 1)]; EB = [memo(g, ("ea", s, b), lambda s=s: ema(M[s], b)) for s in (0, 1)]
            for i in range(b, g["n"] - 1):
                for s in (0, 1):
                    if EA[s][i] > EB[s][i] and EA[s][i - 1] <= EB[s][i - 1] and 30 <= M[s][i] <= 85: return s, i
        return f
    fams["ema_cross"] = ("EMA crossover in-game: a team's {a}-sample EMA crosses above its {b}-sample EMA (at 30-85¢); buy it",
                         [dict(a=a, b=b) for a, b in ((3, 10), (5, 20), (10, 40))], lambda P: ema_cross(P["a"], P["b"]))
    def donchian(w):
        def f(g):
            for i in range(w, g["n"] - 1):
                for s in (0, 1):
                    m = g["m"][s]; win = m[i - w:i]
                    if not np.isnan(win).any() and m[i] > np.nanmax(win) + 2 and 40 <= m[i] <= 85: return s, i
        return f
    fams["donchian"] = ("Donchian breakout in-game: a team breaks 2¢+ above its prior {w}-sample high (at 40-85¢); buy it",
                        [dict(w=w) for w in (10, 20, 40)], lambda P: donchian(P["w"]))
    def boll(w, z):
        def f(g):
            s = g["fav"]; m = g["m"][s]
            for i in range(w, g["n"] - 1):
                win = m[i - w + 1:i + 1]
                if np.isnan(win).any(): continue
                mu, sd = win.mean(), win.std()
                if sd > 1 and m[i] < mu - z * sd and m[i] >= 20: return s, i
        return f
    fams["bollinger"] = ("Bollinger fade in-game: the favorite drops below its {w}-sample mean minus {z} sd; buy it",
                         [dict(w=w, z=z) for w in (10, 20) for z in (2, 2.5, 3)], lambda P: boll(P["w"], P["z"]))
    def ibs(w, lo):
        def f(g):
            for i in range(w, g["n"] - 1):
                for s in (0, 1):
                    win = g["m"][s][i - w:i + 1]
                    if np.isnan(win).any(): continue
                    rg = win.max() - win.min()
                    if rg >= 10 and (win[-1] - win.min()) / rg <= lo and 20 <= win[-1] <= 80: return s, i
        return f
    fams["ibs"] = ("IBS-style reversion in-game: a team sits in the bottom {lo:.0%} of a 10¢+ range over the last {w} samples; buy it",
                   [dict(w=w, lo=lo) for w in (10, 20) for lo in (0.05, 0.1, 0.2)], lambda P: ibs(P["w"], P["lo"]))
    def breakthrough(x):
        def f(g):
            pre = [(g["pre"][s][0] + g["pre"][s][1]) / 2 for s in (0, 1)]; lo, hi = list(pre), list(pre)
            for i in range(1, g["n"] - 1):          # time on the outside, both teams at each step (see ema_cross)
                for s in (0, 1):
                    v = g["m"][s][i]
                    if np.isnan(v): continue
                    lo[s] = min(lo[s], v)
                    if pre[s] - lo[s] >= x and v > hi[s] and v <= 90: return s, i
                    hi[s] = max(hi[s], v)
        return f
    fams["breakthrough"] = ("Breakthrough in-game: a team falls {x}¢+ below its pre-game price, then makes a new in-game high; buy it",
                            [dict(x=x) for x in (10, 20, 30)], lambda P: breakthrough(P["x"]))
    return fams

def section_d():
    idx = E.index(); games = []
    for lg in idx["leagues"]: games += E.load(lg, idx)
    games.sort(key=lambda g: g["ts"]); n = len(games)
    for k, g in enumerate(games): g["per"] = 0 if k < n * 0.55 else 1 if k < n * 0.75 else 2
    def mids(g, s): return np.array([np.nan if g["bid"][s][i] is None else (g["bid"][s][i] + g["ask"][s][i]) / 2 for i in range(g["n"])])
    for g in games: g["m"] = [mids(g, 0), mids(g, 1)]; g["_memo"] = {}
    def fill(g, s, i):
        e = next((j for j in range(i + 1, min(g["n"], i + 4)) if g["live"][s][j]), None)
        if e is None: return None
        p = g["ask"][s][e]; return p if p is not None and 2 <= p <= 98 else None
    def run(rule):
        nets = [[], [], []]
        for g in games:
            hit = rule(g)
            if not hit: continue
            s, i = hit; p = fill(g, s, i)
            if p is None: continue
            nets[g["per"]].append(E.pnl(p / 100, g["win"] == s))
        return [stats(x) for x in nets]
    fams = sports_makers()
    # pre-game line moves (sharp money?): only the 24-hour and 1-hour lines are used, and the bet fills at the 1-hour ask
    def line_move(x, follow):
        def run_lm():
            nets = [[], [], []]
            for g in games:
                a, b = g.get("h24"), g.get("h1")
                if not a or not b: continue
                mv = (b[0][0] + b[0][1]) / 2 - (a[0][0] + a[0][1]) / 2          # team A's move, in cents
                if abs(mv) < x: continue
                s = (0 if mv > 0 else 1) if follow else (1 if mv > 0 else 0)
                p = b[s][1]
                if 2 <= p <= 98: nets[g["per"]].append(E.pnl(p / 100, g["win"] == s))
            return [stats(v) for v in nets]
        return run_lm
    for name, follow in (("line_follow", True), ("line_fade", False)):
        best = None
        for x in (3, 5, 8, 12):
            per = line_move(x, follow)()
            if per[0]["n"] >= 200 and (best is None or per[0]["t"] > best[1][0]["t"]): best = (x, per)
        if best:
            x, per = best
            fams_lm = dict(family=name, rule=(f"Follow the line: the line moved {x}¢+ toward a team between 24 hours and 1 hour before the start; buy that team at the 1-hour price"
                                              if follow else f"Fade the line: the line moved {x}¢+ toward a team between 24 hours and 1 hour out; buy the other team at the 1-hour price"),
                           params=dict(x=x), train=per[0], valid=per[1], test=per[2], tried=4)
            log(f"D {name}: train {per[0]['roi']:+.1%} valid {per[1]['roi']:+.1%} test {per[2]['roi']:+.1%} ({per[2]['n']})")
            fams[name] = fams_lm
    out, pv = [], []
    for name, item in fams.items():
        if isinstance(item, dict):
            out.append(item); pv.append(item["test"]["p"] if item["valid"]["t"] >= 2 else 1); continue
        desc, grid, maker = item
        best = None
        for P in grid:
            per = run(maker(P))
            if per[0]["n"] >= 200 and (best is None or per[0]["t"] > best[1][0]["t"]): best = (P, per)
        if not best: continue
        P, per = best
        out.append(dict(family=name, rule=desc.format(**P), params=P, train=per[0], valid=per[1], test=per[2], tried=len(grid)))
        pv.append(per[2]["p"] if per[1]["t"] >= 2 else 1)
        log(f"D {name}: train {per[0]['roi']:+.1%} valid {per[1]['roi']:+.1%} test {per[2]['roi']:+.1%} ({per[2]['n']})")
    ok = bh(pv)
    for i, f in enumerate(out): f["works"] = i in ok and f["valid"]["t"] >= 2 and f["test"]["t"] >= 2
    return dict(games=n, families=out)

if __name__ == "__main__":
    t0 = time.time(); res = dict(built=time.strftime("%Y-%m-%d"))
    if os.path.exists(os.path.join(UC, "index.json")):
        U = load_universe(); log(len(U), "settled non-sports markets with daily quotes")
        res["A"] = section_a(U); res["E"] = section_e(U); res["C"] = section_c()
        from collections import Counter
        res["universe"] = dict(markets=len(U), categories=dict(Counter(m["cat"] for m in U).most_common()))
    res["B"] = section_b(); log("B done")
    res["D"] = section_d(); log("D done")
    res["minutes"] = round((time.time() - t0) / 60, 1)
    json.dump(res, open(os.path.join(ROOT, "results", "zoo.json"), "w"), indent=1, default=float)
    with open(os.path.join(E.DATA, "zoo.js"), "w") as f:
        f.write("window.ZOO="); json.dump(res, f, separators=(",", ":"), default=float); f.write(";\n")
    log("wrote results/zoo.json and app/data/zoo.js in", res["minutes"], "min")
