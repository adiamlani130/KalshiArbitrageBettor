# Verification

Every result from the original research was checked twice:

1. **Reproduced.** The original analysis scripts were re-run on the original saved data (`data/original_run/`). Every number matched the original tables exactly.
2. **Re-pulled.** All data was downloaded again from Kalshi and ESPN (`scripts/pull_data.py`), and the same scripts were run on it.

The fresh pull is bigger because the original Colab run couldn't read the price fields in Kalshi's archive at first. Many older matches were skipped (tennis) or came back without prices (NBA). The fresh pull reads both formats:

| | Original run | Fresh pull |
|---|---:|---:|
| Tennis best-of-3 matches with prices | 1,295 | 2,145 |
| NBA games matched to play-by-play | 1,026 | 1,316 |

## Tennis

| Strategy | Original result | Reproduced from original data | Fresh pull |
|---|---|---|---|
| Bet every set-1 winner | 1,295 bets, −5.2% | 1,295 bets, −5.2% ✓ | 2,145 bets, −2.2% |
| Bet set-1 winner at −400 or shorter | 749 bets, −2.7% | 749 bets, −2.7% ✓ | 1,271 bets, −0.7% |
| Bet set-1 winner at −900 or shorter | 398 bets, −1.4% | 398 bets, −1.4% ✓ | 636 bets, −0.2% |
| Bet against every set-1 winner | 1,295 bets, +0.1% | 1,295 bets, +0.1% ✓ | 2,145 bets, −12.3% |
| Bet against at −233 to −900, Jul–Sep | 199 bets, +38.3% | 199 bets, +38.3% ✓ | 308 bets, +22.4% |
| Bet against at −233 to −900, Jan–Jul | 392 bets, −9.2% | 392 bets, −9.2% ✓ | 706 bets, −18.6% |
| **Bet against at −233 to −400** | **240 bets, +15.3%** | 240 bets, +15.3% ✓ | **379 bets, +3.9%** |

## NBA

| Strategy | Original result | Reproduced from original data | Fresh pull |
|---|---|---|---|
| Bet team down 15+ | 763 bets, −37.2% | 763 bets, −37.2% ✓ | 975 bets, −38.9% |
| Bet team down 20+ | 487 bets, −37.9% | 487 bets, −37.9% ✓ | 624 bets, −47.9% |
| Down 20+ in 1st half | 208 bets, −62.5% | 208 bets, −62.5% ✓ | 262 bets, −59.4% |
| Down 20+ in 2nd half | 279 bets, −19.6% | 279 bets, −19.6% ✓ | 362 bets, −39.6% |
| Down 20+, took 4+ threes in last 10 min | 126 bets, −80.5% | 126 bets, −80.5% ✓ | 170 bets, −84.7% |
| Bet leader, trailer +900 to +3200 | 223 bets, +3.3% | 223 bets, +3.3% ✓ | 293 bets, +3.4% (+2.2% at the real ask) |
| Bet leader up 16+ after Q1 | 68 bets, +0.9% | 68 bets, +0.9% ✓ | 89 bets, +0.2% |
| Bet leader up 16+ after Q3 | 137 bets, +0.6% | 137 bets, +0.6% ✓ | 176 bets, +1.1% |
| Favorite trailing at halftime: bet favorite | 369 bets, 0.0% | 369 bets, 0.0% ✓ | 465 bets, −1.1% |
| Favorite down 10+ at halftime: bet favorite | 132 bets, +14.9% | 132 bets, +14.9% ✓ | 161 bets, +9.5% |
| Playoffs: bet underdog | 66 bets, +25.4% | 66 bets, +25.4% ✓ | 77 bets, +23.8% |

## What changed and why it matters

- **The tennis edge shrank.** Betting against the set-1 winner at −233 to −400 went from +15.3% to +3.9% once the missing matches were added. The wider −233 to −900 version still loses 18.6% on the months it wasn't found in. Treat it as luck until new matches say otherwise.
- **The NBA comeback results got worse, not better.** Betting on big comebacks loses heavily in every version. That's the favorite-longshot bias: long shots are overpriced.
- **The two positive NBA results are small samples.** "Favorite down 10+ at halftime" (161 bets) and "playoff underdogs" (77 bets) are positive in both pulls. The likely range still includes zero for both.

## Small issues found in the original code

- **Leader bets were priced at the bid.** `nba_analysis.py` prices "bet the leader" as 1 − the trailer's ask, which is the leader's bid, 1–2¢ cheaper than what you'd actually pay. At the real ask the +900 to +3200 strategy returns +2.2% instead of +3.4%. The script is left unchanged so the original numbers reproduce; the Edge Lab uses the real ask.
- **Playoff games.** `nba_analysis.py` finds playoff games by Kalshi titles that start with "Game" (77 in the fresh pull). The Edge Lab uses ESPN's playoff flag (81 games), so its playoff numbers differ slightly.
- **Best-of-5 dates.** Matches during Grand Slam dates are all treated as best-of-5, including Slam qualifying, which is best-of-3. The Edge Lab keeps the same rule so its numbers match the scripts.

## How to re-check

```bash
python analysis/tennis_analysis.py data/original_run results/original_run
python analysis/nba_build.py data/original_run results/original_run
python analysis/nba_analysis.py data/original_run results/original_run
```

Then run the same three commands without the extra arguments for the fresh pull.
