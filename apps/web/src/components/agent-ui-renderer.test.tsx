import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentGeneratedUI } from "@/components/agent-ui-renderer";
import { parseAgentUISpec } from "@/lib/agent-ui.catalog";
import type { PrepareResponse, ResultEnvelope } from "@/lib/gosari.types";

vi.mock("@/components/jeju-weather-map", () => ({
  WEATHER_LABELS: { clear: "맑음", rain: "비", unknown: "자료 없음" },
  JejuWeatherMap: ({
    locations,
    onSelect,
  }: {
    locations: { id: string; name: string }[];
    onSelect: (value: unknown) => void;
  }) => (
    <section aria-label="날씨 지도">
      {locations.map((location) => (
        <button type="button" key={location.id} onClick={() => onSelect(location)}>
          {location.name} 날씨
        </button>
      ))}
    </section>
  ),
}));
vi.mock("@/components/station-map", () => ({ StationMap: () => <div>공개 관측소 목록</div> }));
vi.mock("@/components/analysis-condition-form", () => ({
  AnalysisConditionFields: () => <div>추가 조회 조건</div>,
}));
afterEach(cleanup);

function envelope(
  result: Record<string, unknown>,
  scope: Record<string, unknown> = {}
): ResultEnvelope {
  return {
    schema_version: "result-v1",
    request_id: "request-public",
    data_status: "complete",
    source_mode: "fetched",
    action_status: null,
    link_status: "not_requested",
    cache_resolution: "miss",
    requested_scope: scope,
    effective_scope: {},
    observed_period: {},
    fetched_at: null,
    verified_on: null,
    result,
    evidence_ids: ["evidence-public"],
    warnings: [],
    errors: [],
  };
}
function price(value = 22000) {
  return envelope(
    {
      channel: "wholesale",
      price_cards: [
        {
          channel: "wholesale",
          row_id: "row-public",
          product: "서울가락 생고사리",
          product_option: "특 · 상자",
          price_value: value,
          net_weight_value: 4000,
          price_per_kg_value: value / 4,
          price_as_of: "2026-05-12",
        },
      ],
    },
    { operation: "market_query", source_ids: ["at_settlement"], settlement_date: "2026-05-12" }
  );
}
function resultSpec(
  type = "PriceResults",
  actions = ["adjust_conditions", "compare_packages", "save_to_notebook", "show_price_table"]
) {
  return {
    root: "root",
    elements: {
      root: { type: "ResultLayout", props: {}, children: ["result", "actions"] },
      result: { type, props: { resultRef: "result_1" }, children: [] },
      actions: {
        type: "FollowupActions",
        props: {
          actions: actions.map((id) => ({ id, resultRef: "result_1", label: "임의의 모델 문구" })),
        },
        children: [],
      },
    },
  };
}
function conditionSpec(type: string) {
  return {
    root: "root",
    elements: {
      root: { type: "ResultLayout", props: {}, children: ["form"] },
      form: { type, props: { preparationRef: "preparation_1" }, children: [] },
    },
  };
}

describe("agent JSON renderer", () => {
  it("renders a registered ownership result from the tool reference and rejects model-authored ownership props", () => {
    const owned = envelope(
      {
        land_ownership: {
          location_name: "선흘",
          ownership_class: "private",
          is_private: true,
          owner_type_name: "개인",
          reference_month: "202610",
          source_url: "https://www.vworld.kr/",
        },
      },
      { operation: "land_ownership" }
    );
    const spec = resultSpec("LandOwnershipResults", []);
    render(<AgentGeneratedUI spec={spec} results={{ result_1: owned }} onAction={vi.fn()} />);
    expect(screen.getByText("개인")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "선흘" })).toBeTruthy();
    const fabricated = {
      ...spec,
      elements: {
        ...spec.elements,
        result: {
          type: "LandOwnershipResults",
          props: { resultRef: "result_1", ownership_class: "public" },
          children: [],
        },
      },
    };
    expect(parseAgentUISpec(fabricated, { result_1: owned })).toBeNull();
  });
  it("renders only bound public values and dispatches named followup actions", async () => {
    const action = vi.fn();
    render(
      <AgentGeneratedUI spec={resultSpec()} results={{ result_1: price() }} onAction={action} />
    );
    expect(screen.getByRole("heading", { name: "도매 가격" })).toBeTruthy();
    expect(screen.getByText("22,000원 / 4000g")).toBeTruthy();
    expect(screen.queryByText("임의의 모델 문구")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "다른 규격" }));
    await waitFor(() =>
      expect(action).toHaveBeenCalledWith({
        id: "compare_packages",
        resultRef: "result_1",
        label: "다른 규격",
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "수첩에 기록" }));
    await waitFor(() =>
      expect(action).toHaveBeenCalledWith({
        id: "save_to_notebook",
        resultRef: "result_1",
        label: "수첩에 기록",
      })
    );
  });

  it("switches price results to a table through ActionProvider without querying again", async () => {
    const action = vi.fn();
    render(
      <AgentGeneratedUI spec={resultSpec()} results={{ result_1: price() }} onAction={action} />
    );
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "표로 보기" }));
    expect(await screen.findByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "기준일" })).toBeTruthy();
    expect(screen.getByText("22,000원")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "상품별로 보기" }));
    await waitFor(() => expect(screen.queryByRole("table")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "표로 보기" }));
    expect(await screen.findByRole("table")).toBeTruthy();
    expect(action).not.toHaveBeenCalled();
  });

  it("updates references when a later streamed result replaces the same reference", () => {
    const spec = resultSpec();
    const action = vi.fn();
    const view = render(
      <AgentGeneratedUI spec={spec} results={{ result_1: price() }} onAction={action} />
    );
    view.rerender(
      <AgentGeneratedUI spec={spec} results={{ result_1: price(18000) }} onAction={action} />
    );
    expect(screen.getByText("18,000원 / 4000g")).toBeTruthy();
    expect(screen.queryByText("22,000원 / 4000g")).toBeNull();
  });

  it.each([
    {
      root: "root",
      elements: { root: { type: "HTML", props: { html: "<script>bad</script>" }, children: [] } },
    },
    { root: "root", elements: { root: { type: "ResultLayout", props: {}, children: ["root"] } } },
    {
      root: "root",
      elements: { root: { type: "ResultLayout", props: {}, children: ["missing"] } },
    },
    {
      root: "root",
      elements: { root: { type: "ResultLayout", props: {}, children: ["constructor"] } },
    },
    {
      root: "root",
      elements: {
        root: { type: "ResultLayout", props: {}, children: ["price"] },
        price: {
          type: "PriceResults",
          props: { resultRef: "result_1", price_value: 999 },
          children: [],
        },
      },
    },
  ])("falls back for unregistered, cyclic, dangling or fabricated-value specs", (spec) => {
    render(
      <AgentGeneratedUI
        spec={spec}
        results={{ result_1: price() }}
        onAction={vi.fn()}
        fallback={<p>기존 결과</p>}
      />
    );
    expect(screen.getByText("기존 결과")).toBeTruthy();
    expect(document.querySelector("[data-agent-ui]")).toBeNull();
  });

  it("rejects a missing data reference and dynamic event bindings", () => {
    const spec = resultSpec();
    expect(parseAgentUISpec(spec, {})).toBeNull();
    expect(
      parseAgentUISpec(
        {
          ...spec,
          elements: {
            ...spec.elements,
            result: {
              ...spec.elements.result,
              on: { press: { action: "navigate", params: { url: "https://example.com" } } },
            },
          },
        },
        { result_1: price() }
      )
    ).toBeNull();
  });

  it("binds local price conditions and submits edited package weight via the named action", async () => {
    const confirm = vi.fn();
    const prepare: PrepareResponse = {
      classification: "public",
      feature: "price",
      needs_confirmation: true,
      spec: {
        operation: "market_query",
        source_ids: ["at_settlement"],
        price_channel: "wholesale",
        fresh_or_dried: "생고사리",
        settlement_date: "2026-05-12",
        settlement_date_end: "2026-05-12",
        market_ids: ["110001"],
        package_weight_unit: "4 kg",
      },
    };
    render(
      <AgentGeneratedUI
        spec={conditionSpec("PriceConditions")}
        results={{}}
        preparations={{ preparation_1: prepare }}
        onAction={vi.fn()}
        onConfirm={confirm}
      />
    );
    fireEvent.click(screen.getByText("세부 조건"));
    fireEvent.change(screen.getByLabelText("포장 무게"), { target: { value: "200 g" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0]).toMatchObject({
      operation: "market_query",
      package_weight_unit: "200 g",
      settlement_date: "2026-05-12",
    });
    expect(prepare.spec?.package_weight_unit).toBe("4 kg");
  });

  it("submits local outing locations and dates without inserting generated weather values", async () => {
    const confirm = vi.fn();
    const prepare: PrepareResponse = {
      classification: "public",
      feature: "outing",
      needs_confirmation: true,
      spec: {
        operation: "outing_compare",
        source_ids: ["open_meteo"],
        candidates: [{ location_id: "jeju", date: "2026-11-07", time_slot: "09:00" }],
      },
    };
    render(
      <AgentGeneratedUI
        spec={conditionSpec("OutingConditions")}
        results={{}}
        preparations={{ preparation_1: prepare }}
        onAction={vi.fn()}
        onConfirm={confirm}
      />
    );
    fireEvent.change(screen.getByRole("combobox", { name: "시각" }), {
      target: { value: "15:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "이 조건으로 날씨 조회" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(confirm.mock.calls[0][0].candidates).toEqual([
      { location_id: "jeju", date: "2026-11-07", time_slot: "15:00" },
    ]);
    expect(confirm.mock.calls[0][0]).not.toHaveProperty("temperature_c");
  });

  it("switches verified outing weather to map pins through the named map action", async () => {
    const weather = envelope(
      {
        candidates: [
          {
            candidate_id: "cand-1",
            location_id: "jeju",
            station_name: "제주시",
            weather: {
              temperature_c: 17,
              precipitation_probability: 20,
              condition: "clear",
              target_at: "2026-11-07T09:00+09:00",
            },
          },
        ],
      },
      {
        operation: "outing_compare",
        candidates: [
          { candidate_id: "cand-1", location_id: "jeju", latitude: 33.4996, longitude: 126.5312 },
        ],
      }
    );
    render(
      <AgentGeneratedUI
        spec={resultSpec("WeatherComparison", ["show_weather_map"])}
        results={{ result_1: weather }}
        onAction={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "지도 보기" }));
    fireEvent.click(await screen.findByRole("button", { name: "제주시 날씨" }));
    expect(screen.getByText("맑음 · 17℃ · 강수확률 20%")).toBeTruthy();
  });

  it("preserves temperature-only historical comparisons", () => {
    const value = envelope({
      average_temperature: {
        per_year: {
          "2023": { average: "15.5", valid_days: 50 },
          "2024": { average: "15.7", valid_days: 60 },
        },
      },
    });
    render(
      <AgentGeneratedUI
        spec={resultSpec("WeatherComparison", [])}
        results={{ result_1: value }}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText("2023년")).toBeTruthy();
    expect(screen.getByText("15.5℃")).toBeTruthy();
    expect(screen.getByText("15.7℃")).toBeTruthy();
  });

  it("labels forecast categories in Korean and preserves units, zero and missing values", () => {
    const value = envelope({
      forecast: [
        { category: "TMP", value: "15.5", target_at: "2026-11-07T09:00+09:00" },
        { category: "POP", value: "0", target_at: "2026-11-07T12:00+09:00" },
        { category: "WSD", value: "2.5", target_at: "2026-11-07T15:00+09:00" },
        { category: "PCP", value: null, target_at: "2026-11-07T18:00+09:00" },
      ],
    });
    render(
      <AgentGeneratedUI
        spec={resultSpec("WeatherComparison", [])}
        results={{ result_1: value }}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText("15.5℃")).toBeTruthy();
    expect(screen.getByText("0%")).toBeTruthy();
    expect(screen.getByText("2.5m/s")).toBeTruthy();
    expect(screen.getByText("시간당 강수량")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText("TMP")).toBeNull();
  });
});
