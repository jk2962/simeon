"""Retrospective forecasts for rounds played before forecasts were locked.

`python -m pipeline.retro` writes forecasts/<season>/retro-round-NN.csv for
rounds 1-5 of 2026-27. Each round is fitted, as in run.forecast, on matches
that kicked off before the round's first kickoff, so round N sees only
earlier rounds and earlier seasons.

These are NOT locked forecasts. They were made after the results were known,
by code written after those rounds were played (the promoted-team rule fix
and the PRIOR_STRENGTH decision of 2026-10-07), so they are not evidence
under the model change policy. The file name keeps them out of every
`round-*.csv` glob: score(), the lock logic and scores.csv never see them.
The export shows them on the website labelled as retrospective.
"""

import os

import pandas as pd
import requests

from pipeline import ingest, model, validate
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


if __name__ == "__main__":
    main()
