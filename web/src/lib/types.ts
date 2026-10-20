// The API contract. The backend adapter will be built to match these types.
// Field sources in the Python pipeline are noted where the names differ.

export type TeamCode = string; // e.g. "ARS"

export interface MatchweekSummary {
  season: string; // "2026-27"
  matchweek: number; // 1–38 (pipeline: matchday)
  status: "upcoming" | "in_progress" | "complete";
  // Forecast after the fact, on data before the week's first kickoff
  // (pipeline.retro). Never locked: both timestamps are null.
  retrospective: boolean;
  // Match forecasts and the season table are locked separately, so each has
  // its own timestamp. Null until that lock exists.
  matchesLockedAt: string | null; // ISO 8601
  tableLockedAt: string | null; // ISO 8601
}

export interface PredictedRow {
  teamCode: TeamCode;
  predictedPosition: number; // rank by expectedPoints
  expectedPoints: number; // one decimal (pipeline: exp_points)
  positionProbabilities: number[]; // length 20, index 0 = 1st place (pos_1..pos_20)
  pTitle: number;
  pTop4: number;
  pRelegation: number;
}

export interface ActualRow {
  teamCode: TeamCode;
  position: number;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  goalsFor: number;
  goalsAgainst: number;
  points: number;
}

export interface Snapshot {
  matchweek: number;
  lockedAt: string; // ISO 8601 (pipeline: generated_at_utc of table-round-NN.csv)
  dataThrough: string; // ISO 8601, kickoff of the latest match the model saw
  modelVersion: string; // short commit hash
  predictedTable: PredictedRow[];
  /**
   * The standings at the moment the forecast was locked, that is after round
   * `matchweek - 1`. The forecast and this table describe the same state of
   * information. The results of round `matchweek` appear on the Matches page
   * and in the next snapshot.
   */
  actualTable: ActualRow[];
}

export interface Match {
  id: string;
  kickoff: string; // ISO 8601
  home: TeamCode;
  away: TeamCode;
  prediction: {
    homeWin: number; // homeWin + draw + awayWin = 1
    draw: number;
    awayWin: number;
    expectedGoals: { home: number; away: number };
    // The single most likely scoreline and its probability. It follows from
    // expectedGoals alone, is usually only 8-15% likely, and can disagree
    // with the most likely outcome.
    likelyScore: { home: number; away: number; probability: number };
    analysis: string | null; // plain text
    // Per match, not per matchweek: a rescheduled match is locked on its own.
    // For a retrospective forecast, when it was generated (after kickoff).
    lockedAt: string; // ISO 8601
    lockReason: "missed-lock" | "rescheduled" | "retrospective" | null;
  };
  result: { home: number; away: number } | null;
  // Both null until the match is played and scored.
  market: { pHome: number; pDraw: number; pAway: number } | null; // book_*
  scores: { rpsModel: number; rpsNaive: number; rpsBookmaker: number } | null; // rps_*
}
