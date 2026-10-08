// Self-check, no framework: `npm run check`. Fails loudly if the mock data is
// internally inconsistent or the chip color rule breaks.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { TEAMS, chipColor, contrast, fillOnWhite, getTeam, luminance, textOn } from "../src/config/teams.ts";
import { percent, utcDate, utcDateTime } from "../src/lib/format.ts";

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

// --- display formats ---
assert.deepEqual([0, 0.0049, 0.005, 0.0149, 0.4411, 0.9949, 0.995, 0.9951, 1].map(percent),
  ["<1%", "<1%", "1%", "1%", "44%", "99%", "99%", ">99%", ">99%"]);
assert.equal(utcDateTime("2026-10-07T22:35:46Z"), "Oct 7, 22:35 UTC");
assert.equal(utcDateTime("2026-10-08T00:05:00Z"), "Oct 8, 00:05 UTC");
assert.equal(utcDate("2026-10-07T22:35:46Z"), "Oct 7, 2026");
assert.equal(fillOnWhite("#000000", 0.5), "#808080");
assert.equal(fillOnWhite("#EF0107", 1), "#EF0107");
assert.equal(textOn("#FFFFFF"), "#141414");
assert.equal(textOn("#132257"), "#FFFFFF");
assert.equal(textOn("#EF0107"), "#000000"); // neither ink nor white reaches 4.5:1

// The standings after adding one round of results to a table.
function addRound(table, matches) {
  const rows = Object.fromEntries(table.map((row) => [row.teamCode, { ...row }]));
  for (const { home, away, result } of matches) {
    for (const [code, scored, conceded] of [[home, result.home, result.away], [away, result.away, result.home]]) {
      const row = rows[code];
      row.played += 1;
      row.goalsFor += scored;
      row.goalsAgainst += conceded;
      row[scored > conceded ? "won" : scored === conceded ? "drawn" : "lost"] += 1;
      row.points += scored > conceded ? 3 : scored === conceded ? 1 : 0;
    }
  }
  return rows;
}
const rank = (row) => [row.points, row.goalsFor - row.goalsAgainst, row.goalsFor];
let previousRound = null; // { snapshot, matches } of the matchweek before

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

  // Grid text: every written percentage has at least 4.5:1 against its cell.
  const max = Math.max(...snapshot.predictedTable.flatMap((row) => row.positionProbabilities));
  for (const row of snapshot.predictedTable) {
    row.positionProbabilities.forEach((p, k) => {
      if (p < 0.1) return;
      const fill = fillOnWhite(chipColor(getTeam(row.teamCode)).hex, p / max);
      const ratio = contrast(textOn(fill), fill);
      assert.ok(ratio >= 4.5, `${at} ${row.teamCode} position ${k + 1}: text contrast ${ratio.toFixed(2)} on ${fill}`);
    });
  }

  // actualTable is the standings the forecast was locked on: after round N-1.
  for (const row of snapshot.actualTable) assert.equal(row.played, matchweek - 1, `${at} ${row.teamCode} played`);
  snapshot.actualTable.forEach((row, i) => {
    if (i === 0) return;
    const [above, below] = [rank(snapshot.actualTable[i - 1]), rank(row)];
    const firstDifference = above.findIndex((value, j) => value !== below[j]);
    assert.ok(firstDifference === -1 || above[firstDifference] > below[firstDifference], `${at} order at position ${i + 1}`);
  });
  if (previousRound) {
    // Equal to last week's standings plus last week's results, field for field.
    const expected = addRound(previousRound.snapshot.actualTable, previousRound.matches);
    for (const row of snapshot.actualTable) {
      assert.deepEqual({ ...row, position: 0 }, { ...expected[row.teamCode], position: 0 }, `${at} ${row.teamCode} standings`);
    }
  }
  previousRound = { snapshot, matches };
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
