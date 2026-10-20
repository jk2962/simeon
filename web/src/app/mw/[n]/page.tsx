import { MatchweekPage } from "@/components/MatchweekPage";
import { SnapshotView } from "@/components/SnapshotView";
import type { MatchweekSummary } from "@/lib/types";

// The page waits for the matchweek list so an unknown matchweek can be a real 404.
export const instant = false;

export default function SnapshotPage({ params }: PageProps<"/mw/[n]">) {
  return (
    <MatchweekPage
      params={params}
      tab="snapshot"
      render={(matchweek, matchweeks) => {
        const week = matchweeks.find((m) => m.matchweek === matchweek);
        const previous = matchweeks.find((m) => m.matchweek === matchweek - 1);
        // A week has a table if one was locked or made retrospectively.
        const hasTable = (m?: MatchweekSummary) => Boolean(m && (m.tableLockedAt || m.retrospective));
        if (!hasTable(week)) {
          return (
            <>
              <h1 className="text-3xl font-bold">Season forecast</h1>
              <p className="mt-3 text-muted">No season forecast was locked before MW{matchweek}. See the Matches tab.</p>
            </>
          );
        }
        return (
          <SnapshotView
            matchweek={matchweek}
            retrospective={week?.retrospective ?? false}
            // Movement is only compared between tables of the same kind: locked with locked.
            hasPrevious={hasTable(previous) && previous?.retrospective === week?.retrospective}
          />
        );
      }}
    />
  );
}
