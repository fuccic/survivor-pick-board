/* Survivor pick engine — the in-browser version of model.py's planner.
   Given model data (ratings, fixtures, this week's market odds) and a player's
   used teams, lives and draw rule, it ranks this week's options, builds the
   season plan, and stress-tests the top pick. */
(function (root) {
  var sig = function (x) { return 1 / (1 + Math.exp(-x)); };
  function probs(rh, ra, h, c) {
    var d = rh - ra + h, pH = sig(d - c), pA = sig(-d - c);
    return [pH, 1 - pH - pA, pA];
  }

  // results model: Poisson score grid with Dixon-Coles low-score adjustment (mirrors perf.py)
  var FACT = [1]; for (var f = 1; f <= 10; f++) FACT[f] = FACT[f - 1] * f;
  function rates(G, home, away) {
    return [Math.exp(G.mu + G.home + G.att[home] - G.def[away]), Math.exp(G.mu + G.att[away] - G.def[home])];
  }
  function tau(x, y, lh, la, rho) {
    if (x === 0 && y === 0) return 1 - lh * la * rho;
    if (x === 0 && y === 1) return 1 + lh * rho;
    if (x === 1 && y === 0) return 1 + la * rho;
    if (x === 1 && y === 1) return 1 - rho;
    return 1;
  }
  function goalsWDL(G, home, away) {
    var r = rates(G, home, away), lh = r[0], la = r[1], H = 0, D = 0, A = 0, ph = [], pa = [];
    for (var k = 0; k <= 10; k++) { ph[k] = Math.exp(-lh) * Math.pow(lh, k) / FACT[k]; pa[k] = Math.exp(-la) * Math.pow(la, k) / FACT[k]; }
    for (var i = 0; i <= 10; i++) for (var j = 0; j <= 10; j++) {
      var p = ph[i] * pa[j] * tau(i, j, lh, la, G.rho);
      if (i > j) H += p; else if (i === j) D += p; else A += p;
    }
    var s = H + D + A; return [H / s, D / s, A / s];
  }

  // chance team t "fails" in each round: loss, or loss+draw if draws count as a loss.
  // This week: market odds. Later weeks: blend of odds-based ratings and the results model.
  function outcomes(E, R, h, drawsLose, G, bw) {
    G = G || E.goals; bw = bw == null ? E.blend : bw;
    var out = {}, cache = {};
    var blend = function (home, away) {
      var k = home + '|' + away; if (cache[k]) return cache[k];
      var pm = probs(R[home], R[away], h, E.c), pg = bw < 1 ? goalsWDL(G, home, away) : [0, 0, 0];
      return (cache[k] = [bw * pm[0] + (1 - bw) * pg[0], bw * pm[1] + (1 - bw) * pg[1], bw * pm[2] + (1 - bw) * pg[2]]);
    };
    E.teams.forEach(function (t) {
      out[t] = {};
      E.fixtures[t].forEach(function (f) {
        var w, d, l;
        if (f.round === E.round) { w = E.market[t][0]; d = E.market[t][1]; l = E.market[t][2]; }
        else {
          var p = f.home ? blend(t, f.opp) : blend(f.opp, t);
          if (f.home) { w = p[0]; d = p[1]; l = p[2]; } else { w = p[2]; d = p[1]; l = p[0]; }
        }
        out[t][f.round] = { win: w, draw: d, lose: l, fail: drawsLose ? l + d : l };
      });
    });
    return out;
  }

  // Hungarian algorithm: rows (rounds) to columns (teams), rows <= cols. Returns col index per row.
  function hungarian(a) {
    var n = a.length, m = a[0].length, INF = 1e18;
    var u = new Array(n + 1).fill(0), v = new Array(m + 1).fill(0), p = new Array(m + 1).fill(0), way = new Array(m + 1).fill(0);
    for (var i = 1; i <= n; i++) {
      p[0] = i; var j0 = 0, minv = new Array(m + 1).fill(INF), used = new Array(m + 1).fill(false);
      do {
        used[j0] = true; var i0 = p[j0], delta = INF, j1 = 0;
        for (var j = 1; j <= m; j++) if (!used[j]) {
          var cur = a[i0 - 1][j - 1] - u[i0] - v[j];
          if (cur < minv[j]) { minv[j] = cur; way[j] = j0; }
          if (minv[j] < delta) { delta = minv[j]; j1 = j; }
        }
        for (j = 0; j <= m; j++) { if (used[j]) { u[p[j]] += delta; v[j] -= delta; } else minv[j] -= delta; }
        j0 = j1;
      } while (p[j0] !== 0);
      do { var jj = way[j0]; p[j0] = p[jj]; j0 = jj; } while (j0);
    }
    var ans = new Array(n);
    for (var j2 = 1; j2 <= m; j2++) if (p[j2]) ans[p[j2] - 1] = j2 - 1;
    return ans;
  }

  // expected rounds survived and lives-left distribution for a plan {round: team|null}
  function survival(plan, rounds, O, lives) {
    var dist = new Array(lives + 1).fill(0); dist[lives] = 1; var tot = 0;
    rounds.forEach(function (rd) {
      var t = plan[rd], p = t ? O[t][rd].fail : 1, n = new Array(lives + 1).fill(0);
      for (var k = 1; k <= lives; k++) { n[k] += dist[k] * (1 - p); n[k - 1] += dist[k] * p; }
      n[0] += dist[0]; dist = n; tot += 1 - dist[0];
    });
    return { exp: tot, pEnd: 1 - dist[0], dist: dist };
  }

  // best plan with plan[locked round] fixed (if given); Hungarian start, then swap/substitute search
  function solve(O, teams, rounds, lives, lockRound, lockTeam) {
    var free = rounds.filter(function (r) { return r !== lockRound; });
    var pool = teams.filter(function (t) { return t !== lockTeam; });
    var plan = {};
    if (lockRound != null) plan[lockRound] = lockTeam;
    if (free.length) {
      var cols = pool.slice(); while (cols.length < free.length) cols.push(null); // nobody left: certain failure
      var a = free.map(function (rd) { return cols.map(function (t) { return t ? O[t][rd].fail : 1; }); });
      hungarian(a).forEach(function (ci, i) { plan[free[i]] = cols[ci]; });
    }
    var best = survival(plan, rounds, O, lives).exp, improved = true, guard = 0;
    while (improved && guard++ < 50) {
      improved = false;
      for (var i = 0; i < free.length; i++) {
        var ra = free[i];
        for (var j = i + 1; j < free.length; j++) {
          var rb = free[j], p2 = Object.assign({}, plan); p2[ra] = plan[rb]; p2[rb] = plan[ra];
          var v = survival(p2, rounds, O, lives).exp; if (v > best + 1e-9) { plan = p2; best = v; improved = true; }
        }
        var inPlan = rounds.map(function (r) { return plan[r]; });
        pool.forEach(function (t) {
          if (inPlan.indexOf(t) >= 0) return;
          var p3 = Object.assign({}, plan); p3[ra] = t;
          var v3 = survival(p3, rounds, O, lives).exp; if (v3 > best + 1e-9) { plan = p3; best = v3; improved = true; inPlan = rounds.map(function (r) { return plan[r]; }); }
        });
      }
    }
    return plan;
  }

  function rank(E, opts, R, h, G, bw) {
    var O = outcomes(E, R, h, opts.drawsLose, G, bw);
    var rounds = []; for (var r = E.round; r <= E.last; r++) rounds.push(r);
    var avail = E.teams.filter(function (t) { return opts.used.indexOf(t) < 0; });
    var rows = avail.map(function (t) {
      var plan = solve(O, avail, rounds, opts.lives, E.round, t), s = survival(plan, rounds, O, opts.lives);
      var f = E.fixtures[t][0], o = O[t][E.round];
      return { team: t, opp: f.opp, home: f.home, date: f.date, win: o.win, draw: o.draw, lose: o.lose, fail: o.fail,
               expRounds: s.exp, pEnd: s.pEnd, dist: s.dist,
               plan: rounds.map(function (rd) { var x = plan[rd]; return { round: rd, team: x, fail: x ? O[x][rd].fail : 1 }; }) };
    });
    rows.sort(function (a, b) { return b.expRounds - a.expRounds; });
    rows.forEach(function (x) { x.planCost = rows[0].expRounds - x.expRounds; });
    return { rows: rows, outcomes: O, rounds: rounds, avail: avail };
  }

  function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

  function run(E, opts) { return rank(E, opts, E.ratings, E.h); }

  function stress(E, opts) {
    var scen = [
      { label: 'Home advantage lower', pick: rank(E, opts, E.ratings, E.h - E.homeShift).rows[0].team },
      { label: 'Home advantage higher', pick: rank(E, opts, E.ratings, E.h + E.homeShift).rows[0].team },
      { label: 'Odds model only', pick: rank(E, opts, E.ratings, E.h, E.goals, 1).rows[0].team },
      { label: 'Results model only', pick: rank(E, opts, E.ratings, E.h, E.goals, 0).rows[0].team }
    ];
    var rand = rng(7), hits = {};
    var gauss = function () { var u = 1 - rand(), v = rand(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    for (var i = 0; i < E.runs; i++) {
      var R = {}, G = { mu: E.goals.mu, home: E.goals.home, rho: E.goals.rho, att: {}, def: {} };
      E.teams.forEach(function (t) {
        var z = gauss(); R[t] = E.ratings[t] + z * E.noise;      // same shock nudges both models
        G.att[t] = E.goals.att[t] + z * 0.5 * E.noise + gauss() * 0.05;
        G.def[t] = E.goals.def[t] + z * 0.5 * E.noise + gauss() * 0.05;
      });
      var tp = rank(E, opts, R, E.h, G).rows[0].team; hits[tp] = (hits[tp] || 0) + 1;
    }
    var mc = Object.keys(hits).map(function (k) { return { team: k, share: hits[k] / E.runs }; }).sort(function (a, b) { return b.share - a.share; });
    return { scenarios: scen, monteCarlo: mc, runs: E.runs };
  }

  root.SurvivorEngine = { run: run, stress: stress, survival: survival, goalsWDL: goalsWDL, rates: rates };
  if (typeof module !== 'undefined') module.exports = root.SurvivorEngine;
})(typeof window !== 'undefined' ? window : globalThis);
