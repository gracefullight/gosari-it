type DisplayDate = string | Date | null | undefined;
const DATE_ONLY = /^(\d{4})(?:-(\d{2})-(\d{2})|\.\s*(\d{1,2})\.\s*(\d{1,2})\.?)$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const TIMEZONE = /(Z|[+-]\d{2}:?\d{2})$/i;
const LOCAL_TIMESTAMP = /^(\d{4}-\d{2}-\d{2})T([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d(?:\.\d+)?)?$/;

function dateOnly(value: string): string | undefined {
  const match = DATE_ONLY.exec(value);
  if (!match) return undefined;
  const year = match[1];
  const month = (match[2] ?? match[4]).padStart(2, "0");
  const day = (match[3] ?? match[5]).padStart(2, "0");
  const parsed = new Date(`${year}-${month}-${day}T00:00:00Z`);
  if (
    !Number.isFinite(parsed.getTime()) ||
    parsed.getUTCFullYear() !== Number(year) ||
    parsed.getUTCMonth() + 1 !== Number(month) ||
    parsed.getUTCDate() !== Number(day)
  )
    return undefined;
  return `${year}-${month}-${day}`;
}

function format(value: DisplayDate, includeTime: boolean): string {
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    const day = dateOnly(value);
    if (day) return day;
    // Parse timestamps only: ordinary labels and invalid dates remain legible.
    if (!TIMESTAMP.test(value)) return value;
    if (!dateOnly(value.slice(0, 10))) return value;
    if (!TIMEZONE.test(value)) {
      const local = LOCAL_TIMESTAMP.exec(value);
      if (!local) return value;
      return includeTime ? `${local[1]} ${local[2]}:${local[3]}` : local[1];
    }
  }
  const parsed = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(parsed.getTime())) return typeof value === "string" ? value : "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" as const } : {}),
  }).formatToParts(parsed);
  const part = (name: Intl.DateTimeFormatPartTypes) =>
    parts.find((entry) => entry.type === name)?.value ?? "";
  const day = `${part("year")}-${part("month")}-${part("day")}`;
  return includeTime ? `${day} ${part("hour")}:${part("minute")}` : day;
}

export function formatDisplayDate(value: DisplayDate): string {
  return format(value, false);
}

export function formatDisplayDateTime(value: DisplayDate): string {
  return format(value, true);
}
