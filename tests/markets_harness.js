// Runs app/stocks.js and app/strategies.js outside a browser and checks that no trade decision uses future data:
// compute every decision, scramble all prices after day K, recompute, and compare the decisions made up to day K.
const fs = require("fs"), vm = require("vm"), path = require("path");
const app = path.join(__dirname, "..", "app");
const el = () => ({ innerHTML: "", textContent: "", value: "", hidden: false, style: {}, dataset: {}, addEventListener() {}, querySelectorAll: () => [], querySelector: () => null, setAttribute() {} });
const els = {};
const ctx = { console, Math, Date, JSON, Object, Array, Number, String, Set, Map, Blob: function () {}, URL: { createObjectURL: () => "" },
  URLSearchParams, location: { search: "", hash: "", pathname: "/strategies.html" }, matchMedia: () => ({ matches: true }),
  document: { getElementById: (id) => (els[id] = els[id] || el()), addEventListener() {}, querySelectorAll: () => [], createElement: el, body: el() } };
ctx.window = ctx; vm.createContext(ctx);
for (const f of ["data/stocks.js", "data/targets.js", "stocks.js", "strategies.js"]) vm.runInContext(fs.readFileSync(path.join(app, f), "utf8"), ctx, { filename: f });
const { D, S, N } = ctx.SLAB, { trades } = ctx.SLAB_TEST, { model, basketTrades, hedgeRun, revTrades } = ctx.STRAT_TEST, T = ctx.TARGET_DATA;

let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const snapshot = JSON.stringify([D.px, D.signals.map((s) => [s.p, s.q]), T.under]);
function scrambleAfter(K) {
  for (const tk in D.px) for (const k of ["o", "c"]) for (let i = K + 1; i < N; i++) if (D.px[tk][k][i] != null) D.px[tk][k][i] = 5 + 500 * rnd();
  for (const s of D.signals) for (const k of ["p", "q"]) for (let i = K + 1; i < N; i++) if (s[k] && s[k][i] != null) s[k][i] = Math.round(1 + 98 * rnd());
  for (const u in T.under) for (const k of ["c", "h", "l", "v"]) for (let i = K + 1; i < N; i++) if (T.under[u][k][i] != null) T.under[u][k][i] = 1 + 1000 * rnd();
}
function restore() { const [px, sp, un] = JSON.parse(snapshot); Object.assign(D.px, px); D.signals.forEach((s, j) => { s.p = sp[j][0]; s.q = sp[j][1]; }); Object.assign(T.under, un); }

const results = {}, K = Math.floor(N * 0.6);
const sigs = D.signals.map((s, i) => [s, i]).filter(([s]) => s.p.filter((v) => v != null).length > 120).slice(0, 40);
function decisions() {
  const out = { lag: [], rev: [], basket: [], hedge: [], options: [], canary: [] };
  Object.assign(S, { thr: 3, look: 1, dir: "auto", gap: "", entry: "open", hold: 3, cost: 0.05, hedge: 0, rThr: 1.5, rHold: 3, rCost: 1, bThr: 3, bK: 5, bHold: 3, bUni: "second" });
  for (const [s, si] of sigs) {
    S.theme = s.theme;
    for (const tk of D.themes[s.theme].tickers.slice(0, 4)) {
      for (const t of trades(s, tk)) if (t.i <= K) out.lag.push([si, tk, t.i, t.e, t.want, t.x]);
      for (const t of revTrades(s, tk)) if (t.i <= K) out.rev.push([si, tk, t.i, t.yes, +t.pe.toFixed(4)]);
      for (const h of hedgeRun(s, tk, 60)) if (h.i <= K) out.hedge.push([si, tk, h.i, +h.beta.toFixed(8)]);
    }
  }
  for (const [s, si] of sigs.slice(0, 12)) for (const b of basketTrades(s)) if (b.i <= K) out.basket.push([si, b.i, b.legs.map((l) => l.tk + l.want).join(",")]);
  // canary: a deliberately leaky rule that peeks at the next day's close. It MUST change, or the scramble did nothing.
  for (const [s, si] of sigs.slice(0, 5)) for (let i = K - 3; i <= K; i++) { const c = D.px.SPY.c; if (c[i + 1] != null && c[i] != null) out.canary = (out.canary || []).concat([[i, c[i + 1]]]); }
  for (const t of T.targets) for (let k = 0; k < t.p.length; k++) { const i = t.s + k; if (i <= K && i % 7 === 0) { const m = model(t, i); if (m != null) out.options.push([t.id, i, +m.toFixed(8)]); } }
  return out;
}
const before = decisions(); scrambleAfter(K); const after = decisions(); restore();
for (const k in before) results[k] = { n: before[k].length, same: JSON.stringify(before[k]) === JSON.stringify(after[k]) };
console.log(JSON.stringify(results));
