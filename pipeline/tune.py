"""Choose model.PRIOR_STRENGTH. Run with `python -m pipeline.tune`.

Walk-forward RPS on 2023-24 and 2024-25 for a small grid of values. Before
each week the model is refitted on matches that kicked off strictly before
that week's first match, then scored on the week's matches.

2025-26 and 2026-27 are deliberately NOT used here: 2025-26 is reserved for
the Phase 2 sanity check, and a number chosen on it could not be tested on it.

This prints the results. It does not change PRIOR_STRENGTH: that is set by
hand in pipeline/model.py, where the comment explains the choice. The lowest
RPS here is not automatically the right answer: when several values are tied
within noise, the choice is a judgment call (see MODEL_NOTES.md).
"""

import time

import numpy as np

from pipeline import ingest, model, scoring
from pipeline.run import walk_forward_blocks

TUNING_SEASONS = ["2023-24", "2024-25"]
GRID = [model.NEAR_ZERO_STRENGTH, 3.0, 10.0, 30.0, 100.0]


def walk_forward_model_rps(history, season, prior_strength):
    """Mean RPS of the model on one season, refitted before each week."""
    season_df = history[history["season"] == season]
    scores = []
    for block in walk_forward_blocks(season_df):
        train = ingest.get_training_data(history, block["kickoff_utc"].min())
        fitted = model.fit_with_strength(train, prior_strength)
        probs = []
        for _, match in block.iterrows():
            p = model.predict(fitted, match["home"], match["away"])
            probs.append([p["p_home"], p["p_draw"], p["p_away"]])
        scores.append(scoring.rps_many(probs, scoring.match_outcomes(block)))
    return np.concatenate(scores).mean()


if __name__ == "__main__":
    started = time.time()
    history = ingest.load_history()
    print(f"{'PRIOR_STRENGTH':>14}  " + "  ".join(TUNING_SEASONS) + "     mean")
    means = {}
    for strength in GRID:
        by_season = [walk_forward_model_rps(history, s, strength) for s in TUNING_SEASONS]
        means[strength] = np.mean(by_season)
        print(f"{strength:>14}  " + "   ".join(f"{r:.4f}" for r in by_season) + f"   {means[strength]:.4f}")
    best = min(means, key=means.get)
    print(f"\nLowest mean RPS: PRIOR_STRENGTH = {best}  ({time.time() - started:.0f}s)")
