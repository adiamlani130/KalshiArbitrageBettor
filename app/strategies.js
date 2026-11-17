// Strategies & hedging: six tests built on the stocks lab's data and helpers (window.SLAB) plus target markets.
(function () {
  const L = window.SLAB, T = window.TARGET_DATA; if (!L) return;
  const { D, S, N, esc, pct, pts, money, cls, mean, C, O, ret, dP, link, ranks, corr, sig, span, short, stats, lineChart, legend, tile, table, VIEWS } = L;
  Object.assign(S, { optU: "spx", optKind: "all", optGap: 10, optSel: "", mTk: "WBD", mOffer: 31, mBreak: 15, mGap: 5, mHedge: 100,
    bThr: 5, bK: 6, bHold: 3, bUni: "second", hWin: 60, rThr: 2, rHold: 3, rCost: 1, rScope: "one", nKind: "all" });
  L.setTabs([["opt", "Options vs Kalshi"], ["merger", "Merger spread"], ["basket", "Second-order basket"], ["hedge", "Hedge a stock"], ["reverse", "Stock first, then Kalshi"], ["prenews", "Bets before the news"]], "opt");
  S.after = () => { const p = document.getElementById("pairpanel"); if (p) p.hidden = S.tab === "opt" || S.tab === "prenews"; };

  const STAKE = 10, fee = (p, c) => Math.ceil(0.07 * c * p * (1 - p) * 100 - 1e-9) / 100;
  // $10 on a Kalshi contract bought at price p (0-1), settled or sold at q (0-1); fee on the way in, and on the way out if sold early
  const kpnl = (p, q, sold) => { const c = STAKE / p; return c * q - STAKE - fee(p, c) - (sold ? fee(q, c) : 0); };
  const sel = (k, opts) => `<select data-s="${k}">${opts.map(([v, l]) => `<option value="${esc(v)}"${String(S[k]) === String(v) ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  const num = (k, a = "") => `<input type="number" data-s="${k}" value="${esc(S[k])}" ${a}>`;
  const field = (l, h) => `<label class="field"><span>${l}</span>${h}</label>`;
  const verdict = (st, unit = "per trade") => st.lo > 0 ? `<span class="pill good"><i>Likely a real edge</i> even the low end of the likely range is positive</span>`
    : st.hi < 0 ? `<span class="pill bad"><i>Reliably loses</i> even the high end of the likely range is negative</span>`
    : `<span class="pill warn"><i>Could be luck</i> the likely range ${unit} runs from ${pct(st.lo, 1)} to ${pct(st.hi, 1)}</span>`;
  const byDay = (T2, key = "e") => { const by = {}; T2.forEach((t) => (by[t[key]] = by[t[key]] || []).push(t.r)); return stats(Object.keys(by).sort((a, b) => a - b).map((k) => mean(by[k]))); };
  const curve = (rs, labels, f = money) => { let c = 0; return lineChart([{ pts: [[0, 0]].concat(rs.map((r, k) => [k + 1, (c += r)])), color: c >= 0 ? "var(--good)" : "var(--bad)" }], ["start"].concat(labels), { zero: true, fmtL: f, label: "Running profit" }); };

  // ---------------------------------------------------------------- 1. options-implied probability vs Kalshi
  const cdf = (x) => { const t = 1 / (1 + 0.2316419 * Math.abs(x)), d = 0.3989423 * Math.exp(-x * x / 2);
    const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return x > 0 ? 1 - p : p; };
  const days = (a, b) => (Date.parse(b) - Date.parse(a)) / 864e5;
  // Chance the target is met, from today's price, the options market's volatility and time left (lognormal, no skew)
  function model(t, i) {
    const u = T.under[t.u], s = u.c[i], v = u.v[i]; if (s == null || v == null) return null;
    const yrs = days(D.dates[i], t.exp) / 365; if (yrs <= 0) return null;
    const sg = v / 100, sd = sg * Math.sqrt(yrs), nu = u.drift - sg * sg / 2;
    const above = (k) => cdf((Math.log(s / k) + nu * yrs) / sd);
    if (t.kind === "end") return (t.lo == null ? 1 : above(t.lo)) - (t.hi == null ? 0 : above(t.hi));
    if (t.kind === "max") { for (let j = t.s; j <= i; j++) if (u.h[j] >= t.lo) return 1; const m = Math.log(t.lo / s);
      return Math.min(1, cdf((-m + nu * yrs) / sd) + Math.exp(2 * nu * m / (sg * sg)) * cdf((-m - nu * yrs) / sd)); }
    for (let j = t.s; j <= i; j++) if (u.l[j] != null && u.l[j] <= t.hi) return 1; const m = Math.log(s / t.hi);
    return Math.min(1, cdf((-m - nu * yrs) / sd) + Math.exp(-2 * nu * m / (sg * sg)) * cdf((-m + nu * yrs) / sd));
  }
  const tname = (t) => `${T.under[t.u].label} ${t.kind === "max" ? "reaches" : t.kind === "min" ? "falls to" : "ends"} ${esc(t.title)} by ${t.exp}`;
  function viewOpt() {
    if (!T) return `<div class="empty">Run <code>python scripts/pull_targets.py</code> first.</div>`;
    const pool = T.targets.filter((t) => t.u === S.optU && (S.optKind === "all" || t.kind === S.optKind));
    const X = +S.optGap || 0, trades = []; let bk = 0, bm = 0, nb = 0;
    const live = [];
    for (const t of pool) {
      let done = false, last = null;
      for (let k = 0; k < t.p.length; k++) {
        const i = t.s + k, p = t.p[k]; if (p == null) continue; const m = model(t, i); if (m == null) continue;
        last = { i, p, m };
        if (m >= 0.999 || p < 3 || p > 97) continue;                    // already decided, or nothing left to trade
        if (t.result && k % 5 === 0) { const y = t.result === "yes" ? 1 : 0; bk += (p / 100 - y) ** 2; bm += (m - y) ** 2; nb++; }
        const gap = p - m * 100;
        if (!done && t.result && Math.abs(gap) >= X && days(D.dates[i], t.exp) > 7) {
          const yes = gap < 0, price = Math.min(0.99, (yes ? p : 100 - p) / 100 + 0.01), won = (t.result === "yes") === yes;
          trades.push({ t, i, e: t.u + t.exp + t.kind + (yes ? "y" : "n"), gap, yes, price, won, r: kpnl(price, won ? 1 : 0) / STAKE }); done = true;
        }
      }
      if (!t.result && last && last.p >= 3 && last.p <= 97 && last.m < 0.999) live.push(Object.assign({ t }, last));
    }
    const st = stats(trades.map((t) => t.r)), cl = trades.length ? byDay(trades) : null;
    const sold = trades.filter((t) => !t.yes), bought = trades.filter((t) => t.yes), avg = (a) => a.length ? pct(mean(a.map((t) => t.r)), 1) : "—";
    live.sort((a, b) => Math.abs(b.p - b.m * 100) - Math.abs(a.p - a.m * 100));
    const pick = pool.find((t) => t.id === S.optSel) || (trades[0] || {}).t || pool[0];
    let chart = "";
    if (pick) { const a = [], b = []; pick.p.forEach((p, k) => { if (p == null) return; const m = model(pick, pick.s + k); a.push([pick.s + k, p]); if (m != null) b.push([pick.s + k, m * 100]); });
      chart = `<div><h3 style="margin-bottom:8px">One market: ${tname(pick)} ${pick.result ? `(settled ${pick.result.toUpperCase()})` : "(open)"}</h3>
        ${field("Market", sel("optSel", pool.map((t) => [t.id, `${t.kind === "max" ? "Reaches" : t.kind === "min" ? "Falls to" : "Ends"} ${t.title} by ${t.exp}`])))}
        ${legend([["var(--accent)", "Kalshi price (%)"], ["var(--ink)", "Options-implied chance (%)"]])}${lineChart([{ pts: a, color: "var(--accent)" }, { pts: b, color: "var(--ink)", w: 1.5 }], D.dates, { fmtL: (v) => v + "%", label: "Kalshi versus options-implied" })}</div>`; }
    return `<div style="display:grid;gap:16px"><div class="controls">${field("Underlying", sel("optU", Object.entries(T.under).map(([k, u]) => [k, u.label])))}
        ${field("Target type", sel("optKind", [["all", "All"], ["end", "Price at expiry"], ["max", "High reached"], ["min", "Low reached"]]))}${field("Trade when the gap is at least (pts)", num("optGap", 'min="1" max="60"'))}</div>
      <p class="headline">Each Kalshi target is a binary option, so it can be priced from ${esc(T.under[S.optU].label)}'s price and its options volatility (${esc(T.under[S.optU].vol_from)}). ${st ? `Betting against Kalshi whenever the two disagreed by ${X}+ points (${st.n} markets, held to settlement) returned <b class="${cls(st.m)}">${pct(st.m, 1)}</b> per $10 bet after fees.` : "No settled market had a gap that large."}
        ${nb ? ` On settled markets Kalshi's error score was <b>${(bk / nb).toFixed(3)}</b> and the options model's <b>${(bm / nb).toFixed(3)}</b> (lower is better): ${bk < bm ? "Kalshi was the better forecaster, so the gap is mostly the model's mistake" : "the options model was the better forecaster"}.` : ""}</p>
      ${st ? `<div class="tiles">${tile("Markets traded", st.n)}${tile("Won", (st.win * 100).toFixed(0) + "%")}${tile("Sold Kalshi (it was higher)", `${sold.length} · ${avg(sold)}`)}${tile("Bought Kalshi (it was lower)", `${bought.length} · ${avg(bought)}`)}${tile("Return", pct(st.m, 1), cls(st.m))}${tile("Separate bets", cl.n)}</div>
      <div class="pills">${verdict(cl, "per separate bet")}<span class="pill"><i>${cl.n} separate bets</i> strikes on the same underlying and expiry win or lose together, so they are judged as one</span></div>` : ""}
      ${chart}
      <div><h3 style="margin-bottom:8px">Open right now: biggest disagreements</h3>${table([["Market"], ["Kalshi", "n"], ["Options-implied", "n"], ["Gap", "n"], ["The trade"]],
        live.slice(0, 15).map((x) => `<tr><td class="wrap">${tname(x.t)}</td><td class="n">${x.p.toFixed(0)}%</td><td class="n">${(x.m * 100).toFixed(0)}%</td><td class="n ${cls(x.p - x.m * 100)}">${pts(x.p - x.m * 100, 0)}</td><td class="wrap">${x.p > x.m * 100 ? "Buy No on Kalshi, buy the matching call spread" : "Buy Yes on Kalshi, sell the matching call spread"}</td></tr>`), 380)}</div>
      ${st ? table([["Entered"], ["Market"], ["Kalshi", "n"], ["Options", "n"], ["Bet"], ["Paid", "n"], ["Result", "n"]],
        [...trades].sort((a, b) => b.i - a.i).slice(0, 80).map((x) => `<tr><td>${D.dates[x.i]}</td><td class="wrap">${tname(x.t)}</td><td class="n">${(x.gap + model(x.t, x.i) * 100).toFixed(0)}%</td><td class="n">${(model(x.t, x.i) * 100).toFixed(0)}%</td><td>${x.yes ? "Yes" : "No"}</td><td class="n">${Math.round(x.price * 100)}¢</td><td class="n ${cls(x.r)}">${pct(x.r, 0)}</td></tr>`)) : ""}
      <p class="hint">This tests the Kalshi leg alone. The full arbitrage also takes the opposite side with a tight call spread; that leg is fairly priced by definition, so on average it adds nothing and removes the swings. The model uses one volatility number for every strike, so it underprices crash targets that real options price higher.</p></div>`;
  }

  // ---------------------------------------------------------------- 2. merger spread vs Kalshi
  function viewMerger() {
    const s = sig(), tk = S.tk, c = C(tk), [a, b] = span(s), offer = +S.mOffer, brk = +S.mBreak;
    if (!(offer > brk)) return `<div class="empty">The offer price must be above the price if the deal breaks.</div>`;
    const ctl = `<div class="controls">${field("Offer price per share ($)", num("mOffer", 'step="0.25"'))}${field("Price if the deal breaks ($)", num("mBreak", 'step="0.25"'))}
      ${field("Trade when Kalshi is above the stock by (pts)", num("mGap", 'min="0" max="60"'))}${field("Hedge with Kalshi “No” (% of the break loss)", num("mHedge", 'min="0" max="200" step="25"'))}</div>`;
    const rows = []; for (let i = a; i <= b; i++) if (s.p[i] != null && c[i] != null) rows.push({ i, p: s.p[i], q: Math.max(0, Math.min(1, (c[i] - brk) / (offer - brk))) * 100, px: c[i] });
    if (rows.length < 10) return ctl + `<div class="empty">Too few days where both ${esc(tk)} and this Kalshi market traded. In the Pair panel choose the theme <b>Mergers &amp; takeovers</b>, the takeover market, and the target's stock (for example Paramount's takeover of Warner Brothers with WBD).</div>`;
    // buy $10,000 of stock when Kalshi is more confident than the spread; hedge with No contracts sized to the loss if the deal breaks
    const X = +S.mGap, H = +S.mHedge / 100, eq = [], un = []; let pos = null, cash = 0, cashU = 0, n = 0;
    for (const r of rows) {
      if (!pos && r.p - r.q >= X && r.p < 97) { const sh = 10000 / r.px; pos = { sh, n: H * sh * (r.px - brk), e: r, }; n++; cash -= pos.n * 0.0007 * 100 * (r.p / 100) * (1 - r.p / 100); }
      if (pos) { const stock = pos.sh * (r.px - pos.e.px), no = pos.n * ((100 - r.p) - (100 - pos.e.p)) / 100;
        eq.push([r.i, cash + stock + no]); un.push([r.i, cashU + stock]);
        if (r.p - r.q <= 0 || r === rows[rows.length - 1]) { cash += stock + no; cashU += stock; pos = null; } }
      else { eq.push([r.i, cash]); un.push([r.i, cashU]); }
    }
    const gap = rows.map((r) => r.p - r.q), dd = (e) => { let pk = 0, w = 0; e.forEach(([, v]) => { pk = Math.max(pk, v); w = Math.min(w, v - pk); }); return w; };
    const end = eq.length ? eq[eq.length - 1][1] : 0, endU = un.length ? un[un.length - 1][1] : 0, first = rows[0];
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">At $${first.px.toFixed(2)} against a $${offer} offer and a $${brk} break price, ${esc(tk)} was pricing a <b>${first.q.toFixed(0)}%</b> chance the deal closes on ${D.dates[first.i]}; Kalshi said <b>${first.p.toFixed(0)}%</b>. Over ${rows.length} days Kalshi was on average <b class="${cls(mean(gap))}">${pts(mean(gap), 1)} points</b> ${mean(gap) >= 0 ? "more" : "less"} confident than the stock. Buying the stock when Kalshi led by ${X}+ points${H ? ` and hedging with “No” contracts` : ""} made <b class="${cls(end)}">${money(end)}</b> on $10,000 (${n} trade${n === 1 ? "" : "s"}); unhedged it made ${money(endU)}.</p>
      <div class="tiles">${tile("Days", rows.length)}${tile("Average gap", pts(mean(gap), 1) + " pts")}${tile("Hedged result", money(end), cls(end))}${tile("Unhedged result", money(endU), cls(endU))}${tile("Worst dip, hedged", money(dd(eq)))}${tile("Worst dip, unhedged", money(dd(un)))}</div>
      <div><h3 style="margin-bottom:8px">Chance the deal closes: Kalshi vs the stock's spread</h3>${legend([["var(--accent)", "Kalshi (%)"], ["var(--ink)", `Implied by ${tk}'s price (%)`]])}
        ${lineChart([{ pts: rows.map((r) => [r.i, r.p]), color: "var(--accent)" }, { pts: rows.map((r) => [r.i, r.q]), color: "var(--ink)", w: 1.5 }], D.dates, { fmtL: (v) => v + "%", label: "Deal odds from Kalshi and from the stock" })}</div>
      <div><h3 style="margin-bottom:8px">Profit on $10,000 of stock</h3>${legend([["var(--good)", "With the Kalshi hedge"], ["var(--market)", "Stock only"]])}
        ${lineChart([{ pts: eq, color: "var(--good)" }, { pts: un, color: "var(--market)", dash: true }], D.dates, { zero: true, fmtL: money, label: "Hedged and unhedged profit" })}</div>
      <p class="hint">The stock-implied chance is (price − break price) ÷ (offer − break price). It ignores the time value of waiting for the money, so the stock always looks a little less confident than it is. The offer and break prices are yours to set: they are assumptions, and the answer moves with them. One deal is a case study, not a backtest. The “No” hedge is sized so that, if the deal broke, its payout would cover that share of the stock's fall.</p></div>`;
  }

  // ---------------------------------------------------------------- 3. second-order basket
  function basketTrades(s) {
    const linked = new Set(D.themes[s.theme].tickers), uni = (D.core || Object.keys(D.px)).filter((t) => t !== "SPY" && (S.bUni === "all" || !linked.has(t)));
    const [a, b] = span(s), out = []; let free = 0;
    for (let i = a + 31; i < Math.min(b, N - 2); i++) {
      const mv = dP(s, i); if (mv == null || Math.abs(mv) < S.bThr || i < free) continue;
      const cand = [];
      for (const tk of uni) { const x = [], y = [];
        for (let j = a + 1; j < i; j++) { const d = dP(s, j), r = ret(tk, j); if (d != null && r != null) { x.push(d); y.push(r); } }   // days before today only
        const c = x.length >= 30 ? link(x, y) : null; if (c && Math.abs(c.t) >= 2) cand.push({ tk, c }); }
      cand.sort((p, q) => Math.abs(q.c.t) - Math.abs(p.c.t));
      const legs = cand.slice(0, Math.max(1, S.bK | 0)), x = Math.min(N - 1, i + Math.max(1, S.bHold | 0)); if (legs.length < 2) continue;
      const rs = legs.map((l) => { const o = O(l.tk)[i + 1], e = C(l.tk)[x]; if (o == null || e == null) return null; const want = Math.sign(l.c.r) * Math.sign(mv);
        let r = want * (e / o - 1); if (+S.hedge) r -= want * (C("SPY")[x] / O("SPY")[i + 1] - 1); return { tk: l.tk, want, r: r - 0.001 }; }).filter(Boolean);
      if (rs.length < 2) continue;
      out.push({ i, e: i + 1, x, mv, legs: rs, r: mean(rs.map((l) => l.r)) }); free = x + 1;
    }
    return out;
  }
  function viewBasket() {
    const s = sig(), Tr = basketTrades(s), st = stats(Tr.map((t) => t.r));
    const ctl = `<div class="controls">${field("Kalshi moves at least (pts in a day)", num("bThr", 'min="1" max="60" step="0.5"'))}${field("Stocks in the basket", num("bK", 'min="2" max="20"'))}${field("Hold (trading days)", num("bHold", 'min="1" max="20"'))}
      ${field("Choose stocks from", sel("bUni", [["second", "Only stocks NOT listed for this theme"], ["all", "Every stock"]]))}</div>`;
    // which unlisted stocks have tracked this market so far (uses the whole history, so it describes, it doesn't prove)
    const linked = new Set(D.themes[s.theme].tickers), dep = [];
    for (const tk of D.core || []) { if (linked.has(tk)) continue; const [x, y] = L.lagPairs(s, tk, 0), c = x.length >= 40 ? link(x, y) : null; if (c) dep.push({ tk, c }); }
    dep.sort((p, q) => Math.abs(q.c.t) - Math.abs(p.c.t));
    const depT = `<div><h3 style="margin-bottom:8px">Hidden dependencies: unlisted stocks that moved with this market</h3>${table([["Stock"], ["Same-day link", "n"], ["Per +10 pts", "n"], ["Days", "n"], ["Strength (t)", "n"]],
      dep.slice(0, 12).map((p) => `<tr><td>${p.tk}</td><td class="n ${cls(p.c.r)}">${p.c.r.toFixed(2)}</td><td class="n ${cls(p.c.slope)}">${pct(p.c.slope * 10, 2)}</td><td class="n">${p.c.n}</td><td class="n">${p.c.t.toFixed(1)}</td></tr>`), 300)}
      <p class="hint">None of these is on the theme's obvious list. This table uses the whole history; the backtest above only ever uses days before each trade.</p></div>`;
    if (!st) return ctl + `<div class="empty">No basket trades. The rule needs 30 earlier days and at least two unlisted stocks with a clear link; try a smaller Kalshi move or a longer-lived market.</div>` + depT;
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">When this market moved ${S.bThr}+ points, the script found the ${S.bK} ${S.bUni === "second" ? "stocks outside the obvious list" : "stocks"} that had tracked it most closely so far, and bought or shorted each at the next open. Over <b>${st.n}</b> baskets it averaged <b class="${cls(st.m)}">${pct(st.m, 2)}</b> per basket after costs.</p>
      <div class="tiles">${tile("Baskets", st.n)}${tile("Made money", (st.win * 100).toFixed(0) + "%")}${tile("Average", pct(st.m, 2), cls(st.m))}${tile("Total on $10k each", money(st.total * 10000), cls(st.total))}${tile("t-stat", st.t.toFixed(1))}${tile("Halves", `${pct(st.r1, 1)} / ${pct(st.r2, 1)}`)}</div>
      <div class="pills">${verdict(st, "per basket")}</div>
      <div><h3 style="margin-bottom:8px">Running profit, $10,000 per basket</h3>${curve(Tr.map((t) => t.r * 10000), Tr.map((t) => D.dates[t.e]))}</div>
      ${table([["Signal day"], ["Kalshi move", "n"], ["Basket (bought +, shorted −)"], ["Out"], ["Result", "n"]],
        [...Tr].reverse().map((t) => `<tr><td>${D.dates[t.i]}</td><td class="n ${cls(t.mv)}">${pts(t.mv)} pts</td><td class="wrap">${t.legs.map((l) => (l.want > 0 ? "+" : "−") + l.tk).join(" ")}</td><td>${D.dates[t.x]}</td><td class="n ${cls(t.r)}">${pct(t.r, 2)}</td></tr>`))}
      ${depT}</div>`;
  }

  // ---------------------------------------------------------------- 4. hedge a stock with a Kalshi contract
  // Daily: hedged return = stock return − beta × Kalshi change, with beta fitted on the previous `win` days only.
  function hedgeRun(s, tk, win) {
    const [a, b] = span(s), xs = [], out = [];
    for (let i = a + 1; i <= b; i++) {
      const d = dP(s, i), r = ret(tk, i, 1, 0); if (d == null || r == null) continue;
      if (xs.length >= Math.min(win, 30)) { const w = xs.slice(-win), c = corr(w.map((v) => v[0]), w.map((v) => v[1])); const beta = c ? c.slope : 0; out.push({ i, d, r, beta, h: r - beta * d }); }
      xs.push([d, r]);
    }
    return out;
  }
  const sd = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((x) => (x - m) ** 2))); };
  let HSCAN = null, HKEY = "";
  function viewHedge() {
    const s = sig(), tk = S.tk, win = Math.max(20, S.hWin | 0), R = hedgeRun(s, tk, win);
    const ctl = `<div class="controls">${field("Learn the hedge size from the last (days)", num("hWin", 'min="20" max="250" step="10"'))}</div>`;
    const key = tk + win;
    if (key !== HKEY) { HKEY = key; HSCAN = D.signals.map((x, si) => { const r = hedgeRun(x, tk, win); if (r.length < 40) return null; const u = sd(r.map((v) => v.r)), h = sd(r.map((v) => v.h)); return { si, n: r.length, cut: 1 - (h * h) / (u * u) }; }).filter(Boolean).sort((p, q) => q.cut - p.cut); }
    const best = `<div><h3 style="margin-bottom:8px">Best Kalshi hedges for ${esc(tk)}</h3>${table([["Kalshi market"], ["Days tested", "n"], ["Swings removed", "n"]],
      HSCAN.slice(0, 15).map((p, k) => `<tr class="click" data-hsel="${p.si}"><td class="wrap">${esc(short(D.signals[p.si].title, 80))}</td><td class="n">${p.n}</td><td class="n ${cls(p.cut)}">${pct(p.cut, 0)}</td></tr>`), 380)}
      <p class="hint">Every Kalshi market tried as a hedge for ${esc(tk)}, ranked by how much of the stock's day-to-day variance it would have removed. Each day's hedge size uses earlier days only. Click a row to load it.</p></div>`;
    if (R.length < 20) return ctl + `<div class="empty">Too few overlapping days to test this market as a hedge for ${esc(tk)}.</div>` + best;
    const u = sd(R.map((v) => v.r)), h = sd(R.map((v) => v.h)), cut = 1 - (h * h) / (u * u), last = R[R.length - 1];
    const big = [...R].sort((p, q) => Math.abs(q.d) - Math.abs(p.d)).slice(0, 10), contracts = Math.abs(last.beta) * 10000 * 100;
    let cu = 0, ch = 0; const lu = R.map((v) => [v.i, (cu += v.r) * 100]), lh = R.map((v) => [v.i, (ch += v.h) * 100]);
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">Holding ${esc(tk)} and hedging it each day with this Kalshi market would have ${cut > 0 ? "removed" : "added"} <b class="${cls(cut)}">${Math.abs(cut * 100).toFixed(0)}%</b> of the stock's day-to-day swings over ${R.length} days. ${cut > 0.05 ? `Today the hedge for $10,000 of ${esc(tk)} is about <b>${Math.round(contracts).toLocaleString()} “${last.beta > 0 ? "No" : "Yes"}” contracts</b>.` : "That is too little to be worth the fees: this market is not a useful hedge for this stock."}</p>
      <div class="tiles">${tile("Days", R.length)}${tile("Daily swing, stock", pct(u, 2))}${tile("Daily swing, hedged", pct(h, 2))}${tile("Swings removed", pct(cut, 0), cls(cut))}${tile("Worst day, stock", pct(Math.min(...R.map((v) => v.r)), 1))}${tile("Worst day, hedged", pct(Math.min(...R.map((v) => v.h)), 1))}</div>
      <div><h3 style="margin-bottom:8px">Stock alone vs stock plus hedge (cumulative %)</h3>${legend([["var(--market)", `${tk} alone`], ["var(--accent)", "With the Kalshi hedge"]])}
        ${lineChart([{ pts: lu, color: "var(--market)" }, { pts: lh, color: "var(--accent)" }], D.dates, { zero: true, fmtL: (v) => v.toFixed(0) + "%", label: "Hedged versus unhedged" })}</div>
      <div><h3 style="margin-bottom:8px">Kalshi's 10 biggest days: did the hedge help?</h3>${table([["Date"], ["Kalshi move", "n"], [`${esc(tk)}`, "n"], ["Hedged", "n"], ["Helped?"]],
        big.map((v) => `<tr><td>${D.dates[v.i]}</td><td class="n ${cls(v.d)}">${pts(v.d)} pts</td><td class="n ${cls(v.r)}">${pct(v.r, 2)}</td><td class="n ${cls(v.h)}">${pct(v.h, 2)}</td><td>${Math.abs(v.h) < Math.abs(v.r) ? '<span class="pos">Yes</span>' : '<span class="neg">No</span>'}</td></tr>`))}</div>
      ${best}
      <p class="hint">If the stock tends to rise when the probability rises, the hedge is “No” contracts, which gain when the probability falls. Rebalancing costs (Kalshi's fee and the bid/ask spread) are not included, and a contract stops hedging once it settles.</p></div>`;
  }

  // ---------------------------------------------------------------- 5. the stock moves first: trade the Kalshi contract
  function revTrades(s, tk) {
    const out = [], H = Math.max(1, S.rHold | 0), cost = (+S.rCost || 0) / 100; let free = 0, seen = 0, agree = 0;
    for (let i = 1; i < N - 1; i++) {
      const r = ret(tk, i), p = s.p[i];
      if (r != null && p != null && Math.abs(r) * 100 >= S.rThr && i >= free && seen >= 20 && agree && p >= 5 && p <= 95) {
        let x = Math.min(N - 1, i + H); while (x > i && s.p[x] == null) x--;
        if (x > i) { const yes = Math.sign(agree) * Math.sign(r) > 0, pe = Math.min(0.99, (yes ? p : 100 - p) / 100 + cost), q = Math.max(0.01, (yes ? s.p[x] : 100 - s.p[x]) / 100 - cost);
          out.push({ i, e: i, x, tk, sig: s, mv: r, yes, pe, q, r: kpnl(pe, q, true) / STAKE }); free = x + 1; }
      }
      const d1 = dP(s, i + 1), r0 = r; if (d1 != null && r0 != null && d1 && r0) { seen++; agree += Math.sign(d1) * Math.sign(r0); }   // did Kalshi follow the stock a day later?
    }
    return out;
  }
  function viewReverse() {
    const sigs = S.rScope === "one" ? [sig()] : D.signals.filter((x) => x.theme === S.theme), tks = S.rScope === "all" ? D.themes[S.theme].tickers : [S.tk];
    const Tr = sigs.flatMap((s) => tks.flatMap((t) => revTrades(s, t))).sort((a, b) => a.e - b.e), st = stats(Tr.map((t) => t.r));
    const ctl = `<div class="controls">${field("Stock moves at least (% in a day)", num("rThr", 'min="0.5" max="20" step="0.5"'))}${field("Hold the contract (trading days)", num("rHold", 'min="1" max="20"'))}${field("Spread cost each way (¢)", num("rCost", 'min="0" max="5" step="0.5"'))}
      ${field("Apply to", sel("rScope", [["one", "This market, this stock"], ["sigs", "All markets in theme, this stock"], ["all", "All markets in theme, all linked stocks"]]))}</div>`;
    if (!st) return ctl + `<div class="empty">No trades. The rule needs 20 earlier days to learn which way Kalshi follows the stock; try a smaller stock move or apply it to the whole theme.</div>`;
    const cl = S.rScope === "one" ? st : byDay(Tr);
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">The stocks page found stocks leading Kalshi more often than the reverse. This trades that: when ${S.rScope === "all" ? "a linked stock" : esc(S.tk)} moves ${S.rThr}%+ in a day, buy the Kalshi “Yes” or “No” at 4pm in the direction Kalshi has tended to follow, and sell ${S.rHold} day${S.rHold > 1 ? "s" : ""} later. <b>${st.n}</b> trades averaged <b class="${cls(st.m)}">${pct(st.m, 1)}</b> per $10 after Kalshi's fee both ways and a ${S.rCost}¢ spread.</p>
      <div class="tiles">${tile("Trades", st.n)}${tile("Made money", (st.win * 100).toFixed(0) + "%")}${tile("Average", pct(st.m, 1), cls(st.m))}${tile("Total on $10 each", money(st.total * STAKE), cls(st.total))}${tile("t-stat", cl.t.toFixed(1))}${tile("Halves", `${pct(cl.r1, 1)} / ${pct(cl.r2, 1)}`)}</div>
      <div class="pills">${verdict(cl)}</div>
      <div><h3 style="margin-bottom:8px">Running profit, $10 per trade</h3>${curve(Tr.map((t) => t.r * STAKE), Tr.map((t) => D.dates[t.e]))}</div>
      ${table([["Day"], ["Market"], ["Stock"], ["Stock move", "n"], ["Bought"], ["Paid", "n"], ["Sold", "n"], ["Result", "n"]],
        [...Tr].reverse().slice(0, 80).map((t) => `<tr><td>${D.dates[t.i]}</td><td class="wrap">${esc(short(t.sig.title, 50))}</td><td>${t.tk}</td><td class="n ${cls(t.mv)}">${pct(t.mv, 1)}</td><td>${t.yes ? "Yes" : "No"}</td><td class="n">${Math.round(t.pe * 100)}¢</td><td class="n">${Math.round(t.q * 100)}¢</td><td class="n ${cls(t.r)}">${pct(t.r, 0)}</td></tr>`))}
      <p class="hint">Kalshi's price is read at 4:00pm New York time, the same moment the stock's daily move is known, so this assumes you can trade the contract within minutes of the close.</p></div>`;
  }

  // ---------------------------------------------------------------- 6. bets before the news
  function viewPrenews() {
    if (!T) return `<div class="empty">Run <code>python scripts/pull_targets.py</code> first.</div>`;
    const kinds = [...new Set(T.ladder.map((r) => r[0]))], rows = T.ladder.filter((r) => S.nKind === "all" || r[0] === S.nKind);
    const B = [[0, 10], [10, 25], [25, 50], [50, 75], [75, 90], [90, 100]].map(([a, b]) => { const x = rows.filter((r) => r[2] >= a && r[2] < b); if (!x.length) return null;
      const yes = x.map((r) => kpnl(Math.min(0.99, r[2] / 100 + 0.01), r[3]) / STAKE), no = x.map((r) => kpnl(Math.min(0.99, 1 - r[2] / 100 + 0.01), 1 - r[3]) / STAKE);
      return { a, b, n: x.length, won: mean(x.map((r) => r[3])), imp: mean(x.map((r) => r[2])) / 100, yes: stats(yes), no: stats(no) }; }).filter(Boolean);
    const fav = rows.filter((r) => r[2] >= 75), favR = fav.length ? stats(fav.map((r) => kpnl(Math.min(0.99, r[2] / 100 + 0.01), r[3]) / STAKE)) : null;
    const lon = rows.filter((r) => r[2] < 25), lonR = lon.length ? stats(lon.map((r) => kpnl(r[2] / 100 + 0.01, r[3]) / STAKE)) : null;
    return `<div style="display:grid;gap:16px"><div class="controls">${field("Announcement", sel("nKind", [["all", "All announcements"]].concat(kinds.map((k) => [k, k]))))}</div>
      <p class="headline">${rows.length} Kalshi markets on macro numbers, priced the evening before the release. ${favR ? `Buying every outcome priced 75¢ or more returned <b class="${cls(favR.m)}">${pct(favR.m, 1)}</b> (${favR.n} bets).` : ""} ${lonR ? `Buying every long shot under 25¢ returned <b class="${cls(lonR.m)}">${pct(lonR.m, 1)}</b> (${lonR.n} bets).` : ""}</p>
      ${table([["Kalshi price the evening before"], ["Markets", "n"], ["Came true", "n"], ["Price implied", "n"], ["Gap", "n"], ["Buy Yes", "n"], ["Buy No", "n"]],
        B.map((g) => `<tr><td>${g.a}–${g.b}¢</td><td class="n">${g.n}</td><td class="n">${(g.won * 100).toFixed(0)}%</td><td class="n">${(g.imp * 100).toFixed(0)}%</td><td class="n ${cls(g.won - g.imp)}">${pts((g.won - g.imp) * 100, 0)}</td><td class="n ${cls(g.yes.m)}">${pct(g.yes.m, 0)}</td><td class="n ${cls(g.no.m)}">${pct(g.no.m, 0)}</td></tr>`))}
      <p class="hint">Returns are per $10 bet at the evening price plus 1¢, held through the release, after Kalshi's fee. Thresholds within one release win or lose together, so the number of independent results is the number of releases (about ${new Set(rows.map((r) => r[0] + r[1])).size}), not the number of markets.</p></div>`;
  }

  Object.assign(VIEWS, { opt: viewOpt, merger: viewMerger, basket: viewBasket, hedge: viewHedge, reverse: viewReverse, prenews: viewPrenews });
  document.addEventListener("click", (e) => { const t = e.target.closest("[data-hsel]"); if (!t) return; const si = +t.dataset.hsel; S.sig = si; S.theme = D.signals[si].theme; L.render(); window.scrollTo({ top: 0 }); });
  if (new URLSearchParams(location.search).get("deal") !== "0") { const w = D.signals.findIndex((x) => x.id === "KXTAKEOVERACQWB-27JUN30-PSKY"); if (w >= 0 && D.px.WBD) { S.theme = "mergers"; S.sig = w; S.tk = "WBD"; } }
})();
