import { Header, SHELL } from "@/components/Header";
import { TeamChip } from "@/components/TeamChip";
import { TEAMS, chipColor, getTeam, luminance } from "@/config/teams";

// The two backgrounds a chip can sit on: the page and a surface.
const BACKGROUNDS = ["#F5F5F5", "#FFFFFF"];

function Swatch({ label, hex }: { label: string; hex: string }) {
  return (
    <div className="flex items-center gap-2">
      <span aria-hidden="true" className="size-8 shrink-0 border border-outline" style={{ backgroundColor: hex }} />
      <div className="text-sm leading-tight">
        <div className="text-muted">{label}</div>
        <div>
          {hex} <span className="text-muted">L {luminance(hex).toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}

// Review page for the team color system. "ZZZ" shows the unknown-code fallback.
export default function ColorsPage() {
  return (
    <>
      <Header />
      <main className={`${SHELL} py-8`}>
        <h1 className="text-3xl font-bold">Team colors</h1>
        <p className="mt-1 max-w-prose text-muted">
          {Object.keys(TEAMS).length} clubs, each chip shown on {BACKGROUNDS.join(" and ")}. L is relative luminance, 0 to 1. The
          chip uses the primary color unless it is white or near-white (L above 0.85); then it uses the secondary.
        </p>

        <ul className="mt-6 border-t border-rule">
          {[...Object.keys(TEAMS), "ZZZ"].map((code) => {
            const team = getTeam(code);
            return (
              <li
                key={code}
                className="grid grid-cols-2 items-center gap-x-6 gap-y-3 border-b border-rule py-3 md:grid-cols-[10rem_1fr_11rem_11rem_9.5rem]"
              >
                <div className="flex gap-2">
                  {BACKGROUNDS.map((background) => (
                    <span key={background} className="px-2 py-1" style={{ backgroundColor: background }}>
                      <TeamChip code={code} />
                    </span>
                  ))}
                </div>
                <div>{code in TEAMS ? team.name : "Unknown code"}</div>
                <Swatch label="Primary" hex={team.primary} />
                <Swatch label="Secondary" hex={team.secondary} />
                <div className="col-span-2 text-sm whitespace-nowrap md:col-span-1">
                  <span className="text-muted">Chip uses</span> {chipColor(team).variant}
                </div>
              </li>
            );
          })}
        </ul>
      </main>
    </>
  );
}
