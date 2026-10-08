import Link from "next/link";
import { usingMocks } from "@/lib/api";

export type Tab = "snapshot" | "matches";

// Shared page width and side gutters, for the header and every <main>.
export const SHELL = "mx-auto w-full max-w-[1100px] px-4 sm:px-6";

const TABS: { tab: Tab; label: string; suffix: string }[] = [
  { tab: "snapshot", label: "Snapshot", suffix: "" },
  { tab: "matches", label: "Matches", suffix: "/matches" },
];

function Arrow({ href, label, children }: { href: string | null; label: string; children: string }) {
  const box = "grid size-11 place-items-center text-lg";
  if (!href) {
    return (
      <span aria-disabled="true" aria-label={label} className={`${box} text-outline`}>
        {children}
      </span>
    );
  }
  return (
    <Link href={href} aria-label={label} className={`${box} hover:bg-page`}>
      {children}
    </Link>
  );
}

// Site title, plus the matchweek switcher and tabs when a matchweek is given.
// `matchweeks` is every matchweek number that can be switched to.
export function Header({ current, tab, matchweeks = [] }: { current?: number; tab?: Tab; matchweeks?: number[] }) {
  const suffix = TABS.find((t) => t.tab === tab)?.suffix ?? "";
  const link = (n: number | undefined) => (n === undefined ? null : `/mw/${n}${suffix}`);
  const sorted = [...matchweeks].sort((a, b) => a - b);

  return (
    <header className="border-b border-rule bg-surface">
      {usingMocks() && (
        <p className="bg-ink py-1 text-center text-xs font-semibold tracking-widest text-surface">MOCK DATA</p>
      )}
      <div className={`${SHELL} grid grid-cols-[1fr_auto] items-center gap-x-4 lg:grid-cols-[1fr_auto_1fr]`}>
        <Link href="/" className="justify-self-start py-3 text-xl font-extrabold [font-stretch:125%]">
          Matchweek
        </Link>

        {current !== undefined && (
          <>
            <nav aria-label="Matchweek" className="flex items-center">
              <Arrow href={link(sorted.findLast((n) => n < current))} label="Previous matchweek">
                ←
              </Arrow>
              <span className="min-w-16 text-center font-semibold">MW {current}</span>
              <Arrow href={link(sorted.find((n) => n > current))} label="Next matchweek">
                →
              </Arrow>
            </nav>

            <nav aria-label="Page" className="col-span-2 flex gap-6 lg:col-span-1 lg:justify-self-end">
              {TABS.map((t) => (
                <Link
                  key={t.tab}
                  href={`/mw/${current}${t.suffix}`}
                  aria-current={t.tab === tab ? "page" : undefined}
                  className={`flex h-11 items-center border-b-2 font-medium ${
                    t.tab === tab ? "border-ink" : "border-transparent text-muted hover:text-ink"
                  }`}
                >
                  {t.label}
                </Link>
              ))}
            </nav>
          </>
        )}
      </div>
    </header>
  );
}
