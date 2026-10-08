// Self-check, no framework: `npm run check`. Fails loudly if the mock data is
// internally inconsistent or the chip color rule breaks.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TEAMS, chipColor, getTeam, luminance } from "../src/config/teams.ts";

const read = (file) => JSON.parse(readFileSync(new URL(`../mocks/${file}`, import.meta.url), "utf8"));
const near = (a, b, tolerance = 1e-9) => Math.abs(a - b) <= tolerance;
const codes = Object.keys(TEAMS);
assert.equal(codes.length, 20);

// --- team colors ---
assert.ok(near(luminance("#FFFFFF"), 1) && near(luminance("#000000"), 0));
for (const code of codes) {
  const team = TEAMS[code];
  for (const hex of [team.primary, team.secondary]) assert.match(hex, /^#[0-9A-F]{6}$/, `${code} ${hex}`);
}
// Primary unless it is white or near-white.
const rendered = Object.fromEntries(codes.map((code) => [code, chipColor(TEAMS[code]).hex]));
assert.deepEqual(codes.filter((code) => rendered[code] !== TEAMS[code].primary), ["FUL", "LEE"]);
assert.equal(rendered.MCI, "#6CABDD"); // sky blue
assert.equal(rendered.HUL, "#F5A12D"); // amber
assert.equal(rendered.COV, "#59CBE8"); // sky blue
assert.equal(rendered.FUL, "#000000"); // black
assert.equal(rendered.LEE, "#1D428A"); // navy
assert.equal(getTeam("ZZZ").name, "ZZZ"); // unknown code: no crash

// --- mock data ---
const matchweeks = read("matchweeks.json");
let previousTable = null;
assert.deepEqual(matchweeks.map((m) => [m.matchweek, m.status]), [[6, "complete"], [7, "complete"], [8, "upcoming"]]);

for (const { matchweek, status, matchesLockedAt, tableLockedAt } of matchweeks) {
  const matches = read(`mw-${matchweek}/matches.json`);
  const snapshot = read(`mw-${matchweek}/snapshot.json`);
  const at = `MW${matchweek}`;

  assert.equal(matches.length, 10, at);
  assert.deepEqual(matches.flatMap((m) => [m.home, m.away]).sort(), [...codes].sort(), at);
  for (const m of matches) {
    const p = m.prediction;
    assert.ok(near(p.homeWin + p.draw + p.awayWin, 1), `${at} ${m.id} probabilities`);
    assert.equal(p.lockedAt, matchesLockedAt);
    assert.ok(new Date(p.lockedAt) < new Date(m.kickoff), `${at} ${m.id} locked before kickoff`);
    const played = status === "complete";
    assert.equal(m.result !== null, played, `${at} ${m.id} result`);
    assert.equal(m.market !== null, played);
    assert.equal(m.scores !== null, played);
    if (m.market) assert.ok(near(m.market.pHome + m.market.pDraw + m.market.pAway, 1), `${at} ${m.id} market`);
  }

  assert.equal(snapshot.matchweek, matchweek);
  assert.equal(snapshot.lockedAt, tableLockedAt);
  for (const table of [snapshot.predictedTable, snapshot.actualTable]) {
    assert.deepEqual(table.map((r) => r.teamCode).sort(), [...codes].sort(), at);
  }
  snapshot.predictedTable.forEach((row, i) => {
    assert.equal(row.predictedPosition, i + 1);
    assert.equal(row.positionProbabilities.length, 20);
    assert.ok(near(row.positionProbabilities.reduce((a, b) => a + b), 1, 1e-6), `${at} ${row.teamCode} positions`);
    assert.equal(row.pTitle, row.positionProbabilities[0]);
  });
  // Each position goes to exactly one team, so every column sums to 1 too.
  for (let k = 0; k < 20; k++) {
    const column = snapshot.predictedTable.reduce((sum, row) => sum + row.positionProbabilities[k], 0);
    assert.ok(near(column, 1, 1e-6), `${at} position ${k + 1} sums to ${column}`);
  }
  // Forecasts move between rounds: at least 3 teams shift 2+ predicted places.
  if (previousTable) {
    const before = Object.fromEntries(previousTable.map((row) => [row.teamCode, row.predictedPosition]));
    const movers = snapshot.predictedTable.filter((row) => Math.abs(row.predictedPosition - before[row.teamCode]) >= 2);
    assert.ok(movers.length >= 3, `${at} only ${movers.length} teams moved 2+ places`);
  }
  previousTable = snapshot.predictedTable;
  let goalsFor = 0;
  let goalsAgainst = 0;
  snapshot.actualTable.forEach((row, i) => {
    assert.equal(row.position, i + 1);
    assert.equal(row.played, row.won + row.drawn + row.lost, `${at} ${row.teamCode} played`);
    assert.equal(row.points, 3 * row.won + row.drawn, `${at} ${row.teamCode} points`);
    if (i > 0) assert.ok(row.points <= snapshot.actualTable[i - 1].points, `${at} table order`);
    goalsFor += row.goalsFor;
    goalsAgainst += row.goalsAgainst;
  });
  assert.equal(goalsFor, goalsAgainst, `${at} goals`);
}

console.log("check passed");
