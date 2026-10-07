"""Independent Poisson goals model: team attack, team defense, home advantage.

tests/test_model.py defines what this implementation must satisfy.
MODEL_NOTES.md explains each modeling decision.

Deliberately left out of this version (future work, to be judged by the
Phase 2 backtest rather than added on faith):
  - time-decay weighting (recent matches counting more than old ones);
  - the Dixon-Coles correction for low-scoring draws (0-0, 1-1).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import poisson

# Only matches within this many days before the latest kickoff in `train` are
# used for fitting. The tradeoff: a short window follows current strength
# (squads and managers change) but leaves few matches per team, so estimates
# are noisy; a long window is stable but describes teams as they used to be.
# 730 days is about two seasons, roughly 76 matches per ever-present team.
# This value is a starting point and has NOT been tuned. Tuning it belongs to
# the Phase 2 backtest.
TRAINING_WINDOW_DAYS = 730

MAX_GOALS = 10  # the scoreline grid covers 0-10 goals for each side


@dataclass
class FittedModel:
    """Fitted parameters, all on the log scale.

    Expected goals for a match are:
        home: exp(intercept + home_advantage + attack[home] + defense[away])
        away: exp(intercept + attack[away] + defense[home])

    attack:  higher means the team scores more.
    defense: higher means the team CONCEDES more (a weaker defense).
    Only differences between teams are identified, so store attack and defense
    centered (each averaging zero across teams) with the level in `intercept`.

    promoted_attack / promoted_defense are the prior used for a team with no
    training data. They are None when the training data contains no promoted
    team to learn the prior from.
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

    Model: a Poisson GLM (statsmodels, log link) on goals. Reshape the data to
    one row per team per match (two rows per match) and regress goals on:
      - the scoring team (attack),
      - the conceding team (defense),
      - a home indicator (home advantage, one league-wide value).
    Home and away goals are treated as independent given these parameters.

    Promoted-team prior: a team with no Premier League matches in `train` has
    no fitted strength. Its prior is the average fitted attack and the average
    fitted defense of promoted teams in past seasons. Promoted teams are
    identified FROM THE DATA, not hardcoded: a team is promoted in season S if
    it plays in S but not in the previous season in `train`. The earliest
    season in `train` has no previous season, so it contributes none.
    """
    latest = train["kickoff_utc"].max()
    window = train[train["kickoff_utc"] > latest - pd.Timedelta(days=TRAINING_WINDOW_DAYS)]

    # Long format: two rows per match, one for each side's goals.
    home_rows = pd.DataFrame(
        {
            "team": window["home"].to_numpy(),
            "opponent": window["away"].to_numpy(),
            "home": 1.0,
            "goals": window["home_goals"].to_numpy(dtype=float),
        }
    )
    away_rows = pd.DataFrame(
        {
            "team": window["away"].to_numpy(),
            "opponent": window["home"].to_numpy(),
            "home": 0.0,
            "goals": window["away_goals"].to_numpy(dtype=float),
        }
    )
    long = pd.concat([home_rows, away_rows], ignore_index=True)
    teams = sorted(set(long["team"]))

    # Parameterization. One indicator column per team for attack and one per
    # team for defense would not be identifiable: adding 1 to every attack and
    # subtracting 1 from the intercept gives the same expected goals. So the
    # GLM is fitted with a REFERENCE TEAM: the first team alphabetically has
    # no columns (drop_first=True), which fixes its attack and defense at 0
    # and makes every other team's value "relative to the reference team".
    # That is the simplest design matrix to build and to explain.
    attack_cols = pd.get_dummies(long["team"], prefix="attack", drop_first=True, dtype=float)
    defense_cols = pd.get_dummies(long["opponent"], prefix="defense", drop_first=True, dtype=float)
    design = pd.concat([attack_cols, defense_cols, long[["home"]]], axis=1)
    design = sm.add_constant(design)
    result = sm.GLM(long["goals"], design, family=sm.families.Poisson()).fit()

    attack = {team: result.params.get(f"attack_{team}", 0.0) for team in teams}
    defense = {team: result.params.get(f"defense_{team}", 0.0) for team in teams}

    # The fitted values are then re-expressed as SUM-TO-ZERO: subtract each
    # mean and move it into the intercept. Expected goals are unchanged, but
    # the numbers no longer depend on which team was the reference: 0 is an
    # average team, and exp(intercept) is the goals an average team scores
    # away against an average team.
    attack_mean = np.mean(list(attack.values()))
    defense_mean = np.mean(list(defense.values()))
    attack = {team: float(value - attack_mean) for team, value in attack.items()}
    defense = {team: float(value - defense_mean) for team, value in defense.items()}
    intercept = float(result.params["const"] + attack_mean + defense_mean)

    # Promoted-team prior: the average fitted strength of promoted teams.
    # Known limitation: a promoted team's fitted strength uses ALL its matches
    # in the window, including any later seasons in which it stayed up.
    promoted = _promoted_teams(train, window)
    if promoted:
        promoted_attack = float(np.mean([attack[team] for team in promoted]))
        promoted_defense = float(np.mean([defense[team] for team in promoted]))
    else:
        promoted_attack = None
        promoted_defense = None

    return FittedModel(
        intercept=intercept,
        home_advantage=float(result.params["home"]),
        attack=attack,
        defense=defense,
        promoted_attack=promoted_attack,
        promoted_defense=promoted_defense,
    )


def _promoted_teams(train, window):
    """Teams promoted into a season that has matches in the training window.

    Found from the data: a team is promoted in season S if it plays in S but
    not in the season before S in `train`. Season membership is read from all
    of `train` (so the season before the window is known), but only seasons
    with matches in the window count, because only those teams have a fitted
    strength that reflects their time as a promoted side.
    """
    seasons = sorted(train["season"].unique())  # e.g. '2024-25' sorts by date
    window_seasons = set(window["season"])
    promoted = set()
    for previous, season in zip(seasons, seasons[1:]):
        if season not in window_seasons:
            continue
        in_previous = train[train["season"] == previous]
        in_season = window[window["season"] == season]
        promoted |= (set(in_season["home"]) | set(in_season["away"])) - (
            set(in_previous["home"]) | set(in_previous["away"])
        )
    return sorted(promoted)


def _strength(fitted, team):
    """(attack, defense) for a team; the promoted prior if it was never fitted.

    The prior applies ONLY to teams with zero matches in the training window.
    Known limitation: a team with even a few matches is fitted normally, so
    its estimate early in a season is very noisy.
    """
    if team in fitted.attack:
        return fitted.attack[team], fitted.defense[team]
    if fitted.promoted_attack is None or fitted.promoted_defense is None:
        raise ValueError(
            f"No fitted strength for '{team}' and no promoted-team prior: "
            f"the training data contains no promoted team to learn it from."
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
