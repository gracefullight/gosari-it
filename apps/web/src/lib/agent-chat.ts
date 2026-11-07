import type { AgentChatState, AgentStreamEvent, AgentToolCall } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

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
  if (event.type === "assistant_delta" && typeof event.text === "string")
    result.text = (message.text ?? "") + event.text;
  if (event.type === "assistant_completed" && typeof event.text === "string")
    result.text = event.text;
  if (event.type === "stage") next.stage_message = event.safe_message ?? event.message;
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
    next.status =
      event.stage === "cancelled" ? "cancelled" : event.stage === "failed" ? "failed" : "completed";
    if (event.result) result.envelope = event.result;
    if (event.error) result.error = event.error;
  }
  return result;
}
