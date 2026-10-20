"""Retrospective forecasts for rounds played before forecasts were locked.

`python -m pipeline.retro` writes forecasts/<season>/retro-round-NN.csv and
retro-table-round-NN.csv for rounds 1-5 of 2026-27. Each round is fitted, as
in run.forecast, on matches that kicked off before the round's first kickoff,
so round N sees only earlier rounds and earlier seasons. The season table
simulates every other fixture of the season as unplayed, the same way as
simulate.snapshot.

These are NOT locked forecasts. They were made after the results were known,
by code written after those rounds were played (the promoted-team rule fix
and the PRIOR_STRENGTH decision of 2026-10-07), so they are not evidence
under the model change policy. The file name keeps them out of every
`round-*.csv` glob: score(), the lock logic and scores.csv never see them.
The export shows them on the website labelled as retrospective.
"""

import dataclasses
import os

import numpy as np
import pandas as pd
import requests

from pipeline import ingest, model, simulate, validate
from pipeline.run import FORECASTS_DIR, UTC_FORMAT, git

ROUNDS = range(1, 6)
LOCK_REASON = "retrospective"


def match_ids():
    """{(home, away): (match_id, matchday)} for the season, from football-data.org."""
    ingest.load_env_file()
    token = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not token:
        raise SystemExit("STOP: FOOTBALL_DATA_API_KEY is not set; matchdays come from football-data.org.")
    response = requests.get(ingest.FIXTURES_URL, headers={"X-Auth-Token": token}, timeout=30)
    response.raise_for_status()
    matches = response.json()["matches"]
    home = ingest.canonical_names(pd.Series([m["homeTeam"]["name"] for m in matches]), "fd_org_name")
    away = ingest.canonical_names(pd.Series([m["awayTeam"]["name"] for m in matches]), "fd_org_name")
    return {(h, a): (m["id"], m["matchday"]) for h, a, m in zip(home, away, matches)}


def retro_round(history, played, generated_at, model_version):
    """Forecast one already-played round as if before its first kickoff."""
    train = ingest.get_training_data(history, played["kickoff_utc"].min())
    fitted = model.fit(train)
    rows = []
    for _, match in played.iterrows():
        rows.append(
            {
                "match_id": match["match_id"],
                "matchday": match["matchday"],
                "kickoff_utc": match["kickoff_utc"].strftime(UTC_FORMAT),
                "home": match["home"],
                "away": match["away"],
                **model.predict(fitted, match["home"], match["away"]),
                "model_version": model_version,
                "prior_strength": model.PRIOR_STRENGTH,
                "generated_at_utc": generated_at,
                "data_through_utc": train["kickoff_utc"].max().strftime(UTC_FORMAT),
                "fixtures_source": "api",
                "lock_reason": LOCK_REASON,
            }
        )
    return pd.DataFrame(rows)


def with_unfitted(fitted, teams, covariance, names):
    """Add teams with no match in the window to the fit and its covariance.

    Only before round 1: a newly promoted team with no recent Premier League
    match. It gets the promoted prior mean and, with no data, the prior alone
    as its uncertainty (variance 1 / PRIOR_STRENGTH, no correlation with any
    other parameter), which is what laplace_covariance gives a parameter
    that no match touches. Only used here: the live simulation never needs it.
    """
    extra = sorted(set(names) - set(teams))
    if not extra:
        return fitted, teams, covariance
    attack = {**fitted.attack, **{t: fitted.promoted_attack for t in extra}}
    defense = {**fitted.defense, **{t: fitted.promoted_defense for t in extra}}
    new_teams = sorted(attack)
    # Old parameter order -> new: intercept, home advantage, attacks, defenses.
    old = [0, 1] + [2 + new_teams.index(t) for t in teams] + [2 + len(new_teams) + new_teams.index(t) for t in teams]
    size = 2 + 2 * len(new_teams)
    new_cov = np.eye(size) / model.PRIOR_STRENGTH
    new_cov[np.ix_(old, old)] = covariance
    return dataclasses.replace(fitted, attack=attack, defense=defense), new_teams, new_cov


def retro_table(history, current, pairs, matchday, generated_at, model_version):
    """Simulate the season as it stood before `matchday`'s first kickoff.

    pairs: every (home, away) of the season. Each pair meets once, so the
    remaining fixtures are the pairs not yet played by then.
    """
    season = current["season"].iloc[0]
    first_kickoff = current.loc[current["matchday"] == matchday, "kickoff_utc"].min()
    train = ingest.get_training_data(history, first_kickoff)
    so_far = train[train["season"] == season]
    names = sorted({home for home, _ in pairs})
    table = simulate.current_table(so_far).reindex(names, fill_value=0)
    remaining = pd.DataFrame(sorted(set(pairs) - set(zip(so_far["home"], so_far["away"]))), columns=["home", "away"])
    total = table["played"].add(pd.concat([remaining["home"], remaining["away"]]).value_counts(), fill_value=0)
    if len(total) != simulate.TEAMS_PER_SEASON or (total != simulate.MATCHES_PER_TEAM).any():
        raise ValueError(f"Round {matchday}: results plus fixtures do not give every team 38 matches")

    fitted = model.fit(train)
    fitted, teams, covariance = with_unfitted(fitted, *simulate.laplace_covariance(fitted, train), names)
    rng = np.random.default_rng(simulate.SEED)
    deviations = rng.multivariate_normal(np.zeros(len(covariance)), covariance, size=simulate.N_RUNS)
    exp_points, positions = simulate.simulate_positions(table, remaining, fitted, teams, deviations, rng)
    if not np.allclose(positions.sum(axis=1), 1.0) or not np.allclose(positions.sum(axis=0), 1.0):
        raise ValueError("Position probabilities do not sum to 1 by team and by position")

    out = simulate.table_rows(table, exp_points, positions, season, matchday).assign(
        model_version=model_version,
        prior_strength=model.PRIOR_STRENGTH,
        n_runs=simulate.N_RUNS,
        seed=simulate.SEED,
        generated_at_utc=generated_at,
        data_through_utc=train["kickoff_utc"].max().strftime(UTC_FORMAT),
        last_round_included=matchday - 1,
        fixtures_source="api",
        lock_reason=LOCK_REASON,
    )
    return out.sort_values("exp_points", ascending=False, kind="stable")


def main():
    if git("status", "--porcelain"):
        raise SystemExit("REFUSING: the working tree has uncommitted changes.")
    model_version = git("rev-parse", "--short", "HEAD")
    season = ingest.season_label(ingest.CURRENT_SEASON)
    history = ingest.load_history()
    validate.validate_history(history, season)

    ids = match_ids()
    current = history[history["season"] == season].copy()
    current[["match_id", "matchday"]] = [ids[(h, a)] for h, a in zip(current["home"], current["away"])]
    generated_at = pd.Timestamp.now(tz="UTC").strftime(UTC_FORMAT)

    for matchday in ROUNDS:
        played = current[current["matchday"] == matchday]
        if len(played) != 10:
            raise SystemExit(f"STOP: round {matchday} has {len(played)} results, expected 10.")
        path = FORECASTS_DIR / season / f"retro-round-{matchday:02d}.csv"
        retro_round(history, played, generated_at, model_version).to_csv(path, index=False, mode="x")
        print(f"Written {path}")
        path = FORECASTS_DIR / season / f"retro-table-round-{matchday:02d}.csv"
        retro_table(history, current, list(ids), matchday, generated_at, model_version).to_csv(path, index=False, mode="x")
        print(f"Written {path}")


if __name__ == "__main__":
    main()
