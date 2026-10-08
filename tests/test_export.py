"""The website export: pure builders only, no files and no network."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import poisson

from pipeline import export

CODES = {"Arsenal": "ARS", "Leeds": "LEE", "Hull": "HUL", "Everton": "EVE"}


def scored_row(**overrides):
    """One row shaped like run.score_forecasts output, unplayed by default."""
    row = {
        "match_id": 1,
        "matchday": 6,
        "kickoff_utc": pd.Timestamp("2026-10-10T11:30:00Z"),
        "home": "Arsenal",
        "away": "Leeds",
        "p_home": 0.6,
        "p_draw": 0.25,
        "p_away": 0.15,
        "exp_home_goals": 1.83,
        "exp_away_goals": 0.75,
        "generated_at_utc": "2026-10-07T22:35:46Z",
        "lock_reason": None,
        "home_goals": pd.NA,
        "away_goals": pd.NA,
        "book_home": np.nan,
        "book_draw": np.nan,
        "book_away": np.nan,
        "rps_model": np.nan,
        "rps_naive": np.nan,
        "rps_bookmaker": np.nan,
    }
    return {**row, **overrides}


PLAYED = dict(
    home_goals=2, away_goals=0, book_home=0.65, book_draw=0.22, book_away=0.13,
    rps_model=0.09, rps_naive=0.2, rps_bookmaker=0.07,
)


def test_likely_score_is_the_peak_of_the_scoreline_grid():
    score = export.likely_score(1.83, 0.75)
    assert (score["home"], score["away"]) == (1, 0)
    # The grid cuts off at 10 goals, so the product of the two Poisson
    # probabilities is a hair below the renormalized value.
    assert score["probability"] == pytest.approx(poisson.pmf(1, 1.83) * poisson.pmf(0, 0.75), rel=1e-4)
    assert export.likely_score(0.4, 2.6)["away"] == 2


def test_unplayed_match_has_no_result_market_or_scores():
    [match] = export.build_matches(pd.DataFrame([scored_row()]), CODES, {})
    assert match["id"] == "1" and match["home"] == "ARS" and match["away"] == "LEE"
    assert match["kickoff"] == "2026-10-10T11:30:00Z"
    assert match["prediction"]["lockedAt"] == "2026-10-07T22:35:46Z"
    assert match["prediction"]["lockReason"] is None and match["prediction"]["analysis"] is None
    assert match["result"] is None and match["market"] is None and match["scores"] is None


def test_played_match_carries_result_market_and_scores():
    notes = {("Arsenal", "Leeds"): "A note."}
    [match] = export.build_matches(pd.DataFrame([scored_row(**PLAYED)]), CODES, notes)
    assert match["result"] == {"home": 2, "away": 0}
    assert match["market"] == {"pHome": 0.65, "pDraw": 0.22, "pAway": 0.13}
    assert match["scores"] == {"rpsModel": 0.09, "rpsNaive": 0.2, "rpsBookmaker": 0.07}
    assert match["prediction"]["analysis"] == "A note."


def test_a_fixture_locked_twice_keeps_the_later_lock():
    first = scored_row()
    again = scored_row(
        kickoff_utc=pd.Timestamp("2026-11-03T19:45:00Z"), generated_at_utc="2026-11-02T10:00:00Z",
        lock_reason="rescheduled", p_home=0.5, p_draw=0.3, p_away=0.2,
    )
    [match] = export.build_matches(pd.DataFrame([first, again]), CODES, {})
    assert match["prediction"]["lockReason"] == "rescheduled"
    assert match["prediction"]["homeWin"] == 0.5


def test_round_status():
    unplayed = export.build_matches(pd.DataFrame([scored_row()]), CODES, {})
    played = export.build_matches(pd.DataFrame([scored_row(**PLAYED)]), CODES, {})
    assert export.round_status(unplayed) == "upcoming"
    assert export.round_status(played) == "complete"
    assert export.round_status(unplayed + played) == "in_progress"


def test_standings_points_and_order():
    results = pd.DataFrame(
        [("Arsenal", "Leeds", 2, 0), ("Hull", "Everton", 1, 1), ("Leeds", "Hull", 3, 1)],
        columns=["home", "away", "home_goals", "away_goals"],
    )
    table = export.standings(results, list(CODES), CODES)
    assert [row["teamCode"] for row in table] == ["ARS", "LEE", "EVE", "HUL"]  # LEE and ARS on 3: goal difference
    assert [row["position"] for row in table] == [1, 2, 3, 4]
    leeds = table[1]
    assert (leeds["played"], leeds["won"], leeds["drawn"], leeds["lost"]) == (2, 1, 0, 1)
    assert (leeds["goalsFor"], leeds["goalsAgainst"], leeds["points"]) == (3, 3, 3)
    assert all(row["points"] == 3 * row["won"] + row["drawn"] for row in table)


def test_parse_analysis_reads_notes_and_rejects_unknown_fixtures():
    fixtures = {("Arsenal", "Leeds"), ("Hull", "Everton")}
    text = "# Round 6\n\nIgnored.\n\n## Arsenal v Leeds\nFirst line.\nSecond line.\n\n## Hull v Everton\n"
    assert export.parse_analysis(text, fixtures) == {("Arsenal", "Leeds"): "First line. Second line."}
    with pytest.raises(ValueError, match="names no fixture"):
        export.parse_analysis("## Arsenal v Leads\nTypo.\n", fixtures)


def test_check_refuses_a_forecast_locked_at_kickoff():
    late = scored_row(generated_at_utc="2026-10-10T11:30:00Z")
    matches = export.build_matches(pd.DataFrame([late]), CODES, {})
    with pytest.raises(ValueError, match="at or after kickoff"):
        export.check({6: matches}, {})
