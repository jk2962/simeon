import { Suspense } from "react";
import Link from "next/link";
import { Header, SHELL } from "@/components/Header";
import { getMatchweeks } from "@/lib/api";
import { ukDate } from "@/lib/format";
import type { MatchweekSummary } from "@/lib/types";

const LINK = "font-medium underline underline-offset-4";

const lockOf = (m: MatchweekSummary) => [m.matchesLockedAt, m.tableLockedAt].filter((t) => t !== null).sort()[0];

// Where the forecasts are, for someone who asked for one that does not exist.
async function Pointers() {
  const result = await getMatchweeks();
  const locked = result.ok
    ? result.data.filter((m) => Number.isInteger(m?.matchweek) && lockOf(m)).sort((a, b) => a.matchweek - b.matchweek)
    : [];
  const first = locked.at(0);
  const latest = locked.at(-1);
  if (!first || !latest) {
    return (
      <p className="mt-6">
        <Link href="/" className={LINK}>
          Go to the latest matchweek
        </Link>
      </p>
    );
  }
  return (
    <>
      <p className="mt-2 max-w-prose text-muted">
        Forecasts start at MW{first.matchweek}. Locking began {ukDate(lockOf(first)!)}.
      </p>
      <p className="mt-6 flex gap-6">
        <Link href={`/mw/${first.matchweek}`} className={LINK}>
          Go to MW{first.matchweek}
        </Link>
        {latest !== first && (
          <Link href={`/mw/${latest.matchweek}`} className={LINK}>
            Latest: MW{latest.matchweek}
          </Link>
        )}
      </p>
    </>
  );
}

// Every unknown address, including matchweeks with no forecast. Served with HTTP 404.
export default function NotFound() {
  return (
    <>
      <Header />
      <main className={`${SHELL} py-8`}>
        <h1 className="text-3xl font-bold">No forecast here</h1>
        <p className="mt-2 max-w-prose text-muted">There is nothing at this address.</p>
        <Suspense>
          <Pointers />
        </Suspense>
      </main>
    </>
  );
}
