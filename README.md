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

`.github/workflows/lock.yml` runs `--lock-due` every hour. It locks the next round
between 30h and 1h before its first kickoff: on the first run where every earlier
result is in the data, or once kickoff is under 6h away. It then fails if a round
is under 2h from kickoff and still unlocked. Nothing locks within 15 minutes of kickoff.
The workflow reads the token from the `FOOTBALL_DATA_API_KEY` Actions secret and stops if it is missing.

Outside CI, without the token, fixtures come from `data/manual_fixtures.csv`
(columns `match_id,matchday,kickoff_utc,home,away`; kickoff like
`2026-10-10T11:30:00Z`; team names from the `canonical` column of `data/teams.csv`).
