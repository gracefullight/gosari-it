import { fetchWithSession } from "@/lib/session-bootstrap";

/** Orval 공통 fetch 뮤테이터: 생성된 훅의 모든 요청이 이 경로를 통과한다. */

const SESSION_STORAGE_KEY = "gosari_session_id";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** orval 8 full-response 계약: { data, status, headers }를 반환한다. */
export const customFetch = async <T>(url: string, options?: RequestInit): Promise<T> => {
  const headers = new Headers(options?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  try {
    const sid = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (sid && !headers.has("X-Gosari-Session")) {
      headers.set("X-Gosari-Session", sid);
    }
  } catch {
    // ignore storage errors
  }

  const response = await fetchWithSession(url, {
    credentials: "same-origin",
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new ApiError(response.status, body.error ?? "HTTP_ERROR", body.message ?? "요청 실패");
  }

  const data = await response.json().catch(() => null);
  try {
    if (data && typeof data === "object" && "session_id" in data && typeof data.session_id === "string") {
      window.localStorage.setItem(SESSION_STORAGE_KEY, data.session_id);
    }
  } catch {
    // ignore
  }
  return { data, status: response.status, headers: response.headers } as T;
};
