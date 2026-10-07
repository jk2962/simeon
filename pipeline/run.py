"""Entry point. `python -m pipeline.run --check` loads, validates and reports."""

import argparse

import numpy as np
import pandas as pd

from pipeline import baselines, ingest, scoring, validate

WALK_FORWARD_SEASON = "2025-26"


def walk_forward_blocks(season_df):
    """Group a season's matches into matchweeks for walk-forward refitting.

    The results CSV has no matchweek column, so a matchweek here is a
    Tuesday-to-Monday week: that keeps a Friday-to-Monday round together.
    A midweek round and the following weekend land in the same block, which
    only means one refit covers both. Leakage does not depend on the grouping,
    because training data is cut at the FIRST kickoff of each block.
    """
    week = (season_df["kickoff_utc"] - pd.Timedelta(days=1)).dt.strftime("%G-W%V")
    return [block for _, block in season_df.groupby(week, sort=True)]


def walk_forward_naive_rps(history, season):
    """Mean RPS of the naive baseline, refit before each matchweek."""
    season_df = history[history["season"] == season]
    scores = []
    for block in walk_forward_blocks(season_df):
        train = ingest.get_training_data(history, block["kickoff_utc"].min())
        probs = np.tile(baselines.naive_probs(train), (len(block), 1))
        scores.append(scoring.rps_many(probs, scoring.match_outcomes(block)))
    return np.concatenate(scores).mean()


def bookmaker_rps(history, season):
    """Mean RPS of the bookmaker baseline. No fitting, so no walk-forward."""
    season_df = history[history["season"] == season]
    probs = np.array([baselines.bookmaker_probs(row) for _, row in season_df.iterrows()])
    return scoring.rps_many(probs, scoring.match_outcomes(season_df)).mean()


def check():
    history = ingest.load_history()
    current = ingest.season_label(ingest.CURRENT_SEASON)
    validate.validate_history(history, current)
    fixtures = ingest.load_fixtures()

    print("\n== Seasons loaded (matches) ==")
    print(history.groupby("season").size().to_string(header=False))

    current_df = history[history["season"] == current]
    print(f"\n== Current season {current} ==")
    print(f"Matches played so far: {len(current_df)}")
    print(f"Latest result in the data: {current_df['kickoff_utc'].max():%Y-%m-%d %H:%M} UTC")

    print("\n== Next 10 fixtures ==")
    now = pd.Timestamp.now(tz="UTC")
    upcoming = fixtures[fixtures["kickoff_utc"] > now].head(10)
    if len(upcoming) == 0:
        print("NO UPCOMING FIXTURES AVAILABLE (see the warning above).")
    for _, f in upcoming.iterrows():
        new_york = f["kickoff_utc"].tz_convert("America/New_York")
        print(
            f"MD{f['matchday']}  {f['kickoff_utc']:%a %Y-%m-%d %H:%M} UTC  "
            f"{new_york:%a %H:%M} New York  {f['home']} v {f['away']}"
        )

    print("\n== Odds coverage ==")
    coverage = pd.crosstab(history["season"], history["odds_source"])
    coverage["pct_missing"] = validate.odds_missing_pct(history).round(1)
    print(coverage.to_string())

    print(f"\n== RPS on {WALK_FORWARD_SEASON} (lower is better) ==")
    print(f"Naive baseline (walk-forward): {walk_forward_naive_rps(history, WALK_FORWARD_SEASON):.4f}")
    print(f"Bookmaker baseline:            {bookmaker_rps(history, WALK_FORWARD_SEASON):.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="simeon pipeline")
    parser.add_argument("--check", action="store_true", help="load, validate and report")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        parser.print_help()
