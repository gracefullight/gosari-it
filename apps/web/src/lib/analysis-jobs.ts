import { fetchWithSession } from "@/lib/session-bootstrap";

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
