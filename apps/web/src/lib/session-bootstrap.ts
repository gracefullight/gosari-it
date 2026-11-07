const SESSION_STORAGE_KEY = "gosari_session_id";
const RECOVERABLE_FORM_PATH = /\/(prepare|recall)$/;
const TRAILING_SLASH = /\/$/;
let bootstrap: Promise<Response> | null = null;
let recoveryEnabled = true;
let generation = 0;

function storedSessionId(): string | null {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function requestHeaders(options?: RequestInit): Headers {
  const headers = new Headers(options?.headers);
  const sessionId = storedSessionId();
  if (sessionId) headers.set("X-Gosari-Session", sessionId);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  return headers;
}

function createSession(options?: RequestInit): Promise<Response> {
  if (bootstrap) return bootstrap;
  const startedGeneration = generation;
  const task = (async () => {
    const response = await fetch("/api/v1/sessions/", {
      credentials: "same-origin",
      ...options,
      method: "POST",
      headers: requestHeaders(options),
    });
    if (response.ok) {
      const body = (await response
        .clone()
        .json()
        .catch(() => null)) as { session_id?: unknown } | null;
      if (
        typeof body?.session_id === "string" &&
        generation === startedGeneration &&
        recoveryEnabled
      ) {
        try {
          window.localStorage.setItem(SESSION_STORAGE_KEY, body.session_id);
        } catch {
          /* storage unavailable */
        }
      }
    }
    return response;
  })();
  bootstrap = task;
  void task
    .finally(() => {
      if (bootstrap === task) bootstrap = null;
    })
    .catch(() => {});
  return task;
}

function allowsRecovery(pathname: string, method: string): boolean {
  if (pathname.startsWith("/api/v1/sessions")) return false;
  if (method === "GET" || method === "HEAD") return true;
  if (method !== "POST") return false;
  return (
    pathname === "/api/v1/analysis/jobs" ||
    pathname === "/api/v1/personal/search" ||
    RECOVERABLE_FORM_PATH.test(pathname)
  );
}

/** Recover read requests once; consent, commit and explicit session closure never retry. */
export async function fetchWithSession(url: string, options?: RequestInit): Promise<Response> {
  const pathname = new URL(url, window.location.origin).pathname.replace(TRAILING_SLASH, "");
  const method = (options?.method ?? "GET").toUpperCase();
  if (pathname === "/api/v1/sessions" && method === "POST") {
    recoveryEnabled = true;
    return (await createSession(options)).clone();
  }
  const previousSid = storedSessionId();
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: requestHeaders(options),
  });
  if (pathname === "/api/v1/sessions/current" && method === "DELETE" && response.ok) {
    recoveryEnabled = false;
    generation += 1;
  }
  if (response.ok || !recoveryEnabled || !allowsRecovery(pathname, method)) return response;
  const body = (await response
    .clone()
    .json()
    .catch(() => null)) as { error?: string } | null;
  if (body?.error !== "SESSION_REQUIRED" && body?.error !== "SESSION_EXPIRED") return response;
  try {
    if (!storedSessionId() || storedSessionId() === previousSid) {
      const restored = await createSession();
      if (!restored.ok) return response;
    }
  } catch {
    return response;
  }
  if (!recoveryEnabled || options?.signal?.aborted) return response;
  return fetch(url, { credentials: "same-origin", ...options, headers: requestHeaders(options) });
}
