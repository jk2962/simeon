import type { Match } from "./types";

export type Outcome = "home" | "draw" | "away";
export const OUTCOMES: Outcome[] = ["home", "draw", "away"];

// Model and market differ "most" on an outcome only from this many points.
const NOTABLE_GAP = 0.1;

export function outcomeOf(result: { home: number; away: number }): Outcome {
  return result.home > result.away ? "home" : result.home === result.away ? "draw" : "away";
}

export function modelProbs(match: Match): Record<Outcome, number> {
  const { homeWin, draw, awayWin } = match.prediction;
  return { home: homeWin, draw, away: awayWin };
}

export function marketProbs(match: Match): Record<Outcome, number> | null {
  return match.market && { home: match.market.pHome, draw: match.market.pDraw, away: match.market.pAway };
}

// A forecast only counts if it was locked before the match kicked off.
export function lockedInTime(match: Match): boolean {
  return Date.parse(match.prediction.lockedAt) < Date.parse(match.kickoff);
}

// The outcome where model and market are furthest apart, if by 10 points or more.
export function biggestGap(match: Match): Outcome | null {
  const market = marketProbs(match);
  if (!market) return null;
  const model = modelProbs(match);
  const gap = (o: Outcome) => Math.round(Math.abs(model[o] - market[o]) * 1000) / 1000;
  const widest = OUTCOMES.reduce((a, b) => (gap(b) > gap(a) ? b : a));
  return gap(widest) >= NOTABLE_GAP ? widest : null;
}

export type WeekSummary = {
  total: number;
  played: number;
  // Mean RPS over the matches that are played, scored and were locked in
  // time. Null when there are none.
  rps: { model: number; market: number; naive: number; matches: number } | null;
};

export function summarize(matches: Match[]): WeekSummary {
  const scored = matches.flatMap((m) => (m.result && m.scores && lockedInTime(m) ? [m.scores] : []));
  const mean = (pick: (s: (typeof scored)[number]) => number) => scored.reduce((sum, s) => sum + pick(s), 0) / scored.length;
  return {
    total: matches.length,
    played: matches.filter((m) => m.result).length,
    rps: scored.length
      ? {
          model: mean((s) => s.rpsModel),
          market: mean((s) => s.rpsBookmaker),
          naive: mean((s) => s.rpsNaive),
          matches: scored.length,
        }
      : null,
  };
}
