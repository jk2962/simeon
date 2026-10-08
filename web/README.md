# Matchweek (web)

The website for simeon's forecasts. Self-contained: its own `package.json`, nothing shared with the Python pipeline.

## Run

```
npm install
npm run dev      # http://localhost:3000, on mock data
npm run build
npm run lint
npm run gen-mocks  # rebuild mocks/ from the pipeline files
npm run check    # mock data and chip color self-check
```

## Data

Pages read through `src/lib/api.ts` and do not know the source.

The first of these that applies:

1. `API_BASE_URL` set: fetched from that backend (contract in `src/lib/types.ts`).
2. `data/` exists: the real forecasts, written by `python -m pipeline.export` from the repo root and committed.
3. Development only: `mocks/`, with a MOCK DATA banner in the header. `USE_MOCKS=1 npm run dev` forces the mocks while `data/` exists.
4. Production with none of the above: pages show an inline error. Mocks are never served in production.

## Mock data

`mocks/` covers matchweeks 6–8 of 2026-27, built by `scripts/gen-mocks.ts`. Fixtures, the results of rounds 1–5 and everything locked for round 6 are copied from the pipeline's files. Everything else is invented: all results from round 6 on, the round 7–8 forecasts (a small stand-in model, re-simulated after each round), market prices and scores.

## Team colors

`src/config/teams.ts`. Review them at `/dev/colors`. No logos, crests or league branding anywhere.
