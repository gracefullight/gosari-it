import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalConfirmDialog } from "@/components/approval-confirm-dialog";
import { ChatShell } from "@/components/chat-shell";
import { MainSideNavigation } from "@/components/main-side-navigation";
import { ResultCard } from "@/components/result-card";
import { api } from "@/lib/gosari.api";
import type { Preview, ResultEnvelope } from "@/lib/gosari.types";

const EVIDENCE_HEADING = /근거 및 출처/;
const SURVEY_DATE = /2026-11-04/;
const EXTERNAL_LINK = /외부 링크/;
const OLD_PRICE_PROSE = /함께 안내|인증을 뜻하지/;
const INTERNAL_FIELDS = /internal-record|internal-created|unexpected_field|raw-json|revision/;
const NOTEBOOK_HEADING = /내 기록/;

vi.mock("@/components/weather-map-page", () => ({
  WeatherMapPage: ({ mode }: { mode: string }) => (
    <section aria-label="날씨 지도">{mode} 지도</section>
  ),
}));

let queryClient: QueryClient;
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});
afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.restoreAllMocks();
});

const envelope: ResultEnvelope = {
  schema_version: "1",
  request_id: "request",
  data_status: "complete",
  source_mode: "replay",
  action_status: null,
  link_status: "none",
  cache_resolution: "miss",
  requested_scope: {},
  effective_scope: {},
  observed_period: {},
  fetched_at: null,
  verified_on: "2026-11-05",
  result: {},
  evidence_ids: ["internal-evidence"],
  warnings: [],
  errors: [],
};

describe("Result display", () => {
  it("labels hourly observed rain separately from daily rain and preserves zero", () => {
    render(
      <ResultCard
        envelope={{
          ...envelope,
          source_mode: "fetched",
          result: {
            rain_period_label: "1시간 강수 (mm)",
            stations: [
              {
                station_name: "제주시",
                station_code: "jeju",
                observation_time: "2026-11-07T13:00:00+09:00",
                temperature_c: "14.4",
                day_rain_mm: null,
                rain_1h_mm: 0,
              },
            ],
          },
        }}
      />
    );
    expect(screen.getByRole("columnheader", { name: "1시간 강수 (mm)" })).toBeTruthy();
    expect(screen.queryByRole("columnheader", { name: "일강수 (mm)" })).toBeNull();
    expect(screen.getByRole("cell", { name: "0" })).toBeTruthy();
  });

  it("shows observation values without fetching or exposing internal evidence", () => {
    const evidence = vi.spyOn(api, "evidence");
    render(
      <ResultCard
        envelope={{
          ...envelope,
          result: {
            stations: [
              {
                station_name: "가파도",
                station_code: "test",
                observation_time: "2026-11-05",
                temperature_c: "17.5",
                day_rain_mm: "0",
              },
            ],
          },
        }}
      />
    );
    expect(screen.getByText("가파도")).toBeTruthy();
    expect(screen.getByText("17.5")).toBeTruthy();
    expect(screen.queryByText(EVIDENCE_HEADING)).toBeNull();
    expect(document.body.textContent).not.toContain("internal-evidence");
    expect(evidence).not.toHaveBeenCalled();
  });

  it("keeps prices, dates and links when a cached response contains old explanatory prose", () => {
    render(
      <ResultCard
        envelope={{
          ...envelope,
          result: {
            notice: "산림조합 임산물가격정보 공식 조회 링크와 조회 표본을 함께 안내합니다.",
            sample_cards: [
              {
                channel: "survey",
                title: "생산지 조사가",
                price_value: 11500,
                net_weight_value: 1000,
                price_as_of: "2026-11-04",
                source_url: "https://www.forestinfo.or.kr/",
                description: "제주산 인증을 뜻하지 않으며 출하기 입력값이 이후에도 표시될 수 있음.",
              },
            ],
          },
        }}
      />
    );
    expect(screen.getByText("11,500원 / kg")).toBeTruthy();
    expect(screen.getAllByText(SURVEY_DATE).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: EXTERNAL_LINK }).getAttribute("href")).toBe(
      "https://www.forestinfo.or.kr/"
    );
    expect(screen.queryByText(OLD_PRICE_PROSE)).toBeNull();
  });

  it("shows record contents in confirmations and keeps internal fields out", () => {
    const preview: Preview = {
      preview_id: "preview",
      action: "notebook.delete",
      target_id: "target",
      target_revision: 3,
      schema_version: "1",
      preview_hash: "hash",
      expires_at: "later",
      display_payload: {
        record_id: "internal-record",
        revision: 3,
        created_at: "internal-created",
        activity_text: "선흘 채취 기록",
        experience_date: "2026-04-12",
        unexpected_field: { secret: "raw-json" },
      },
    };
    render(<ApprovalConfirmDialog preview={preview} onClose={vi.fn()} onCommitted={vi.fn()} />);
    expect(screen.getByText("선흘 채취 기록")).toBeTruthy();
    expect(screen.getByText("2026-04-12")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(INTERNAL_FIELDS);
  });
});

function renderWorkspace() {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        entries: [],
        count: 0,
        drafts: [],
        regions: [],
        stations: [],
        result: { result: {} },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    )
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <Provider>
        <MainSideNavigation open onToggle={vi.fn()} onEndSession={vi.fn()} />
        <ChatShell />
      </Provider>
    </QueryClientProvider>
  );
}

describe("Workspace routes", () => {
  it("keeps an empty home idle without starting an analysis", () => {
    const run = vi.spyOn(api, "runAnalysis");
    renderWorkspace();
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
    expect(
      (screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement).disabled
    ).toBe(false);
    expect(run).not.toHaveBeenCalled();
  });

  it("updates the URL for menu navigation and responds to browser back", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "나들이" }));
    expect(window.location.pathname).toBe("/outing");
    expect(screen.getByRole("region", { name: "날씨 지도" }).textContent).toContain("outing");
    fireEvent.click(screen.getByRole("button", { name: "가격 조사" }));
    expect(window.location.pathname).toBe("/prices");
    await screen.findByRole("group", { name: "가격 종류" });
    fireEvent.click(screen.getByRole("button", { name: "내 수첩" }));
    expect(window.location.pathname).toBe("/notebook");
    expect(screen.getByRole("heading", { name: "내 수첩" })).toBeTruthy();
    await act(async () => {
      window.history.back();
    });
    await waitFor(() => expect(window.location.pathname).toBe("/prices"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "가격 조사" })).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "내 수첩" })).toBeNull();
  });

  it("opens a direct notebook write URL and separates the list", async () => {
    window.history.replaceState(null, "", "/notebook/new");
    renderWorkspace();
    await waitFor(() => expect(screen.getByRole("heading", { name: "새 기록" })).toBeTruthy());
    expect(screen.getByLabelText("채취 날짜")).toBeTruthy();
    expect(screen.queryByText("저장된 기록이 없습니다.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "목록으로" }));
    expect(window.location.pathname).toBe("/notebook");
    expect(screen.queryByLabelText("채취 날짜")).toBeNull();
    expect(screen.getByRole("heading", { name: NOTEBOOK_HEADING })).toBeTruthy();
  });

  it("handles a popstate URL change and shows unknown routes with a home action", async () => {
    renderWorkspace();
    act(() => {
      window.history.pushState(null, "", "/missing");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("heading", { name: "페이지를 찾을 수 없습니다" })).toBeTruthy();
    expect(screen.queryByLabelText("메시지 입력")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "홈으로" }));
    expect(window.location.pathname).toBe("/");
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();
  });
});
