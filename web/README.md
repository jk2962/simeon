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

- `API_BASE_URL` set: fetched from that backend (contract in `src/lib/types.ts`).
- `API_BASE_URL` unset, development: read from `mocks/`. The header shows a MOCK DATA banner.
- `API_BASE_URL` unset, production: pages show an inline error. Mocks are never served in production.

## Mock data

`mocks/` covers matchweeks 6–8 of 2026-27, built by `scripts/gen-mocks.ts`. Fixtures, the results of rounds 1–5 and everything locked for round 6 are copied from the pipeline's files. Everything else is invented: all results from round 6 on, the round 7–8 forecasts (a small stand-in model, re-simulated after each round), market prices and scores.

## Team colors

`src/config/teams.ts`. Review them at `/dev/colors`. No logos, crests or league branding anywhere.
