import { describe, expect, it } from "vitest";
import { formatDisplayDate, formatDisplayDateTime } from "@/lib/date-format";

describe("display dates", () => {
  it("keeps date-only values and normalizes legacy separators without timezone shifts", () => {
    expect(formatDisplayDate("2026-11-07")).toBe("2026-11-07");
    expect(formatDisplayDate("2026.11.07")).toBe("2026-11-07");
    expect(formatDisplayDate("2026. 11. 7.")).toBe("2026-11-07");
  });

  it("uses Korean time across UTC day boundaries", () => {
    expect(formatDisplayDate("2026-11-06T18:20:00Z")).toBe("2026-11-07");
    expect(formatDisplayDateTime(new Date("2026-11-06T18:20:00Z"))).toBe("2026-11-07 03:20");
    expect(formatDisplayDateTime("2026-11-07T23:20:00-05:00")).toBe("2026-11-08 13:20");
    expect(formatDisplayDateTime("2026-11-07T09:00")).toBe("2026-11-07 09:00");
  });

  it("preserves unknown labels and invalid dates instead of inventing a date", () => {
    expect(formatDisplayDate("확인시점 없음")).toBe("확인시점 없음");
    expect(formatDisplayDate("2026.02.30")).toBe("2026.02.30");
    expect(formatDisplayDate("2026-02-30T12:00:00Z")).toBe("2026-02-30T12:00:00Z");
    expect(formatDisplayDate(new Date("invalid"))).toBe("");
    expect(formatDisplayDate(null)).toBe("");
  });
});
