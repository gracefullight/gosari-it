import { describe, expect, it } from "vitest";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { hasDetailedResult, hasDisplayableResult } from "@/lib/result-display";

const empty = {
  data_status: null,
  source_mode: null,
  result: {},
  action_status: null,
  warnings: [],
  errors: [],
} as unknown as ResultEnvelope;
describe("meaningful chat results", () => {
  it("keeps actual zero rows, partial values and official links available in details", () => {
    expect(
      hasDetailedResult({
        ...empty,
        data_status: "no_data",
        result: {
          sample_cards: [],
          product_count: 0,
          available_sample_count: 3,
          reason: "NO_MATCHING_SAMPLE",
        },
      })
    ).toBe(false);
    expect(
      hasDetailedResult({
        ...empty,
        data_status: "complete",
        result: { stations: [{ rain_mm: 0 }] },
      })
    ).toBe(true);
    expect(
      hasDetailedResult({
        ...empty,
        data_status: "partial",
        result: { price_cards: [{ price_value: 0 }] },
      })
    ).toBe(true);
    expect(
      hasDetailedResult({
        ...empty,
        result: { links: [{ title: "공식 조회", url: "https://example.com" }] },
      })
    ).toBe(true);
  });
  it("does not create a card for a plain assistant response with no result", () => {
    expect(hasDisplayableResult(empty)).toBe(false);
    expect(
      hasDisplayableResult({
        ...empty,
        data_status: "complete",
        result: { channel: "retail", sample_cards: [] },
      })
    ).toBe(false);
  });
  it.each(["no_data", "partial", "unavailable", "conflict"] as const)(
    "keeps a real %s state visible",
    (data_status) => {
      expect(hasDisplayableResult({ ...empty, data_status })).toBe(true);
    }
  );
  it("keeps zero-valued data and explicit warnings or errors", () => {
    expect(hasDisplayableResult({ ...empty, result: { rainfall: 0 } })).toBe(true);
    expect(
      hasDisplayableResult({ ...empty, warnings: ["선택한 날짜 자료 일부가 없습니다."] })
    ).toBe(true);
    expect(
      hasDisplayableResult({
        ...empty,
        errors: [{ code: "UPSTREAM_FAILED", message: "조회에 실패했습니다." }],
      })
    ).toBe(true);
  });
});
