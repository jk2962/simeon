import { MatchesView } from "@/components/MatchesView";
import { MatchweekPage } from "@/components/MatchweekPage";

// The page waits for the matchweek list so an unknown matchweek can be a real 404.
export const instant = false;

export default function MatchesPage({ params }: PageProps<"/mw/[n]/matches">) {
  return (
    <MatchweekPage
      params={params}
      tab="matches"
      render={(matchweek, matchweeks) => {
        const week = matchweeks.find((m) => m.matchweek === matchweek);
        return (
          <MatchesView
            matchweek={matchweek}
            weekLockedAt={week?.matchesLockedAt ?? null}
            retrospective={week?.retrospective ?? false}
          />
        );
      }}
    />
  );
}
