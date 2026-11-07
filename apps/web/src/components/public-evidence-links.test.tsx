import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PublicEvidenceLinks } from "@/components/public-evidence-links";
import { api } from "@/lib/gosari.api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("shows linked public values with plain labels and keeps transport metadata out of the dialog", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue({
    public_query_spec: { operation: "current_observation", source_ids: ["kma_aws"] },
    source_manifests: [
      {
        source_id: "kma_aws",
        verified_on: "2026-04-12",
        transport_status: "ok",
        content_hash: "internal-hash",
      },
    ],
    result_values: { temperature_c: 15.5, station_count: 43 },
    created_at: "2026-04-12T00:00:00Z",
  });
  render(<PublicEvidenceLinks ids={["public-weather"]} />);
  fireEvent.click(screen.getByRole("button", { name: "연결한 공개 조회 1건" }));
  await screen.findByText("기상청");
  expect(screen.getByText("기온 (℃)")).toBeTruthy();
  expect(screen.getByText("15.5")).toBeTruthy();
  expect(screen.queryByText("public_query_spec")).toBeNull();
  expect(screen.queryByText("internal-hash")).toBeNull();
  expect(screen.queryByText("current_observation")).toBeNull();
});

it("keeps the link intact when the source cannot be fetched", async () => {
  vi.spyOn(api, "evidence").mockRejectedValue(new Error("offline"));
  render(<PublicEvidenceLinks ids={["public-weather"]} />);
  fireEvent.click(screen.getByRole("button", { name: "연결한 공개 조회 1건" }));
  await screen.findByText("1건을 불러오지 못했습니다.");
  fireEvent.click(screen.getByRole("button", { name: "닫기" }));
  expect(screen.getByRole("button", { name: "연결한 공개 조회 1건" })).toBeTruthy();
});

it("keeps a readable sample label when the linked source was replayed", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue({
    source_manifests: [{ source_id: "kma_aws", source_mode: "replay" }],
    result_values: { temperature_c: 15.5 },
  });
  render(<PublicEvidenceLinks ids={["sample"]} />);
  fireEvent.click(screen.getByRole("button", { name: "연결한 공개 조회 1건" }));
  expect(await screen.findByText("표본 자료")).toBeTruthy();
  expect(screen.queryByText("source_mode")).toBeNull();
});
it("shows partial data without exposing failed-scope metadata", async () => {
  vi.spyOn(api, "evidence").mockResolvedValue({
    source_manifests: [
      {
        source_id: "kma_aws",
        source_mode: "fetched",
        transport_status: "partial",
        failed_scope: { internal_page: 2 },
      },
    ],
    result_values: { temperature_c: 15.5 },
  });
  render(<PublicEvidenceLinks ids={["partial"]} />);
  fireEvent.click(screen.getByRole("button", { name: "연결한 공개 조회 1건" }));
  expect(await screen.findByText("일부 자료")).toBeTruthy();
  expect(screen.queryByText("internal_page")).toBeNull();
});
it("shows the number of missing linked queries while retaining successful values", async () => {
  vi.spyOn(api, "evidence")
    .mockRejectedValueOnce(new Error("missing"))
    .mockResolvedValueOnce({
      source_manifests: [{ source_id: "kma_aws" }],
      result_values: { temperature_c: 15.5 },
    });
  render(<PublicEvidenceLinks ids={["missing", "available"]} />);
  fireEvent.click(screen.getByRole("button", { name: "연결한 공개 조회 2건" }));
  expect(await screen.findByText("1건을 불러오지 못했습니다.")).toBeTruthy();
  expect(screen.getByText("15.5")).toBeTruthy();
});
