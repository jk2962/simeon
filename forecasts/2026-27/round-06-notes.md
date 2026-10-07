# 2026-27 round 6: pre-registered notes

Written before the first kickoff (2026-10-10 11:30 UTC) and before any result is known.

- **Model version:** `64fa02d`, Poisson GLM with MAP shrinkage, PRIOR_STRENGTH = 3.
- **Data cutoff:** matches that kicked off before 2026-10-10 11:30 UTC; the latest is 2026-09-20 15:30 UTC.
- **Generated:** 2026-10-07 22:35 UTC. Fixtures from the football-data.org API.

## Known divergences from the betting market

Two forecasts were known, before generation, to sit far from market prices (see MODEL_NOTES.md).

1. **Coventry v Newcastle: home 11.3%, draw 20.8%, away 67.9%** (expected goals 0.62 - 1.90).
   Cause: Coventry has 5 Premier League matches (1 goal scored, 10 conceded), and at strength 3 the promoted-team prior only partly offsets them.
   Evidence the model is wrong: Coventry scoring 2 or more, or avoiding defeat. One match is weak evidence; if Coventry scores 6 or more in its next 5 matches, the attack estimate was too low.
2. **Ipswich v Fulham: home 20.8%, draw 21.8%, away 57.4%** (expected goals 1.09 - 1.96).
   Cause: 34 of Ipswich's 39 matches in the training window are from its 2024-25 relegation season, a different squad. The model has no second-division data.
   Evidence the model is wrong: Ipswich avoiding defeat, or Fulham scoring 0 or 1. If Ipswich takes 5 or more points from its next 5 matches, the old data is misleading the model.

These forecasts were not adjusted after generation: round-06.csv is the direct output of `python -m pipeline.run --forecast` at the version above.
