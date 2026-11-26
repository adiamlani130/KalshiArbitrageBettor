"""Long shots are overpriced in every sport in the backtests (backing the team behind lost 16% on held-back games),
so the other side, a heavy favorite late in the game, may be slightly underpriced. Fees are small at 85-95c."""
TITLE = "Late in any game, buy the team priced 85-95c"
DOMAIN = "games"
LEAGUES = "all"
DUR = {"nfl": 190, "ncaaf": 205, "nba": 150, "wnba": 125, "ncaab": 125, "mlb": 170, "nhl": 155}

def decide(g):
    i0 = int(DUR.get(g["league"], 100) * 0.65 / g["step"])        # about two-thirds of a typical game, from the schedule
    for i in range(i0, g["n"]):
        for s in (0, 1):
            b, a = g["bid"][s][i], g["ask"][s][i]
            if g["live"][s][i] and b is not None and a is not None and 85 <= (a + b) / 2 <= 95:
                return [dict(i=i, side=s)]
    return []
