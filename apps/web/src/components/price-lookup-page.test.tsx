import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PriceCardList } from "@/components/price-card-list";
import { PriceLookupPage } from "@/components/price-lookup-page";

let queryClient: QueryClient;
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
