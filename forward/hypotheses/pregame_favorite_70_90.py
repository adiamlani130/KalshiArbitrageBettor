"""The favorite-long-shot bias, before the game: buy the favorite priced 70-90c five minutes before the start."""
TITLE = "Before the start, buy the favorite priced 70-90c"
DOMAIN = "games"
LEAGUES = "all"

def decide(g):
    q = g.get("pre")
    if not q: return []
    s = 0 if sum(q[0]) >= sum(q[1]) else 1
    return [dict(i="pre", side=s)] if 70 <= q[s][1] <= 90 else []
