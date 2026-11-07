import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AnalysisConditionForm } from "@/components/analysis-condition-form";

const { confirmSpec, openFeature } = vi.hoisted(() => ({
  confirmSpec: vi.fn(),
  openFeature: vi.fn(),
}));
vi.mock("@/hooks/use-chat", () => ({ useChat: () => ({ confirmSpec, openFeature }) }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("preserves the user's parsed place, years, period and elements", () => {
  render(
    <AnalysisConditionForm
      prepare={{
        classification: "public",
        needs_confirmation: true,
        spec: {
          operation: "history_compare",
          source_ids: ["jeju_579"],
          station_selections: [{ source_id: "jeju_579", station_name: "제주" }],
          years: [2022, 2025],
          month_day_start: "03-01",
          month_day_end: "04-30",
          elements: ["average_temperature"],
        },
      }}
    />
  );
  expect((screen.getByLabelText("지역") as HTMLInputElement).value).toBe("제주");
  expect((screen.getByLabelText("비교 연도 (쉼표 구분)") as HTMLInputElement).value).toBe(
    "2022,2025"
  );
  fireEvent.click(screen.getByRole("button", { name: "이 조건으로 비교" }));
  expect(confirmSpec).toHaveBeenCalledWith(
    expect.objectContaining({
      years: [2022, 2025],
      month_day_start: "03-01",
      month_day_end: "04-30",
      elements: ["average_temperature"],
    }),
    expect.any(String)
  );
});

it("keeps an outing confirmation as an outing instead of forcing historical statistics", () => {
  const spec = {
    operation: "outing_compare",
    source_ids: ["open_meteo"],
    candidates: [{ location_id: "aewol", date: "2026-11-08", time_slot: "09:00" }],
  };
  render(
    <AnalysisConditionForm prepare={{ classification: "public", needs_confirmation: true, spec }} />
  );
  fireEvent.click(screen.getByRole("button", { name: "이 조건으로 조회" }));
  expect(confirmSpec).toHaveBeenCalledWith(spec, "이 조건으로 조회");
  expect(screen.queryByLabelText("지역")).toBeNull();
});

it("does not invent a station or years for unresolved historical questions", () => {
  render(
    <AnalysisConditionForm
      prepare={{ classification: "public", feature: "history_compare", needs_confirmation: true }}
    />
  );
  expect((screen.getByLabelText("지역") as HTMLInputElement).value).toBe("");
  expect(
    (screen.getByRole("button", { name: "이 조건으로 비교" }) as HTMLButtonElement).disabled
  ).toBe(true);
  expect(confirmSpec).not.toHaveBeenCalled();
});

it.each(["market_query", "retail_lookup", "survey_link"])(
  "keeps unresolved %s conditions and execution inside chat",
  (featureHint) => {
    render(
      <AnalysisConditionForm
        prepare={{
          classification: "public",
          feature: "price",
          needs_confirmation: true,
          form: {
            feature_hint: featureHint,
            questions: ["도매·조사가·상품 가격 중 무엇을 볼까요?"],
          },
        }}
      />
    );
    expect(screen.queryByRole("button", { name: "나들이 조건 선택" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "판매가" }));
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    expect(openFeature).not.toHaveBeenCalled();
    expect(confirmSpec).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ operation: "retail_lookup", price_channel: "retail" }),
      expect.any(String),
      null
    );
  }
);

it("preserves an already resolved wholesale specification", () => {
  const spec = {
    operation: "market_query",
    source_ids: ["at_settlement"],
    price_channel: "wholesale",
    settlement_date: "2026-04-15",
    market_ids: ["110001"],
    fresh_or_dried: "생고사리",
  };
  render(
    <AnalysisConditionForm
      prepare={{ classification: "public", feature: "price", needs_confirmation: true, spec }}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
  expect(confirmSpec).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining(spec),
    expect.any(String),
    null
  );
  expect(openFeature).not.toHaveBeenCalled();
});

it("resolves missing outing conditions inside chat while preserving the parsed day", () => {
  render(
    <AnalysisConditionForm
      prepare={{
        classification: "public",
        feature: "outing",
        needs_confirmation: true,
        form: { feature_hint: "outing", initial_values: { date: "2026-11-08" } },
      }}
    />
  );
  expect(screen.getByRole("button", { name: "지역 1 날짜" }).textContent).toContain("2026-11-08");
  expect(
    (screen.getByRole("button", { name: "이 조건으로 날씨 조회" }) as HTMLButtonElement).disabled
  ).toBe(true);
  fireEvent.change(screen.getByRole("combobox", { name: "지역" }), { target: { value: "aewol" } });
  fireEvent.change(screen.getByRole("combobox", { name: "시각" }), { target: { value: "09:00" } });
  fireEvent.click(screen.getByRole("button", { name: "이 조건으로 날씨 조회" }));
  expect(confirmSpec).toHaveBeenCalledExactlyOnceWith(
    expect.objectContaining({
      operation: "outing_compare",
      source_ids: ["open_meteo"],
      candidates: [{ location_id: "aewol", date: "2026-11-08", time_slot: "09:00" }],
    }),
    expect.any(String),
    null
  );
  expect(openFeature).not.toHaveBeenCalled();
});

it("uses inline weather questions for an unresolved generic request without menu shortcuts", () => {
  render(
    <AnalysisConditionForm
      prepare={{
        classification: "public",
        needs_confirmation: true,
        form: { questions: ["어느 지역의 날씨를 볼까요?"] },
      }}
    />
  );
  expect(screen.getByRole("form", { name: "채팅 나들이 조건" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "나들이 조건 선택" })).toBeNull();
  expect(screen.queryByRole("button", { name: "가격 조사" })).toBeNull();
  expect(openFeature).not.toHaveBeenCalled();
});
