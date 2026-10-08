import { Suspense, type ReactNode } from "react";
import Link from "next/link";
import { getMatchweeks } from "@/lib/api";
import { utcDate } from "@/lib/format";
import type { MatchweekSummary } from "@/lib/types";
import { ErrorNote } from "./ErrorNote";
import { Header, SHELL, type Tab } from "./Header";

const TITLES: Record<Tab, string> = { snapshot: "Snapshot", matches: "Matches" };

type Props = {
  params: Promise<{ n: string }>;
  tab: Tab;
  // The page body for a matchweek that exists. Without it the page shows only
  // its title and the matchweek number.
  render?: (matchweek: number, matchweeks: MatchweekSummary[]) => ReactNode;
};

// The shared frame of both matchweek pages: header, then the page body.
export function MatchweekPage(props: Props) {
  return (
    <Suspense fallback={<Header />}>
      <Content {...props} />
    </Suspense>
  );
}

const lockOf = (m: MatchweekSummary) => [m.matchesLockedAt, m.tableLockedAt].filter((t) => t !== null).sort()[0];

// Shown inside the shell for a matchweek that has no forecast.
function NotFound({ matchweek, matchweeks }: { matchweek: number; matchweeks: MatchweekSummary[] }) {
  const first = matchweeks.find((m) => lockOf(m));
  const latest = matchweeks.findLast((m) => lockOf(m));
  const early = first && matchweek < first.matchweek;
  const target = early ? first : latest;
  return (
    <>
      <Header />
      <main className={`${SHELL} py-8`}>
        <h1 className="text-3xl font-bold">No forecast here</h1>
        <p className="mt-2 max-w-prose text-muted">
          {early
            ? `Forecasts start at MW${first.matchweek}. Locking began ${utcDate(lockOf(first)!)}.`
            : "There is no forecast for that matchweek."}
        </p>
        <p className="mt-6">
          <Link href={target ? `/mw/${target.matchweek}` : "/"} className="font-medium underline underline-offset-4">
            {target ? `Go to MW${target.matchweek}` : "Go to the latest matchweek"}
          </Link>
        </p>
      </main>
    </>
  );
}

async function Content({ params, tab, render }: Props) {
  const { n: raw } = await params;
  const n = /^\d{1,2}$/.test(raw) ? Number(raw) : NaN;

  const result = await getMatchweeks();
  const matchweeks = result.ok
    ? result.data.filter((m) => Number.isInteger(m?.matchweek)).sort((a, b) => a.matchweek - b.matchweek)
    : [];
  const exists = matchweeks.some((m) => m.matchweek === n);
  // Without the list a numbered matchweek cannot be ruled out, so it gets the error note below.
  if (Number.isNaN(n) || (result.ok && !exists)) return <NotFound matchweek={n} matchweeks={matchweeks} />;

  return (
    <>
      <Header current={n} tab={tab} matchweeks={matchweeks.map((m) => m.matchweek)} />
      <main className={`${SHELL} py-8`}>
        {result.ok && render ? (
          render(n, matchweeks)
        ) : (
          <>
            <h1 className="text-3xl font-bold">{TITLES[tab]}</h1>
            <p className="mt-1 text-muted">Matchweek {n}</p>
          </>
        )}
        {!result.ok && (
          <div className="mt-6">
            <ErrorNote message={result.error} />
          </div>
        )}
      </main>
    </>
  );
}
