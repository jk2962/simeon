import { chipColor, getTeam } from "@/config/teams";
import { percent, ukDateTime, ukTime } from "@/lib/format";
import { OUTCOMES, biggestGap, lockedInTime, marketProbs, modelProbs, outcomeOf, type Outcome } from "@/lib/matches";
import type { Match, TeamCode } from "@/lib/types";
import { TeamChip } from "./TeamChip";

// Chip and name. Below 640px the short name sits under the chip, so two long
// names still fit either side of the score.
function Side({ code, end = false }: { code: TeamCode; end?: boolean }) {
  const team = getTeam(code);
  return (
    <div className={`flex min-w-0 flex-col gap-x-3 gap-y-1 sm:flex-row sm:items-center ${end ? "items-end text-right sm:justify-end" : "items-start"}`}>
      <TeamChip code={code} />
      <span className="hidden sm:inline">{team.name}</span>
      <span className="text-sm sm:hidden">{team.shortName}</span>
    </div>
  );
}

// Why this match's lock is worth a line, or null for an ordinary lock.
function lockNote(match: Match, weekLockedAt: string | null): string | null {
  const { lockedAt, lockReason } = match.prediction;
  if (lockReason === "rescheduled") return `Locked separately (rescheduled) · ${ukDateTime(lockedAt)}`;
  if (lockReason === "missed-lock") return `Locked late · ${ukDateTime(lockedAt)}`;
  if (weekLockedAt && lockedAt !== weekLockedAt) return `Locked separately · ${ukDateTime(lockedAt)}`;
  return null;
}

// One fixture: the locked forecast, the market's view, and the result once played.
// `now` is the request time, used only to tell "not yet played" from "result pending".
export function MatchCard({ match, weekLockedAt, now }: { match: Match; weekLockedAt: string | null; now: number }) {
  const { home, away, result } = match;
  const model = modelProbs(match);
  const market = marketProbs(match);
  const name: Record<Outcome, string> = { home, draw: "Draw", away };
  const gap = biggestGap(match);
  const gapName = gap && (gap === "draw" ? "the draw" : `${name[gap]} win`);
  const outcome = result && outcomeOf(result);
  const fill: Record<Outcome, string | undefined> = {
    home: chipColor(getTeam(home)).hex,
    draw: undefined, // neutral, from the class below
    away: chipColor(getTeam(away)).hex,
  };
  const forecast = OUTCOMES.map((o) => `${name[o]} ${percent(model[o])}`);
  const inTime = lockedInTime(match);
  const note = lockNote(match, weekLockedAt);
  const likely = match.prediction.likelyScore;

  return (
    <article aria-label={`${getTeam(home).name} v ${getTeam(away).name}`} className="border border-rule bg-surface p-4">
      <p className="text-sm text-muted">
        <time dateTime={match.kickoff}>{ukTime(match.kickoff)}</time>
      </p>

      <div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <Side code={home} />
        {/* The actual score. Blank until the match is played, never 0 – 0. */}
        <div className="text-center">
          {result ? (
            <p className="text-2xl font-bold" aria-label={`${result.home} to ${result.away}`}>
              {result.home} – {result.away}
            </p>
          ) : (
            <p className="text-2xl font-bold text-muted" aria-label="No score yet">
              – : –
            </p>
          )}
          <p className="text-xs text-muted">
            {result ? "Full time" : Date.parse(match.kickoff) <= now ? "Result pending" : "Not played yet"}
          </p>
        </div>
        <Side code={away} end />
      </div>
      <p className="mt-2 text-center text-sm text-muted">
        Most likely score before kickoff{" "}
        <span className="font-semibold text-ink">
          {likely.home} – {likely.away}
        </span>{" "}
        ({percent(likely.probability)})
      </p>

      {/* Widths are the three probabilities. The gap keeps two teams of one color apart. */}
      <div role="img" aria-label={`Model: ${forecast.join(", ")}`} className="mt-4 flex h-3 gap-[2px]">
        {OUTCOMES.map((o) => (
          <span key={o} className="bg-rule" style={{ flexGrow: model[o], flexBasis: 0, backgroundColor: fill[o] }} />
        ))}
      </div>
      <p className="mt-1.5 flex justify-between gap-2 text-sm font-medium">
        {forecast.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </p>

      <div className="mt-3 space-y-1 text-sm">
        {market && (
          <p className="text-muted">
            Market {OUTCOMES.map((o) => `${name[o]} ${percent(market[o])}`).join(" · ")}
            {gapName && ` · model differs most on ${gapName}`}
          </p>
        )}
        <p>
          Expected goals {match.prediction.expectedGoals.home.toFixed(2)} – {match.prediction.expectedGoals.away.toFixed(2)}
        </p>
        {outcome && (
          <p>
            Model gave this result {percent(model[outcome])}
            {market && ` · Market ${percent(market[outcome])}`}
          </p>
        )}
        {!inTime && <p className="font-medium">Locked after kickoff — not counted</p>}
        {inTime && note && <p className="text-muted">{note}</p>}
      </div>

      {match.prediction.analysis && (
        <p className="mt-3 max-w-prose border-t border-rule pt-3 text-sm leading-relaxed">{match.prediction.analysis}</p>
      )}
    </article>
  );
}
