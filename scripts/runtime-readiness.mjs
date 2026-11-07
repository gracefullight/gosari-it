import { setTimeout as delay } from "node:timers/promises";

export function isDatabaseReady(value) {
  return value?.status === "ready" && value?.database === "ok";
}

export async function readCapabilities({ port, fetchImpl = fetch }) {
  const response = await fetchImpl(`http://127.0.0.1:${port}/api/v1/capabilities/`, {
    signal: AbortSignal.timeout(3_000),
  });
  if (!response.ok) throw new Error(`상태 확인 실패: HTTP ${response.status}`);
  const value = await response.json();
  if (typeof value?.profile !== "string" || !["live", "replay", "limited"].includes(value?.runtime_mode)) {
    throw new Error("상태 응답 형식을 확인할 수 없습니다.");
  }
  return value;
}

export async function waitForReadiness({
  port,
  timeoutMs = 60_000,
  intervalMs = 1_000,
  fetchImpl = fetch,
}) {
  const deadline = Date.now() + timeoutMs;
  let lastFailure = "응답 없음";
  while (Date.now() < deadline) {
    try {
      const response = await fetchImpl(`http://127.0.0.1:${port}/api/v1/health/ready`, {
        signal: AbortSignal.timeout(Math.max(1, Math.min(3_000, deadline - Date.now()))),
      });
      if (!response.ok) throw new Error(`readiness HTTP ${response.status}`);
      const value = await response.json();
      if (!isDatabaseReady(value)) throw new Error("DB 또는 앱 준비 미완료");
      const ui = await fetchImpl(`http://127.0.0.1:${port}/`, {
        signal: AbortSignal.timeout(Math.max(1, Math.min(3_000, deadline - Date.now()))),
      });
      if (!ui.ok || !ui.headers.get("content-type")?.includes("text/html")) {
        throw new Error("UI 준비 미완료");
      }
      if (!(await ui.text()).includes('id="root"')) throw new Error("UI 문서 없음");
      return value;
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : "연결 실패";
    }
    const remaining = deadline - Date.now();
    if (remaining > 0) await delay(Math.min(intervalMs, remaining));
  }
  throw new Error(`앱 준비 제한 시간 초과: ${lastFailure}`);
}
