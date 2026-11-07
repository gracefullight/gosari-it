import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readAgentEvents } from "@/lib/agent-stream";
import { streamAnalysisJob } from "@/lib/analysis-jobs";
import { api } from "@/lib/gosari.api";
import type { JobResult } from "@/lib/gosari.types";
import { fetchWithSession } from "@/lib/session-bootstrap";

vi.mock("@/lib/session-bootstrap", () => ({ fetchWithSession: vi.fn() }));
afterEach(() => vi.resetAllMocks());
const encoder = new TextEncoder();
const job: JobResult = {
  job_id: "stream-job",
  request_id: "request",
  stage: "running",
  created_at: "2026-11-07",
  events: [],
  result: null,
  error: null,
};
const result = {
  schema_version: "1",
  request_id: "request",
  data_status: "complete" as const,
  source_mode: "replay" as const,
  action_status: null,
  link_status: "none",
  cache_resolution: "miss",
  requested_scope: {},
  effective_scope: {},
  observed_period: {},
  fetched_at: null,
  verified_on: "2026-11-05",
  result: {},
  evidence_ids: [],
  warnings: [],
  errors: [],
};
function frame(type: string, id: string, extra: Record<string, unknown> = {}) {
  return `id: ${id}\r\nevent: ${type}\r\ndata: ${JSON.stringify({ event_id: id, job_id: job.job_id, ...extra })}\r\n\r\n`;
}

describe("agent event stream", () => {
  it("cancels a job whose creation response arrives after the caller aborted", async () => {
    let respond!: (response: Response) => void;
    vi.mocked(fetchWithSession)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            respond = resolve;
          })
      )
      .mockResolvedValueOnce(new Response("{}"));
    const controller = new AbortController();
    const onEvent = vi.fn();
    const pending = api.runAnalysis(
      { operation: "retail_lookup", source_ids: ["retail_sample"] },
      undefined,
      { signal: controller.signal, onEvent }
    );
    controller.abort();
    respond(new Response(JSON.stringify(job)));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchWithSession).toHaveBeenCalledTimes(2);
    expect(fetchWithSession).toHaveBeenLastCalledWith(
      `/api/v1/jobs/${job.job_id}/cancel`,
      expect.objectContaining({ method: "POST" })
    );
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("delivers split UTF-8 deltas before completion, preserves named tool events and caches actual chunks", async () => {
    let writer!: ReadableStreamDefaultController<Uint8Array>;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        writer = controller;
      },
    });
    vi.mocked(fetchWithSession).mockResolvedValue(
      new Response(stream, { headers: { "Content-Type": "text/event-stream" } })
    );
    const client = new QueryClient();
    const events = vi.fn();
    const pending = streamAnalysisJob(job, { queryClient: client, onEvent: events });
    const bytes = encoder.encode(frame("assistant_delta", "e1", { text: "제주 고사리" }));
    for (const byte of bytes) writer.enqueue(new Uint8Array([byte]));
    await vi.waitFor(() => expect(events).toHaveBeenCalledTimes(1));
    expect(events.mock.calls[0][0].text).toBe("제주 고사리");
    expect(client.getQueryData(["analysis", "stream", job.job_id])).toHaveLength(1);
    writer.enqueue(
      encoder.encode(
        frame("tool_started", "e2", {
          tool_call_id: "call-1",
          name: "retail_lookup",
          label: "판매가 조회",
        })
      )
    );
    writer.enqueue(encoder.encode(frame("done", "e3", { stage: "completed", result })));
    writer.close();
    expect((await pending).result).toEqual(result);
    expect(events.mock.calls.map(([event]) => event.type)).toEqual([
      "assistant_delta",
      "tool_started",
      "done",
    ]);
    expect(fetchWithSession).toHaveBeenCalledTimes(1);
    client.clear();
  });

  it("deduplicates replayed IDs and sends the reconnect cursor without creating a job", async () => {
    const body =
      frame("assistant_delta", "e1", { text: "한 번" }) +
      frame("assistant_delta", "e1", { text: "한 번" }) +
      frame("done", "e2", { stage: "cancelled" });
    vi.mocked(fetchWithSession).mockResolvedValue(new Response(body));
    const received = [];
    for await (const event of readAgentEvents(job.job_id, { lastEventId: "prior" }))
      received.push(event);
    expect(received).toHaveLength(2);
    expect(fetchWithSession).toHaveBeenCalledWith(
      "/api/v1/jobs/stream-job/events",
      expect.objectContaining({ headers: expect.objectContaining({ "Last-Event-ID": "prior" }) })
    );
  });

  it("reports premature EOF as disconnected and never falls back to polling", async () => {
    vi.mocked(fetchWithSession).mockResolvedValue(
      new Response(frame("assistant_delta", "e1", { text: "받은 부분" }))
    );
    const callback = vi.fn();
    await expect(streamAnalysisJob(job, { onEvent: callback })).rejects.toMatchObject({
      name: "AgentStreamDisconnectedError",
    });
    expect(callback).toHaveBeenCalledOnce();
    expect(fetchWithSession).toHaveBeenCalledTimes(1);
  });

  it("cancels the reader immediately when aborted", async () => {
    const cancelled = vi.fn();
    const controller = new AbortController();
    vi.mocked(fetchWithSession).mockResolvedValue(
      new Response(new ReadableStream({ cancel: cancelled }))
    );
    const pending = streamAnalysisJob(job, { signal: controller.signal });
    const assertion = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await Promise.resolve();
    controller.abort();
    await assertion;
    expect(cancelled).toHaveBeenCalledOnce();
    expect(fetchWithSession).toHaveBeenCalledTimes(1);
  });
});
