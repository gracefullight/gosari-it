import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { LandOwnershipResults } from "@/components/land-ownership-results";
import { ResultCard } from "@/components/result-card";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { hasDetailedResult } from "@/lib/result-display";

afterEach(cleanup);
const land = {
  location_id: "aws:965",
  location_name: "한라산남벽",
  pnu: "INTERNAL-PNU",
  latitude: 33.3524,
  longitude: 126.533,
  ownership_class: "public",
  is_private: false,
  owner_type_code: "INTERNAL-CODE",
  owner_type_name: "국유지",
  reference_month: "202610",
  last_updated: "2026-11-01",
  source_name: "브이월드",
  source_url: "https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do",
  owner_name: "MUST-NOT-RENDER",
  phone: "PRIVATE-PHONE",
};
function envelope(
  value: Record<string, unknown> = land,
  status: ResultEnvelope["data_status"] = "complete"
): ResultEnvelope {
  return {
    schema_version: "1",
    request_id: "request",
    data_status: status,
    source_mode: "fetched",
    action_status: null,
    link_status: "none",
    cache_resolution: "miss",
    requested_scope: { operation: "land_ownership" },
    effective_scope: {},
    observed_period: {},
    fetched_at: null,
    verified_on: null,
    result: { land_ownership: value },
    evidence_ids: ["INTERNAL-EVIDENCE"],
    warnings: [],
    errors: [],
  };
}

it.each([
  ["private", true, "개인", "개인"],
  ["public", false, "국유지", "국유지"],
  ["public", false, "법인", "법인"],
  ["unknown", null, "법인", "법인"],
  ["private", true, "", "사유지"],
  ["public", false, "", "국·공유지"],
])(
  "renders the official ownership classification without inferring from the location: %s",
  (classification, isPrivate, officialName, label) => {
    render(
      <LandOwnershipResults
        envelope={envelope({
          ...land,
          ownership_class: classification,
          is_private: isPrivate,
          owner_type_name: officialName,
        })}
      />
    );
    expect(screen.getByRole("heading", { name: "한라산남벽" })).toBeTruthy();
    expect(screen.getByText(String(label))).toBeTruthy();
    expect(screen.getByText("2026-10")).toBeTruthy();
    const link = screen.getByRole("link", { name: "브이월드 공식 출처 (새 창)" });
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(document.body.textContent).not.toContain("INTERNAL");
    expect(document.body.textContent).not.toContain("MUST-NOT-RENDER");
    expect(document.body.textContent).not.toContain("PRIVATE-PHONE");
    expect(screen.queryByText("공유지")).toBeNull();
  }
);

it("preserves the official national-land name in the fallback result card", () => {
  render(<ResultCard envelope={envelope()} />);
  expect(screen.getByText("국유지")).toBeTruthy();
  expect(screen.queryByText("공유지")).toBeNull();
  expect(screen.getByText("2026-10")).toBeTruthy();
});

it.each(["no_data", "unavailable"] as const)(
  "hides empty %s ownership details even when placeholder coordinates exist",
  (status) => {
    const value = envelope(
      {
        location_name: "한라산남벽",
        latitude: 33.3524,
        longitude: 126.533,
        pnu: "INTERNAL",
        ownership_class: "unknown",
        is_private: null,
        owner_type_name: null,
      },
      status
    );
    expect(hasDetailedResult(value)).toBe(false);
    const { container } = render(<ResultCard envelope={value} />);
    expect(container.textContent).toBe("");
  }
);

it("preserves false as a real result and hides unsafe source URLs", () => {
  const value = envelope(
    {
      ...land,
      ownership_class: "unknown",
      owner_type_name: null,
      is_private: false,
      source_url: "javascript:alert(1)",
    },
    "partial"
  );
  expect(hasDetailedResult(value)).toBe(true);
  render(<ResultCard envelope={value} />);
  expect(screen.getByText("아니오")).toBeTruthy();
  expect(screen.queryByRole("link")).toBeNull();
});

it("does not create meaningful data from a place, parcel code and coordinates alone", () => {
  expect(
    hasDetailedResult(
      envelope({
        location_name: "지점",
        pnu: "123",
        latitude: 33,
        longitude: 126,
        ownership_class: "unknown",
        is_private: null,
      })
    )
  ).toBe(false);
});
