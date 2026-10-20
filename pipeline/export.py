"""Export the locked forecasts as the JSON files the website reads.

`python -m pipeline.export` writes web/data/:

    matchweeks.json        one entry per round that has a locked file
    mw-N/matches.json      the round's match forecasts, with results once played
    mw-N/snapshot.json     the season-table forecast locked before the round

The shapes are the API contract in web/src/lib/types.ts. Nothing here
forecasts: the files in forecasts/ are only read, and the results, market
prices and scores come from run.score_forecasts, as in `--score`.

Optional: forecasts/<season>/round-NN-analysis.md holds hand-written match
notes (see parse_analysis).
"""

import json
import os
import re

import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

from pipeline import ingest, model, validate
from pipeline.run import BOOK_COLS, FORECASTS_DIR, PROB_COLS, score_forecasts

OUT_DIR = ingest.REPO / "web" / "data"
POSITIONS = [f"pos_{k}" for k in range(1, 21)]
RPS_COLS = ["rps_model", "rps_naive", "rps_bookmaker"]


def likely_score(exp_home_goals, exp_away_goals):
    """The single most likely scoreline and its probability.

    Uses the same 0-10 scoreline grid as model.predict, so it follows from the
    two locked expected-goals numbers alone. It is usually only 8-15% likely,
    and it can disagree with the most likely outcome (1-1 can be the likeliest
    score of a match the home side is favoured to win).
    """
    goals = np.arange(model.MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(goals, exp_home_goals), poisson.pmf(goals, exp_away_goals))
    grid = grid / grid.sum()
    home, away = np.unravel_index(grid.argmax(), grid.shape)
    return {"home": int(home), "away": int(away), "probability": float(grid[home, away])}


def parse_analysis(text, fixtures):
    """Hand-written notes per match: {(home, away): text}.

    The file is Markdown. A line `## Home v Away` (canonical team names)
    starts a match, and the lines under it are its note. Anything before the
    first such line is ignored. A heading that names no fixture of the round
    raises, so a typo cannot silently drop a note.
    """
    notes, current = {}, None
    for line in text.splitlines():
        heading = re.fullmatch(r"##\s+(.+?)\s+v\s+(.+?)\s*", line)
        if heading:
            current = (heading[1], heading[2])
            if current not in fixtures:
                raise ValueError(f"Analysis heading names no fixture of the round: {line!r}")
            notes[current] = []
        elif current:
            notes[current].append(line.strip())
    return {fixture: " ".join(filter(None, lines)) for fixture, lines in notes.items() if any(lines)}


def api_results():
    """{match_id: (home_goals, away_goals)} for finished matches, from football-data.org.

    football-data.co.uk, the scoring source, can lag the final whistle by
    days. Empty without a token or if the call fails: the export then just
    waits for football-data.co.uk.
    """
    ingest.load_env_file()
    token = os.environ.get("FOOTBALL_DATA_API_KEY")
    if not token:
        return {}
    try:
        response = requests.get(ingest.FIXTURES_URL, headers={"X-Auth-Token": token}, timeout=30)
        response.raise_for_status()
        matches = response.json()["matches"]
    except (requests.RequestException, ValueError, KeyError) as error:
        print(f"Could not fetch API results ({type(error).__name__}); showing football-data.co.uk results only.")
        return {}
    return {
        m["id"]: (m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"])
        for m in matches
        if m["status"] == "FINISHED"
    }


def fill_results(scored, results):
    """Fill blank scores from `results` ({match_id: (home, away)}).

    Display only: market and RPS stay blank, so a match is scored only once
    football-data.co.uk has it with closing odds. A result already there is
    never overwritten.
    """
    scored = scored.copy()
    blank = scored["home_goals"].isna() & scored["match_id"].isin(results)
    for col, side in [("home_goals", 0), ("away_goals", 1)]:
        scored.loc[blank, col] = scored.loc[blank, "match_id"].map(lambda i: results[i][side])
    return scored


def standings(results, teams, codes):
    """League table from results: one row per team in `teams`, best first.

    Ordered as the Premier League does up to goals scored (points, goal
    difference, goals scored), then by name.
    """
    rows = {
        team: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "goalsFor": 0, "goalsAgainst": 0, "points": 0}
        for team in teams
    }
    for match in results.itertuples():
        sides = [(match.home, match.home_goals, match.away_goals), (match.away, match.away_goals, match.home_goals)]
        for team, scored, conceded in sides:
            row = rows[team]
            row["played"] += 1
            row["goalsFor"] += int(scored)
            row["goalsAgainst"] += int(conceded)
            row["won" if scored > conceded else "drawn" if scored == conceded else "lost"] += 1
            row["points"] += 3 if scored > conceded else 1 if scored == conceded else 0
    order = sorted(
        rows,
        key=lambda t: (-rows[t]["points"], rows[t]["goalsAgainst"] - rows[t]["goalsFor"], -rows[t]["goalsFor"], t),
    )
    return [{"teamCode": codes[team], "position": i + 1, **rows[team]} for i, team in enumerate(order)]


def build_snapshot(table, history, codes):
    """One snapshot from the rows of a table-round-NN.csv.

    actualTable is the standings the forecast was locked on: every match of
    the season up to the file's data_through_utc, which is what the model saw.
    """
    table = table.sort_values("exp_points", ascending=False, kind="stable")
    season = table["season"].iloc[0]
    cutoff = pd.Timestamp(table["data_through_utc"].iloc[0])
    seen = history[(history["season"] == season) & (history["kickoff_utc"] <= cutoff)]
    predicted = [
        {
            "teamCode": codes[row.team],
            "predictedPosition": rank,
            "expectedPoints": round(float(row.exp_points), 1),
            "positionProbabilities": [float(getattr(row, col)) for col in POSITIONS],
            "pTitle": round(float(row.p_title), 4),
            "pTop4": round(float(row.p_top4), 4),
            "pRelegation": round(float(row.p_relegation), 4),
        }
        for rank, row in enumerate(table.itertuples(), start=1)
    ]
    return {
        "matchweek": int(table["matchday"].iloc[0]),
        "lockedAt": table["generated_at_utc"].iloc[0],
        "dataThrough": table["data_through_utc"].iloc[0],
        "modelVersion": str(table["model_version"].iloc[0]),
        "predictedTable": predicted,
        "actualTable": standings(seen, list(table["team"]), codes),
    }


def _numbers(row, cols, keys):
    """{key: value} for the columns, or None if any of them is blank."""
    values = [row[col] for col in cols]
    if any(pd.isna(value) for value in values):
        return None
    return dict(zip(keys, map(float, values)))


def build_matches(scored, codes, analysis):
    """The matches of one round, earliest kickoff first.

    scored: this round's rows of run.score_forecasts (results, bookmaker and
    RPS columns blank until played), with a lock_reason column.
    analysis: {(home, away): text}, see parse_analysis.

    A fixture forecast twice (locked, postponed, locked again) keeps only its
    latest lock: the earlier one was made for a date that was never played.
    """
    latest = scored.sort_values("generated_at_utc", kind="stable").drop_duplicates(["home", "away"], keep="last")
    matches = []
    for _, row in latest.sort_values(["kickoff_utc", "match_id"], kind="stable").iterrows():
        result = _numbers(row, ["home_goals", "away_goals"], ["home", "away"])
        # ponytail: a played match with no bookmaker odds gets no scores at all,
        # because the contract's scores object needs all three. Split it if
        # that ever happens.
        played_with_odds = result is not None and not pd.isna(row["rps_bookmaker"])
        matches.append(
            {
                "id": str(row["match_id"]),
                "kickoff": row["kickoff_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home": codes[row["home"]],
                "away": codes[row["away"]],
                "prediction": {
                    **_numbers(row, PROB_COLS, ["homeWin", "draw", "awayWin"]),
                    "expectedGoals": _numbers(row, ["exp_home_goals", "exp_away_goals"], ["home", "away"]),
                    "likelyScore": likely_score(row["exp_home_goals"], row["exp_away_goals"]),
                    "analysis": analysis.get((row["home"], row["away"])),
                    "lockedAt": row["generated_at_utc"],
                    "lockReason": None if pd.isna(row["lock_reason"]) else row["lock_reason"],
                },
                "result": result and {side: int(goals) for side, goals in result.items()},
                "market": _numbers(row, BOOK_COLS, ["pHome", "pDraw", "pAway"]) if played_with_odds else None,
                "scores": _numbers(row, RPS_COLS, ["rpsModel", "rpsNaive", "rpsBookmaker"]) if played_with_odds else None,
            }
        )
    return matches


def round_status(matches):
    """'upcoming' with no results, 'complete' with all of them, else 'in_progress'."""
    played = sum(match["result"] is not None for match in matches)
    return "upcoming" if played == 0 else "complete" if played == len(matches) else "in_progress"


def check(matches_by_round, snapshots):
    """Refuse to write anything the website would show wrongly."""
    for matchday, matches in matches_by_round.items():
        for match in matches:
            p = match["prediction"]
            if abs(p["homeWin"] + p["draw"] + p["awayWin"] - 1.0) > 1e-9:
                raise ValueError(f"Round {matchday} match {match['id']}: probabilities do not sum to 1")
            if pd.Timestamp(p["lockedAt"]) >= pd.Timestamp(match["kickoff"]):
                raise ValueError(f"Round {matchday} match {match['id']}: locked at or after kickoff")
    for matchday, snapshot in snapshots.items():
        probs = np.array([row["positionProbabilities"] for row in snapshot["predictedTable"]])
        if probs.shape != (20, 20) or len(snapshot["actualTable"]) != 20:
            raise ValueError(f"Round {matchday} table: expected 20 teams and 20 positions")
        if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-6) or not np.allclose(probs.sum(axis=0), 1.0, atol=1e-6):
            raise ValueError(f"Round {matchday} table: position probabilities do not sum to 1 by team and by position")


def export(out_dir=OUT_DIR):
    season = ingest.season_label(ingest.CURRENT_SEASON)
    season_dir = FORECASTS_DIR / season
    history = ingest.load_history()
    validate.validate_history(history, season)
    teams = pd.read_csv(ingest.TEAMS_CSV)
    codes = dict(zip(teams["canonical"], teams["code"]))

    # Match forecasts: every round file, whole rounds and partial locks alike.
    round_locks = {}  # matchday -> lock time of the whole-round file
    frames = []
    for path in sorted(season_dir.glob("round-*.csv")):
        frame = pd.read_csv(path).assign(season=season)
        if "lock_reason" not in frame:
            frame["lock_reason"] = None
            round_locks[int(frame["matchday"].iloc[0])] = frame["generated_at_utc"].iloc[0]
        frames.append(frame)
    matches_by_round = {}
    if frames:
        forecasts = pd.concat(frames, ignore_index=True)
        forecasts["kickoff_utc"] = pd.to_datetime(forecasts["kickoff_utc"], utc=True)
        scored = fill_results(score_forecasts(forecasts, history), api_results())
        for matchday, round_df in scored.groupby("matchday"):
            notes_path = season_dir / f"round-{matchday:02d}-analysis.md"
            fixtures = set(zip(round_df["home"], round_df["away"]))
            analysis = parse_analysis(notes_path.read_text(), fixtures) if notes_path.exists() else {}
            matches_by_round[int(matchday)] = build_matches(round_df, codes, analysis)

    snapshots = {}
    for path in sorted(season_dir.glob("table-round-*.csv")):
        snapshot = build_snapshot(pd.read_csv(path), history, codes)
        snapshots[snapshot["matchweek"]] = snapshot

    check(matches_by_round, snapshots)

    matchweeks = []
    for matchday in sorted(set(matches_by_round) | set(snapshots)):
        matches = matches_by_round.get(matchday, [])
        locks = sorted(match["prediction"]["lockedAt"] for match in matches)
        matchweeks.append(
            {
                "season": season,
                "matchweek": matchday,
                "status": round_status(matches),
                # A round locked only in parts has no whole-round file: use its earliest lock.
                "matchesLockedAt": round_locks.get(matchday, locks[0] if locks else None),
                "tableLockedAt": snapshots[matchday]["lockedAt"] if matchday in snapshots else None,
            }
        )

    def write(relative, data):
        path = out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")

    write("matchweeks.json", matchweeks)
    for matchday, matches in matches_by_round.items():
        write(f"mw-{matchday}/matches.json", matches)
    for matchday, snapshot in snapshots.items():
        write(f"mw-{matchday}/snapshot.json", snapshot)

    print(f"\n== Exported {season} to {out_dir} ==")
    for week in matchweeks:
        matches = matches_by_round.get(week["matchweek"], [])
        played = sum(match["result"] is not None for match in matches)
        print(
            f"Round {week['matchweek']:>2}  {week['status']:<12}{played}/{len(matches)} played  "
            f"table {'yes' if week['tableLockedAt'] else 'no'}"
        )


if __name__ == "__main__":
    export()
