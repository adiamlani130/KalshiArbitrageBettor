"""Machine search for in-game betting strategies, with a strict three-way time split.

    python analysis/evolve.py            # ~10-20 minutes; writes results/evolved.json and app/data/evolved.js
    python analysis/evolve.py --quick    # a smaller run for testing

Every game in every league becomes a set of decision points: an hour before the start, just before the start,
and every 10 minutes during the game (5 for UFC), for each side. Each decision point carries only what was
known at that moment (prices up to then, the pre-game line, the schedule) plus the price you would actually
pay: the ask at the first live quote 1-3 samples later. Its result is the profit on a $10 bet held to the end.

Three searches run over this table:
  1. A genetic algorithm evolving readable rules ("in the NBA, between 20 and 60 minutes in, buy a team that is
     15¢+ off its high and still the pre-game favorite"), tens of thousands of them.
  2. NEAT (NeuroEvolution of Augmenting Topologies) evolving small neural networks that decide when to bet.
  3. A gradient-boosted model predicting the chance of winning, betting when it disagrees with the price.

Games are split by start date: the first 55% to search on, the next 20% to choose between candidates
("validation"), and the last 25% held back and used exactly once ("test"). Rule thresholds come from the
search period only. A strategy is reported as confirmed only if it survives a Benjamini-Hochberg
false-discovery rate of 5% on the test games, across everything sent to the test, with a t-statistic of 2+.
"""
import json, math, os, random, sys, time
import numpy as np
import engine as E

QUICK = "--quick" in sys.argv
SPLITS = (0.55, 0.75)
NEAT_POP, NEAT_GENS = (60, 10) if QUICK else (250, 80)     # networks per generation, generations
MIN_TRAIN, MIN_VALID, MIN_TEST = 200, 60, 40
DUR = {"nfl": 190, "ncaaf": 205, "nba": 150, "wnba": 125, "ncaab": 125, "mlb": 170, "nhl": 155, "epl": 115, "ucl": 115,
       "laliga": 115, "mls": 115, "ufc": 25, "atp": 110, "wta": 100}
FEATURES = [  # name, plain-English label, unit for thresholds
    ("elapsed", "minutes into the game", "min"), ("p", "the team's price", "¢"), ("chg", "change since the start", "¢"),
    ("chg10", "change in the last 10 minutes", "¢"), ("off_high", "distance below its in-game high", "¢"),
    ("off_low", "distance above its in-game low", "¢"), ("is_fav", "was the pre-game favorite", "bool"),
    ("is_home", "is the home team", "bool"), ("fav_pre", "the favorite's pre-game price", "¢"), ("flips", "lead changes on price so far", ""),
    ("spread", "bid/ask spread", "¢"), ("lpvol", "log10 contracts traded before the start", ""), ("move_1h", "line move in the last hour before the start", "¢"),
    ("fill", "price paid", "¢"), ("draw", "price of a draw (soccer)", "¢"), ("frac", "share of a typical game played", ""), ("hour", "start hour (New York)", "h"),
]
FI = {f[0]: i for i, f in enumerate(FEATURES)}

def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

# ---------------------------------------------------------------- the decision-point table
THREE_WAY = ("epl", "ucl", "laliga", "mls")

def points(g, lg):
    """Every moment a bet could be placed in one game, as (order, side, features, price paid in cents).
    Features use only prices up to that moment; the price paid is the ask at the first live quote 1-3 samples later."""
    out = []
    n, step, three, ts = g["n"], g["step"], lg in THREE_WAY, g["ts"]
    mid = [[None if g["bid"][s][i] is None else (g["bid"][s][i] + g["ask"][s][i]) / 2 for i in range(n)] for s in (0, 1)]
    premid = [(g["pre"][s][0] + g["pre"][s][1]) / 2 for s in (0, 1)]
    fav = g["fav"]; favp = premid[fav]; hour = (ts // 3600 - 5) % 24
    lpvol = math.log10((g.get("pvol") or 0) + 1); h1 = g.get("h1")
    def add(order, s, feats, price):
        if price is not None and 2 <= price <= 98: out.append((order, s, feats, price))
    for s in (0, 1):
        home = 0.5 if g["home"] is None else float(s == 0)
        if h1:      # an hour before the start: only the line at that moment is known (no start price, no pre-game volume)
            h1mid = [(h1[k][0] + h1[k][1]) / 2 for k in (0, 1)]; fav1 = 0 if h1mid[0] >= h1mid[1] else 1
            add(-2, s, [-60, h1mid[s], 0, 0, 0, 0, float(s == fav1), home, h1mid[fav1], 0, h1[s][1] - h1[s][0], -1, 0,
                        h1[s][1], (100 - sum(h1mid)) if three else 0, -60 / DUR[lg], hour], h1[s][1])
        mv = premid[s] - (h1[s][0] + h1[s][1]) / 2 if h1 else 0
        add(-1, s, [-5, premid[s], 0, 0, 0, 0, float(s == fav), home, favp, 0, g["pre"][s][1] - g["pre"][s][0], lpvol, mv,
                    g["pre"][s][1], (100 - sum(premid)) if three else 0, -5 / DUR[lg], hour], g["pre"][s][1])
    every = max(1, round((5 if lg == "ufc" else 10) / step)); back = max(1, round(10 / step))
    hi, lo, flips, side_ = [0, 0], [100, 100], 0, 0
    for i in range(n - 1):
        for s in (0, 1):
            if mid[s][i] is not None: hi[s] = max(hi[s], mid[s][i]); lo[s] = min(lo[s], mid[s][i])
        if mid[fav][i] is not None:
            z = 1 if mid[fav][i] > 52 else -1 if mid[fav][i] < 48 else 0
            if z and side_ and z != side_: flips += 1
            if z: side_ = z
        if i == 0 or i % every: continue
        for s in (0, 1):
            m = mid[s][i]
            if m is None: continue
            e = next((j for j in range(i + 1, min(n, i + 4)) if g["live"][s][j]), None)
            if e is None: continue
            m10 = mid[s][max(0, i - back)]
            other = mid[1 - s][i] if mid[1 - s][i] is not None else 100 - m
            add(i, s, [i * step, m, m - premid[s], m - (m10 if m10 is not None else m), hi[s] - m, m - lo[s], float(s == fav),
                       0.5 if g["home"] is None else float(s == 0), favp, flips, g["ask"][s][i] - g["bid"][s][i], lpvol,
                       (premid[s] - (h1[s][0] + h1[s][1]) / 2) if h1 else 0, g["ask"][s][e], (100 - m - other) if three else 0,
                       i * step / DUR[lg], hour], g["ask"][s][e])
    return out

def build_table():
    idx = E.index(); leagues = list(idx["leagues"]); sports = sorted({idx["leagues"][l]["sport"] for l in leagues})
    rows, meta = [], []      # meta: game id, order within game, side, league, sport, win, net, ts
    games = []
    for li, lg in enumerate(leagues):
        for g in E.load(lg, idx):
            games.append((g["ts"], lg, g))
    games.sort(key=lambda x: x[0])
    for gid, (ts, lg, g) in enumerate(games):
        sport = sports.index(idx["leagues"][lg]["sport"]); league = leagues.index(lg)
        for order, s, feats, price in points(g, lg):
            won = g["win"] == s
            rows.append(feats); meta.append((gid, order, s, league, sport, won, E.pnl(price / 100, won), ts))
    X = np.asarray(rows, dtype=np.float32); M = np.asarray(meta, dtype=np.float64)
    order = np.lexsort((M[:, 2], M[:, 1], M[:, 0]))       # by game, then time, then side: first match = earliest
    X, M = X[order], M[order]
    gid = M[:, 0].astype(np.int32); ngames = len(games)
    cut1, cut2 = int(ngames * SPLITS[0]), int(ngames * SPLITS[1])
    period = np.where(gid < cut1, 0, np.where(gid < cut2, 1, 2)).astype(np.int8)   # games are already in date order
    dates = [time.strftime("%Y-%m-%d", time.gmtime(games[k][0] - 5 * 3600)) for k in (0, cut1, cut2, ngames - 1)]
    return dict(X=X, gid=gid, side=M[:, 2].astype(np.int8), league=M[:, 3].astype(np.int8), sport=M[:, 4].astype(np.int8),
                won=M[:, 5].astype(bool), net=M[:, 6].astype(np.float32), ts=M[:, 7], period=period, leagues=leagues, sports=sports,
                ngames=ngames, dates=dates, labels=[idx["leagues"][l]["label"] for l in leagues])

# ---------------------------------------------------------------- scoring a set of bets
def stats(net):
    n = len(net)
    if n < 2: return dict(n=n, roi=0.0, t=0.0, p=1.0)
    m = float(net.mean()); sd = float(net.std(ddof=1)); t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    return dict(n=n, roi=m / E.STAKE, t=t, p=0.5 * math.erfc(t / math.sqrt(2)))

def first_bets(T, mask):
    """One bet per game: the earliest decision point where the strategy says yes."""
    idx = np.flatnonzero(mask)
    if not len(idx): return idx
    _, first = np.unique(T["gid"][idx], return_index=True)
    return idx[first]

def by_period(T, rows):
    return [stats(T["net"][rows[T["period"][rows] == k]]) for k in (0, 1, 2)]

# ---------------------------------------------------------------- 1. genetic algorithm over readable rules
WINDOWS = [("h1", -60, -60), ("pre", -5, -5), ("early", 1, 30), ("first half", 1, 0.5), ("second half", 0.5, 1.0), ("late", 0.75, 1.5),
           ("any time in-game", 1, 9999), ("any time", -60, 9999)]
COND_FEATS = ["p", "chg", "chg10", "off_high", "off_low", "fav_pre", "flips", "spread", "lpvol", "move_1h", "fill", "draw", "hour", "is_fav", "is_home"]

class Rules:
    def __init__(self, T, rnd):
        self.T, self.rnd = T, rnd
        tr = T["period"] == 0
        # thresholds are quantiles of the SEARCH period only
        self.q = {f: np.unique(np.quantile(T["X"][tr, FI[f]], np.linspace(0.05, 0.95, 19))) for f in COND_FEATS}
        self.cache = {}

    def random(self):
        r = self.rnd
        g = dict(win=r.randrange(len(WINDOWS)), cat=r.choice([None, None, ("sport", r.randrange(len(self.T["sports"]))), ("league", r.randrange(len(self.T["leagues"])))]),
                 conds=[], band=(r.choice([2, 10, 20, 30, 40, 50]), r.choice([50, 60, 70, 80, 90, 98])))
        if g["band"][0] >= g["band"][1]: g["band"] = (2, 98)
        for _ in range(r.randint(0, 3)): g["conds"].append(self.rand_cond())
        return g

    def rand_cond(self):
        f = self.rnd.choice(COND_FEATS)
        if f in ("is_fav", "is_home"): return (f, "==", float(self.rnd.random() < 0.5))
        return (f, self.rnd.choice(["<=", ">="]), float(self.rnd.choice(list(self.q[f]))))

    def mutate(self, g):
        r = self.rnd; g = json.loads(json.dumps(g)); g["cat"] = tuple(g["cat"]) if g["cat"] else None
        g["conds"] = [tuple(c) for c in g["conds"]]; g["band"] = tuple(g["band"])
        k = r.random()
        if k < 0.15: g["win"] = r.randrange(len(WINDOWS))
        elif k < 0.25: g["cat"] = r.choice([None, ("sport", r.randrange(len(self.T["sports"]))), ("league", r.randrange(len(self.T["leagues"])))])
        elif k < 0.35:
            lo, hi = g["band"]; lo = r.choice([2, 10, 20, 30, 40, 50, 60]); hi = max(lo + 10, r.choice([50, 60, 70, 80, 90, 98])); g["band"] = (lo, min(98, hi))
        elif k < 0.5 and len(g["conds"]) < 3: g["conds"].append(self.rand_cond())
        elif k < 0.6 and g["conds"]: g["conds"].pop(r.randrange(len(g["conds"])))
        elif g["conds"]:
            i = r.randrange(len(g["conds"])); f, op, v = g["conds"][i]
            if f in ("is_fav", "is_home"): g["conds"][i] = (f, op, 1.0 - v)
            else:
                qs = list(self.q[f]); j = min(range(len(qs)), key=lambda j: abs(qs[j] - v))
                j = max(0, min(len(qs) - 1, j + r.choice([-2, -1, 1, 2]))); g["conds"][i] = (f, op if r.random() < 0.8 else ("<=" if op == ">=" else ">="), float(qs[j]))
        else: g["conds"].append(self.rand_cond())
        return g

    def cross(self, a, b):
        c = self.mutate(a); pool = list(a["conds"]) + list(b["conds"]); self.rnd.shuffle(pool)
        c["conds"] = [tuple(x) for x in pool[:self.rnd.randint(0, min(3, len(pool)))]]
        if self.rnd.random() < 0.5: c["win"] = b["win"]
        return c

    def key(self, g):
        return json.dumps([g["win"], g["cat"], sorted(map(list, g["conds"])), list(g["band"])])

    def mask(self, g):
        T, X = self.T, self.T["X"]
        name, lo, hi = WINDOWS[g["win"]]
        el, fr = X[:, FI["elapsed"]], X[:, FI["frac"]]
        if name in ("first half", "second half", "late"): m = (el > 0) & (fr >= (0 if name == "first half" else lo)) & (fr < hi)
        else: m = (el >= lo) & (el <= hi)
        if g["cat"]: m &= (T[g["cat"][0]] == g["cat"][1])
        f = X[:, FI["fill"]]; m &= (f >= g["band"][0]) & (f <= g["band"][1])
        for fname, op, v in g["conds"]:
            col = X[:, FI[fname]]
            m &= (col <= v) if op == "<=" else (col >= v) if op == ">=" else (col == v)
        return m

    def score(self, g):
        k = self.key(g)
        if k in self.cache: return self.cache[k]
        rows = first_bets(self.T, self.mask(g)); tr = rows[self.T["period"][rows] == 0]
        s = stats(self.T["net"][tr])
        fit = s["t"] - 0.15 * len(g["conds"]) if s["n"] >= MIN_TRAIN else -10 + s["n"] / MIN_TRAIN
        self.cache[k] = (fit, s, g)
        return self.cache[k]

def describe(T, g):
    name = WINDOWS[g["win"]][0]
    when = {"h1": "an hour before the start", "pre": "just before the start", "early": "in the first 30 minutes", "first half": "in the first half of the game",
            "second half": "in the second half of the game", "late": "late in the game", "any time in-game": "at any point during the game", "any time": "at any time"}[name]
    where = "in any sport" if not g["cat"] else f"in {T['labels'][g['cat'][1]]}" if g["cat"][0] == "league" else f"in {T['sports'][g['cat'][1]].lower()}"
    parts = []
    for f, op, v in g["conds"]:
        lab = dict((a, b) for a, b, _ in FEATURES)[f]; unit = dict((a, c) for a, _, c in FEATURES)[f]
        if unit == "bool": parts.append({("is_fav", 1): "it was the pre-game favorite", ("is_fav", 0): "it was the pre-game underdog",
                                         ("is_home", 1): "it is the home team", ("is_home", 0): "it is the away team"}[(f, int(v))])
        else: parts.append(f"{lab} {'at most' if op == '<=' else 'at least'} {v:g}{unit if unit not in ('', 'bool') else ''}")
    lo, hi = g["band"]
    s = f"Buy a team {when}, {where}" + (f", when {', '.join(parts)}" if parts else "") + (f", paying {lo}–{hi}¢" if (lo, hi) != (2, 98) else "")
    return s

def run_ga(T, seed, pop_n, gens, randoms):
    rnd = random.Random(seed); R = Rules(T, rnd)
    for _ in range(randoms): R.score(R.random())
    pop = [R.random() for _ in range(pop_n)]
    for gen in range(gens):
        scored = sorted((R.score(g) for g in pop), key=lambda x: -x[0])
        elite = [x[2] for x in scored[:pop_n // 10]]
        nxt = list(elite)
        while len(nxt) < pop_n:
            a = max(rnd.sample(scored, 4), key=lambda x: x[0])[2]; b = max(rnd.sample(scored, 4), key=lambda x: x[0])[2]
            nxt.append(R.cross(a, b) if rnd.random() < 0.3 else R.mutate(a))
        nxt[-pop_n // 10:] = [R.random() for _ in range(pop_n // 10)]       # fresh blood every generation
        pop = nxt
        if gen % 10 == 0: log(f"GA seed {seed} gen {gen}: best train t {scored[0][0]:.2f}, {len(R.cache):,} rules scored")
    return R

# ---------------------------------------------------------------- 2. NEAT
NEAT_IN = ["elapsed", "p", "chg", "chg10", "off_high", "off_low", "is_fav", "is_home", "fav_pre", "flips", "spread", "lpvol", "move_1h", "fill", "draw", "frac"]
NEAT_CFG = """
[NEAT]
fitness_criterion = max
fitness_threshold = 1000
pop_size = {pop}
reset_on_extinction = True
no_fitness_termination = True
[DefaultGenome]
num_inputs = {nin}
num_hidden = 0
num_outputs = 1
initial_connection = partial_direct 0.3
feed_forward = True
compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient = 0.5
conn_add_prob = 0.4
conn_delete_prob = 0.3
node_add_prob = 0.2
node_delete_prob = 0.15
activation_default = tanh
activation_options = tanh relu sigmoid
activation_mutate_rate = 0.1
aggregation_default = sum
aggregation_options = sum
aggregation_mutate_rate = 0.0
bias_init_mean = 0.0
bias_init_stdev = 1.0
bias_init_type = gaussian
bias_max_value = 30.0
bias_min_value = -30.0
bias_mutate_power = 0.5
bias_mutate_rate = 0.7
bias_replace_rate = 0.1
response_init_mean = 1.0
response_init_stdev = 0.0
response_init_type = gaussian
response_max_value = 30.0
response_min_value = -30.0
response_mutate_power = 0.0
response_mutate_rate = 0.0
response_replace_rate = 0.0
weight_init_mean = 0.0
weight_init_stdev = 1.0
weight_init_type = gaussian
weight_max_value = 30
weight_min_value = -30
weight_mutate_power = 0.5
weight_mutate_rate = 0.8
weight_replace_rate = 0.1
enabled_default = True
enabled_mutate_rate = 0.01
enabled_rate_to_false_add = 0.0
enabled_rate_to_true_add = 0.0
single_structural_mutation = False
structural_mutation_surer = default
node_gene_type = DefaultNodeGene
connection_gene_type = DefaultConnectionGene
[DefaultSpeciesSet]
compatibility_threshold = 3.0
[DefaultStagnation]
species_fitness_func = max
max_stagnation = 15
species_elitism = 2
[DefaultReproduction]
elitism = 2
survival_threshold = 0.2
min_species_size = 2
"""

def run_neat(T, pop, gens, seed):
    import neat
    random.seed(seed); np.random.seed(seed)
    cols = [FI[f] for f in NEAT_IN]; Z = T["X"][:, cols].astype(np.float64)
    tr = T["period"] == 0
    mu, sd = Z[tr].mean(0), Z[tr].std(0) + 1e-9            # scaled with search-period statistics only
    Z = (Z - mu) / sd
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".neat.cfg")
    open(path, "w").write(NEAT_CFG.format(pop=pop, nin=len(cols)))
    cfg = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet, neat.DefaultStagnation, path)
    acts = {"tanh": np.tanh, "relu": lambda x: np.maximum(0, x), "sigmoid": lambda x: 1 / (1 + np.exp(-np.clip(5 * x, -60, 60)))}
    def decide(genome, rows=None):
        net = neat.nn.FeedForwardNetwork.create(genome, cfg)
        vals = {-(k + 1): (Z[:, k] if rows is None else Z[rows, k]) for k in range(len(cols))}
        n = len(Z) if rows is None else len(rows)
        for node, act, agg, bias, resp, links in net.node_evals:
            s = np.zeros(n)
            for i, w in links: s = s + w * vals[i]
            vals[node] = acts.get(act.__name__.replace("_activation", ""), np.tanh)(bias + resp * s)
        return vals[net.output_nodes[0]] > 0.5
    hall = {}
    def fitness(genomes, config):
        for gid_, g in genomes:
            rows = first_bets(T, decide(g)); s = stats(T["net"][rows[T["period"][rows] == 0]])
            g.fitness = s["t"] if s["n"] >= MIN_TRAIN else -10 + s["n"] / MIN_TRAIN
            if s["n"] >= MIN_TRAIN: hall[gid_] = (g.fitness, g)
    p = neat.Population(cfg)
    gen = [0]
    class Rep(neat.reporting.BaseReporter):
        def post_evaluate(self, config, population, species, best):
            gen[0] += 1
            if gen[0] % 5 == 0: log(f"NEAT gen {gen[0]}: best train t {best.fitness:.2f}, {len(species.species)} species")
    p.add_reporter(Rep())
    p.run(fitness, gens)
    os.remove(path)
    top = sorted(hall.values(), key=lambda x: -x[0])[:40]
    out = []
    for fit, g in top:
        rows = first_bets(T, decide(g)); per = by_period(T, rows)
        out.append(dict(nodes=len(g.nodes), conns=sum(1 for c in g.connections.values() if c.enabled), train=per[0], valid=per[1], test=per[2], rows=rows))
    return out, cfg

# ---------------------------------------------------------------- 3. gradient-boosted model vs the market
def run_gbm(T):
    from sklearn.ensemble import HistGradientBoostingClassifier
    X = np.column_stack([T["X"], T["sport"], T["league"]]).astype(np.float32)
    tr, va, te = (T["period"] == k for k in (0, 1, 2))
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
                                       categorical_features=[X.shape[1] - 2, X.shape[1] - 1], random_state=0)
    m.fit(X[tr], T["won"][tr])
    prob = m.predict_proba(X)[:, 1]
    fill = T["X"][:, FI["fill"]] / 100
    brier = lambda a, y: float(np.mean((a - y) ** 2))
    y = T["won"].astype(float)
    calib = dict(model_valid=brier(prob[va], y[va]), market_valid=brier(fill[va], y[va]), model_test=brier(prob[te], y[te]), market_test=brier(fill[te], y[te]))
    fee = 0.07 * (1 - fill)                     # Kalshi's fee per $1 staked, roughly
    edge = prob - fill - fee * fill
    best = None
    for tau in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12):
        rows = first_bets(T, edge >= tau); per = by_period(T, rows)
        if per[1]["n"] >= MIN_VALID and (best is None or per[1]["t"] > best[1][1]["t"]): best = (tau, per, rows)
    return dict(calib=calib, tau=best[0], train=best[1][0], valid=best[1][1], test=best[1][2]), best[2]

# ---------------------------------------------------------------- putting it together
def curve(T, rows):
    rows = rows[T["period"][rows] == 2]; rows = rows[np.argsort(T["ts"][rows], kind="stable")]
    c = np.cumsum(T["net"][rows]); step = max(1, len(c) // 120)
    return [round(float(v), 1) for v in c[::step]] + ([round(float(c[-1]), 1)] if len(c) else [])

def bh(pvals, q=0.10):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i]); keep = 0
    for k, i in enumerate(order, 1):
        if pvals[i] <= q * k / len(pvals): keep = k
    return set(order[:keep])

def main():
    t0 = time.time(); T = build_table()
    log(f"{len(T['net']):,} decision points from {T['ngames']:,} games; split dates {T['dates']}")
    # GA: several independent islands with different seeds
    islands = [(1, 160, 25, 2000)] if QUICK else [(s, 400, 80, 10000) for s in range(1, 7)]
    pool = {}
    for seed, pn, gens, rn in islands:
        R = run_ga(T, seed, pn, gens, rn); pool.update(R.cache)
    evaluated = len(pool)
    ranked = sorted((v for v in pool.values() if v[1]["n"] >= MIN_TRAIN), key=lambda v: -v[1]["t"])
    train_good = [v for v in ranked if v[1]["t"] >= 2]
    log(f"GA: {evaluated:,} distinct rules scored, {len(train_good):,} with train t >= 2")
    R = Rules(T, random.Random(0))
    cand = []
    for fit, s, g in ranked[:400]:
        rows = first_bets(T, R.mask(g)); per = by_period(T, rows)
        if per[1]["n"] >= MIN_VALID and per[1]["t"] >= 2 and per[0]["t"] >= 2: cand.append((per, g, rows))
    # send up to 25 distinct validated rules to the test, most convincing first, skipping near-duplicates
    cand.sort(key=lambda c: -c[0][1]["t"]); chosen = []
    for per, g, rows in cand:
        gs = set(T["gid"][rows].tolist())
        if any(len(gs & o) / max(1, len(gs | o)) > 0.6 for _, _, _, o in chosen): continue
        chosen.append((per, g, rows, gs))
        if len(chosen) >= 25: break
    passed = {k for k in bh([c[0][2]["p"] if c[0][2]["n"] >= MIN_TEST else 1.0 for c in chosen], q=0.05) if chosen[k][0][2]["t"] >= 2}
    rules = [dict(rule=describe(T, g), train=per[0], valid=per[1], test=per[2], confirmed=k in passed, validated=True, curve=curve(T, rows))
             for k, (per, g, rows, _) in enumerate(chosen)]
    # Near misses: the best of the rest by validation alone, shown so you can see how close anything came.
    # They were not sent to the test, so their test numbers are for display only and don't count in the correction.
    near = []
    for fit, s_, g in ranked[:400]:
        rows = first_bets(T, R.mask(g)); per = by_period(T, rows)
        if per[1]["n"] < MIN_VALID or any(r["rule"] == describe(T, g) for r in rules): continue
        gs = set(T["gid"][rows].tolist())
        if any(len(gs & o) / max(1, len(gs | o)) > 0.6 for _, _, o in near): continue
        near.append((per, g, gs))
    near.sort(key=lambda x: -x[0][1]["t"])
    rules += [dict(rule=describe(T, g), train=per[0], valid=per[1], test=per[2], confirmed=False, validated=False, curve=curve(T, first_bets(T, R.mask(g))))
              for per, g, _ in near[:max(0, 15 - len(rules))]]
    log(f"GA: {len(cand)} validated, {len(chosen)} sent to test, {len(passed)} confirmed")
    # null distribution: what random rules do on the test games
    rnd = random.Random(99); null = []
    while len(null) < (200 if QUICK else 1000):
        g = R.random(); rows = first_bets(T, R.mask(g)); s = stats(T["net"][rows[T["period"][rows] == 2]])
        if s["n"] >= MIN_TEST: null.append(round(s["roi"], 4))
    # NEAT
    neat_out, _ = run_neat(T, NEAT_POP, NEAT_GENS, 5)
    nv = [x for x in neat_out if x["valid"]["n"] >= MIN_VALID]
    nbest = max(nv, key=lambda x: x["valid"]["t"]) if nv else None
    neat_res = None
    if nbest:
        neat_res = dict(nodes=nbest["nodes"], conns=nbest["conns"], train=nbest["train"], valid=nbest["valid"], test=nbest["test"],
                        confirmed=nbest["test"]["t"] >= 2 and nbest["test"]["n"] >= MIN_TEST, curve=curve(T, nbest["rows"]),
                        evolved=NEAT_POP * NEAT_GENS, best_train=[dict(train=x["train"], valid=x["valid"]) for x in neat_out[:12]])
        log(f"NEAT best by validation: train {nbest['train']['roi']:+.1%} valid {nbest['valid']['roi']:+.1%} test {nbest['test']['roi']:+.1%} ({nbest['test']['n']} bets)")
    # GBM
    gbm, grows = run_gbm(T); gbm["curve"] = curve(T, grows)
    log(f"GBM: Brier model {gbm['calib']['model_test']:.4f} vs market {gbm['calib']['market_test']:.4f}; test {gbm['test']['roi']:+.1%} on {gbm['test']['n']} bets")
    # simple baselines on the test games
    def base(mask):
        rows = first_bets(T, mask); return by_period(T, rows)[2]
    X = T["X"]
    baselines = {"Every pre-game favorite": base((X[:, FI["elapsed"]] == -5) & (X[:, FI["is_fav"]] == 1)),
                 "Every pre-game underdog": base((X[:, FI["elapsed"]] == -5) & (X[:, FI["is_fav"]] == 0)),
                 "Every team at 90¢+ in-game": base((X[:, FI["elapsed"]] > 0) & (X[:, FI["fill"]] >= 90)),
                 "Every team at 10¢ or less in-game": base((X[:, FI["elapsed"]] > 0) & (X[:, FI["fill"]] <= 10))}
    clean = lambda d: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
    for r in rules:
        for k in ("train", "valid", "test"): r[k] = clean(r[k])
    out = dict(built=time.strftime("%Y-%m-%d"), quick=QUICK, points=len(T["net"]), games=T["ngames"], dates=T["dates"], split=SPLITS,
               funnel=dict(evaluated=evaluated, train_good=len(train_good), validated=len(cand), tested=len(chosen), confirmed=len(passed)),
               rules=rules, null=null, neat=neat_res, gbm=gbm, baselines={k: clean(v) for k, v in baselines.items()},
               minutes=round((time.time() - t0) / 60, 1))
    os.makedirs(os.path.join(E.ROOT, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(E.ROOT, "results", "evolved.json"), "w"), indent=1, default=float)
    with open(os.path.join(E.DATA, "evolved.js"), "w") as f:
        f.write("window.EVOLVED="); json.dump(out, f, separators=(",", ":"), default=float); f.write(";\n")
    log(f"done in {out['minutes']} min; funnel {out['funnel']}")
    for r in rules[:10]:
        print(("CONFIRMED " if r["confirmed"] else "          ") + r["rule"], "| train", f"{r['train']['roi']:+.1%}", r["train"]["n"],
              "| valid", f"{r['valid']['roi']:+.1%}", r["valid"]["n"], "| test", f"{r['test']['roi']:+.1%}", r["test"]["n"], f"t={r['test']['t']:.1f}")

if __name__ == "__main__":
    main()
