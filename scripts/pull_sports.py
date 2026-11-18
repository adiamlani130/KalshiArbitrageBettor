"""Pull game-winner price paths for many sports from Kalshi's public API (no key needed)
and write the compact per-league files the Edge Lab loads on demand.

    python scripts/pull_sports.py                 # every league below (1-2 hours, resumable)
    python scripts/pull_sports.py nfl mlb         # just some leagues
    python scripts/pull_sports.py --build         # rebuild app/data/ from the cache, no downloads

For every settled game it saves, for one team ("A", the home team where Kalshi says who is home):
  - A's bid/ask 24 hours, 1 hour and 5 minutes before the start, plus the first price and pre-game volume
  - A's bid/ask every STEP minutes from the start until the market closed (the "price path")
Three-way sports (soccer) also save team B's own path, because B's price is not 100 - A's.

Raw downloads are cached in data/sports_cache/ (git-ignored) so a stopped run can resume.
Output: app/data/sports_<league>.js and app/data/sports_index.js.
"""
import json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "sports_cache")
OUT = os.path.join(ROOT, "app", "data")
SINCE = "2025-08-01"          # earliest game start to keep
MAX_GAMES = 2000              # most recent games kept per league
ET = ZoneInfo("America/New_York")

# id: (Kalshi series, label, sport, typical minutes from start to finish, path step in minutes,
#      three-way market (draw possible), second-listed team is home, start time is only a rough schedule)
LEAGUES = {
    "nfl":    ("KXNFLGAME",    "NFL",                  "Football",   190, 2, False, True,  False),
    "ncaaf":  ("KXNCAAFGAME",  "College football",     "Football",   205, 2, False, True,  False),
    "nba":    ("KXNBAGAME",    "NBA",                  "Basketball", 150, 2, False, True,  False),
    "wnba":   ("KXWNBAGAME",   "WNBA",                 "Basketball", 125, 2, False, True,  False),
    "ncaab":  ("KXNCAAMBGAME", "College basketball (M)", "Basketball", 125, 2, False, True, False),
    "mlb":    ("KXMLBGAME",    "MLB",                  "Baseball",   170, 2, False, True,  False),
    "nhl":    ("KXNHLGAME",    "NHL",                  "Hockey",     155, 2, False, True,  False),
    "epl":    ("KXEPLGAME",    "Premier League",       "Soccer",     115, 2, True,  False, False),
    "ucl":    ("KXUCLGAME",    "Champions League",     "Soccer",     115, 2, True,  False, False),
    "laliga": ("KXLALIGAGAME", "La Liga",              "Soccer",     115, 2, True,  False, False),
    "mls":    ("KXMLSGAME",    "MLS",                  "Soccer",     115, 2, True,  False, False),
    "ufc":    ("KXUFCFIGHT",   "UFC",                  "MMA",         20, 1, False, False, True),
    "atp":    ("KXATPMATCH",   "Tennis · ATP",         "Tennis",     110, 2, False, False, True),
    "wta":    ("KXWTAMATCH",   "Tennis · WTA",         "Tennis",     100, 2, False, False, True),
}

# ------------------------------------------------------------------ http
_local, _lock, _next = threading.local(), threading.Lock(), [0.0]
RATE = 0.065  # seconds between requests across all threads

def get(path, **p):
    s = getattr(_local, "s", None) or requests.Session(); _local.s = s
    for attempt in range(7):
        with _lock:
            wait = _next[0] - time.time(); _next[0] = max(time.time(), _next[0]) + RATE
        if wait > 0: time.sleep(wait)
        try:
            r = s.get(BASE + path, params={k: v for k, v in p.items() if v is not None}, timeout=30)
            if r.status_code == 429: time.sleep(1.5 * (attempt + 1)); continue
            if r.status_code >= 500: time.sleep(1 + attempt); continue
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return {}

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def ts(iso): return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) if iso else None

def all_markets(series):
    out = {}
    for path, extra in (("/markets", {"status": "settled"}), ("/historical/markets", {})):
        cur = None
        while True:
            r = get(path, series_ticker=series, limit=1000, cursor=cur, **extra)
            for m in r.get("markets", []): out.setdefault(m["ticker"], m)
            cur = r.get("cursor")
            if not cur or not r.get("markets"): break
    return list(out.values())

def milestones():
    """event ticker -> scheduled start, home/away team ids, season info (Kalshi's own schedule data)."""
    path = os.path.join(CACHE, "milestones.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400: return json.load(open(path))
    out, cur, n = {}, None, 0
    while True:
        r = get("/milestones", limit=500, category="Sports", minimum_start_date=SINCE + "T00:00:00Z", cursor=cur)
        for m in r.get("milestones", []):
            d = m.get("details") or {}
            rec = dict(start=ts(m.get("start_date")), home=d.get("home_team_id"), away=d.get("away_team_id"),
                       title=m.get("title"), season=(d.get("season") or {}).get("type"))
            for ev in set((m.get("primary_event_tickers") or []) + (m.get("related_event_tickers") or [])
                          + [d.get("main_game_event_ticker")]):
                if ev: out.setdefault(ev, rec)
        n += len(r.get("milestones", [])); cur = r.get("cursor")
        if n % 5000 < 500: log("milestones", n)
        if not cur or not r.get("milestones"): break
    json.dump(out, open(path, "w"))
    return out

def candles(series, tk, a, b, interval):
    for path in (f"/series/{series}/markets/{tk}/candlesticks", f"/historical/markets/{tk}/candlesticks"):
        c = get(path, start_ts=a, end_ts=b, period_interval=interval).get("candlesticks")
        if c: return c
    return []

def px(c, k):
    """Closing bid or ask of one candle, in cents (live and archive endpoints name the field differently)."""
    v = c.get(k) or {}; v = v.get("close_dollars", v.get("close"))
    return None if v is None else round(float(v) * 100)
vol = lambda c: float(c.get("volume_fp") or c.get("volume") or 0)
team_id = lambda m: next(iter((m.get("custom_strike") or {}).values()), None)

# ------------------------------------------------------------------ one game
def detect_start(cs, close, sched, moves, floor=None, mult=None):
    """When did the match or fight actually start? The first minute (no earlier than 10 minutes before the
    scheduled time) when the price has moved in at least `moves` of the last 10 minutes, or, if `floor` is
    set, when 10-minute volume reaches `floor` contracts and `mult` times the previous hour's pace.
    Causal: it uses only candles up to that minute. Checked against the true end of set 1 in tennis
    (56 of 60 sample matches start 20-80 minutes before set 1 ends, none after) and fight length in UFC."""
    t_, v_ = [c["end_period_ts"] for c in cs], [vol(c) for c in cs]
    m_ = []
    for c in cs:
        b, a = px(c, "yes_bid"), px(c, "yes_ask")
        m_.append(None if b is None or a is None or a - b > 30 else (a + b) / 2)
    for k, t in enumerate(t_):
        if t > close - 600: return None
        if t < sched - 600: continue
        w = [j for j in range(k, -1, -1) if t_[j] > t - 600]
        moved = sum(1 for j in w if j and m_[j] is not None and m_[j - 1] is not None and abs(m_[j] - m_[j - 1]) >= 1)
        if moved >= moves: return t
        if floor:
            now = sum(v_[j] for j in w); prior = sum(v_[j] for j in range(k, -1, -1) if t - 4200 < t_[j] <= t - 600)
            if now >= floor and now >= mult * prior / 6: return t
    return None

def series_at(cs, t0, step, n):
    """Bid and ask sampled every `step` minutes from t0 (last candle at or before each sample)."""
    bids, asks, i, b, a = [], [], 0, None, None
    for k in range(n):
        t = t0 + k * step * 60
        while i < len(cs) and cs[i]["end_period_ts"] <= t:
            nb, na = px(cs[i], "yes_bid"), px(cs[i], "yes_ask")
            if nb is not None: b = nb
            if na is not None: a = na
            i += 1
        bids.append(b); asks.append(a)
    return bids, asks

def last_before(cs, t):
    b = a = None
    for c in cs:
        if c["end_period_ts"] > t: break
        nb, na = px(c, "yes_bid"), px(c, "yes_ask")
        if nb is not None: b = nb
        if na is not None: a = na
    return b, a

def game(lg, ev, mk, ms):
    series, _, _, dur, step, three, second_home, rough = LEAGUES[lg]
    mk = [m for m in mk if m.get("result") in ("yes", "no")]
    tie = [m for m in mk if m["ticker"].endswith("-TIE")]
    teams = sorted((m for m in mk if not m["ticker"].endswith("-TIE")), key=lambda m: m["ticker"])
    if len(teams) != 2: return None
    if not three and sum(m["result"] == "yes" for m in teams) != 1: return None      # void or tie
    close = min(ts(m["close_time"]) for m in teams)
    occ = ts(teams[0].get("occurrence_datetime") or teams[0].get("expected_expiration_time"))
    # Scheduled start from Kalshi's own schedule, else the time set when the market was listed.
    # Never fall back on the close time: that is only known once the game is over.
    start = (ms or {}).get("start") or (occ - dur * 60 if occ else None)
    if not start or start >= close: return None
    sched = start
    # which team is A: the home team if Kalshi's schedule says so, else by ticker order
    home_id = (ms or {}).get("home")
    order = "".join(ev.split("-")[1][7:])          # e.g. WASNYG (away then home in US leagues)
    A = next((m for m in teams if home_id and team_id(m) == home_id), None)
    home_known = A is not None
    if A is None:
        codes = [m["ticker"].rsplit("-", 1)[1] for m in teams]
        if second_home and order.endswith(codes[0]) and not order.endswith(codes[1]): A = teams[0]
        elif second_home and order.endswith(codes[1]): A = teams[1]
        else: A = teams[0]
        home_known = second_home
    B = teams[1] if A is teams[0] else teams[0]

    def pull(m):
        hourly = candles(series, m["ticker"], sched - 7 * 86400, sched - 3600, 60)
        a = min(sched - 150 * 60, close - 7 * 3600) if rough else sched - 150 * 60
        minute = candles(series, m["ticker"], a, min(close + 120, max(sched, a) + 9 * 3600), 1)
        return hourly, minute
    hA, mA = pull(A)
    if not mA: return None
    pre_at = sched - 300                     # the price you could buy just before a scheduled start
    if rough:
        # Tennis matches and fights rarely start on schedule. Detect the start from a burst of trading,
        # using only volume up to that minute, and treat the path as starting at the moment of detection.
        start = detect_start(mA, close, sched, **({"moves": 3, "floor": 3000, "mult": 6} if lg == "ufc" else {"moves": 5}))
        if start is None: return None
        pre_at = start + 60                  # first price you could get once you knew it had started
    n = max(2, min(300, int((close - start) / 60 / step) + 1))
    row = dict(ev=ev, start=start, sched=sched, mins=round((close - start) / 60), A=A.get("yes_sub_title"), B=B.get("yes_sub_title"),
               home=home_known, won=A["result"] == "yes", draw=bool(three and A["result"] == "no" and B["result"] == "no"),
               season=(ms or {}).get("season"), vol=round(sum(float(m.get("volume_fp") or m.get("volume") or 0) for m in mk)))
    def side(h, m, tag):
        pre = [c for c in m if c["end_period_ts"] <= pre_at]
        row[tag + "open"] = list(last_before((h or pre)[:1], 9e12))
        row[tag + "h24"] = list(last_before(h, sched - 86400))      # early prices are relative to the schedule,
        row[tag + "h1"] = list(last_before(h + pre, sched - 3600))  # which is known in advance
        row[tag + "pre"] = list(last_before(h + pre, pre_at))
        row[tag + "b"], row[tag + "a"] = series_at(m, start, step, n)
        if tag == "": row["pvol"] = round(sum(vol(c) for c in h) + sum(vol(c) for c in pre if c["end_period_ts"] > pre_at - 3600))
    side(hA, mA, "")
    if three:
        hB, mB = pull(B)
        if not mB: return None
        side(hB, mB, "B")
    if row["pre"][1] is None or row["a"].count(None) > n / 2: return None
    return row

# ------------------------------------------------------------------ league
def pull_league(lg):
    series = LEAGUES[lg][0]
    path = os.path.join(CACHE, lg + ".jsonl")
    done = {}
    if os.path.exists(path):
        for line in open(path):
            try: r = json.loads(line); done[r["ev"]] = r
            except Exception: pass
    ms = milestones()
    events = {}
    for m in all_markets(series):
        events.setdefault(m.get("event_ticker") or m["ticker"].rsplit("-", 1)[0], []).append(m)
    t0 = ts(SINCE + "T00:00:00Z")
    todo = sorted(((ev, mk) for ev, mk in events.items() if min(ts(m["close_time"]) for m in mk) > t0),
                  key=lambda x: -min(ts(m["close_time"]) for m in x[1]))[:MAX_GAMES]
    new = [(ev, mk) for ev, mk in todo if ev not in done]
    log(lg, len(events), "events,", len(todo), "kept,", len(new), "to download")
    f = open(path, "a")
    def work(x):
        try: return x[0], game(lg, x[0], x[1], ms.get(x[0]))
        except Exception as e: return x[0], {"err": repr(e)}
    with ThreadPoolExecutor(14) as ex:
        for i, (ev, row) in enumerate(ex.map(work, new)):
            row = row or {"skip": True}; row["ev"] = ev
            f.write(json.dumps(row, separators=(",", ":")) + "\n"); f.flush()
            if i % 200 == 0: log(lg, i, "of", len(new))
    f.close()

# ------------------------------------------------------------------ build app files
# One character per price (0-100 cents); "~" marks a missing quote.
ALPHABET = "".join(chr(c) for c in range(35, 127) if chr(c) not in "\\~") + "¡¢£¤¥¦§¨©ª«"
assert len(ALPHABET) >= 101
enc = lambda xs: "".join("~" if x is None else ALPHABET[max(0, min(100, x))] for x in xs)

def build(leagues):
    os.makedirs(OUT, exist_ok=True)
    index = {}
    mpath = os.path.join(CACHE, "milestones.json")
    sched_ok = json.load(open(mpath)) if os.path.exists(mpath) else {}
    for lg in LEAGUES:
        path = os.path.join(CACHE, lg + ".jsonl")
        if not os.path.exists(path): continue
        rows = {}
        for line in open(path):
            try: r = json.loads(line)
            except Exception: continue
            # Keep only games whose start came from Kalshi's schedule (known in advance). Rows pulled before this
            # rule existed could fall back on the close time, which is only known once the game is over.
            if "pre" in r and ("sched" in r or (sched_ok.get(r["ev"]) or {}).get("start") == r["start"]): rows[r["ev"]] = r
        rows = sorted(rows.values(), key=lambda r: -r["start"])
        _, label, sport, dur, step, three, _, rough = LEAGUES[lg]
        cols = ["ts", "A", "B", "home", "won", "draw", "season", "vol", "pvol", "mins",
                "open", "h24", "h1", "pre", "b", "a"] + (["Bopen", "Bh24", "Bh1", "Bpre", "Bb", "Ba"] if three else [])
        pair = lambda v: None if not v or v[0] is None or v[1] is None else [v[0], v[1]]
        out = []
        for r in rows:
            rec = [r.get("sched", r["start"]), r["A"], r["B"], int(bool(r["home"])), int(r["won"]), int(r["draw"]), r.get("season"),
                   r["vol"], r.get("pvol"), r["mins"], pair(r["open"]), pair(r["h24"]), pair(r["h1"]), pair(r["pre"]),
                   enc(r["b"]), enc(r["a"])]
            if three: rec += [pair(r["Bopen"]), pair(r["Bh24"]), pair(r["Bh1"]), pair(r["Bpre"]), enc(r["Bb"]), enc(r["Ba"])]
            out.append(rec)
        if not out: continue
        js = os.path.join(OUT, f"sports_{lg}.js")
        with open(js, "w", encoding="utf-8") as f:
            f.write(f'(window.EDGE_SPORTS=window.EDGE_SPORTS||{{}})["{lg}"]=')
            json.dump({"cols": cols, "rows": out}, f, separators=(",", ":"), ensure_ascii=False); f.write(";\n")
        day = lambda t: datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d")
        index[lg] = dict(label=label, sport=sport, step=step, three=three, rough=rough, n=len(out),
                         first=day(rows[-1]["start"]), last=day(rows[0]["start"]), kb=round(os.path.getsize(js) / 1024))
        log(lg, len(out), "games ->", js, index[lg]["kb"], "KB")
    with open(os.path.join(OUT, "sports_index.js"), "w", encoding="utf-8") as f:
        f.write("window.EDGE_SPORTS_INDEX=")
        json.dump({"built": time.strftime("%Y-%m-%d"), "alphabet": ALPHABET, "leagues": index}, f, ensure_ascii=False)
        f.write(";\n")

if __name__ == "__main__":
    os.makedirs(CACHE, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--build" not in sys.argv:
        for lg in (args or LEAGUES): pull_league(lg)
    build(args or LEAGUES)
