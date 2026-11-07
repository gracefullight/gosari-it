import { describe, expect, it } from "vitest";
import { conditionPreparation, notebookPreparation } from "@/lib/agent-ui-actions";
import type { ResultEnvelope } from "@/lib/gosari.types";

const envelope: ResultEnvelope = {
  schema_version: "1",
  request_id: "read-result",
  data_status: "complete",
  source_mode: "replay",
  action_status: null,
  link_status: "none",
  cache_resolution: "miss",
  requested_scope: {
    operation: "retail_lookup",
    source_ids: ["retail_sample", "tamnao"],
    fresh_or_dried: "건고사리",
  },
  effective_scope: {},
  observed_period: {},
  fetched_at: null,
  verified_on: "2026-11-05",
  result: { channel: "retail" },
  evidence_ids: ["public-evidence"],
  warnings: [],
  errors: [],
};

describe("generated UI follow-up preparation", () => {
  it("keeps the real query source and accepts public condition edits without trusting action-supplied operations", () => {
    const next = conditionPreparation(envelope, {
      package_weight_unit: "200 g",
      source_ids: ["arbitrary_source"],
      operation: "notebook.delete",
      private_note: "not public",
    });
    expect(next.spec).toMatchObject({
      operation: "retail_lookup",
      source_ids: ["retail_sample", "tamnao"],
      package_weight_unit: "200 g",
    });
    expect(next.spec).not.toHaveProperty("private_note");
    expect(next.needs_confirmation).toBe(true);
  });

  it("opens a personal draft with actual evidence and an outing day without inventing activity text", () => {
    const prepared = notebookPreparation({
      ...envelope,
      requested_scope: { operation: "outing_compare", candidates: [{ date: "2026-11-09" }] },
    });
    expect(prepared.classification).toBe("personal");
    expect(prepared.form?.initial_values).toEqual({
      experience_date: "2026-11-09",
      public_evidence_ids: ["public-evidence"],
    });
    expect(prepared.form?.initial_values).not.toHaveProperty("activity_text");
  });

  it("does not turn a price observation day into the user's activity date", () => {
    const prepared = notebookPreparation({
      ...envelope,
      requested_scope: { operation: "retail_lookup", settlement_date: "2026-11-05" },
    });
    expect(prepared.form?.initial_values).toEqual({ public_evidence_ids: ["public-evidence"] });
  });
});
