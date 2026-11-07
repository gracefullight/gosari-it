import { formatDisplayDate } from "@/lib/date-format";
import type { PrepareResponse, ResultEnvelope } from "@/lib/gosari.types";

const CONDITION_FIELDS = new Set([
  "settlement_date",
  "settlement_date_end",
  "market_ids",
  "fresh_or_dried",
  "grade",
  "package_code",
  "package_weight_unit",
  "product_option",
  "origin_filter",
  "candidates",
  "preferred_elements",
  "years",
  "month_day_start",
  "month_day_end",
  "elements",
]);
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const PUBLIC_QUERY_FIELDS = new Set([
  ...CONDITION_FIELDS,
  "schema_version",
  "operation",
  "source_ids",
  "station_selections",
  "comparison_scope",
  "aggregation",
  "unit",
  "timezone",
  "polarity",
  "accumulation_window",
  "forecast_grid_id",
  "forecast_published_at",
  "forecast_target_times",
  "price_channel",
  "item_codes",
  "survey_region",
  "survey_stage",
  "survey_as_of",
  "product_id",
  "shipping_basis",
  "coupon_basis",
]);

export function conditionPreparation(
  envelope: ResultEnvelope,
  values?: Record<string, unknown>
): PrepareResponse {
  const updates = Object.fromEntries(
    Object.entries(values ?? {}).filter(([field]) => CONDITION_FIELDS.has(field))
  );
  const scope = {
    ...Object.fromEntries(
      Object.entries(envelope.requested_scope).filter(([field]) => PUBLIC_QUERY_FIELDS.has(field))
    ),
    ...updates,
  };
  if (updates.package_weight_unit && !updates.product_option) {
    scope.product_option = undefined;
    scope.product_id = undefined;
  }
  const operation = String(scope.operation ?? "");
  const price =
    ["market_query", "retail_lookup", "survey_link"].includes(operation) ||
    ["wholesale", "survey", "retail"].includes(String(envelope.result.channel));
  if (price) {
    const operationForChannel: Record<string, string> = {
      wholesale: "market_query",
      survey: "survey_link",
      retail: "retail_lookup",
    };
    scope.operation = operation || operationForChannel[String(envelope.result.channel)];
    return {
      classification: "public",
      feature: "price",
      needs_confirmation: true,
      spec: scope,
      form: { kind: "price_conditions", feature_hint: "price", initial_values: scope },
    };
  }
  if (operation === "history_compare")
    return {
      classification: "public",
      feature: "history_compare",
      needs_confirmation: true,
      spec: scope,
    };
  return {
    classification: "public",
    feature: "outing",
    needs_confirmation: true,
    form: { feature_hint: "outing", initial_values: scope },
  };
}

export function notebookPreparation(envelope: ResultEnvelope): PrepareResponse {
  const first = Array.isArray(envelope.requested_scope.candidates)
    ? envelope.requested_scope.candidates[0]
    : undefined;
  const date =
    first && typeof first === "object"
      ? formatDisplayDate(String(first.date ?? first.target_date ?? ""))
      : "";
  return {
    classification: "personal",
    feature: "notebook",
    needs_confirmation: true,
    form: {
      kind: "notebook_draft",
      initial_values: {
        ...(ISO_DAY.test(date) ? { experience_date: date } : {}),
        public_evidence_ids: envelope.evidence_ids,
      },
    },
  };
}
