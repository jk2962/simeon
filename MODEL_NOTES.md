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

**Promoted-team prior.** A team is "promoted" in a season if it did not play
in the previous Premier League season. One function applies that definition
both to learn the prior and to decide who gets it, so a team that came back
after a season or more away (Ipswich in 2026-27) counts as promoted even with
older matches in the window. The prior mean is learned from the data: the
average gap between promoted teams and established teams over each promoted
team's full promoted season, using completed seasons only (currently attack
-0.37, defense +0.33). The alternative is a league-average prior mean, which
is clearly too generous. Known limitations: every promoted team gets the same
prior, whatever it did in the Championship, and a returning team's old
matches still count as data. Second-division results would improve both.

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

How PRIOR_STRENGTH = 3 was chosen: `python -m pipeline.tune` scores the grid
0.01, 3, 10, 30, 100 by walk-forward RPS on 2023-24 and 2024-25:

    0.01: 0.1964   3: 0.1962   10: 0.1957   30: 0.1951   100: 0.1965

The honest reading: the lowest value is at 30, but 30 beats 3 by only 0.0011,
which is 1.3 standard errors, so the grid does not separate them. The pattern
also points two ways. Across all matches more shrinkage looks slightly
better; on the 30 matches involving a team with under 10 matches it looks
worse (RPS 0.110 unpenalized, 0.113 at 3, 0.116 at 10, 0.121 at 30). And at
10 or 30 established teams move a lot (Arsenal's defense by 0.06 and 0.13),
which breaks the requirement that teams with 70+ matches barely move. So 3 is
not a tuned optimum. It rests on numerical stability and on the prior belief
that 5 matches should not fully define a team. 2025-26 and 2026-27 were
excluded from this choice: 2025-26 is the Phase 2 sanity check, and a setting
chosen on a season cannot be honestly tested on it. The alternative is a full
Bayesian model with a fitted prior variance, or a stronger penalty for
promoted teams only; I would revisit the value with more seasons of data.

**Renormalizing the 0-10 grid.** The grid ignores scorelines with 11 or more
goals, so its cells sum to slightly less than 1. Dividing by the total makes
home/draw/away sum to exactly 1, which RPS requires. The lost probability is
tiny (about one in a million for typical matches). The alternative is a bigger
grid, which changes nothing that matters.

**No time decay yet.** Inside the window every match counts equally. Decay
weights (as in Dixon-Coles) add a tuning parameter, and a tuned parameter
needs a backtest to justify it. The hard window is the simple version of the
same idea. I would add decay if the backtest shows it lowers RPS.

## Model change policy

Pre-registered on 2026-10-08, before round 6 of 2026-27 (first kickoff
2026-10-10 11:30 UTC), the first round with a locked forecast. Rounds 1 to 5
were never locked.

A "model change" is any change to the formula, to PRIOR_STRENGTH, to the
training window, to the promoted-team prior, to how matches are weighted, or
to the season simulation's method and uncertainty settings, including how
prior variance is derived. Refitting the parameters on new results is not a
model change: it happens every week.

**1. Checkpoints.** A model change may only be considered after rounds 10, 20
and 30 of a season, and before the next round is locked: once the round's
originally scheduled match dates have passed; postponed matches do not delay
the checkpoint. Between checkpoints the model is frozen. At
most 2 candidates are considered per checkpoint, and they are named in the
decision log before any backtest is run. An adopted change applies from the
next locked round onward. Forecasts already locked are never regenerated.

**2. Evidence required.** A candidate must beat the current model on a
walk-forward backtest over past seasons, scored by RPS, and must not worsen
calibration. The repo holds six completed seasons, 2020-21 to 2025-26. As in
`pipeline.tune`, candidates are compared on 2023-24 and 2024-25 (760
matches), earlier seasons are training data only, and 2025-26 is the holdout.
Locked 2026-27 forecasts are not backtest evidence: they may suggest which
candidate to test, but they cannot justify adopting it. Checkpoints control
when new ideas may be acted on; they add no new evidence, since 2026-27
forecasts are excluded.

Threshold. A candidate is adopted only if all four hold:

- Mean RPS over the 760 comparison matches is lower than the current model's
  by at least 2 standard errors of the paired per-match difference.
- RPS is lower in 2023-24 and in 2024-25 separately.
- On the 2025-26 holdout, RPS is not higher than the current model's. The
  holdout may be used only for candidates that pass the first two
  conditions, and once per candidate. Every use is logged, because each one
  makes the holdout a little less clean.
- Calibration is not worse on the comparison seasons. Calibration error is
  measured over ten equal-width probability bins with home, draw and away
  forecasts pooled: the mean absolute gap between predicted probability and
  observed frequency, weighted by bin count. It may not rise by more than
  one bootstrap standard error, taken from resampling the 760 comparison
  matches with replacement and recomputing the difference in calibration
  error (candidate minus current) on each resample. The absolute gap between
  predicted and observed draw rate may not grow by more than one bootstrap
  standard error of the paired difference, computed the same way as for
  calibration error.

By this rule the PRIOR_STRENGTH = 30 candidate of 2026-10-07 (1.3 standard
errors) would not have been adopted.

**3. Weekly diagnostics.** Reported after every round, on locked forecasts
only: cumulative RPS against the bookmaker, calibration by probability bin,
and predicted against observed draw rate. No action is taken on them between
checkpoints. `python -m pipeline.run --score` produces the first; the other
two are not built yet.

**4. One-off events.** A lucky win, an off day, an injury or an early red
card is handled only by a rule that is defined in advance, tested by backtest
under point 2, and adopted at a checkpoint. An example is a downweight for
matches with a red card, using the red-card columns (`HR`, `AR`) already in
the results files. No result is ever dropped or downweighted by judgment.

**5. Logging.** Every checkpoint gets an entry in the decision log below,
with the date, the candidates considered, the evidence (the numbers) and the
outcome. "No change" and rejected candidates are logged too.

**6. Bug fixes.** A bug is code that does not do what MODEL_NOTES.md already
stated before the bug was found. A fix is not a model change and does not
wait for a checkpoint, but it may only restore the documented behavior. It
applies from the next locked round, is logged in the decision log, and never
regenerates locked forecasts. Anything that changes documented behavior is a
model change.

## Decision log

- **2026-10-07: PRIOR_STRENGTH kept at 3; a pre-stated rule was deliberately
  overridden.** The rule set before rerunning the grid was "update the
  constant if the best grid value changes". After the promoted-rule fix the
  best value changed from 0.01 to 30, and the constant was NOT updated.
  Reasons:
  1. 30 beats 3 by 0.0011 RPS, which is 1.3 standard errors, and most of it
     comes from a single season (2024-25: -0.0018; 2023-24: -0.0003).
  2. The small-sample subset that shrinkage is meant to help gets worse with
     higher strength (30 matches: 0.113 at 3, 0.121 at 30).
  3. Strength 30 compresses established teams heavily (Arsenal's defense
     moves by 0.13), and about half of its gain comes from matches with no
     promoted team at all (-0.0007, 0.7 standard errors). How much to
     compress established teams is a separate modeling choice, to be
     evaluated later on more seasons.
- **2026-10-08: Model change policy amended twice, before any locked
  forecast was scored.** The draw-rate condition now allows growth of up to
  one bootstrap standard error of the paired difference (it was "may not
  grow"), and a checkpoint now opens once the round's originally scheduled
  match dates have passed, without waiting for postponed matches (it was
  "once every match of that round has been scored").
- **2026-10-08: Round-6 season snapshot gives Hull a 2.8% title probability;
  a round-10 candidate is named.** With fixed parameters the figure is 0.02%.
  The cause: the Laplace draws treat PRIOR_STRENGTH = 3, which was chosen for
  numerical stability, as a literal prior, and for a promoted team with 5
  matches that prior is very wide. Named candidate for the round-10
  checkpoint: a simulation prior variance separate from PRIOR_STRENGTH,
  evaluated by backtesting season simulations from round 6 of 2023-24 and
  2024-25 against final positions (RPS over positions). Locked snapshots are
  not regenerated.

## Known divergences from the market reference

Checked on 2026-10-05 against approximate market probabilities for the round
of 10 October. The model was NOT adjusted to match them.

- **Coventry v Newcastle: model 11/21/68, market 29/26/45.** Coventry scored
  1 goal and conceded 10 in its 5 matches. At strength 3 the prior counts
  like about 3 goals, so its attack only moves from -1.72 to -0.93 against a
  prior mean of -0.37.
- **Ipswich v Fulham: model 21/22/57, market 35/27/39.** Ipswich now gets the
  promoted prior mean, but that changed almost nothing (away 56% to 57%). It
  has 39 matches in the window, 34 of them from its 2024-25 relegation
  season, and that data alone already rates it slightly below a typical
  promoted team. The divergence comes from old data about a different squad,
  not from the prior mean. The model knows nothing about its Championship
  season.

## Open issues

- **A returning team is still misread before its first match of the
  season.** Until it has played, the latest season in the training data is
  the previous one, so the fit cannot know the team is promoted and rates it
  on its old matches with a prior mean of 0.
- **PRIOR_STRENGTH is not settled.** After the promoted-rule fix the grid's
  lowest RPS is at 30, not separated from 3 by the data, and 10 or 30 would
  move established teams by more than the tests allow. One strength for all
  teams may be the wrong shape: promoted teams may want more shrinkage than
  established ones.
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
