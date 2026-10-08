// Display formats. Times are always UTC and say so, so the server and the
// browser can never disagree about them.

// Every model probability on the site goes through this: never "0%" or "100%".
export function percent(p: number): string {
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return `${Math.min(99, Math.max(1, Math.round(p * 100)))}%`;
}

const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});
const DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

function format(iso: string, formatter: Intl.DateTimeFormat): string | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : formatter.format(date);
}

// "Oct 7, 22:35 UTC". An unreadable timestamp is shown as it came.
export function utcDateTime(iso: string): string {
  const text = format(iso, DATE_TIME);
  return text ? `${text} UTC` : iso;
}

// "Oct 7, 2026"
export function utcDate(iso: string): string {
  return format(iso, DATE) ?? iso;
}
