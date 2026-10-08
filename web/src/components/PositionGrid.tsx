import { chipColor, fillOnWhite, getTeam, textOn } from "@/config/teams";
import { percent } from "@/lib/format";
import type { PredictedRow } from "@/lib/types";
import { TeamChip } from "./TeamChip";

const EMPTY_BELOW = 0.005; // under 0.5% the cell stays blank
const LABEL_FROM = 0.1; // the percentage is written in the cell from 10%

// One row per club, one column per finishing position. A cell is the club's
// color at an opacity equal to the probability, scaled so that the most
// likely cell on the page is fully opaque.
export function PositionGrid({ rows }: { rows: PredictedRow[] }) {
  const positions = Array.from({ length: Math.max(0, ...rows.map((row) => row.positionProbabilities.length)) }, (_, k) => k + 1);
  const max = Math.max(...rows.flatMap((row) => row.positionProbabilities), EMPTY_BELOW);
  const sticky = "sticky bg-surface";

  return (
    // Below 1024px the grid scrolls inside this box, so its sticky header and
    // club column hold against the box. From 1024px it fits the page.
    <div
      role="region"
      aria-label="Finishing position probabilities"
      tabIndex={0}
      className="max-h-[75vh] overflow-auto border border-rule bg-surface lg:max-h-none lg:overflow-visible"
    >
      <table className="w-full min-w-[60rem] border-separate border-spacing-0 text-xs lg:min-w-0 lg:table-fixed">
        <thead>
          <tr>
            <th scope="col" className={`${sticky} top-0 left-0 z-20 w-20 border-b border-rule px-2 py-2 text-left font-medium text-muted lg:w-44`}>
              Club
            </th>
            {positions.map((k) => (
              <th key={k} scope="col" className={`${sticky} top-0 z-10 border-b border-rule py-2 font-medium text-muted`}>
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const team = getTeam(row.teamCode);
            const color = chipColor(team).hex;
            return (
              <tr key={row.teamCode}>
                <th scope="row" className={`${sticky} left-0 z-10 px-2 text-left font-normal`}>
                  <span className="flex items-center gap-2">
                    <TeamChip code={row.teamCode} />
                    <span className="hidden truncate text-sm lg:inline">{team.shortName}</span>
                  </span>
                </th>
                {positions.map((k) => {
                  const p = row.positionProbabilities[k - 1] ?? 0;
                  const fill = p < EMPTY_BELOW ? null : fillOnWhite(color, p / max);
                  return (
                    <td
                      key={k}
                      aria-label={`${team.name}, position ${k}: ${percent(p)}`}
                      className="h-9 min-w-11 border border-surface text-center font-medium"
                      style={fill ? { backgroundColor: fill, color: textOn(fill) } : undefined}
                    >
                      {p >= LABEL_FROM ? percent(p) : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
