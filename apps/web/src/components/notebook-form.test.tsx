import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NotebookForm } from "@/components/notebook-form";
import { api } from "@/lib/gosari.api";
import { messagesAtom } from "@/stores/chat.atoms";

const RECORD_LABEL = /^기록/;
const DATE_LABEL = /^채취 날짜/;

vi.mock("@/components/date-picker-field", () => ({
  DatePickerField: ({
    id,
    value,
    onChange,
  }: {
    id: string;
    value: string;
    onChange: (value: string) => void;
  }) => <input id={id} value={value} onChange={(event) => onChange(event.target.value)} />,
}));
vi.mock("@/components/location-picker-dialog", () => ({
  LocationPickerDialog: ({ onSelect }: { onSelect: (v: unknown) => void }) => (
    <button
      type="button"
      onClick={() => onSelect({ address: "제주시 조천읍", latitude: 33.45, longitude: 126.7 })}
    >
      위치 확정
    </button>
  ),
}));
beforeEach(() => {
  vi.spyOn(api, "notebookRecall").mockResolvedValue({ entries: [], count: 0 });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("separates record listing from writing", async () => {
  const navigate = vi.fn();
  render(
    <Provider>
      <NotebookForm onPreview={vi.fn()} onNavigate={navigate} />
    </Provider>
  );
  await screen.findByText("아직 기록이 없습니다.");
  expect(screen.queryByLabelText("기록")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "기록 쓰기" }));
  expect(navigate).toHaveBeenCalledWith("/notebook/new");
  expect(screen.getByLabelText(RECORD_LABEL)).toBeTruthy();
  expect(screen.queryByLabelText("동행 검색")).toBeNull();
});
it("includes the chosen address and map coordinates in the preview request", async () => {
  const prepare = vi
    .spyOn(api, "notebookPrepare")
    .mockResolvedValue({ preview_id: "preview" } as Awaited<
      ReturnType<typeof api.notebookPrepare>
    >);
  render(
    <Provider>
      <NotebookForm mode="write" onPreview={vi.fn()} />
    </Provider>
  );
  fireEvent.change(screen.getByLabelText(DATE_LABEL), { target: { value: "2026-04-12" } });
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "채취 기록" } });
  fireEvent.click(screen.getByRole("button", { name: "지도 선택" }));
  fireEvent.click(screen.getByRole("button", { name: "위치 확정" }));
  await waitFor(() =>
    expect((screen.getByLabelText("위치") as HTMLInputElement).value).toBe("제주시 조천읍")
  );
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "저장할 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "저장할 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        location_address: "제주시 조천읍",
        latitude: 33.45,
        longitude: 126.7,
      }),
      "create",
      undefined
    )
  );
});

it("lets users clear search conditions from a zero-result state", async () => {
  render(
    <Provider>
      <NotebookForm onPreview={vi.fn()} />
    </Provider>
  );
  await screen.findByText("아직 기록이 없습니다.");
  fireEvent.change(screen.getByLabelText("동행 검색"), { target: { value: "미등록동행" } });
  await screen.findByText("검색 조건에 맞는 기록이 없습니다.");
  fireEvent.click(screen.getByRole("button", { name: "검색 조건 지우기" }));
  await screen.findByText("아직 기록이 없습니다.");
  expect((screen.getByLabelText("동행 검색") as HTMLInputElement).value).toBe("");
});

it("keeps existing public query and region links while editing notebook text", async () => {
  vi.spyOn(api, "notebookList").mockResolvedValue({
    entries: [
      {
        record_id: "record",
        experience_date: "2026-04-12",
        activity_text: "봄 채취",
        companion_aliases: [],
        amount_value: null,
        amount_unit: null,
        private_region_id: "region",
        public_evidence_ids: ["public-old"],
      } as never,
    ],
  });
  const prepare = vi
    .spyOn(api, "notebookPrepare")
    .mockResolvedValue({ preview_id: "update" } as Awaited<ReturnType<typeof api.notebookPrepare>>);
  render(
    <Provider>
      <NotebookForm mode="write" recordId="record" onPreview={vi.fn()} />
    </Provider>
  );
  await screen.findByDisplayValue("봄 채취");
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "봄 채취 수정" } });
  fireEvent.click(screen.getByRole("button", { name: "수정 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({ private_region_id: "region", public_evidence_ids: ["public-old"] }),
      "update",
      "record"
    )
  );
});

it("links a recent public query to the notebook without exposing its raw parameters", async () => {
  const store = createStore();
  store.set(messagesAtom, [
    {
      id: "public-result",
      role: "assistant",
      envelope: {
        result: { station_count: 43 },
        evidence_ids: ["public-query"],
        observed_period: {},
        verified_on: "2026-04-12",
      } as never,
    },
  ]);
  const prepare = vi
    .spyOn(api, "notebookPrepare")
    .mockResolvedValue({ preview_id: "create" } as Awaited<ReturnType<typeof api.notebookPrepare>>);
  render(
    <Provider store={store}>
      <NotebookForm mode="write" onPreview={vi.fn()} />
    </Provider>
  );
  fireEvent.change(screen.getByLabelText(DATE_LABEL), { target: { value: "2026-04-12" } });
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "봄 채취" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "공개 조회 · 2026-04-12" }));
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "저장할 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "저장할 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({ public_evidence_ids: ["public-query"] }),
      "create",
      undefined
    )
  );
  expect(screen.queryByText("public_query_spec")).toBeNull();
});

it("starts a notebook with the public weather references passed from the map", async () => {
  const prepare = vi
    .spyOn(api, "notebookPrepare")
    .mockResolvedValue({ preview_id: "map-note" } as Awaited<
      ReturnType<typeof api.notebookPrepare>
    >);
  render(
    <Provider>
      <NotebookForm
        mode="write"
        initialDate="2026-11-07"
        initialEvidenceIds={["ev-map-weather"]}
        onPreview={vi.fn()}
      />
    </Provider>
  );
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "오늘 다녀온 기록" } });
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "저장할 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "저장할 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        experience_date: "2026-11-07",
        public_evidence_ids: ["ev-map-weather"],
      }),
      "create",
      undefined
    )
  );
});
