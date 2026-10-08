import { MatchweekPage } from "@/components/MatchweekPage";

export default function MatchesPage({ params }: PageProps<"/mw/[n]/matches">) {
  return <MatchweekPage params={params} tab="matches" />;
}
