import { MatchweekPage } from "@/components/MatchweekPage";
import { SnapshotView } from "@/components/SnapshotView";

// The page waits for the matchweek list so an unknown matchweek can be a real 404.
export const instant = false;

export default function SnapshotPage({ params }: PageProps<"/mw/[n]">) {
  return (
    <MatchweekPage
      params={params}
      tab="snapshot"
      render={(matchweek, matchweeks) =>
        matchweeks.find((m) => m.matchweek === matchweek)?.tableLockedAt === null ? (
          <>
            <h1 className="text-3xl font-bold">Season forecast</h1>
            <p className="mt-3 text-muted">No season forecast was locked before MW{matchweek}. See the Matches tab.</p>
          </>
        ) : (
          <SnapshotView
            matchweek={matchweek}
            hasPrevious={matchweeks.some((m) => m.matchweek === matchweek - 1 && m.tableLockedAt)}
          />
        )
      }
    />
  );
}
