import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AgentChatMessage } from "@/components/agent-chat-message";
import { emptyAgentState } from "@/lib/agent-chat";
import type { AgentToolCall, ResultEnvelope } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

vi.mock("@/hooks/use-chat", () => ({
  useChat: () => ({ resumeStream: vi.fn(), push: vi.fn(), confirmSpec: vi.fn() }),
}));
vi.mock("@/components/agent-ui-renderer", () => ({ AgentGeneratedUI: () => null }));
vi.mock("@/components/result-card", () => ({ ResultCard: () => <div>실제 결과</div> }));
afterEach(cleanup);

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "answer",
    role: "assistant",
    kind: "agent",
    stream: emptyAgentState(),
    ...overrides,
  };
}

it("shows dots only before assistant text and real tool activity begin", () => {
  const view = render(<AgentChatMessage message={message()} />);
  expect(screen.getByRole("status").textContent).toContain("답변 작성 중");
  view.rerender(<AgentChatMessage message={message({ text: "확인한 가격입니다." })} />);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByRole("region", { name: "AI 응답 본문" }).textContent).toBe(
    "확인한 가격입니다."
  );
  view.rerender(
    <AgentChatMessage
      message={message({
        stream: {
          ...emptyAgentState(),
          tools: [{ id: "one", name: "retail_lookup", label: "판매가 조회", status: "running" }],
        },
      })}
    />
  );
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByRole("region", { name: "AI 응답 본문" })).toBeNull();
});

it("groups actual calls into one closed trace and preserves ordered conditions and failures", () => {
  const tools: AgentToolCall[] = [
    {
      id: "first",
      name: "retail_lookup",
      label: "판매가 조회",
      status: "completed",
      summary: "표본 2건",
      conditions: { package_weight_unit: "100 g" },
    },
    {
      id: "second",
      name: "forecast_compare",
      label: "날씨 조회",
      status: "failed",
      error: "예보를 가져오지 못했습니다.",
    },
    {
      id: "third",
      name: "market_query",
      label: "도매가 조회",
      status: "running",
      conditions: { price_channel: "wholesale" },
    },
  ];
  const { container } = render(
    <AgentChatMessage
      message={message({
        text: "일부 결과를 확인했습니다.",
        stream: { ...emptyAgentState(), tools },
      })}
    />
  );
  const outer = container.querySelectorAll("article > details");
  expect(outer).toHaveLength(1);
  expect(container.querySelector("article")?.firstElementChild).toBe(outer[0]);
  expect(outer[0].hasAttribute("open")).toBe(false);
  expect(outer[0].querySelector("summary")?.textContent).toContain("도매가 조회 · 진행 중");
  const entries = Array.from(outer[0].querySelectorAll("ol > li"));
  expect(entries.map((entry) => entry.querySelector("div > span")?.textContent)).toEqual([
    "판매가 조회",
    "날씨 조회",
    "도매가 조회",
  ]);
  expect(entries[0].textContent).toContain("100 g");
  expect(entries[0].textContent).toContain("표본 2건");
  expect(entries[1].textContent).toContain("예보를 가져오지 못했습니다.");
  expect(screen.queryByRole("status")).toBeNull();
});

it("hides no-data result details while preserving the explanation and actual tool trace", () => {
  const emptyResult = {
    data_status: "no_data",
    result: {
      channel: "retail",
      reason: "NO_MATCHING_SAMPLE",
      matched_sample_count: 0,
      available_sample_count: 3,
      sample_cards: [],
      links: [],
    },
    warnings: [],
    errors: [],
  } as unknown as ResultEnvelope;
  render(
    <AgentChatMessage
      message={message({
        text: "조건에 맞는 표본을 찾지 못했습니다.",
        envelope: emptyResult,
        ui_results: { result_1: emptyResult },
        stream: {
          ...emptyAgentState(),
          status: "completed",
          tools: [
            {
              id: "empty",
              name: "retail_lookup",
              label: "판매가 조회",
              status: "completed",
              result: emptyResult,
            },
          ],
        },
      })}
    />
  );
  expect(screen.getByText("조건에 맞는 표본을 찾지 못했습니다.")).toBeTruthy();
  expect(screen.getByLabelText("도구 실행 내역")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "상세 보기" })).toBeNull();
});

it("keeps a cached tool-free answer free of trace controls and empty result cards", () => {
  const { container } = render(
    <AgentChatMessage
      message={message({
        text: "안녕하세요.",
        stream: { ...emptyAgentState(), status: "completed" },
      })}
    />
  );
  expect(container.querySelector("details")).toBeNull();
  expect(screen.queryByRole("region", { name: "조회 결과" })).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
});

it("keeps a zero-hit private search as assistant text without a details button", () => {
  render(
    <AgentChatMessage
      message={message({
        text: "저장된 관심 지역이 없습니다.",
        personal_search: { query: "", kind: "region", count: 0 },
        stream: { ...emptyAgentState(), status: "completed" },
      })}
    />
  );
  expect(screen.getByText("저장된 관심 지역이 없습니다.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "상세 보기" })).toBeNull();
});

it("renders streamed assistant markdown and leaves only the details button in its result row", () => {
  const envelope = {
    data_status: "complete",
    result: { stations: [{ rain_mm: 0 }] },
    warnings: [],
    errors: [],
  } as unknown as ResultEnvelope;
  const view = render(
    <AgentChatMessage message={message({ text: "**서귀포가 1위**입니다.", envelope })} />
  );
  expect(screen.getByText("서귀포가 1위").tagName).toBe("STRONG");
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByRole("region", { name: "조회 결과" }).textContent).toBe("상세 보기");
  view.rerender(
    <AgentChatMessage
      message={message({
        text: "**서귀포가 1위**입니다.",
        envelope,
        stream: { ...emptyAgentState(), status: "completed" },
      })}
    />
  );
  expect(screen.getByText("서귀포가 1위").tagName).toBe("STRONG");
});
