import type {
  ActionResult,
  Capabilities,
  Consent,
  JobResult,
  NotebookEntry,
  PrepareResponse,
  Preview,
  ResultEnvelope,
  Station,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.error ?? "HTTP_ERROR", body.message ?? "요청 실패");
  }
  return response.json() as Promise<T>;
}

export const api = {
  createSession: () => request<{ session_id: string }>("/sessions/", { method: "POST" }),
  endSession: () => request<{ status: string }>("/sessions/current", { method: "DELETE" }),
  capabilities: () => request<Capabilities>("/capabilities/"),
  prepare: (payload: { text?: string; spec?: Record<string, unknown> }) =>
    request<PrepareResponse>("/analysis/prepare", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runAnalysis: (spec: Record<string, unknown>, safeText: string) =>
    request<JobResult>("/analysis/jobs", {
      method: "POST",
      body: JSON.stringify({ spec, safe_text: safeText }),
    }),
  stations: () => request<ResultEnvelope>("/stations/"),
  mapsPrepare: () =>
    request<{ map: Record<string, unknown>; stations: Station[] }>("/maps/prepare", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  evidence: (id: string) => request<Record<string, unknown>>(`/evidence/${id}`),

  notebookPrepare: (payload: Record<string, unknown>, action = "create", recordId?: string) =>
    request<Preview>("/notebook/prepare", {
      method: "POST",
      body: JSON.stringify({ action, payload, record_id: recordId }),
    }),
  notebookList: () => request<{ entries: NotebookEntry[] }>("/notebook/"),
  notebookRecall: (conditions: Record<string, unknown>) =>
    request<{ entries: NotebookEntry[]; count: number }>("/notebook/recall", {
      method: "POST",
      body: JSON.stringify(conditions),
    }),

  regionsPrepare: (payload: Record<string, unknown>, action = "create", regionId?: string) =>
    request<Preview>("/regions/prepare", {
      method: "POST",
      body: JSON.stringify({ action, payload, region_id: regionId }),
    }),
  regionsList: () => request<{ regions: Record<string, unknown>[] }>("/regions/"),

  sharePrepare: (payload: Record<string, unknown>) =>
    request<Preview>("/share/prepare", { method: "POST", body: JSON.stringify(payload) }),
  shareList: () => request<{ drafts: Record<string, unknown>[] }>("/share/"),

  consent: (preview: Preview) =>
    request<Consent>("/consents/", {
      method: "POST",
      body: JSON.stringify({
        preview_id: preview.preview_id,
        preview_hash: preview.preview_hash,
        decision: "confirm",
      }),
    }),
  commit: (
    path: "/notebook/commit" | "/regions/commit" | "/share/commit",
    preview: Preview,
    consent: Consent
  ) =>
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

export function commitPathFor(
  action: string
): "/notebook/commit" | "/regions/commit" | "/share/commit" {
  if (action.startsWith("notebook.")) return "/notebook/commit";
  if (action.startsWith("region.")) return "/regions/commit";
  return "/share/commit";
}
