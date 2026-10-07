"""Tests for the shrinkage of team strengths toward their prior means."""

import numpy as np
import pandas as pd

from pipeline import ingest, model
from test_model import synthetic_league

# A fixed cutoff, so these tests see the same matches every time they run:
# five rounds into 2026-27, when the two newly promoted teams (Coventry and
# Hull) have exactly 5 matches each.
CUTOFF = pd.Timestamp("2026-10-10 11:30", tz="UTC")


def real_fits():
    """The real fit and the near-unpenalized fit on the same training data."""
    train = ingest.get_training_data(ingest.load_history(), CUTOFF)
    window_start = train["kickoff_utc"].max() - pd.Timedelta(days=model.TRAINING_WINDOW_DAYS)
    window = train[train["kickoff_utc"] > window_start]
    matches_played = pd.concat([window["home"], window["away"]]).value_counts()
    shrunk = model.fit(train)
    unpenalized = model.fit_with_strength(train, model.NEAR_ZERO_STRENGTH)
    return shrunk, unpenalized, matches_played


def relative_to_established(params, established):
    """Each team's value minus the average of the established teams.

    Only differences between teams affect predictions (a shift in every
    attack is absorbed by the intercept), and the prior means are defined as
    gaps to established teams, so this is the scale to compare on.
    """
    mean = np.mean([params[team] for team in established])
    return {team: value - mean for team, value in params.items()}


def test_team_with_zero_goals_gets_finite_attack():
    matches, _, _ = synthetic_league()
    kickoff = matches["kickoff_utc"].max()
    # A new team plays 3 matches and never scores. Without a penalty the best
    # attack estimate is minus infinity and the fit diverges.
    new_rows = pd.DataFrame(
        {
            "season": "S4",
            "kickoff_utc": [kickoff + pd.Timedelta(hours=h) for h in (1, 2, 3)],
            "home": ["NEW", "T00", "NEW"],
            "away": ["T00", "NEW", "T01"],
            "home_goals": [0, 2, 0],
            "away_goals": [1, 0, 3],
        }
    )
    fitted = model.fit(pd.concat([matches, new_rows], ignore_index=True))

    assert np.isfinite(fitted.attack["NEW"])
    assert np.isfinite(fitted.defense["NEW"])
    prediction = model.predict(fitted, "NEW", "T00")
    assert np.isfinite(prediction["p_home"]) and prediction["p_home"] > 0


def test_five_match_promoted_team_lies_between_data_and_prior():
    shrunk, unpenalized, matches_played = real_fits()
    established = [team for team, n in matches_played.items() if n >= 70]
    promoted = [team for team, n in matches_played.items() if n == 5]
    assert sorted(promoted) == ["Coventry", "Hull"]

    for name, prior_mean in [("attack", shrunk.promoted_attack), ("defense", shrunk.promoted_defense)]:
        shrunk_values = relative_to_established(getattr(shrunk, name), established)
        unpenalized_values = relative_to_established(getattr(unpenalized, name), established)
        for team in promoted:
            low, high = sorted([unpenalized_values[team], prior_mean])
            assert low < shrunk_values[team] < high, (team, name)


def test_teams_with_many_matches_barely_move():
    shrunk, unpenalized, matches_played = real_fits()
    established = [team for team, n in matches_played.items() if n >= 70]
    assert len(established) >= 15

    for name in ["attack", "defense"]:
        shrunk_values = relative_to_established(getattr(shrunk, name), established)
        unpenalized_values = relative_to_established(getattr(unpenalized, name), established)
        for team in established:
            assert abs(shrunk_values[team] - unpenalized_values[team]) < 0.05, (team, name)
