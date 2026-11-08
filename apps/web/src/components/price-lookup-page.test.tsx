import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { getDefaultStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as datePickerField from "@/components/date-picker-field";
import { PriceCardList } from "@/components/price-card-list";
import { PriceLookupPage } from "@/components/price-lookup-page";
import { priceLookupStateAtom } from "@/stores/price-lookup.atoms";

let queryClient: QueryClient;
beforeEach(() => getDefaultStore().set(priceLookupStateAtom, null));
afterEach(() => {
  cleanup();
  queryClient?.clear();
  vi.restoreAllMocks();
});

function mountPrices() {
  return render(
    <QueryClientProvider client={queryClient}>
      <PriceLookupPage />
    </QueryClientProvider>
  );
}

function mockPrices() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
    const body = JSON.parse(String(init?.body)) as { spec: { price_channel: string } };
    const survey = body.spec.price_channel === "survey";
    return new Response(
      JSON.stringify({
        job_id: "job",
        request_id: "request",
        stage: "completed",
        created_at: "now",
        result: {
          request_id: "request",
          result: {
            sample_cards: [
              {
                channel: body.spec.price_channel,
                title: survey ? "생산지 조사가" : "제주 건고사리",
                price_value: survey ? 11500 : 32500,
                net_weight_value: 1000,
                price_as_of: "2026-11-04",
              },
            ],
          },
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  });
}

describe("PriceLookupPage cache", () => {
  it("restores its channel, applied conditions, labels, draft and price basis without another request", async () => {
    queryClient = new QueryClient();
    vi.spyOn(datePickerField, "DatePickerField").mockImplementation(
      ({ id, value, onChange, "aria-label": label }) => (
        <input
          id={id}
          aria-label={label}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    );
    const options = {
      markets: [
        { value: "110001", label: "서울가락" },
        { value: "210001", label: "부산엄궁" },
      ],
      forms: [{ value: "생고사리", label: "생고사리" }],
      grades: [{ value: "grade-a", label: "특등급" }],
      packages: [{ value: "package-a", label: "상자" }],
      weights: [{ value: "200g", label: "200g" }],
    };
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const { spec } = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify({
          job_id: "cached-price",
          request_id: "request",
          stage: "completed",
          result: {
            request_id: "request",
            result: {
              options: spec.grade ? { ...options, grades: [], packages: [], weights: [] } : options,
              price_cards: [
                {
                  row_id: JSON.stringify(spec),
                  channel: spec.price_channel,
                  product: spec.grade ? "적용 조건 고사리" : "기본 고사리",
                  price_value: 5000,
                  net_weight_value: 200,
                  price_per_kg_value: 25000,
                  price_as_of: spec.settlement_date ?? "2026-11-04",
                },
              ],
            },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    });
    let view = mountPrices();
    await screen.findByText("기본 고사리");
    fireEvent.click(screen.getByRole("button", { name: "도매 거래" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "가격 조회" }).hasAttribute("disabled")).toBe(false)
    );
    fireEvent.click(screen.getByText("세부 조건"));
    fireEvent.change(screen.getByLabelText("가격 시작일"), { target: { value: "2026-04-14" } });
    fireEvent.change(screen.getByLabelText("가격 종료일"), { target: { value: "2026-04-15" } });
    fireEvent.change(screen.getByLabelText("시장", { exact: true }), {
      target: { value: "210001" },
    });
    fireEvent.change(screen.getByLabelText("고사리 종류"), { target: { value: "생고사리" } });
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "grade-a" } });
    fireEvent.change(screen.getByLabelText("포장"), { target: { value: "package-a" } });
    fireEvent.change(screen.getByLabelText("단량"), { target: { value: "200g" } });
    fireEvent.change(screen.getByLabelText("산지명"), { target: { value: "제주" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await screen.findByText("적용 조건 고사리");
    fireEvent.click(screen.getByRole("button", { name: "1kg 환산" }));
    view.unmount();
    view = mountPrices();
    expect(screen.getByRole("button", { name: "도매 거래" }).getAttribute("aria-pressed")).toBe(
      "true"
    );
    expect(screen.getByRole("button", { name: "조회 조건 변경" })).toBeTruthy();
    expect(screen.getByText("적용 조건 고사리")).toBeTruthy();
    expect(screen.getByText("25,000원 / kg")).toBeTruthy();
    expect(screen.getByRole("button", { name: "1kg 환산" }).getAttribute("aria-pressed")).toBe(
      "true"
    );
    expect(
      screen.getByText(
        (text, element) =>
          element?.tagName === "P" &&
          text.includes("부산엄궁") &&
          text.includes("특등급") &&
          text.includes("상자")
      )
    ).toBeTruthy();
    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByRole("button", { name: "조회 조건 변경" }));
    expect(screen.getByText("세부 조건").closest("details")?.open).toBe(true);
    fireEvent.change(screen.getByLabelText("가격 시작일"), { target: { value: "2026-04-13" } });
    fireEvent.change(screen.getByLabelText("시장", { exact: true }), {
      target: { value: "110001" },
    });
    fireEvent.change(screen.getByLabelText("산지명"), { target: { value: "서귀포" } });
    view.unmount();
    view = mountPrices();
    expect((screen.getByLabelText("가격 시작일") as HTMLInputElement).value).toBe("2026-04-13");
    expect((screen.getByLabelText("시장", { exact: true }) as HTMLSelectElement).value).toBe(
      "110001"
    );
    expect((screen.getByLabelText("산지명") as HTMLInputElement).value).toBe("서귀포");
    expect(
      (screen.getByLabelText("등급") as HTMLSelectElement).selectedOptions[0].textContent
    ).toBe("특등급");
    expect(
      (screen.getByLabelText("포장") as HTMLSelectElement).selectedOptions[0].textContent
    ).toBe("상자");
    expect(screen.getByText("적용 조건 고사리")).toBeTruthy();
    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(4));
    expect(JSON.parse(String(request.mock.calls[3][1]?.body)).spec).toMatchObject({
      settlement_date: "2026-04-13",
      settlement_date_end: "2026-04-15",
      market_ids: ["110001"],
      origin_filter: "서귀포",
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "새로고침" }).hasAttribute("disabled")).toBe(false)
    );
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(5));
    view.unmount();
  });

  it("retains applied option labels after an empty response and clears only extra conditions", async () => {
    queryClient = new QueryClient();
    const requests: Record<string, unknown>[] = [];
    const options = {
      markets: [{ value: "110001", label: "서울가락" }],
      forms: [{ value: "생고사리", label: "생고사리" }],
      grades: [{ value: "grade-a", label: "특등급" }],
      packages: [{ value: "package-a", label: "상자" }],
      weights: [{ value: "200g", label: "200g" }],
    };
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const spec = JSON.parse(String(init?.body)).spec as Record<string, unknown>;
      requests.push(spec);
      return new Response(
        JSON.stringify({
          job_id: "job",
          request_id: "request",
          stage: "completed",
          created_at: "now",
          result: {
            request_id: "request",
            result: {
              price_cards: [],
              options: spec.grade ? { ...options, grades: [], packages: [], weights: [] } : options,
            },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    });
    const view = render(
      <QueryClientProvider client={queryClient}>
        <PriceLookupPage initialChannel="wholesale" />
      </QueryClientProvider>
    );
    await screen.findByText("선택한 날짜·시장에서 조건에 맞는 거래가 없습니다.");
    fireEvent.click(screen.getByText("세부 조건"));
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "grade-a" } });
    fireEvent.change(screen.getByLabelText("포장"), { target: { value: "package-a" } });
    fireEvent.change(screen.getByLabelText("단량"), { target: { value: "200g" } });
    fireEvent.change(screen.getByLabelText("산지명"), { target: { value: "제주" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await screen.findByText(
      (text, element) =>
        element?.tagName === "P" &&
        text.includes("특등급") &&
        text.includes("상자") &&
        text.includes("200g") &&
        text.includes("제주")
    );
    fireEvent.click(screen.getByRole("button", { name: "조회 조건 변경" }));
    expect(
      (screen.getByLabelText("등급") as HTMLSelectElement).selectedOptions[0].textContent
    ).toBe("특등급");
    expect(
      (screen.getByLabelText("포장") as HTMLSelectElement).selectedOptions[0].textContent
    ).toBe("상자");
    for (let repeat = 0; repeat < 3; repeat += 1) {
      fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
      await screen.findByText(
        (text, element) =>
          element?.tagName === "P" && text.includes("특등급") && text.includes("상자")
      );
      await act(async () => {});
      expect(request).toHaveBeenCalledTimes(2);
      fireEvent.click(screen.getByRole("button", { name: "조회 조건 변경" }));
      expect(
        (screen.getByLabelText("등급") as HTMLSelectElement).selectedOptions[0].textContent
      ).toBe("특등급");
      expect(
        (screen.getByLabelText("포장") as HTMLSelectElement).selectedOptions[0].textContent
      ).toBe("상자");
    }
    view.unmount();
    mountPrices();
    fireEvent.click(screen.getByRole("button", { name: "세부 조건 지우기" }));
    await screen.findByRole("button", { name: "날짜·시장 바꾸기" });
    expect((screen.getByLabelText("등급") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("포장") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("단량") as HTMLSelectElement).value).toBe("");
    expect((screen.getByLabelText("산지명") as HTMLInputElement).value).toBe("");
    expect(requests[1]).toEqual(
      expect.objectContaining({
        grade: "grade-a",
        package_code: "package-a",
        package_weight_unit: "200g",
        origin_filter: "제주",
        market_ids: ["110001"],
      })
    );
    expect(requests[0].settlement_date).toBe(requests[1].settlement_date);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("clears only extra conditions while retaining an unsubmitted date, market and form draft", async () => {
    queryClient = new QueryClient();
    vi.spyOn(datePickerField, "DatePickerField").mockImplementation(
      ({ id, value, onChange, "aria-label": label }) => (
        <input
          id={id}
          aria-label={label}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      )
    );
    const options = {
      markets: [
        { value: "110001", label: "서울가락" },
        { value: "210001", label: "부산엄궁" },
      ],
      forms: [
        { value: "생고사리", label: "생고사리" },
        { value: "건고사리", label: "건고사리" },
      ],
      grades: [{ value: "grade-a", label: "특등급" }],
      packages: [{ value: "package-a", label: "상자" }],
      weights: [{ value: "200g", label: "200g" }],
    };
    const requests: Record<string, unknown>[] = [];
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const spec = JSON.parse(String(init?.body)).spec as Record<string, unknown>;
      requests.push(spec);
      return new Response(
        JSON.stringify({
          job_id: "job-draft",
          request_id: "request-draft",
          stage: "completed",
          created_at: "now",
          result: {
            request_id: "request-draft",
            result: {
              price_cards: [],
              options: spec.grade ? { ...options, grades: [], packages: [], weights: [] } : options,
            },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    });
    render(
      <QueryClientProvider client={queryClient}>
        <PriceLookupPage initialChannel="wholesale" />
      </QueryClientProvider>
    );
    await screen.findByText("선택한 날짜·시장에서 조건에 맞는 거래가 없습니다.");
    const appliedDate = (screen.getByLabelText("가격 시작일") as HTMLInputElement).value;
    fireEvent.click(screen.getByText("세부 조건"));
    fireEvent.change(screen.getByLabelText("등급"), { target: { value: "grade-a" } });
    fireEvent.change(screen.getByLabelText("포장"), { target: { value: "package-a" } });
    fireEvent.change(screen.getByLabelText("단량"), { target: { value: "200g" } });
    fireEvent.change(screen.getByLabelText("산지명"), { target: { value: "제주" } });
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await screen.findByRole("button", { name: "세부 조건 지우기" });
    fireEvent.click(await screen.findByRole("button", { name: "조회 조건 변경" }));
    const draftDate = new Date(`${appliedDate}T12:00:00Z`);
    draftDate.setUTCDate(draftDate.getUTCDate() - 1);
    const newDate = draftDate.toISOString().slice(0, 10);
    fireEvent.change(screen.getByLabelText("가격 시작일"), { target: { value: newDate } });
    fireEvent.change(screen.getByLabelText("가격 종료일"), { target: { value: newDate } });
    fireEvent.change(screen.getByLabelText("시장", { exact: true }), {
      target: { value: "210001" },
    });
    fireEvent.change(screen.getByLabelText("고사리 종류"), { target: { value: "건고사리" } });
    cleanup();
    mountPrices();
    fireEvent.click(screen.getByRole("button", { name: "세부 조건 지우기" }));
    expect(screen.getByRole("button", { name: "가격 조회" })).toBeTruthy();
    await screen.findByRole("button", { name: "날짜·시장 바꾸기" });
    expect((screen.getByLabelText("가격 시작일") as HTMLInputElement).value).toBe(newDate);
    expect((screen.getByLabelText("가격 종료일") as HTMLInputElement).value).toBe(newDate);
    expect((screen.getByLabelText("시장", { exact: true }) as HTMLSelectElement).value).toBe(
      "210001"
    );
    expect((screen.getByLabelText("고사리 종류") as HTMLSelectElement).value).toBe("건고사리");
    for (const label of ["등급", "포장", "단량", "산지명"]) {
      expect((screen.getByLabelText(label) as HTMLInputElement | HTMLSelectElement).value).toBe("");
    }
    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(2);
    expect(requests[1]).toEqual(
      expect.objectContaining({
        settlement_date: appliedDate,
        market_ids: ["110001"],
        grade: "grade-a",
      })
    );
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(3));
    expect(requests[2]).toEqual(
      expect.objectContaining({
        settlement_date: newDate,
        settlement_date_end: newDate,
        market_ids: ["210001"],
        fresh_or_dried: "건고사리",
        grade: "",
        package_code: "",
        package_weight_unit: "",
        origin_filter: "",
      })
    );
  });

  it("reuses each channel after switching and remounting, and refreshes explicitly", async () => {
    queryClient = new QueryClient();
    const request = mockPrices();
    const first = mountPrices();
    await screen.findByText("제주 건고사리");
    fireEvent.click(screen.getByRole("button", { name: "지역 조사가" }));
    await screen.findByText("생산지 조사가");
    expect(request).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "소매 판매가" }));
    expect(screen.getByText("제주 건고사리")).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(2);
    first.unmount();
    mountPrices();
    expect(screen.getByText("제주 건고사리")).toBeTruthy();
    await act(async () => {});
    expect(request).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(3));
    expect(String(request.mock.calls[0][0])).toBe("/api/v1/analysis/jobs");
  });

  it("does not cache a failed request as an empty result", async () => {
    queryClient = new QueryClient();
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "SOURCE_UNAVAILABLE", message: "가격 조회 실패" }), {
        status: 503,
      })
    );
    mountPrices();
    await screen.findByText("가격 조회 실패");
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("조회된 가격이 없습니다.")).toBeNull();
  });
});

it("keeps price and date prominent while moving calculations and fees into collapsed details", () => {
  render(
    <PriceCardList
      cards={[
        {
          channel: "retail",
          product: "제주 건고사리",
          price_value: 32500,
          net_weight_value: 200,
          price_as_of: "2026-11-04",
          price_per_kg_value: 162500,
          shipping_value: 3000,
          coupon_price: 30000,
          coupon_condition: "회원",
          conversion_formula: "32,500원 ÷ 0.2kg",
        },
      ]}
    />
  );
  expect(screen.getByText("32,500원 / 200g")).toBeTruthy();
  const details = screen.getByText("세부정보").closest("details");
  expect(details?.open).toBe(false);
  expect(details?.textContent).toContain("162,500원/kg");
  expect(details?.textContent).toContain("3,000원");
  expect(details?.textContent).toContain("30,000원");
});

it("keeps the external source and all price details available from the compact result row", () => {
  render(
    <PriceCardList
      cards={[
        {
          channel: "retail",
          product: "제주 건고사리",
          net_weight_value: 200,
          price_value: 32500,
          price_as_of: "2026-11-04",
          shipping_value: 3000,
          source_url: "https://example.com/product",
          coupon_price: 30000,
        },
      ]}
    />
  );
  const summary = screen.getByText("세부정보").closest("summary");
  const details = summary?.closest("details");
  expect(details?.open).toBe(false);
  expect(summary?.textContent).toContain("32,500원 / 200g");
  expect(summary?.textContent).toContain("2026-11-04");
  const link = screen.getByRole("link", { name: "제주 건고사리 외부 링크" });
  expect(summary?.contains(link)).toBe(true);
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  fireEvent.click(summary as HTMLElement);
  expect(details?.open).toBe(true);
  expect(details?.textContent).toContain("3,000원");
  expect(details?.textContent).toContain("30,000원");
});

it("compares different package weights using one shared 1kg display switch", () => {
  render(
    <PriceCardList
      cards={[
        {
          channel: "retail",
          product: "200g 상품",
          price_value: 32500,
          net_weight_value: 200,
          price_per_kg_value: 162500,
        },
        {
          channel: "retail",
          product: "80g 상품",
          price_value: 14800,
          net_weight_value: 80,
          price_per_kg_value: 185000,
        },
        { channel: "retail", product: "중량 미확인 상품", price_value: 5000 },
      ]}
    />
  );
  expect(screen.getByText("32,500원 / 200g")).toBeTruthy();
  expect(screen.getByText("14,800원 / 80g")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "1kg 환산" }));
  expect(screen.getByText("162,500원 / kg")).toBeTruthy();
  expect(screen.getByText("185,000원 / kg")).toBeTruthy();
  expect(screen.getByText("환산가 없음")).toBeTruthy();
  expect(screen.getByRole("button", { name: "1kg 환산" }).getAttribute("aria-pressed")).toBe(
    "true"
  );
  fireEvent.click(screen.getByRole("button", { name: "상품 가격" }));
  expect(screen.getByText("32,500원 / 200g")).toBeTruthy();
  expect(screen.getByText("5,000원")).toBeTruthy();
});
