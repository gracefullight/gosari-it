import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchWithSession: typeof import("@/lib/session-bootstrap").fetchWithSession;
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(async () => {
  vi.resetModules();
  window.localStorage.clear();
  window.localStorage.setItem("gosari_session_id", "old-session");
  ({ fetchWithSession } = await import("@/lib/session-bootstrap"));
});
afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("session recovery", () => {
  it("does not bootstrap valid requests", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ prices: [] }));
    expect(
      (await fetchWithSession("/api/v1/analysis/jobs", { method: "POST", body: "{}" })).ok
    ).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
    expect(new Headers(request.mock.calls[0][1]?.headers).get("X-Gosari-Session")).toBe(
      "old-session"
    );
  });

  it("recovers both the Orval and legacy API adapters with one shared bootstrap", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (url === "/api/v1/sessions/") return json({ session_id: "new-session" });
      const sid = new Headers(options?.headers).get("X-Gosari-Session");
      return sid === "new-session"
        ? json({ entries: [], result: { result: {} } })
        : json({ error: "SESSION_EXPIRED", message: "세션 만료" }, 401);
    });
    const { customFetch } = await import("@/lib/api/mutator");
    const { api } = await import("@/lib/gosari.api");
    const [generated, legacy] = await Promise.all([
      customFetch<{ status: number }>("/api/v1/analysis/jobs", { method: "POST", body: "{}" }),
      api.notebookList(),
    ]);
    expect(generated.status).toBe(200);
    expect(legacy.entries).toEqual([]);
    expect(request.mock.calls.filter(([url]) => url === "/api/v1/sessions/")).toHaveLength(1);
    expect(window.localStorage.getItem("gosari_session_id")).toBe("new-session");
    expect(request).toHaveBeenCalledTimes(5);
  });

  it("shares an explicit app bootstrap with concurrent recovery", async () => {
    let complete!: (response: Response) => void;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      if (url === "/api/v1/sessions/")
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      return new Headers(options?.headers).get("X-Gosari-Session") === "new-session"
        ? json({ entries: [] })
        : json({ error: "SESSION_REQUIRED" }, 401);
    });
    const startup = fetchWithSession("/api/v1/sessions/", { method: "POST" });
    const lookup = fetchWithSession("/api/v1/notebook/");
    await Promise.resolve();
    complete(json({ session_id: "new-session" }));
    const results = await Promise.all([startup, lookup]);
    expect(results.every((response) => response.ok)).toBe(true);
    expect(request.mock.calls.filter(([url]) => url === "/api/v1/sessions/")).toHaveLength(1);
  });

  it("retries the original request exactly once even if the new session is rejected", async () => {
    const request = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url) =>
        url === "/api/v1/sessions/"
          ? json({ session_id: "new-session" })
          : json({ error: "SESSION_REQUIRED" }, 401)
      );
    const response = await fetchWithSession("/api/v1/analysis/jobs", {
      method: "POST",
      body: "{}",
    });
    expect(response.status).toBe(401);
    expect(request).toHaveBeenCalledTimes(3);
  });

  it("does not retry consent or commit and does not reopen an explicitly closed session", async () => {
    const request = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url) =>
        url === "/api/v1/sessions/current"
          ? json({ status: "closed" })
          : json({ error: "SESSION_EXPIRED" }, 401)
      );
    await fetchWithSession("/api/v1/consents/", { method: "POST" });
    await fetchWithSession("/api/v1/notebook/commit", { method: "POST" });
    await fetchWithSession("/api/v1/sessions/current", { method: "DELETE" });
    await fetchWithSession("/api/v1/notebook/");
    expect(request).toHaveBeenCalledTimes(4);
    expect(request.mock.calls.some(([url]) => url === "/api/v1/sessions/")).toBe(false);
  });

  it("preserves the original API error when session bootstrap fails", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (url === "/api/v1/sessions/") throw new Error("network offline");
      return json({ error: "SESSION_EXPIRED", message: "기존 오류" }, 401);
    });
    const response = await fetchWithSession("/api/v1/notebook/recall", {
      method: "POST",
      body: "{}",
    });
    expect(await response.json()).toEqual({ error: "SESSION_EXPIRED", message: "기존 오류" });
    expect(request).toHaveBeenCalledTimes(2);
  });
});
