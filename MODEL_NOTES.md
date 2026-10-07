# Model notes

The model: each side's goals are Poisson, with

    log(expected home goals) = intercept + home_advantage + attack[home] + defense[away]
    log(expected away goals) = intercept + attack[away] + defense[home]

All parameters are on the log scale, so effects multiply: a home advantage of
0.155 means exp(0.155) = 1.17 times as many goals. A higher `defense` value
means a team concedes MORE.

## Decisions

**Poisson for goals.** Goals are counts of rare events spread over 90 minutes,
which is what a Poisson describes, and it needs one number per side. The
alternative is the negative binomial, which allows more spread than a Poisson.
I would switch if real scorelines showed clearly more variance than the mean
(overdispersion) after accounting for team strength.

**Independence between the two sides.** The probability of a scoreline is the
product of the two Poisson probabilities. It is simple and needs no extra
parameter. Its weakness is draws: real matches have more 0-0 and 1-1 results
than independence predicts, so this model tends to under-forecast draws. The
alternatives are the Dixon-Coles correction (one extra parameter that shifts
the four lowest scorelines) or a bivariate Poisson. I would add Dixon-Coles if
the backtest shows predicted draw rates below observed ones.

**Parameterization.** One attack and one defense value per team, plus a single
league-wide home advantage. Each team value is "prior mean + deviation". The
raw model is not identifiable (add 1 to every attack, subtract 1 from the
intercept: same predictions). The shrinkage penalty settles it: among all
equivalent solutions it picks the one with the smallest deviations, so no
reference team is needed. The alternative is per-team home advantage, which
doubles as many parameters on the same data. I would only consider it with far
more matches per team.

**730-day training window.** Recent matches describe a team's current
strength; more matches give steadier estimates. Two seasons is about 76
matches per ever-present team. The alternatives are a shorter or longer
window, or using everything with time-decay weights. 730 is a reasoned
starting point and has NOT been tuned; the Phase 2 backtest decides.

**Promoted-team prior.** A team with no match in the window before the
current season gets a prior mean learned from the data: the average gap
between promoted teams and established teams over each promoted team's full
first season, using completed seasons only (currently attack -0.37, defense
+0.33). The alternative is a league-average prior mean, which is clearly too
generous: on the tuning seasons it scored worse on matches involving a team
with under 10 matches (RPS 0.134 vs 0.113, n=30). Known limitations: every
promoted team gets the same prior, whatever it did in the Championship, and a
returning team with old matches in the window (Ipswich) is rated on those old
matches. Second-division results would improve both.

**Shrinkage (MAP estimation).** What: each team's deviation from its prior
mean carries an L2 penalty, so the fit minimizes

    -log-likelihood + (PRIOR_STRENGTH / 2) * sum(deviation^2)

The intercept and home advantage are not penalized. Why: with few matches the
plain estimate is extreme (one goal in 5 matches gave Coventry an attack of
-1.56), and a team with zero goals has no finite estimate at all, so the fit
breaks. The penalty pulls a team toward its prior mean, strongly with little
data and hardly at all with a lot (teams with 70+ matches move by under 0.02).
Equivalence: this is ridge regression on the deviations, and it is also the
Bayesian MAP estimate under a Normal(0, 1/PRIOR_STRENGTH) prior on each
deviation, because the log of that prior is exactly the penalty term. A rough
reading: PRIOR_STRENGTH = 3 means the prior counts like about 3 goals of data.

How PRIOR_STRENGTH = 3 was chosen: `python -m pipeline.tune` scored the grid
0.01, 3, 10, 30, 100 by walk-forward RPS on 2023-24 and 2024-25:

    0.01: 0.1964   3: 0.1965   10: 0.1966   30: 0.1975   100: 0.2021

The honest reading: RPS is flat from 0.01 to 10 (differences within one
standard error) and worse beyond. On the 30 matches involving a team with
under 10 matches, shrinkage showed NO benefit: RPS was 0.110 unpenalized,
0.113 at 3 and 0.115 at 10. The newly promoted teams in those seasons really
were as bad as their first results. So 3 is not justified by predictive gain.
It rests on numerical stability and on the prior belief that 5 matches should
not fully define a team. 2025-26 and 2026-27 were excluded from this choice:
2025-26 is the Phase 2 sanity check, and a setting chosen on a season cannot
be honestly tested on it. The alternative is a full Bayesian model with a
fitted prior variance; I would revisit the value with more seasons of data.

**Renormalizing the 0-10 grid.** The grid ignores scorelines with 11 or more
goals, so its cells sum to slightly less than 1. Dividing by the total makes
home/draw/away sum to exactly 1, which RPS requires. The lost probability is
tiny (about one in a million for typical matches). The alternative is a bigger
grid, which changes nothing that matters.

**No time decay yet.** Inside the window every match counts equally. Decay
weights (as in Dixon-Coles) add a tuning parameter, and a tuned parameter
needs a backtest to justify it. The hard window is the simple version of the
same idea. I would add decay if the backtest shows it lowers RPS.

## Open issues

- **The "promoted" definition should be "not in last season's Premier
  League".** Today a team gets the promoted prior mean only if it has no match
  in the 730-day window before the current season. A team that came back up
  after one season away (Ipswich in 2026-27) is therefore treated as
  established and rated on its old matches.
- **Evaluate PRIOR_STRENGTH on early-season promoted-team matches, which
  needs older Premier League seasons from the same source.** The repo's data
  starts in 2020-21, and promoted teams can only be identified from 2021-22
  (the first season has no previous season to compare with). The current
  evidence is 30 matches from two seasons, too few to say whether shrinkage
  helps or hurts those matches.
- **The promoted prior rests on very few promoted teams.** It averages 15
  team-seasons today (3 per season, 2021-22 to 2025-26), and only 6 and 9 when
  it was used to score 2023-24 and 2024-25. Older seasons would steady it.

## Likely interview questions

**1. Why Poisson, and how do you know it fits?**
Goals are counts of rare, roughly independent events, and Poisson is the
standard one-parameter model for that. I would check it by comparing the
observed distribution of goals with the predicted one, and I judge the model
on forecast quality (RPS against the bookmaker), not on fit alone.

**2. What does the independence assumption cost you?**
It under-predicts low-scoring draws, because teams' scores are slightly
correlated in real matches. I left the Dixon-Coles fix out on purpose so the
first version is simple, and the backtest will show whether draws are
miscalibrated enough to need it.

**3. How do you prevent data leakage?**
Every fit takes its data from one function, `get_training_data`, which keeps
only matches that kicked off strictly before a cutoff. The promoted-team prior
and the training window are computed only from that data. Closing odds are
used only as a benchmark, never as a model input.

**4. Why RPS instead of accuracy or log loss?**
Accuracy ignores probabilities, and the outcomes are ordered: predicting a
home win when the match is drawn is a smaller miss than when the away side
wins. RPS scores the whole probability forecast and respects that order. Log
loss is a reasonable alternative but ignores the order and punishes
near-zero probabilities very heavily.

**5. Do you expect to beat the bookmaker?**
No. Closing odds contain team news, injuries and market money that this model
never sees. The realistic goal is to clearly beat the naive baseline (0.228
RPS on 2025-26) and to measure honestly how far the model is from the market
(0.205).

**6. Why shrink team strengths, and how did you choose how much?**
Without shrinkage a team's first few matches define it, and a team that has
not scored yet breaks the fit. I penalize each team's deviation from a prior
mean, which is ridge regression and also the MAP estimate under a normal
prior. I chose the strength on two earlier seasons and found RPS was flat
across small values, so I say plainly that the value is a stability choice,
not a tuned gain, and I kept 2025-26 out of it so that season stays a clean
test.
