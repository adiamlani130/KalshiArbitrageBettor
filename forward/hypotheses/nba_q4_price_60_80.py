"""NBA buy-the-leader rules were the only family that kept passing the 2025-26 search, and 'leading 4-9 in the 4th'
made +6.4% on 109 games of 2026-27. Forward test the price version: in the 4th quarter, buy the team priced 60-80c."""
TITLE = "NBA 4th quarter: buy the team priced 60-80c"
DOMAIN = "games"
LEAGUES = ["nba"]

def decide(g):
    for i in range(int(105 / g["step"]), g["n"]):        # ~105 minutes after the scheduled tip: usually the 4th quarter
        for s in (0, 1):
            b, a = g["bid"][s][i], g["ask"][s][i]
            if g["live"][s][i] and b is not None and a is not None and 60 <= (a + b) / 2 <= 80:
                return [dict(i=i, side=s)]
    return []
