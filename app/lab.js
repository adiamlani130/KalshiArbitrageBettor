(function () {
  const DS = window.DATASETS, $ = (id) => document.getElementById(id);
  const STAKE = 10;
  const S = { ds: "tennis", moment: null, side: null, pmin: 1, pmax: 99, filters: [], from: "", to: "",
              take: "all", n: 1000, seed: 1, tab: "bet", x: null, bins: 5, preset: null };

  // ---------------------------------------------------------------- math
  const fee = (p, c) => Math.ceil(0.07 * c * p * (1 - p) * 100 - 1e-9) / 100;
  const pnl = (p, won) => { const c = STAKE / p; return (won ? c - STAKE : -STAKE) - fee(p, c); };
  const odds = (p) => p >= 0.5 ? "−" + Math.round(100 * p / (1 - p)) : "+" + Math.round(100 * (1 - p) / p);
  const pct = (v, d = 1) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%";
  const money = (v) => (v > 0 ? "+$" : v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
  const median = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : NaN; };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  const ds = () => DS[S.ds];
  const col = (k) => ds().cols.find((c) => c.key === k);
  const momentAt = () => (ds().moments.find((m) => m.id === S.moment) || {}).at ?? 0;
  const fmtVal = (c, v) => v == null ? "—" : c.type === "bool" ? (v ? "Yes" : "No") : c.pct ? (v * 100).toFixed(0) + "¢" : typeof v === "number" ? +v.toFixed(1) : v;

  // ---------------------------------------------------------------- sample → filters → bets
  function sample() {
    let rows = ds().rows.filter((r) => (!S.from || r.date >= S.from) && (!S.to || r.date <= S.to));
    const n = Math.max(1, S.n | 0);
    if (S.take === "recent") rows = [...rows].sort((a, b) => b.date.localeCompare(a.date)).slice(0, n);
    if (S.take === "random") { const R = rng(S.seed); rows = rows.map((r) => [R(), r]).sort((a, b) => a[0] - b[0]).slice(0, n).map((x) => x[1]); }
    return rows;
  }
  function passes(r, f) {
    const v = r[f.key]; if (v == null) return false;
    const c = col(f.key); if (!c) return true;
    if (c.type === "bool") return f.val === "" || f.val == null || v === (f.val === true || f.val === "true");
    if (c.type === "cat") return !f.val || v === f.val;
    const lo = f.min === "" || f.min == null ? -Infinity : +f.min, hi = f.max === "" || f.max == null ? Infinity : +f.max;
    return c.type === "date" ? (!f.min || v >= f.min) && (!f.max || v <= f.max) : v >= lo && v <= hi;
  }
  function bets(rows) {
    const out = [];
    for (const r of rows) {
      if (!S.filters.every((f) => passes(r, f))) continue;
      const b = ds().bet(r, S.moment, S.side);
      if (!b || b.p == null || !(b.p > 0.009 && b.p < 0.991)) continue;
      if (b.p * 100 < S.pmin - 1e-9 || b.p * 100 > S.pmax + 1e-9) continue;
      out.push(Object.assign({ r, net: pnl(b.p, b.won) }, b));
    }
    return out.sort((a, b) => a.r.date.localeCompare(b.r.date));
  }
  function stats(B) {
    const n = B.length; if (!n) return null;
    const nets = B.map((b) => b.net), mean = nets.reduce((s, x) => s + x, 0) / n;
    const sd = Math.sqrt(nets.reduce((s, x) => s + (x - mean) ** 2, 0) / Math.max(1, n - 1));
    const half = Math.floor(n / 2), h1 = nets.slice(0, half), h2 = nets.slice(half);
    const avg = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length / STAKE : NaN;
    return { n, won: B.filter((b) => b.won).length / n, odds: odds(median(B.map((b) => b.p))), staked: STAKE * n,
             net: mean * n, roi: mean / STAKE, lo: (mean - 1.96 * sd / Math.sqrt(n)) / STAKE, hi: (mean + 1.96 * sd / Math.sqrt(n)) / STAKE,
             r1: avg(h1), r2: avg(h2), d1: B[0].r.date, d2: B[half]?.r.date, d3: B[n - 1].r.date, n1: h1.length, n2: h2.length };
  }

  // ---------------------------------------------------------------- controls
  function fillSelect(el, items, val) { el.innerHTML = items.map((i) => `<option value="${esc(i.id)}"${i.id === val ? " selected" : ""}>${esc(i.label)}</option>`).join(""); }
  function renderDatasetButtons() {
    $("dataset").innerHTML = Object.entries(DS).map(([k, d]) => `<button aria-pressed="${k === S.ds}" data-ds="${k}">${esc(d.label)}</button>`).join("");
  }
  function renderPresets() {
    const groups = {};
    PRESETS.forEach((p, i) => (groups[p.ds] = groups[p.ds] || []).push(`<option value="${i}"${S.preset === i ? " selected" : ""}>${esc(p.label)}</option>`));
    $("preset").innerHTML = `<option value="">Load a strategy from the research…</option>` +
      Object.entries(groups).map(([k, o]) => `<optgroup label="${esc(DS[k].label)}">${o.join("")}</optgroup>`).join("");
  }
  function catValues(key) {
    const counts = {}; ds().rows.forEach((r) => { if (r[key] != null) counts[r[key]] = (counts[r[key]] || 0) + 1; });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).map((e) => e[0]);
  }
  function renderFilters() {
    const allowed = ds().cols.filter((c) => c.at <= momentAt());
    $("filters").innerHTML = S.filters.map((f, i) => {
      const c = col(f.key) || allowed[0];
      const opts = allowed.map((a) => `<option value="${a.key}"${a.key === c.key ? " selected" : ""}>${esc(a.label)}</option>`).join("");
      let vals;
      if (c.type === "bool") vals = `<div class="vals one"><select data-i="${i}" data-f="val"><option value="true"${f.val === true || f.val === "true" ? " selected" : ""}>Yes</option><option value="false"${f.val === false || f.val === "false" ? " selected" : ""}>No</option></select></div>`;
      else if (c.type === "cat") vals = `<div class="vals one"><select data-i="${i}" data-f="val">${catValues(c.key).map((v) => `<option${v === String(f.val) ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></div>`;
      else { const t = c.type === "date" ? "date" : "number", st = c.pct ? ' step="0.01"' : ' step="1"';
        vals = `<div class="vals"><input type="${t}"${st} placeholder="min" data-i="${i}" data-f="min" value="${esc(f.min ?? "")}"><input type="${t}"${st} placeholder="max" data-i="${i}" data-f="max" value="${esc(f.max ?? "")}"></div>`; }
      return `<div class="filter"><select data-i="${i}" data-f="key">${opts}</select><button class="x" data-rm="${i}" aria-label="Remove condition">×</button>${vals}${c.pct ? '<span class="hint" style="grid-column:1/-1">Prices as decimals: 0.70 = 70¢ = −233</span>' : ""}</div>`;
    }).join("") || `<p class="hint">No conditions. Every ${ds().unit.replace(/s$/, "")} in the sample counts.</p>`;
  }
  function syncControls() {
    const d = ds();
    renderDatasetButtons(); renderPresets();
    if (!d.moments.some((m) => m.id === S.moment)) S.moment = d.moments[0].id;
    if (!d.sides.some((s) => s.id === S.side)) S.side = d.sides[0].id;
    fillSelect($("moment"), d.moments, S.moment); fillSelect($("side"), d.sides, S.side);
    const dates = d.rows.map((r) => r.date).sort();
    for (const id of ["from", "to"]) { $(id).min = dates[0]; $(id).max = dates[dates.length - 1]; }
    $("from").value = S.from || dates[0]; $("to").value = S.to || dates[dates.length - 1];
    $("take").value = S.take; $("n").value = S.n; $("n").disabled = S.take === "all"; $("reshuffle").hidden = S.take !== "random";
    $("pmin").value = S.pmin; $("pmax").value = S.pmax;
    $("oddsnote").textContent = `${S.pmin}¢–${S.pmax}¢ is ${odds(Math.max(.01, S.pmin / 100))} to ${odds(Math.min(.99, S.pmax / 100))} in sportsbook odds.`;
    renderFilters();
    if (!S.x || !col(S.x)) S.x = d.defaultX;
    $("xcol").innerHTML = d.cols.filter((c) => c.type !== "date").map((c) =>
      `<option value="${c.key}"${c.key === S.x ? " selected" : ""}>${esc(c.label)}${c.at > momentAt() ? " (after your bet)" : ""}</option>`).join("");
    $("bins").value = S.bins;
    $("tab-bet").setAttribute("aria-selected", S.tab === "bet"); $("tab-link").setAttribute("aria-selected", S.tab === "link");
    $("view-bet").hidden = S.tab !== "bet"; $("view-link").hidden = S.tab !== "link";
  }

  // ---------------------------------------------------------------- charts (plain SVG)
  function pnlChart(B) {
    const W = 640, H = 220, L = 52, R = 12, T = 12, Bm = 26;
    let cum = 0; const pts = B.map((b, i) => ({ i, y: (cum += b.net), b }));
    const ys = [0, ...pts.map((p) => p.y)], lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.08 || 10;
    const y0 = lo - pad, y1 = hi + pad, X = (i) => L + (W - L - R) * (pts.length > 1 ? i / (pts.length - 1) : 0.5), Y = (v) => T + (H - T - Bm) * (1 - (v - y0) / (y1 - y0));
    const ticks = niceTicks(y0, y1, 4);
    const grid = ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line-2)"/><text x="${L - 8}" y="${Y(t) + 4}" text-anchor="end">${money(t)}</text>`).join("");
    const line = pts.map((p, k) => `${k ? "L" : "M"}${X(p.i).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
    const area = pts.length ? `${line}L${X(pts[pts.length - 1].i)},${Y(0)}L${X(0)},${Y(0)}Z` : "";
    const end = pts[pts.length - 1], color = end && end.y >= 0 ? "var(--good)" : "var(--bad)";
    return `<div class="chart" data-kind="pnl"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Running profit over ${B.length} bets">
      ${grid}<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--ink-3)" stroke-width="1"/>
      <path d="${area}" fill="${color}" opacity=".10"/><path d="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
      ${end ? `<circle cx="${X(end.i)}" cy="${Y(end.y)}" r="4" fill="${color}" stroke="var(--sheet)" stroke-width="2"/>` : ""}
      <text x="${L}" y="${H - 6}">${esc(B[0]?.r.date || "")}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${esc(end?.b.r.date || "")}</text>
      <line class="cross" x1="0" x2="0" y1="${T}" y2="${H - Bm}" stroke="var(--ink-3)" stroke-dasharray="3 3" opacity="0"/>
      <rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - Bm}" fill="transparent" class="hit"/></svg><div class="tip" hidden></div></div>`;
  }
  function niceTicks(a, b, n) {
    const step0 = (b - a) / n, mag = 10 ** Math.floor(Math.log10(Math.abs(step0) || 1)), err = step0 / mag;
    const step = (err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1) * mag, out = [];
    for (let t = Math.ceil(a / step) * step; t <= b; t += step) out.push(Math.abs(t) < 1e-9 ? 0 : t);
    return out;
  }
  function wirePnl(root, B) {
    const ch = root.querySelector('[data-kind="pnl"]'); if (!ch || !B.length) return;
    const svg = ch.querySelector("svg"), tip = ch.querySelector(".tip"), cross = svg.querySelector(".cross");
    let cum = 0; const cums = B.map((b) => (cum += b.net));
    const move = (ev) => {
      const rc = svg.getBoundingClientRect(), vx = (ev.clientX - rc.left) / rc.width * 640;
      const i = Math.max(0, Math.min(B.length - 1, Math.round((vx - 52) / (640 - 64) * (B.length - 1))));
      const x = 52 + (640 - 64) * (B.length > 1 ? i / (B.length - 1) : .5), b = B[i];
      cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.setAttribute("opacity", 1);
      tip.hidden = false; tip.style.left = (x / 640 * rc.width) + "px"; tip.style.top = "30px";
      tip.innerHTML = `Bet ${i + 1} · ${esc(b.r.date)}<br>${esc(b.pick)} at ${Math.round(b.p * 100)}¢ · ${b.won ? "won" : "lost"} ${money(b.net)}<br>Running total ${money(cums[i])}`;
    };
    svg.addEventListener("pointermove", move); svg.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("opacity", 0); });
  }
  function linkChart(G) {
    const W = 640, H = 240, L = 40, R = 12, T = 14, Bm = 44, n = G.length, bw = (W - L - R) / n;
    const Y = (v) => T + (H - T - Bm) * (1 - v);
    const grid = [0, .25, .5, .75, 1].map((t) => `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="var(--line-2)"/><text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${t * 100}%</text>`).join("");
    const bars = G.map((g, i) => {
      const x = L + i * bw + bw * 0.18, w = bw * 0.64, top = Y(g.won), mk = Y(g.price);
      return `<g class="bar" data-i="${i}"><rect x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - Bm}" fill="transparent"/>
        <path d="M${x},${Y(0)}V${top + 4}Q${x},${top} ${x + 4},${top}H${x + w - 4}Q${x + w},${top} ${x + w},${top + 4}V${Y(0)}Z" fill="var(--accent)" opacity=".85"/>
        <line x1="${x - 4}" x2="${x + w + 4}" y1="${mk}" y2="${mk}" stroke="var(--ink)" stroke-width="2.5"/>
        <text x="${L + i * bw + bw / 2}" y="${H - 26}" text-anchor="middle">${esc(g.label)}</text>
        <text x="${L + i * bw + bw / 2}" y="${H - 12}" text-anchor="middle">n=${g.n}</text></g>`;
    }).join("");
    return `<div class="legend"><span><i class="sw" style="background:var(--accent)"></i>How often your pick actually won</span><span><i class="sw" style="background:var(--ink);height:3px"></i>What the Kalshi price implied</span></div>
      <div class="chart" data-kind="link"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Win rate versus market price by group">${grid}${bars}
      <line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="var(--ink-3)"/></svg><div class="tip" hidden></div></div>`;
  }
  function wireLink(root, G) {
    const ch = root.querySelector('[data-kind="link"]'); if (!ch) return;
    const tip = ch.querySelector(".tip"), svg = ch.querySelector("svg");
    svg.querySelectorAll(".bar").forEach((el) => {
      el.addEventListener("pointerenter", () => {
        const g = G[+el.dataset.i], rc = svg.getBoundingClientRect(), n = G.length;
        tip.hidden = false; tip.style.left = ((40 + (+el.dataset.i + .5) * (588 / n)) / 640 * rc.width) + "px"; tip.style.top = "20px";
        tip.innerHTML = `${esc(g.label)} · ${g.n} bets<br>Won ${(g.won * 100).toFixed(1)}% · price said ${(g.price * 100).toFixed(1)}%<br>Return ${pct(g.roi)}`;
      });
      el.addEventListener("pointerleave", () => (tip.hidden = true));
    });
  }

  // ---------------------------------------------------------------- views
  const sideLabel = () => ds().sides.find((s) => s.id === S.side).label.toLowerCase();
  const momentLabel = () => { const m = ds().moments.find((m) => m.id === S.moment); return m.phrase || m.label.toLowerCase(); };
  function renderBet(rows) {
    const B = bets(rows), st = stats(B), v = $("view-bet"), pre = S.preset != null ? PRESETS[S.preset] : null;
    const compare = pre && pre.ds === S.ds ? `<p class="compare"><b>Original research result</b> for “${esc(pre.label)}”: ${esc(pre.orig)}. That run used a smaller, older data pull; the numbers above use the fresh one.</p>` : "";
    if (!st) { v.innerHTML = compare + `<div class="empty">No bets match these settings. Try widening the price range or removing a condition.</div>`; return; }
    const luck = st.lo > 0 ? ["good", "Likely a real edge", "even the low end of the likely range is profitable"]
      : st.hi < 0 ? ["bad", "Reliably loses", "even the high end of the likely range loses money"]
      : ["warn", "Could be luck", `the likely range runs from ${pct(st.lo)} to ${pct(st.hi)}`];
    const halves = st.n < 20 ? ["", "Too few bets to split", ""] : st.r1 > 0 && st.r2 > 0 ? ["good", "Held up in both halves", ""] : st.r1 < 0 && st.r2 < 0 ? ["bad", "Lost in both halves", ""] : ["warn", "Only worked in one half", ""];
    const buckets = [[1, 20], [20, 40], [40, 60], [60, 80], [80, 99]].map(([a, b]) => {
      const x = B.filter((q) => q.p * 100 >= a && q.p * 100 < (b === 99 ? 100 : b)), s = stats(x);
      return s ? `<tr><td>${a}–${b}¢ <span class="hint">(${odds(a / 100)} to ${odds(Math.min(.99, b / 100))})</span></td><td class="n">${s.n}</td><td class="n">${(s.won * 100).toFixed(1)}%</td><td class="n ${s.roi >= 0 ? "pos" : "neg"}">${pct(s.roi)}</td></tr>` : "";
    }).join("");
    const recent = B.slice(-60).reverse().map((b) => `<tr><td>${esc(b.r.date)}</td><td>${esc(b.r.match)}</td><td>${esc(b.pick)}</td><td class="n">${Math.round(b.p * 100)}¢ <span class="hint">${odds(b.p)}</span></td><td>${b.won ? "Won" : "Lost"}</td><td class="n ${b.net >= 0 ? "pos" : "neg"}">${money(b.net)}</td></tr>`).join("");
    v.innerHTML = `<div style="display:grid;gap:16px">
      <p class="headline">Betting <b>${esc(sideLabel())}</b> ${esc(momentLabel())} in <b>${st.n.toLocaleString()}</b> ${ds().unit} would have ${st.net >= 0 ? "made" : "lost"} <b class="${st.net >= 0 ? "pos" : "neg"}">${money(st.net).replace(/^[+−]/, "")}</b> on $${st.staked.toLocaleString()} staked, a <b class="${st.roi >= 0 ? "pos" : "neg"}">${pct(st.roi)}</b> return.</p>
      ${compare}
      <div class="tiles">
        <div class="tile"><span>Bets</span><b>${st.n.toLocaleString()}</b></div>
        <div class="tile"><span>Won</span><b>${(st.won * 100).toFixed(1)}%</b></div>
        <div class="tile"><span>Typical odds</span><b>${st.odds}</b></div>
        <div class="tile"><span>Staked</span><b>$${st.staked.toLocaleString()}</b></div>
        <div class="tile"><span>Net</span><b class="${st.net >= 0 ? "pos" : "neg"}">${money(st.net)}</b></div>
        <div class="tile"><span>Return</span><b class="${st.roi >= 0 ? "pos" : "neg"}">${pct(st.roi)}</b></div>
      </div>
      <div class="pills"><span class="pill ${luck[0]}"><i>${luck[1]}</i> ${luck[2]}</span>
        <span class="pill ${halves[0]}"><i>${halves[1]}</i> ${st.n >= 20 ? `${esc(st.d1)} → ${esc(st.d2)}: ${pct(st.r1)} · ${esc(st.d2)} → ${esc(st.d3)}: ${pct(st.r2)}` : ""}</span></div>
      <div><h3 style="margin-bottom:8px">Running profit, bet by bet</h3>${pnlChart(B)}</div>
      <div class="grid2">
        <div><h3 style="margin-bottom:8px">By the price you paid</h3><div class="tablewrap"><table><thead><tr><th>Price</th><th class="n">Bets</th><th class="n">Won</th><th class="n">Return</th></tr></thead><tbody>${buckets}</tbody></table></div>
          <p class="hint" style="margin-top:8px">Long shots (cheap prices) usually lose more than favorites. That's the favorite-longshot bias.</p></div>
        <div><h3 style="margin-bottom:8px">Latest bets</h3><div class="tablewrap" style="max-height:320px;overflow-y:auto"><table><thead><tr><th>Date</th><th>Game</th><th>Pick</th><th class="n">Price</th><th>Result</th><th class="n">P&amp;L</th></tr></thead><tbody>${recent}</tbody></table></div></div>
      </div></div>`;
    wirePnl(v, B);
  }
  function groups(B) {
    const c = col(S.x), k = Math.max(2, +S.bins);
    const has = B.filter((b) => b.r[S.x] != null);
    let G;
    if (c.type === "num") {
      const vals = has.map((b) => b.r[S.x]).sort((a, b) => a - b);
      const cuts = [...new Set(Array.from({ length: k - 1 }, (_, i) => vals[Math.floor(vals.length * (i + 1) / k)]))];
      const edges = [-Infinity, ...cuts, Infinity];
      G = edges.slice(0, -1).map((lo, i) => {
        const hi = edges[i + 1], x = has.filter((b) => b.r[S.x] >= lo && b.r[S.x] < hi);
        const a = x.length ? Math.min(...x.map((b) => b.r[S.x])) : lo, z = x.length ? Math.max(...x.map((b) => b.r[S.x])) : hi;
        return { label: a === z ? fmtVal(c, a) : `${fmtVal(c, a)}–${fmtVal(c, z)}`, x };
      });
    } else {
      const keys = [...new Set(has.map((b) => String(b.r[S.x])))];
      G = keys.map((key) => ({ label: c.type === "bool" ? (key === "true" ? "Yes" : "No") : key, x: has.filter((b) => String(b.r[S.x]) === key) }))
        .sort((a, b) => b.x.length - a.x.length).slice(0, 10);
    }
    return G.filter((g) => g.x.length).map((g) => { const s = stats(g.x);
      return { label: g.label, n: s.n, won: s.won, price: g.x.reduce((t, b) => t + b.p, 0) / s.n, roi: s.roi, lo: s.lo, hi: s.hi }; });
  }
  function renderLink(rows) {
    const B = bets(rows), out = $("linkout"), c = col(S.x);
    if (!B.length) { out.innerHTML = `<div class="empty">No bets match these settings.</div>`; return; }
    const G = groups(B);
    const best = [...G].filter((g) => g.n >= 30).sort((a, b) => (b.won - b.price) - (a.won - a.price))[0];
    const later = c.at > momentAt();
    out.innerHTML = `<div style="display:grid;gap:14px;margin-top:14px">
      <p class="headline">Does <b>${esc(c.label.toLowerCase())}</b> change how often <b>${esc(sideLabel())}</b> wins, compared with what Kalshi's price ${esc(momentLabel())} expected?</p>
      ${later ? `<p class="compare">This is only known <b>after</b> you'd place the bet, so it can show a link but can't be a strategy on its own.</p>` : ""}
      ${linkChart(G)}
      <div class="tablewrap"><table><thead><tr><th>${esc(c.label)}</th><th class="n">Bets</th><th class="n">Won</th><th class="n">Price implied</th><th class="n">Gap</th><th class="n">Return</th><th class="n">Likely range</th></tr></thead><tbody>
      ${G.map((g) => `<tr><td>${esc(g.label)}</td><td class="n">${g.n}</td><td class="n">${(g.won * 100).toFixed(1)}%</td><td class="n">${(g.price * 100).toFixed(1)}%</td><td class="n ${g.won - g.price >= 0 ? "pos" : "neg"}">${pct(g.won - g.price)}</td><td class="n ${g.roi >= 0 ? "pos" : "neg"}">${pct(g.roi)}</td><td class="n">${pct(g.lo, 0)} to ${pct(g.hi, 0)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="hint">${best ? `Biggest gap: <b>${esc(best.label)}</b>, where picks won ${pct(best.won - best.price)} more often than the price implied (${best.n} bets). ` : ""}A gap only matters if it survives the fee and a fresh sample. Check it in <b>Test a bet</b>, then split the dates.</p></div>`;
    wireLink(out, G);
  }
  function render() {
    syncControls();
    const rows = sample();
    const all = ds().rows.length;
    $("samplenote").textContent = `${rows.length.toLocaleString()} of ${all.toLocaleString()} ${ds().unit} in the sample.`;
    if (S.tab === "bet") renderBet(rows); else renderLink(rows);
  }

  // ---------------------------------------------------------------- events
  document.addEventListener("click", (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.ds) { Object.assign(S, { ds: t.dataset.ds, moment: null, side: null, filters: [], from: "", to: "", x: null, preset: null, pmin: 1, pmax: 99 }); render(); }
    else if (t.dataset.rm != null) { S.filters.splice(+t.dataset.rm, 1); S.preset = null; render(); }
    else if (t.id === "addfilter") { const c = ds().cols.find((c) => c.at <= momentAt() && c.type !== "date"); S.filters.push({ key: c.key }); render(); }
    else if (t.id === "reshuffle") { S.seed++; render(); }
    else if (t.id === "scratch") { Object.assign(S, { moment: null, side: null, filters: [], from: "", to: "", take: "all", pmin: 1, pmax: 99, preset: null, tab: "bet" }); render(); }
    else if (t.id === "tab-bet" || t.id === "tab-link") { S.tab = t.id.slice(4); render(); }
  });
  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.i != null) {
      const f = S.filters[+t.dataset.i];
      if (t.dataset.f === "key") { S.filters[+t.dataset.i] = { key: t.value }; const c = col(t.value); if (c.type === "bool") S.filters[+t.dataset.i].val = true; if (c.type === "cat") S.filters[+t.dataset.i].val = catValues(c.key)[0]; }
      else f[t.dataset.f] = t.value;
      S.preset = null; render(); return;
    }
    const map = { from: "from", to: "to", take: "take", moment: "moment", side: "side", xcol: "x", bins: "bins" };
    if (map[t.id]) { S[map[t.id]] = t.value; if (t.id === "moment") S.filters = S.filters.filter((f) => (col(f.key) || {}).at <= momentAt()); if (!["xcol", "bins"].includes(t.id)) S.preset = null; render(); }
    else if (t.id === "n") { S.n = Math.max(10, +t.value || 1000); render(); }
    else if (t.id === "pmin" || t.id === "pmax") { S[t.id] = Math.min(99, Math.max(1, +t.value || (t.id === "pmin" ? 1 : 99))); S.preset = null; render(); }
    else if (t.id === "preset" && t.value !== "") {
      const p = PRESETS[+t.value];
      Object.assign(S, { ds: p.ds, moment: p.moment, side: p.side, pmin: p.pmin || 1, pmax: p.pmax || 99, from: p.from || "", to: p.to || "",
                         take: "all", filters: p.filters.map((f) => Object.assign({}, f)), preset: +t.value, tab: "bet", x: null });
      render();
    }
  });
  $("built").textContent = `Data built ${window.EDGE_DATA.built}.`;
  const start = PRESETS.findIndex((p) => p.label === "Bet against set-1 winner at −233 to −400");
  const p = PRESETS[start];
  Object.assign(S, { ds: p.ds, moment: p.moment, side: p.side, filters: p.filters.map((f) => Object.assign({}, f)), preset: start });
  render();
})();
