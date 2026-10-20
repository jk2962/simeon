// Builds mocks/ from the pipeline's files. Run from web/: `npm run gen-mocks`.
//
// Real, copied from the repo: the fixture list, the results of rounds 1-5,
// and everything locked for round 6 (match probabilities and the table
// simulation).
// Invented here: every result from round 6 on, the round 7-8 forecasts,
// market prices and scores. Rounds 7-8 come from a small stand-in model (one
// rating per team, Poisson goals) fitted to reproduce the real round-6
// expected points, then re-simulated after each invented round.
//
// Reads ../data/raw/E0_2627.csv, which the pipeline downloads and git ignores.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { TEAMS } from "../src/config/teams.ts";
import type { ActualRow, Match, MatchweekSummary, PredictedRow, Snapshot } from "../src/lib/types";

const REPO = new URL("../../", import.meta.url);
const OUT = new URL("../mocks/", import.meta.url);
const SEASON = "2026-27";
const N_RUNS = 10_000;
const HOME_GOALS = 1.5; // mean goals of two equal teams
const AWAY_GOALS = 1.2;
const RATING_NOISE = 0.12; // per-run spread of each rating, widens the tables
const RATING_STEP = 0.02; // how far one result moves a rating, per goal of surprise
const NAIVE: Probs = [0.44, 0.25, 0.31]; // stand-in for the pipeline's naive baseline

type Probs = [number, number, number]; // home, draw, away
type Fixture = { id: string; matchday: number; kickoff: string; home: string; away: string };
type Result = { home: string; away: string; homeGoals: number; awayGoals: number };

const ROUNDS: { matchweek: number; status: MatchweekSummary["status"]; matchesLockedAt: string; tableLockedAt: string; dataThrough: string }[] = [
  { matchweek: 6, status: "complete", matchesLockedAt: "2026-10-07T22:35:46Z", tableLockedAt: "2026-10-08T04:49:45Z", dataThrough: "2026-09-20T15:30:00Z" },
  { matchweek: 7, status: "complete", matchesLockedAt: "2026-10-16T08:17:52Z", tableLockedAt: "2026-10-16T08:18:40Z", dataThrough: "2026-10-12T19:00:00Z" },
  { matchweek: 8, status: "upcoming", matchesLockedAt: "2026-10-22T16:17:31Z", tableLockedAt: "2026-10-22T16:18:22Z", dataThrough: "2026-10-19T19:00:00Z" },
];
const MODEL_VERSION = "20f98e7";

const ANALYSIS: Record<string, string> = {
  "Coventry v Newcastle":
    "Coventry have one goal from five matches, and the promoted-team prior only partly offsets that. The model sits well below market prices on the home side. Coventry scoring twice or avoiding defeat would count against it.",
  "Ipswich v Fulham":
    "Most of Ipswich's matches in the training window come from their 2024-25 relegation season with a different squad. The model has no second-division data, so it may rate them too low.",
  "Liverpool v Man City": "The closest match of the round on expected goals, 1.57 against 1.61. Neither side reaches 40%.",
  "Nottingham Forest v Arsenal":
    "Arsenal are favoured away from home. Forest's rating has barely moved since the start of the season.",
  "Chelsea v Tottenham":
    "Tottenham's poor start pulled their rating down sharply. Home advantage does most of the remaining work here.",
};

// --- helpers ---------------------------------------------------------------

function csv(path: string): Record<string, string>[] {
  const [head, ...lines] = readFileSync(new URL(path, REPO), "utf8").replace(/^﻿/, "").trim().split(/\r?\n/);
  const columns = head.split(",");
  return lines.map((line) => Object.fromEntries(line.split(",").map((value, i) => [columns[i], value])));
}

// Seeded, so the mocks are reproducible (mulberry32).
let seed = 2026;
function random(): number {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

function normal(): number {
  return Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random());
}

function poissonDraw(mean: number): number {
  let k = 0;
  let p = Math.exp(-mean);
  let cumulative = p;
  const u = random();
  while (u > cumulative && k < 15) {
    k += 1;
    p *= mean / k;
    cumulative += p;
  }
  return k;
}

const round4 = (x: number) => Math.round(x * 1e4) / 1e4;

// Rounded to 4 places with the three still summing to exactly 1.
function probs3([home, draw]: number[]): Probs {
  const a = round4(home);
  const b = round4(draw);
  return [a, b, round4(1 - a - b)];
}

function goalMeans(homeRating: number, awayRating: number): [number, number] {
  return [HOME_GOALS * Math.exp(homeRating - awayRating), AWAY_GOALS * Math.exp(awayRating - homeRating)];
}

// Home, draw, away from a 0-10 scoreline grid, as pipeline/model.py does.
function outcomeProbs(homeMean: number, awayMean: number): Probs {
  const pmf = (mean: number) => {
    const out = [Math.exp(-mean)];
    for (let k = 1; k <= 10; k++) out.push((out[k - 1] * mean) / k);
    return out;
  };
  const [h, a] = [pmf(homeMean), pmf(awayMean)];
  let [home, draw, total] = [0, 0, 0];
  for (let i = 0; i <= 10; i++) {
    for (let j = 0; j <= 10; j++) {
      const p = h[i] * a[j];
      total += p;
      if (i > j) home += p;
      if (i === j) draw += p;
    }
  }
  return [home / total, draw / total, 1 - (home + draw) / total];
}

// The single most likely scoreline on the 0-10 grid, as pipeline/export.py does.
function likelyScore(homeMean: number, awayMean: number): Match["prediction"]["likelyScore"] {
  const pmf = (mean: number) => Array.from({ length: 11 }, (_, k) => k).map((k) => {
    let p = Math.exp(-mean);
    for (let i = 1; i <= k; i++) p *= mean / i;
    return p;
  });
  const [h, a] = [pmf(homeMean), pmf(awayMean)];
  const total = h.reduce((x, y) => x + y) * a.reduce((x, y) => x + y);
  const home = h.indexOf(Math.max(...h));
  const away = a.indexOf(Math.max(...a));
  return { home, away, probability: round4((h[home] * a[away]) / total) };
}

function rps(p: Probs, homeGoals: number, awayGoals: number): number {
  const o = homeGoals > awayGoals ? [1, 0] : homeGoals === awayGoals ? [0, 1] : [0, 0];
  return ((p[0] - o[0]) ** 2 + (p[0] + p[1] - o[0] - o[1]) ** 2) / 2;
}

const pointsFor = (scored: number, conceded: number) => (scored > conceded ? 3 : scored === conceded ? 1 : 0);

// --- inputs ----------------------------------------------------------------

const code = Object.fromEntries(Object.entries(TEAMS).map(([teamCode, team]) => [team.canonicalName, teamCode]));
const table6 = csv(`forecasts/${SEASON}/table-round-06.csv`);
const round6 = new Map(csv(`forecasts/${SEASON}/round-06.csv`).map((row) => [row.match_id, row]));
const fixtures: Fixture[] = csv("data/manual_fixtures.csv").map((row) => ({
  id: row.match_id,
  matchday: Number(row.matchday),
  kickoff: row.kickoff_utc,
  home: row.home,
  away: row.away,
}));
const canonical = (name: string) => (name === "Nott'm Forest" ? "Nottingham Forest" : name);
const results: Result[] = csv("data/raw/E0_2627.csv").map((row) => ({
  home: canonical(row.HomeTeam),
  away: canonical(row.AwayTeam),
  homeGoals: Number(row.FTHG),
  awayGoals: Number(row.FTAG),
}));

const teams = table6.map((row) => row.team).sort();
const index = new Map(teams.map((team, i) => [team, i]));
const at = (team: string) => index.get(team)!;
if (teams.length !== 20 || teams.some((team) => !code[team])) throw new Error("teams.ts does not cover the table file");
if (results.length !== 50 || fixtures.length !== 330) throw new Error("Expected 5 rounds played and 33 to come");

// --- tables ----------------------------------------------------------------

function actualTable(played: Result[]): ActualRow[] {
  const rows = teams.map((team) => ({ team, played: 0, won: 0, drawn: 0, lost: 0, goalsFor: 0, goalsAgainst: 0, points: 0 }));
  for (const r of played) {
    for (const [team, scored, conceded] of [[r.home, r.homeGoals, r.awayGoals], [r.away, r.awayGoals, r.homeGoals]] as const) {
      const row = rows[at(team)];
      row.played += 1;
      row.goalsFor += scored;
      row.goalsAgainst += conceded;
      row[scored > conceded ? "won" : scored === conceded ? "drawn" : "lost"] += 1;
      row.points += pointsFor(scored, conceded);
    }
  }
  const difference = (row: (typeof rows)[number]) => row.goalsFor - row.goalsAgainst;
  rows.sort((a, b) => b.points - a.points || difference(b) - difference(a) || b.goalsFor - a.goalsFor || a.team.localeCompare(b.team));
  return rows.map(({ team, ...row }, i) => ({ teamCode: code[team], position: i + 1, ...row }));
}

// Plays the remaining fixtures N_RUNS times. Each run has exactly one team in
// each position, so every row and every column of the result sums to 1.
function simulate(played: Result[], remaining: Fixture[], ratings: number[]): PredictedRow[] {
  const start = actualTable(played);
  const base = teams.map((team) => {
    const row = start.find((r) => r.teamCode === code[team])!;
    return { points: row.points, difference: row.goalsFor - row.goalsAgainst, scored: row.goalsFor };
  });
  const pairs = remaining.map((f) => [at(f.home), at(f.away)]);
  const counts = teams.map(() => new Array<number>(20).fill(0));
  const totalPoints = new Array<number>(20).fill(0);

  for (let run = 0; run < N_RUNS; run++) {
    const rating = ratings.map((r) => r + RATING_NOISE * normal());
    const points = base.map((b) => b.points);
    const difference = base.map((b) => b.difference);
    const scored = base.map((b) => b.scored);
    for (const [h, a] of pairs) {
      const [homeMean, awayMean] = goalMeans(rating[h], rating[a]);
      const homeGoals = poissonDraw(homeMean);
      const awayGoals = poissonDraw(awayMean);
      points[h] += pointsFor(homeGoals, awayGoals);
      points[a] += pointsFor(awayGoals, homeGoals);
      difference[h] += homeGoals - awayGoals;
      difference[a] += awayGoals - homeGoals;
      scored[h] += homeGoals;
      scored[a] += awayGoals;
    }
    // Premier League order (points, goal difference, goals scored), then at random.
    const tiebreak = teams.map(() => random());
    const order = teams.map((_, i) => i);
    order.sort((x, y) => points[y] - points[x] || difference[y] - difference[x] || scored[y] - scored[x] || tiebreak[x] - tiebreak[y]);
    order.forEach((team, position) => (counts[team][position] += 1));
    points.forEach((p, team) => (totalPoints[team] += p));
  }

  return teams
    .map((team, i) => ({ team, expectedPoints: totalPoints[i] / N_RUNS, positions: counts[i].map((c) => c / N_RUNS) }))
    .sort((a, b) => b.expectedPoints - a.expectedPoints)
    .map((row, i) => predictedRow(row.team, i, row.expectedPoints, row.positions));
}

function predictedRow(team: string, rank: number, expectedPoints: number, positions: number[]): PredictedRow {
  return {
    teamCode: code[team],
    predictedPosition: rank + 1,
    expectedPoints: Math.round(expectedPoints * 10) / 10,
    positionProbabilities: positions,
    pTitle: positions[0],
    pTop4: round4(positions.slice(0, 4).reduce((a, b) => a + b)),
    pRelegation: round4(positions.slice(-3).reduce((a, b) => a + b)),
  };
}

// Ratings under which the stand-in model expects the same final points as the
// real round-6 simulation.
function fitRatings(): number[] {
  const target = teams.map((team) => Number(table6.find((row) => row.team === team)!.exp_points));
  const current = actualTable(results);
  const ratings = teams.map(() => 0);
  for (let step = 0; step < 400; step++) {
    const expected = teams.map((team) => current.find((r) => r.teamCode === code[team])!.points);
    for (const f of fixtures) {
      const [h, a] = [at(f.home), at(f.away)];
      const [home, draw, away] = outcomeProbs(...goalMeans(ratings[h], ratings[a]));
      expected[h] += 3 * home + draw;
      expected[a] += 3 * away + draw;
    }
    expected.forEach((points, i) => (ratings[i] += 0.01 * (target[i] - points)));
  }
  return ratings;
}

// --- build -----------------------------------------------------------------

const ratings = fitRatings();
const summaries: MatchweekSummary[] = [];
const tables: PredictedRow[][] = [];

for (const round of ROUNDS) {
  const { matchweek, status } = round;
  const roundFixtures = fixtures.filter((f) => f.matchday === matchweek);

  // Locked before the round: the table first, then the matches.
  const predictedTable =
    matchweek === 6
      ? table6.map((row, i) =>
          predictedRow(row.team, i, Number(row.exp_points), teams.map((_, k) => Number(row[`pos_${k + 1}`]))),
        )
      : simulate(results, fixtures.filter((f) => f.matchday >= matchweek), ratings);
  tables.push(predictedTable);

  // The standings the forecast was locked on: everything before this round.
  const standings = actualTable(results);

  const matches: Match[] = [];
  const roundResults: Result[] = [];
  for (const f of roundFixtures) {
    const locked = matchweek === 6 ? round6.get(f.id) : undefined;
    const [homeMean, awayMean] = locked
      ? [Number(locked.exp_home_goals), Number(locked.exp_away_goals)]
      : goalMeans(ratings[at(f.home)], ratings[at(f.away)]);
    const p = locked
      ? probs3([Number(locked.p_home), Number(locked.p_draw)])
      : probs3(outcomeProbs(homeMean, awayMean));

    let result: Match["result"] = null;
    let market: Match["market"] = null;
    let scores: Match["scores"] = null;
    if (status === "complete") {
      const [homeGoals, awayGoals] = [poissonDraw(homeMean), poissonDraw(awayMean)];
      roundResults.push({ home: f.home, away: f.away, homeGoals, awayGoals });
      const noisy = p.map((x) => x * (0.85 + 0.3 * random()));
      const total = noisy.reduce((a, b) => a + b);
      const book = probs3(noisy.map((x) => x / total));
      result = { home: homeGoals, away: awayGoals };
      market = { pHome: book[0], pDraw: book[1], pAway: book[2] };
      scores = {
        rpsModel: round4(rps(p, homeGoals, awayGoals)),
        rpsNaive: round4(rps(NAIVE, homeGoals, awayGoals)),
        rpsBookmaker: round4(rps(book, homeGoals, awayGoals)),
      };
      // A result better than expected raises the rating, and the reverse.
      const surprise = homeGoals - awayGoals - (homeMean - awayMean);
      ratings[at(f.home)] += RATING_STEP * surprise;
      ratings[at(f.away)] -= RATING_STEP * surprise;
    }

    matches.push({
      id: f.id,
      kickoff: f.kickoff,
      home: code[f.home],
      away: code[f.away],
      prediction: {
        homeWin: p[0],
        draw: p[1],
        awayWin: p[2],
        expectedGoals: { home: Math.round(homeMean * 100) / 100, away: Math.round(awayMean * 100) / 100 },
        likelyScore: likelyScore(homeMean, awayMean),
        analysis: ANALYSIS[`${f.home} v ${f.away}`] ?? null,
        lockedAt: round.matchesLockedAt,
        lockReason: null,
      },
      result,
      market,
      scores,
    });
  }
  results.push(...roundResults);

  const snapshot: Snapshot = {
    matchweek,
    lockedAt: round.tableLockedAt,
    dataThrough: round.dataThrough,
    modelVersion: MODEL_VERSION,
    predictedTable,
    actualTable: standings,
  };
  mkdirSync(new URL(`mw-${matchweek}/`, OUT), { recursive: true });
  writeFileSync(new URL(`mw-${matchweek}/matches.json`, OUT), JSON.stringify(matches, null, 2) + "\n");
  writeFileSync(new URL(`mw-${matchweek}/snapshot.json`, OUT), JSON.stringify(snapshot, null, 2) + "\n");
  summaries.push({ season: SEASON, matchweek, status, retrospective: false, matchesLockedAt: round.matchesLockedAt, tableLockedAt: round.tableLockedAt });
}
writeFileSync(new URL("matchweeks.json", OUT), JSON.stringify(summaries, null, 2) + "\n");

// Report how far the predicted table moved between rounds.
for (let i = 1; i < tables.length; i++) {
  const before = new Map(tables[i - 1].map((row) => [row.teamCode, row.predictedPosition]));
  const movers = tables[i]
    .map((row) => ({ team: row.teamCode, from: before.get(row.teamCode)!, to: row.predictedPosition }))
    .filter((m) => Math.abs(m.to - m.from) >= 2);
  console.log(`MW${ROUNDS[i - 1].matchweek} to MW${ROUNDS[i].matchweek}: ${movers.length} teams moved 2+ places`, movers.map((m) => `${m.team} ${m.from}→${m.to}`).join(", "));
}
