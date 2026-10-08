# simeon

Probabilistic Premier League match forecasts, locked before kickoff and scored against the betting market.

Work in progress.

## Setup

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
export FOOTBALL_DATA_API_KEY=...   # football-data.org token; never commit it
```

## Run

```
.venv/bin/pytest
.venv/bin/python -m pipeline.run --check
.venv/bin/python -m pipeline.run --forecast   # lock the next round; needs a clean working tree
.venv/bin/python -m pipeline.run --score      # score locked forecasts, rewrite forecasts/scores.csv
.venv/bin/python -m pipeline.simulate         # lock the season-table snapshot for the next round; needs a clean working tree
```

Without the token, fixtures come from `data/manual_fixtures.csv`
(columns `match_id,matchday,kickoff_utc,home,away`; kickoff like
`2026-10-10T11:30:00Z`; team names from the `canonical` column of `data/teams.csv`).
