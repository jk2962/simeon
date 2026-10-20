import { Suspense } from "react";
import { redirect } from "next/navigation";
import { ErrorNote } from "@/components/ErrorNote";
import { Header, SHELL } from "@/components/Header";
import { getMatchweeks } from "@/lib/api";

export default function Home() {
  return (
    <Suspense fallback={<Header />}>
      <Latest />
    </Suspense>
  );
}

// Sends the visitor to the first matchweek, to read the season from the start.
async function Latest() {
  const result = await getMatchweeks();
  const weeks = result.ok
    ? result.data.filter((m) => m?.matchesLockedAt || m?.tableLockedAt || m?.retrospective).map((m) => m.matchweek)
    : [];
  if (weeks.length > 0) redirect(`/mw/${Math.min(...weeks)}`);

  return (
    <>
      <Header />
      <main className={`${SHELL} py-8`}>
        <ErrorNote message={result.ok ? "No matchweek has locked predictions yet." : result.error} />
      </main>
    </>
  );
}
