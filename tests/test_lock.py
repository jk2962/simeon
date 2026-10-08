"""Which fixtures are locked together, with postponed and rescheduled matches."""

import pandas as pd
import pytest

from pipeline.run import (
    SEASON_MATCHES,
    is_whole_round,
    lock_due,
    lock_reason,
    lock_units,
    results_in,
    round_started,
)

NOW = pd.Timestamp("2026-10-15 12:00", tz="UTC")
ROUND_7 = "2026-10-17T14:00:00Z"
ROUND_8 = "2026-10-24T14:00:00Z"


def make_fixtures(moved=None):
    """Rounds 7 and 8, ten matches each. `moved` replaces the kickoff of H0 v A0 in round 7."""
    rows = [
        (matchday, kickoff, f"H{i}", f"A{i}") if matchday == 7 else (matchday, kickoff, f"A{i}", f"H{i}")
        for matchday, kickoff in [(7, ROUND_7), (8, ROUND_8)]
        for i in range(10)
    ]
    fixtures = pd.DataFrame(rows, columns=["matchday", "kickoff_utc", "home", "away"])
    fixtures["kickoff_utc"] = pd.to_datetime(fixtures["kickoff_utc"], utc=True)
    if moved is not None:
        fixtures.loc[0, "kickoff_utc"] = pd.NaT if moved == "no date" else pd.Timestamp(moved)
    return fixtures


def slots_for(unit):
    """What locked_kickoffs() returns once `unit` has been locked."""
    return {(f.home, f.away): [f.kickoff_utc] for f in unit.itertuples()}


def test_next_lock_is_the_whole_next_round():
    units = lock_units(make_fixtures(), NOW, {})
    assert [len(u) for u in units] == [10, 10]
    assert units[0]["matchday"].unique().tolist() == [7]
    assert lock_reason(units[0], make_fixtures(), NOW, round_locked=False) is None


def test_postponed_match_with_no_date_is_left_out_of_the_round_lock():
    fixtures = make_fixtures(moved="no date")
    units = lock_units(fixtures, NOW, {})
    assert [len(u) for u in units] == [9, 10]
    assert "H0" not in set(units[0]["home"])
    # It is still one of the round's ten unplayed fixtures, so this is the round's lock.
    assert lock_reason(units[0], fixtures, NOW, round_locked=False) is None


def test_rescheduled_match_is_locked_later_under_its_original_round():
    fixtures = make_fixtures(moved="2026-10-21T19:00:00Z")  # midweek, before round 8
    first, second, third = lock_units(fixtures, NOW, {})
    assert len(first) == 9 and len(third) == 10
    assert second[["matchday", "home", "away"]].values.tolist() == [[7, "H0", "A0"]]
    assert not is_whole_round(second)

    # After round 7 is locked and played, the rescheduled match is next.
    later = pd.Timestamp("2026-10-20 12:00", tz="UTC")
    unplayed = fixtures[fixtures["kickoff_utc"] > later]
    unit = lock_units(unplayed, later, slots_for(first))[0]
    assert unit.equals(second)
    assert lock_reason(unit, unplayed, later, round_locked=True) == "rescheduled"


def test_match_postponed_after_its_lock_is_locked_again_for_the_new_date():
    locked = slots_for(make_fixtures().iloc[:10])  # all of round 7, at the original time
    fixtures = make_fixtures(moved="2026-10-21T19:00:00Z")
    units = lock_units(fixtures, NOW, locked)
    assert units[0][["matchday", "home"]].values.tolist() == [[7, "H0"]]
    assert lock_reason(units[0], fixtures, NOW, round_locked=True) == "rescheduled"
    assert units[1]["matchday"].unique().tolist() == [8]


def test_kickoff_moved_within_a_day_keeps_its_lock():
    locked = slots_for(make_fixtures().iloc[:10])
    fixtures = make_fixtures(moved="2026-10-18T13:00:00Z")  # Saturday to Sunday
    assert lock_units(fixtures, NOW, locked)[0]["matchday"].unique().tolist() == [8]


def test_match_brought_forward_before_its_round_is_rescheduled():
    fixtures = make_fixtures()
    fixtures.loc[10, "kickoff_utc"] = pd.Timestamp("2026-10-13T19:00:00Z")  # a round-8 match
    early = pd.Timestamp("2026-10-12 12:00", tz="UTC")
    unit = lock_units(fixtures, early, {})[0]
    assert unit[["matchday", "home"]].values.tolist() == [[8, "A0"]]
    assert lock_reason(unit, fixtures, early, round_locked=False) == "rescheduled"


@pytest.mark.parametrize("played", [1, 6])
def test_missed_round_locks_every_match_still_to_play(played):
    # The API no longer lists a match that has kicked off.
    fixtures = make_fixtures().iloc[played:]
    unit = lock_units(fixtures, NOW, {})[0]
    assert unit["matchday"].unique().tolist() == [7]
    assert len(unit) == 10 - played
    assert (unit["kickoff_utc"] > NOW).all()
    assert lock_reason(unit, fixtures, NOW, round_locked=False) == "missed-lock"


def test_missed_round_in_the_manual_file_leaves_out_matches_that_kicked_off():
    fixtures = make_fixtures()
    fixtures.loc[:2, "kickoff_utc"] = pd.Timestamp("2026-10-15T11:00:00Z")  # an hour ago
    unit = lock_units(fixtures, NOW, {})[0]
    assert len(unit) == 7 and (unit["kickoff_utc"] > NOW).all()
    assert lock_reason(unit, fixtures, NOW, round_locked=False) == "missed-lock"


def test_round_started():
    fixtures = make_fixtures()
    assert not round_started(fixtures, 7, NOW)
    assert round_started(fixtures.iloc[1:], 7, NOW)  # the API no longer lists a played match
    assert round_started(fixtures, 7, pd.Timestamp(ROUND_7))  # the manual file shows a past kickoff


KICKOFF = pd.Timestamp(ROUND_7)


def before(**delta):
    return KICKOFF - pd.Timedelta(**delta)


@pytest.mark.parametrize(
    "now, results_are_in, due",
    [
        (before(hours=30, seconds=1), True, False),  # window not open yet
        (before(hours=30), True, True),
        (before(hours=30), False, False),  # in the window, waiting for results
        (before(hours=6), False, False),  # "under 6h" excludes 6h itself
        (before(hours=6) + pd.Timedelta(seconds=1), False, True),
        (before(hours=1), False, True),
        (before(minutes=59, seconds=59), True, False),  # the scheduled window has closed
        (KICKOFF, True, False),
        (KICKOFF + pd.Timedelta(minutes=1), True, False),  # a run after kickoff
    ],
)
def test_lock_due_boundaries(now, results_are_in, due):
    assert lock_due(KICKOFF, now, results_are_in) is due


def test_lock_due_with_a_47_75h_gap_between_rounds():
    # Monday 20:00 to Wednesday 19:45: the window opens 17.75h after the
    # previous round's last kickoff, when its result may not be in the data.
    last_kickoff = pd.Timestamp("2026-10-19T20:00:00Z")
    kickoff = last_kickoff + pd.Timedelta(hours=47.75)
    opens = kickoff - pd.Timedelta(hours=30)
    assert opens - last_kickoff == pd.Timedelta(hours=17.75)
    assert not lock_due(kickoff, opens, False)
    assert lock_due(kickoff, opens, True)  # locks on the first run that has the result
    assert lock_due(kickoff, kickoff - pd.Timedelta(hours=5, minutes=59), False)


def test_results_in_counts_every_match_that_has_kicked_off():
    fixtures = make_fixtures()  # 20 still to play
    assert results_in(fixtures, SEASON_MATCHES - 20, NOW)
    assert not results_in(fixtures, SEASON_MATCHES - 21, NOW)
    # The manual file still lists a match that has kicked off: its result is waited for.
    assert not results_in(fixtures, SEASON_MATCHES - 20, pd.Timestamp(ROUND_7))


def test_results_in_does_not_wait_for_a_postponed_match():
    fixtures = make_fixtures(moved="no date")
    fixtures.loc[0, "matchday"] = 6  # postponed out of the previous round
    assert results_in(fixtures, SEASON_MATCHES - 20, NOW)
