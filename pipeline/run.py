"""Entry point. `python -m pipeline.run --check` loads, validates and reports."""

import argparse
import subprocess

import numpy as np
import pandas as pd

from pipeline import baselines, ingest, model, scoring, validate

WALK_FORWARD_SEASON = "2025-26"

# The model may beat the bookmaker's closing odds by luck, but not by much:
# those odds contain information the model never sees. A margin above this is
# treated as a sign that future data leaked into training.
LEAKAGE_ALARM_MARGIN = 0.005

FORECASTS_DIR = ingest.REPO / "forecasts"
MATCHES_PER_ROUND = 10
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

PROB_COLS = ["p_home", "p_draw", "p_away"]
BOOK_COLS = ["book_home", "book_draw", "book_away"]
# A kickoff moved by up to a day (Saturday to Sunday for television) is still
# the match that was forecast. Anything further is a postponement.
RESCHEDULE_TOLERANCE = pd.Timedelta(days=1)


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

    # Ranked on attack minus defense. Only current-season teams are listed:
    # the fit also holds relegated teams that still have matches in the window.
    print(f"\n== Model: team strength, {current} teams only ==")
    fitted = model.fit(ingest.get_training_data(history, now))
    current_teams = sorted(set(current_df["home"]) | set(current_df["away"]))
    strength = pd.Series({t: fitted.attack[t] - fitted.defense[t] for t in current_teams})
    strength = strength.sort_values(ascending=False).round(3)
    print(f"Home advantage: {fitted.home_advantage:.3f} (x{np.exp(fitted.home_advantage):.2f} goals)")
    print(f"Strongest: {strength.head(3).to_dict()}")
    print(f"Weakest:   {strength.tail(3).to_dict()}")


def backtest():
    """Holdout sanity check: walk forward through 2025-26 one match date at a time.

    2025-26 took no part in any modeling choice, so this is run once, at the
    committed PRIOR_STRENGTH, to check the model behaves. It must never be
    used to compare settings.
    """
    season = WALK_FORWARD_SEASON
    history = ingest.load_history()
    validate.validate_history(history, ingest.season_label(ingest.CURRENT_SEASON))
    season_df = history[history["season"] == season]
    promoted = model._promoted_teams(history, season)

    scored = []
    for _, day in season_df.groupby(season_df["kickoff_utc"].dt.date):
        # Everything used for this date kicked off strictly before its first
        # match, so no match that day can inform another one.
        train = ingest.get_training_data(history, day["kickoff_utc"].min())
        fitted = model.fit(train)
        naive = baselines.naive_probs(train)
        outcomes = scoring.match_outcomes(day)

        model_probs = []
        for _, match in day.iterrows():
            p = model.predict(fitted, match["home"], match["away"])
            model_probs.append([p["p_home"], p["p_draw"], p["p_away"]])
        book_probs = [baselines.bookmaker_probs(match) for _, match in day.iterrows()]

        scored.append(
            pd.DataFrame(
                {
                    "model": scoring.rps_many(model_probs, outcomes),
                    "naive": scoring.rps_many(np.tile(naive, (len(day), 1)), outcomes),
                    "bookmaker": scoring.rps_many(book_probs, outcomes),
                    "promoted": (day["home"].isin(promoted) | day["away"].isin(promoted)).to_numpy(),
                }
            )
        )
    scored = pd.concat(scored, ignore_index=True)

    print(f"\n== Holdout backtest, {season}, PRIOR_STRENGTH = {model.PRIOR_STRENGTH} ==")
    print(f"Refits (match dates): {season_df['kickoff_utc'].dt.date.nunique()}")
    print(f"Promoted teams: {sorted(promoted)}")
    print(f"\nMean RPS on the same {len(scored)} matches (lower is better)")
    for name in ["model", "naive", "bookmaker"]:
        print(f"  {name:<10} {scored[name].mean():.4f}   n={len(scored)}")
    with_promoted = scored[scored["promoted"]]
    others = scored[~scored["promoted"]]
    print("\nModel RPS by match type")
    print(f"  involving a promoted team  {with_promoted['model'].mean():.4f}   n={len(with_promoted)}")
    print(f"  all other matches          {others['model'].mean():.4f}   n={len(others)}")

    model_rps = scored["model"].mean()
    if scored["bookmaker"].mean() - model_rps > LEAKAGE_ALARM_MARGIN:
        raise SystemExit(
            f"\nLEAKAGE ALARM: the model beats the bookmaker by more than "
            f"{LEAKAGE_ALARM_MARGIN} RPS. Suspect leakage. Investigate before forecasting."
        )
    if model_rps > scored["naive"].mean():
        raise SystemExit("\nSTOP: the model is worse than the naive baseline.")
    print("\nSanity check passed: no leakage alarm, and the model beats the naive baseline.")


def git(*args):
    """Run a git command in the repo and return its output."""
    result = subprocess.run(
        ["git", *args], cwd=ingest.REPO, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def locked_kickoffs(season):
    """(home, away) -> kickoff times of the forecasts already locked for that pair."""
    slots = {}
    for path in sorted((FORECASTS_DIR / season).glob("round-*.csv")):
        for row in pd.read_csv(path).itertuples():
            slots.setdefault((row.home, row.away), []).append(pd.Timestamp(row.kickoff_utc))
    return slots


def lock_units(fixtures, now, slots):
    """Split the upcoming fixtures into the groups that are locked together.

    A group is the fixtures of one matchday that fall in the same matchweek
    (see walk_forward_blocks). A match rescheduled out of its round lands in
    another week, so it forms a group of its own and keeps its original
    matchday. A postponed match with no date is in no group. Matches that
    have kicked off are in no group either, so what is left of a round that
    was never locked is still a group. Groups are returned earliest first
    kickoff first.

    slots: locked_kickoffs(). A fixture is skipped if a forecast is already
    locked for it within RESCHEDULE_TOLERANCE of its current kickoff, the same
    rule score_forecasts uses. A forecast locked for a date the match has
    since moved away from does not count, so that match is locked again.
    Pass {} to ignore locks.
    """
    covered = [
        any(abs(f.kickoff_utc - k) <= RESCHEDULE_TOLERANCE for k in slots.get((f.home, f.away), []))
        for f in fixtures.itertuples()
    ]
    upcoming = fixtures[(fixtures["kickoff_utc"] > now) & ~np.array(covered, dtype=bool)]
    units = [
        block
        for _, matchday_df in upcoming.groupby("matchday")
        for block in walk_forward_blocks(matchday_df)
    ]
    return sorted(units, key=lambda unit: unit["kickoff_utc"].min())


def is_whole_round(unit):
    """True if the group is the round itself, not matches rescheduled out of it."""
    return len(unit) > MATCHES_PER_ROUND / 2


def round_started(fixtures, matchday, now):
    """True unless all ten fixtures of the round are still to be played.

    Postponed fixtures count: they are still listed. A match that has kicked
    off is not (the API drops it, the manual file shows a past kickoff).
    """
    listed = fixtures[fixtures["matchday"] == matchday]
    return len(listed) != MATCHES_PER_ROUND or bool((listed["kickoff_utc"] <= now).any())


def lock_reason(unit, fixtures, now, round_locked):
    """Why a lock is partial, or None for a complete round locked before its first kickoff.

    round_locked: whether round-NN.csv exists for the unit's matchday.
    "missed-lock": the round's first kickoff passed with no round-NN.csv, so
    these are the matches of it still to be played.
    "rescheduled": the fixture was moved out of its round, before or after
    the round was locked.
    """
    started = round_started(fixtures, int(unit["matchday"].iloc[0]), now)
    if is_whole_round(unit) and not round_locked and not started:
        return None
    return "missed-lock" if started and not round_locked else "rescheduled"


def forecast():
    """Forecast the next round and write it to forecasts/<season>/round-NN.csv.

    The file is the locked record, so this refuses to run when the result
    could not be trusted or reproduced: uncommitted code, or a forecast file
    that already exists.

    round-NN.csv is only ever a complete round locked before its first
    kickoff (less any match postponed out of it). Every other lock goes to
    round-NN-partial-<date>.csv, under the original matchday and with a
    lock_reason column (see lock_reason). Each match in it is still locked
    before its own kickoff.
    """
    # The file records the commit that produced it. That is only true if the
    # code on disk is exactly that commit.
    if git("status", "--porcelain"):
        raise SystemExit("REFUSING TO FORECAST: the working tree has uncommitted changes.")
    model_version = git("rev-parse", "--short", "HEAD")

    history = ingest.load_history()
    season = ingest.season_label(ingest.CURRENT_SEASON)
    validate.validate_history(history, season)
    fixtures = ingest.load_fixtures()
    fixtures_source = fixtures.attrs["source"]

    # Forecast the next group of fixtures to kick off with no locked forecast.
    now = pd.Timestamp.now(tz="UTC")
    units = lock_units(fixtures, now, locked_kickoffs(season))
    if not units:
        raise SystemExit("REFUSING TO FORECAST: no upcoming fixtures without a locked forecast.")
    round_df = units[0]
    matchday = int(round_df["matchday"].iloc[0])
    first_kickoff = round_df["kickoff_utc"].min()
    left_out = fixtures[fixtures["matchday"] == matchday].drop(round_df.index)

    path = FORECASTS_DIR / season / f"round-{matchday:02d}.csv"
    reason = lock_reason(round_df, fixtures, now, path.exists())
    if reason:
        path = path.with_name(f"round-{matchday:02d}-partial-{first_kickoff:%Y-%m-%d}.csv")
    if path.exists():
        raise FileExistsError(f"{path} already exists. Forecasts are never overwritten.")

    # One fit for the whole round, on matches before the round's FIRST
    # kickoff, so every forecast is locked on the same information.
    train = ingest.get_training_data(history, first_kickoff)
    fitted = model.fit(train)

    rows = []
    for _, fixture in round_df.iterrows():
        p = model.predict(fitted, fixture["home"], fixture["away"])
        rows.append(
            {
                "match_id": fixture["match_id"],
                "matchday": fixture["matchday"],
                "kickoff_utc": fixture["kickoff_utc"].strftime(UTC_FORMAT),
                "home": fixture["home"],
                "away": fixture["away"],
                **p,  # p_home, p_draw, p_away, exp_home_goals, exp_away_goals
                "model_version": model_version,
                "prior_strength": model.PRIOR_STRENGTH,
                "generated_at_utc": now.strftime(UTC_FORMAT),
                "data_through_utc": train["kickoff_utc"].max().strftime(UTC_FORMAT),
                "fixtures_source": fixtures_source,
            }
        )
    forecasts = pd.DataFrame(rows)
    if reason:
        forecasts["lock_reason"] = reason

    # Validate before anything is written.
    totals = forecasts[["p_home", "p_draw", "p_away"]].sum(axis=1)
    if ((totals - 1.0).abs() > 1e-9).any():
        raise ValueError("Forecast probabilities do not sum to 1")
    canonical = set(pd.read_csv(ingest.TEAMS_CSV)["canonical"])
    unknown = sorted((set(forecasts["home"]) | set(forecasts["away"])) - canonical)
    if unknown:
        raise ValueError(f"Non-canonical team names: {unknown}")

    path.parent.mkdir(parents=True, exist_ok=True)
    forecasts.to_csv(path, index=False, mode="x")  # "x": fail if the file exists

    print(f"\n== Forecasts: {season} round {matchday}{f' (partial: {reason})' if reason else ''} ==")
    print(f"Model version {model_version} | PRIOR_STRENGTH {model.PRIOR_STRENGTH} | fixtures from {fixtures_source}")
    print(f"Generated {now.strftime(UTC_FORMAT)} | data through {train['kickoff_utc'].max().strftime(UTC_FORMAT)}")
    print(f"First kickoff {first_kickoff.strftime(UTC_FORMAT)}\n")
    print(f"{'Kickoff (New York)':<20}{'Match':<36}{'Home':>6}{'Draw':>6}{'Away':>6}   Exp. goals")
    for fixture, row in zip(round_df.itertuples(), forecasts.itertuples()):
        new_york = fixture.kickoff_utc.tz_convert("America/New_York")
        print(
            f"{new_york:%a %d %b %H:%M}    {row.home + ' v ' + row.away:<36}"
            f"{row.p_home:>6.1%}{row.p_draw:>6.1%}{row.p_away:>6.1%}"
            f"   {row.exp_home_goals:.2f} - {row.exp_away_goals:.2f}"
        )
    for f in left_out.itertuples():
        when = "postponed, no date" if pd.isna(f.kickoff_utc) else f.kickoff_utc.strftime(UTC_FORMAT)
        print(f"Not in this lock: {f.home} v {f.away} ({when})")
    print(f"\nWritten to {path}")


def score_forecasts(forecasts, history):
    """Join locked forecasts to results and score them. No files, no network.

    `forecasts` holds the rows of the round files plus a `season` column, with
    kickoff_utc parsed. Returns one row per forecast: the result, bookmaker
    and RPS columns are blank until the match is played.

    The two sources share no match id, so the join is on season, home and
    away: each pair meets once per season at each ground. A pair can have two
    forecasts (one locked before a postponement, one after the match was
    rescheduled). Only the one made for the date actually played is scored.

    Raises ValueError if a forecast to be scored was not locked before its
    match kicked off.
    """
    result_cols = ["home_goals", "away_goals", *ingest.ODDS_COLS, "odds_source"]
    results = history[["season", "home", "away", "kickoff_utc", *result_cols]]
    merged = forecasts.merge(
        results.rename(columns={"kickoff_utc": "played_utc"}),
        on=["season", "home", "away"],
        how="left",
        validate="m:1",
    )
    # A match played on another date was postponed after the forecast was
    # locked. That forecast was made for a different day, so it is not scored.
    played = (merged["played_utc"] - merged["kickoff_utc"]).abs() <= RESCHEDULE_TOLERANCE
    merged.loc[~played, result_cols] = pd.NA

    # A forecast only counts if it was locked before the match kicked off.
    locked_utc = pd.to_datetime(merged["generated_at_utc"], utc=True)
    late = merged[played & (locked_utc >= merged["played_utc"])]
    if len(late) > 0:
        raise ValueError(
            "Forecast(s) locked at or after kickoff:\n"
            + late[["season", "home", "away", "generated_at_utc", "played_utc"]].to_string(index=False)
        )

    merged["outcome"] = None
    merged.loc[played, "outcome"] = scoring.match_outcomes(merged[played])
    merged[[*BOOK_COLS, "rps_model", "rps_naive", "rps_bookmaker"]] = np.nan
    merged.loc[played, "rps_model"] = scoring.rps_many(
        merged.loc[played, PROB_COLS], merged.loc[played, "outcome"]
    )

    # The naive baseline gets the same information as the model: matches
    # before the first kickoff of the lock (one generated_at_utc per lock).
    for _, round_df in merged.groupby(["season", "matchday", "generated_at_utc"]):
        done = round_df[played[round_df.index]]
        train = ingest.get_training_data(history, round_df["kickoff_utc"].min())
        naive = np.tile(baselines.naive_probs(train), (len(done), 1))
        merged.loc[done.index, "rps_naive"] = scoring.rps_many(naive, done["outcome"])

    has_odds = played & merged[ingest.ODDS_COLS].notna().all(axis=1)
    book = np.array(
        [baselines.bookmaker_probs(row) for _, row in merged[has_odds].iterrows()]
    ).reshape(-1, 3)
    merged.loc[has_odds, BOOK_COLS] = book
    merged.loc[has_odds, "rps_bookmaker"] = scoring.rps_many(book, merged.loc[has_odds, "outcome"])

    return merged.drop(columns=["played_utc", *ingest.ODDS_COLS])


def score():
    """Score every locked forecast against results and write forecasts/scores.csv.

    Unlike the round files, scores.csv is derived and is rewritten on every
    run. The round files are only read.
    """
    history = ingest.load_history()
    validate.validate_history(history, ingest.season_label(ingest.CURRENT_SEASON))

    paths = sorted(FORECASTS_DIR.glob("*/round-*.csv"))
    if not paths:
        raise SystemExit("NOTHING TO SCORE: no forecast files.")
    forecasts = pd.concat(
        [pd.read_csv(p).assign(season=p.parent.name) for p in paths], ignore_index=True
    )
    forecasts["kickoff_utc"] = pd.to_datetime(forecasts["kickoff_utc"], utc=True)
    scored = score_forecasts(forecasts, history)

    path = FORECASTS_DIR / "scores.csv"
    scored.to_csv(path, index=False, date_format=UTC_FORMAT)

    played = scored[scored["rps_model"].notna()]
    print(f"\n== Locked forecasts: {len(scored)} | scored: {len(played)} | pending: {len(scored) - len(played)} ==")
    overdue = scored["rps_model"].isna() & (
        scored["kickoff_utc"] < pd.Timestamp.now(tz="UTC") - RESCHEDULE_TOLERANCE
    )
    if overdue.any():
        print(f"{overdue.sum()} forecast(s) past kickoff with no result yet (results file lag, or postponed).")
    # All three are compared on the same matches: those with bookmaker odds.
    same = played[played["rps_bookmaker"].notna()]
    if len(same):
        print(f"\nMean RPS on the same {len(same)} matches (lower is better)")
        for name in ["model", "naive", "bookmaker"]:
            print(f"  {name:<10} {same[f'rps_{name}'].mean():.4f}")
    print(f"\nWritten to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="simeon pipeline")
    parser.add_argument("--check", action="store_true", help="load, validate and report")
    parser.add_argument("--backtest", action="store_true", help="holdout sanity check on 2025-26")
    parser.add_argument("--forecast", action="store_true", help="forecast and lock the next round")
    parser.add_argument("--score", action="store_true", help="score locked forecasts against results")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.backtest:
        backtest()
    elif args.forecast:
        forecast()
    elif args.score:
        score()
    else:
        parser.print_help()
