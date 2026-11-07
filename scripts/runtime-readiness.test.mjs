import assert from "node:assert/strict";
import { test } from "node:test";
import { readCapabilities, waitForReadiness } from "./runtime-readiness.mjs";

const ready = { status: "ready", database: "ok", llm: "not_configured" };
const ui = () => new Response('<html><div id="root"></div></html>', {
  headers: { "content-type": "text/html; charset=utf-8" },
});

test("DB가 준비되고 UI가 있을 때 모델 키 없이도 준비 완료", async () => {
  const requests = [];
  const value = await waitForReadiness({
    port: 8765,
    fetchImpl: async (url) => {
      requests.push(url);
      return url.endsWith("/ready") ? Response.json(ready) : ui();
    },
  });
  assert.deepEqual(value, ready);
  assert.equal(requests.length, 2);
});

for (const [label, health] of [
  ["HTTP 오류 JSON", () => Response.json(ready, { status: 503 })],
  ["DB 제한 상태", () => Response.json({ status: "limited", database: "unavailable" })],
  ["준비 형식이 아닌 JSON", () => Response.json({ error: "NOT_FOUND" })],
]) {
  test(`${label}을 준비 완료로 처리하지 않음`, async () => {
    await assert.rejects(waitForReadiness({
      port: 8765, timeoutMs: 25, intervalMs: 1,
      fetchImpl: async () => health(),
    }), /제한 시간 초과/);
  });
}

test("API만 준비되고 UI가 없으면 성공하지 않음", async () => {
  await assert.rejects(waitForReadiness({
    port: 8765, timeoutMs: 25, intervalMs: 1,
    fetchImpl: async (url) => url.endsWith("/ready") ? Response.json(ready) : Response.json({ error: "NOT_FOUND" }),
  }), /UI 준비 미완료/);
});

test("DB 지연 후 정상 응답을 기다림", async () => {
  let attempts = 0;
  const value = await waitForReadiness({
    port: 8765, timeoutMs: 500, intervalMs: 1,
    fetchImpl: async (url) => {
      if (!url.endsWith("/ready")) return ui();
      attempts++;
      return Response.json(attempts === 1 ? { status: "limited", database: "unavailable" } : ready);
    },
  });
  assert.equal(attempts, 2);
  assert.deepEqual(value, ready);
});

test("상태 명령은 HTTP 오류를 정상 결과로 처리하지 않음", async () => {
  await assert.rejects(readCapabilities({
    port: 8765, fetchImpl: async () => Response.json({ error: "HTTP_ERROR" }, { status: 503 }),
  }), /HTTP 503/);
});

test("상태 명령은 알 수 없는 JSON을 정상으로 처리하지 않음", async () => {
  await assert.rejects(readCapabilities({
    port: 8765, fetchImpl: async () => Response.json({ error: "HTTP_ERROR" }),
  }), /응답 형식/);
});

test("상태 명령은 실제 제한 모드를 그대로 반환", async () => {
  const capabilities = { profile: "center", runtime_mode: "limited", files: {} };
  assert.deepEqual(await readCapabilities({
    port: 8765, fetchImpl: async () => Response.json(capabilities),
  }), capabilities);
});
