# Beating the Bookie: Finding Edges in Kalshi Sports Markets

*Original write-up. The numbers below come from the first round of analysis in Colab and the Claude chat. The re-run in [`results/results.md`](results/results.md) is the version you can reproduce.*

For years, people have labeled sports betting as just a cost of being a sports fan: you drink, have fun, and lose the occasional parlay while gaining the excitement of a now personal game.

What if someone bet on a more technical basis instead, with their own strategy that comes with years of backtesting and an established win rate?

I narrowed my research to three sports: basketball, football, and tennis. Basketball and football are the most popular events in the US and carry huge volume. I chose tennis because it's an individual sport driven heavily by trackable statistics, without many of the confounding variables a team sport has. I used Colab to pull data from Kalshi's history of odds and outcomes, looking for trends that could create asymmetric returns in the betting markets.

## Football

A 2022 Dartmouth study found that a model combining yardage differential and turnover differential correctly predicted 132 of 150 games (88%). That's promising, but there isn't much room to profit from those stats because they change so quickly during a game.

## NBA

Analyst Dean Oliver built a similar metric from four team stats, but it ran into the same problem: no profitable entry point for bettors. A more promising idea came from the MIT Sloan conference. When teams trail, the trailing team shooting threes is statistically favored, while the leading team often plays conservatively and lets the lead get chipped away. However, that strategy had a strongly negative return. Two strategies worked far better: betting the 10-point favorite after the first quarter, and betting the underdog in playoff games.

## Tennis

Tennis was the last and most promising sport. The big trend: from 1991 to 2020, the player who won the first set of a best-of-3 ATP match went on to win 88.3% of the time.

- Across a sample of 1,295 recent ATP matches, betting on the set-1 winner alone lost 5.2% after fees.
- Adding a filter for players who were favorites of at least -400, to cut out underdog flukes, still returned -2.7%.
- Surprisingly, the only strategy with any conviction was betting **against** the set-1 winner at odds between -233 and -400. It returned **15.3% on 240 bets**.

## Conclusion

Prediction markets give bettors more options than ever before, creating more chances for consistent returns. My research was limited to samples of about 1,000 games, but there were some promising edges. Even if the strategies don't hold up on a broader sample, they offer another way to approach the biggest underdog story: beating the bookie.
