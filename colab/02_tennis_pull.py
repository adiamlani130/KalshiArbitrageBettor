# Tennis pull (run after 01_setup.py). Output: set1_all.csv
# One row per ATP match: the set-1 winner, their match price ~1-2 min after set 1 ended,
# their pre-match price, the match result, and set-1 start/end times.
# Set 1's end time comes from the KXATPSETWINNER "set 1" market, which closes when the set ends.
match = {m["ticker"]: m for m in all_mk("KXATPMATCH") + all_mk("KXATPMATCH", hist=True, n=6000)}
s1 = [m for m in all_mk("KXATPSETWINNER") + all_mk("KXATPSETWINNER", hist=True, n=15000)
      if m["ticker"].split("-")[2] == "1" and m.get("result") == "yes"]
print(len(match), "match markets,", len(s1), "set-1 results")

rows = []
for n_done, s in enumerate(s1):
    if n_done % 200 == 0: print(n_done, "checked,", len(rows), "saved")
    code, side = s["ticker"].split("-")[1], s["ticker"].split("-")[3]
    T = int(pd.Timestamp(s["close_time"]).timestamp())
    tk = f"KXATPMATCH-{code}-{side}"; flip = tk not in match   # flip = only the opponent's market exists
    if flip:
        tk = next((t for t in match if t.startswith(f"KXATPMATCH-{code}-")), None)
        if not tk: continue
    c = cdl("KXATPMATCH", tk, T - 4*3600, T + 600)
    if not c: continue
    ts = np.array([x["end_period_ts"] for x in c]); vol = np.array([vf(x) for x in c])
    bid = np.array([f(x, "yes_bid") for x in c]); ask = np.array([f(x, "yes_ask") for x in c])
    j = int(np.argmax(ts >= T + 60))                     # first minute >= 60s after set 1 ends
    if ts[j] < T + 60: continue
    rv = pd.Series(vol).rolling(10, min_periods=1).sum().values
    i = int(np.argmax(rv > 0.25 * rv.max()))             # match start = first big volume spike
    pre = np.nanmedian(((bid + ask) / 2)[max(0, i-20):max(1, i-2)])
    won = match[tk]["result"] == ("no" if flip else "yes")
    b, a = (1 - ask[j], 1 - bid[j]) if flip else (bid[j], ask[j])
    rows.append(dict(code=code, player=s.get("yes_sub_title"), bid=b, ask=a, won=won,
                     pre=1 - pre if flip else pre, lag=ts[j] - T, start=int(ts[i]), t_end=T))
pd.DataFrame(rows).to_csv("set1_all.csv", index=False); print(len(rows), "matches saved")
# Note: in the original run the archive fields weren't handled yet, so older matches were
# re-pulled separately into set1_hist.csv. With f()/vf() above, one pass covers both.
