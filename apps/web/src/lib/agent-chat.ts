import type {
  AgentChatHistoryEntry,
  AgentChatState,
  AgentStreamEvent,
  AgentToolCall,
  PersonalFormFeature,
  PersonalSearchSummary,
} from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

const PERSONAL_SEARCH_KINDS = new Set(["region", "notebook", "share", "contact", "all"]);
export function readPersonalForm(value: unknown): PersonalFormFeature | undefined {
  return value === "notebook" || value === "region_compare" || value === "share"
    ? value
    : undefined;
}
export function readPersonalSearchSummary(value: unknown): PersonalSearchSummary | undefined {
  if (!value || typeof value !== "object") return undefined;
  const row = value as Record<string, unknown>;
  if (
    typeof row.query !== "string" ||
    row.query.length > 2000 ||
    typeof row.kind !== "string" ||
    !PERSONAL_SEARCH_KINDS.has(row.kind) ||
    typeof row.count !== "number" ||
    !Number.isSafeInteger(row.count) ||
    row.count < 0
  )
    return undefined;
  return { query: row.query, kind: row.kind as PersonalSearchSummary["kind"], count: row.count };
}

export function getAgentChatHistory(messages: ChatMessage[]): AgentChatHistoryEntry[] {
  return messages
    .filter(
      (message) =>
        !message.error &&
        !message.prepare &&
        !message.preview &&
        !!message.text?.trim() &&
        ((message.role === "user" && (!message.kind || message.kind === "text")) ||
          (message.role === "assistant" &&
            (message.kind === "text" ||
              (message.kind === "agent" && message.stream?.status === "completed"))))
    )
    .slice(-12)
    .map((message) => ({ role: message.role, content: message.text! }));
}

export function emptyAgentState(): AgentChatState {
  return { status: "streaming", seen_event_ids: [], tools: [] };
}

export function applyAgentEvent(message: ChatMessage, event: AgentStreamEvent): ChatMessage {
  const stream = message.stream ?? emptyAgentState();
  if (stream.seen_event_ids.includes(event.event_id)) return message;
  const next = {
    ...stream,
    job_id: event.job_id,
    last_event_id: event.event_id,
    seen_event_ids: [...stream.seen_event_ids, event.event_id],
  };
  const result: ChatMessage = { ...message, stream: next };
  if (event.type === "personal_search")
    result.personal_search =
      readPersonalSearchSummary(event.personal_search ?? event) ?? message.personal_search;
  if (event.type === "personal_form")
    result.personal_form =
      readPersonalForm(event.personal_form ?? event.feature) ?? message.personal_form;
  if (event.type === "assistant_delta" && typeof event.text === "string")
    result.text = (message.text ?? "") + event.text;
  if (event.type === "assistant_completed" && typeof event.text === "string")
    result.text = event.text;
  if (event.type === "stage") next.stage_message = event.safe_message ?? event.message;
  if (event.type === "ui_spec" && event.spec) {
    result.ui_spec = event.spec;
    result.ui_results = { ...message.ui_results, ...event.results };
    result.ui_selection_source = event.selection_source;
  }
  if (event.type.startsWith("tool_") && event.tool_call_id) {
    const current = stream.tools.find((tool) => tool.id === event.tool_call_id);
    const tool: AgentToolCall = {
      ...current,
      id: event.tool_call_id,
      name: event.name ?? current?.name ?? "",
      label: event.label ?? current?.label ?? "자료 조회",
      status:
        event.type === "tool_completed"
          ? "completed"
          : event.type === "tool_failed"
            ? "failed"
            : "running",
      conditions: event.conditions ?? current?.conditions,
      summary: event.summary ?? current?.summary,
      error:
        event.type === "tool_failed" ? (event.message ?? "자료를 가져오지 못했습니다.") : undefined,
      result: event.result ?? current?.result,
    };
    next.tools = current
      ? stream.tools.map((item) => (item.id === tool.id ? tool : item))
      : [...stream.tools, tool];
  }
  if (event.type === "error") {
    result.error = event.message ?? "답변을 받지 못했습니다.";
    next.status = "failed";
  }
  if (event.type === "done") {
    result.personal_form = readPersonalForm(event.personal_form) ?? result.personal_form;
    result.personal_search =
      readPersonalSearchSummary(event.personal_search) ?? result.personal_search;
    next.status =
      event.stage === "cancelled" ? "cancelled" : event.stage === "failed" ? "failed" : "completed";
    if (event.result) result.envelope = event.result;
    if (event.ui_spec) result.ui_spec = event.ui_spec;
    if (event.ui_results) result.ui_results = { ...result.ui_results, ...event.ui_results };
    if (event.ui_selection_source) result.ui_selection_source = event.ui_selection_source;
    if (event.error) result.error = event.error;
  }
  return result;
}
