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

// Sends the visitor to the highest matchweek that has a lock.
async function Latest() {
  const result = await getMatchweeks();
  const locked = result.ok
    ? result.data.filter((m) => m?.matchesLockedAt || m?.tableLockedAt).map((m) => m.matchweek)
    : [];
  if (locked.length > 0) redirect(`/mw/${Math.max(...locked)}`);

  return (
    <>
      <Header />
      <main className={`${SHELL} py-8`}>
        <ErrorNote message={result.ok ? "No matchweek has locked predictions yet." : result.error} />
      </main>
    </>
  );
}
