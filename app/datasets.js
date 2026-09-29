// What you can bet on in each dataset: the moments you can bet at, the sides you can pick,
// and the columns you can filter or compare by. `at` = the moment a column becomes known
// (0 = before the game, higher = later moments, 9 = only after the game is over).
(function () {
  const D = window.EDGE_DATA;
  const table = (t) => t.rows.map((r) => Object.fromEntries(t.cols.map((c, i) => [c, r[i]])));
  const bump = (p) => (p == null ? null : Math.min(0.99, p + 0.01));   // midpoint -> estimated ask

  // ---------------------------------------------------------------- tennis
  const tennis = table(D.tennis);
  const tennisCols = [
    { key: "date", label: "Date", type: "date", at: 0 },
    { key: "tour", label: "Tournament", type: "cat", at: 0 },
    { key: "rnd", label: "Round", type: "cat", at: 0 },
    { key: "bo5", label: "Best-of-5 (Grand Slam main draw)", type: "bool", at: 0 },
    { key: "s1w_pre", label: "Set-1 winner's price before the match", type: "num", at: 0, pct: true },
    { key: "s1w_fav", label: "Set-1 winner was the pre-match favorite", type: "bool", at: 0 },
    { key: "s1w_ask", label: "Set-1 winner's price after set 1 (ask)", type: "num", at: 1, pct: true },
    { key: "jump", label: "Price jump for the set-1 winner (pts)", type: "num", at: 1, pct: true },
    { key: "set1_min", label: "Set 1 length (minutes, estimated)", type: "num", at: 1 },
    { key: "s1w_set2", label: "Set-1 winner also won set 2", type: "bool", at: 9 },
    { key: "deciding_set", label: "Went to a deciding 3rd set", type: "bool", at: 9 },
    { key: "set2_min", label: "Set 2 length (minutes)", type: "num", at: 9 },
    { key: "set3_min", label: "Set 3 length (minutes)", type: "num", at: 9 },
    { key: "match_min", label: "Match length (minutes, estimated)", type: "num", at: 9 },
  ];
  function tennisBet(r, moment, side) {
    const s1w = side === "s1w" || (side === "fav" && r.s1w_fav) || (side === "dog" && r.s1w_fav === false);
    if ((side === "fav" || side === "dog") && r.s1w_fav == null) return null;
    let p;
    if (moment === "pre") p = s1w ? bump(r.s1w_pre) : bump(r.s1w_pre == null ? null : 1 - r.s1w_pre);
    else p = s1w ? r.s1w_ask : 1 - r.s1w_bid;
    const name = s1w ? r.s1w : r.match.split(" vs ")[1];
    return { p, won: s1w ? r.won : !r.won, pick: name };
  }

  // ---------------------------------------------------------------- NBA games
  const games = table(D.nba_games).map((r) => {
    const favHome = r.home_pre >= 0.5;
    const o = Object.assign({}, r, {
      fav: favHome ? r.home : r.away,
      home_b2b: r.home_rest === 1, away_b2b: r.away_rest === 1,
      b2b_edge: r.home_rest === 1 && r.away_rest > 1 ? "Home tired" : r.away_rest === 1 && r.home_rest > 1 ? "Away tired" : "Neither / both",
      fav_pre: favHome ? r.home_pre : 1 - r.home_pre,
    });
    for (const m of ["q1", "h", "q3"]) {
      if (r[m + "_margin"] == null) continue;
      o["fav_" + m] = favHome ? r[m + "_margin"] : -r[m + "_margin"];
      o["lead_" + m] = Math.abs(r[m + "_margin"]);
    }
    o.fav_final = favHome ? r.final_margin : -r.final_margin;
    o.threes_diff_1h = r.home_3pa_1h - r.away_3pa_1h;
    return o;
  });
  const gameCols = [
    { key: "date", label: "Date", type: "date", at: 0 },
    { key: "stage", label: "Season stage", type: "cat", at: 0 },
    { key: "home", label: "Home team", type: "cat", at: 0 },
    { key: "away", label: "Away team", type: "cat", at: 0 },
    { key: "fav", label: "Pre-game favorite", type: "cat", at: 0 },
    { key: "fav_pre", label: "Favorite's price before tip-off", type: "num", at: 0, pct: true },
    { key: "home_pre", label: "Home team's price before tip-off", type: "num", at: 0, pct: true },
    { key: "home_rest", label: "Home team days of rest", type: "num", at: 0 },
    { key: "away_rest", label: "Away team days of rest", type: "num", at: 0 },
    { key: "b2b_edge", label: "Back-to-back (tired team)", type: "cat", at: 0 },
    { key: "fav_q1", label: "Favorite's lead after Q1", type: "num", at: 1 },
    { key: "lead_q1", label: "Size of the lead after Q1", type: "num", at: 1 },
    { key: "fav_h", label: "Favorite's lead at halftime", type: "num", at: 2 },
    { key: "lead_h", label: "Size of the lead at halftime", type: "num", at: 2 },
    { key: "home_3pa_1h", label: "Home 3-point attempts, 1st half", type: "num", at: 2 },
    { key: "away_3pa_1h", label: "Away 3-point attempts, 1st half", type: "num", at: 2 },
    { key: "threes_diff_1h", label: "Home minus away 3PA, 1st half", type: "num", at: 2 },
    { key: "fav_q3", label: "Favorite's lead after Q3", type: "num", at: 3 },
    { key: "lead_q3", label: "Size of the lead after Q3", type: "num", at: 3 },
    { key: "fav_final", label: "Favorite's final margin", type: "num", at: 9 },
  ];
  const gm = { pre: 0, q1: 1, h: 2, q3: 3 };
  function gameBet(r, moment, side) {
    const ask = moment === "pre" ? [r.pre_home_ask, r.pre_away_ask] : [r[moment + "_home_ask"], r[moment + "_away_ask"]];
    const margin = moment === "pre" ? 0 : r[moment + "_margin"];
    if (ask[0] == null || margin == null) return null;
    let home;
    if (side === "home") home = true;
    else if (side === "away") home = false;
    else if (side === "fav" || side === "dog") home = (r.home_pre >= 0.5) === (side === "fav");
    else { if (margin === 0) return null; home = (margin > 0) === (side === "leader"); }
    return { p: home ? ask[0] : ask[1], won: home ? r.home_won : !r.home_won, pick: home ? r.home : r.away };
  }

  // ---------------------------------------------------------------- NBA swings
  const swings = table(D.nba_swings).map((r) => Object.assign({}, r, {
    half: r.period <= 2 ? "1st half" : "2nd half",
    more_threes: r.tpa_10 > r.opp_tpa_10,
  }));
  const swingCols = [
    { key: "date", label: "Date", type: "date", at: 0 },
    { key: "stage", label: "Season stage", type: "cat", at: 0 },
    { key: "trailer", label: "Trailing team", type: "cat", at: 1 },
    { key: "trailer_was_fav", label: "Trailing team was the pre-game favorite", type: "bool", at: 1 },
    { key: "trailer_home", label: "Trailing team is at home", type: "bool", at: 1 },
    { key: "period", label: "Quarter it happened (5+ = OT)", type: "num", at: 1 },
    { key: "half", label: "Half it happened", type: "cat", at: 1 },
    { key: "trail_ask", label: "Trailing team's price", type: "num", at: 1, pct: true },
    { key: "lead_ask", label: "Leading team's price", type: "num", at: 1, pct: true },
    { key: "tpa_10", label: "Trailer's 3PA, last 10 min", type: "num", at: 1 },
    { key: "tpm_10", label: "Trailer's 3PM, last 10 min", type: "num", at: 1 },
    { key: "opp_tpa_10", label: "Leader's 3PA, last 10 min", type: "num", at: 1 },
    { key: "more_threes", label: "Trailer shooting more threes than leader (last 10 min)", type: "bool", at: 1 },
    { key: "game_3pa", label: "Trailer's 3PA so far this game", type: "num", at: 1 },
    { key: "game_3pct", label: "Trailer's 3P% so far this game", type: "num", at: 1, pct: true },
  ];
  function swingBet(r, moment, side) {
    if (r.deficit !== +moment.slice(1)) return null;
    const trail = side === "trailer";
    return { p: trail ? r.trail_ask : r.lead_ask, won: trail ? r.trail_won : !r.trail_won,
             pick: trail ? r.trailer : r.match.replace(r.trailer, "").replace(" @ ", "").trim() };
  }

  window.DATASETS = {
    tennis: {
      label: "Tennis · ATP", unit: "matches", rows: tennis, cols: tennisCols, bet: tennisBet,
      moments: [{ id: "s1", label: "Right after set 1", phrase: "right after set 1", at: 1 }, { id: "pre", label: "Before the match (estimated price)", phrase: "before the match", at: 0 }],
      sides: [{ id: "s1w", label: "The set-1 winner" }, { id: "s1l", label: "The set-1 loser" },
              { id: "fav", label: "The pre-match favorite" }, { id: "dog", label: "The pre-match underdog" }],
      defaultX: "set1_min",
    },
    nba: {
      label: "NBA · games", unit: "games", rows: games, cols: gameCols, bet: gameBet,
      moments: [{ id: "pre", label: "Before tip-off", phrase: "before tip-off", at: 0 }, { id: "q1", label: "End of Q1", phrase: "at the end of Q1", at: 1 },
                { id: "h", label: "Halftime", phrase: "at halftime", at: 2 }, { id: "q3", label: "End of Q3", phrase: "at the end of Q3", at: 3 }],
      sides: [{ id: "fav", label: "The pre-game favorite" }, { id: "dog", label: "The pre-game underdog" },
              { id: "home", label: "The home team" }, { id: "away", label: "The away team" },
              { id: "leader", label: "Whoever is leading" }, { id: "trailer", label: "Whoever is trailing" }],
      momentAt: gm, defaultX: "fav_pre",
    },
    swings: {
      label: "NBA · big deficits", unit: "moments", rows: swings, cols: swingCols, bet: swingBet,
      moments: [{ id: "d10", label: "First time a team is down 10", phrase: "the first time a team falls 10 behind", at: 1 }, { id: "d15", label: "First time a team is down 15", phrase: "the first time a team falls 15 behind", at: 1 },
                { id: "d20", label: "First time a team is down 20", phrase: "the first time a team falls 20 behind", at: 1 }],
      sides: [{ id: "trailer", label: "The trailing team (comeback)" }, { id: "leader", label: "The leading team" }],
      defaultX: "tpa_10",
    },
  };

  // Settings from the original Colab + Claude research, with that run's results for comparison.
  const T = (label, side, extra, orig) => Object.assign({ ds: "tennis", moment: "s1", side, label, orig }, extra,
    { filters: [{ key: "bo5", val: false }].concat(extra.filters || []) });
  window.PRESETS = [
    T("Bet every set-1 winner", "s1w", {}, "1,295 bets, 76.6% won, −5.2%"),
    T("Bet set-1 winner at −400 or shorter", "s1w", { pmin: 80 }, "749 bets, 88.0% won, −2.7%"),
    T("Bet set-1 winner at −900 or shorter", "s1w", { pmin: 90 }, "398 bets, 93.0% won, −1.4%"),
    T("Bet against every set-1 winner", "s1l", {}, "1,295 bets, 23.4% won, +0.1%"),
    T("Bet against set-1 winner at −233 to −400", "s1l", { filters: [{ key: "s1w_ask", min: 0.70, max: 0.799 }] }, "240 bets, 32.5% won, +15.3%"),
    T("Bet against set-1 winner at −233 to −900: Jul–Sep", "s1l", { from: "2026-07-22", filters: [{ key: "s1w_ask", min: 0.70, max: 0.899 }] }, "199 bets, 29.6% won, +38.3% (where the pattern was found)"),
    T("Bet against set-1 winner at −233 to −900: Jan–Jul", "s1l", { to: "2026-07-21", filters: [{ key: "s1w_ask", min: 0.70, max: 0.899 }] }, "392 bets, 20.7% won, −9.2% (the out-of-sample test)"),
    { ds: "nba", label: "Playoffs: bet the underdog", moment: "pre", side: "dog", filters: [{ key: "stage", val: "Playoffs" }], orig: "66 bets, 42.4% won, +25.4%" },
    { ds: "nba", label: "Playoffs: bet the favorite", moment: "pre", side: "fav", filters: [{ key: "stage", val: "Playoffs" }], orig: "66 bets, 57.6% won, −17.5%" },
    { ds: "nba", label: "Bet every pre-game favorite", moment: "pre", side: "fav", filters: [], orig: "1,020 bets, 68.4% won, −4.7%" },
    { ds: "nba", label: "Favorite down 10+ at halftime: bet the favorite", moment: "h", side: "fav", filters: [{ key: "fav_h", max: -10 }], orig: "132 bets, 25.8% won, +14.9%" },
    { ds: "nba", label: "Favorite trailing at halftime: bet the favorite", moment: "h", side: "fav", filters: [{ key: "fav_h", max: -1 }], orig: "369 bets, 42.3% won, 0.0%" },
    { ds: "nba", label: "Bet the leader up 16+ after Q1", moment: "q1", side: "leader", filters: [{ key: "lead_q1", min: 16 }], orig: "68 bets, 91.2% won, +0.9%" },
    { ds: "nba", label: "Bet the leader up 16+ after Q3", moment: "q3", side: "leader", filters: [{ key: "lead_q3", min: 16 }], orig: "137 bets, 97.8% won, +0.6%" },
    { ds: "swings", label: "Bet the team down 15+", moment: "d15", side: "trailer", filters: [], orig: "763 bets, 11.7% won, −37.2%" },
    { ds: "swings", label: "Bet the team down 20+", moment: "d20", side: "trailer", filters: [], orig: "487 bets, 3.9% won, −37.9%" },
    { ds: "swings", label: "Down 20+ in the 1st half", moment: "d20", side: "trailer", filters: [{ key: "period", max: 2 }], orig: "208 bets, 7.2% won, −62.5%" },
    { ds: "swings", label: "Down 20+ in the 2nd half", moment: "d20", side: "trailer", filters: [{ key: "period", min: 3 }], orig: "279 bets, 1.4% won, −19.6%" },
    { ds: "swings", label: "Down 20+, took 4+ threes in last 10 min", moment: "d20", side: "trailer", filters: [{ key: "tpa_10", min: 4 }], orig: "126 bets, 4.8% won, −80.5%" },
    { ds: "swings", label: "Bet the leader when the trailer is +900 to +3200", moment: "d20", side: "leader", filters: [{ key: "trail_ask", min: 0.03, max: 0.10 }], orig: "223 bets, 98.2% won, +3.3% (priced at the leader's bid, not ask)" },
  ];
})();
