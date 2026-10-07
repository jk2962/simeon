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
league-wide home advantage. The raw model is not identifiable (add 1 to every
attack, subtract 1 from the intercept: same predictions), so the GLM is fitted
with a reference team fixed at 0, then re-centered so attack and defense each
average 0. Predictions are identical either way; centered values are easier to
read (0 is an average team) and do not depend on which team was the reference.
The alternative is per-team home advantage, which doubles as many parameters
on the same data. I would only consider it with far more matches per team.

**730-day training window.** Recent matches describe a team's current
strength; more matches give steadier estimates. Two seasons is about 76
matches per ever-present team. The alternatives are a shorter or longer
window, or using everything with time-decay weights. 730 is a reasoned
starting point and has NOT been tuned; the Phase 2 backtest decides.

**Promoted-team prior.** A team with zero matches in the window has nothing to
fit, so it gets the average fitted attack and defense of promoted teams, found
from the data (in a season but not the previous one), never hardcoded and
never from future matches. The alternative is treating it as an average team,
which is clearly too generous. Known limitations: (1) the prior stops applying
after a team's FIRST match, so early-season estimates rest on a handful of
games and can be extreme; (2) a promoted team's fitted strength uses all its
matches in the window, including later seasons if it stayed up. Shrinking
small samples toward the prior (a penalized or Bayesian fit) would fix (1).

**Renormalizing the 0-10 grid.** The grid ignores scorelines with 11 or more
goals, so its cells sum to slightly less than 1. Dividing by the total makes
home/draw/away sum to exactly 1, which RPS requires. The lost probability is
tiny (about one in a million for typical matches). The alternative is a bigger
grid, which changes nothing that matters.

**No time decay yet.** Inside the window every match counts equally. Decay
weights (as in Dixon-Coles) add a tuning parameter, and a tuned parameter
needs a backtest to justify it. The hard window is the simple version of the
same idea. I would add decay if the backtest shows it lowers RPS.

## Five likely interview questions

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
