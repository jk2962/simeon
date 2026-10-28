# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

simeon: probabilistic Premier League match forecasts, locked before kickoff and scored (RPS) against the betting market. Two independent parts: a Python pipeline at the repo root and a Next.js site in `web/` that share nothing but the exported JSON.

## Commands

Python (3.12, venv at `.venv`; `pytest.ini` sets `pythonpath = .`):

```
.venv/bin/pytest                                   # all tests
.venv/bin/pytest tests/test_lock.py -k postponed   # one file / one test
.venv/bin/python -m pipeline.run --check           # load, validate, report baselines
.venv/bin/python -m pipeline.run --backtest        # 2025-26 holdout sanity check
.venv/bin/python -m pipeline.run --forecast        # lock the next round (clean tree required)
.venv/bin/python -m pipeline.run --score           # rewrite forecasts/scores.csv
.venv/bin/python -m pipeline.simulate              # lock season-table snapshot (clean tree required)
.venv/bin/python -m pipeline.retro                 # retrospective rounds 1-5 (clean tree required)
.venv/bin/python -m pipeline.tune                  # PRIOR_STRENGTH grid; prints only, changes nothing
.venv/bin/python -m pipeline.export                # write web/data/*.json from forecasts/
```

`FOOTBALL_DATA_API_KEY` (football-data.org) can live in the gitignored `.env`; without it, fixtures fall back to `data/manual_fixtures.csv`. Results/odds are downloaded from football-data.co.uk into gitignored `data/raw/`.

Web (run inside `web/`): `npm run dev`, `npm run build`, `npm run lint`, `npm run check` (mock-data and team-color self-check, plain `node:assert`), `npm run gen-mocks`.

## Pipeline architecture

- `ingest.py` loads all seasons into one standardized DataFrame (team names mapped via `data/teams.csv` `canonical` column) and fixtures (API or manual CSV). **All training data must come from `ingest.get_training_data(matches, before_utc)`**, which keeps only matches strictly before a cutoff — this is the leakage guard.
- `validate.py` raises `ValueError` on bad data; it never drops or fixes rows.
- `model.py`: independent Poisson GLM (attack/defense per team + one home advantage) with MAP/L2 shrinkage toward a prior mean (learned promoted-team prior, else 0). `PRIOR_STRENGTH = 3`, `TRAINING_WINDOW_DAYS = 730`. `tests/test_model.py` is the spec.
- `run.py`: CLI, walk-forward backtests, locking logic (`lock_units`, `lock_due`, partial/postponed-match handling) and `score_forecasts`. `baselines.py` (naive + bookmaker closing odds) and `scoring.py` (RPS, outcome order H < D < A matters).
- `simulate.py`: Monte Carlo season (10,000 runs, seed 2026) with team parameters drawn from a Laplace covariance.
- `export.py`: reads `forecasts/` (never forecasts itself) and writes `web/data/` in the shape of `web/src/lib/types.ts`.

## Locked forecasts are an audit record

- `forecasts/<season>/round-NN.csv`, `table-round-NN.csv` and partial locks are written once, stamped with the git short SHA (`model_version`). `--forecast`, `simulate` and `retro` refuse to run with uncommitted changes, so commit code first. Never edit, regenerate or delete a locked file.
- `retro-*` files are after-the-fact forecasts for rounds 1-5, kept separate by name and labelled on the site; they are not evidence.
- `.github/workflows/lock.yml` runs `--lock-due` hourly and commits locks as `Forecast: <path> (locked before kickoff)`; it then runs `--assert-locked`. Lock timing rules are in README.md.

## Model change policy (MODEL_NOTES.md)

MODEL_NOTES.md documents every modeling decision and a pre-registered change policy. Read it before touching `model.py`, `simulate.py`, `PRIOR_STRENGTH`, the window, the promoted prior, match weighting or simulation uncertainty. In short: model changes only at checkpoints (after rounds 10/20/30), at most 2 named candidates, adopted only on the stated walk-forward RPS/calibration thresholds (compare on 2023-24 + 2024-25; 2025-26 is a holdout used once per candidate). Bug fixes may only restore already-documented behavior. Every decision, including "no change", goes in the decision log. Don't tune the model to match market prices.

## Web (`web/`)

- Next.js 16.4 / React 19.3 / Tailwind 4. Per `web/AGENTS.md`, this Next.js has breaking changes vs. training data: read `web/node_modules/next/dist/docs/` before writing Next code. `next dev` re-adds that block to `web/AGENTS.md`.
- All data goes through `src/lib/api.ts`. Source priority: `API_BASE_URL` → committed `web/data/` → `mocks/` (dev only, shows a MOCK DATA banner; `USE_MOCKS=1` forces it) → inline error in production. Mocks are never served in production.
- Team colors live in `src/config/teams.ts` (review at `/dev/colors`). No team logos or crests; the only league mark is the tab icon (`src/app/icon.png`).

## Commit style

Prefixes seen in history: `pipeline: …`, `web: …`, `Scores: round N results`, `Season snapshot: …`, `Forecast: …`.
