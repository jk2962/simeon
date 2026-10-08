import { Suspense, type ReactNode } from "react";
import { notFound } from "next/navigation";
import { getMatchweeks } from "@/lib/api";
import type { MatchweekSummary } from "@/lib/types";
import { ErrorNote } from "./ErrorNote";
import { Header, SHELL, type Tab } from "./Header";

type Props = {
  params: Promise<{ n: string }>;
  tab: Tab;
  // The page body for a matchweek that exists.
  render: (matchweek: number, matchweeks: MatchweekSummary[]) => ReactNode;
};

// The shared frame of both matchweek pages: header, then the page body.
//
// Whether the matchweek exists is settled here, before any Suspense boundary,
// so an unknown one is a real HTTP 404 (see app/not-found.tsx). Once a
// boundary starts streaming the status is already 200. The pages opt out of
// the static shell for this (`instant = false`).
export async function MatchweekPage({ params, tab, render }: Props) {
  const { n: raw } = await params;
  if (!/^\d{1,2}$/.test(raw)) notFound();
  const n = Number(raw);

  const result = await getMatchweeks();
  const matchweeks = result.ok
    ? result.data.filter((m) => Number.isInteger(m?.matchweek)).sort((a, b) => a.matchweek - b.matchweek)
    : [];
  // Without the list a matchweek cannot be ruled out, so it gets the error note instead.
  if (result.ok && !matchweeks.some((m) => m.matchweek === n)) notFound();

  return (
    <>
      <Header current={n} tab={tab} matchweeks={matchweeks.map((m) => m.matchweek)} />
      <main className={`${SHELL} py-8`}>
        {result.ok ? <Suspense>{render(n, matchweeks)}</Suspense> : <ErrorNote message={result.error} />}
      </main>
    </>
  );
}
