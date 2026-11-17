// "All sports" dataset: one row per game with the whole in-game price path (a price every 1-2 minutes),
// so any timing rule can be tested in the browser: fixed moments, price triggers, drops, jumps, exits.
// League files (data/sports_<league>.js) load only when a league is switched on.
(function () {
  const IDX = window.EDGE_SPORTS_INDEX;
  if (!IDX) return;
  const CODE = {}; [...IDX.alphabet].forEach((ch, i) => (CODE[ch] = i));
  const loaded = {}, loading = {};
  const decode = (s) => { const a = new Float32Array(s.length); let last = NaN;
    for (let i = 0; i < s.length; i++) { const v = CODE[s[i]]; if (v !== undefined) last = v; a[i] = last; } return a; };
  // An empty order book (bid 0, ask 100) is not a price: keep the last real quote instead.
  const clean = (bid, ask) => { for (let i = 1; i < bid.length; i++) if (!(ask[i] - bid[i] <= 30)) { bid[i] = bid[i - 1]; ask[i] = ask[i - 1]; } };
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const fmtET = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23", weekday: "short" });
  const STAGE = { REG: "Regular season", POST: "Playoffs", PRE: "Preseason" };

  function build(lg) {
    const meta = IDX.leagues[lg], t = window.EDGE_SPORTS[lg], ix = Object.fromEntries(t.cols.map((c, i) => [c, i]));
    return t.rows.map((r) => {
      const g = (k) => r[ix[k]];
      const parts = Object.fromEntries(fmtET.formatToParts(new Date(g("ts") * 1000)).map((p) => [p.type, p.value]));
      const three = meta.three, aB = decode(g("b")), aA = decode(g("a"));
      clean(aB, aA);
      const bB = three ? decode(g("Bb")) : aA.map((v) => 100 - v), bA = three ? decode(g("Ba")) : aB.map((v) => 100 - v);
      if (three) clean(bB, bA);
      // [bid, ask] for A and B at each pre-game moment (B = buying "No" on A when there are only two outcomes)
      const pair = (k) => { const a = g(k); if (!a) return null; const b = three ? g("B" + k) : [100 - a[1], 100 - a[0]]; return b ? [a, b] : null; };
      const pre = pair("pre"), mid = (p) => (p[0] + p[1]) / 2;
      if (!pre) return null;
      const favA = mid(pre[0]) >= mid(pre[1]), F = favA ? 0 : 1, home = g("home") ? 0 : null;
      const o = { lg, league: meta.label, sport: meta.sport, step: meta.step, three, date: `${parts.year}-${parts.month}-${parts.day}`,
        weekday: DAYS.find((d) => d.startsWith(parts.weekday)), hour: +parts.hour, names: [g("A"), g("B")],
        match: home === 0 ? `${g("B")} @ ${g("A")}` : `${g("A")} vs ${g("B")}`, home, win: g("draw") ? -1 : g("won") ? 0 : 1,
        stage: STAGE[g("season")] || "Other / unknown", vol: g("vol"), pvol: g("pvol"), mins: g("mins"),
        bid: [aB, bB], ask: [aA, bA], pre, open: pair("open"), h24: pair("h24"), h1: pair("h1"), fav: F, n: aA.length };
      o.fav_pre = mid(pre[F]) / 100; o.fav_name = o.names[F]; o.dog_name = o.names[1 - F];
      if (home === 0) o.home_pre = mid(pre[0]) / 100;
      for (const [k, key] of [["open", "move_open"], ["h24", "move_24h"], ["h1", "move_1h"]]) if (o[k]) o[key] = (mid(pre[F]) - mid(o[k][F])) / 100;
      // after-the-fact descriptors (for Find a link only)
      let lo = 100, hi = 0, flips = 0, side = 0;
      for (let i = 0; i < o.n; i++) { const m = (o.bid[F][i] + o.ask[F][i]) / 2; if (m < lo) lo = m; const d = 100 - m; if (d > hi) hi = d;
        const s = m > 52 ? 1 : m < 48 ? -1 : 0; if (s && side && s !== side) flips++; if (s) side = s; }
      o.fav_low = lo / 100; o.dog_high = hi / 100; o.flips = flips; o.fav_won = o.win === F; o.was_draw = o.win === -1;
      return o;
    }).filter(Boolean);
  }
  function ensure(leagues, done) {
    const need = leagues.filter((l) => !loaded[l]);
    if (!need.length) return true;
    need.forEach((l) => {
      if (loading[l]) return; loading[l] = true;
      const s = document.createElement("script"); s.src = `data/sports_${l}.js`;
      s.onload = () => { loaded[l] = build(l); delete window.EDGE_SPORTS[l]; if (leagues.every((x) => loaded[x])) done(); };
      s.onerror = () => { loaded[l] = []; done(); };
      document.head.appendChild(s);
    });
    return false;
  }

  // ---------------------------------------------------------------- finding the moment
  const WATCH = [{ id: "fav", label: "the pre-game favorite" }, { id: "dog", label: "the pre-game underdog" },
                 { id: "home", label: "the home team" }, { id: "away", label: "the away team" }, { id: "either", label: "either team" }];
  const watchSides = (r, w) => w === "fav" ? [r.fav] : w === "dog" ? [1 - r.fav] : w === "home" ? (r.home === 0 ? [0] : []) : w === "away" ? (r.home === 0 ? [1] : []) : [0, 1];
  const midAt = (r, s, i) => (r.bid[s][i] + r.ask[s][i]) / 2;
  const P = (id, label, def, min, max) => ({ id, label, def, min, max });
  const X = P("x", "Price (¢)", 30, 1, 99), M = P("m", "Within (minutes)", 10, 2, 120);
  const watchP = { id: "w", label: "Watch", def: "fav", options: WATCH };
  const MOMENTS = [
    { id: "pre", label: "Just before the start", phrase: "just before the start", at: 0 },
    { id: "h1", label: "1 hour before the start", phrase: "an hour before the start", at: 0 },
    { id: "h24", label: "24 hours before the start", phrase: "a day before the start", at: 0 },
    { id: "t", label: "A set time into the game", phrase: (p) => `${p.t} minutes into the game`, at: 1, params: [P("t", "Minutes after the start", 30, 2, 400)] },
    { id: "below", label: "When a team's price first falls to…", phrase: (p) => `the first time ${wl(p.w)} falls to ${p.x}¢ or less`, at: 1, trig: true, params: [watchP, X] },
    { id: "above", label: "When a team's price first rises to…", phrase: (p) => `the first time ${wl(p.w)} reaches ${p.x}¢ or more`, at: 1, trig: true, params: [watchP, Object.assign({}, X, { def: 80 })] },
    { id: "drop", label: "When a team falls X¢ from its in-game high", phrase: (p) => `the first time ${wl(p.w)} is ${p.x}¢ off its in-game high`, at: 1, trig: true, params: [watchP, Object.assign({}, X, { label: "Drop (¢)", def: 20 })] },
    { id: "rise", label: "When a team climbs X¢ from its in-game low", phrase: (p) => `the first time ${wl(p.w)} is ${p.x}¢ above its in-game low`, at: 1, trig: true, params: [watchP, Object.assign({}, X, { label: "Climb (¢)", def: 20 })] },
    { id: "crash", label: "When a team drops X¢ within a few minutes", phrase: (p) => `the first time ${wl(p.w)} drops ${p.x}¢ within ${p.m} minutes`, at: 1, trig: true, params: [watchP, Object.assign({}, X, { label: "Drop (¢)", def: 15 }), M] },
    { id: "spike", label: "When a team jumps X¢ within a few minutes", phrase: (p) => `the first time ${wl(p.w)} jumps ${p.x}¢ within ${p.m} minutes`, at: 1, trig: true, params: [watchP, Object.assign({}, X, { label: "Jump (¢)", def: 15 }), M] },
  ];
  function wl(w) { return (WATCH.find((x) => x.id === w) || WATCH[0]).label; }
  // Returns { i: sample index where the rule was first seen, s: which team triggered it } or null.
  function find(r, moment, p) {
    if (moment === "t") { const i = Math.round(p.t / r.step); return i >= 0 && i < r.n - 1 ? { i, s: r.fav } : null; }
    const sides = watchSides(r, p.w), x = +p.x, k = Math.max(1, Math.round((p.m || 10) / r.step));
    const hi = [0, 0], lo = [100, 100];
    for (let i = 0; i < r.n - 1; i++) {
      for (const s of sides) {
        const m = midAt(r, s, i); if (!(m >= 0)) continue;
        if (m > hi[s]) hi[s] = m; if (m < lo[s]) lo[s] = m;
        if (i === 0) continue;
        const m0 = midAt(r, s, 0);
        if (moment === "below" && m0 > x && m <= x) return { i, s };
        if (moment === "above" && m0 < x && m >= x) return { i, s };
        if (moment === "drop" && hi[s] - m >= x) return { i, s };
        if (moment === "rise" && m - lo[s] >= x) return { i, s };
        if (moment === "crash" || moment === "spike") {
          const b = midAt(r, s, Math.max(0, i - k)), d = m - b;
          if (moment === "crash" ? d <= -x : d >= x) return { i, s };
        }
      }
    }
    return null;
  }

  // ---------------------------------------------------------------- the bet
  const SIDES_FIXED = [{ id: "fav", label: "The pre-game favorite" }, { id: "dog", label: "The pre-game underdog" },
                       { id: "home", label: "The home team" }, { id: "away", label: "The away team" }];
  const SIDES_TRIG = [{ id: "trig", label: "The team that triggered it" }, { id: "other", label: "The other team" }].concat(SIDES_FIXED);
  const SIDES_T = [{ id: "leader", label: "Whoever is ahead on price" }, { id: "trailer", label: "Whoever is behind on price" }].concat(SIDES_FIXED);
  function pickSide(r, side, hit, i) {
    if (side === "fav") return r.fav; if (side === "dog") return 1 - r.fav;
    if (side === "home") return r.home === 0 ? 0 : null; if (side === "away") return r.home === 0 ? 1 : null;
    if (side === "trig") return hit.s; if (side === "other") return 1 - hit.s;
    const a = midAt(r, 0, i), b = midAt(r, 1, i); if (a === b) return null;
    return (a > b) === (side === "leader") ? 0 : 1;
  }
  function bet(r, moment, side, p, exit) {
    const mo = MOMENTS.find((m) => m.id === moment);
    if (!mo.at) {   // before the game: one price, hold to the end
      const q = r[moment]; if (!q) return null;
      const s = pickSide(r, side, null, 0); if (s == null) return null;
      return { p: q[s][1] / 100, won: r.win === s, pick: r.names[s], x: { pick_fav: s === r.fav, pick_home: r.home === 0 ? s === 0 : null, pick_pre: (r.pre[s][0] + r.pre[s][1]) / 200 } };
    }
    const hit = find(r, moment, p); if (!hit) return null;
    const i = hit.i, e = i + 1;                     // see it at sample i, get filled one sample (1-2 minutes) later
    if (e >= r.n) return null;
    const s = pickSide(r, side, hit, i); if (s == null) return null;
    const price = r.ask[s][e]; if (!(price >= 2 && price <= 98)) return null;
    let hi = 0, lo = 100, flips = 0, sd = 0;
    for (let j = 0; j <= i; j++) { const m = midAt(r, s, j); if (m > hi) hi = m; if (m < lo) lo = m;
      const z = m > 52 ? 1 : m < 48 ? -1 : 0; if (z && sd && z !== sd) flips++; if (z) sd = z; }
    const now = midAt(r, s, i), pre = (r.pre[s][0] + r.pre[s][1]) / 2, back = Math.max(0, i - Math.round(10 / r.step));
    const out = { p: price / 100, won: r.win === s, pick: r.names[s], x: {
      elapsed: i * r.step, pick_fav: s === r.fav, pick_home: r.home === 0 ? s === 0 : null, pick_pre: pre / 100, pick_chg: (now - pre) / 100,
      pick_high: hi / 100, pick_low: lo / 100, off_high: (hi - now) / 100, off_low: (now - lo) / 100,
      chg10: (now - midAt(r, s, back)) / 100, flips_sofar: flips, fav_now: midAt(r, r.fav, i) / 100 } };
    // what happened afterwards (only for Find a link)
    let best = 0, worst = 100;
    for (let j = e; j < r.n; j++) { const b = r.bid[s][j]; if (b > best) best = b; if (b < worst) worst = b; }
    out.x.best_after = (best - price) / 100; out.x.worst_after = (worst - price) / 100;
    // optional early exit: sell at the bid when a target, a stop or a time limit is hit
    const tp = +exit.tp || 0, sl = +exit.sl || 0, tm = +exit.tm || 0;
    if (tp || sl || tm) {
      for (let j = e + 1; j < r.n - 1; j++) {
        const b = r.bid[s][j];
        if (tp && b >= price + tp) { out.sell = (price + tp) / 100; break; }       // a resting sell order at the target
        if (sl && b <= price - sl) { out.sell = Math.max(1, b) / 100; break; }      // stop: sold at whatever the bid was
        if (tm && (j - e) * r.step >= tm) { out.sell = Math.max(1, b) / 100; break; }
      }
    }
    return out;
  }

  const cols = [
    { key: "date", label: "Date", type: "date", at: 0 },
    { key: "league", label: "League", type: "cat", at: 0 },
    { key: "sport", label: "Sport", type: "cat", at: 0 },
    { key: "stage", label: "Season stage", type: "cat", at: 0 },
    { key: "weekday", label: "Day of the week", type: "cat", at: 0 },
    { key: "hour", label: "Start hour (US Eastern, 0-23)", type: "num", at: 0 },
    { key: "match", label: "Team or player name contains", type: "text", at: 0 },
    { key: "fav_name", label: "Favorite's name contains", type: "text", at: 0 },
    { key: "fav_pre", label: "Favorite's price just before the start", type: "num", at: 0, pct: true },
    { key: "home_pre", label: "Home team's price just before the start", type: "num", at: 0, pct: true },
    { key: "move_1h", label: "Favorite's price move in the last hour before the start", type: "num", at: 0, pct: true },
    { key: "move_24h", label: "Favorite's price move in the last 24 hours", type: "num", at: 0, pct: true },
    { key: "move_open", label: "Favorite's price move since the market opened", type: "num", at: 0, pct: true },
    { key: "pvol", label: "Contracts traded before the start", type: "num", at: 0 },
    { key: "pick_fav", label: "Your pick was the pre-game favorite", type: "bool", at: 0, dyn: true },
    { key: "pick_home", label: "Your pick is the home team", type: "bool", at: 0, dyn: true },
    { key: "pick_pre", label: "Your pick's price before the start", type: "num", at: 0, pct: true, dyn: true },
    { key: "elapsed", label: "Minutes into the game when you bet", type: "num", at: 1, dyn: true },
    { key: "pick_chg", label: "Your pick's price change since the start", type: "num", at: 1, pct: true, dyn: true },
    { key: "chg10", label: "Your pick's price change in the last 10 minutes", type: "num", at: 1, pct: true, dyn: true },
    { key: "pick_high", label: "Your pick's highest price so far", type: "num", at: 1, pct: true, dyn: true },
    { key: "pick_low", label: "Your pick's lowest price so far", type: "num", at: 1, pct: true, dyn: true },
    { key: "off_high", label: "How far your pick is below its high", type: "num", at: 1, pct: true, dyn: true },
    { key: "off_low", label: "How far your pick is above its low", type: "num", at: 1, pct: true, dyn: true },
    { key: "fav_now", label: "Pre-game favorite's price when you bet", type: "num", at: 1, pct: true, dyn: true },
    { key: "flips_sofar", label: "Lead changes on price so far", type: "num", at: 1, dyn: true },
    { key: "best_after", label: "Best price gain after you bet", type: "num", at: 9, pct: true, dyn: true },
    { key: "worst_after", label: "Worst price drop after you bet", type: "num", at: 9, pct: true, dyn: true },
    { key: "mins", label: "Game length (minutes)", type: "num", at: 9 },
    { key: "flips", label: "Lead changes on price, whole game", type: "num", at: 9 },
    { key: "fav_low", label: "Favorite's lowest price in the game", type: "num", at: 9, pct: true },
    { key: "dog_high", label: "Underdog's highest price in the game", type: "num", at: 9, pct: true },
    { key: "vol", label: "Contracts traded, whole game", type: "num", at: 9 },
    { key: "was_draw", label: "Ended in a draw", type: "bool", at: 9 },
  ];

  window.DATASETS.paths = {
    label: "All sports · price paths", unit: "games", cols, bet, moments: MOMENTS, defaultX: "fav_pre",
    get rows() { return this.leagues.filter((l) => this.on[l] && loaded[l]).flatMap((l) => loaded[l]); },
    sidesFor: (m) => { const mo = MOMENTS.find((x) => x.id === m); return mo.trig ? SIDES_TRIG : mo.id === "t" ? SIDES_T : SIDES_FIXED; },
    sides: SIDES_FIXED, exits: true,
    leagues: Object.keys(IDX.leagues), meta: IDX.leagues, on: { nfl: true }, ensure(done) { return ensure(this.leagues.filter((l) => this.on[l]), done); },
    note: "Prices only: a team's price falling is the market's read of the score. Bets fill at the ask 1–2 minutes after the rule is first seen.",
  };
  window.PRESETS.push(
    { ds: "paths", label: "Any sport: bet every pre-game favorite", moment: "pre", side: "fav", filters: [] },
    { ds: "paths", label: "Buy the favorite when it falls to 30¢", moment: "below", side: "trig", params: { w: "fav", x: 30 }, filters: [] },
    { ds: "paths", label: "Buy the leader once anyone reaches 90¢", moment: "above", side: "trig", params: { w: "either", x: 90 }, filters: [] },
    { ds: "paths", label: "Fade a 15¢ jump in 10 minutes", moment: "spike", side: "other", params: { w: "either", x: 15, m: 10 }, filters: [] },
    { ds: "paths", label: "Buy a 15¢ crash, sell on a 8¢ bounce", moment: "crash", side: "trig", params: { w: "fav", x: 15, m: 10 }, exit: { tp: 8 }, filters: [] },
    { ds: "paths", label: "Favorite that drifted up 3¢+ in the last hour", moment: "pre", side: "fav", filters: [{ key: "move_1h", min: 0.03 }] },
  );
})();
