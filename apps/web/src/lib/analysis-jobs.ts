import { experimental_streamedQuery, type QueryClient } from "@tanstack/react-query";
import { readPersonalForm, readPersonalSearchSummary } from "@/lib/agent-chat";
import { readAgentEvents } from "@/lib/agent-stream";
import type { AgentStreamEvent, JobResult } from "@/lib/gosari.types";
import { fetchWithSession } from "@/lib/session-bootstrap";

export interface AnalysisStreamOptions {
  conversationId?: string;
  signal?: AbortSignal;
  onProgress?: (job: JobResult) => void;
  onEvent?: (event: AgentStreamEvent) => void;
  queryClient?: QueryClient;
  lastEventId?: string;
}

export async function streamAnalysisJob(
  initial: JobResult,
  options: AnalysisStreamOptions
): Promise<JobResult> {
  let final = initial;
  let finished = false;
  options.onProgress?.(initial);
  async function* events(signal?: AbortSignal) {
    const combined =
      options.signal && signal
        ? AbortSignal.any([options.signal, signal])
        : (options.signal ?? signal);
    for await (const event of readAgentEvents(initial.job_id, {
      signal: combined,
      lastEventId: options.lastEventId,
    })) {
      options.onEvent?.(event);
      if (event.type === "personal_search")
        final = {
          ...final,
          personal_search:
            readPersonalSearchSummary(event.personal_search ?? event) ?? final.personal_search,
        };
      if (event.type === "personal_form")
        final = {
          ...final,
          personal_form:
            readPersonalForm(event.personal_form ?? event.feature) ?? final.personal_form,
        };
      if (event.type === "ui_spec" && event.spec) {
        final = {
          ...final,
          ui_spec: event.spec,
          ui_results: { ...final.ui_results, ...event.results },
          ui_selection_source: event.selection_source,
        };
      }
      if (event.type === "done") {
        finished = true;
        final = {
          ...final,
          stage: event.stage ?? "completed",
          result: event.result ?? null,
          error: event.error ?? null,
          model_usage: event.model_usage,
          ui_spec: event.ui_spec ?? final.ui_spec,
          ui_results: { ...final.ui_results, ...event.ui_results },
          ui_selection_source: event.ui_selection_source ?? final.ui_selection_source,
          personal_search:
            readPersonalSearchSummary(event.personal_search) ?? final.personal_search,
          personal_form: readPersonalForm(event.personal_form) ?? final.personal_form,
        };
      }
      yield event;
    }
  }
  if (options.queryClient) {
    await options.queryClient.fetchQuery({
      queryKey: ["analysis", "stream", initial.job_id],
      queryFn: experimental_streamedQuery({
        streamFn: ({ signal }) => events(signal),
        refetchMode: "append",
      }),
      staleTime: 0,
      gcTime: 30 * 60 * 1000,
      retry: false,
    });
  } else {
    for await (const _ of events()) {
      /* Deliver server events as soon as they arrive. */
    }
  }
  if (!finished) throw new Error("답변을 받지 못했습니다.");
  // A final read is only needed when an older server omits its terminal result.
  if (!final.result && final.stage !== "cancelled" && final.stage !== "failed") {
    const response = await fetchWithSession(`/api/v1/jobs/${encodeURIComponent(initial.job_id)}`, {
      signal: options.signal,
    });
    if (!response.ok) throw new Error("완료된 답변을 확인하지 못했습니다.");
    const completed = (await response.json()) as JobResult;
    final = {
      ...completed,
      personal_search:
        readPersonalSearchSummary(completed.personal_search) ?? final.personal_search,
      personal_form: readPersonalForm(completed.personal_form) ?? final.personal_form,
    };
  }
  options.onProgress?.(final);
  return final;
}

interface PendingAnalysisJob {
  job_id: string;
  stage: string;
  result?: unknown;
  error?: string | null;
}

export async function waitForAnalysisJob<T extends PendingAnalysisJob>(
  initial: T,
  signal?: AbortSignal,
  onProgress?: (job: T) => void
): Promise<T> {
  let job = initial;
  const terminal = new Set(["completed", "partial", "failed", "cancelled"]);
  onProgress?.(job);
  while (!job.result && !terminal.has(job.stage)) {
    signal?.throwIfAborted();
    await new Promise<void>((resolve, reject) => {
      const stop = () => {
        clearTimeout(timer);
        reject(new DOMException("조회가 취소되었습니다.", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal?.removeEventListener("abort", stop);
        resolve();
      }, 400);
      signal?.addEventListener("abort", stop, { once: true });
    });
    const response = await fetchWithSession(`/api/v1/jobs/${encodeURIComponent(job.job_id)}`, {
      credentials: "same-origin",
      signal,
    });
    if (!response.ok)
      throw new Error(
        response.status === 404
          ? "조회가 중단되었습니다. 다시 조회해 주세요."
          : "조회 상태를 확인하지 못했습니다."
      );
    job = (await response.json()) as T;
    onProgress?.(job);
  }
  return job;
}

export async function cancelAnalysisJob(jobId: string): Promise<void> {
  const response = await fetchWithSession(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("조회 취소에 실패했습니다.");
}
