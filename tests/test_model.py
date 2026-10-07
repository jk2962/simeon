"""Tests the owner's model.fit and model.predict must pass.

They are skipped while those functions raise NotImplementedError.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline import ingest, model

SKIP_REASON = "pipeline/model.py is not implemented yet (the owner writes fit and predict)"

# True parameters of the synthetic league (log scale, see model.FittedModel).
TRUE_INTERCEPT = 0.10
TRUE_HOME_ADVANTAGE = 0.25
N_TEAMS = 20
N_SEASONS = 5  # 5 double round robins of 20 teams = 1900 matches

# Recovery tolerances on the log scale. With 1900 matches each team has about
# 250 goals for and against, so a team parameter has a standard error near
# 0.07 and home advantage near 0.03. The tolerances are roughly 3 standard
# errors: loose enough for noise, tight enough to catch a wrong model.
TEAM_TOLERANCE = 0.25
HOME_ADVANTAGE_TOLERANCE = 0.10


def fit_or_skip(train):
    try:
        return model.fit(train)
    except NotImplementedError:
        pytest.skip(SKIP_REASON)


def predict_or_skip(fitted, home, away):
    try:
        return model.predict(fitted, home, away)
    except NotImplementedError:
        pytest.skip(SKIP_REASON)


def synthetic_league():
    """Seeded matches drawn from known attack, defense and home parameters."""
    rng = np.random.default_rng(42)
    teams = [f"T{i:02d}" for i in range(N_TEAMS)]
    attack = rng.normal(0, 0.3, N_TEAMS)
    defense = rng.normal(0, 0.3, N_TEAMS)
    attack -= attack.mean()
    defense -= defense.mean()

    rows = []
    kickoff = pd.Timestamp("2020-08-01 14:00", tz="UTC")
    for season in range(N_SEASONS):
        for h in range(N_TEAMS):
            for a in range(N_TEAMS):
                if h == a:
                    continue
                home_mean = np.exp(TRUE_INTERCEPT + TRUE_HOME_ADVANTAGE + attack[h] + defense[a])
                away_mean = np.exp(TRUE_INTERCEPT + attack[a] + defense[h])
                rows.append(
                    {
                        "season": f"S{season}",
                        "kickoff_utc": kickoff,
                        "home": teams[h],
                        "away": teams[a],
                        "home_goals": rng.poisson(home_mean),
                        "away_goals": rng.poisson(away_mean),
                    }
                )
                kickoff += pd.Timedelta(hours=1)
    matches = pd.DataFrame(rows)
    return matches, dict(zip(teams, attack)), dict(zip(teams, defense))


def centered(params):
    """Subtract the mean, so the comparison does not depend on how the
    implementation splits the overall level between intercept and teams."""
    mean = np.mean(list(params.values()))
    return {team: value - mean for team, value in params.items()}


def real_training_data():
    """Everything before the first kickoff of the current season."""
    history = ingest.load_history()
    current = history[history["season"] == ingest.season_label(ingest.CURRENT_SEASON)]
    train = ingest.get_training_data(history, current["kickoff_utc"].min())
    return train, current


def test_probabilities_sum_to_one():
    matches, _, _ = synthetic_league()
    fitted = fit_or_skip(matches)
    for home, away in [("T00", "T01"), ("T05", "T19"), ("T19", "T00")]:
        p = predict_or_skip(fitted, home, away)
        assert abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1.0) <= 1e-9
        assert min(p["p_home"], p["p_draw"], p["p_away"]) > 0


def test_fit_recovers_known_parameters():
    matches, true_attack, true_defense = synthetic_league()
    fitted = fit_or_skip(matches)

    assert abs(fitted.home_advantage - TRUE_HOME_ADVANTAGE) <= HOME_ADVANTAGE_TOLERANCE

    fitted_attack = centered(fitted.attack)
    fitted_defense = centered(fitted.defense)
    for team in true_attack:
        assert abs(fitted_attack[team] - true_attack[team]) <= TEAM_TOLERANCE, team
        assert abs(fitted_defense[team] - true_defense[team]) <= TEAM_TOLERANCE, team


def test_promoted_team_gets_finite_prediction():
    train, current = real_training_data()
    fitted = fit_or_skip(train)

    # Promoted teams are found from the data: in the current season, but with
    # no match in the training data.
    current_teams = set(current["home"]) | set(current["away"])
    promoted = sorted(current_teams - set(train["home"]) - set(train["away"]))
    assert promoted, "expected at least one team with no training data"
    established = sorted(current_teams & set(train["home"]))[0]

    for home, away in [(promoted[0], established), (established, promoted[0])]:
        p = predict_or_skip(fitted, home, away)
        for key in ["p_home", "p_draw", "p_away", "exp_home_goals", "exp_away_goals"]:
            assert np.isfinite(p[key]), key
        assert abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1.0) <= 1e-9


def test_home_advantage_is_positive_on_real_data():
    train, _ = real_training_data()
    fitted = fit_or_skip(train)
    assert fitted.home_advantage > 0
