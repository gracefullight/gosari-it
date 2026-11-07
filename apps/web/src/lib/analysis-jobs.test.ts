import { afterEach, expect, it, vi } from "vitest";
import { cancelAnalysisJob, waitForAnalysisJob } from "@/lib/analysis-jobs";
import { fetchWithSession } from "@/lib/session-bootstrap";

vi.mock("@/lib/session-bootstrap", () => ({ fetchWithSession: vi.fn() }));
afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

it("waits for an accepted job and returns its final result", async () => {
  vi.useFakeTimers();
  const completed = { job_id: "job-one", stage: "completed", result: { result: { count: 2 } } };
  vi.mocked(fetchWithSession).mockResolvedValue(new Response(JSON.stringify(completed)));
  const progress = vi.fn();
  const result = waitForAnalysisJob(
    { job_id: "job-one", stage: "running", result: null },
    undefined,
    progress
  );
  await vi.runAllTimersAsync();
  expect(await result).toEqual(completed);
  expect(progress).toHaveBeenCalledTimes(2);
  expect(fetchWithSession).toHaveBeenCalledWith("/api/v1/jobs/job-one", expect.any(Object));
});

it("does not start more polls when the caller aborts", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const result = waitForAnalysisJob(
    { job_id: "job-two", stage: "running", result: null },
    controller.signal
  );
  const assertion = expect(result).rejects.toMatchObject({ name: "AbortError" });
  controller.abort();
  await assertion;
  await vi.runAllTimersAsync();
  expect(fetchWithSession).not.toHaveBeenCalled();
});

it("returns cancelled jobs and explicitly sends cancellation", async () => {
  const job = { job_id: "job-three", stage: "cancelled", result: null };
  expect(await waitForAnalysisJob(job)).toEqual(job);
  expect(fetchWithSession).not.toHaveBeenCalled();
  vi.mocked(fetchWithSession).mockResolvedValue(new Response("{}"));
  await cancelAnalysisJob(job.job_id);
  expect(fetchWithSession).toHaveBeenCalledWith(
    "/api/v1/jobs/job-three/cancel",
    expect.objectContaining({ method: "POST" })
  );
});
