"""Independent Poisson goals model. INTERFACE ONLY: the owner writes fit and predict.

tests/test_model.py defines what the implementation must satisfy.
"""

from dataclasses import dataclass


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
    raise NotImplementedError("Owner implements this")


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
    raise NotImplementedError("Owner implements this")
