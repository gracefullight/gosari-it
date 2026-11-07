import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, expect, it, vi } from "vitest";
import { OutingPlanForm } from "@/components/outing-plan-form";
import * as analysisJobs from "@/lib/analysis-jobs";
import { api } from "@/lib/gosari.api";
import { featureResultsAtom } from "@/stores/chat.atoms";

vi.mock("@/components/date-picker-field", () => ({
  DatePickerField: ({
    id,
    value,
    onChange,
    "aria-label": ariaLabel,
  }: {
    id: string;
    value: string;
    onChange: (value: string) => void;
    "aria-label": string;
  }) => (
    <input
      id={id}
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
vi.mock("@/components/result-card", () => ({ ResultCard: () => <p>비교 결과</p> }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("submits locations and exact hours with a unique, reordered preference list", async () => {
  const store = createStore();
  const result = { request_id: "outing-result", result: {}, evidence_ids: ["public-outing"] };
  const run = vi.spyOn(api, "runAnalysis").mockResolvedValue({ result } as never);
  render(
    <Provider store={store}>
      <OutingPlanForm initialDate="2026-11-08" />
    </Provider>
  );
  fireEvent.change(screen.getByLabelText("1순위"), { target: { value: "low_wind" } });
  fireEvent.change(screen.getByLabelText("후보 2 날짜"), { target: { value: "2026-11-09" } });
  fireEvent.click(screen.getByRole("button", { name: "후보 비교" }));
  await waitFor(() =>
    expect(run.mock.calls[0]?.[0]).toEqual({
      operation: "outing_compare",
      source_ids: ["open_meteo"],
      candidates: [
        { location_id: "jeju", date: "2026-11-08", time_slot: "09:00" },
        { location_id: "seogwipo", date: "2026-11-09", time_slot: "12:00" },
      ],
      preferred_elements: ["low_wind", "mild_temperature", "low_rain"],
    })
  );
  await screen.findByText("비교 결과");
  expect(store.get(featureResultsAtom).나들이?.evidence_ids).toEqual(["public-outing"]);
});

it("keeps between two and four candidates and prevents duplicate choices", () => {
  render(
    <Provider>
      <OutingPlanForm initialDate="2026-11-08" />
    </Provider>
  );
  expect((screen.getByRole("button", { name: "후보 1 삭제" }) as HTMLButtonElement).disabled).toBe(
    true
  );
  fireEvent.click(screen.getByRole("button", { name: "후보 추가" }));
  fireEvent.click(screen.getByRole("button", { name: "후보 추가" }));
  expect((screen.getByRole("button", { name: "후보 추가" }) as HTMLButtonElement).disabled).toBe(
    true
  );
  expect(screen.getByText("같은 지역·날짜·시각이 겹칩니다.")).toBeTruthy();
  expect((screen.getByRole("button", { name: "후보 비교" }) as HTMLButtonElement).disabled).toBe(
    true
  );
  fireEvent.click(screen.getByRole("button", { name: "후보 4 삭제" }));
  expect(screen.queryByText("같은 지역·날짜·시각이 겹칩니다.")).toBeNull();
});

it("reports a failed comparison and enables retry", async () => {
  vi.spyOn(api, "runAnalysis").mockRejectedValue(new Error("날씨를 불러오지 못했습니다."));
  render(
    <Provider>
      <OutingPlanForm initialDate="2026-11-08" />
    </Provider>
  );
  fireEvent.click(screen.getByRole("button", { name: "후보 비교" }));
  await screen.findByRole("alert");
  expect((screen.getByRole("button", { name: "후보 비교" }) as HTMLButtonElement).disabled).toBe(
    false
  );
});

it("cancels the running public job and stops polling", async () => {
  const cancel = vi.spyOn(analysisJobs, "cancelAnalysisJob").mockResolvedValue();
  vi.spyOn(api, "runAnalysis").mockImplementation(
    (_spec, _text, options) =>
      new Promise((_resolve, reject) => {
        options?.onProgress?.({ job_id: "job-outing", stage: "running" } as never);
        options?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("cancelled", "AbortError")),
          { once: true }
        );
      })
  );
  render(
    <Provider>
      <OutingPlanForm initialDate="2026-11-08" />
    </Provider>
  );
  fireEvent.click(screen.getByRole("button", { name: "후보 비교" }));
  fireEvent.click(await screen.findByRole("button", { name: "비교 취소" }));
  await waitFor(() => expect(cancel).toHaveBeenCalledWith("job-outing"));
  await screen.findByText("비교를 취소했습니다.");
  expect((screen.getByRole("button", { name: "후보 비교" }) as HTMLButtonElement).disabled).toBe(
    false
  );
});
