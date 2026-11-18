# Do popular sports-betting trends beat Kalshi's prediction markets?

**Author:** Adi Amlani, University of Florida (Finance & Mathematics)

**[Try the live tool](https://adiamlani130.github.io/KalshiArbitrageBettor/)** · **[Run the analysis in Colab](https://colab.research.google.com/github/adiamlani130/KalshiArbitrageBettor/blob/main/colab/run_in_colab.ipynb)** (no setup, about a minute)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/adiamlani130/KalshiArbitrageBettor/blob/main/colab/run_in_colab.ipynb)

This project tests well-known sports "trends" against real Kalshi prediction-market prices to see whether any of them could actually make money. Every strategy assumes **$10 per bet**, bought at the real asking price at that moment, with **Kalshi's trading fee subtracted**.

**Short answer:** no simple rule reliably beats the market after fees. The one pattern that shows up everywhere is the **favorite-longshot bias**: long shots (big comebacks, big underdogs) are overpriced, while heavy favorites are priced about right.

**Try it yourself:** the [Kalshi Edge Lab](https://adiamlani130.github.io/KalshiArbitrageBettor/) runs in the browser with nothing to install.

| Page | What it's for |
|---|---|
| [Home](https://adiamlani130.github.io/KalshiArbitrageBettor/app/) | What the lab is, real games replayed price by price, and the headline results |
| [Strategy builder](https://adiamlani130.github.io/KalshiArbitrageBettor/app/sports.html) | Build and test any betting rule on 16,930 games across 14 leagues. Every strategy is a shareable link; save strategies and compare them side by side; sweep a threshold to check it isn't luck |
| [Case studies](https://adiamlani130.github.io/KalshiArbitrageBettor/app/research.html) | The three original studies (tennis set 1, NBA halftime favorites, NBA comebacks) with real scores, ready to load and tweak |
| [Markets vs stocks](https://adiamlani130.github.io/KalshiArbitrageBettor/app/stocks.html) | 336 Kalshi markets against 242 stocks and ETFs: who moves first, lag trades, hourly shocks, announcements, earnings calls |
| [Strategies & hedging](https://adiamlani130.github.io/KalshiArbitrageBettor/app/strategies.html) | Kalshi vs options-implied odds, merger spreads, second-order baskets, hedging a stock with a contract |
| [Strategy search](https://adiamlani130.github.io/KalshiArbitrageBettor/app/findings.html) | What survived when a genetic algorithm, NEAT neural networks, a gradient-boosted model and a grid search hunted for strategies, judged on games they never saw |

## Key results

Numbers below use the full data pull (`data/`). The first run in Colab pulled fewer matches because of a bug in reading Kalshi's archive; those original numbers are reproduced exactly from `data/original_run/` and compared side by side in [docs/VERIFICATION.md](docs/VERIFICATION.md).

### Tennis (ATP, Jan–Sep 2026, best-of-3 matches)

A well-known stat says the ATP player who wins set 1 of a best-of-3 match wins about 88% of the time (1991–2020). On Kalshi in 2026, set-1 winners won **78.9%**, and the market had already priced that in.

| Strategy | Bets | Bets won | Typical odds | Net | Return |
|---|---:|---:|---:|---:|---:|
| Bet every set-1 winner | 2,145 | 78.9% | −488 | −$474 | −2.2% |
| Bet set-1 winner at −400 or shorter | 1,271 | 89.4% | −900 | −$92 | −0.7% |
| Bet set-1 winner at −900 or shorter | 636 | 94.0% | −1567 | −$15 | −0.2% |
| Bet against every set-1 winner | 2,145 | 21.1% | +456 | −$2,642 | −12.3% |
| Bet against set-1 winner at −233 to −900, **Jul–Sep** (where it was found) | 308 | 26.0% | +400 | +$689 | +22.4% |
| Same rule on **Jan–Jul** matches it was never fitted to | 706 | 18.1% | +426 | −$1,311 | −18.6% |
| Bet against set-1 winner at −233 to −400 | 379 | 29.3% | +270 | +$146 | +3.9% |

The "bet against the set-1 winner" edge is the main methods lesson. It made money only in the months where it was found, and lost 18.6% on the earlier months. On the first, smaller pull the narrower −233 to −400 version showed +15.3% on 240 bets. With the complete data it's +3.9% on 379 bets, which is well within luck.

### NBA (2025–26 season, 1,316 games)

| Strategy | Bets | Bets won | Typical odds | Net | Return |
|---|---:|---:|---:|---:|---:|
| Bet team down 15+ | 975 | 11.5% | +1011 | −$3,791 | −38.9% |
| Bet team down 20+ | 624 | 3.7% | +2400 | −$2,991 | −47.9% |
| Down 20+, took 4+ threes in the last 10 min | 170 | 4.1% | +2400 | −$1,441 | −84.7% |
| Bet leader when trailer is +900 to +3200 | 293 | 98.3% | −1900 | +$100 | +3.4%* |
| Pre-game favorite down 10+ at halftime: bet favorite | 161 | 26.1% | +300 | +$153 | +9.5% |
| Favorite trailing at halftime: bet favorite | 465 | 43.4% | +122 | −$50 | −1.1% |
| Bet every pre-game favorite | 1,307 | 69.0% | −223 | −$554 | −4.2% |
| Playoffs: bet the underdog | 77 | 41.6% | +203 | +$183 | +23.8% |

\* The analysis script prices the leader at its bid. Buying at the real ask, as the Edge Lab does, gives **+2.2%**.

The two positive NBA results have small samples: 161 and 77 bets. The Edge Lab's "likely range" for each includes zero, so neither is proven.

Full tables (35+ strategies, including back-to-backs, runs and line movement) are in `results/`.

- **Strategies & hedging.** Six less obvious tests: Kalshi against options-implied odds, a merger spread against Kalshi's deal odds, baskets of second-order stocks, hedging a stock with a contract, trading the contract after the stock moves, and betting the ladder before macro news.

- **Findings.** What is left after a computer tries 1,630 betting rules and 2,621 market-stock pairs, finding each on one period and testing it once on a later one.

## What survived out of sample

`analysis/discover.py` splits every league's games by date (first 60% to search, last 40% held back), searches a fixed grid of rules, and tests the ones that look profitable once on the held-back games with a 10% false-discovery rate.

| | Tried | Looked good in the search period | Held up on held-back data |
|---|---:|---:|---:|
| Sports betting rules (16,930 games) | 1,630 | 11 (luck alone gives about 37) | 1 |
| Rules that lose in both periods | 1,630 | | 167 |
| Kalshi and a stock moving on the same day | 2,621 | 190 (luck: 7) | 136 |
| Kalshi leading the stock by a day | 2,621 | 15 | 0 |
| The stock leading Kalshi by a day | 2,606 | 13 | 0 |

- **No rule is a reliable winner.** The one survivor is narrow: in WTA matches that start close (favorite at 50–60¢), buying whoever is ahead on price 30 minutes in returned +8.7% in the search period and +13.5% on 177 held-back matches. One survivor out of 1,630 tries is a lead to keep watching, not a strategy.
- **Losing is repeatable.** Backing whoever is behind an hour in lost 17.5% and then 19.9% across all 14 leagues (5,735 held-back bets). Long shots are overpriced in every sport.
- **Prediction markets and stocks move together, and neither leads.** Same-day links replicate; next-day leads in either direction do not.
- **The sweep caught a bug.** Its first run showed tennis favorites bought an hour early earning 10–15%. That was look-ahead: "favorite" was being decided from the closing line. Early bets now use the favorite at the time of the bet, and a test guards it.

## What you can test

### Sports: strategy builder and case studies

The *strategy builder* uses the all-sports price paths; the *case studies* page holds the three original datasets with real scores.

| | Tennis · ATP | NBA · games | NBA · big deficits | All sports · price paths |
|---|---|---|---|---|
| Data | Set results + prices | ESPN scores + prices | ESPN scores + prices | Prices only, every 1–2 minutes |
| Leagues | ATP | NBA | NBA | 14 leagues |
| When you can bet | Before the match, after set 1 | Before tip-off, end of Q1, halftime, end of Q3 | First time down 10, 15 or 20 | Before the start (5 min, 1 hour, 24 hours), any minute of the game, or on a price trigger |

Price triggers in *All sports* are things like "the first time the favorite falls to 30¢", "the first time either team reaches 90¢", "a team drops 15¢ within 10 minutes" or "a team is 20¢ off its in-game high". You choose the team to watch, the threshold and who to bet on (the team that triggered it, or the other one).

You can then add conditions (league, day of week, start hour, pre-game price, how the line moved in the last hour or day, pre-game volume, minutes into the game, how far the pick is off its high, lead changes so far, and more) and optionally **get out early**: sell at a target, at a stop, or after a set time, instead of holding to the result.

Four tabs read the same bets:

- **Test a bet** - profit, win rate, a likely range, and whether it held in both halves of the sample. For trigger rules, one click reruns the strategy at every nearby threshold, so you can tell a smooth edge from a lucky spike.
- **Find a link** - win rate against the price-implied chance, split by any column.
- **Strongest links** - splits the bet by every condition you could have known in time, ranks the groups, and says how many would look that strong by luck.
- **My strategies** - save strategies in your browser and compare them side by side on the same games.

Every strategy lives in the page's link, so copying the address (or the *Copy link* button) shares exactly what you built.

### Markets vs stocks

| Tab | Question it answers |
|---|---|
| Who moves first | Does Kalshi's daily change line up with the stock's move on the same day, on later days (Kalshi leads) or on earlier days (the stock leads)? |
| Lag trade | If Kalshi moves X points and the stock hasn't moved yet, does buying (or shorting) the stock at the next open make money after costs? |
| Hourly shocks | After Kalshi's biggest one-hour jumps, what had the stock already done, and what was left by the first price you could trade? |
| Announcements | For Fed, CPI, jobs, GDP and unemployment releases: how big was the surprise against Kalshi's price the evening before, and how did the stock react that day and after? |
| Strongest pairs | Ranks every market-stock pair by how strongly one leads the other, and says how many would pass by luck. |
| Paper trade | Turns the current lag-trade rule into a settings file for `scripts/alpaca_paper.py`, which places the trade in an Alpaca paper account. |

### Strategies & hedging

| Tab | Idea | What the data said |
|---|---|---|
| Options vs Kalshi | A Kalshi price target is a binary option. Price it from the underlying and its volatility index (VIX, VXN, OVX), and bet against Kalshi when the two disagree. | Kalshi was the better forecaster on all five underlyings, so most gaps were the model's error, not an arbitrage. |
| Merger spread | A target's discount to the offer implies a chance the deal closes. Compare it with Kalshi's takeover market, buy the stock when Kalshi is more confident, hedge with "No". | Paramount / Warner Bros: Kalshi and the stock stayed within a few points of each other. One deal, so a case study only. |
| Second-order basket | When a market moves, trade the stocks *outside* the obvious list that have tracked it most closely so far. | Small samples, negative after costs on the markets tried. |
| Hedge a stock | Size a Kalshi position against a stock each day from past data only, and measure how much of the stock's swings it removes. Ranks every market as a hedge. | Works for close matches (S&P targets remove up to ~58% of SPY's daily variance); policy markets remove little. |
| Stock first, then Kalshi | Stocks lead Kalshi more often than the reverse, so buy the contract after the stock moves. | Loses after the fee and a 1¢ spread each way. |
| Bets before the news | Buy macro-release markets the evening before. | Long shots under 25¢ lost 48%; favorites lost 6%. The favorite-longshot bias again. |

`scripts/options_binary.py` does the real call-spread calculation on a live Alpaca options chain and compares it with a Kalshi market. It is read-only and has not been run against a live account here.

Kalshi probabilities are read at 4:00pm New York time, the stock close, so "trade at the next open" uses a price you could really have got.

## How it was done

1. **Data (`colab/`, `scripts/pull_data.py`).** Kalshi's free public API gave minute-by-minute prices for ATP match markets (`KXATPMATCH`), set-winner markets (`KXATPSETWINNER`) and NBA game markets (`KXNBAGAME`). ESPN's public API gave NBA play-by-play with real-world timestamps.
2. **Timing.** In tennis, the "set 1 winner" market closes when set 1 ends, which gives an exact timestamp. In the NBA, each play's timestamp was matched to the Kalshi price at that minute. Bets are placed at the ask 1–5 minutes after the event, to be realistic about reaction time.
3. **Testing.** Each strategy is reported for the full sample and for each half of the season separately. A pattern that only works in one half is treated as likely luck.
4. **Verification.** Every number from the original Colab + Claude research was re-run from its saved data and matches exactly. The data was then pulled again from scratch and re-run ([docs/VERIFICATION.md](docs/VERIFICATION.md)).

## Reproduce it

```bash
pip install -r requirements.txt
python analysis/tennis_analysis.py
python analysis/nba_build.py
python analysis/nba_analysis.py
```

Add `data/original_run results/original_run` to each command to reproduce the original Colab numbers instead. To pull fresh data (about 45 minutes, no API key needed), run `python scripts/pull_data.py`, then `python app/build_data.py` to rebuild the Edge Lab's data.

To open the Edge Lab locally, run `python -m http.server --directory app` and go to http://localhost:8000.

To refresh the newer data and rerun every search (no API keys needed), in this order:

```bash
pip install numpy scikit-learn neat-python
python scripts/pull_sports.py     # 14 leagues of in-game price paths from Kalshi (1-2 hours, resumable)
python scripts/pull_stocks.py     # Kalshi probabilities + Yahoo Finance prices (about 15 minutes)
python scripts/pull_targets.py    # price-target markets + volatility indexes for the Strategies page
python analysis/discover.py       # grid search with a held-back test (about 30 seconds)
python analysis/evolve.py         # genetic algorithm, NEAT and gradient boosting (about 15 minutes)
python scripts/build_home.py      # homepage data
```

### Paper trading the lag trade

`scripts/alpaca_paper.py` runs one lag-trade rule on live prices with an [Alpaca](https://alpaca.markets) **paper** account (fake money). Build the rule in the lab's *Paper trade* tab, download `signal.json`, then:

```bash
export ALPACA_KEY=your_paper_key ALPACA_SECRET=your_paper_secret
python scripts/alpaca_paper.py signal.json            # dry run: shows what it would do
python scripts/alpaca_paper.py signal.json --trade    # places the paper order
```

It reads Kalshi's live probability, checks whether it moved enough while the stock hasn't, places the order, and closes the position after the holding period the next time you run it. It only talks to Alpaca's paper endpoint. It has been checked against live Kalshi data but not against an Alpaca account, so start with the dry run.

## Changing things

| To... | Edit |
|---|---|
| Add or rename a page in the menu | `PAGES` at the top of `app/nav.js` |
| Add an example strategy to the builder | `window.PRESETS.push(...)` at the bottom of `app/paths.js` (case studies: `app/datasets.js`) |
| Add a condition you can filter on | `cols` in `app/paths.js`: a column with `at: -1` is known before the game, `0` at the start, `1` in-game, `9` only afterwards (shown in *Find a link*, never usable as a condition) |
| Add a new kind of bet timing | `MOMENTS` and `find()` in `app/paths.js`, and the same in `analysis/engine.py` (a test checks the two agree) |
| Add a league | `LEAGUES` in `scripts/pull_sports.py`, then `python scripts/pull_sports.py <league>` |
| Add a Kalshi theme or stocks | `THEMES` in `scripts/pull_stocks.py`, then rerun it |
| Change what the machine search tries | `WINDOWS`, `COND_FEATS` and the island sizes in `analysis/evolve.py` |
| Change colors or fonts | the variables at the top of `app/style.css` (light and dark) |

After any change, run `python -m unittest discover tests`; the leakage tests will fail if a new rule or column looks at the future.

## Tests

```bash
pip install numpy
python -m unittest discover tests
```

28 checks run on every push (GitHub Actions). The most important ones look for **leakage**, a strategy using information it couldn't have had yet. They change the future and confirm the past doesn't change:

- **Sports engine:** 500+ bets on random price paths; every price after the fill is rewritten and the result flipped, and no bet may change.
- **Machine search:** 125 real games; every quote after a random moment is scrambled, and every decision point up to that moment must stay identical.
- **Markets pages:** the real `stocks.js` and `strategies.js` run in Node. Every price after a cutoff day is scrambled, and 25,000+ lag trades, stock-first trades, baskets, hedges and options prices must not change. A deliberately leaky canary rule must change, proving the test can see a leak.

The rest cover the fee and profit math, trigger rules, empty order books, the time splits, the false-discovery correction, the published data (files load, final prices agree with results, in-game prices are calibrated), and the browser and Python engines giving the same bets and profit. [docs/LEAKAGE.md](docs/LEAKAGE.md) lists every leak found and fixed.

## Repo layout

- `app/` - the Kalshi Edge Lab website
  - `index.html` (home), `sports.html` (strategy builder), `research.html` (case studies), `stocks.html` (markets vs stocks), `strategies.html` (strategies & hedging), `findings.html` (strategy search)
  - `nav.js` (the one navigation bar; add a page there), `lab.js` (the sports engine and UI), `paths.js` (the 14-league dataset), `datasets.js` (the case-study datasets), `stocks.js`, `strategies.js`, `style.css`
  - `data/` - league price paths (loaded on demand), stocks and target-market data, search results, homepage data
  - `build_data.py` - builds the case-study score data
- `analysis/` - `engine.py` (the sports engine in Python), `discover.py` (grid search, held-back test), `evolve.py` (genetic algorithm, NEAT, gradient boosting), and the original study scripts; `common.py` holds the bet and fee math
- `scripts/` - data pulls (`pull_sports.py`, `pull_stocks.py`, `pull_targets.py`, `pull_data.py`), `build_home.py`, and the Alpaca scripts (`alpaca_paper.py`, `options_binary.py`)
- `tests/` - the test suite, including the Node harness for the markets pages
- `data/` - raw data from Kalshi and ESPN (`original_run/` is the first Colab pull; `manual/` holds prices for delisted stocks)
- `results/` - output tables and search results (`original_run/` holds the original results)
- `docs/` - the write-up, the verification report and the leakage audit
- `colab/` - one-click notebook that re-runs the original results, plus the original Colab notebook
- `index.html` - sends the website's main link to the Edge Lab

## Caveats

- Samples are one season (NBA) and about 9 months (tennis). Promising leads need future data to confirm.
- Pre-match and game-start times are estimated from trading-volume spikes, so they can be off by a few minutes. Set lengths in the Edge Lab are estimates for the same reason.
- Grand Slam (best-of-5) matches are identified by tournament dates.
- "Before the match" tennis prices in the Edge Lab are midpoints plus 1¢, because only midpoints were saved for that moment.
- *All sports · price paths* has prices but no scores. A falling price is the market's read of the score, not the score itself. Tennis and UFC start times are estimated from the burst in trading, so "before the start" prices for those two can be a few minutes off.
- In-game bets fill at the ask one sample (1–2 minutes) after the rule is first seen. Faster traders would get better prices; slower ones worse.
- The stocks page tests hundreds of market-stock pairs, so some look strong by luck. The scanner says how many. Stock trades assume you get the opening price and pay the cost you set; real fills, borrow costs for shorts and taxes are not modelled.
- "Options-implied" odds on the Strategies page come from a volatility index and a no-skew lognormal model, not real option chains (Yahoo's chain endpoint was not reachable). Warner Bros prices come from Alpha Vantage because Yahoo drops delisted stocks; they are in `data/manual/WBD.csv`.
- The merger test's offer and break prices are assumptions you set on the page.
- This is research, not betting or investment advice.

