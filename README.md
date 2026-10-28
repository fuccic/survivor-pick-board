# ⚽ Survivor Pick Board

*Because "I just had a feeling about Fulham" is not a strategy.*

Every week of a Premier League survivor pool comes down to one nervy question: **who do I pick so I'm still standing on Monday night?** This little app answers it with math instead of vibes, then shows you the answer on a page you can check from your phone at the pub.

## The game

- 🫀 **3 lives.** Lose a match, lose a life. Lose three, you're out.
- 🤝 **Draws are free.** A scrappy 0–0 counts as a win for us.
- 🎟️ **Each team once per half.** Burn Arsenal in week 1 and they're gone until round 20.

That last rule is the whole puzzle. The safest team this week might be the only lifeboat you have in round 15.

**Try it:** https://fuccic.github.io/survivor-pick-board/

## Play along with your own picks

The page opens on an example player. Tap the teams **you've** already used, set your lives, and say whether a draw is safe in your pool. Your pick, season plan and stress test update instantly, all in your browser. Your choices are saved on your device, so next week you just tap the team you used.

## What you get

- **This week's pick**, with its chance of losing in big friendly numbers
- **Every other option ranked**, and what each one would cost you later in the season
- **A season plan to round 19**: which team to save for which week
- **A fixture board** that lights up the danger rounds in red
- **A form guide and matchup** for every option: last five results and an expected score
- **A stress test**, so you know whether the pick is a sure thing or a coin flip
- **Your pick history**, lives and all

## How we pick

1. **Only a loss hurts.** We don't care how often a team wins, just how rarely it loses. A stubborn draw machine can beat a flashy goal machine.
2. **Trust the bookies first.** This week's chances come straight from betting odds, with the bookies' cut taken out. They know about the injuries before we do.
3. **Rate everyone two ways.** The *odds model* fits team strengths to the last three rounds of betting prices, with a gentle nudge toward Opta's season projection. The *results model* gives every team an attack and a defence rating from this season's matches, using shots on target as well as goals (shots are steadier) and counting recent games a bit more. Each future fixture is scored as that attack against that defence, so every matchup gets its own chance of a win, a draw, or a loss.
   - **Blend by what actually predicts.** We fit the odds model without the latest week, then check which mix best predicts that week's fresh prices. Right now that's 80% odds, 20% results. `backtest.py` checks the results model against real results (it beats a no-skill guess, and shots on target help).
4. **Plan the whole half, not just Saturday.** Every unused team gets assigned to at most one round between now and round 19, arranged to keep you alive as long as possible.
5. **Rank this week by the whole plan.** We lock in each option, rebuild the best plan around it, and see how much survival it costs. "Plan cost" is the number of expected rounds you give up.
6. **Poke it with a stick.** The top pick is re-run with more and less home advantage, with each model on its own, and in 60 runs with random noise on every team. If it keeps winning, sleep easy. If it splits, it's a close call and the page says so.
7. **Repeat every week.** New results, new odds, new plan.

## Run it yourself

You'll need Python 3 with `numpy` and `scipy`.

```bash
pip install numpy scipy

# grab the latest fixtures
curl -sS -o en1.json https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json

# crunch the numbers, then build the page
python3 model.py data.json en1.json results.csv
python3 build.py data.json template.html index.html   # inlines engine.js too
```

Open `index.html` in a browser and you're done.

### The weekly ritual

*(For whoever runs the site.)*

Before each round, open `model.py` and update:

- `USED`: the teams you've burned
- `LIVES`: how many you've got left
- `CUR`: the round you're picking for
- `HISTORY`: last week's result (fingers crossed)
- `results.csv`: add last week's scores and shots on target
- the new round's odds (add a `MW…` dict and include it in `CALIB`)

Then run the three commands above.

## What's in the box

| File | What it does |
|---|---|
| `model.py` | The brains: fits ratings, blends the two models, ranks picks, plans the season, runs stress tests |
| `perf.py` | The results model: attack/defence ratings from goals and shots on target |
| `backtest.py` | Checks the results model against real results, round by round |
| `results.csv` | This season's scores and shots on target |
| `engine.js` | The planner, ported to the browser so anyone can enter their own picks |
| `template.html` | The good-looking part |
| `build.py` | Pours the numbers into the page |
| `data.json` | This week's results from the model |
| `index.html` | The finished page |

## FAQ

**Can it guarantee I win the pool?**
No. Even the best plan only gets through round 19 about 1 time in 8. The goal is to outlast the other 103 people, not the fixture list.

**Why didn't it pick the team in the best form?**
Form counts twice: it's baked into the odds, and the results model reads it straight from the scores and shots. But if that team is your only good option for a scary round later, it's worth more saved than spent.

**Can I pick Man City this week?**
You already used them. Sorry. (Not that sorry.)

## Fine print

This is a fun tool for a friendly pool. It is not betting advice, and it can't stop a 94th-minute deflection off someone's knee.
