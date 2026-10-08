import { MatchweekPage } from "@/components/MatchweekPage";

export default function SnapshotPage({ params }: PageProps<"/mw/[n]">) {
  return <MatchweekPage params={params} tab="snapshot" />;
}
