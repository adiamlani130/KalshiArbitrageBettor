"""On a random 15,000 Mentions markets, those at 40-60c the day before the event resolved YES 37-47% of the time,
6-8 points under their price (buying NO: +7% and +12% in the two bands, t 1.0-1.7). Found by looking, so it only
counts if it holds on markets that settle from now on."""
import re
from datetime import datetime, timezone
TITLE = "Mentions: buy NO at 40-60c the day before the event"
DOMAIN = "markets"
CATEGORIES = ["Mentions"]

MON = {m: i for i, m in enumerate(("", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")) if m}

def day_before(m):
    """Index of the day-end quote on the day before the event date in the ticker (fixed at listing), if the market
    was trading then. Never uses the close time or Kalshi's expiration fields (often the latest possible date)."""
    x = re.search(r"-(\d{2})([A-Z]{3})(\d{2})", m["event"])
    if not x or x.group(2) not in MON: return None
    try: d = int(datetime(2000 + int(x.group(1)), MON[x.group(2)], int(x.group(3)), tzinfo=timezone.utc).timestamp())
    except ValueError: return None
    ks = [k for k, t in enumerate(m["T"]) if d - 86400 < t <= d and m["ask"][k] is not None]
    return ks[-1] if ks else None

def decide(m):
    k = day_before(m)
    return [dict(k=k, side="no")] if k is not None and 40 <= m["mid"][k] < 60 else []
