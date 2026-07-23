import { getLocale } from "@/i18n";

const locale = getLocale();

export const shortDateFmt = new Intl.DateTimeFormat(locale, {
  month: "short",
  day: "numeric",
});

export const weekdayDateFmt = new Intl.DateTimeFormat(locale, {
  weekday: "short",
  month: "short",
  day: "numeric",
});

export const hmsTimeFmt = new Intl.DateTimeFormat(locale, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export const windowDateFmt = new Intl.DateTimeFormat(locale, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

// `Intl.NumberFormat.prototype.format` is a bound getter — safe to extract.
export const intFmt = new Intl.NumberFormat(locale).format;

/** Parse a `YYYY-MM-DD` string as a local date (avoids UTC-midnight day-shift bugs). */
export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
