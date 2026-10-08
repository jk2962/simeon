import numpy as np
import pandas as pd
import pytest

from pipeline.run import score_forecasts


def utc(text):
    return pd.Timestamp(text, tz="UTC")


def make_history(rows):
    """rows: (kickoff, home, away, home_goals, away_goals, odds or None)."""
    return pd.DataFrame(
        {
            "season": "2026-27",
            "kickoff_utc": [utc(r[0]) for r in rows],
            "home": [r[1] for r in rows],
            "away": [r[2] for r in rows],
            "home_goals": pd.array([r[3] for r in rows], dtype="Int64"),
            "away_goals": pd.array([r[4] for r in rows], dtype="Int64"),
            "odds_home": [r[5][0] if r[5] else np.nan for r in rows],
            "odds_draw": [r[5][1] if r[5] else np.nan for r in rows],
            "odds_away": [r[5][2] if r[5] else np.nan for r in rows],
            "odds_source": ["pinnacle_close" if r[5] else "none" for r in rows],
        }
    )


def make_forecasts(rows):
    """rows: (kickoff, home, away). Every forecast is 50/30/20."""
    return pd.DataFrame(
        {
            "season": "2026-27",
            "matchday": 6,
            "kickoff_utc": [utc(r[0]) for r in rows],
            "home": [r[1] for r in rows],
            "away": [r[2] for r in rows],
            "p_home": 0.5,
            "p_draw": 0.3,
            "p_away": 0.2,
        }
    )


HISTORY = make_history(
    [
        # Before the round: one home win and one draw, so naive = (0.5, 0.5, 0).
        ("2026-09-01 14:00", "A", "B", 1, 0, None),
        ("2026-09-08 14:00", "B", "A", 1, 1, None),
        # The round.
        ("2026-10-10 14:00", "A", "C", 2, 0, (2.0, 4.0, 4.0)),
        ("2026-10-11 12:00", "C", "B", 0, 0, None),  # moved by 16 hours, no odds
        ("2026-12-01 20:00", "D", "A", 0, 3, (3.0, 3.0, 3.0)),  # postponed
    ]
)
FORECASTS = make_forecasts(
    [
        ("2026-10-10 14:00", "A", "C"),
        ("2026-10-10 20:00", "C", "B"),
        ("2026-10-11 14:00", "B", "D"),  # not played yet
        ("2026-10-11 16:00", "D", "A"),
    ]
)


def test_played_match_is_scored_against_both_baselines():
    row = score_forecasts(FORECASTS, HISTORY).iloc[0]
    assert row["outcome"] == "H"
    assert row["rps_model"] == pytest.approx(0.145)
    assert row["rps_naive"] == pytest.approx(0.125)
    assert row[["book_home", "book_draw", "book_away"]].tolist() == pytest.approx([0.5, 0.25, 0.25])
    assert row["rps_bookmaker"] == pytest.approx(0.15625)


def test_small_kickoff_move_is_scored_and_missing_odds_leave_bookmaker_blank():
    row = score_forecasts(FORECASTS, HISTORY).iloc[1]
    assert row["outcome"] == "D"
    assert row["rps_model"] == pytest.approx((0.5**2 + 0.2**2) / 2)
    assert np.isnan(row["rps_bookmaker"])


def test_unplayed_and_postponed_matches_are_not_scored():
    scored = score_forecasts(FORECASTS, HISTORY)
    assert len(scored) == len(FORECASTS)
    for row in (scored.iloc[2], scored.iloc[3]):
        assert pd.isna(row["home_goals"]) and pd.isna(row["outcome"])
        assert np.isnan(row["rps_model"]) and np.isnan(row["rps_naive"]) and np.isnan(row["rps_bookmaker"])
