"""Backtest the results model: for each round from 4 on, fit on earlier games only,
predict that round, score against what happened (log-loss; lower is better)."""
import math, itertools, sys
from datetime import timedelta
import perf

M = sorted(perf.load(sys.argv[1] if len(sys.argv) > 1 else 'results.csv'), key=lambda m: m['date'])
TEAMS = sorted(perf.NAMES.values())
# group into rounds by date gaps (matchweeks)
rounds, cur = [], []
for m in M:
    if cur and (m['date'] - cur[-1]['date']).days > 3: rounds.append(cur); cur = []
    cur.append(m)
rounds.append(cur)

def outcome(m): return 0 if m['hg'] > m['ag'] else (1 if m['hg'] == m['ag'] else 2)

def score(params, start=3):
    ll, n = 0.0, 0
    for k in range(start, len(rounds)):
        train = [m for r in rounds[:k] for m in r]
        P = perf.fit(train, TEAMS, rounds[k][0]['date'], **params)
        for m in rounds[k]:
            p = perf.wdl(P, m['home'], m['away'])[outcome(m)]
            ll -= math.log(max(p, 1e-9)); n += 1
    return ll / n, n

if __name__ == '__main__':
    print('rounds:', [len(r) for r in rounds])
    # no-skill baseline: home/draw/away frequencies from the training rounds
    base, n = 0.0, 0
    for k in range(3, len(rounds)):
        train = [m for r in rounds[:k] for m in r]; c = [0, 0, 0]
        for m in train: c[outcome(m)] += 1
        for m in rounds[k]: base -= math.log((c[outcome(m)] + 1) / (len(train) + 3)); n += 1
    print('baseline (home/draw/away rates): %.4f over %d matches' % (base / n, n))
    res = []
    for gw, hl, rg in itertools.product((1.0, 0.7, 0.5, 0.3), (30, 60, 120, 1e9), (1, 2, 4, 8)):
        s, n = score({'goal_w':gw, 'half_life':hl, 'ridge':rg}); res.append((s, gw, hl, rg))
    res.sort()
    for s, gw, hl, rg in res[:8]:
        print('logloss %.4f  goals_weight %.1f  half_life %s  shrink %g' % (s, gw, 'none' if hl > 1e8 else int(hl), rg))
    print('worst: %.4f' % res[-1][0])
    print('goals-only best: %.4f' % min(r[0] for r in res if r[1] == 1.0))
