import numpy as np
import pandas as pd
import pytest

from pipeline import ingest, model, simulate

TEAMS = ["A", "B", "C", "D"]


def toy_league():
    """Four level teams except A, which scores far more. Nothing played yet."""
    fitted = model.FittedModel(
        intercept=0.0,
        home_advantage=0.2,
        attack={"A": 1.5, "B": 0.0, "C": 0.0, "D": 0.0},
        defense={team: 0.0 for team in TEAMS},
        promoted_attack=None,
        promoted_defense=None,
    )
    table = pd.DataFrame({"played": 0, "points": 0, "gd": 0, "gf": 0}, index=TEAMS)
    pairs = [(h, a) for h in TEAMS for a in TEAMS if h != a]
    fixtures = pd.DataFrame(pairs, columns=["home", "away"])
    return fitted, table, fixtures


def test_positions_sum_to_one_and_the_strong_team_wins():
    fitted, table, fixtures = toy_league()
    deviations = np.zeros((2000, 2 + 2 * len(TEAMS)))
    exp_points, positions = simulate.simulate_positions(
        table, fixtures, fitted, TEAMS, deviations, np.random.default_rng(0)
    )
    assert positions.sum(axis=1).to_numpy() == pytest.approx(1.0)
    assert positions.sum(axis=0).to_numpy() == pytest.approx(1.0)
    assert positions.loc["A", 1] > 0.8
    assert exp_points["A"] > exp_points["B"]
    # 12 matches, each worth 2 or 3 points.
    assert 24 <= exp_points.sum() <= 36


def test_parameter_draws_widen_the_position_distribution():
    fitted, table, fixtures = toy_league()
    rng = np.random.default_rng(0)
    fixed = np.zeros((2000, 2 + 2 * len(TEAMS)))
    noisy = rng.normal(0.0, 0.5, size=fixed.shape)
    _, fixed_positions = simulate.simulate_positions(table, fixtures, fitted, TEAMS, fixed, rng)
    _, noisy_positions = simulate.simulate_positions(table, fixtures, fitted, TEAMS, noisy, rng)
    assert simulate.position_spread(noisy_positions) > simulate.position_spread(fixed_positions)


def test_current_table_counts_points_and_goals():
    season = pd.DataFrame(
        {"home": ["A", "B"], "away": ["B", "A"], "home_goals": [2, 1], "away_goals": [0, 1]}
    )
    table = simulate.current_table(season)
    assert table.loc["A"].tolist() == [2, 4, 2, 3]  # played, points, gd, gf
    assert table.loc["B"].tolist() == [2, 1, -2, 1]


def test_laplace_covariance_on_real_data():
    history = ingest.load_history()
    train = ingest.get_training_data(history, pd.Timestamp.now(tz="UTC"))
    fitted = model.fit(train)
    teams, covariance = simulate.laplace_covariance(fitted, train)  # runs the goals check

    assert covariance.shape == (2 + 2 * len(teams),) * 2
    assert np.allclose(covariance, covariance.T)
    assert (np.linalg.eigvalsh(covariance) > 0).all()

    # Less data means more uncertainty: the team with the fewest matches in
    # the window has a wider attack than the team with the most.
    window = train[
        train["kickoff_utc"]
        > train["kickoff_utc"].max() - pd.Timedelta(days=model.TRAINING_WINDOW_DAYS)
    ]
    matches = pd.concat([window["home"], window["away"]]).value_counts()
    attack_variance = pd.Series(np.diag(covariance)[2 : 2 + len(teams)], index=teams)
    assert attack_variance[matches.idxmin()] > attack_variance[matches.idxmax()]
