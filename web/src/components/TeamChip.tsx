import { chipColor, getTeam } from "@/config/teams";
import type { TeamCode } from "@/lib/types";

// A color block and the 3-letter code. The outline keeps pale colors visible.
export function TeamChip({ code }: { code: TeamCode }) {
  const team = getTeam(code);
  return (
    <span className="inline-flex items-center gap-1.5 align-middle" title={team.name}>
      <span
        aria-hidden="true"
        className="size-3.5 shrink-0 rounded-[2px] border border-outline"
        style={{ backgroundColor: chipColor(team).hex }}
      />
      <span className="text-sm font-semibold tracking-wide [font-stretch:80%]">{code}</span>
    </span>
  );
}
