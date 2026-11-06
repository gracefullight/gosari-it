export type DataStatus =
  | "complete"
  | "partial"
  | "no_data"
  | "conflict"
  | "needs_confirmation"
  | "unavailable";

export type SourceMode = "fetched" | "cache" | "replay" | "link" | "permitted_file";

export interface ResultEnvelope {
  schema_version: string;
  request_id: string;
  data_status: DataStatus | null;
  source_mode: SourceMode | null;
  action_status: string | null;
  link_status: string;
  cache_resolution: string;
  requested_scope: Record<string, unknown>;
  effective_scope: Record<string, unknown>;
  observed_period: Record<string, unknown>;
  fetched_at: string | null;
  verified_on: string | null;
  result: Record<string, unknown>;
  evidence_ids: string[];
  warnings: string[];
  errors: { code: string; message: string }[];
}

export interface JobResult {
  job_id: string;
  request_id: string;
  stage: string;
  created_at: string;
  result: ResultEnvelope | null;
  error: string | null;
  events: unknown[];
}

export interface Preview {
  preview_id: string;
  action: string;
  target_id: string;
  target_revision: number;
  schema_version: string;
  display_payload: Record<string, unknown>;
  preview_hash: string;
  expires_at: string;
  action_status: string;
  display?: Record<string, unknown>;
}

export interface Consent {
  consent_id: string;
  preview_id: string;
  action: string;
  target_id: string;
  target_revision: number;
  preview_hash: string;
}

export interface ActionResult {
  action_id: string;
  state: "committed" | "failed";
  result_id: string | null;
  resulting_revision: number | null;
  safe_error: string | null;
}

export interface Capabilities {
  profile: string;
  runtime_mode: "live" | "replay" | "limited";
  map: { tiles: boolean; osm_attribution_required: boolean };
  llm: { available: boolean; model: string };
  sources: Record<string, boolean>;
  files: Record<string, boolean>;
  cache: { response_cache: boolean; semantic: boolean };
}

export interface PrepareResponse {
  classification: "public" | "personal";
  feature?: string;
  needs_confirmation: boolean;
  spec?: Record<string, unknown>;
  form?: {
    note?: string;
    questions?: string[];
    feature_hint?: string;
    fields?: { name: string; label: string; type: string }[];
  };
}

export interface NotebookEntry {
  record_id: string;
  revision: number;
  experience_date: string;
  companion_aliases: string[];
  activity_text: string;
  amount_value: string | null;
  amount_unit: string | null;
  created_at: string;
  updated_at: string;
}

export interface Station {
  source_id: string;
  station_code: string | null;
  station_name: string;
  altitude_m: number | null;
  location: string;
}
