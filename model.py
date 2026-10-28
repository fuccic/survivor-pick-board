"""Survivor pick model — 'how we pick'.

1. Ratings: fit team strengths to recent bookmaker prices (overround removed),
   lightly pulled toward Opta's preseason points projection.
2. This week: use the actual bookmaker price. A pick only fails on a LOSS (draws are free).
3. Future weeks: model probabilities from the fitted ratings.
4. Season plan: assign each unused team to at most one remaining round (Hungarian
   algorithm on lose-probability), then improve with pairwise swaps.
5. Rank this week's options by lose% now AND by how much using them now hurts the plan.
6. Stress-test the top pick with rating noise and alternate home advantage.
"""
import json, sys, random
from fractions import Fraction as F
import numpy as np
from scipy.optimize import minimize, linear_sum_assignment

OUT = sys.argv[1]
FX = sys.argv[2]

TEAMS = ['Arsenal','Villa','Bournemouth','Brentford','Brighton','Chelsea','Coventry','Palace','Everton',
         'Fulham','Hull','Ipswich','Leeds','Liverpool','Man City','Man Utd','Newcastle','Forest','Sunderland','Spurs']
ALIAS = {'Arsenal FC':'Arsenal','Aston Villa FC':'Villa','AFC Bournemouth':'Bournemouth','Brentford FC':'Brentford',
         'Brighton & Hove Albion FC':'Brighton','Chelsea FC':'Chelsea','Coventry City FC':'Coventry',
         'Crystal Palace FC':'Palace','Everton FC':'Everton','Fulham FC':'Fulham','Hull City AFC':'Hull',
         'Ipswich Town FC':'Ipswich','Leeds United FC':'Leeds','Liverpool FC':'Liverpool',
         'Manchester City FC':'Man City','Manchester United FC':'Man Utd','Newcastle United FC':'Newcastle',
         'Nottingham Forest FC':'Forest','Sunderland AFC':'Sunderland','Tottenham Hotspur FC':'Spurs'}

# ---- pool state ----
USED = ['Arsenal','Coventry','Man City','Chelsea','Everton','Man Utd','Spurs','Brentford']
LIVES = 2
CUR, LAST = 9, 19
HISTORY = [
    {'round':'1–5','team':'Arsenal, Coventry, Man City, Chelsea, Everton','result':'Coventry lost — 1 life gone','lives':2},
    {'round':6,'team':'Man Utd','opp':'Spurs','home':True,'score':'1–1','result':'D','lives':2},
    {'round':7,'team':'Spurs','opp':'Coventry','home':True,'score':'3–1','result':'W','lives':2},
    {'round':8,'team':'Brentford','opp':'Hull','home':False,'score':'1–1','result':'D','lives':2},
]

# ---- prices ----
def frac(*v):
    p = np.array([1/(float(F(x))+1) for x in v]); return p/p.sum()
def amer(*v):
    def ip(a): return 100/(a+100) if a > 0 else -a/(-a+100)
    p = np.array([ip(x) for x in v]); return p/p.sum()

MW7 = {('Everton','Chelsea'):frac('11/5','14/5','5/4'),('Brentford','Liverpool'):frac('6/4','11/4','15/8'),
       ('Fulham','Hull'):frac('3/4','3/1','4/1'),('Man City','Ipswich'):frac('5/19','13/2','23/2'),
       ('Newcastle','Villa'):frac('13/10','14/5','21/10'),('Bournemouth','Sunderland'):frac('22/19','13/5','13/5'),
       ('Brighton','Palace'):frac('6/11','18/5','5/1'),('Leeds','Man Utd'):frac('11/8','27/10','2/1'),
       ('Forest','Arsenal'):frac('5/1','3/1','4/6'),('Spurs','Coventry'):frac('1/2','15/4','31/5')}
MW8 = {('Ipswich','Forest'):frac('11/5','13/5','13/10'),('Villa','Man City'):frac('17/5','16/5','8/11'),
       ('Arsenal','Everton'):frac('2/5','19/5','77/10'),('Coventry','Fulham'):frac('19/10','13/5','13/10'),
       ('Chelsea','Spurs'):frac('4/5','16/5','33/10'),('Palace','Newcastle'):frac('15/8','11/4','7/5'),
       ('Hull','Brentford'):frac('17/5','3/1','3/4'),('Liverpool','Brighton'):frac('11/10','3/1','23/10'),
       ('Man Utd','Bournemouth'):frac('6/7','3/1','29/10'),('Sunderland','Leeds'):frac('19/10','12/5','6/4')}
# Round 9: DraftKings (Man City–Brighton and Newcastle–Everton from LetsBetMD, the only full markets)
MW9 = {('Chelsea','Man Utd'):amer(-130,300,310),('Man City','Brighton'):amer(-154,335,360),
       ('Bournemouth','Leeds'):amer(110,240,245),('Brentford','Forest'):amer(105,265,240),
       ('Coventry','Sunderland'):amer(205,230,135),('Hull','Ipswich'):amer(160,240,165),
       ('Spurs','Palace'):amer(-189,350,450),('Villa','Fulham'):amer(100,265,250),
       ('Liverpool','Arsenal'):amer(200,255,125),('Newcastle','Everton'):amer(125,260,200)}
CALIB = {}
for w, mw in ((0.6, MW7), (0.8, MW8), (1.0, MW9)):
    for k, v in mw.items(): CALIB[k] = (v, w)

# Opta preseason projection (Aug 26); teams the article didn't list get the league mean
OPTA = {'Arsenal':74.8,'Man City':68.44,'Liverpool':61.42,'Chelsea':58.48,'Man Utd':55.34,'Brighton':55.21,
        'Newcastle':52.98,'Villa':52.98,'Brentford':52.75,'Everton':51.99,'Palace':45.81,'Ipswich':45.44,
        'Forest':44.44,'Coventry':44.25,'Hull':44.10,'Fulham':43.37,'Sunderland':43.02}
mu = np.mean(list(OPTA.values()))
Z = np.array([(OPTA.get(t, mu) - mu) / 10 for t in TEAMS])

sig = lambda x: 1/(1+np.exp(-x))
def probs(rh, ra, h, c):
    d = rh - ra + h; pH = sig(d - c); pA = sig(-d - c); return pH, 1 - pH - pA, pA

IDX = {t:i for i,t in enumerate(TEAMS)}
def fit(lam=0.05):
    n = len(TEAMS)
    def err(x):
        r = x[:n]; h, c, s = x[n:]
        e = 0
        for (a,b),(p,w) in CALIB.items():
            e += w*np.sum((np.array(probs(r[IDX[a]], r[IDX[b]], h, c)) - p)**2)
        return e + lam*np.sum((r - s*Z)**2) + 10*np.mean(r)**2
    x0 = np.concatenate([Z*0.8, [0.25, 0.55, 0.8]])
    res = minimize(err, x0, method='L-BFGS-B')
    r = res.x[:n]; h, c, s = res.x[n:]
    resid = np.sqrt(sum(w*np.sum((np.array(probs(r[IDX[a]], r[IDX[b]], h, c)) - p)**2)
                        for (a,b),(p,w) in CALIB.items()) / (3*len(CALIB)))
    return {t:float(r[IDX[t]]) for t in TEAMS}, float(h), float(c), float(resid)

# ---- fixtures ----
d = json.load(open(FX)); FIX = {}
for x in d['matches']:
    rd = int(x['round'].split()[-1])
    if CUR <= rd <= LAST:
        a, b = ALIAS[x['team1']], ALIAS[x['team2']]
        FIX[(rd,a)] = (b, True, x['date']); FIX[(rd,b)] = (a, False, x['date'])
ROUNDS = list(range(CUR, LAST+1))
AVAIL = [t for t in TEAMS if t not in USED]

def outcome(R, h, c, rd, t):
    o, home, _ = FIX[(rd,t)]
    if rd == CUR:
        H, D, A = MW9[(t,o) if home else (o,t)]
    else:
        H, D, A = probs(R[t], R[o], h, c) if home else probs(R[o], R[t], h, c)
    return (float(H), float(D), float(A)) if home else (float(A), float(D), float(H))  # (win, draw, lose) for t

def lose_matrix(R, h, c):
    return {(t,rd): outcome(R,h,c,rd,t)[2] for t in AVAIL for rd in ROUNDS}

def survival(plan, L):
    """plan: {round: team}. Returns (expected rounds survived, P(alive at end), dist of lives left)."""
    dist = np.zeros(LIVES+1); dist[LIVES] = 1.0; tot = 0.0
    for rd in ROUNDS:
        p = L[(plan[rd], rd)]; new = np.zeros(LIVES+1)
        for k in range(1, LIVES+1):
            new[k] += dist[k]*(1-p); new[k-1] += dist[k]*p
        new[0] += dist[0]; dist = new; tot += 1 - dist[0]
    return tot, 1 - dist[0], dist

def solve(L, force=None):
    teams = AVAIL; nR = len(ROUNDS)
    C = np.zeros((len(teams), max(nR, len(teams))))
    for i,t in enumerate(teams):
        for j,rd in enumerate(ROUNDS): C[i,j] = L[(t,rd)]
    if force:
        i = teams.index(force); C[i,:] += 10; C[i,0] -= 10; C[:,0] += 10; C[i,0] -= 10
    ri, ci = linear_sum_assignment(C)
    plan = {ROUNDS[j]: teams[i] for i,j in zip(ri,ci) if j < nR}
    # pairwise swap / substitute improvement on expected rounds survived
    best = survival(plan, L)[0]; improved = True
    while improved:
        improved = False
        for a in ROUNDS:
            if force and a == CUR: continue
            for b in ROUNDS:
                if b <= a or (force and b == CUR): continue
                p2 = dict(plan); p2[a], p2[b] = plan[b], plan[a]
                v = survival(p2, L)[0]
                if v > best + 1e-9: plan, best, improved = p2, v, True
            for t in teams:
                if t in plan.values(): continue
                if force and a == CUR: continue
                p2 = dict(plan); p2[a] = t
                v = survival(p2, L)[0]
                if v > best + 1e-9: plan, best, improved = p2, v, True
    return plan

def rank_week(R, h, c):
    L = lose_matrix(R, h, c)
    rows, plans = [], {}
    for t in AVAIL:
        p = solve(L, force=t); s = survival(p, L); plans[t] = p
        w, dr, lo = outcome(R, h, c, CUR, t)
        rows.append({'team':t, 'win':w, 'draw':dr, 'lose':lo, 'expRounds':s[0], 'pEnd':s[1],
                     'plan':[{'round':rd,'team':p[rd],'lose':L[(p[rd],rd)]} for rd in ROUNDS]})
    rows.sort(key=lambda r: -r['expRounds'])
    best = rows[0]['expRounds']
    for r in rows: r['planCost'] = best - r['expRounds']   # expected rounds given up vs the best start
    base = plans[rows[0]['team']]
    return rows, base, L, survival(base, L)

R, h, c, resid = fit()
rows, plan, L, S = rank_week(R, h, c)
top = rows[0]['team']

# ---- stress tests ----
stress = []
def top_pick(Rx, hx, cx):
    return rank_week(Rx, hx, cx)[0][0]['team']
for hh in (h - 0.12, h + 0.12):
    stress.append({'label':'Home advantage %s' % ('lower' if hh < h else 'higher'), 'pick':top_pick(R, hh, c)})
for lam in (0.01, 0.3):
    Rx, hx, cx, _ = fit(lam)
    stress.append({'label':'%s pull toward Opta' % ('Weaker' if lam < 0.05 else 'Stronger'), 'pick':top_pick(Rx, hx, cx)})
random.seed(7); np.random.seed(7); N = 60; hits = {}
for _ in range(N):
    Rx = {t: R[t] + np.random.normal(0, 0.15) for t in TEAMS}
    tp = top_pick(Rx, h, c); hits[tp] = hits.get(tp, 0) + 1
mc = sorted(({'team':k,'share':v/N} for k,v in hits.items()), key=lambda x:-x['share'])

# ---- export ----
grid = []
for t in AVAIL:
    grid.append({'team':t, 'cells':[{'round':rd, 'opp':FIX[(rd,t)][0], 'home':FIX[(rd,t)][1],
                                      'lose':L[(t,rd)]} for rd in ROUNDS]})
out = {
    'updated':'2026-10-28', 'round':CUR, 'lastRound':LAST, 'lives':LIVES, 'livesStart':3,
    'entrants':104, 'used':USED, 'available':AVAIL, 'history':HISTORY,
    'rules':['3 lives; a loss costs one','Draws are free','Each team once per half-season (rounds 1–19)'],
    'thisWeek':[{**r,
                 'opp':FIX[(CUR,r['team'])][0], 'home':FIX[(CUR,r['team'])][1], 'date':FIX[(CUR,r['team'])][2]}
                for r in rows],
    'plan':[{'round':rd, 'team':plan[rd], 'opp':FIX[(rd,plan[rd])][0], 'home':FIX[(rd,plan[rd])][1],
             'lose':L[(plan[rd],rd)]} for rd in ROUNDS],
    'skipped':[t for t in AVAIL if t not in plan.values()],
    'survival':{'expRounds':S[0], 'pEnd':S[1], 'livesLeft':{str(k):float(S[2][k]) for k in range(LIVES+1)}},
    'grid':grid, 'ratings':sorted(({'team':t,'r':R[t]} for t in TEAMS), key=lambda x:-x['r']),
    'model':{'homeAdv':h, 'drawWidth':c, 'fitError':resid, 'calibMatches':len(CALIB)},
    'stress':{'scenarios':stress, 'monteCarlo':mc, 'runs':N},
    'sources':[{'title':'Sports betting odds, week 9 (RG.org)','url':'https://rg.org/news/soccer/liverpool-vs-arsenal-chelsea-vs-man-utd-premier-league-week-9-odds-2026'},
               {'title':'openfootball 2026-27 fixtures','url':'https://github.com/openfootball/football.json'},
               {'title':'Opta preseason projection (SI)','url':'https://www.si.com/soccer/supercomputer-predicts-final-2026-27-premier-league-table-arsenal-perfect-start'},
               {'title':'Hull 1–1 Brentford (theScore)','url':'https://www.thescore.com/epl/event/98338'}],
}
json.dump(out, open(OUT,'w'), indent=1)
print('fit: h=%.3f c=%.3f resid=%.4f' % (h, c, resid))
for r in rows:
    print('%-11s v %-11s %s  W%.2f D%.2f L%.2f  cost %+.3f  expR %.2f' % (r['team'], FIX[(CUR,r['team'])][0],
          'H' if FIX[(CUR,r['team'])][1] else 'A', r['win'], r['draw'], r['lose'], -r['planCost'], r['expRounds']))
print('plan:', [(p, plan[p], round(L[(plan[p],p)],2)) for p in ROUNDS], 'skip', out['skipped'])
print('survival', S[0], S[1], S[2])
print('stress', stress, mc)
