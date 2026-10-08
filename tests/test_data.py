"""Tests for ingest.py, validate.py and baselines.py on small hand-made data."""

import numpy as np
import pandas as pd
import pytest

from pipeline import baselines, ingest, validate


def raw_row(date, time, home="Arsenal", away="Chelsea", **extra):
    row = {"Date": date, "Time": time, "HomeTeam": home, "AwayTeam": away, "FTHG": 1, "FTAG": 0}
    row.update(extra)
    return row


# ---- ingest: time zones ----

def test_uk_time_converts_to_utc_in_summer_and_winter():
    raw = pd.DataFrame(
        [
            raw_row("15/08/2025", "20:00"),  # BST: UTC+1
            raw_row("17/01/2026", "15:00"),  # GMT: UTC+0
            raw_row("25/10/2025", "15:00"),  # last day of BST
            raw_row("26/10/2025", "14:00"),  # first day of GMT
        ]
    )
    kickoffs = ingest.standardize_season(raw, "2526")["kickoff_utc"]
    expected = ["2025-08-15 19:00", "2026-01-17 15:00", "2025-10-25 14:00", "2025-10-26 14:00"]
    assert list(kickoffs.dt.strftime("%Y-%m-%d %H:%M")) == expected
    assert str(kickoffs.dt.tz) == "UTC"


# ---- ingest: team names ----

def test_team_names_map_to_canonical():
    raw = pd.DataFrame([raw_row("15/08/2025", "20:00", home="Nott'm Forest")])
    assert ingest.standardize_season(raw, "2526")["home"].iloc[0] == "Nottingham Forest"


def test_unmapped_team_raises_and_names_it():
    raw = pd.DataFrame([raw_row("15/08/2025", "20:00", home="Wrexham")])
    with pytest.raises(ValueError, match="Wrexham"):
        ingest.standardize_season(raw, "2526")


# ---- ingest: odds source priority ----

def test_odds_source_priority():
    pinnacle = {"PSCH": 2.0, "PSCD": 3.5, "PSCA": 4.0}
    avg_close = {"AvgCH": 2.1, "AvgCD": 3.4, "AvgCA": 3.9}
    avg_open = {"AvgH": 2.2, "AvgD": 3.3, "AvgA": 3.8}
    raw = pd.DataFrame(
        [
            raw_row("15/08/2025", "20:00", **pinnacle, **avg_close, **avg_open),
            raw_row("16/08/2025", "15:00", **avg_close, **avg_open),
            raw_row("17/08/2025", "15:00", **avg_open),
            raw_row("18/08/2025", "20:00"),
        ]
    )
    out = ingest.standardize_season(raw, "2526")
    assert list(out["odds_source"]) == ["pinnacle_close", "avg_close", "avg_open", "none"]
    assert list(out["odds_home"][:3]) == [2.0, 2.1, 2.2]
    assert np.isnan(out["odds_home"][3])


# ---- ingest: no leakage ----

def test_get_training_data_is_strictly_before():
    matches = pd.DataFrame(
        {"kickoff_utc": pd.to_datetime(["2026-10-03 14:00", "2026-10-10 11:30", "2026-10-10 14:00"], utc=True)}
    )
    train = ingest.get_training_data(matches, pd.Timestamp("2026-10-10 11:30", tz="UTC"))
    # The match kicking off exactly at the cutoff is excluded.
    assert list(train.index) == [0]


def test_get_training_data_rejects_naive_timestamp():
    matches = pd.DataFrame({"kickoff_utc": pd.to_datetime(["2026-10-03 14:00"], utc=True)})
    with pytest.raises(ValueError):
        ingest.get_training_data(matches, pd.Timestamp("2026-10-10 11:30"))


# ---- validate ----

def full_season():
    """A valid 20-team double round robin: 380 matches."""
    teams = [f"T{i:02d}" for i in range(20)]
    rows = [(h, a) for h in teams for a in teams if h != a]
    season = pd.DataFrame(rows, columns=["home", "away"])
    season["season"] = "2025-26"
    season["home_goals"] = pd.array([1] * 380, dtype="Int64")
    season["away_goals"] = pd.array([0] * 380, dtype="Int64")
    season["odds_home"] = 2.0
    season["odds_draw"] = 3.5
    season["odds_away"] = 4.0
    return season


def test_valid_season_passes():
    season = full_season()
    validate.validate_completed_season(season)
    validate.validate_odds(season)


def test_wrong_match_count_raises():
    with pytest.raises(ValueError, match="380"):
        validate.validate_completed_season(full_season().iloc[:-1])


def test_duplicate_fixture_raises():
    season = full_season()
    season.loc[1, ["home", "away"]] = season.loc[0, ["home", "away"]].to_numpy()
    with pytest.raises(ValueError, match="duplicate"):
        validate.validate_completed_season(season)


def test_missing_goals_raises():
    season = full_season()
    season.loc[0, "home_goals"] = pd.NA
    with pytest.raises(ValueError, match="missing a score"):
        validate.validate_completed_season(season)


def test_odds_at_or_below_one_raise():
    season = full_season()
    season.loc[0, "odds_draw"] = 1.0
    with pytest.raises(ValueError, match="odds_draw"):
        validate.validate_odds(season)


def test_odds_missing_pct():
    season = full_season()
    season.loc[:37, "odds_home"] = np.nan  # 38 of 380 = 10%
    assert validate.odds_missing_pct(season)["2025-26"] == pytest.approx(10.0)


# ---- baselines ----

def test_naive_probs_are_training_frequencies():
    train = pd.DataFrame({"home_goals": [2, 1, 0, 3], "away_goals": [0, 1, 2, 1]})
    assert baselines.naive_probs(train) == pytest.approx([0.5, 0.25, 0.25])


def test_bookmaker_probs_remove_the_margin():
    row = {"home": "A", "away": "B", "odds_home": 2.0, "odds_draw": 4.0, "odds_away": 4.0}
    # Fair odds: no margin, so probabilities are exactly 1/odds.
    assert baselines.bookmaker_probs(row) == pytest.approx([0.5, 0.25, 0.25])
    # Same odds shortened by 10%: the margin is removed, same probabilities.
    row = {"home": "A", "away": "B", "odds_home": 1.8, "odds_draw": 3.6, "odds_away": 3.6}
    assert baselines.bookmaker_probs(row) == pytest.approx([0.5, 0.25, 0.25])


def test_bookmaker_probs_missing_odds_raise():
    row = {"home": "A", "away": "B", "odds_home": 2.0, "odds_draw": np.nan, "odds_away": 4.0}
    with pytest.raises(ValueError):
        baselines.bookmaker_probs(row)


# ---- ingest: the UK clock change on 2026-10-25 ----

def test_kickoffs_around_the_2026_clock_change_are_utc():
    raw = pd.DataFrame(
        [
            raw_row("23/10/2026", "20:00"),  # Friday, BST: UTC+1
            raw_row("24/10/2026", "15:00"),  # Saturday, last day of BST
            raw_row("25/10/2026", "14:00"),  # Sunday, clocks went back at 02:00: GMT
            raw_row("25/10/2026", "16:30"),
        ]
    )
    kickoffs = ingest.standardize_season(raw, "2627")["kickoff_utc"]
    # The same times the fixtures API gives for round 8, which is already UTC.
    api = ["2026-10-23T19:00:00Z", "2026-10-24T14:00:00Z", "2026-10-25T14:00:00Z", "2026-10-25T16:30:00Z"]
    assert list(kickoffs) == list(pd.to_datetime(api, utc=True))
    # Saturday 15:00 to Sunday 14:00 is 23 hours on the UK clock, 24 in UTC.
    assert kickoffs[2] - kickoffs[1] == pd.Timedelta(hours=24)
    assert str(kickoffs.dt.tz) == "UTC"


def test_time_in_the_repeated_hour_is_refused_not_guessed():
    raw = pd.DataFrame([raw_row("25/10/2026", "01:30")])  # happens twice that night
    with pytest.raises(Exception, match="(?i)ambiguous"):
        ingest.standardize_season(raw, "2627")


# ---- ingest: postponed fixtures ----

def api_match(match_id, status, utc_date, home, away, matchday=7):
    return {
        "id": match_id,
        "status": status,
        "matchday": matchday,
        "utcDate": utc_date,
        "homeTeam": {"name": home},
        "awayTeam": {"name": away},
    }


def test_postponed_fixture_is_kept_with_no_kickoff(monkeypatch):
    names = pd.read_csv(ingest.TEAMS_CSV)["fd_org_name"].tolist()
    matches = [
        api_match(1, "FINISHED", "2026-10-10T14:00:00Z", names[0], names[1], matchday=6),
        api_match(2, "POSTPONED", "2026-10-17T14:00:00Z", names[2], names[3]),
        api_match(3, "TIMED", "2026-10-17T14:00:00Z", names[4], names[5]),
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"matches": matches}

    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "test")
    monkeypatch.setattr(ingest.requests, "get", lambda *args, **kwargs: Response())
    fixtures = ingest.load_fixtures()

    # Still counted as a match to play, so every team keeps its 38.
    assert fixtures["match_id"].tolist() == [3, 2]
    assert pd.isna(fixtures["kickoff_utc"].iloc[1])
    assert str(fixtures["kickoff_utc"].dt.tz) == "UTC"
    assert pd.concat([fixtures["home"], fixtures["away"]]).value_counts().eq(1).all()


def test_missing_token_stops_in_ci_instead_of_using_the_manual_file(monkeypatch):
    monkeypatch.setattr(ingest, "load_env_file", lambda: None)
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit, match="FOOTBALL_DATA_API_KEY is not set"):
        ingest.load_fixtures()
