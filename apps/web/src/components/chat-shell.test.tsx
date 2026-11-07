import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalConfirmDialog } from "@/components/approval-confirm-dialog";
import { ChatShell } from "@/components/chat-shell";
import { MainSideNavigation } from "@/components/main-side-navigation";
import { ResultCard } from "@/components/result-card";
import { api } from "@/lib/gosari.api";
import type { AgentChatResponse, Preview, ResultEnvelope } from "@/lib/gosari.types";

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
  it("waits for terminal cancellation after stopping a disconnected answer", async () => {
    const job = {
      job_id: "disconnected-cancel-job",
      request_id: "request",
      stage: "running",
      created_at: "2026-11-07",
      events: [],
      result: null,
      error: null,
    };
    const chat = vi.spyOn(api, "chat").mockResolvedValue({ kind: "job", ...job });
    const getJob = vi.spyOn(api, "getJob").mockResolvedValue(job);
    renderWorkspace();
    const event = (type: string, id: string, data: Record<string, unknown>) =>
      `event: ${type}\ndata: ${JSON.stringify({ event_id: id, job_id: job.job_id, ...data })}\n\n`;
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const resumed = new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
      },
    });
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(
        new Response(event("assistant_delta", "dc1", { text: "남아 있는 답변" }))
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(job)))
      .mockResolvedValueOnce(new Response(resumed));
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "가격 조회" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    await screen.findByRole("button", { name: "이어서 받기" });
    fireEvent.click(screen.getByRole("button", { name: "답변 중지" }));
    await waitFor(() => expect(getJob).toHaveBeenCalledExactlyOnceWith(job.job_id));
    expect(screen.queryByText("답변을 중지했습니다.")).toBeNull();
    expect(await screen.findByText("취소를 요청했습니다.")).toBeTruthy();
    expect(screen.getByText("남아 있는 답변")).toBeTruthy();
    writer.enqueue(new TextEncoder().encode(event("done", "dc2", { stage: "cancelled" })));
    writer.close();
    expect(await screen.findByText("답변을 중지했습니다.")).toBeTruthy();
    expect(chat).toHaveBeenCalledOnce();
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(window.location.pathname).toBe("/");
  });

  it("runs an ambiguous tomorrow outing from inline conditions and keeps its answer in chat", async () => {
    vi.spyOn(api, "chat").mockResolvedValue({
      kind: "confirmation",
      preparation: {
        classification: "public",
        feature: "outing",
        needs_confirmation: true,
        form: {
          feature_hint: "outing",
          initial_values: { date: "2026-11-08" },
          questions: ["지역과 시각을 골라 주세요."],
        },
      },
    });
    const job = {
      job_id: "inline-outing-job",
      request_id: "inline-outing-request",
      stage: "completed",
      created_at: "2026-11-07",
      events: [],
      result: envelope,
      error: null,
    };
    const run = vi.spyOn(api, "runAnalysis").mockImplementation(async (_spec, _text, options) => {
      options?.onEvent?.({
        type: "assistant_delta",
        event_id: "outing-answer",
        job_id: job.job_id,
        text: "채팅에서 날씨를 확인했습니다.",
      });
      return job;
    });
    renderWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "내일 나들이" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    await screen.findByRole("form", { name: "채팅 나들이 조건" });
    fireEvent.change(screen.getByRole("combobox", { name: "지역" }), {
      target: { value: "aewol" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "시각" }), {
      target: { value: "09:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "이 조건으로 날씨 조회" }));
    expect(await screen.findByText("채팅에서 날씨를 확인했습니다.")).toBeTruthy();
    expect(run).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        operation: "outing_compare",
        candidates: [{ location_id: "aewol", date: "2026-11-08", time_slot: "09:00" }],
      }),
      expect.any(String),
      expect.objectContaining({ onEvent: expect.any(Function) })
    );
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByRole("heading", { name: "나들이" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "메시지 입력" })).toBeTruthy();
  });

  it("cancels a late chat job after reset instead of appending it to the new conversation", async () => {
    let respond!: (value: AgentChatResponse) => void;
    vi.spyOn(api, "chat").mockImplementation(
      () =>
        new Promise((resolve) => {
          respond = resolve;
        })
    );
    const stream = vi.spyOn(api, "streamJob");
    renderWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "판매가" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    fireEvent.click(screen.getByRole("button", { name: "새 대화 초기화" }));
    await act(async () =>
      respond({
        kind: "job",
        job_id: "late-job",
        request_id: "late-request",
        stage: "running",
        created_at: "2026-11-07",
        events: [],
        result: null,
        error: null,
      })
    );
    expect(stream).not.toHaveBeenCalled();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/v1/jobs/late-job/cancel",
      expect.objectContaining({ method: "POST" })
    );
    expect(screen.getByRole("heading", { name: "고사리잇" })).toBeTruthy();
    expect(screen.queryByRole("article", { name: "AI 답변" })).toBeNull();
    await waitFor(() =>
      expect(
        (screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement).disabled
      ).toBe(false)
    );
  });

  it("keeps partial text while a server-acknowledged cancellation finishes the stream", async () => {
    const job = {
      kind: "job" as const,
      job_id: "cancel-job",
      request_id: "cancel-request",
      stage: "running",
      created_at: "2026-11-07",
      events: [],
      result: null,
      error: null,
    };
    vi.spyOn(api, "chat").mockResolvedValue(job);
    renderWorkspace();
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
      },
    });
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(new Response(stream))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...job, stage: "running" })));
    const emit = (type: string, id: string, data: Record<string, unknown>) =>
      writer.enqueue(
        new TextEncoder().encode(
          `event: ${type}\ndata: ${JSON.stringify({ event_id: id, job_id: job.job_id, ...data })}\n\n`
        )
      );
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "도매 가격" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    await screen.findByRole("button", { name: "답변 중지" });
    emit("assistant_delta", "c1", { text: "지금 받은 문장" });
    expect(await screen.findByText("지금 받은 문장")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "답변 중지" }));
    await screen.findByText("취소를 요청했습니다.");
    expect(screen.queryByText("답변을 중지했습니다.")).toBeNull();
    emit("done", "c2", { stage: "cancelled" });
    writer.close();
    expect(await screen.findByText("답변을 중지했습니다.")).toBeTruthy();
    expect(screen.getByText("지금 받은 문장")).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    await waitFor(() =>
      expect(
        (screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement).disabled
      ).toBe(false)
    );
  });

  it("renders real SSE deltas before completion and keeps each actual tool call collapsed", async () => {
    const initial = {
      kind: "job" as const,
      job_id: "live-job",
      request_id: "live-request",
      stage: "running",
      created_at: "2026-11-07",
      events: [],
      result: null,
      error: null,
    };
    const chat = vi.spyOn(api, "chat").mockResolvedValue(initial);
    renderWorkspace();
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
      },
    });
    vi.mocked(globalThis.fetch).mockResolvedValue(
      new Response(body, { headers: { "Content-Type": "text/event-stream" } })
    );
    const emit = (type: string, eventId: string, data: Record<string, unknown>) =>
      writer.enqueue(
        new TextEncoder().encode(
          `event: ${type}\ndata: ${JSON.stringify({ event_id: eventId, job_id: initial.job_id, ...data })}\n\n`
        )
      );
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "고사리 판매가 알려줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    await screen.findByRole("button", { name: "답변 중지" });
    emit("assistant_delta", "s1", { text: "확인한 상품은 " });
    expect(await screen.findByText("확인한 상품은")).toBeTruthy();
    emit("tool_started", "s2", {
      tool_call_id: "retail-call",
      name: "retail_lookup",
      label: "판매가 조회",
      conditions: {
        price_channel: "retail",
        fresh_or_dried: "건고사리",
        api_key: "SHOULD_NOT_RENDER",
        private_note: "SHOULD_NOT_RENDER",
      },
    });
    const tool = (await screen.findByText("판매가 조회")).closest("details");
    expect(tool?.open).toBe(false);
    expect(document.body.textContent).not.toContain("SHOULD_NOT_RENDER");
    expect(
      (screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement).disabled
    ).toBe(true);
    const prices = {
      ...envelope,
      result: {
        sample_cards: [
          {
            channel: "retail",
            product: "스트리밍 고사리",
            price_value: 32500,
            net_weight_value: 200,
          },
        ],
      },
    };
    emit("tool_completed", "s3", {
      tool_call_id: "retail-call",
      name: "retail_lookup",
      summary: "상품 표본 1건",
      result: prices,
    });
    emit("tool_started", "s4", {
      tool_call_id: "survey-call",
      name: "survey_link",
      label: "조사가 조회",
      conditions: { price_channel: "survey" },
    });
    emit("tool_failed", "s5", {
      tool_call_id: "survey-call",
      name: "survey_link",
      message: "조사가를 가져오지 못했습니다.",
    });
    emit("assistant_completed", "s6", { text: "상품 표본 가격을 확인했습니다." });
    emit("done", "s7", { stage: "completed", result: prices });
    writer.close();
    await waitFor(() =>
      expect(
        (screen.getByRole("textbox", { name: "메시지 입력" }) as HTMLTextAreaElement).disabled
      ).toBe(false)
    );
    expect(screen.getByText("상품 표본 가격을 확인했습니다.")).toBeTruthy();
    expect(screen.queryByText("확인한 상품은")).toBeNull();
    expect(screen.getAllByText("스트리밍 고사리")).toHaveLength(1);
    expect(screen.getByText("실패")).toBeTruthy();
    expect(screen.getByText("조사가 조회").closest("details")?.open).toBe(false);
    fireEvent.click(screen.getByText("판매가 조회"));
    expect(within(tool!).getByText("상품 표본 1건")).toBeTruthy();
    expect(window.location.pathname).toBe("/");
    expect(chat).toHaveBeenCalledOnce();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(queryClient.getQueryData(["analysis", "stream", initial.job_id])).toHaveLength(7);
  });

  it("reconnects an interrupted answer to the same job without creating another analysis", async () => {
    const job = {
      job_id: "resume-job",
      request_id: "resume-request",
      stage: "running",
      created_at: "2026-11-07",
      events: [],
      result: null,
      error: null,
    };
    const chat = vi.spyOn(api, "chat").mockResolvedValue({ kind: "job", ...job });
    const getJob = vi.spyOn(api, "getJob").mockResolvedValue(job);
    renderWorkspace();
    const event = (type: string, id: string, data: Record<string, unknown>) =>
      `event: ${type}\ndata: ${JSON.stringify({ event_id: id, job_id: job.job_id, ...data })}\n\n`;
    vi.mocked(globalThis.fetch)
      .mockResolvedValueOnce(new Response(event("assistant_delta", "r1", { text: "앞부분" })))
      .mockResolvedValueOnce(
        new Response(
          event("assistant_delta", "r1", { text: "앞부분" }) +
            event("assistant_delta", "r2", { text: " 뒷부분" }) +
            event("done", "r3", { stage: "completed", result: envelope })
        )
      );
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "판매가 알려줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    fireEvent.click(await screen.findByRole("button", { name: "이어서 받기" }));
    expect(await screen.findByText("앞부분 뒷부분")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "이어서 받기" })).toBeNull());
    expect(chat).toHaveBeenCalledOnce();
    expect(getJob).toHaveBeenCalledExactlyOnceWith(job.job_id);
    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject(expect.anything());
    const headers = new Headers(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers);
    expect(headers.get("Last-Event-ID")).toBe("r1");
  });

  it("answers a generic price question with inline channel selection and chat result cards", async () => {
    vi.spyOn(api, "chat").mockResolvedValue({
      kind: "confirmation",
      preparation: {
        classification: "public",
        feature: "price",
        needs_confirmation: true,
        form: { feature_hint: "price", questions: ["어떤 가격을 볼까요?"] },
      },
    });
    const run = vi.spyOn(api, "runAnalysis").mockResolvedValue({
      job_id: "price-chat-job",
      request_id: "price-chat-request",
      stage: "completed",
      created_at: "2026-11-07T07:00:00Z",
      events: [],
      error: null,
      result: {
        ...envelope,
        result: {
          sample_cards: [
            {
              channel: "retail",
              product: "채팅 고사리",
              price_value: 32500,
              net_weight_value: 200,
              price_as_of: "2026-11-05",
            },
          ],
        },
      },
    });
    renderWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "제주 고사리가격" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    fireEvent.click(await screen.findByRole("button", { name: "판매가" }));
    fireEvent.click(screen.getByRole("button", { name: "가격 조회" }));
    expect(await screen.findByText("채팅 고사리")).toBeTruthy();
    expect(screen.getByText("32,500원 / 200g")).toBeTruthy();
    expect(window.location.pathname).toBe("/");
    expect(screen.getByRole("textbox", { name: "메시지 입력" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "가격 조사" })).toBeNull();
    expect(run).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ operation: "retail_lookup", price_channel: "retail" }),
      expect.any(String),
      expect.any(Object)
    );
  });

  it("runs a resolved retail question immediately and leaves its result in the conversation", async () => {
    const spec = {
      operation: "retail_lookup",
      source_ids: ["retail_sample"],
      price_channel: "retail",
    };
    vi.spyOn(api, "chat").mockResolvedValue({
      kind: "confirmation",
      preparation: {
        classification: "public",
        feature: "price",
        needs_confirmation: false,
        spec,
      },
    });
    const run = vi.spyOn(api, "runAnalysis").mockResolvedValue({
      job_id: "resolved-price-job",
      request_id: "resolved-price-request",
      stage: "completed",
      created_at: "2026-11-07T07:00:00Z",
      events: [],
      error: null,
      result: {
        ...envelope,
        result: {
          sample_cards: [
            {
              channel: "retail",
              product: "탐나오 고사리",
              price_value: 17000,
              net_weight_value: 100,
            },
          ],
        },
      },
    });
    renderWorkspace();
    fireEvent.change(screen.getByRole("textbox", { name: "메시지 입력" }), {
      target: { value: "탐나오 건고사리 가격" },
    });
    fireEvent.click(screen.getByRole("button", { name: "메시지 보내기" }));
    expect(await screen.findByText("탐나오 고사리")).toBeTruthy();
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByRole("button", { name: "가격 조회" })).toBeNull();
    expect(run).toHaveBeenCalledExactlyOnceWith(spec, "탐나오 건고사리 가격", expect.any(Object));
  });

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
