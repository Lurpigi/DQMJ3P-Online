// Dates are shown in the competition's official zone (fixed UTC offset) and in the viewer's zone.
function zoneOf(offsetMinutes: number): string {
  if (offsetMinutes === 0) return "UTC";
  if (offsetMinutes % 60 !== 0) return "UTC";
  const h = offsetMinutes / 60;
  return `Etc/GMT${h > 0 ? "-" : "+"}${Math.abs(h)}`; // POSIX sign: Etc/GMT-1 = UTC+1
}

export function offsetLabel(offsetMinutes: number) {
  if (offsetMinutes === 0) return "UTC";
  const sign = offsetMinutes > 0 ? "+" : "−";
  const m = Math.abs(offsetMinutes);
  return `UTC${sign}${Math.floor(m / 60)}${m % 60 ? ":" + String(m % 60).padStart(2, "0") : ""}`;
}

export function dateTime(iso: string | null | undefined, locale: string, offsetMinutes?: number) {
  if (!iso) return "—";
  const opts: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" };
  if (offsetMinutes !== undefined) opts.timeZone = zoneOf(offsetMinutes);
  return new Intl.DateTimeFormat(locale, opts).format(new Date(iso));
}

export function dateOnly(iso: string | null | undefined, locale: string, offsetMinutes?: number) {
  if (!iso) return "—";
  const opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" };
  if (offsetMinutes !== undefined) opts.timeZone = zoneOf(offsetMinutes);
  return new Intl.DateTimeFormat(locale, opts).format(new Date(iso));
}

/** A calendar day (YYYY-MM-DD) without time zone conversion. */
export function day(isoDay: string | null | undefined, locale: string) {
  if (!isoDay) return "—";
  const [y, m, d] = isoDay.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(Date.UTC(y, m - 1, d));
}

/** Last day of an edition: ends_at is exclusive. */
export function lastMoment(iso: string) {
  return new Date(new Date(iso).getTime() - 1).toISOString();
}

export function num(value: number | null | undefined, locale: string) {
  return value === null || value === undefined ? "—" : new Intl.NumberFormat(locale).format(value);
}

export function percent(part: number, whole: number, locale: string) {
  if (!whole) return "—";
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(part / whole);
}

export function relative(iso: string, locale: string, now = Date.now()) {
  const diff = (new Date(iso).getTime() - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function duration(seconds: number) {
  const s = Math.max(0, Math.floor(seconds));
  return { days: Math.floor(s / 86400), hours: Math.floor((s % 86400) / 3600), minutes: Math.floor((s % 3600) / 60) };
}

export const RANK_LETTERS = ["—", "F", "E", "D", "C", "B", "A", "S", "SS"];
