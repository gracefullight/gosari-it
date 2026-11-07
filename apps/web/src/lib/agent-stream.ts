import type { AgentEventType, AgentStreamEvent } from "@/lib/gosari.types";
import { fetchWithSession } from "@/lib/session-bootstrap";

const EVENT_TYPES = new Set<AgentEventType>([
  "stage",
  "assistant_delta",
  "assistant_completed",
  "tool_started",
  "tool_completed",
  "tool_failed",
  "ui_spec",
  "personal_search",
  "personal_form",
  "error",
  "done",
]);
const NEWLINE = /\r\n|\r|\n/;
const LEADING_SPACE = /^ /;

export class AgentStreamDisconnectedError extends Error {
  constructor() {
    super("답변 연결이 끊겼습니다. 이어서 받을 수 있습니다.");
    this.name = "AgentStreamDisconnectedError";
  }
}

/** Read actual server events. The reader never fabricates text or submits a new job. */
export async function* readAgentEvents(
  jobId: string,
  options: { signal?: AbortSignal; lastEventId?: string } = {}
): AsyncGenerator<AgentStreamEvent> {
  const response = await fetchWithSession(`/api/v1/jobs/${encodeURIComponent(jobId)}/events`, {
    credentials: "same-origin",
    signal: options.signal,
    headers: {
      Accept: "text/event-stream",
      ...(options.lastEventId ? { "Last-Event-ID": options.lastEventId } : {}),
    },
  });
  if (!response.ok || !response.body) {
    if (response.status === 404)
      throw new Error("이 대화를 이어받을 수 없습니다. 다시 질문해 주세요.");
    throw new AgentStreamDisconnectedError();
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let ended = false;
  const seen = new Set<string>();
  const abort = () => {
    void reader.cancel();
  };
  options.signal?.addEventListener("abort", abort, { once: true });
  try {
    while (true) {
      options.signal?.throwIfAborted();
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // Normalize complete lines only; a CRLF may itself cross a network chunk.
      let boundary = findBoundary(buffer);
      while (boundary) {
        const frame = buffer.slice(0, boundary.start);
        buffer = buffer.slice(boundary.end);
        let type = "message";
        let id = "";
        const data: string[] = [];
        for (const line of frame.split(NEWLINE)) {
          if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("id:")) id = line.slice(3).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(LEADING_SPACE, ""));
        }
        if (data.length && EVENT_TYPES.has(type as AgentEventType)) {
          let raw: Record<string, unknown>;
          try {
            raw = JSON.parse(data.join("\n"));
          } catch {
            throw new AgentStreamDisconnectedError();
          }
          if (!raw || typeof raw !== "object" || raw.job_id !== jobId)
            throw new AgentStreamDisconnectedError();
          const eventId = typeof raw.event_id === "string" ? raw.event_id : id;
          if (!eventId) throw new AgentStreamDisconnectedError();
          if (!seen.has(eventId)) {
            seen.add(eventId);
            const event = { ...raw, type, event_id: eventId } as AgentStreamEvent;
            yield event;
            if (event.type === "done") {
              ended = true;
              return;
            }
          }
        }
        boundary = findBoundary(buffer);
      }
      if (done) break;
    }
    options.signal?.throwIfAborted();
    if (!ended) throw new AgentStreamDisconnectedError();
  } catch (error) {
    if (options.signal?.aborted) options.signal.throwIfAborted();
    if (
      error instanceof AgentStreamDisconnectedError ||
      (error instanceof Error && error.message.startsWith("이 대화"))
    )
      throw error;
    throw new AgentStreamDisconnectedError();
  } finally {
    options.signal?.removeEventListener("abort", abort);
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

const FRAME_BOUNDARY = /\r\n\r\n|\n\n|\r\r/;
function findBoundary(value: string): { start: number; end: number } | undefined {
  const found = FRAME_BOUNDARY.exec(value);
  return found ? { start: found.index, end: found.index + found[0].length } : undefined;
}
