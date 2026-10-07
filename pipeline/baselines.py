"""Baseline forecasts that the model has to beat (naive) or approach (bookmaker)."""

import numpy as np

from pipeline.ingest import ODDS_COLS
from pipeline.scoring import match_outcomes


def naive_probs(train):
    """League-wide (p_home, p_draw, p_away) frequencies in the training data.

    `train` must come from ingest.get_training_data, so the frequencies use
    only matches played before the match being predicted.
    """
    if len(train) == 0:
        raise ValueError("naive_probs needs at least one training match")
    outcomes = match_outcomes(train)
    return np.array([(outcomes == o).mean() for o in ["H", "D", "A"]])


def bookmaker_probs(row):
    """(p_home, p_draw, p_away) implied by one match's odds.

    Proportional de-vig: 1/odds sums to more than 1 (the bookmaker's margin),
    so divide each by the total. This is the simplest method and assumes the
    margin is spread evenly across outcomes. Alternatives exist (e.g. Shin's
    method, which puts more of the margin on longshots); they are deliberately
    not implemented here.
    """
    odds = np.array([row[c] for c in ODDS_COLS], dtype=float)
    if np.isnan(odds).any():
        raise ValueError(f"No odds for {row['home']} v {row['away']}")
    inverse = 1.0 / odds
    return inverse / inverse.sum()
