import { readFile } from "node:fs/promises";
import path from "node:path";
import { io } from "next/cache";
import type { Match, MatchweekSummary, Snapshot } from "./types";

// Every fetcher resolves to a Result and never throws, so a page can render
// an inline error instead of crashing.
export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

// Mocks stand in for a missing backend during development only. In
// production a missing API_BASE_URL is an error, never a silent fallback.
export function usingMocks(): boolean {
  return !process.env.API_BASE_URL && process.env.NODE_ENV !== "production";
}

// The time of the request. Read here, after io(), so it is never baked into the build.
export async function requestTime(): Promise<number> {
  await io();
  return Date.now();
}

async function load<T>(apiPath: string, isValid: (data: unknown) => boolean): Promise<Result<T>> {
  await io(); // request time only: nothing here is baked into the build
  try {
    let data: unknown;
    if (usingMocks()) {
      const file = path.join(process.cwd(), "mocks", `${apiPath.replace("/matchweeks/", "mw-")}.json`);
      data = JSON.parse(await readFile(file, "utf8"));
    } else {
      const base = process.env.API_BASE_URL;
      if (!base) return { ok: false, error: "API_BASE_URL is not set, so there is no data to show." };
      const response = await fetch(base.replace(/\/$/, "") + apiPath, { cache: "no-store" });
      if (!response.ok) return { ok: false, error: `The data service answered with status ${response.status}.` };
      data = await response.json();
    }
    if (!isValid(data)) return { ok: false, error: "The data service sent a response in an unexpected shape." };
    return { ok: true, data: data as T };
  } catch {
    return { ok: false, error: "The data could not be loaded. Try again shortly." };
  }
}

const isObject = (data: unknown): data is Record<string, unknown> =>
  typeof data === "object" && data !== null && !Array.isArray(data);
const isRows = (data: unknown, numbers: string[]): boolean =>
  Array.isArray(data) &&
  data.every((row) => isObject(row) && typeof row.teamCode === "string" && numbers.every((key) => Number.isFinite(row[key])));

// Every field the Snapshot page reads, so a malformed response becomes an
// error note instead of a crash.
function isSnapshot(data: unknown): boolean {
  return (
    isObject(data) &&
    typeof data.lockedAt === "string" &&
    typeof data.modelVersion === "string" &&
    isRows(data.predictedTable, ["predictedPosition", "expectedPoints", "pTitle", "pTop4", "pRelegation"]) &&
    (data.predictedTable as Record<string, unknown>[]).every(
      (row) => Array.isArray(row.positionProbabilities) && row.positionProbabilities.every(Number.isFinite),
    ) &&
    isRows(data.actualTable, ["position", "points"])
  );
}

const hasNumbers = (data: unknown, keys: string[]): boolean => isObject(data) && keys.every((key) => Number.isFinite(data[key]));
const nullOr = (data: unknown, keys: string[]): boolean => data === null || hasNumbers(data, keys);

// Every field the Matches page reads.
function isMatches(data: unknown): boolean {
  return (
    Array.isArray(data) &&
    data.every((match) => {
      if (!isObject(match) || !isObject(match.prediction)) return false;
      const { prediction } = match;
      return (
        ["id", "kickoff", "home", "away"].every((key) => typeof match[key] === "string") &&
        hasNumbers(prediction, ["homeWin", "draw", "awayWin"]) &&
        hasNumbers(prediction.expectedGoals, ["home", "away"]) &&
        (prediction.analysis === null || typeof prediction.analysis === "string") &&
        typeof prediction.lockedAt === "string" &&
        (prediction.lockReason === null || typeof prediction.lockReason === "string") &&
        nullOr(match.result, ["home", "away"]) &&
        nullOr(match.market, ["pHome", "pDraw", "pAway"]) &&
        nullOr(match.scores, ["rpsModel", "rpsNaive", "rpsBookmaker"])
      );
    })
  );
}

export function getMatchweeks(): Promise<Result<MatchweekSummary[]>> {
  return load("/matchweeks", Array.isArray);
}

export function getSnapshot(matchweek: number): Promise<Result<Snapshot>> {
  return load(`/matchweeks/${matchweek}/snapshot`, isSnapshot);
}

export function getMatches(matchweek: number): Promise<Result<Match[]>> {
  return load(`/matchweeks/${matchweek}/matches`, isMatches);
}
