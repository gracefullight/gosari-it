import {
  type AnalysisStreamOptions,
  cancelAnalysisJob,
  streamAnalysisJob,
  waitForAnalysisJob,
} from "@/lib/analysis-jobs";
import type {
  ActionResult,
  AgentChatResponse,
  Capabilities,
  Consent,
  JobResult,
  NotebookEntry,
  PersonalContact,
  PersonalSearchResponse,
  PrepareResponse,
  Preview,
  PrivateRegion,
  ShareDraft,
  Station,
} from "@/lib/gosari.types";
import { fetchWithSession } from "@/lib/session-bootstrap";

const SESSION_STORAGE_KEY = "gosari_session_id";

function getStoredSessionId(): string | null {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setStoredSessionId(sessionId: string | null): void {
  try {
    if (sessionId) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    } else {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch {
    // ignore storage errors
  }
}

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const storedSid = getStoredSessionId();
  if (storedSid) {
    headers["X-Gosari-Session"] = storedSid;
  }
  const response = await fetchWithSession(path, {
    credentials: "same-origin",
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new ApiError(response.status, body.error ?? "HTTP_ERROR", body.message ?? "요청 실패");
  }
  return (await response.json()) as T;
}

export const api = {
  createSession: async () => {
    const res = await request<{ session_id: string; expires_at: string; resumed?: boolean }>(
      "/api/v1/sessions/",
      { method: "POST" }
    );
    if (res.session_id) {
      setStoredSessionId(res.session_id);
    }
    return res;
  },
  endSession: async () => {
    const result = await request<{ ended: boolean }>("/api/v1/sessions/current", {
      method: "DELETE",
    });
    setStoredSessionId(null);
    return result;
  },
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  prepare: (body: { text: string; feature?: string }) =>
    request<PrepareResponse>("/api/v1/analysis/prepare", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  chat: (body: { text: string; conversation_id?: string }, signal?: AbortSignal) =>
    request<AgentChatResponse>("/api/v1/analysis/chat", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }),
  streamJob: (job: JobResult, options: AnalysisStreamOptions) => streamAnalysisJob(job, options),
  runAnalysis: async (
    spec: Record<string, unknown>,
    safeText?: string,
    options?: AnalysisStreamOptions
  ) => {
    const initial = await request<JobResult>("/api/v1/analysis/jobs", {
      method: "POST",
      body: JSON.stringify({ spec, safe_text: safeText, conversation_id: options?.conversationId }),
      signal: options?.signal,
    });
    if (options?.signal?.aborted) {
      void cancelAnalysisJob(initial.job_id).catch(() => {});
      options.signal.throwIfAborted();
    }
    return options?.onEvent
      ? streamAnalysisJob(initial, options)
      : waitForAnalysisJob(initial, options?.signal, options?.onProgress);
  },
  getJob: (jobId: string) => request<JobResult>(`/api/v1/jobs/${jobId}`),
  evidence: (evidenceId: string) =>
    request<Record<string, unknown>>(`/api/v1/evidence/${evidenceId}`),
  mapsPrepare: () =>
    request<{ stations: Station[]; count: number }>("/api/v1/maps/prepare", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  notebookList: () => request<{ entries: NotebookEntry[] }>("/api/v1/notebook/"),
  notebookRecall: (params: { start?: string; end?: string; alias?: string }) =>
    request<{ entries: NotebookEntry[]; count: number; notice?: string }>(
      "/api/v1/notebook/recall",
      {
        method: "POST",
        body: JSON.stringify({
          start: params.start || null,
          end: params.end || null,
          alias: params.alias || null,
        }),
      }
    ),
  notebookPrepare: (
    payload: Record<string, unknown>,
    action: "create" | "update" | "delete" = "create",
    recordId?: string
  ) =>
    request<Preview>("/api/v1/notebook/prepare", {
      method: "POST",
      body: JSON.stringify({ action, record_id: recordId ?? null, payload }),
    }),
  regionsList: () => request<{ regions: PrivateRegion[] }>("/api/v1/regions/"),
  regionsPrepare: (
    payload: Record<string, unknown>,
    action: "create" | "update" | "delete" = "create",
    regionId?: string
  ) =>
    request<Preview>("/api/v1/regions/prepare", {
      method: "POST",
      body: JSON.stringify({ action, region_id: regionId ?? null, payload }),
    }),
  shareList: () => request<{ drafts: ShareDraft[] }>("/api/v1/share/"),
  contactsList: () => request<{ contacts: PersonalContact[] }>("/api/v1/contacts/"),
  personalSearch: (query: string) =>
    request<PersonalSearchResponse>("/api/v1/personal/search", {
      method: "POST",
      body: JSON.stringify({ query, limit: 20 }),
    }),
  contactsPrepare: (
    payload: Record<string, unknown>,
    action: "create" | "update" | "delete" = "create",
    contactId?: string
  ) =>
    request<Preview>("/api/v1/contacts/prepare", {
      method: "POST",
      body: JSON.stringify({ action, contact_id: contactId ?? null, payload }),
    }),
  sharePrepare: (
    payload: Record<string, unknown>,
    action: "save" | "update" | "delete" = "save",
    draftId?: string
  ) =>
    request<Preview>("/api/v1/share/prepare", {
      method: "POST",
      body: JSON.stringify(
        action === "save" ? payload : { action, share_draft_id: draftId, payload }
      ),
    }),
  consent: (preview: Preview) =>
    request<Consent>("/api/v1/consents/", {
      method: "POST",
      body: JSON.stringify({
        preview_id: preview.preview_id,
        preview_hash: preview.preview_hash,
        decision: "confirm",
      }),
    }),
  commit: (path: string, preview: Preview, consent: Consent) =>
    request<ActionResult>(path, {
      method: "POST",
      body: JSON.stringify({
        consent_id: consent.consent_id,
        preview_id: preview.preview_id,
        action: preview.action,
        target_id: preview.target_id,
        target_revision: preview.target_revision,
        preview_hash: preview.preview_hash,
      }),
    }),
};

export function commitPathFor(action: string): string {
  if (action.startsWith("contact.")) return "/api/v1/contacts/commit";
  if (action.startsWith("notebook.")) return "/api/v1/notebook/commit";
  if (action.startsWith("region.")) return "/api/v1/regions/commit";
  if (action.startsWith("share.")) return "/api/v1/share/commit";
  throw new Error(`알 수 없는 액션: ${action}`);
}
