"""Ranked Probability Score (RPS) for home/draw/away forecasts. Lower is better.

RPS compares cumulative probabilities, so it respects the order
home < draw < away: a forecast that put its weight on "draw" is punished less
for an away win than one that put its weight on "home".
"""

import numpy as np

OUTCOMES = ["H", "D", "A"]  # the order matters


def match_outcomes(matches):
    """'H', 'D' or 'A' for each match, from home_goals and away_goals."""
    home = matches["home_goals"].to_numpy(dtype=float, na_value=np.nan)
    away = matches["away_goals"].to_numpy(dtype=float, na_value=np.nan)
    if np.isnan(home).any() or np.isnan(away).any():
        raise ValueError("Cannot compute outcomes: some matches have no score")
    return np.where(home > away, "H", np.where(home == away, "D", "A"))


def rps(probs_hda, outcome):
    """RPS of one forecast (p_home, p_draw, p_away) for outcome 'H', 'D' or 'A'."""
    return float(rps_many([probs_hda], [outcome])[0])


def rps_many(probs_hda, outcomes):
    """Vectorized RPS: probs_hda has shape (n, 3); outcomes has n of 'H'/'D'/'A'."""
    probs = np.asarray(probs_hda, dtype=float)
    outcomes = np.asarray(outcomes)
    if probs.ndim != 2 or probs.shape[1] != 3 or len(probs) != len(outcomes):
        raise ValueError("probs_hda must have shape (n, 3) with one outcome per row")
    if (probs < 0).any() or not np.allclose(probs.sum(axis=1), 1.0, atol=1e-9):
        raise ValueError("Each forecast must be non-negative and sum to 1")
    if not np.isin(outcomes, OUTCOMES).all():
        raise ValueError(f"Outcomes must be one of {OUTCOMES}")

    # One-hot actual result, e.g. 'D' -> (0, 1, 0).
    actual = (outcomes[:, None] == np.array(OUTCOMES)[None, :]).astype(float)
    # Cumulative difference at "home" and at "home or draw". The third
    # cumulative term is always 1 - 1 = 0, so it is left out.
    cum_diff = np.cumsum(probs - actual, axis=1)[:, :2]
    return (cum_diff**2).sum(axis=1) / 2
