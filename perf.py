"""Results-based team model: attack/defence ratings from this season's matches.

Each match is scored with 'performance goals': a blend of real goals and shots on
target (converted at the league's goals-per-shot-on-target rate), because shots
are steadier than goals over a handful of games. Recent games count more.
Ratings are pulled toward average so 8 games can't produce wild numbers.
Win/draw/loss comes from a Poisson score grid with a Dixon-Coles low-score
adjustment, so every matchup gets its own draw chance.
"""
import csv, math
from datetime import date
import numpy as np
from scipy.optimize import minimize, minimize_scalar

NAMES = {'Arsenal':'Arsenal','Aston Villa':'Villa','Bournemouth':'Bournemouth','Brentford':'Brentford',
         'Brighton':'Brighton','Chelsea':'Chelsea','Coventry':'Coventry','Crystal Palace':'Palace',
         'Everton':'Everton','Fulham':'Fulham','Hull':'Hull','Ipswich':'Ipswich','Leeds':'Leeds',
         'Liverpool':'Liverpool','Man City':'Man City','Man United':'Man Utd','Newcastle':'Newcastle',
         "Nott'm Forest":'Forest','Sunderland':'Sunderland','Tottenham':'Spurs'}

def load(path):
    out = []
    for r in csv.DictReader(open(path)):
        d, m, y = map(int, r['Date'].split('/'))
        out.append({'date':date(y,m,d), 'home':NAMES[r['HomeTeam']], 'away':NAMES[r['AwayTeam']],
                    'hg':int(r['FTHG']), 'ag':int(r['FTAG']), 'hst':int(r['HST']), 'ast':int(r['AST'])})
    return out

def fit(matches, teams, asof, goal_w=0.5, half_life=60.0, ridge=2.0):
    idx = {t:i for i,t in enumerate(teams)}; n = len(teams)
    conv = sum(m['hg']+m['ag'] for m in matches) / max(1, sum(m['hst']+m['ast'] for m in matches))
    H = np.array([idx[m['home']] for m in matches]); A = np.array([idx[m['away']] for m in matches])
    yh = np.array([goal_w*m['hg'] + (1-goal_w)*conv*m['hst'] for m in matches])
    ya = np.array([goal_w*m['ag'] + (1-goal_w)*conv*m['ast'] for m in matches])
    w = np.array([0.5 ** ((asof - m['date']).days / half_life) for m in matches])
    def nll(x):
        mu, hm = x[0], x[1]; att = x[2:2+n]; de = x[2+n:]
        lh = mu + hm + att[H] - de[A]; la = mu + att[A] - de[H]
        f = -np.sum(w*(yh*lh - np.exp(lh) + ya*la - np.exp(la)))
        return f + ridge*(np.sum(att**2) + np.sum(de**2))
    def grad(x):
        mu, hm = x[0], x[1]; att = x[2:2+n]; de = x[2+n:]
        lh = mu + hm + att[H] - de[A]; la = mu + att[A] - de[H]
        rh = w*(np.exp(lh) - yh); ra = w*(np.exp(la) - ya)
        g = np.zeros_like(x); g[0] = rh.sum() + ra.sum(); g[1] = rh.sum()
        ga = np.bincount(H, rh, n) + np.bincount(A, ra, n); gd = -np.bincount(A, rh, n) - np.bincount(H, ra, n)
        g[2:2+n] = ga + 2*ridge*att; g[2+n:] = gd + 2*ridge*de
        return g
    x0 = np.zeros(2 + 2*n); x0[0] = math.log(1.35)
    x = minimize(nll, x0, jac=grad, method='L-BFGS-B').x
    P = {'mu':float(x[0]), 'home':float(x[1]), 'att':{t:float(x[2+i]) for i,t in enumerate(teams)},
         'def':{t:float(x[2+n+i]) for i,t in enumerate(teams)}, 'rho':0.0}
    # Dixon-Coles rho from real (integer) scores, given the fitted rates
    def rho_nll(rho):
        s = 0
        for m, wi in zip(matches, w):
            lh, la = rates(P, m['home'], m['away'])
            s -= wi * math.log(max(1e-9, tau(m['hg'], m['ag'], lh, la, rho)))
        return s
    P['rho'] = float(minimize_scalar(rho_nll, bounds=(-0.2, 0.2), method='bounded').x)
    return P

def rates(P, home, away):
    return (math.exp(P['mu'] + P['home'] + P['att'][home] - P['def'][away]),
            math.exp(P['mu'] + P['att'][away] - P['def'][home]))

def tau(x, y, lh, la, rho):
    if x == 0 and y == 0: return 1 - lh*la*rho
    if x == 0 and y == 1: return 1 + lh*rho
    if x == 1 and y == 0: return 1 + la*rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0

def wdl(P, home, away, maxg=10):
    lh, la = rates(P, home, away)
    ph = [math.exp(-lh) * lh**k / math.factorial(k) for k in range(maxg+1)]
    pa = [math.exp(-la) * la**k / math.factorial(k) for k in range(maxg+1)]
    H = D = A = 0.0
    for i in range(maxg+1):
        for j in range(maxg+1):
            p = ph[i]*pa[j]*tau(i, j, lh, la, P['rho'])
            if i > j: H += p
            elif i == j: D += p
            else: A += p
    s = H + D + A
    return H/s, D/s, A/s

def form(matches, teams, k=5):
    out = {t:[] for t in teams}
    for m in sorted(matches, key=lambda m: m['date']):
        for t, gf, ga, home, opp in ((m['home'], m['hg'], m['ag'], True, m['away']), (m['away'], m['ag'], m['hg'], False, m['home'])):
            out[t].append({'r':'W' if gf > ga else ('D' if gf == ga else 'L'), 'gf':gf, 'ga':ga, 'home':home, 'opp':opp})
    return {t:v[-k:] for t,v in out.items()}
