/** Parse a YYYY-MM-DD ISO string and return the year, or null if invalid. */
export function toYear(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = /^(\d{4})-\d{2}-\d{2}(?:T.*)?$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  return Number.isFinite(year) ? year : null;
}

/** Parse a YYYY-MM-DD ISO string into a UTC Date, or null if invalid. */
export function parseIsoDateUtc(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T.*)?$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  return new Date(Date.UTC(year, month - 1, day));
}

/** Serialize a Date to a YYYY-MM-DD ISO string using UTC fields. */
export function toIsoDateUtc(date: Date): string {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Convert a year number to a start-of-year ISO date string (YYYY-01-01). */
export function yearToIsoStart(year: number): string {
  return `${String(year).padStart(4, "0")}-01-01`;
}

/** Convert a year number to an end-of-year ISO date string (YYYY-12-31). */
export function yearToIsoEnd(year: number): string {
  return `${String(year).padStart(4, "0")}-12-31`;
}

/**
 * Whether the period from `start` to `end` is the one shown at `value`.
 *
 * Periods are read as [start, end[ where they meet: when one map ends the year
 * (or day) another begins, that shared bound belongs to the map that begins, so
 * the two are never drawn on top of each other. A bound nothing else starts on
 * stays inclusive, otherwise the last map would vanish at the end of the
 * timeline, and so would a map covering a single year.
 *
 * `periodStarts` holds the start of every period on the timeline, in the same
 * unit as the other arguments (years, or ISO dates, which sort as strings).
 */
export function isPeriodActiveAt<T extends number | string>(
  start: T,
  end: T,
  value: T,
  periodStarts: ReadonlySet<T>,
): boolean {
  if (value < start || value > end) return false;
  if (value < end || start === end) return true;
  return !periodStarts.has(end);
}
