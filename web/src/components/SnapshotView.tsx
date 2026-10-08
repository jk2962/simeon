import { getSnapshot } from "@/lib/api";
import { ukDateTime } from "@/lib/format";
import { ErrorNote } from "./ErrorNote";
import { ForecastTable } from "./ForecastTable";
import { PositionGrid } from "./PositionGrid";

// The Snapshot page body: where the model expects each club to finish, next
// to where it stands now, and how the forecast moved since last week.
export async function SnapshotView({ matchweek, hasPrevious }: { matchweek: number; hasPrevious: boolean }) {
  const [current, earlier] = await Promise.all([
    getSnapshot(matchweek),
    hasPrevious ? getSnapshot(matchweek - 1) : null,
  ]);

  if (!current.ok) {
    return (
      <>
        <h1 className="text-3xl font-bold">Season forecast</h1>
        <div className="mt-6">
          <ErrorNote message={current.error} />
        </div>
      </>
    );
  }

  const snapshot = current.data;
  const rows = [...snapshot.predictedTable].sort((a, b) => a.predictedPosition - b.predictedPosition);
  const actual = new Map(snapshot.actualTable.map((row) => [row.teamCode, row]));
  const previous = earlier?.ok
    ? new Map(earlier.data.predictedTable.map((row) => [row.teamCode, row.predictedPosition]))
    : null;

  return (
    <>
      <h1 className="text-3xl font-bold">Season forecast</h1>
      <p className="mt-1 text-muted">
        Locked before MW{matchweek} · <time dateTime={snapshot.lockedAt}>{ukDateTime(snapshot.lockedAt)}</time> · model{" "}
        {snapshot.modelVersion.slice(0, 7)}
      </p>
      {!previous && (
        <p className="mt-1 text-sm text-muted">
          {hasPrevious
            ? `The MW${matchweek - 1} forecast could not be loaded, so changes since then are not shown.`
            : "First locked forecast — no previous week to compare."}
        </p>
      )}

      <div className="mt-6">
        <ForecastTable matchweek={matchweek} rows={rows} actual={actual} previous={previous} />
      </div>

      <h2 className="mt-12 text-xl font-bold">Where each club could finish</h2>
      <p className="mt-1 mb-4 max-w-prose text-sm text-muted">
        The stronger the color, the more likely the position. Chances of 10% or more are written in.
      </p>
      <PositionGrid rows={rows} />
    </>
  );
}
