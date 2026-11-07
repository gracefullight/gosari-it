import { expect, it } from "vitest";
import {
  applyAgentEvent,
  applyAgentJobEvents,
  emptyAgentState,
  getAgentChatHistory,
  readPersonalForm,
  readPersonalSearchSummary,
} from "@/lib/agent-chat";
import type { AgentStreamEvent, AgentUISpec, ResultEnvelope } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

const spec: AgentUISpec = {
  root: "root",
  elements: { root: { type: "PriceResults", props: { resultRef: "result_1" }, children: [] } },
};
const result = { result: { price_cards: [{ price_value: 17000 }] } } as unknown as ResultEnvelope;
const start: ChatMessage = {
  id: "answer",
  role: "assistant",
  kind: "agent",
  stream: emptyAgentState(),
};
const event: AgentStreamEvent = {
  type: "ui_spec",
  event_id: "ui-one",
  job_id: "job",
  spec,
  results: { result_1: result },
  selection_source: "model",
};

it("binds a UI selection to actual result objects and ignores a replay of the same event", () => {
  const first = applyAgentEvent(start, event);
  expect(first.ui_spec).toBe(spec);
  expect(first.ui_results?.result_1).toBe(result);
  expect(first.ui_selection_source).toBe("model");
  expect(applyAgentEvent(first, { ...event, results: {} })).toBe(first);
});

it("preserves the selected UI and bindings when the terminal event arrives", () => {
  const first = applyAgentEvent(start, event);
  const final = applyAgentEvent(first, {
    type: "done",
    event_id: "done",
    job_id: "job",
    stage: "completed",
    result,
  });
  expect(final.ui_spec).toBe(spec);
  expect(final.ui_results?.result_1).toBe(result);
  expect(final.stream?.status).toBe("completed");
});

it("restores tool results from nested terminal job events without replaying or accepting another job", () => {
  const job = {
    job_id: "job",
    events: [
      {
        event_id: "start",
        job_id: "job",
        event_type: "tool_started",
        payload: {
          tool_call_id: "street",
          name: "open_street_view",
          label: "거리뷰",
          conditions: { location_id: "aws:965" },
        },
      },
      {
        event_id: "end",
        job_id: "job",
        event_type: "tool_completed",
        payload: { tool_call_id: "street", name: "open_street_view", result },
      },
      {
        event_id: "other",
        job_id: "another-job",
        event_type: "tool_started",
        payload: { tool_call_id: "wrong" },
      },
    ],
  };
  const restored = applyAgentJobEvents(start, job);
  expect(restored.stream?.tools).toHaveLength(1);
  expect(restored.stream?.tools[0]).toMatchObject({
    id: "street",
    status: "completed",
    result,
    conditions: { location_id: "aws:965" },
  });
  expect(applyAgentJobEvents(restored, job)).toBe(restored);
  const partial = applyAgentEvent(start, {
    type: "tool_completed",
    event_id: "end",
    job_id: "job",
    tool_call_id: "street",
    result,
  });
  expect(applyAgentJobEvents(partial, job).stream?.tools[0].status).toBe("completed");
});

it("preserves search metadata once and excludes raw records from metadata and history", () => {
  const search = {
    query: "",
    kind: "region",
    count: 1,
    records: [{ id: "PRIVATE-ID", title: "PRIVATE-TITLE", latitude: 33.123456 }],
  };
  const metadata = readPersonalSearchSummary(search);
  expect(metadata).toEqual({ query: "", kind: "region", count: 1 });
  const event: AgentStreamEvent = {
    type: "personal_search",
    event_id: "personal-one",
    job_id: "job",
    query: "",
    kind: "region",
    count: 1,
  };
  const first = applyAgentEvent(start, event);
  expect(first.personal_search).toEqual(metadata);
  expect(applyAgentEvent(first, event)).toBe(first);
  const final = applyAgentEvent(first, {
    type: "done",
    event_id: "personal-done",
    job_id: "job",
    stage: "completed",
    personal_search: { query: "", kind: "region", count: 0 },
  });
  expect(final.personal_search?.count).toBe(0);
  expect(getAgentChatHistory([{ ...final, text: "저장된 지역을 확인했습니다." }])).toEqual([
    { role: "assistant", content: "저장된 지역을 확인했습니다." },
  ]);
  expect(readPersonalSearchSummary({ query: "", kind: "system", count: 1 })).toBeUndefined();
  expect(readPersonalSearchSummary({ query: "", kind: "all", count: -1 })).toBeUndefined();
});

it("accepts only the three existing personal form features from stream and terminal metadata", () => {
  const opened = applyAgentEvent(start, {
    type: "personal_form",
    event_id: "form-one",
    job_id: "job",
    feature: "notebook",
  });
  expect(opened.personal_form).toBe("notebook");
  expect(
    applyAgentEvent(opened, {
      type: "done",
      event_id: "form-done",
      job_id: "job",
      stage: "completed",
      personal_form: "share",
    }).personal_form
  ).toBe("share");
  expect(readPersonalForm("system")).toBeUndefined();
  expect(readPersonalForm({ feature: "notebook", record: "PRIVATE" })).toBeUndefined();
});

it("restores only the latest twelve user and completed assistant texts, without tool or private payloads", () => {
  const previous: ChatMessage[] = Array.from({ length: 14 }, (_, index) => ({
    id: `user-${index}`,
    role: "user",
    kind: "text",
    text: `질문 ${index}`,
  }));
  previous.push(
    { ...start, id: "running", text: "미완료", stream: emptyAgentState() },
    { ...start, id: "failed", text: "실패", error: "오류" },
    { id: "private", role: "assistant", kind: "personal-form", text: "개인 폼" },
    { id: "preview", role: "assistant", kind: "preview", text: "승인 내용" },
    {
      ...start,
      id: "done",
      text: "성산 내일 예보입니다.",
      stream: { ...emptyAgentState(), status: "completed" },
      envelope: result,
      ui_results: { result_1: result },
    }
  );
  const history = getAgentChatHistory(previous);
  expect(history).toHaveLength(12);
  expect(history[0]).toEqual({ role: "user", content: "질문 3" });
  expect(history.at(-1)).toEqual({ role: "assistant", content: "성산 내일 예보입니다." });
  expect(history.every((entry) => Object.keys(entry).sort().join() === "content,role")).toBe(true);
});
