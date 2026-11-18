"""Pull the data behind the "Markets vs stocks" lab: Kalshi probabilities for economic, policy and
company questions, lined up against daily and hourly stock prices from Yahoo Finance. No keys needed.

    python scripts/pull_stocks.py            # about 15 minutes, resumable
    python scripts/pull_stocks.py --build    # rebuild app/data/stocks.js from the cache

What it saves (app/data/stocks.js):
  dates    - every US trading day since START
  px       - open and (dividend-adjusted) close for ~100 stocks and ETFs on those days
  signals  - Kalshi markets with real volume and a life of two weeks or more; one probability per
             trading day, read at 4:00pm New York time (the stock close), so the two line up exactly
  shocks   - the biggest one-hour jumps in each busy Kalshi market, with what linked stocks did in the
             hours before and after (first price you could actually trade, then +1h ... +3 days)
  events   - scheduled announcements (Fed, CPI, jobs, GDP, unemployment): what Kalshi expected the
             evening before, what happened, and so how big the surprise was. Also earnings calls:
             Kalshi's "what will the CEO say" markets give the call date for ~60 companies and a
             measure of how unexpected the call was
"""
import json, os, re, sys, threading, time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
YAHOO = "https://query2.finance.yahoo.com/v8/finance/chart/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "stocks_cache")
OUT = os.path.join(ROOT, "app", "data", "stocks.js")
START = "2024-09-03"
ET = ZoneInfo("America/New_York")
MIN_VOLUME, MIN_DAYS, PER_SERIES = 20000, 14, 5

# theme: (label, Kalshi series to search, stocks/ETFs that should care)
THEMES = {
 "fed": ("Fed & interest rates", "KXFEDDECISION FEDDECISION KXFED FED KXRATECUTCOUNT RATECUTCOUNT KXFEDFUNDSYEAR KXLOWESTRATE KXTERMINALRATE KXRATECUT KXFEDCUT KXFEDHIKE KXEMERCUTS KX10YR550PCT KXMORTGAGERATE KXFRMMIN KXFRMMAX",
         "TLT IEF SHY KRE XLF IWM XHB ITB XLU XLRE GLD UUP SPY QQQ TOL LEN DHI JPM BAC"),
 "fedchair": ("Fed chair & independence", "KXFEDCHAIRNOM KXPRESNOMFEDCHAIR KXLEAVEPOWELL KXPOWELLLEAVE LEAVEPOWELL POWELLLEAVE KXTRYFIREPOWELL KXFEDCHAIRCONFIRM KXFEDCHAIRCONFIRMED KXPOWELLPROTEMP KXLEAVEPOWELLGOV KXTRUMPPOW",
              "TLT GLD UUP KRE SPY IWM XLF SLV"),
 "recession": ("Recession & growth", "KXRECSSNBER RECSSNBER KXQRECESS KXNBERRECESSQ KXGDP GDP KXGDPYEAR KXU3EOY KXU3MAX KXGDPUSMIN KXIMFRECESS",
               "SPY IWM XLY XLP HYG LQD XLI TLT KRE CAT XRT VXX"),
 "inflation": ("Inflation", "KXACPI ACPI KXHIGHINFLATION KXCPIYOY KXCPICOREYOY", "TIP GLD TLT XLE SLV XLP SPY"),
 "shutdown": ("Government shutdown & debt", "KXGOVSHUT GOVSHUT KXSHUTDOWNBY KXSHUTDOWNBYDATE SHUTDOWNBY KXGOVSHUTLENGTH KXGOVTSHUTLENGTH GOVSHUTLENGTH KXSHUTLENGTH KXDCEIL DCEIL KXNUMSHUTDOWNS",
              "SPY ITA LMT RTX NOC UNH TLT VXX IWM"),
 "tariffs": ("Tariffs & trade", "KXDJTVOSTARIFFS KXTARIFFS KXTARIFFPRC KXTARIFFSPRC KXTRADEDEALPRC KXUSCHINATRUCE KXTARIFFAGREE KXLARGETARIFF KXTARIFFSEMI KXTARIFFPHARMA KXTARIFFSSTEEL KXTARIFFSCOPPER KXTARIFFSALUMINUM KXTARIFFSCANADA KXTARIFFSMEX KXTARIFFSEU KXAVGTARIFF KXEFFTARIFF KXTARIFFREFUND KXTARIFFRATEPRC KXTARIFFRATEEU KXTARIFFRATECAN KXTARIFFRATEMEX KXTARIFFRATEJP KXTARIFFKILL KXBLOCKTARIFF KXCIT301 KXNEWTARIFFS KXTARIFFSNEW KXGLOBALTARIFFS KXTARIFFENDGLOBAL KXTARIFFENDPRC KXNEWDEAL KXCANUSDEAL KXTARIFFSGLOBAL KXTARIFFCHECKS KXTARREBATE KXTARIFFDECISIONRELEASE KXTRUMPSCOTUSVOTE",
             "SPY XRT NKE WMT TGT BBY GM F CAT DE NUE CLF FCX SMH AAPL FXI KWEB EWW EWC EWJ XLI PFE LLY MRK COST HD"),
 "chips": ("Chips, AI & China tech", "KXGPURULE KXH200REVOKE KXCHIPEXPORTLAW KXCHINAAIEXPORT KXCHIPSREPEAL KXHUANGCHINA KXCHINARARE KXCHINABOEING KXCHIPREMOTE KXCHINAEUV KXTOPMODEL KXCODINGMODEL KXTOPLLMCHANGE KXOAIPROFIT KXOPENAIPROFIT KXAGICO KXOAIAGI KXTRUMPCHINA KXRECOGROC KXTAIWANLVL4",
           "NVDA AMD SMH SOXX INTC AVGO TSM MU MP BA GOOGL MSFT META ORCL PLTR"),
 "tiktok": ("TikTok", "KXTIKTOKBAN TIKTOKBAN KXTIKTOKSELL KXTIKTOKEXTENSION KXACQUANNOUNCETIKTOK KXTIKTOKCOURT TIKTOKCOURT KXTIKTOKSCOTUS KXTIKTOKDJT KXTIKTOKLEAVE KXTIKTOKSTORE",
            "META SNAP PINS GOOGL ORCL"),
 "policy": ("Tax, energy & crypto policy", "KXCORPTAX KXCORPTAXCUT KXEVCREDITS KX48ETAXCREDIT KXSTABLECOIN KXSALT KXCAPGAIN KXMARIJUANA280E KXTIPTAX KXBTCRESERVE KXCRUDEEXPORTBAN KXSENATEACAEXT",
            "TSLA RIVN TAN ENPH FSLR ICLN COIN HOOD MSTR IBIT MSOS UNH XLE SPY"),
 "elections": ("Elections", "PRES POPVOTE KXPOPVOTE KXCONTROLH CONTROLH KXCONTROLS CONTROLS KXPRESPARTY PRESPARTYFULL KXGOVSENSPLIT",
               "DJT GEO CXW TSLA TAN ICLN XLE XLF KRE COIN IBIT SPY IWM UNH LMT FSLR"),
 "tesla": ("Tesla & Musk", "KXTSLA KXTSLAA TESLA ROBOTAXI KXROBOTAXI ROBOTAXIOUT KXUFSD KXTESLAOPTIMUS TESLAOPTIMUS KXTRUMPTESLA KXROBOTAXIAREA KXROBOTAXICA KXTESLATARIFF KXACQANNOUNCESPACEX",
           "TSLA RIVN GM F UBER ARKK"),
 "deals": ("Deals & company events", "KXACQPYPL KXACQANNOUNCEWDAY KXACQANNOUNCECART KXACQUIREDFIRST KXACQANNOUNCECHROME KXACQUIRECHROME KXAPPLEUS APPLEUS KXAPPLEAI KXHOODA KXMETAA KXUBERA KXBAA KXCOMPANYLAYOFF KXIPOFANNIE KXANTITRUSTOAIMSFT KXNVIDIAGROQFINE",
           "AAPL GOOGL MSFT META UBER BA HOOD NVDA AMZN"),
 "index": ("Index, gold & oil targets", "KXINXY INXY KXINXMAXY KXINXMINY KXINXPOS KXINXEOYCLOSE KXINXMAX2026 KXNASDAQ100Y NASDAQ100Y KXNASDAQ100MAXY KXNASDAQ100MINY KXRUTA KXRUTH KXRUTL KXGOLDYEAR KXGOLDEOY KXGOLDY KXWTIMAX KXWTIMIN WTIMAX WTIMIN KXSILVERYEAR KXINXVSGOLD KXINXVSBTC KXWTIVSBRENT",
           "SPY QQQ IWM DIA GLD GDX SLV USO XLE XOM CVX OXY VXX TLT"),
 "mergers": ("Mergers & takeovers", "KXTAKEOVERACQWB KXACQANNOUNCEEBAY KXTAKEOVERNEE KXCOMPANYACTIONEA KXCOMPANYACTIONMERGER KXTAKEOVERUNP KXACQUANNOUNCEBANCOS KXACQPYPL KXACQANNOUNCEWDAY KXACQANNOUNCESBUX KXACQANNOUNCEGDDY",
             "WBD PSKY NFLX EBAY GME D NEE EA TSLA UNP NSC PYPL WDAY SBUX GDDY CMCSA"),
 "crypto": ("Bitcoin & crypto", "KXBTCMAXY KXBTCMINY KXBTCY KXBTC2025100 KXBTCMAX150 KXETHMAXY KXETHMINY KXETHY KXBTCVSGOLD KXCHINAUNBANBTC",
            "COIN MSTR IBIT MARA HOOD ARKK QQQ"),
}
EXTRA = "DIA EFA EEM AMZN NFLX GS WFC C LOW DAL UAL XLK XLB XLV"
TICKERS = sorted(set(" ".join(v[2] for v in THEMES.values()).split() + EXTRA.split()))
# scheduled announcements: series -> (label, how a market's ticker/strike maps to a "higher than expected" direction)
SCHEDULED = {"KXFEDDECISION": "Fed decision", "FEDDECISION": "Fed decision", "KXCPI": "CPI (month over month)",
             "KXCPIYOY": "CPI (year over year)", "KXCPICORE": "Core CPI", "KXPAYROLLS": "Jobs report",
             "KXU3": "Unemployment rate", "KXGDP": "GDP growth"}
FED_W = {"H0": 0, "C25": -1, "C26": -2, "H25": 1, "H26": 2}
EARN = re.compile(r"^KX(?:EARNINGSMENTION|MENTIONEARN|EARNIGNSMENTION)([A-Z]{1,5})$")   # -> company ticker

_local, _lock, _next = threading.local(), threading.Lock(), [0.0]
def get(url, **p):
    s = getattr(_local, "s", None) or requests.Session(); _local.s = s
    s.headers["User-Agent"] = "Mozilla/5.0"
    for attempt in range(7):
        with _lock:
            wait = _next[0] - time.time(); _next[0] = max(time.time(), _next[0]) + 0.12
        if wait > 0: time.sleep(wait)
        try:
            r = s.get(url, params={k: v for k, v in p.items() if v is not None}, timeout=30)
            if r.status_code in (429, 500, 502, 503): time.sleep(1.5 * (attempt + 1)); continue
            return r.json()
        except Exception:
            time.sleep(1 + attempt)
    return {}
def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)
def ts(iso): return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
def cached(name, fn):
    path = os.path.join(CACHE, name + ".json")
    if os.path.exists(path): return json.load(open(path))
    v = fn(); json.dump(v, open(path, "w")); return v
fv = lambda m: float(m.get("volume_fp") or m.get("volume") or 0)

def markets(series):
    out = {}
    for path in ("/markets", "/historical/markets"):
        cur = None
        while True:
            r = get(BASE + path, series_ticker=series, limit=1000, cursor=cur)
            for m in r.get("markets", []): out.setdefault(m["ticker"], m)
            cur = r.get("cursor")
            if not cur or not r.get("markets"): break
    keep = ("ticker event_ticker title yes_sub_title result status open_time close_time volume_fp volume "
            "floor_strike cap_strike strike_type rules_primary").split()
    return [{k: m.get(k) for k in keep if m.get(k) is not None} for m in out.values()]

def candles(series, tk, a, b, interval):
    out = []
    span = 100 * 86400 if interval == 60 else 2000 * 86400
    while a < b:
        e = min(b, a + span); got = []
        for path in (f"/series/{series}/markets/{tk}/candlesticks", f"/historical/markets/{tk}/candlesticks"):
            got = get(BASE + path, start_ts=a, end_ts=e, period_interval=interval).get("candlesticks") or []
            if got: break
        out += got; a = e
    rows, last = [], None
    for c in sorted(out, key=lambda c: c["end_period_ts"]):
        d = lambda k: (lambda v: None if v is None else float(v))((c.get(k) or {}).get("close_dollars", (c.get(k) or {}).get("close")))
        bid, ask, tr = d("yes_bid"), d("yes_ask"), d("price")
        p = (bid + ask) / 2 if bid is not None and ask is not None and 0 < ask - bid <= 0.06 else tr
        if p is None: p = last
        if p is not None: rows.append([c["end_period_ts"], round(p, 4)]); last = p
    return rows

def yahoo(tk, interval):
    r = get(YAHOO + tk, period1=ts(START + "T00:00:00Z") - 5 * 86400, period2=int(time.time()), interval="1d") if interval == "1d" \
        else get(YAHOO + tk, range="730d", interval="1h")
    try:
        r = r["chart"]["result"][0]; q = r["indicators"]["quote"][0]
        adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
        return [[t, o, c, a] for t, o, c, a in zip(r["timestamp"], q["open"], q["close"], adj) if o and c and a]
    except Exception:
        return []

def pull():
    os.makedirs(CACHE, exist_ok=True)
    for tk in TICKERS:
        for iv in ("1d", "1h"): cached(f"px_{iv}_{tk}", lambda: yahoo(tk, iv))
    log("prices done")
    series = {s: th for th, v in THEMES.items() for s in v[1].split()}
    with ThreadPoolExecutor(4) as ex:
        allm = dict(zip(series, ex.map(lambda s: cached("mk_" + s, lambda: markets(s)), series)))
    now, t0, picked = int(time.time()), ts(START + "T00:00:00Z"), []
    for s, ms in allm.items():
        ok = [m for m in ms if fv(m) >= (5000 if series[s] == "mergers" else MIN_VOLUME) and min(ts(m["close_time"]), now) - max(ts(m["open_time"]), t0) >= MIN_DAYS * 86400]
        picked += [(s, m) for m in sorted(ok, key=lambda m: -fv(m))[:PER_SERIES]]
    log(len(series), "series,", len(picked), "markets picked")
    def one(x):
        s, m = x
        return cached("c60_" + m["ticker"], lambda: candles(s, m["ticker"], max(ts(m["open_time"]), t0), min(ts(m["close_time"]), now) + 3600, 60))
    with ThreadPoolExecutor(4) as ex: list(ex.map(one, picked))
    json.dump([[s, m] for s, m in picked], open(os.path.join(CACHE, "picked.json"), "w"))
    log("signal candles done")
    ev = []
    for s in SCHEDULED:
        ms = [m for m in cached("mk_" + s, lambda: markets(s)) if m.get("result") in ("yes", "no") and ts(m["close_time"]) > t0 and fv(m) >= 2000]
        ev += [(s, m) for m in ms]
    def two(x):
        s, m = x
        return cached("c1d_" + m["ticker"], lambda: candles(s, m["ticker"], max(ts(m["open_time"]), ts(m["close_time"]) - 20 * 86400), ts(m["close_time"]) + 86400, 1440))
    with ThreadPoolExecutor(4) as ex: list(ex.map(two, ev))
    json.dump([[s, m] for s, m in ev], open(os.path.join(CACHE, "events.json"), "w"))
    log(len(ev), "announcement markets done")
    # earnings calls: every "what will they say on the earnings call" series, up to 5 busiest phrases per call
    sers = cached("earn_series", lambda: [x["ticker"] for x in get(BASE + "/series", category="Mentions").get("series", []) if EARN.match(x["ticker"])])
    earn = []
    for s in sers:
        tk = EARN.match(s).group(1)
        if not cached("px_1d_" + tk, lambda: yahoo(tk, "1d")): continue
        by = {}
        for m in cached("mk_" + s, lambda: markets(s)):
            if m.get("result") in ("yes", "no") and ts(m["close_time"]) > t0 and fv(m) >= 300: by.setdefault(m["event_ticker"], []).append(m)
        for ms in by.values(): earn += [(s, m) for m in sorted(ms, key=lambda m: -fv(m))[:5]]
    with ThreadPoolExecutor(4) as ex: list(ex.map(two, earn))
    json.dump([[s, m] for s, m in earn], open(os.path.join(CACHE, "earnings.json"), "w"))
    log(len(sers), "earnings-call series,", len(earn), "phrase markets done")

# ------------------------------------------------------------------ build
def build():
    load = lambda n: json.load(open(os.path.join(CACHE, n + ".json")))
    day = lambda t: datetime.fromtimestamp(t, ET).strftime("%Y-%m-%d")
    spy = [r for r in load("px_1d_SPY") if day(r[0]) >= START]
    dates = [day(r[0]) for r in spy]; di = {d: i for i, d in enumerate(dates)}
    close16 = [int(datetime.strptime(d + " 16:00", "%Y-%m-%d %H:%M").replace(tzinfo=ET).timestamp()) for d in dates]
    px, hourly = {}, {}
    earn = load("earnings") if os.path.exists(os.path.join(CACHE, "earnings.json")) else []
    earn_tk = sorted({EARN.match(s).group(1) for s, _ in earn} - set(TICKERS))
    for tk in TICKERS + earn_tk:
        o, c = [None] * len(dates), [None] * len(dates)
        for t, op, cl, adj in load("px_1d_" + tk):
            i = di.get(day(t))
            if i is not None: c[i] = round(adj, 3); o[i] = round(op * adj / cl, 3)
        if sum(v is not None for v in c) > 60: px[tk] = {"o": o, "c": c}
        if tk in TICKERS: hourly[tk] = [r for r in load("px_1h_" + tk)]
    # delisted stocks Yahoo no longer serves (e.g. a takeover target after the deal closed): data/manual/<TICKER>.csv
    manual = os.path.join(ROOT, "data", "manual")
    for f in sorted(os.listdir(manual)) if os.path.isdir(manual) else []:
        o, c = [None] * len(dates), [None] * len(dates)
        for line in open(os.path.join(manual, f)).read().split()[1:]:
            d, op, cl = line.split(","); i = di.get(d)
            if i is not None: o[i], c[i] = float(op), float(cl)
        px[f[:-4]] = {"o": o, "c": c}
    log(len(px), "tickers,", len(dates), "days")

    signals, shocks = [], []
    picked = load("picked")
    for s, m in sorted(picked, key=lambda x: -fv(x[1])):
        cs = load("c60_" + m["ticker"])
        if len(cs) < 48: continue
        T = [c[0] for c in cs]; P = [c[1] for c in cs]
        end = min(ts(m["close_time"]), T[-1] + 3600)
        def at(t):
            k = bisect_right(T, t) - 1
            return round(P[k] * 1000) / 10 if k >= 0 and T[0] <= t <= end and t - T[k] < 4 * 86400 else None
        p = [at(t) for t in close16]                      # 4:00pm, the stock close
        q = [at(t + 3600) for t in close16]               # 5:00pm: the first price you can trade after seeing the close
        vals = [v for v in p if v is not None]
        if len(vals) < 12 or max(vals) - min(vals) < 4: continue
        th = next(k for k, v in THEMES.items() if s in v[1].split())
        sub = m.get("yes_sub_title") or ""
        title = re.sub(r"\s+", " ", m["title"].replace("*", "").replace("above_below_between ?", "be:")).strip()
        if sub and sub.lower() not in title.lower() and sub.lower() not in ("yes", "starts"): title += f" — {sub}"
        sid = len(signals)
        signals.append(dict(id=m["ticker"], title=title, theme=th, vol=round(fv(m)), result=m.get("result") or None,
                            open=day(ts(m["open_time"])), close=day(ts(m["close_time"])), p=p, q=q))
        # One-hour jumps of 6+ points, taken in time order and at least 3 days apart. Every jump that meets the
        # rule is kept: nothing is filtered on what the price did afterwards, which you could not know at the time.
        if sid >= 140: continue
        used = []
        for i in range(1, len(P)):
            if not (T[i] - T[i - 1] <= 3600 and abs(P[i] - P[i - 1]) >= 0.06 and 0.03 < P[i] < 0.97 and T[i] < end - 3600): continue
            if (used and T[i] - used[-1] < 3 * 86400) or len(used) >= 10: continue
            used.append(T[i])
            rec = dict(s=sid, t=T[i], d=datetime.fromtimestamp(T[i], ET).strftime("%Y-%m-%d %H:%M"),
                       p0=round(P[i - 1] * 100, 1), p1=round(P[i] * 100, 1), r={})
            for tk in ["SPY"] + [x for x in THEMES[th][2].split() if x != "SPY"][:9]:
                h = hourly.get(tk) or []
                if not h: continue
                hs = [x[0] for x in h]
                a = bisect_right(hs, T[i] - 3600 - 3600) - 1          # last bar that finished before the Kalshi hour began
                b = bisect_right(hs, T[i] - 1)                       # first bar that starts after the Kalshi hour ended
                if a < 7 or b >= len(h) - 22 or hs[b] - T[i] > 4 * 86400: continue
                ref = h[a][2]; f = lambda v: round((v / ref - 1) * 100, 2)
                rec["r"][tk] = [f(h[a - 7][2]), f(h[a - 3][2]), f(h[b][1])] + [f(h[b + k][2]) for k in (0, 1, 3, 6, 13, 20)]
            if len(rec["r"]) > 1: shocks.append(rec)
    log(len(signals), "signals,", len(shocks), "shocks")

    events = {}
    for s, m in load("events") + earn:
        cs = load("c1d_" + m["ticker"])
        tc = ts(m["close_time"])
        before = [c for c in cs if c[0] <= tc - 6 * 3600]
        if not before: continue
        e = events.setdefault(m["event_ticker"], dict(kind=SCHEDULED.get(s, "Earnings calls"), t=tc, mk=[],
                                                      tk=EARN.match(s).group(1) if EARN.match(s) else None))
        e["t"] = min(e["t"], tc)
        e["mk"].append((m, before[-1][1]))
    out_events = []
    for et, e in events.items():
        i = next((k for k, t in enumerate(close16) if t > e["t"]), None)     # first stock close after the news
        if i is None or i < 1 or len(e["mk"]) < 2 or (e["tk"] and e["tk"] not in px): continue
        fed = e["kind"] == "Fed decision"
        if fed: sur = sum(FED_W.get(m["ticker"].rsplit("-", 1)[1], 0) * ((m["result"] == "yes") - p) for m, p in e["mk"])
        else: sur = sum((m["result"] == "yes") - p for m, p in e["mk"])
        hit = [(m, p) for m, p in e["mk"] if m["result"] == "yes"]
        top = max(e["mk"], key=lambda x: x[1])
        lab = lambda m: m.get("yes_sub_title") or m["ticker"].rsplit("-", 1)[1]
        if e["tk"]:
            m, p = max(e["mk"], key=lambda x: abs((x[0]["result"] == "yes") - x[1])); sur = None
            what = f'{"Said" if m["result"] == "yes" else "Did not say"} "{lab(m)}" (priced {p * 100:.0f}%)'
        elif fed and hit: what = f"{lab(hit[0][0])} (priced {hit[0][1] * 100:.0f}%)"
        else: what = f"{sum(m['result'] == 'yes' for m, _ in e['mk'])} of {len(e['mk'])} thresholds cleared; {sum(p for _, p in e['mk']):.1f} were expected"
        out_events.append(dict(id=et, kind=e["kind"], date=dates[i], i=i, tk=e["tk"], surprise=None if sur is None else round(sur, 3),
                               shock=round(sum(abs((m["result"] == "yes") - p) for m, p in e["mk"]) / len(e["mk"]), 3),
                               what=what, n=len(e["mk"])))
    out_events.sort(key=lambda x: x["date"])
    log(len(out_events), "announcements")

    data = dict(built=time.strftime("%Y-%m-%d"), dates=dates, px=px, signals=signals, shocks=shocks, events=out_events,
                themes={k: dict(label=v[0], tickers=[t for t in v[2].split() if t in px]) for k, v in THEMES.items()},
                core=[t for t in TICKERS if t in px],
                shock_steps=["7h before", "3h before", "first trade", "+1h", "+2h", "+4h", "+1 day", "+2 days", "+3 days"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("window.STOCK_DATA="); json.dump(data, f, separators=(",", ":")); f.write(";\n")
    log("wrote", OUT, round(os.path.getsize(OUT) / 1e6, 2), "MB")

if __name__ == "__main__":
    if "--build" not in sys.argv: pull()
    build()
