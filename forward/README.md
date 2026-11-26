# Forward testing

Backtests can be fooled: with enough ideas tried on past data, some look great by luck, and subtle look-ahead
slips in (this project found three). A forward test can't be fooled that way, because each idea is judged only on
games and markets that had not happened yet when it was written down.

**Latest results: [REPORT.md](REPORT.md)** (updated daily).

## How it works

1. **An idea is a small Python file** in `hypotheses/`: a title, a domain (`games` or `markets`) and a `decide()`
   function that says when to bet and on which side. See `lib.py` for the exact format and `hypotheses/` for examples.
2. **A GitHub Action runs `run.py` every day** (`.github/workflows/forward.yml`; no AI involved). It:
   - **registers** any new file the first time it sees it on `main`, recording that moment and the file's
     fingerprint. Ideas can't be backdated, and an idea edited after registration is disqualified (write a new
     file instead).
   - **pulls** the Kalshi games (14 leagues) that settled since yesterday, and a random sample of up to 1,500 newly
     settled markets outside sports. Markets are chosen at random, never by volume or result.
   - **bets** each idea only where its decision came *after* it was registered: at the real ask, with Kalshi's fee,
     held to settlement.
   - **leak-checks every bet**: it scrambles everything after the decision (later prices, the close time) and
     flips the result. If the decision changes, the idea is peeking, and it is disqualified for good.
   - **writes** the bets to `bets/<idea>.jsonl` and the scoreboard to `REPORT.md` and `results.json`.
3. **A weekly Claude session** reads the report, proposes up to 5 new ideas, checks them with `check.py`, and
   opens a pull request. **An idea starts counting when that pull request is merged.**

## Verdicts

| Verdict | Means |
|---|---|
| too early | fewer than 30 events so far |
| no edge yet | 30+ events, nothing significant |
| promising | profitable with p < 0.05, but not yet past the bar below |
| **BREAKTHROUGH** | 100+ events, profitable, and significant after a false-discovery correction across **every idea ever registered**, including failed and retired ones |
| failing | 100+ events and losing money |
| disqualified | edited after registration, or caught peeking |

Returns are averaged per event (outcomes of one event move together). Expect a few months before any idea has 100
events.

## Commands

    python forward/check.py forward/hypotheses/my_idea.py   # does it run and pass the leak check on past data?
    python forward/run.py                                   # what the daily job runs
    python forward/run.py --report                          # rebuild the report from saved bets
