import { MatchweekPage } from "@/components/MatchweekPage";
import { SnapshotView } from "@/components/SnapshotView";

export default function SnapshotPage({ params }: PageProps<"/mw/[n]">) {
  return (
    <MatchweekPage
      params={params}
      tab="snapshot"
      render={(matchweek, matchweeks) => (
        <SnapshotView matchweek={matchweek} hasPrevious={matchweeks.some((m) => m.matchweek === matchweek - 1)} />
      )}
    />
  );
}
