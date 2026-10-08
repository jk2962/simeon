import { getTeam } from "@/config/teams";
import { percent } from "@/lib/format";
import type { ActualRow, PredictedRow, TeamCode } from "@/lib/types";
import { TeamChip } from "./TeamChip";

// A thin rule closes the top four and the last safe place.
const ZONE_ENDS = [4, 17];

const HEAD = "px-2 py-2 text-xs font-medium text-muted";
const CELL = "px-2 py-2.5";
const WIDE_ONLY = "hidden sm:table-cell"; // dropped below 640px

function Change({ places }: { places: number }) {
  if (places === 0) {
    return (
      <span aria-label="No change" className="text-muted">
        –
      </span>
    );
  }
  const size = Math.abs(places);
  return (
    <span aria-label={`${places > 0 ? "Up" : "Down"} ${size} ${size === 1 ? "place" : "places"}`}>
      {places > 0 ? "▲" : "▼"}
      {size}
    </span>
  );
}

function Chance({ p }: { p: number }) {
  return <td className={`${CELL} ${WIDE_ONLY} text-right ${p < 0.005 ? "text-muted" : ""}`}>{percent(p)}</td>;
}

// The forecast next to the current standings. `previous` is last week's
// predicted position per club, or null when there is no earlier forecast.
export function ForecastTable({
  matchweek,
  rows,
  actual,
  previous,
}: {
  matchweek: number;
  rows: PredictedRow[];
  actual: Map<TeamCode, ActualRow>;
  previous: Map<TeamCode, number> | null;
}) {
  const standings = `Table after MW${matchweek - 1}`;
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <td colSpan={previous ? 4 : 3} />
          {/* The group covers Now and Pts; below 640px only Now is left. */}
          <th scope="colgroup" className={`${HEAD} border-b border-rule text-right sm:hidden`}>
            {standings}
          </th>
          <th scope="colgroup" colSpan={2} className={`${HEAD} ${WIDE_ONLY} border-b border-rule text-center`}>
            {standings}
          </th>
          <td colSpan={3} className={WIDE_ONLY} />
        </tr>
        <tr className="border-b border-ink">
          <th scope="col" className={`${HEAD} w-8 text-right`}>
            <abbr title="Predicted final position" className="no-underline">
              #
            </abbr>
          </th>
          {previous && (
            <th scope="col" className={`${HEAD} w-10 text-left`}>
              <abbr title={`Change in predicted position since MW${matchweek - 1}`} className="no-underline">
                Δ
              </abbr>
            </th>
          )}
          <th scope="col" className={`${HEAD} text-left`}>
            Club
          </th>
          <th scope="col" className={`${HEAD} text-right`}>
            <abbr title="Expected final points" className="no-underline">
              xPts
            </abbr>
          </th>
          <th scope="col" className={`${HEAD} text-right`}>
            <abbr title="Position now" className="no-underline">
              Now
            </abbr>
          </th>
          <th scope="col" className={`${HEAD} ${WIDE_ONLY} text-right`}>
            <abbr title="Points now" className="no-underline">
              Pts
            </abbr>
          </th>
          <th scope="col" className={`${HEAD} ${WIDE_ONLY} text-right`}>
            Title
          </th>
          <th scope="col" className={`${HEAD} ${WIDE_ONLY} text-right`}>
            Top 4
          </th>
          <th scope="col" className={`${HEAD} ${WIDE_ONLY} text-right`}>
            <abbr title="Relegation" className="no-underline">
              Releg.
            </abbr>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const team = getTeam(row.teamCode);
          const now = actual.get(row.teamCode);
          const before = previous?.get(row.teamCode);
          return (
            <tr
              key={row.teamCode}
              className={`border-b ${ZONE_ENDS.includes(row.predictedPosition) ? "border-ink" : "border-rule"}`}
            >
              <td className={`${CELL} text-right text-muted`}>{row.predictedPosition}</td>
              {previous && (
                <td className={`${CELL} text-left text-sm`}>
                  {before === undefined ? null : <Change places={before - row.predictedPosition} />}
                </td>
              )}
              <th scope="row" className={`${CELL} text-left font-normal`}>
                <span className="flex items-center gap-3">
                  <TeamChip code={row.teamCode} />
                  <span className="hidden sm:inline">{team.name}</span>
                  <span className="sm:hidden">{team.shortName}</span>
                </span>
              </th>
              <td className={`${CELL} text-right font-semibold`}>{row.expectedPoints.toFixed(1)}</td>
              <td className={`${CELL} text-right`}>{now?.position ?? "–"}</td>
              <td className={`${CELL} ${WIDE_ONLY} text-right`}>{now?.points ?? "–"}</td>
              <Chance p={row.pTitle} />
              <Chance p={row.pTop4} />
              <Chance p={row.pRelegation} />
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
