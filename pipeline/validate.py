"""Data checks. Every failure raises ValueError; nothing is dropped or fixed."""

from pipeline.ingest import ODDS_COLS


def _check_teams_duplicates_goals(season_df, name):
    """Checks shared by completed seasons and the current season."""
    n_teams = len(set(season_df["home"]) | set(season_df["away"]))
    if n_teams != 20:
        raise ValueError(f"Season {name}: expected 20 teams, found {n_teams}")

    duplicated = season_df[season_df.duplicated(["season", "home", "away"], keep=False)]
    if len(duplicated) > 0:
        pairs = sorted(set(zip(duplicated["home"], duplicated["away"])))
        raise ValueError(f"Season {name}: duplicate fixtures {pairs}")

    # Every row in the results file is a completed match, so it needs a score.
    no_score = season_df[season_df[["home_goals", "away_goals"]].isna().any(axis=1)]
    if len(no_score) > 0:
        pairs = list(zip(no_score["home"], no_score["away"]))
        raise ValueError(f"Season {name}: completed matches missing a score {pairs}")


def validate_completed_season(season_df):
    name = season_df["season"].iloc[0]
    if len(season_df) != 380:
        raise ValueError(f"Season {name}: expected 380 matches, found {len(season_df)}")
    _check_teams_duplicates_goals(season_df, name)

    # With 380 matches, 20 teams and no duplicates this is already implied
    # (there are exactly 380 ordered pairs of 20 teams). It is kept as an
    # explicit safety net in case one of those checks is ever changed.
    home_counts = season_df["home"].value_counts()
    away_counts = season_df["away"].value_counts()
    wrong_home = home_counts[home_counts != 19].to_dict()
    wrong_away = away_counts[away_counts != 19].to_dict()
    if wrong_home or wrong_away:
        raise ValueError(
            f"Season {name}: every team must play 19 home and 19 away. "
            f"Wrong home counts: {wrong_home}. Wrong away counts: {wrong_away}."
        )


def validate_current_season(season_df):
    name = season_df["season"].iloc[0]
    _check_teams_duplicates_goals(season_df, name)


def validate_odds(history):
    """Every odds value that is present must be greater than 1.0."""
    for col in ODDS_COLS:
        bad = history[history[col] <= 1.0]
        if len(bad) > 0:
            first = bad.iloc[0]
            raise ValueError(
                f"{len(bad)} value(s) in {col} are <= 1.0. First: {first['season']} "
                f"{first['home']} v {first['away']} = {first[col]}"
            )


def odds_missing_pct(history):
    """Percent of matches per season with no usable odds."""
    missing = history[ODDS_COLS].isna().any(axis=1)
    return missing.groupby(history["season"]).mean() * 100


def validate_history(history, current_season):
    """Run every check on the output of ingest.load_history()."""
    for name, season_df in history.groupby("season"):
        if name == current_season:
            validate_current_season(season_df)
        else:
            validate_completed_season(season_df)
    validate_odds(history)
