// Display formats. Times are always UK time and say so. They are formatted on
// the server with a fixed time zone, so the server and the browser can never
// disagree about them.

// Every model probability on the site goes through this: never "0%" or "100%".
export function percent(p: number): string {
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return `${Math.min(99, Math.max(1, Math.round(p * 100)))}%`;
}

const UK = { timeZone: "Europe/London" } as const;
const DATE_TIME = new Intl.DateTimeFormat("en-US", {
  ...UK,
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const DATE = new Intl.DateTimeFormat("en-US", { ...UK, month: "short", day: "numeric", year: "numeric" });
const TIME = new Intl.DateTimeFormat("en-GB", { ...UK, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const DAY = new Intl.DateTimeFormat("en-GB", { ...UK, weekday: "short", day: "numeric", month: "short" });

// An unreadable timestamp is shown as it came.
function format(iso: string, formatter: Intl.DateTimeFormat): string | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : formatter.format(date);
}

// "Oct 16, 09:18 UK"
export function ukDateTime(iso: string): string {
  const text = format(iso, DATE_TIME);
  return text ? `${text} UK` : iso;
}

// "Oct 7, 2026"
export function ukDate(iso: string): string {
  return format(iso, DATE) ?? iso;
}

// "15:00 UK"
export function ukTime(iso: string): string {
  const text = format(iso, TIME);
  return text ? `${text} UK` : iso;
}

// "Sat 17 Oct", the UK calendar day a kickoff falls on.
export function ukDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const part = Object.fromEntries(DAY.formatToParts(date).map((p) => [p.type, p.value]));
  return `${part.weekday} ${part.day} ${part.month}`;
}
