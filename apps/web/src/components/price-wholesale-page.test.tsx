import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { getDefaultStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PriceLookupPage } from "@/components/price-lookup-page";
import { priceLookupStateAtom } from "@/stores/price-lookup.atoms";

vi.mock("@/components/date-picker-field", () => ({
  DatePickerField: ({
    value,
    onChange,
    "aria-label": label,
  }: {
    value: string;
    onChange: (value: string) => void;
    "aria-label": string;
  }) => (
    <input aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
let client: QueryClient;
beforeEach(() => getDefaultStore().set(priceLookupStateAtom, null));
afterEach(() => {
  cleanup();
  client?.clear();
  vi.restoreAllMocks();
});
const options = {
  markets: [
    { value: "110001", label: "서울가락" },
    { value: "210001", label: "부산엄궁" },
  ],
  forms: [
    { value: "생고사리", label: "생고사리" },
    { value: "건고사리", label: "건고사리" },
  ],
  grades: [
    { value: "11", label: "특" },
    { value: "12", label: "상" },
  ],
  packages: [{ value: "101", label: "상자" }],
  weights: [{ value: "4 kg", label: "4 kg" }],
};
function mount() {
  client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <PriceLookupPage initialChannel="wholesale" />
    </QueryClientProvider>
  );
}
function mockRequest(failed = false) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
    const { spec } = JSON.parse(String(init?.body));
    return new Response(
      JSON.stringify({
        stage: "completed",
        job_id: "job",
        request_id: "req",
        result: {
          request_id: "req",
          data_status: failed ? "partial" : "complete",
          source_mode: "fetched",
          result: {
            options,
            price_cards: [
              {
                row_id: JSON.stringify(spec),
                channel: "wholesale",
                product: spec.grade ? "가락 생고사리 특" : "가락 생고사리 전체",
                price_value: 20000,
                net_weight_value: 4000,
                price_per_kg_value: 5000,
                price_as_of: spec.settlement_date,
              },
            ],
            failed_scope: failed ? [{ settlement_date: "2026-04-15", market_code: "210001" }] : [],
          },
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });
}

describe("wholesale prices", () => {
  it("applies explicit conditions, includes all of them in the request, and reuses a previous selection", async () => {
    const request = mockRequest();
    mount();
    await screen.findByText("가락 생고사리 전체");
    fireEvent.change(screen.getByLabelText("가격 시작일"), { target: { value: "2026-04-14" } });
    fireEvent.change(screen.getByLabelText("가격 종료일"), { target: { value: "2026-04-15" } });
    fireEvent.change(screen.getByLabelText("고사리 종류"), { target: { value: "생고사리" } });
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "11" } });
    fireEvent.change(screen.getByLabelText("포장"), { target: { value: "101" } });
    fireEvent.change(screen.getByLabelText("단량"), { target: { value: "4 kg" } });
    fireEvent.change(screen.getByLabelText("산지명"), { target: { value: "제주" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "부산엄궁" }));
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await screen.findByText("가락 생고사리 특");
    expect(JSON.parse(String(request.mock.calls[1][1]?.body)).spec).toMatchObject({
      settlement_date: "2026-04-14",
      settlement_date_end: "2026-04-15",
      market_ids: ["110001", "210001"],
      fresh_or_dried: "생고사리",
      grade: "11",
      package_code: "101",
      package_weight_unit: "4 kg",
      origin_filter: "제주",
    });
    fireEvent.click(screen.getByRole("button", { name: "조회 조건 변경" }));
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "새로고침" }).hasAttribute("disabled")).toBe(false)
    );
    fireEvent.click(screen.getByRole("button", { name: "조회 조건 변경" }));
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(screen.getByText("가락 생고사리 특")).toBeTruthy());
    expect(request).toHaveBeenCalledTimes(3);
  });

  it("shows the failed scope while keeping successful rows", async () => {
    mockRequest(true);
    mount();
    await screen.findByText("가락 생고사리 전체");
    expect(screen.getByText("일부 날짜·시장 조회에 실패했습니다.")).toBeTruthy();
    expect(screen.getByText("2026-04-15 · 부산엄궁")).toBeTruthy();
    expect(screen.queryByText("선택한 날짜·시장에서 조건에 맞는 거래가 없습니다.")).toBeNull();
  });

  it("does not submit an inverted date range", async () => {
    const request = mockRequest();
    mount();
    await screen.findByText("가락 생고사리 전체");
    fireEvent.change(screen.getByLabelText("가격 시작일"), { target: { value: "2026-04-15" } });
    fireEvent.change(screen.getByLabelText("가격 종료일"), { target: { value: "2026-04-14" } });
    expect(screen.getByRole("alert").textContent).toContain("종료일");
    expect(screen.getByRole("button", { name: "가격 조회" }).hasAttribute("disabled")).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
  });
});

it("waits for a 202 analysis job before displaying prices", async () => {
  const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const pending = String(url).endsWith("/analysis/jobs");
    return new Response(
      JSON.stringify(
        pending
          ? { job_id: "price-job", stage: "running", request_id: "req", result: null }
          : {
              job_id: "price-job",
              stage: "completed",
              request_id: "req",
              result: {
                request_id: "req",
                result: {
                  options,
                  price_cards: [
                    {
                      row_id: "async",
                      channel: "wholesale",
                      product: "조회 완료 생고사리",
                      price_value: 20000,
                      net_weight_value: 4000,
                    },
                  ],
                },
              },
            }
      ),
      { status: pending ? 202 : 200, headers: { "Content-Type": "application/json" } }
    );
  });
  mount();
  await screen.findByText("조회 완료 생고사리");
  expect(request.mock.calls.map(([url]) => String(url))).toEqual([
    "/api/v1/analysis/jobs",
    "/api/v1/jobs/price-job",
  ]);
});
