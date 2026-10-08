import type { TeamCode } from "@/lib/types";

export interface Team {
  name: string;
  shortName: string;
  // Spelled exactly as the `canonical` column of data/teams.csv.
  canonicalName: string;
  primary: string;
  secondary: string;
}

// The canonical-name→code mapping will move to a `code` column in
// data/teams.csv when the adapter is built; teams.ts then holds colors only.
//
// The 20 clubs of the 2026-27 season. Team colors are for chips only, never text.
export const TEAMS: Record<TeamCode, Team> = {
  ARS: { name: "Arsenal", shortName: "Arsenal", canonicalName: "Arsenal", primary: "#EF0107", secondary: "#FFFFFF" },
  AVL: { name: "Aston Villa", shortName: "Aston Villa", canonicalName: "Aston Villa", primary: "#670E36", secondary: "#95BFE5" },
  BOU: { name: "AFC Bournemouth", shortName: "Bournemouth", canonicalName: "Bournemouth", primary: "#DA291C", secondary: "#000000" },
  BRE: { name: "Brentford", shortName: "Brentford", canonicalName: "Brentford", primary: "#E30613", secondary: "#FFFFFF" }, // VERIFY primary
  BHA: { name: "Brighton & Hove Albion", shortName: "Brighton", canonicalName: "Brighton", primary: "#0057B8", secondary: "#FFFFFF" },
  CHE: { name: "Chelsea", shortName: "Chelsea", canonicalName: "Chelsea", primary: "#034694", secondary: "#FFFFFF" },
  COV: { name: "Coventry City", shortName: "Coventry", canonicalName: "Coventry", primary: "#59CBE8", secondary: "#FFFFFF" }, // VERIFY primary
  CRY: { name: "Crystal Palace", shortName: "Crystal Palace", canonicalName: "Crystal Palace", primary: "#1B458F", secondary: "#C4122E" },
  EVE: { name: "Everton", shortName: "Everton", canonicalName: "Everton", primary: "#003399", secondary: "#FFFFFF" },
  FUL: { name: "Fulham", shortName: "Fulham", canonicalName: "Fulham", primary: "#FFFFFF", secondary: "#000000" },
  HUL: { name: "Hull City", shortName: "Hull", canonicalName: "Hull", primary: "#F5A12D", secondary: "#000000" }, // VERIFY primary
  IPS: { name: "Ipswich Town", shortName: "Ipswich", canonicalName: "Ipswich", primary: "#0044A9", secondary: "#FFFFFF" }, // VERIFY primary
  LEE: { name: "Leeds United", shortName: "Leeds", canonicalName: "Leeds", primary: "#FFFFFF", secondary: "#1D428A" },
  LIV: { name: "Liverpool", shortName: "Liverpool", canonicalName: "Liverpool", primary: "#C8102E", secondary: "#00B2A9" },
  MCI: { name: "Manchester City", shortName: "Man City", canonicalName: "Man City", primary: "#6CABDD", secondary: "#1C2C5B" },
  MUN: { name: "Manchester United", shortName: "Man United", canonicalName: "Man United", primary: "#DA291C", secondary: "#FBE122" },
  NEW: { name: "Newcastle United", shortName: "Newcastle", canonicalName: "Newcastle", primary: "#241F20", secondary: "#FFFFFF" },
  NFO: { name: "Nottingham Forest", shortName: "Nott'm Forest", canonicalName: "Nottingham Forest", primary: "#DD0000", secondary: "#FFFFFF" }, // VERIFY primary
  SUN: { name: "Sunderland", shortName: "Sunderland", canonicalName: "Sunderland", primary: "#EB172B", secondary: "#FFFFFF" }, // VERIFY primary
  TOT: { name: "Tottenham Hotspur", shortName: "Tottenham", canonicalName: "Tottenham", primary: "#132257", secondary: "#FFFFFF" },
};

const NEUTRAL = "#8C8C8C";

// Unknown codes get a neutral gray team under the code they came with.
export function getTeam(code: TeamCode): Team {
  return TEAMS[code] ?? { name: code, shortName: code, canonicalName: code, primary: NEUTRAL, secondary: NEUTRAL };
}

// Above this relative luminance a color counts as white or near-white.
const NEAR_WHITE = 0.85;

// WCAG relative luminance of a #RRGGBB color, 0 (black) to 1 (white).
export function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const channel = parseInt(hex.slice(i, i + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Which color the chip shows: the primary, unless it is white or near-white.
// Pale colors stay visible through the chip's outline.
export function chipColor(team: Team): { hex: string; variant: "primary" | "secondary" } {
  return luminance(team.primary) > NEAR_WHITE
    ? { hex: team.secondary, variant: "secondary" }
    : { hex: team.primary, variant: "primary" };
}
