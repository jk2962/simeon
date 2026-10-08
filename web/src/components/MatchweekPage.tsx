import { Suspense } from "react";
import { notFound } from "next/navigation";
import { getMatchweeks } from "@/lib/api";
import { ErrorNote } from "./ErrorNote";
import { Header, SHELL, type Tab } from "./Header";

const TITLES: Record<Tab, string> = { snapshot: "Snapshot", matches: "Matches" };

// The shared frame of both matchweek pages: header, title, matchweek number.
export function MatchweekPage({ params, tab }: { params: Promise<{ n: string }>; tab: Tab }) {
  return (
    <Suspense fallback={<Header />}>
      <Content params={params} tab={tab} />
    </Suspense>
  );
}

async function Content({ params, tab }: { params: Promise<{ n: string }>; tab: Tab }) {
  const { n: raw } = await params;
  const n = Number(raw);
  if (!/^\d{1,2}$/.test(raw) || n < 1 || n > 38) notFound();

  const result = await getMatchweeks();
  const matchweeks = result.ok
    ? result.data.map((m) => m?.matchweek).filter((m) => Number.isInteger(m))
    : [];
  if (result.ok && !matchweeks.includes(n)) notFound();

  return (
    <>
      <Header current={n} tab={tab} matchweeks={matchweeks} />
      <main className={`${SHELL} py-8`}>
        <h1 className="text-3xl font-bold">{TITLES[tab]}</h1>
        <p className="mt-1 text-muted">Matchweek {n}</p>
        {!result.ok && (
          <div className="mt-6">
            <ErrorNote message={result.error} />
          </div>
        )}
      </main>
    </>
  );
}
