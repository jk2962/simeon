import { getMatches, requestTime } from "@/lib/api";
import { ukDateTime, ukDay } from "@/lib/format";
import { summarize } from "@/lib/matches";
import type { Match } from "@/lib/types";
import { ErrorNote } from "./ErrorNote";
import { MatchCard } from "./MatchCard";

// The Matches page body: the week in one line, then every fixture by UK date.
export async function MatchesView({ matchweek, weekLockedAt }: { matchweek: number; weekLockedAt: string | null }) {
  const [result, now] = await Promise.all([getMatches(matchweek), requestTime()]);

  if (!result.ok) {
    return (
      <>
        <h1 className="text-3xl font-bold">Match forecasts</h1>
        <div className="mt-6">
          <ErrorNote message={result.error} />
        </div>
      </>
    );
  }

  const matches = [...result.data].sort((a, b) => Date.parse(a.kickoff) - Date.parse(b.kickoff));
  const summary = summarize(matches);
  // The week's lock, or the earliest match lock if the week has none recorded.
  const lockedAt = weekLockedAt ?? matches.map((m) => m.prediction.lockedAt).sort()[0];
  const days = new Map<string, Match[]>();
  for (const match of matches) days.set(ukDay(match.kickoff), [...(days.get(ukDay(match.kickoff)) ?? []), match]);

  return (
    <>
      <h1 className="text-3xl font-bold">Match forecasts</h1>
      {lockedAt && (
        <p className="mt-1 text-muted">
          Forecasts locked <time dateTime={lockedAt}>{ukDateTime(lockedAt)}</time>.
          {summary.played === 0 ? " Results appear after each match." : ` ${summary.played} of ${summary.total} played.`}
        </p>
      )}
      {summary.rps && (
        <>
          <p className="mt-3 text-lg font-semibold">
            Model {summary.rps.model.toFixed(3)} · Market {summary.rps.market.toFixed(3)} · Naive {summary.rps.naive.toFixed(3)}
          </p>
          <p className="text-sm text-muted">
            RPS: lower is better. One week is a small sample.
            {summary.rps.matches < summary.played && ` Averaged over ${summary.rps.matches} of ${summary.played} played matches.`}
          </p>
        </>
      )}
      {matches.length === 0 && <p className="mt-6 text-muted">No fixtures are listed for this matchweek yet.</p>}

      {[...days].map(([day, dayMatches]) => (
        <section key={day} className="mt-8">
          <h2 className="text-lg font-bold">{day}</h2>
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            {dayMatches.map((match) => (
              <MatchCard key={match.id} match={match} weekLockedAt={weekLockedAt} now={now} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
