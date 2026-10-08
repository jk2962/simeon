"""Monte Carlo season simulation. `python -m pipeline.simulate` locks a snapshot.

Every remaining fixture of the season is played out N_RUNS times and the
final tables are counted. Each run draws its own team parameters, so the
spread of the results reflects how uncertain the fitted strengths are, not
only match-day luck. See laplace_covariance for how they are drawn.

What the spread still leaves out: the promoted-team prior mean is treated as
known, team strengths are held fixed for the rest of the season (no
transfers, injuries or form), and the model itself is assumed to be right.
"""

import numpy as np
import pandas as pd

from pipeline import ingest, model, validate
from pipeline.run import (
    FORECASTS_DIR,
    UTC_FORMAT,
    git,
    is_whole_round,
    lock_units,
    round_started,
)

N_RUNS = 10_000
SEED = 2026  # recorded in the snapshot, so a locked file can be reproduced
TEAMS_PER_SEASON = 20
MATCHES_PER_TEAM = 38
TOP = 4
RELEGATED = 3

# The fit stops at a convergence tolerance, so fitted goals match actual
# goals closely, not exactly (see the check in laplace_covariance).
GOALS_CHECK_RTOL = 1e-3


def current_table(season_df):
    """Played, points, goal difference and goals scored per team so far."""
    home = pd.DataFrame(
        {"team": season_df["home"], "gf": season_df["home_goals"], "ga": season_df["away_goals"]}
    )
    away = pd.DataFrame(
        {"team": season_df["away"], "gf": season_df["away_goals"], "ga": season_df["home_goals"]}
    )
    rows = pd.concat([home, away], ignore_index=True).astype({"gf": int, "ga": int})
    rows["points"] = np.where(rows["gf"] > rows["ga"], 3, np.where(rows["gf"] == rows["ga"], 1, 0))
    rows["gd"] = rows["gf"] - rows["ga"]
    return rows.groupby("team").agg(
        played=("gf", "size"), points=("points", "sum"), gd=("gd", "sum"), gf=("gf", "sum")
    )


def laplace_covariance(fitted, train):
    """Covariance of the fitted parameters, used to draw them at random.

    model.fit returns the MAP estimate: the peak of the posterior under a
    Normal(0, 1 / PRIOR_STRENGTH) prior on each team deviation. The Laplace
    approximation treats the posterior as a normal distribution centred on
    that peak, whose covariance is the inverse of the curvature there:

        curvature = X' diag(expected goals) X + PRIOR_STRENGTH on each deviation

    The first term is the information in the matches, the second the prior.
    A team with few goals has little of the first, so its draws vary a lot.

    Returns (teams, covariance). Parameter order: intercept, home advantage,
    one attack per team, one defense per team, with teams in the order given.

    The design matrix X is rebuilt here, the same way as in
    model._fit_penalized, because the fit does not return it. The check
    below catches the two drifting apart.
    """
    latest = train["kickoff_utc"].max()
    window = train[train["kickoff_utc"] > latest - pd.Timedelta(days=model.TRAINING_WINDOW_DAYS)]
    teams = sorted(fitted.attack)
    index = {team: i for i, team in enumerate(teams)}
    home = window["home"].map(index).to_numpy()
    away = window["away"].map(index).to_numpy()
    n = len(window)

    # Two rows per match, home side first: the scoring team's attack, the
    # conceding team's defense, and a home indicator.
    scoring = np.concatenate([home, away])
    conceding = np.concatenate([away, home])
    is_home = np.concatenate([np.ones(n), np.zeros(n)])
    goals = np.concatenate(
        [window["home_goals"].to_numpy(dtype=float), window["away_goals"].to_numpy(dtype=float)]
    )
    design = np.zeros((2 * n, 2 + 2 * len(teams)))
    design[:, 0] = 1.0
    design[:, 1] = is_home
    design[np.arange(2 * n), 2 + scoring] = 1.0
    design[np.arange(2 * n), 2 + len(teams) + conceding] = 1.0

    attack = np.array([fitted.attack[team] for team in teams])
    defense = np.array([fitted.defense[team] for team in teams])
    expected = np.exp(
        fitted.intercept + fitted.home_advantage * is_home + attack[scoring] + defense[conceding]
    )

    # At the MAP the two unpenalized parameters satisfy: fitted goals equal
    # actual goals, in total (intercept) and for the home side (home
    # advantage). If this fails, X no longer matches the fit.
    for label, rows in [("all", slice(None)), ("home", is_home == 1)]:
        if not np.isclose(expected[rows].sum(), goals[rows].sum(), rtol=GOALS_CHECK_RTOL):
            raise ValueError(
                f"Laplace check failed ({label} goals): fitted {expected[rows].sum():.2f}, "
                f"actual {goals[rows].sum():.0f}. The design here no longer matches model.fit."
            )

    penalty = np.r_[0.0, 0.0, np.full(2 * len(teams), model.PRIOR_STRENGTH)]
    curvature = design.T @ (expected[:, None] * design) + np.diag(penalty)
    return teams, np.linalg.inv(curvature)


def simulate_positions(table, fixtures, fitted, teams, deviations, rng):
    """Play the remaining fixtures once per row of `deviations`.

    table: current_table() for the teams of the season.
    deviations: shape (n_runs, n_parameters), added to the fitted parameters
    in the order of laplace_covariance. All zeros means every run uses the
    point estimates.

    Returns (expected final points per team, DataFrame of finishing-position
    probabilities: one row per team, columns 1..n_teams).

    Goals are drawn straight from the two Poisson means, without the 0-10
    grid of model.predict (the grid drops about one scoreline in a million).
    Ties are broken as the Premier League does up to goals scored (points,
    goal difference, goals scored) and at random after that.
    """
    names = list(table.index)
    missing = sorted(set(names) - set(teams))
    if missing:
        raise ValueError(f"No fitted strength for {missing}")
    cols = [teams.index(team) for team in names]
    n_runs, n_teams = len(deviations), len(names)

    intercept = fitted.intercept + deviations[:, 0]
    home_advantage = fitted.home_advantage + deviations[:, 1]
    attack = np.array([fitted.attack[t] for t in names]) + deviations[:, 2 : 2 + len(teams)][:, cols]
    defense = np.array([fitted.defense[t] for t in names]) + deviations[:, 2 + len(teams) :][:, cols]

    points = np.tile(table["points"].to_numpy(dtype=float), (n_runs, 1))
    gd = np.tile(table["gd"].to_numpy(dtype=float), (n_runs, 1))
    gf = np.tile(table["gf"].to_numpy(dtype=float), (n_runs, 1))
    for home, away in zip(fixtures["home"], fixtures["away"]):
        h, a = names.index(home), names.index(away)
        home_goals = rng.poisson(np.exp(intercept + home_advantage + attack[:, h] + defense[:, a]))
        away_goals = rng.poisson(np.exp(intercept + attack[:, a] + defense[:, h]))
        draw = home_goals == away_goals
        points[:, h] += 3 * (home_goals > away_goals) + draw
        points[:, a] += 3 * (away_goals > home_goals) + draw
        gd[:, h] += home_goals - away_goals
        gd[:, a] += away_goals - home_goals
        gf[:, h] += home_goals
        gf[:, a] += away_goals

    # lexsort sorts ascending with the LAST key first, so negate to put the
    # best team in column 0. order[run, position] is a team index.
    order = np.lexsort((rng.random((n_runs, n_teams)), -gf, -gd, -points))
    counts = np.zeros((n_teams, n_teams))
    np.add.at(counts, (order, np.arange(n_teams)[None, :]), 1)
    positions = pd.DataFrame(counts / n_runs, index=names, columns=range(1, n_teams + 1))
    return pd.Series(points.mean(axis=0), index=names), positions


def position_spread(positions):
    """Standard deviation of finishing position, averaged over teams."""
    place = positions.columns.to_numpy(dtype=float)
    mean = positions.to_numpy() @ place
    return float(np.sqrt(positions.to_numpy() @ place**2 - mean**2).mean())


def snapshot():
    """Simulate the rest of the season and lock it before the next round.

    Written to forecasts/<season>/table-round-NN.csv under the same rules as
    run.forecast: a clean working tree, a round that has not started, and no
    overwriting.
    """
    if git("status", "--porcelain"):
        raise SystemExit("REFUSING TO SIMULATE: the working tree has uncommitted changes.")
    model_version = git("rev-parse", "--short", "HEAD")

    history = ingest.load_history()
    season = ingest.season_label(ingest.CURRENT_SEASON)
    validate.validate_history(history, season)
    fixtures = ingest.load_fixtures()

    # One table per round: a rescheduled match on its own gets none. Locked
    # forecasts are ignored ({}), so this picks the same round whether it
    # runs before or after run.forecast.
    now = pd.Timestamp.now(tz="UTC")
    round_df = next((u for u in lock_units(fixtures, now, {}) if is_whole_round(u)), None)
    if round_df is None:
        raise SystemExit("REFUSING TO SIMULATE: no upcoming round.")
    matchday = int(round_df["matchday"].iloc[0])
    first_kickoff = round_df["kickoff_utc"].min()

    path = FORECASTS_DIR / season / f"table-round-{matchday:02d}.csv"
    if path.exists():
        raise FileExistsError(f"{path} already exists. Snapshots are never overwritten.")
    if round_started(fixtures, matchday, now):
        raise SystemExit(
            f"REFUSING TO SIMULATE: round {matchday} has already kicked off, "
            "or its fixture list is incomplete."
        )

    # Same cutoff as the round's match forecasts.
    train = ingest.get_training_data(history, first_kickoff)
    table = current_table(train[train["season"] == season])
    # Every unplayed fixture, including postponed ones with no date.
    remaining = pd.concat([fixtures["home"], fixtures["away"]]).value_counts()
    total = table["played"].add(remaining, fill_value=0)
    if len(total) != TEAMS_PER_SEASON or (total != MATCHES_PER_TEAM).any():
        raise ValueError(
            "Results plus fixtures do not give every team 38 matches "
            f"(fixtures from {fixtures.attrs['source']}):\n{total[total != MATCHES_PER_TEAM]}"
        )

    fitted = model.fit(train)
    teams, covariance = laplace_covariance(fitted, train)
    # The same seed for both, so the only difference is the parameter draws.
    rng = np.random.default_rng(SEED)
    deviations = rng.multivariate_normal(np.zeros(len(covariance)), covariance, size=N_RUNS)
    exp_points, positions = simulate_positions(table, fixtures, fitted, teams, deviations, rng)
    _, fixed_positions = simulate_positions(
        table, fixtures, fitted, teams, np.zeros_like(deviations), np.random.default_rng(SEED)
    )

    # Validate before anything is written.
    if not np.allclose(positions.sum(axis=1), 1.0) or not np.allclose(positions.sum(axis=0), 1.0):
        raise ValueError("Position probabilities do not sum to 1 by team and by position")
    # A match hands out 3 points, or 2 if drawn.
    points_per_match = (exp_points.sum() - table["points"].sum()) / len(fixtures)
    draw_rate = 3 - points_per_match
    if not 0.15 < draw_rate < 0.35:
        raise ValueError(f"Implausible simulated draw rate: {draw_rate:.3f}")

    out = pd.DataFrame(
        {
            "season": season,
            "matchday": matchday,
            "team": table.index,
            "played": table["played"].to_numpy(),
            "points": table["points"].to_numpy(),
            "exp_points": exp_points.to_numpy(),
            "p_title": positions[1].to_numpy(),
            "p_top4": positions.loc[:, :TOP].sum(axis=1).to_numpy(),
            "p_relegation": positions.iloc[:, -RELEGATED:].sum(axis=1).to_numpy(),
        }
    )
    out = pd.concat([out, positions.add_prefix("pos_").reset_index(drop=True)], axis=1)
    out = out.assign(
        model_version=model_version,
        prior_strength=model.PRIOR_STRENGTH,
        n_runs=N_RUNS,
        seed=SEED,
        generated_at_utc=now.strftime(UTC_FORMAT),
        data_through_utc=train["kickoff_utc"].max().strftime(UTC_FORMAT),
        last_round_included=matchday - 1,
        fixtures_source=fixtures.attrs["source"],
    )
    out = out.sort_values("exp_points", ascending=False, kind="stable")

    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, mode="x")  # "x": fail if the file exists

    print(f"\n== Season simulation: {season}, locked before round {matchday} ==")
    print(f"Model version {model_version} | {N_RUNS} runs | seed {SEED} | fixtures from {fixtures.attrs['source']}")
    print(f"Generated {now.strftime(UTC_FORMAT)} | data through {train['kickoff_utc'].max().strftime(UTC_FORMAT)}")
    print(f"Remaining fixtures: {len(fixtures)} | simulated draw rate {draw_rate:.3f}\n")
    print(f"{'Team':<20}{'Pld':>4}{'Pts':>5}{'Exp pts':>9}{'Title':>8}{'Top 4':>8}{'Releg.':>8}")
    for row in out.itertuples():
        print(
            f"{row.team:<20}{row.played:>4}{row.points:>5}{row.exp_points:>9.1f}"
            f"{row.p_title:>8.1%}{row.p_top4:>8.1%}{row.p_relegation:>8.1%}"
        )
    sampled, fixed = position_spread(positions), position_spread(fixed_positions)
    print(
        f"\nSpread of finishing position (standard deviation, averaged over teams): "
        f"{sampled:.2f} with parameter draws, {fixed:.2f} with fixed estimates "
        f"({sampled / fixed - 1:+.0%})"
    )
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    snapshot()
