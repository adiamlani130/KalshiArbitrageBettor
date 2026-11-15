# Do popular sports-betting trends beat Kalshi's prediction markets?

**Author:** Adi Amlani, University of Florida (Finance & Mathematics)

**[Try the live tool](https://adiamlani130.github.io/KalshiArbitrageBettor/)** · **[Run the analysis in Colab](https://colab.research.google.com/github/adiamlani130/KalshiArbitrageBettor/blob/main/colab/run_in_colab.ipynb)** (no setup, about a minute)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/adiamlani130/KalshiArbitrageBettor/blob/main/colab/run_in_colab.ipynb)

This project tests well-known sports "trends" against real Kalshi prediction-market prices to see whether any of them could actually make money. Every strategy assumes **$10 per bet**, bought at the real asking price at that moment, with **Kalshi's trading fee subtracted**.

**Short answer:** no simple rule reliably beats the market after fees. The one pattern that shows up everywhere is the **favorite-longshot bias**: long shots (big comebacks, big underdogs) are overpriced, while heavy favorites are priced about right.

**Try it yourself:** the [Kalshi Edge Lab](https://adiamlani130.github.io/KalshiArbitrageBettor/) runs in the browser with nothing to install. It has two pages:

- **Sports lab.** Build any strategy: pick a sport, a sample (for example 1,000 random tennis matches), when to bet, who to bet on, a price range and any conditions, and see what it would have made. *All sports · price paths* covers 14 leagues (NFL, college football, NBA, WNBA, college basketball, MLB, NHL, four soccer leagues, UFC, ATP and WTA) and lets you bet on what the price does during the game. See [What you can test](#what-you-can-test).
- **Markets vs stocks.** Lines up Kalshi probabilities (Fed decisions, tariffs, shutdowns, elections, Tesla, bitcoin and more) with about 100 stocks and ETFs, to test whether the prediction market moves before the stock does.

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

## What you can test

### Sports lab

| | Tennis · ATP | NBA · games | NBA · big deficits | All sports · price paths |
|---|---|---|---|---|
| Data | Set results + prices | ESPN scores + prices | ESPN scores + prices | Prices only, every 1–2 minutes |
| Leagues | ATP | NBA | NBA | 14 leagues |
| When you can bet | Before the match, after set 1 | Before tip-off, end of Q1, halftime, end of Q3 | First time down 10, 15 or 20 | Before the start (5 min, 1 hour, 24 hours), any minute of the game, or on a price trigger |

Price triggers in *All sports* are things like "the first time the favorite falls to 30¢", "the first time either team reaches 90¢", "a team drops 15¢ within 10 minutes" or "a team is 20¢ off its in-game high". You choose the team to watch, the threshold and who to bet on (the team that triggered it, or the other one).

You can then add conditions (league, day of week, start hour, pre-game price, how the line moved in the last hour or day, pre-game volume, minutes into the game, how far the pick is off its high, lead changes so far, and more) and optionally **get out early**: sell at a target, at a stop, or after a set time, instead of holding to the result.

Three tabs read the same bets:

- **Test a bet** - profit, win rate, a likely range, and whether it held in both halves of the sample.
- **Find a link** - win rate against the price-implied chance, split by any column.
- **Strongest links** - splits the bet by every condition you could have known in time, ranks the groups, and says how many would look that strong by luck.

### Markets vs stocks

| Tab | Question it answers |
|---|---|
| Who moves first | Does Kalshi's daily change line up with the stock's move on the same day, on later days (Kalshi leads) or on earlier days (the stock leads)? |
| Lag trade | If Kalshi moves X points and the stock hasn't moved yet, does buying (or shorting) the stock at the next open make money after costs? |
| Hourly shocks | After Kalshi's biggest one-hour jumps, what had the stock already done, and what was left by the first price you could trade? |
| Announcements | For Fed, CPI, jobs, GDP and unemployment releases: how big was the surprise against Kalshi's price the evening before, and how did the stock react that day and after? |
| Strongest pairs | Ranks every market-stock pair by how strongly one leads the other, and says how many would pass by luck. |
| Paper trade | Turns the current lag-trade rule into a settings file for `scripts/alpaca_paper.py`, which places the trade in an Alpaca paper account. |

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

To refresh the newer data (no API keys needed):

```bash
python scripts/pull_sports.py     # 14 leagues of in-game price paths from Kalshi (1-2 hours, resumable)
python scripts/pull_stocks.py     # Kalshi probabilities + Yahoo Finance prices (about 15 minutes)
```

### Paper trading the lag trade

`scripts/alpaca_paper.py` runs one lag-trade rule on live prices with an [Alpaca](https://alpaca.markets) **paper** account (fake money). Build the rule in the lab's *Paper trade* tab, download `signal.json`, then:

```bash
export ALPACA_KEY=your_paper_key ALPACA_SECRET=your_paper_secret
python scripts/alpaca_paper.py signal.json            # dry run: shows what it would do
python scripts/alpaca_paper.py signal.json --trade    # places the paper order
```

It reads Kalshi's live probability, checks whether it moved enough while the stock hasn't, places the order, and closes the position after the holding period the next time you run it. It only talks to Alpaca's paper endpoint. It has been checked against live Kalshi data but not against an Alpaca account, so start with the dry run.

## Repo layout

- `app/` - the Kalshi Edge Lab: `index.html` (sports lab) and `stocks.html` (markets vs stocks); `build_data.py` builds the tennis and NBA score data
- `app/data/` - the all-sports price paths (one file per league, loaded on demand) and the stocks data
- `scripts/pull_sports.py`, `scripts/pull_stocks.py` - pull and build everything in `app/data/`
- `scripts/alpaca_paper.py` - paper-trades a lag-trade rule through Alpaca
- `index.html` - sends the website's main link straight to the Edge Lab
- `colab/run_in_colab.ipynb` - one-click notebook that re-runs every result
- `colab/` - also holds the original Colab notebook and the cleaned-up Colab data-pull scripts
- `scripts/pull_data.py` - the same data pull as one script you can run anywhere
- `analysis/` - analysis scripts; `common.py` holds the bet and fee math
- `data/` - raw data from Kalshi and ESPN (`original_run/` is the first Colab pull)
- `results/` - output tables (`original_run/` holds the original results)
- `docs/` - the write-up and the verification report

## Caveats

- Samples are one season (NBA) and about 9 months (tennis). Promising leads need future data to confirm.
- Pre-match and game-start times are estimated from trading-volume spikes, so they can be off by a few minutes. Set lengths in the Edge Lab are estimates for the same reason.
- Grand Slam (best-of-5) matches are identified by tournament dates.
- "Before the match" tennis prices in the Edge Lab are midpoints plus 1¢, because only midpoints were saved for that moment.
- *All sports · price paths* has prices but no scores. A falling price is the market's read of the score, not the score itself. Tennis and UFC start times are estimated from the burst in trading, so "before the start" prices for those two can be a few minutes off.
- In-game bets fill at the ask one sample (1–2 minutes) after the rule is first seen. Faster traders would get better prices; slower ones worse.
- The stocks page tests hundreds of market-stock pairs, so some look strong by luck. The scanner says how many. Stock trades assume you get the opening price and pay the cost you set; real fills, borrow costs for shorts and taxes are not modelled.
- This is research, not betting or investment advice.

