# Leakage audit

A backtest leaks when a decision uses information that would not have been available at the moment the bet or trade was placed. Leaks make strategies look better than they are, so every page and script in this project was checked for them. This page lists what was checked, what was wrong, how it was fixed, and which automated test now guards it.

## The rule every strategy follows

1. A decision at time *t* may use only prices, scores and schedule information timestamped at or before *t*.
2. The bet or trade fills **after** *t*: in sports, at the ask of the first live quote 1–3 samples (1–6 minutes) later; for stocks, at the next day's open.
3. Anything chosen by looking at results (a threshold, a rule, a model) is judged on games or days it was not chosen on.

## What was wrong, and what changed

| # | Where | The leak | Fix | Guarded by |
|---|---|---|---|---|
| 1 | Tennis and UFC start times (`scripts/pull_sports.py`) | The start was taken as the first minute whose trading volume reached 25% of the match's **peak** volume. The peak is only known afterwards. Checked against the true end of set 1, 5 of 60 sample ATP matches had a "start" *after* set 1 had ended. | A causal detector: the first minute (no earlier than 10 minutes before the scheduled time) when the price has moved in 5 of the last 10 minutes (UFC: 3 of 10, or a volume burst of 3,000+ contracts at 6× the previous hour's pace). It uses only candles up to that minute. On the same 60 matches, 56 now start 20–80 minutes before set 1 ends and none after. "Just before the start" for these sports is the first price after the start is detected; "1 hour" and "24 hours" before are measured from the published schedule. ATP, WTA and UFC were re-pulled. | `detect_start` docstring; re-pull |
| 2 | Games with no published start time | If Kalshi had no schedule for a game, the start was set from the market's **close** time, which is only known after the game. | Such games are dropped (about 7 of 16,834). | `pull_sports.py` build step |
| 3 | In-game fills (`app/paths.js`, `analysis/engine.py`) | When the order book emptied (bid 0, ask 100), the last real quote was carried forward, and a bet could **fill** at that stale price, sometimes after the result was effectively known. | Carried-forward quotes are still used to *see* a trigger, but a bet fills only at a live two-sided quote, within 3 samples of the trigger, or not at all. Early exits sell only into a live bid. | `test_no_fill_at_an_empty_book`, browser/Python parity test |
| 4 | Bets placed 1 hour or 24 hours early | "Favorite" was decided from the line 5 minutes before the start. | The favorite is the favorite at the moment of the bet. Conditions that depend on the closing line are not offered for early bets. | `test_early_bet_uses_the_favorite_at_that_moment`, `test_an_hour_out_ignores_the_closing_line` |
| 5 | Options vs Kalshi, bitcoin and ether (`scripts/pull_targets.py`) | Yahoo stamps crypto daily bars at 00:00 UTC, the previous evening in New York, so each close was filed **a day early**. The model priced Kalshi with a crypto price from ~19 hours later. | Crypto bars are filed by their UTC date, so day D's close (7–8pm New York) is always before Kalshi's midnight price for D. | markets harness: `test_options_model` |
| 6 | Hourly shocks (`scripts/pull_stocks.py`) | Jumps that reversed within the next 2 hours were thrown out, and each market's biggest jumps over its whole life were chosen. Both use what happened afterwards. | Every one-hour jump of 6+ points is kept, in time order, at least 3 days apart. | build code |
| 7 | "Stock first, then Kalshi" (`app/strategies.js`) | The stock's move to the 4pm close was the signal, and the contract was bought at its 4pm price: the same instant. | The contract is bought and sold at its 5pm price, an hour after the signal. | `test_stock_first_then_kalshi` |
| 8 | Lag trade entry (`app/stocks.js`) | "Buy at that day's close" traded at 4pm on a signal read at 4pm. | Removed. The choices are the next day's open or the open two days later. | `test_lag_trade` |
| 9 | Merger spread default (`app/strategies.js`) | The default offer was $31, the price the stock ended at. | The default is Paramount's $30 tender, the figure public when the Kalshi market opened. | — |

## How the tests check for leaks

The strongest test for a leak is to **change the future and see if the past changes**. The suite does this everywhere a strategy makes decisions:

- **Sports engine** (`tests/test_engine.py`): 300 random price paths × 6 rule types. Every price after each fill is rewritten and the result flipped; the bet's timing, side and price must not change (500+ bets checked).
- **Machine search** (`tests/test_evolve.py`): in 125 real games, every quote after a random moment is scrambled and the result flipped; every decision point up to that moment (its features and the price paid) must be identical. The "1 hour before" decision point is checked against changes to the closing line, volume and favorite.
- **Markets pages** (`tests/test_markets.py` → `tests/markets_harness.js`): runs the real `stocks.js` and `strategies.js` in Node, computes every lag trade, stock-first trade, basket, hedge size and options-model price, scrambles every stock, Kalshi, index and volatility price after a cutoff day, and recomputes. All 25,000+ decisions up to the cutoff must match. A **canary**, a deliberately leaky rule that peeks one day ahead, must change, proving the scramble reached the future.
- **Time splits** (`tests/test_evolve.py`): the search, validation and test periods are in date order, and rule thresholds are quantiles of the search period alone.
- **Two engines, one answer**: the browser engine (`app/paths.js`, run in Node) and the Python engine (`analysis/engine.py`) must produce the same bets and the same profit on the NFL file.

## Known limits (disclosed, not leaks in a trade)

- **Which markets are studied.** The stocks lab includes Kalshi markets with at least 20,000 contracts traded over their life and a price range of 4+ points. A trader in the past couldn't have known which markets would become busy. This affects which questions are asked, not whether a decision peeks.
- **Which stocks belong to a theme** (for example, defense stocks for a shutdown) reflects judgment made today.
- **Descriptive views use the whole sample**, and say so: *Find a link*, *Strongest links*, *Who moves first*, the hedge ranking, and the "hidden dependencies" table describe the past. Only the strategy backtests are walk-forward.
- **The original case studies** keep their original method so the published numbers reproduce. Their tennis "before the match" price used the volume-peak start time from leak #1; it is labelled *estimated* on the page.
