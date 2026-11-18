// Markets vs Stocks: line up Kalshi probabilities with stock prices and test who moves first.
(function () {
  const D = window.STOCK_DATA, $ = (id) => document.getElementById(id);
  if (!D) { $("view").innerHTML = `<div class="empty">No data yet. Run <code>python scripts/pull_stocks.py</code>.</div>`; return; }
  const N = D.dates.length, STAKE = 10000;
  let TABS = [["lead", "Who moves first"], ["trade", "Lag trade"], ["shock", "Hourly shocks"], ["news", "Announcements"], ["scan", "Strongest pairs"], ["paper", "Paper trade"]];
  const S = { tab: "lead", theme: "fed", sig: 0, tk: "TLT", hedge: 0, thr: 5, look: 1, dir: "auto", gap: "", entry: "open", hold: 3, cost: 0.05, scope: "one",
              shockMin: 8, shockTheme: "pair", kind: "Fed decision", drift: 3, earnTk: "all", scanBy: "lead", scanScope: "linked" };

  // ---------------------------------------------------------------- helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v, d = 1) => v == null || isNaN(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%";
  const pts = (v, d = 1) => v == null || isNaN(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
  const money = (v) => (v > 0 ? "+$" : v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const cls = (v) => (v >= 0 ? "pos" : "neg");
  const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
  const C = (tk) => D.px[tk].c, O = (tk) => D.px[tk].o;
  // stock return from close i-k to close i (minus SPY's when hedged)
  function ret(tk, i, k = 1, hedge = S.hedge) {
    const c = C(tk); if (i - k < 0 || i >= N || c[i] == null || c[i - k] == null) return null;
    let r = c[i] / c[i - k] - 1;
    if (+hedge && tk !== "SPY") { const s = C("SPY"); r -= s[i] / s[i - k] - 1; }
    return r;
  }
  const dP = (sig, i, k = 1) => (i - k < 0 || i >= N || sig.p[i] == null || sig.p[i - k] == null ? null : sig.p[i] - sig.p[i - k]);
  function corr(x, y) {
    const n = x.length; if (n < 8) return null;
    const mx = mean(x), my = mean(y); let sxy = 0, sxx = 0, syy = 0;
    for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
    if (!sxx || !syy) return null;
    const r = sxy / Math.sqrt(sxx * syy);
    return { r, n, t: r * Math.sqrt((n - 2) / Math.max(1e-9, 1 - r * r)), slope: sxy / sxx };
  }
  // Rank correlation, so one wild day (an election night, say) can't create a "link" by itself.
  // The slope is fitted after clipping both sides to their 5th-95th percentile range.
  function ranks(a) { const o = a.map((v, i) => [v, i]).sort((p, q) => p[0] - q[0]), r = new Array(a.length);
    for (let i = 0; i < o.length;) { let j = i; while (j + 1 < o.length && o[j + 1][0] === o[i][0]) j++; for (let k = i; k <= j; k++) r[o[k][1]] = (i + j) / 2; i = j + 1; } return r; }
  function clip(a) { const s = [...a].sort((p, q) => p - q), lo = s[Math.floor(s.length * 0.05)], hi = s[Math.ceil(s.length * 0.95) - 1]; return a.map((v) => Math.min(hi, Math.max(lo, v))); }
  function link(x, y) { const c = corr(ranks(x), ranks(y)); if (!c) return null; const w = corr(clip(x), clip(y)); c.slope = w ? w.slope : 0; return c; }
  // pairs (Kalshi change on day i, stock return on day i+lag); lag > 0 means Kalshi moved first
  function lagPairs(sig, tk, lag, hedge = S.hedge) {
    const x = [], y = [];
    for (let i = 1; i < N; i++) { const a = dP(sig, i), b = ret(tk, i + lag, 1, hedge); if (a != null && b != null) { x.push(a); y.push(b); } }
    return [x, y];
  }
  const sig = () => D.signals[S.sig];
  const span = (s) => { let a = s.p.findIndex((v) => v != null), b = N - 1; while (b > a && s.p[b] == null) b--; return [a, b]; };
  const short = (t, n = 70) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
  function stats(rs) {
    const n = rs.length; if (!n) return null;
    const m = mean(rs), sd = Math.sqrt(rs.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, n - 1)), se = sd / Math.sqrt(n), h = Math.floor(n / 2);
    return { n, m, win: rs.filter((x) => x > 0).length / n, t: se ? m / se : 0, lo: m - 1.96 * se, hi: m + 1.96 * se, total: m * n,
             r1: h ? mean(rs.slice(0, h)) : NaN, r2: mean(rs.slice(h)) };
  }

  // ---------------------------------------------------------------- charts (plain SVG)
  function ticks(a, b, n) { const s0 = (b - a) / n || 1, mag = 10 ** Math.floor(Math.log10(Math.abs(s0))), e = s0 / mag, st = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag, o = [];
    for (let t = Math.ceil(a / st) * st; t <= b + 1e-9; t += st) o.push(Math.abs(t) < 1e-9 ? 0 : +t.toFixed(6)); return o; }
  // lines: [{ pts: [[x, y]...], color, axis: "l"|"r", dash }]; x is an index into `labels`
  function lineChart(lines, labels, o = {}) {
    const W = 680, H = o.h || 240, L = 46, R = o.right ? 50 : 12, T = 12, B = 26;
    const rng = (ax) => { const v = lines.filter((l) => (l.axis || "l") === ax).flatMap((l) => l.pts.map((p) => p[1])); if (o.zero && ax === "l") v.push(0);
      if (!v.length) return null; let a = Math.min(...v), b = Math.max(...v); const pad = (b - a) * 0.08 || 1; return [a - pad, b + pad]; };
    const rl = rng("l"), rr = rng("r"), xs = lines.flatMap((l) => l.pts.map((p) => p[0])), x0 = Math.min(...xs), x1 = Math.max(...xs);
    const X = (x) => L + (W - L - R) * (x1 > x0 ? (x - x0) / (x1 - x0) : 0.5), Y = (v, r) => T + (H - T - B) * (1 - (v - r[0]) / (r[1] - r[0]));
    const fl = o.fmtL || ((v) => v), fr = o.fmtR || ((v) => v);
    let g = ticks(rl[0], rl[1], 4).map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t, rl)}" y2="${Y(t, rl)}" stroke="var(--line-2)"/><text x="${L - 6}" y="${Y(t, rl) + 4}" text-anchor="end">${fl(t)}</text>`).join("");
    if (rr) g += ticks(rr[0], rr[1], 4).map((t) => `<text x="${W - R + 6}" y="${Y(t, rr) + 4}">${fr(t)}</text>`).join("");
    if (o.zero) g += `<line x1="${L}" x2="${W - R}" y1="${Y(0, rl)}" y2="${Y(0, rl)}" stroke="var(--ink-3)"/>`;
    const paths = lines.map((l) => { const r = (l.axis || "l") === "l" ? rl : rr;
      return `<path d="${l.pts.map((p, k) => `${k ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1], r).toFixed(1)}`).join("")}" fill="none" stroke="${l.color}" stroke-width="${l.w || 2}" stroke-linejoin="round"${l.dash ? ' stroke-dasharray="4 3"' : ""}/>` +
        (l.dots ? l.pts.map((p) => `<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1], r).toFixed(1)}" r="3" fill="${l.color}"/>`).join("") : ""); }).join("");
    const lab = o.xticks ? o.xticks.map((i) => `<text x="${X(i)}" y="${H - 8}" text-anchor="middle">${esc(labels[i])}</text>`).join("")
      : `<text x="${L}" y="${H - 8}">${esc(labels[x0])}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(labels[x1])}</text>`;
    const mark = o.mark != null ? `<line x1="${X(o.mark)}" x2="${X(o.mark)}" y1="${T}" y2="${H - B}" stroke="var(--ink-3)" stroke-dasharray="3 3"/>` : "";
    return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || "chart")}">${g}${mark}${paths}${lab}</svg></div>`;
  }
  function barChart(bars, o = {}) {   // bars: [{ label, v, note, strong }]
    const W = 680, H = 220, L = 46, R = 12, T = 12, B = 40, n = bars.length, bw = (W - L - R) / n;
    const m = Math.max(o.band || 0, ...bars.map((b) => Math.abs(b.v))) * 1.15 || 1, Y = (v) => T + (H - T - B) * (1 - (v + m) / (2 * m));
    const grid = ticks(-m, m, 4).map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line-2)"/><text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${t.toFixed(2)}</text>`).join("");
    const band = o.band ? `<rect x="${L}" y="${Y(o.band)}" width="${W - L - R}" height="${Y(-o.band) - Y(o.band)}" fill="var(--market)" opacity=".13"/>` : "";
    const rects = bars.map((b, i) => { const x = L + i * bw + bw * 0.2, y = Math.min(Y(b.v), Y(0)), h = Math.abs(Y(b.v) - Y(0));
      return `<rect x="${x}" y="${y}" width="${bw * 0.6}" height="${Math.max(1, h)}" rx="3" fill="${b.strong ? "var(--accent)" : "var(--market)"}"><title>${esc(b.note || "")}</title></rect>
        <text x="${L + i * bw + bw / 2}" y="${H - 22}" text-anchor="middle">${esc(b.label)}</text>`; }).join("");
    return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || "bars")}">${grid}${band}<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--ink-3)"/>${rects}
      <text x="${L}" y="${H - 6}">${esc(o.left || "")}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${esc(o.right || "")}</text></svg></div>`;
  }
  function scatter(P, o = {}) {       // P: [{ x, y, tip }]
    const W = 680, H = 260, L = 50, R = 12, T = 12, B = 30;
    const xa = Math.max(...P.map((p) => Math.abs(p.x))) * 1.1 || 1, ya = Math.max(...P.map((p) => Math.abs(p.y))) * 1.1 || 1;
    const X = (v) => L + (W - L - R) * (v + xa) / (2 * xa), Y = (v) => T + (H - T - B) * (1 - (v + ya) / (2 * ya));
    const c = corr(P.map((p) => p.x), P.map((p) => p.y));
    const fit = c ? `<line x1="${X(-xa)}" x2="${X(xa)}" y1="${Y(-xa * c.slope)}" y2="${Y(xa * c.slope)}" stroke="var(--accent)" stroke-width="2" stroke-dasharray="5 4"/>` : "";
    return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || "scatter")}">
      ${ticks(-ya, ya, 4).map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line-2)"/><text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${(t * 100).toFixed(1)}%</text>`).join("")}
      <line x1="${X(0)}" x2="${X(0)}" y1="${T}" y2="${H - B}" stroke="var(--ink-3)"/><line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--ink-3)"/>${fit}
      ${P.map((p) => `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="4.5" fill="var(--accent)" opacity=".75"><title>${esc(p.tip)}</title></circle>`).join("")}
      <text x="${L}" y="${H - 8}">${esc(o.left || "")}</text><text x="${W - R}" y="${H - 8}" text-anchor="end">${esc(o.right || "")}</text></svg></div>`;
  }
  const legend = (items) => `<div class="legend">${items.map(([c, t]) => `<span><i class="sw" style="background:${c}"></i>${esc(t)}</span>`).join("")}</div>`;
  const tile = (k, v, c = "") => `<div class="tile"><span>${k}</span><b class="${c}">${v}</b></div>`;
  const table = (head, rows, max = 320) => `<div class="tablewrap" style="max-height:${max}px;overflow-y:auto"><table><thead><tr>${head.map((h) => `<th class="${h[1] || ""}">${h[0]}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${head.length}" class="empty">Nothing to show.</td></tr>`}</tbody></table></div>`;

  // ---------------------------------------------------------------- 1. who moves first
  function viewLead() {
    const s = sig(), tk = S.tk, [a, b] = span(s), c = C(tk);
    const base = c.slice(a, b + 1).find((v) => v != null);
    const lp = [], ls = [];
    for (let i = a; i <= b; i++) { if (s.p[i] != null) lp.push([i, s.p[i]]); if (c[i] != null) ls.push([i, c[i] / base * 100 - 100]); }
    const lags = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5].map((k) => { const [x, y] = lagPairs(s, tk, k); return { k, c: link(x, y) }; }).filter((l) => l.c);
    if (!lags.length) return `<div class="empty">Not enough overlapping days for ${esc(tk)} and this market.</div>`;
    const n = lags.find((l) => l.k === 0)?.c.n || lags[0].c.n, band = 1.96 / Math.sqrt(n);
    const same = lags.find((l) => l.k === 0), best = [...lags].sort((x, y) => Math.abs(y.c.t) - Math.abs(x.c.t))[0];
    const lead = lags.filter((l) => l.k > 0).sort((x, y) => Math.abs(y.c.t) - Math.abs(x.c.t))[0];
    const say = !same ? "" : Math.abs(same.c.t) < 2 ? `On the same day there is <b>no clear link</b> (rank correlation ${same.c.r.toFixed(2)}).`
      : `On the same day, a 10-point rise in the probability went with a <b class="${cls(same.c.slope)}">${pct(same.c.slope * 10, 2)}</b> move in ${esc(tk)} (correlation ${same.c.r.toFixed(2)}).`;
    const say2 = lead && Math.abs(lead.c.t) >= 2 ? ` Kalshi's move also lined up with ${esc(tk)}'s move <b>${lead.k} day${lead.k > 1 ? "s" : ""} later</b> (correlation ${lead.c.r.toFixed(2)}): a possible lag to trade.`
      : ` Kalshi's moves did <b>not</b> reliably show up in ${esc(tk)} on later days, so there is no obvious lag to trade.`;
    const big = []; for (let i = a + 1; i <= b; i++) { const d = dP(s, i); if (d != null) big.push([Math.abs(d), i, d]); }
    big.sort((x, y) => y[0] - x[0]);
    return `<div style="display:grid;gap:16px">
      <p class="headline">${say}${say2}</p>
      <div class="tiles">${tile("Days compared", n)}${tile("Same-day link", same ? same.c.r.toFixed(2) : "—")}${tile("Strongest lag", (best.k > 0 ? "+" : "") + best.k + "d")}
        ${tile("At that lag", best.c.r.toFixed(2))}${tile("Kalshi volume", (s.vol / 1e6).toFixed(1) + "M")}${tile("Settled", s.result ? s.result.toUpperCase() : "open")}</div>
      <div><h3 style="margin-bottom:8px">Probability and price</h3>${legend([["var(--accent)", "Kalshi probability (left, %)"], ["var(--ink)", `${tk} change since the market opened (right, %)`]])}
        ${lineChart([{ pts: lp, color: "var(--accent)" }, { pts: ls, color: "var(--ink)", axis: "r", w: 1.5 }], D.dates, { right: true, fmtL: (v) => v + "%", fmtR: (v) => (v > 0 ? "+" : "") + v + "%", label: "Kalshi probability and stock price" })}</div>
      <div><h3 style="margin-bottom:8px">Who moves first?</h3>
        ${barChart(lags.map((l) => ({ label: (l.k > 0 ? "+" : "") + l.k, v: l.c.r, strong: Math.abs(l.c.r) > band, note: `lag ${l.k}: correlation ${l.c.r.toFixed(3)}, ${l.c.n} days` })), { band, left: "← stock moved first (days)", right: "Kalshi moved first (days) →", label: "Correlation by lag" })}
        <p class="hint">Each bar is the link between Kalshi's daily change and ${esc(tk)}'s daily return that many days later (right) or earlier (left). Bars inside the grey band are what luck alone produces.</p></div>
      <div><h3 style="margin-bottom:8px">Kalshi's biggest days, and what ${esc(tk)} did</h3>
        ${table([["Date"], ["Kalshi move", "n"], ["Probability after", "n"], [`${esc(tk)} same day`, "n"], ["Next day", "n"], ["Next 3 days", "n"]],
          big.slice(0, 25).map(([, i, d]) => { const r0 = ret(tk, i), r1 = ret(tk, i + 1), r3 = ret(tk, i + 3, 3);
            return `<tr><td>${D.dates[i]}</td><td class="n ${cls(d)}">${pts(d)} pts</td><td class="n">${s.p[i].toFixed(0)}%</td><td class="n ${cls(r0)}">${pct(r0, 2)}</td><td class="n ${cls(r1)}">${pct(r1, 2)}</td><td class="n ${cls(r3)}">${pct(r3, 2)}</td></tr>`; }))}</div></div>`;
  }

  // ---------------------------------------------------------------- 2. lag trade
  function trades(s, tk) {
    const out = [], o = O(tk), c = C(tk), so = O("SPY"), sc = C("SPY"), k = Math.max(1, S.look | 0), H = Math.max(1, S.hold | 0);
    let free = 0, seen = 0, agree = 0;   // agree: days so far when Kalshi and the stock moved the same way, minus days they didn't
    for (let i = 1; i < N - 1; i++) {
      const d1 = dP(s, i), r1 = ret(tk, i, 1);
      const move = dP(s, i, k), sr = ret(tk, i, k);
      if (move != null && sr != null && Math.abs(move) >= S.thr && i >= free) {
        let sign = S.dir === "up" ? 1 : S.dir === "down" ? -1 : 0;
        if (!sign && seen >= 20) sign = Math.sign(agree);   // learned from earlier days only
        const want = sign * Math.sign(move);
        // The signal is read at 4pm on day i, so the first price you can trade is the next day's open (or later).
        const e = i + (S.entry === "open2" ? 2 : 1), x = Math.min(N - 1, e - 1 + H), pe = o[e];
        if (want && e < N && pe != null && c[x] != null && x >= e && !(S.gap !== "" && sr * want * 100 >= +S.gap)) {
          let r = want * (c[x] / pe - 1);
          if (+S.hedge && tk !== "SPY") r -= want * (sc[x] / so[e] - 1);
          r -= 2 * S.cost / 100;
          out.push({ i, e, x, tk, sig: s, move, want, pre: sr, r }); free = x + 1;
        }
      }
      if (d1 != null && r1 != null && d1 && r1) { seen++; agree += Math.sign(d1) * Math.sign(r1); }
    }
    return out;
  }
  function allTrades() {
    const sigs = S.scope === "sigs" || S.scope === "all" ? D.signals.filter((x) => x.theme === S.theme) : [sig()];
    const tks = S.scope === "stocks" || S.scope === "all" ? D.themes[S.theme].tickers : [S.tk];
    return sigs.flatMap((s) => tks.flatMap((t) => trades(s, t))).sort((a, b) => a.e - b.e);
  }
  function viewTrade() {
    const T = allTrades(), multi = S.scope !== "one";
    const st = stats(T.map((t) => t.r));
    if (st && multi) {   // many trades share a day, so judge luck on one average result per entry day
      const by = {}; T.forEach((t) => (by[t.e] = by[t.e] || []).push(t.r));
      const d = stats(Object.keys(by).sort((a, b) => a - b).map((k) => mean(by[k])));
      Object.assign(st, { t: d.t, lo: d.lo, hi: d.hi, r1: d.r1, r2: d.r2, days: d.n });
    }
    const rule = `Kalshi moves ${S.thr}+ pts in ${S.look} day${S.look > 1 ? "s" : ""}${S.gap !== "" ? `, stock has moved less than ${S.gap}% that way` : ""}; trade at ${S.entry === "open" ? "the next open" : "the open two days later"}, hold ${S.hold} day${S.hold > 1 ? "s" : ""}`;
    if (!st) return `<div class="empty">No trades for this rule (${esc(rule)}). Lower the Kalshi move, or apply it to more markets or stocks.${S.dir === "auto" ? " “Follow its past link” needs 20 earlier days before it will trade." : ""}</div>`;
    let cum = 0; const curve = T.map((t, k) => [k, (cum += t.r * STAKE)]);
    const luck = st.lo > 0 ? ["good", "Likely a real edge", "even the low end of the likely range is positive"] : st.hi < 0 ? ["bad", "Reliably loses", "even the high end of the likely range is negative"]
      : ["warn", "Could be luck", `the likely range per trade runs from ${pct(st.lo, 2)} to ${pct(st.hi, 2)}`];
    const halves = st.n < 12 ? ["", "Too few trades to split"] : st.r1 > 0 && st.r2 > 0 ? ["good", "Held up in both halves"] : st.r1 < 0 && st.r2 < 0 ? ["bad", "Lost in both halves"] : ["warn", "Only worked in one half"];
    return `<div style="display:grid;gap:16px">
      <p class="headline">Rule: ${esc(rule)}. Across <b>${st.n}</b> trades of $${STAKE.toLocaleString()} it would have ${st.total >= 0 ? "made" : "lost"} <b class="${cls(st.total)}">${money(st.total * STAKE).replace(/^[+−]/, "")}</b>, an average of <b class="${cls(st.m)}">${pct(st.m, 2)}</b> per trade after costs.</p>
      <div class="tiles">${tile("Trades", st.n)}${tile("Made money", (st.win * 100).toFixed(0) + "%")}${tile("Average", pct(st.m, 2), cls(st.m))}${tile("Total", money(st.total * STAKE), cls(st.total))}
        ${tile("t-stat", st.t.toFixed(1))}${tile("Halves", `${pct(st.r1, 1)} / ${pct(st.r2, 1)}`)}</div>
      <div class="pills"><span class="pill ${luck[0]}"><i>${luck[1]}</i> ${luck[2]}</span><span class="pill ${halves[0]}"><i>${halves[1]}</i></span>
        ${multi ? `<span class="pill"><i>${st.days} separate days</i> trades entered on the same day are judged as one, because stocks in a theme move together</span>` : ""}</div>
      <div><h3 style="margin-bottom:8px">Running profit, trade by trade</h3>${lineChart([{ pts: [[0, 0]].concat(curve.map(([k, v]) => [k + 1, v])), color: st.total >= 0 ? "var(--good)" : "var(--bad)" }],
        ["start"].concat(T.map((t) => D.dates[t.e])), { zero: true, fmtL: (v) => money(v), label: "Cumulative profit" })}</div>
      ${table([["Signal day"], ...(multi ? [["Market"], ["Stock"]] : []), ["Kalshi move", "n"], ["Stock so far", "n"], ["Trade"], ["In"], ["Out"], ["Result", "n"]],
        [...T].reverse().slice(0, 80).map((t) => `<tr><td>${D.dates[t.i]}</td>${multi ? `<td class="wrap">${esc(short(t.sig.title, 48))}</td><td>${t.tk}</td>` : ""}<td class="n ${cls(t.move)}">${pts(t.move)} pts</td><td class="n">${pct(t.pre, 2)}</td>
          <td>${t.want > 0 ? "Buy" : "Short"}</td><td>${D.dates[t.e]}</td><td>${D.dates[t.x]}</td><td class="n ${cls(t.r)}">${pct(t.r, 2)}</td></tr>`))}
      <p class="hint">Each trade is ${S.hedge ? "hedged with an opposite SPY position, " : ""}entered at ${S.entry === "open" ? "the next day's opening price" : "the opening price two days after the signal"}, with ${S.cost}% taken off each way. Positions in the same stock never overlap.</p></div>`;
  }

  // ---------------------------------------------------------------- 3. hourly shocks
  function viewShock() {
    const steps = ["−7h", "−3h", "jump", "first trade", "+1h", "+2h", "+4h", "+1 day", "+2 days", "+3 days"];
    const pool = D.shocks.filter((h) => Math.abs(h.p1 - h.p0) >= S.shockMin && (S.shockTheme === "all" || (S.shockTheme === "pair" ? h.s === S.sig : D.signals[h.s].theme === S.theme)) && h.r[S.tk]);
    const path = (h) => { const v = h.r[S.tk], sp = h.r.SPY || v.map(() => 0); const a = +S.hedge && S.tk !== "SPY" ? v.map((x, k) => x - sp[k]) : v; return [a[0], a[1], 0].concat(a.slice(2)); };
    const up = pool.filter((h) => h.p1 > h.p0), dn = pool.filter((h) => h.p1 < h.p0);
    const avg = (hs) => steps.map((_, k) => mean(hs.map((h) => path(h)[k])));
    const lines = []; if (up.length) lines.push({ pts: avg(up).map((v, k) => [k, v]), color: "var(--good)", dots: true }); if (dn.length) lines.push({ pts: avg(dn).map((v, k) => [k, v]), color: "var(--bad)", dots: true });
    const ctl = `<div class="controls"><label class="field"><span>Which Kalshi markets</span><select data-s="shockTheme"><option value="pair"${S.shockTheme === "pair" ? " selected" : ""}>Just the chosen market</option><option value="theme"${S.shockTheme === "theme" ? " selected" : ""}>Every market in this theme</option><option value="all"${S.shockTheme === "all" ? " selected" : ""}>Every market</option></select></label>
      <label class="field"><span>Jump of at least (pts in one hour)</span><input type="number" data-s="shockMin" min="6" max="60" value="${S.shockMin}"></label></div>`;
    if (!pool.length) return ctl + `<div class="empty">No one-hour jumps that big with hourly ${esc(S.tk)} prices. Try “Every market in this theme”, or a stock linked to the theme.</div>`;
    const first = (hs) => hs.length ? mean(hs.map((h) => path(h)[3])) / 100 : null, later = (hs) => hs.length ? mean(hs.map((h) => path(h)[9] - path(h)[3])) / 100 : null;
    const before = (hs) => hs.length ? mean(hs.map((h) => -path(h)[0])) / 100 : null;
    const say = (hs, word) => hs.length ? `After the ${hs.length} ${word}-jump${hs.length > 1 ? "s" : ""}, ${esc(S.tk)} had moved <b>${pct(first(hs), 2)}</b> by the first price you could trade, then a further <b>${pct(later(hs), 2)}</b> over the next 3 days.` : "";
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">${pool.length} one-hour Kalshi jump${pool.length > 1 ? "s" : ""} of ${S.shockMin}+ points. ${say(up, "up")} ${say(dn, "down")}</p>
      <div class="tiles">${tile("Up-jumps", up.length)}${tile("Down-jumps", dn.length)}${tile("Stock in the 7h before (up)", pct(before(up), 2))}${tile("Stock in the 7h before (down)", pct(before(dn), 2))}
        ${tile("Left to trade (up)", pct(later(up), 2))}${tile("Left to trade (down)", pct(later(dn), 2))}</div>
      <div><h3 style="margin-bottom:8px">Average ${esc(S.tk)} path around the jump</h3>${legend([["var(--good)", "After the probability jumped up"], ["var(--bad)", "After it dropped"]])}
        ${lineChart(lines, steps, { zero: true, xticks: steps.map((_, k) => k), mark: 2, fmtL: (v) => v.toFixed(1) + "%", label: "Stock path around Kalshi jumps" })}
        <p class="hint">Zero is ${esc(S.tk)}'s last price before the hour Kalshi jumped (dashed line). If the stock had already moved in the hours before, the stock led. “First trade” is the first price you could have got once the jump was visible. If the lines keep going after it, there was something left to trade.</p></div>
      ${table([["When (New York)"], ["Market"], ["Jump", "n"], ["7h before", "n"], ["First trade", "n"], ["+1 day", "n"], ["+3 days", "n"]],
        [...pool].sort((a, b) => b.t - a.t).map((h) => { const p = path(h); return `<tr><td>${h.d}</td><td class="wrap">${esc(short(D.signals[h.s].title, 60))}</td><td class="n ${cls(h.p1 - h.p0)}">${h.p0.toFixed(0)}→${h.p1.toFixed(0)}%</td>
          <td class="n">${pct(-p[0] / 100, 2)}</td><td class="n ${cls(p[3])}">${pct(p[3] / 100, 2)}</td><td class="n ${cls(p[7])}">${pct(p[7] / 100, 2)}</td><td class="n ${cls(p[9])}">${pct(p[9] / 100, 2)}</td></tr>`; }))}</div>`;
  }

  // ---------------------------------------------------------------- 4. announcements
  function viewNews() {
    const kinds = [...new Set(D.events.map((e) => e.kind))], H = Math.max(1, S.drift | 0);
    if (!kinds.includes(S.kind)) S.kind = kinds[0];
    if (S.kind === "Earnings calls") return viewEarnings(kinds, H);
    const E = D.events.filter((e) => e.kind === S.kind).map((e) => ({ e, day: ret(S.tk, e.i), after: ret(S.tk, e.i + H, H) })).filter((x) => x.day != null);
    const ctl = `<div class="controls"><label class="field"><span>Announcement</span><select data-s="kind">${kinds.map((k) => `<option${k === S.kind ? " selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
      <label class="field"><span>Then follow the stock for (days)</span><input type="number" data-s="drift" min="1" max="20" value="${H}"></label></div>`;
    if (E.length < 3) return ctl + `<div class="empty">Too few ${esc(S.kind)} announcements with prices.</div>`;
    const c0 = corr(E.map((x) => x.e.surprise), E.map((x) => x.day)), c1 = corr(E.filter((x) => x.after != null).map((x) => x.e.surprise), E.filter((x) => x.after != null).map((x) => x.after));
    const unit = S.kind === "Fed decision" ? "more hawkish than priced (in quarter-point steps)" : "higher than priced (in thresholds)";
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline">The surprise is what happened minus what Kalshi priced the evening before. Across <b>${E.length}</b> ${esc(S.kind)} announcements, ${c0 ? `the link between the surprise and ${esc(S.tk)}'s move that day was <b>${c0.r.toFixed(2)}</b>${Math.abs(c0.t) >= 2 ? "" : " (not clearly different from none)"}` : "there is too little data"}${c1 ? `, and <b>${c1.r.toFixed(2)}</b> for the following ${H} day${H > 1 ? "s" : ""}` : ""}.</p>
      <div><h3 style="margin-bottom:8px">Surprise vs ${esc(S.tk)}'s move on the day</h3>${scatter(E.map((x) => ({ x: x.e.surprise, y: x.day, tip: `${x.e.date}: surprise ${pts(x.e.surprise, 2)}, ${S.tk} ${pct(x.day, 2)}` })), { left: "← lower than priced", right: unit + " →", label: "Surprise versus reaction" })}</div>
      ${table([["Date"], ["What happened"], ["Surprise", "n"], ["How unexpected", "n"], [`${esc(S.tk)} that day`, "n"], [`Next ${H}d`, "n"]],
        [...E].reverse().map((x) => `<tr><td>${x.e.date}</td><td class="wrap">${esc(x.e.what)}</td><td class="n ${cls(x.e.surprise)}">${pts(x.e.surprise, 2)}</td><td class="n">${(x.e.shock * 100).toFixed(0)}%</td><td class="n ${cls(x.day)}">${pct(x.day, 2)}</td><td class="n ${cls(x.after)}">${pct(x.after, 2)}</td></tr>`))}
      <p class="hint">“How unexpected” is the average gap between Kalshi's price and the result across that announcement's markets: near 0% means fully priced in. These are small samples, so read the pattern, not the decimals.</p></div>`;
  }

  // Earnings calls: Kalshi's "what will they say" markets give the call date and how unexpected the call was.
  function viewEarnings(kinds, H) {
    const all = D.events.filter((e) => e.kind === "Earnings calls" && D.px[e.tk]), cos = [...new Set(all.map((e) => e.tk))].sort();
    if (S.earnTk !== "all" && !cos.includes(S.earnTk)) S.earnTk = "all";
    const E = all.filter((e) => S.earnTk === "all" || e.tk === S.earnTk).map((e) => ({ e, day: ret(e.tk, e.i), after: ret(e.tk, e.i + H, H) })).filter((x) => x.day != null);
    const ctl = `<div class="controls"><label class="field"><span>Announcement</span><select data-s="kind">${kinds.map((k) => `<option${k === S.kind ? " selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
      <label class="field"><span>Company</span><select data-s="earnTk"><option value="all">All ${cos.length} companies</option>${cos.map((t) => `<option${t === S.earnTk ? " selected" : ""}>${t}</option>`).join("")}</select></label>
      <label class="field"><span>Then follow the stock for (days)</span><input type="number" data-s="drift" min="1" max="20" value="${H}"></label></div>`;
    if (E.length < 3) return ctl + `<div class="empty">Too few earnings calls with prices.</div>`;
    const F = E.filter((x) => x.after != null), up = F.filter((x) => x.day > 0), dn = F.filter((x) => x.day < 0);
    const drift = link(F.map((x) => x.day), F.map((x) => x.after)), sur = link(E.map((x) => x.e.shock), E.map((x) => Math.abs(x.day)));
    const follow = F.length ? mean(F.map((x) => Math.sign(x.day) * x.after)) : NaN;
    return `<div style="display:grid;gap:16px">${ctl}
      <p class="headline"><b>${E.length}</b> earnings calls. The stock moved <b>${(mean(E.map((x) => Math.abs(x.day))) * 100).toFixed(1)}%</b> on the average earnings day. Trading in the same direction for the next ${H} day${H > 1 ? "s" : ""} would have averaged <b class="${cls(follow)}">${pct(follow, 2)}</b> per call${drift ? ` (link between the day's move and what followed: ${drift.r.toFixed(2)}${Math.abs(drift.t) < 2 ? ", not clearly different from none" : ""})` : ""}.${sur ? ` Calls that Kalshi found more surprising went with ${sur.r >= 0 ? "bigger" : "smaller"} moves (link ${sur.r.toFixed(2)}${Math.abs(sur.t) < 2 ? ", weak" : ""}).` : ""}</p>
      <div class="tiles">${tile("Calls", E.length)}${tile("Up days", up.length)}${tile(`Next ${H}d after up`, up.length ? pct(mean(up.map((x) => x.after)), 2) : "—")}${tile("Down days", dn.length)}${tile(`Next ${H}d after down`, dn.length ? pct(mean(dn.map((x) => x.after)), 2) : "—")}${tile("Follow the move", pct(follow, 2), cls(follow))}</div>
      <div><h3 style="margin-bottom:8px">Earnings-day move vs the next ${H} day${H > 1 ? "s" : ""}</h3>${scatter(F.map((x) => ({ x: x.day * 100, y: x.after, tip: `${x.e.tk} ${x.e.date}: ${pct(x.day, 1)} on the day, ${pct(x.after, 1)} after` })), { left: "← fell on earnings (%)", right: "rose on earnings (%) →", label: "Earnings move versus later drift" })}
        <p class="hint">Dots in the top-right and bottom-left kept going (drift). Top-left and bottom-right reversed.</p></div>
      ${table([["Date"], ["Company"], ["Most surprising thing on the call"], ["How unexpected", "n"], ["Move on earnings", "n"], [`Next ${H}d`, "n"]],
        [...E].sort((a, b) => b.e.i - a.e.i).map((x) => `<tr><td>${x.e.date}</td><td>${x.e.tk}</td><td class="wrap">${esc(x.e.what)}</td><td class="n">${(x.e.shock * 100).toFixed(0)}%</td><td class="n ${cls(x.day)}">${pct(x.day, 2)}</td><td class="n ${cls(x.after)}">${pct(x.after, 2)}</td></tr>`))}
      <p class="hint">Call dates come from Kalshi's “what will they say on the earnings call” markets. “Move on earnings” is the first full trading day after the call's markets settled, which for most companies is the day the market reacts to the results. “How unexpected” is the average gap between Kalshi's price for each phrase and whether it was said.</p></div>`;
  }

  // ---------------------------------------------------------------- 5. strongest pairs
  let SCAN = null, SCANKEY = "";
  function viewScan() {
    const key = S.scanBy + S.scanScope + S.hedge;
    if (key !== SCANKEY) {
      const lag = S.scanBy === "lead" ? 1 : S.scanBy === "same" ? 0 : -1; SCAN = []; SCANKEY = key;
      D.signals.forEach((s, si) => { for (const tk of S.scanScope === "linked" ? D.themes[s.theme].tickers : D.core || Object.keys(D.px)) {
        const [x, y] = lagPairs(s, tk, lag), c = x.length >= 40 ? link(x, y) : null; if (c) SCAN.push({ si, tk, c }); } });
      SCAN.sort((a, b) => Math.abs(b.c.t) - Math.abs(a.c.t));
    }
    const strong = SCAN.filter((p) => Math.abs(p.c.t) > 1.96).length, bonf = SCAN.filter((p) => Math.abs(p.c.t) > 3.9).length;
    const what = { lead: "Kalshi's move today vs the stock's move tomorrow", same: "Kalshi and the stock on the same day", lag: "the stock's move today vs Kalshi's move tomorrow" }[S.scanBy];
    return `<div style="display:grid;gap:16px"><div class="controls">
        <label class="field"><span>Rank by</span><select data-s="scanBy"><option value="lead"${S.scanBy === "lead" ? " selected" : ""}>Kalshi leads the stock by a day</option><option value="same"${S.scanBy === "same" ? " selected" : ""}>Same-day link</option><option value="lag"${S.scanBy === "lag" ? " selected" : ""}>Stock leads Kalshi by a day</option></select></label>
        <label class="field"><span>Compare each market with</span><select data-s="scanScope"><option value="linked"${S.scanScope === "linked" ? " selected" : ""}>Stocks linked to its theme</option><option value="every"${S.scanScope === "every" ? " selected" : ""}>Every stock (slower, more false alarms)</option></select></label></div>
      <p class="headline">${SCAN.length.toLocaleString()} pairs tested for ${what}. <b>${strong}</b> pass the usual test; luck alone would pass about <b>${Math.round(SCAN.length * 0.05)}</b>. <b>${bonf}</b> are strong enough to survive that many tries.</p>
      ${table([["Kalshi market"], ["Stock"], ["Link", "n"], ["Per +10 pts", "n"], ["Days", "n"], ["Strength (t)", "n"]],
        SCAN.slice(0, 60).map((p, k) => `<tr class="click" data-pair="${k}"><td class="wrap">${esc(short(D.signals[p.si].title, 76))}</td><td>${p.tk}</td><td class="n ${cls(p.c.r)}">${p.c.r.toFixed(2)}</td><td class="n ${cls(p.c.slope)}">${pct(p.c.slope * 10, 2)}</td><td class="n">${p.c.n}</td><td class="n">${p.c.t.toFixed(1)}</td></tr>`), 520)}
      <p class="hint">Click a row to open that pair in <b>Who moves first</b>, then try it as a <b>Lag trade</b>. A strength above about 3.9 is what it takes to stand out from this many comparisons; treat the rest as leads to check, not findings.</p></div>`;
  }

  // ---------------------------------------------------------------- 6. paper trade
  function viewPaper() {
    const s = sig(), auto = S.dir === "auto" ? (link(...lagPairs(s, S.tk, 0)) || { r: 0 }).r >= 0 ? "up" : "down" : S.dir;
    const cfg = { kalshi_ticker: s.id, kalshi_series: s.id.split("-")[0], symbol: S.tk, move_points: +S.thr, lookback_days: +S.look, stock_direction_when_probability_rises: auto,
                  max_stock_move_pct: S.gap === "" ? null : +S.gap, hold_days: +S.hold, dollars_per_trade: 1000, hedge_with_spy: !!+S.hedge };
    const live = !s.result;
    return `<div style="display:grid;gap:14px">
      <p class="headline">Run the current lag-trade rule on live prices with an <b>Alpaca paper account</b> (fake money). The script reads Kalshi's live probability, checks the rule, and places a paper order for the stock.</p>
      ${live ? "" : `<p class="compare">This Kalshi market has already settled, so it can't trigger again. Pick one that is still open (its Settled tile says “open”) before running the script.</p>`}
      <p class="note">1. Create a free paper account at alpaca.markets and copy its API key and secret. 2. Save the settings below as <code>signal.json</code>. 3. Run:</p>
      <pre class="code">export ALPACA_KEY=your_paper_key ALPACA_SECRET=your_paper_secret
python scripts/alpaca_paper.py signal.json            # dry run: shows what it would do
python scripts/alpaca_paper.py signal.json --trade    # places the paper order</pre>
      <pre class="code" id="cfg">${esc(JSON.stringify(cfg, null, 2))}</pre>
      <div><button class="btn primary" id="dl">Download signal.json</button></div>
      <p class="hint">The script only talks to Alpaca's paper endpoint and refuses to run against a live account. It trades once per signal, and closes the position after the holding period when you run it again (for example, once a day from cron).</p></div>`;
  }

  // ---------------------------------------------------------------- controls
  const VIEWS = { lead: viewLead, trade: viewTrade, shock: viewShock, news: viewNews, scan: viewScan, paper: viewPaper };
  function sync() {
    $("tabs").innerHTML = TABS.map(([id, l]) => `<button role="tab" data-tab="${id}" aria-selected="${S.tab === id}">${l}</button>`).join("");
    $("theme").innerHTML = Object.entries(D.themes).map(([k, t]) => `<option value="${k}"${k === S.theme ? " selected" : ""}>${esc(t.label)} (${D.signals.filter((s) => s.theme === k).length})</option>`).join("");
    const list = D.signals.map((s, i) => [s, i]).filter(([s]) => s.theme === S.theme);
    if (!list.some(([, i]) => i === S.sig) && list.length) S.sig = list[0][1];
    $("sig").innerHTML = list.map(([s, i]) => `<option value="${i}"${i === S.sig ? " selected" : ""}>${esc(short(s.title, 78))} · ${s.open.slice(2, 7)}→${s.close.slice(2, 7)}</option>`).join("");
    const linked = D.themes[S.theme].tickers, rest = Object.keys(D.px).filter((t) => !linked.includes(t));
    if (!D.px[S.tk]) S.tk = linked[0];
    const opt = (t) => `<option${t === S.tk ? " selected" : ""}>${t}</option>`;
    $("tk").innerHTML = `<optgroup label="Linked to this theme">${linked.map(opt).join("")}</optgroup><optgroup label="Everything else">${rest.map(opt).join("")}</optgroup>`;
    for (const k of ["hedge", "thr", "look", "dir", "gap", "entry", "hold", "cost", "scope"]) if ($(k)) $(k).value = S[k];
    const s = sig(), [a, b] = span(s);
    $("pairnote").textContent = `${s.id} · ${D.dates[a]} to ${D.dates[b]} · ${Math.round(s.vol).toLocaleString()} contracts traded.`;
    if ($("rulepanel")) $("rulepanel").hidden = !(S.tab === "trade" || S.tab === "paper");
  }
  function render() { sync(); $("view").innerHTML = VIEWS[S.tab](); if (S.after) S.after(); }
  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-tab],[data-pair],#dl"); if (!t) return;
    if (t.dataset.tab) S.tab = t.dataset.tab;
    else if (t.dataset.pair != null) { const p = SCAN[+t.dataset.pair]; S.sig = p.si; S.theme = D.signals[p.si].theme; S.tk = p.tk; S.tab = "lead"; window.scrollTo({ top: 0 }); }
    else { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([$("cfg").textContent], { type: "application/json" })); a.download = "signal.json"; a.click(); return; }
    render();
  });
  document.addEventListener("change", (e) => {
    const t = e.target, k = t.dataset.s || t.id; if (!(k in S)) return;
    const num = ["thr", "look", "hold", "cost", "shockMin", "drift", "hedge"].includes(k);
    if (k === "scanBy" || k === "scanScope" || k === "hedge") SCANKEY = "";
    S[k] = k === "sig" ? +t.value : k === "gap" ? t.value : num ? Math.max(0, +t.value || 0) : t.type === "number" ? (t.value === "" ? "" : +t.value) : t.value;
    if (k === "theme") { S.sig = -1; if (!D.themes[S.theme].tickers.includes(S.tk)) S.tk = D.themes[S.theme].tickers[0]; }
    render();
  });
  $("built").textContent = `Data built ${D.built}: ${D.signals.length} Kalshi markets, ${Object.keys(D.px).length} stocks and ETFs, ${D.dates[0]} to ${D.dates[N - 1]}.`;
  // The Strategies page (strategies.js) adds its own tabs on top of the same data and helpers.
  window.SLAB_TEST = { trades };          // used by tests/test_markets.py
  window.SLAB = { D, S, N, STAKE, esc, pct, pts, money, cls, mean, C, O, ret, dP, corr, link, ranks, lagPairs, sig, span, short, stats,
                  lineChart, barChart, scatter, legend, tile, table, VIEWS, render, setTabs: (t, first) => { TABS = t; S.tab = first; } };
  document.addEventListener("DOMContentLoaded", render);
})();
