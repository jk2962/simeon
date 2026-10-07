"""Independent Poisson goals model: team attack, team defense, home advantage.

tests/test_model.py defines what this implementation must satisfy.
MODEL_NOTES.md explains each modeling decision.

Deliberately left out of this version (future work, to be judged by the
Phase 2 backtest rather than added on faith):
  - time-decay weighting (recent matches counting more than old ones);
  - the Dixon-Coles correction for low-scoring draws (0-0, 1-1).
"""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import poisson
from statsmodels.tools.sm_exceptions import ConvergenceWarning

# Only matches within this many days before the latest kickoff in `train` are
# used for fitting. The tradeoff: a short window follows current strength
# (squads and managers change) but leaves few matches per team, so estimates
# are noisy; a long window is stable but describes teams as they used to be.
# 730 days is about two seasons, roughly 76 matches per ever-present team.
# This value is a starting point and has NOT been tuned. Tuning it belongs to
# the Phase 2 backtest.
TRAINING_WINDOW_DAYS = 730

# Strength of the pull of each team's attack and defense toward its prior
# mean (see fit). It is the precision (1 / variance) of a normal prior on the
# deviation from the prior mean. A useful way to read it: a team's own data
# is worth roughly "goals scored" (attack) or "goals conceded" (defense), so
# PRIOR_STRENGTH = 3 means the prior counts about as much as 3 goals.
#
# How 3 was chosen, honestly: `python -m pipeline.tune` scores a grid by
# walk-forward RPS on 2023-24 and 2024-25 only (2025-26 and 2026-27 are NOT
# used). The lowest RPS is at 30, but it beats 3 by only 1.3 standard errors,
# so the data does not separate them. On the 30 matches involving a team with
# under 10 matches, more shrinkage looked worse, not better. And at 10 or 30
# established teams move by more than 0.05, which the tests forbid. So 3 is
# not a tuned optimum. It is a judgment call that rests on numerical
# stability (a team with zero goals no longer breaks the fit) and on the prior
# belief that 5 matches should not fully define a team. See MODEL_NOTES.md.
PRIOR_STRENGTH = 3.0

# A penalty so weak it changes nothing that matters, but still keeps the fit
# finite and identified. Used as the "unpenalized" reference, and for the
# single-season fits behind the promoted-team prior, where every team has 38
# matches and shrinking would only bias the prior toward zero.
NEAR_ZERO_STRENGTH = 0.01

MATCHES_PER_SEASON = 380  # a season with exactly this many matches is complete
MAX_GOALS = 10  # the scoreline grid covers 0-10 goals for each side


@dataclass
class FittedModel:
    """Fitted parameters, all on the log scale.

    Expected goals for a match are:
        home: exp(intercept + home_advantage + attack[home] + defense[away])
        away: exp(intercept + attack[away] + defense[home])

    attack:  higher means the team scores more.
    defense: higher means the team CONCEDES more (a weaker defense).
    Each value is "prior mean + fitted deviation". The prior mean is 0 for an
    established team, so 0 reads as "a typical established team" and the
    overall level of scoring sits in `intercept`.

    promoted_attack / promoted_defense are the prior mean for a promoted team:
    how far promoted teams have been from established teams in past seasons.
    They are also the full estimate for a team with no training data at all.
    They are None when `train` has no completed season to learn them from.
    """

    intercept: float
    home_advantage: float
    attack: dict
    defense: dict
    promoted_attack: float | None
    promoted_defense: float | None


def fit(train) -> FittedModel:
    """Fit the model on `train` and return a FittedModel.

    `train` MUST come from ingest.get_training_data(matches, before_utc), with
    columns season, kickoff_utc, home, away, home_goals, away_goals.

    Model: a Poisson GLM (statsmodels, log link) on goals. The data is reshaped
    to one row per team per match (two rows per match) and goals are regressed
    on the scoring team (attack), the conceding team (defense) and a home
    indicator (home advantage, one league-wide value). Home and away goals are
    treated as independent given these parameters.

    Shrinkage: each team's attack and defense is "prior mean + deviation", and
    the deviations carry an L2 penalty of strength PRIOR_STRENGTH. A team with
    many matches is barely affected; a team with few matches is pulled toward
    its prior mean, and the more so the less data it has.

    Prior mean: 0 (a typical established team) for most teams. A team that is
    promoted in the current season gets the promoted-team prior instead.
    "Promoted" means it did not play in the previous Premier League season
    (see _promoted_teams), whether or not it has older matches in the window.
    The prior is the average gap between promoted teams and established
    teams, measured over each promoted team's full promoted season. It is
    identified FROM THE DATA, not hardcoded, and uses only COMPLETED seasons
    in `train`: the season in progress is excluded.
    """
    return fit_with_strength(train, PRIOR_STRENGTH)


def fit_with_strength(train, prior_strength) -> FittedModel:
    """fit() with an explicit penalty strength. Used for tuning and in tests."""
    latest = train["kickoff_utc"].max()
    window = train[train["kickoff_utc"] > latest - pd.Timedelta(days=TRAINING_WINDOW_DAYS)]

    promoted_attack, promoted_defense = _promoted_prior(train)

    # Teams promoted in the current season get the promoted prior mean.
    # Everyone else gets 0.
    current_season = train["season"].max()  # '2026-27' > '2025-26' as text
    promoted = _promoted_teams(train, current_season)

    prior_attack = {}
    prior_defense = {}
    for team in sorted(set(window["home"]) | set(window["away"])):
        if team in promoted and promoted_attack is not None:
            prior_attack[team] = promoted_attack
            prior_defense[team] = promoted_defense
        else:
            prior_attack[team] = 0.0
            prior_defense[team] = 0.0

    intercept, home_advantage, attack, defense = _fit_penalized(
        window, prior_attack, prior_defense, prior_strength
    )
    return FittedModel(
        intercept=intercept,
        home_advantage=home_advantage,
        attack=attack,
        defense=defense,
        promoted_attack=promoted_attack,
        promoted_defense=promoted_defense,
    )


def _fit_penalized(matches, prior_attack, prior_defense, strength):
    """Penalized Poisson fit. Returns (intercept, home_advantage, attack, defense).

    attack and defense are dicts of team -> prior mean + fitted deviation.
    """
    # Long format: two rows per match, one for each side's goals.
    home_rows = pd.DataFrame(
        {
            "team": matches["home"].to_numpy(),
            "opponent": matches["away"].to_numpy(),
            "home": 1.0,
            "goals": matches["home_goals"].to_numpy(dtype=float),
        }
    )
    away_rows = pd.DataFrame(
        {
            "team": matches["away"].to_numpy(),
            "opponent": matches["home"].to_numpy(),
            "home": 0.0,
            "goals": matches["away_goals"].to_numpy(dtype=float),
        }
    )
    long = pd.concat([home_rows, away_rows], ignore_index=True)
    teams = sorted(set(long["team"]))

    # Parameterization: attack = prior mean + deviation (same for defense).
    # The prior means are known numbers, so they go into the GLM OFFSET (a
    # term added to the linear predictor with its coefficient fixed at 1).
    # The fitted coefficients are then the DEVIATIONS, one attack column and
    # one defense column for EVERY team.
    #
    # Without a penalty that design is not identifiable: adding 1 to every
    # attack and subtracting 1 from the intercept gives the same expected
    # goals, which is why the unpenalized version needed a reference team.
    # The penalty removes the problem. Of all the equivalent solutions it
    # picks the one with the smallest deviations, which is the one where the
    # deviations sum to zero. So no team has to be singled out as reference.
    offset = long["team"].map(prior_attack) + long["opponent"].map(prior_defense)
    attack_cols = pd.get_dummies(long["team"], prefix="attack", dtype=float)
    defense_cols = pd.get_dummies(long["opponent"], prefix="defense", dtype=float)
    design = pd.concat([attack_cols, defense_cols, long[["home"]]], axis=1)
    design.insert(0, "const", 1.0)

    # statsmodels minimizes  -loglikelihood / n_rows + sum(alpha * coef^2) / 2.
    # Setting alpha = strength / n_rows makes that the same as minimizing
    #     -loglikelihood + (strength / 2) * sum(deviation^2),
    # i.e. the MAP estimate under a Normal(0, 1 / strength) prior on each
    # deviation. alpha is 0 for the intercept and home advantage: they are
    # estimated from every match and need no shrinkage.
    is_deviation = ~design.columns.isin(["const", "home"])
    alpha = np.where(is_deviation, strength / len(long), 0.0)

    glm = sm.GLM(long["goals"], design, family=sm.families.Poisson(), offset=offset)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)  # fail loudly
        result = glm.fit_regularized(alpha=alpha, L1_wt=0.0)  # L1_wt=0: pure L2
    coef = pd.Series(np.asarray(result.params), index=design.columns)

    attack = {team: float(prior_attack[team] + coef[f"attack_{team}"]) for team in teams}
    defense = {team: float(prior_defense[team] + coef[f"defense_{team}"]) for team in teams}
    return float(coef["const"]), float(coef["home"]), attack, defense


def _promoted_teams(train, season):
    """Teams that are promoted in `season`: they play in it, but did not play
    in the previous Premier League season in `train`.

    This is the one definition of "promoted", used both to learn the prior
    (_promoted_prior) and to decide which teams get it (fit_with_strength).
    A team that was relegated and came back after one or more seasons away
    counts as promoted, even if its older matches are still in the training
    window. Returns an empty set for the earliest season in `train`, which
    has no previous season to compare with.
    """
    seasons = sorted(train["season"].unique())  # e.g. '2024-25' sorts by date
    position = seasons.index(season)
    if position == 0:
        return set()
    previous = train[train["season"] == seasons[position - 1]]
    current = train[train["season"] == season]
    return (set(current["home"]) | set(current["away"])) - (
        set(previous["home"]) | set(previous["away"])
    )


def _promoted_prior(train):
    """(attack, defense) prior mean for a promoted team, or (None, None).

    For every COMPLETED season in `train` that has a previous season:
      1. find the promoted teams (_promoted_teams);
      2. fit that season on its own, so each promoted team is measured over
         its full promoted season (38 matches) and nothing else;
      3. record each promoted team's gap to the average established team.
    The prior is the average gap. A gap to established teams is used, not to
    the league average, because in fit() the established teams' prior mean is
    0 and the promoted prior has to be on that same scale.

    The season in progress is excluded: a few matches per team would add
    noise. All completed seasons in `train` are used, including ones older
    than the training window, because more promoted teams give a steadier
    average.
    """
    attack_gaps = []
    defense_gaps = []
    for season in sorted(train["season"].unique()):
        matches = train[train["season"] == season]
        if len(matches) != MATCHES_PER_SEASON:
            continue  # in progress, or cut short by the training cutoff
        promoted = _promoted_teams(train, season)
        if not promoted:
            continue  # the earliest season: no previous season to compare with
        season_teams = set(matches["home"]) | set(matches["away"])
        established = season_teams - promoted

        no_prior = {team: 0.0 for team in season_teams}
        _, _, attack, defense = _fit_penalized(matches, no_prior, no_prior, NEAR_ZERO_STRENGTH)
        established_attack = np.mean([attack[team] for team in established])
        established_defense = np.mean([defense[team] for team in established])
        attack_gaps += [attack[team] - established_attack for team in promoted]
        defense_gaps += [defense[team] - established_defense for team in promoted]

    if not attack_gaps:
        return None, None
    return float(np.mean(attack_gaps)), float(np.mean(defense_gaps))


def _strength(fitted, team):
    """(attack, defense) for a team; the promoted prior if it was never fitted.

    A team with any match in the training window was fitted (and shrunk
    toward its prior mean); only a team with zero matches lands here.
    """
    if team in fitted.attack:
        return fitted.attack[team], fitted.defense[team]
    if fitted.promoted_attack is None or fitted.promoted_defense is None:
        raise ValueError(
            f"No fitted strength for '{team}' and no promoted-team prior: "
            f"the training data has no completed season to learn it from."
        )
    return fitted.promoted_attack, fitted.promoted_defense


def predict(fitted, home, away) -> dict:
    """Forecast one match. Returns a dict with keys
    p_home, p_draw, p_away, exp_home_goals, exp_away_goals.

    exp_home_goals and exp_away_goals are the two Poisson means from the
    FittedModel formula. A team missing from fitted.attack uses
    promoted_attack / promoted_defense; if those are None, raise ValueError
    naming the team.

    p_home, p_draw, p_away come from a scoreline grid of 0-10 goals for each
    side: P(i, j) = Poisson(i; exp_home_goals) * Poisson(j; exp_away_goals).
    Sum the cells with i > j, i == j and i < j, then divide by the grid total
    so the three probabilities sum to exactly 1 (the grid cuts off the tiny
    probability of 11+ goals).
    """
    home_attack, home_defense = _strength(fitted, home)
    away_attack, away_defense = _strength(fitted, away)
    exp_home_goals = np.exp(fitted.intercept + fitted.home_advantage + home_attack + away_defense)
    exp_away_goals = np.exp(fitted.intercept + away_attack + home_defense)

    # grid[i, j] = P(home scores i) * P(away scores j): independence means the
    # joint probability is just the product of the two Poisson probabilities.
    goals = np.arange(MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(goals, exp_home_goals), poisson.pmf(goals, exp_away_goals))
    grid = grid / grid.sum()  # renormalize for the 11+ goals the grid cuts off

    return {
        "p_home": float(np.tril(grid, -1).sum()),  # below the diagonal: i > j
        "p_draw": float(np.trace(grid)),  # the diagonal: i == j
        "p_away": float(np.triu(grid, 1).sum()),  # above the diagonal: i < j
        "exp_home_goals": float(exp_home_goals),
        "exp_away_goals": float(exp_away_goals),
    }
