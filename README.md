# Survivor Pick Board

Weekly pick model and dashboard for a Premier League survivor pool (2026–27).

Pool rules: 3 lives, a loss costs one, draws are free, each team once per half-season (rounds 1–19).

## How we pick

1. **Only a loss hurts.** Draws are free, so every team is judged on its chance of losing, not winning.
2. **Start from the market.** This week's chances come from bookmaker prices with the margin removed.
3. **Rate every team for later rounds.** Team strengths are fitted to the last three rounds of prices (recent weeks weighted more), lightly pulled toward Opta's season projection.
4. **Plan the whole half.** Each unused team is assigned to at most one round through round 19 (Hungarian algorithm on lose probability, then pairwise-swap improvement) to maximize expected rounds survived.
5. **Rank this week by the full plan.** Each option is locked in for this round and the plan rebuilt around it. "Plan cost" is the expected rounds of survival given up versus the best start.
6. **Stress-test.** The top pick is re-checked with higher/lower home advantage, more/less weight on Opta, and 60 runs with random noise on the ratings.
7. **Refresh weekly.** Update results and lives, pull new prices, refit, replan, rebuild the page.

## Files

| File | What it is |
|---|---|
| `model.py` | Fits ratings, ranks this week's options, builds the season plan, runs stress tests, writes `data.json` |
| `template.html` | The dashboard page (data is inlined at build time) |
| `build.py` | Inlines `data.json` into the template to produce `survivor.html` |
| `data.json` | Latest model output |
| `survivor.html` | Built page |

## Weekly refresh

1. In `model.py`, update `USED`, `LIVES`, `CUR` (current round), `HISTORY`, and add the new round's prices (`MW…` dicts and `CALIB`).
2. Download fixtures:
   ```
   curl -sS -o en1.json https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json
   ```
3. Run:
   ```
   pip install numpy scipy
   python3 model.py data.json en1.json
   python3 build.py data.json template.html survivor.html
   ```

Not betting advice.
