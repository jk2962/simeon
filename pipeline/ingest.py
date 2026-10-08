"""Load Premier League results, odds and fixtures into standardized DataFrames."""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "data" / "raw"
TEAMS_CSV = REPO / "data" / "teams.csv"
MANUAL_FIXTURES_CSV = REPO / "data" / "manual_fixtures.csv"

# football-data.co.uk season codes: "2526" is the 2025-26 season.
COMPLETED_SEASONS = ["2021", "2122", "2223", "2324", "2425", "2526"]
CURRENT_SEASON = "2627"

RESULTS_URL = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
FIXTURES_URL = "https://api.football-data.org/v4/competitions/PL/matches"

# Odds source priority, best first. Each row uses the first source that has
# all three prices (home, draw, away).
#   1. Pinnacle closing: the sharpest book with the lowest margin, and closing
#      prices include all pre-match information (team news, late money).
#   2. Market-average closing: same timing, but averages in soft books, so it
#      carries a higher margin and a little more favourite-longshot bias.
#   3. Market-average pre-closing ("opening"): collected days before kickoff,
#      so it misses late information. Last resort only.
# NOTE: closing odds are only known at kickoff. They are a benchmark to score
# against, never an input to a forecast that must be locked before kickoff.
ODDS_SOURCES = [
    ("pinnacle_close", ["PSCH", "PSCD", "PSCA"]),
    ("avg_close", ["AvgCH", "AvgCD", "AvgCA"]),
    ("avg_open", ["AvgH", "AvgD", "AvgA"]),
]
ODDS_COLS = ["odds_home", "odds_draw", "odds_away"]
REQUIRED_RAW_COLS = ["Date", "Time", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]


def season_label(code):
    """'2526' -> '2025-26'."""
    return f"20{code[:2]}-{code[2:]}"


def canonical_names(names, source_col):
    """Map source team names to canonical names using data/teams.csv.

    source_col is the teams.csv column the names come from:
    'fd_couk_name', 'fd_org_name' or 'canonical'.
    """
    teams = pd.read_csv(TEAMS_CSV)
    mapping = dict(zip(teams[source_col], teams["canonical"]))
    unmapped = sorted(set(names) - set(mapping))
    if unmapped:
        raise ValueError(
            f"Unmapped team name(s) in column '{source_col}': {unmapped}. "
            f"Add them to {TEAMS_CSV}."
        )
    return names.map(mapping)


def download_season(code):
    """Return the path of the cached season CSV, downloading it if needed.

    Completed seasons never change, so a cached copy is reused. The current
    season is downloaded again on every call because new results are added.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"E0_{code}.csv"
    if path.exists() and code != CURRENT_SEASON:
        return path
    try:
        response = requests.get(RESULTS_URL.format(code=code), timeout=30)
        response.raise_for_status()
    except requests.RequestException as error:
        if not path.exists():
            raise
        print(
            f"!!! WARNING: could not refresh season {season_label(code)} "
            f"({type(error).__name__}). USING THE CACHED COPY, WHICH MAY BE STALE. !!!"
        )
        return path
    path.write_bytes(response.content)
    return path


def standardize_season(raw, code):
    """Turn one raw football-data.co.uk season into the standard columns."""
    missing_cols = [c for c in REQUIRED_RAW_COLS if c not in raw.columns]
    if missing_cols:
        raise ValueError(f"Season {code}: missing column(s) {missing_cols}")
    id_cols = ["Date", "Time", "HomeTeam", "AwayTeam"]
    if raw[id_cols].isna().any().any():
        bad_rows = raw.index[raw[id_cols].isna().any(axis=1)].tolist()
        raise ValueError(f"Season {code}: blank date/time/team in rows {bad_rows}")

    # Dates and times in the CSV are UK local time. Localizing to
    # Europe/London applies GMT in winter and BST (UTC+1) in summer.
    # ambiguous/nonexistent="raise" refuses to guess around clock changes.
    local = pd.to_datetime(raw["Date"] + " " + raw["Time"], format="%d/%m/%Y %H:%M")
    kickoff_utc = local.dt.tz_localize(
        "Europe/London", ambiguous="raise", nonexistent="raise"
    ).dt.tz_convert("UTC")

    out = pd.DataFrame(
        {
            "season": season_label(code),
            "kickoff_utc": kickoff_utc,
            "home": canonical_names(raw["HomeTeam"], "fd_couk_name"),
            "away": canonical_names(raw["AwayTeam"], "fd_couk_name"),
            # Nullable integers: a missing score stays missing (validate.py
            # rejects it) and a non-integer score raises here.
            "home_goals": raw["FTHG"].astype("Int64"),
            "away_goals": raw["FTAG"].astype("Int64"),
            "odds_home": np.nan,
            "odds_draw": np.nan,
            "odds_away": np.nan,
            "odds_source": "none",
        }
    )
    for source, cols in ODDS_SOURCES:
        if not all(c in raw.columns for c in cols):
            continue  # this bookmaker is not in this season's file
        use = (out["odds_source"] == "none") & raw[cols].notna().all(axis=1)
        out.loc[use, ODDS_COLS] = raw.loc[use, cols].to_numpy()
        out.loc[use, "odds_source"] = source
    return out


def load_history():
    """All completed seasons plus the current season to date, oldest first.

    Columns: season, kickoff_utc, home, away, home_goals, away_goals,
    odds_home, odds_draw, odds_away, odds_source.
    """
    seasons = []
    for code in COMPLETED_SEASONS + [CURRENT_SEASON]:
        raw = pd.read_csv(download_season(code), encoding="utf-8-sig")
        seasons.append(standardize_season(raw, code))
    history = pd.concat(seasons, ignore_index=True)
    return history.sort_values("kickoff_utc", kind="stable").reset_index(drop=True)


def get_training_data(matches, before_utc):
    """Return only the matches that kicked off strictly before `before_utc`.

    This is the ONLY way training data may be selected. Anything that predicts
    a match must be fitted on get_training_data(matches, that match's kickoff),
    so the match itself, and anything played at the same time or later, can
    never leak into its own forecast.
    """
    before_utc = pd.Timestamp(before_utc)
    if before_utc.tzinfo is None:
        raise ValueError("before_utc must be timezone-aware (UTC)")
    return matches[matches["kickoff_utc"] < before_utc]


def load_env_file():
    """Copy KEY=VALUE lines from .env into os.environ (stdlib only).

    A variable already set in the environment is left alone. Values are never
    printed.
    """
    path = REPO / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))


def load_fixtures():
    """Unplayed fixtures: match_id, matchday, kickoff_utc, home, away.

    kickoff_utc is always UTC. It is blank (NaT) for a postponed match with no
    new date: that match will still be played, so the season simulation needs
    it, but no forecast can be locked for it until it is rescheduled.

    Uses the football-data.org API. If the token is missing or the call fails,
    falls back to data/manual_fixtures.csv with a loud warning, except in CI
    (the CI environment variable), where it stops instead.
    """
    load_env_file()
    token = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not token:
        return _manual_fixtures("FOOTBALL_DATA_API_KEY is not set")
    try:
        # One call returns the whole season (free tier allows 10 calls/min).
        response = requests.get(FIXTURES_URL, headers={"X-Auth-Token": token}, timeout=30)
        response.raise_for_status()
        matches = response.json()["matches"]
    except (requests.RequestException, ValueError, KeyError) as error:
        # Only the error type is printed: the token must never reach the output.
        return _manual_fixtures(f"football-data.org call failed ({type(error).__name__})")

    # A POSTPONED match still carries its old date in the API, so that date
    # is dropped. Once rescheduled it comes back as SCHEDULED or TIMED with
    # the new date and its original matchday.
    upcoming = [m for m in matches if m["status"] in ("SCHEDULED", "TIMED", "POSTPONED")]
    fixtures = pd.DataFrame(
        {
            "match_id": [m["id"] for m in upcoming],
            "matchday": [m["matchday"] for m in upcoming],
            "kickoff_utc": pd.to_datetime(
                [None if m["status"] == "POSTPONED" else m["utcDate"] for m in upcoming], utc=True
            ),
            "home": [m["homeTeam"]["name"] for m in upcoming],
            "away": [m["awayTeam"]["name"] for m in upcoming],
        }
    )
    fixtures["home"] = canonical_names(fixtures["home"], "fd_org_name")
    fixtures["away"] = canonical_names(fixtures["away"], "fd_org_name")
    fixtures = fixtures.sort_values("kickoff_utc", kind="stable").reset_index(drop=True)
    fixtures.attrs["source"] = "api"  # read by run.forecast for the audit trail
    return fixtures


def _manual_fixtures(reason):
    # An unattended run must not lock a forecast on a hand-maintained file.
    if os.environ.get("CI"):
        raise SystemExit(f"STOP: {reason}. No fallback to {MANUAL_FIXTURES_CSV.name} in CI.")
    print("!" * 70)
    print(f"!!! WARNING: {reason}.")
    print(f"!!! FALLING BACK TO {MANUAL_FIXTURES_CSV}")
    print("!" * 70)
    fixtures = pd.read_csv(MANUAL_FIXTURES_CSV)
    expected = ["match_id", "matchday", "kickoff_utc", "home", "away"]
    if list(fixtures.columns) != expected:
        raise ValueError(f"{MANUAL_FIXTURES_CSV} must have columns {expected}")
    # Only kickoff_utc may be blank: a postponed match with no new date.
    if fixtures.drop(columns="kickoff_utc").isna().any().any():
        raise ValueError(f"{MANUAL_FIXTURES_CSV} has blank cells")
    # Kickoff times must be written with an explicit UTC marker, e.g.
    # 2026-10-10T11:30:00Z, so a local time cannot be mistaken for UTC.
    if not fixtures["kickoff_utc"].dropna().astype(str).str.endswith("Z").all():
        raise ValueError(f"{MANUAL_FIXTURES_CSV}: every kickoff_utc must end in 'Z'")
    fixtures["kickoff_utc"] = pd.to_datetime(fixtures["kickoff_utc"], utc=True)
    fixtures["home"] = canonical_names(fixtures["home"], "canonical")
    fixtures["away"] = canonical_names(fixtures["away"], "canonical")
    fixtures = fixtures.sort_values("kickoff_utc", kind="stable").reset_index(drop=True)
    fixtures.attrs["source"] = "manual"
    return fixtures
