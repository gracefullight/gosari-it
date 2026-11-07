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

export type AgentUISelectionSource = "model" | "model_with_fallback" | "fallback" | "cache";

export interface JobResult {
  job_id: string;
  request_id: string;
  stage: string;
  created_at: string;
  result: ResultEnvelope | null;
  error: string | null;
  events: unknown[];
  model_usage?: Record<string, unknown>;
  ui_spec?: AgentUISpec | null;
  ui_results?: Record<string, ResultEnvelope>;
  ui_selection_source?: AgentUISelectionSource;
  personal_search?: PersonalSearchSummary | null;
  personal_form?: PersonalFormFeature | null;
}

export type PersonalFormFeature = "notebook" | "region_compare" | "share";

export type PersonalSearchKind = "region" | "notebook" | "share" | "contact" | "all";
export interface PersonalSearchSummary {
  query: string;
  kind: PersonalSearchKind;
  count: number;
}

export interface AgentUISpec {
  root: string;
  elements: Record<
    string,
    {
      type: string;
      props: Record<string, unknown>;
      children?: string[];
    }
  >;
}

export type AgentEventType =
  | "stage"
  | "assistant_delta"
  | "assistant_completed"
  | "tool_started"
  | "tool_completed"
  | "tool_failed"
  | "ui_spec"
  | "personal_search"
  | "personal_form"
  | "error"
  | "done";

export interface AgentStreamEvent {
  type: AgentEventType;
  event_id: string;
  job_id: string;
  request_id?: string;
  timestamp?: string;
  text?: string;
  stage?: string;
  safe_message?: string;
  message?: string;
  code?: string;
  tool_call_id?: string;
  name?: string;
  label?: string;
  conditions?: Record<string, unknown>;
  summary?: string;
  result?: ResultEnvelope | null;
  error?: string | null;
  model_usage?: Record<string, unknown>;
  spec?: AgentUISpec;
  results?: Record<string, ResultEnvelope>;
  selection_source?: AgentUISelectionSource;
  ui_spec?: AgentUISpec | null;
  ui_results?: Record<string, ResultEnvelope>;
  ui_selection_source?: AgentUISelectionSource;
  personal_search?: PersonalSearchSummary | null;
  personal_form?: PersonalFormFeature | null;
  feature?: PersonalFormFeature;
  query?: string;
  kind?: PersonalSearchKind;
  count?: number;
}

export interface AgentToolCall {
  id: string;
  name: string;
  label: string;
  status: "running" | "completed" | "failed";
  conditions?: Record<string, unknown>;
  summary?: string;
  error?: string;
  result?: ResultEnvelope;
}

export interface AgentChatState {
  status: "streaming" | "completed" | "cancelled" | "disconnected" | "failed";
  job_id?: string;
  last_event_id?: string;
  seen_event_ids: string[];
  stage_message?: string;
  tools: AgentToolCall[];
}

export type AgentChatResponse =
  | { kind: "confirmation"; preparation: PrepareResponse }
  | ({ kind: "job" } & JobResult);

export interface AgentChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
}

export interface AgentChatRequest {
  text: string;
  conversation_id?: string;
  history?: AgentChatHistoryEntry[];
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
  action_status?: string;
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
    kind?: string;
    inline?: boolean;
    initial_values?: Record<string, unknown>;
    price_channels?: { value: string; label: string }[];
    market_options?: { value: string; label: string }[];
    query?: string;
    note?: string;
    questions?: string[];
    feature_hint?: string;
    fields?: { name: string; label: string; type: string }[];
  };
}

export interface PersonalSearchResponse {
  query: string;
  mode: "hybrid" | "keyword";
  answer: string;
  items: {
    kind: "notebook" | "region" | "contact" | "share";
    id: string;
    title: string;
    snippet: string;
    date: string | null;
  }[];
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
  private_region_id?: string | null;
  public_evidence_ids?: string[];
  location_address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface ShareItem {
  contact_id?: string | null;
  occurred_on?: string | null;
  status?: "planned" | "delivered";
  recipient_alias: string;
  amount_value: string | number;
  amount_unit: string;
  planned_delivery?: string | null;
  optional_role_note?: string | null;
}

export interface PersonalContact {
  contact_id: string;
  revision: number;
  name: string;
  relationship: "가족" | "친척" | "친구" | "이웃" | "동료" | "기타";
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ShareDraft {
  share_draft_id: string;
  revision: number;
  items: ShareItem[];
  message_enabled: boolean;
  editable_message: string | null;
  source_record_ids: string[];
  public_evidence_ids: string[];
  prepared_at: string;
}

export interface PrivateRegion {
  visited_on?: string | null;
  region_id: string;
  revision: number;
  latitude?: number | null;
  longitude?: number | null;
  kind: "existing" | "interest";
  public_area_code: string | null;
  coarse_grid: string | null;
  local_alias: string;
  selected_station_mapping_ids: string[];
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
