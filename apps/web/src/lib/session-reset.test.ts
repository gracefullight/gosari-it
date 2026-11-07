import { afterEach, expect, it, vi } from "vitest";
import { api } from "@/lib/gosari.api";
import { fetchWithSession } from "@/lib/session-bootstrap";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

it("keeps the user's identity and recovery available after a failed reset", async () => {
  localStorage.setItem("gosari_session_id", "session-existing");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify({ error: "DATABASE_UNAVAILABLE", message: "저장소 연결 실패" }), {
      status: 503,
    })
  );
  await expect(api.endSession()).rejects.toThrow("저장소 연결 실패");
  expect(localStorage.getItem("gosari_session_id")).toBe("session-existing");
  fetch
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ error: "SESSION_REQUIRED" }), { status: 401 })
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ session_id: "session-restored" }), { status: 201 })
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ entries: [] })));
  expect((await fetchWithSession("/api/v1/notebook/")).ok).toBe(true);
  expect(localStorage.getItem("gosari_session_id")).toBe("session-restored");
});
