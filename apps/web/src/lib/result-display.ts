import type { ResultEnvelope } from "@/lib/gosari.types";

const METADATA_FIELDS = new Set([
  "channel",
  "source",
  "source_url",
  "notice",
  "description",
  "operation",
]);
function hasValue(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "boolean") return true;
  if (Array.isArray(value)) return value.some(hasValue);
  if (typeof value === "object") return Object.values(value).some(hasValue);
  return false;
}

export function hasDisplayableResult(envelope?: ResultEnvelope | null): envelope is ResultEnvelope {
  if (!envelope) return false;
  if (envelope.errors.length || envelope.warnings.length) return true;
  if (envelope.data_status && envelope.data_status !== "complete") return true;
  if (envelope.action_status && envelope.action_status !== "none") return true;
  return Object.entries(envelope.result).some(
    ([key, value]) => !METADATA_FIELDS.has(key) && hasValue(value)
  );
}

const DETAIL_METADATA_FIELDS = new Set([
  ...METADATA_FIELDS,
  "reason",
  "message",
  "explanation",
  "status",
  "data_status",
  "source_mode",
  "sample_filter_status",
]);

export function hasDetailedResult(envelope?: ResultEnvelope | null): envelope is ResultEnvelope {
  if (!envelope) return false;
  if (
    "land_ownership" in envelope.result ||
    envelope.requested_scope?.operation === "land_ownership"
  )
    return hasLandOwnershipData(envelope);
  return Object.entries(envelope.result).some(
    ([key, value]) =>
      !DETAIL_METADATA_FIELDS.has(key) &&
      key !== "count" &&
      !key.endsWith("_count") &&
      hasValue(value)
  );
}

export function hasLandOwnershipData(envelope?: ResultEnvelope | null): boolean {
  if (!envelope || envelope.data_status === "no_data" || envelope.data_status === "unavailable")
    return false;
  const land = envelope.result.land_ownership;
  if (!land || typeof land !== "object" || Array.isArray(land)) return false;
  const row = land as Record<string, unknown>;
  return (
    row.ownership_class === "private" ||
    row.ownership_class === "public" ||
    typeof row.is_private === "boolean" ||
    (typeof row.owner_type_name === "string" && Boolean(row.owner_type_name.trim()))
  );
}
