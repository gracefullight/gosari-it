import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { NotebookForm } from "@/components/notebook-form";
import { api } from "@/lib/gosari.api";
import { messagesAtom } from "@/stores/chat.atoms";
import {
  clearCommittedNotebookDraftAtom,
  notebookDraftsAtom,
} from "@/stores/notebook-drafts.atoms";

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
    <>
      <button
        type="button"
        onClick={() => onSelect({ address: "제주시 조천읍", latitude: 33.45, longitude: 126.7 })}
      >
        위치 확정
      </button>
      <button
        type="button"
        onClick={() => onSelect({ address: "", latitude: 33.38, longitude: 126.55 })}
      >
        핀 위치 확정
      </button>
    </>
  ),
}));
beforeEach(() => {
  vi.spyOn(api, "notebookRecall").mockResolvedValue({ entries: [], count: 0 });
  vi.spyOn(api, "evidence").mockResolvedValue({});
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
it("keeps a searched address editable without changing its selected map coordinates", async () => {
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
  fireEvent.change(screen.getByLabelText("위치"), { target: { value: "가족과 가는 조천 숲" } });
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "저장할 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "저장할 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        location_address: "가족과 가는 조천 숲",
        latitude: 33.45,
        longitude: 126.7,
      }),
      "create",
      undefined
    )
  );
});

it("gives an unnamed map pin a readable location while preserving its exact coordinates", async () => {
  const prepare = vi
    .spyOn(api, "notebookPrepare")
    .mockResolvedValue({ preview_id: "pin-preview" } as Awaited<
      ReturnType<typeof api.notebookPrepare>
    >);
  render(
    <Provider>
      <NotebookForm mode="write" initialDate="2026-11-07" onPreview={vi.fn()} />
    </Provider>
  );
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), {
    target: { value: "지도에 찍은 채취 장소" },
  });
  fireEvent.click(screen.getByRole("button", { name: "지도 선택" }));
  fireEvent.click(screen.getByRole("button", { name: "핀 위치 확정" }));
  expect((screen.getByLabelText("위치") as HTMLInputElement).value).toBe("지도에서 선택한 위치");
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "저장할 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "저장할 내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        location_address: "지도에서 선택한 위치",
        latitude: 33.38,
        longitude: 126.55,
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
  fireEvent.click(screen.getByText("날씨·가격 자료 연결"));
  fireEvent.click(screen.getByRole("checkbox", { name: "현재 날씨 · 2026-04-12" }));
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

it("restores an unsaved record draft after remount without mixing records or sessions", async () => {
  const session = vi.spyOn(window.localStorage, "getItem").mockReturnValue("session-a");
  const entry = (id: string) => ({
    record_id: id,
    experience_date: "2026-11-07",
    activity_text: `${id} 원본`,
    companion_aliases: [],
    location_address: "원래 장소",
    latitude: 33.380012,
    longitude: 126.550034,
  });
  vi.spyOn(api, "notebookList").mockResolvedValue({
    entries: [entry("first"), entry("second")],
  } as never);
  const store = createStore();
  const node = (id: string) => (
    <Provider store={store}>
      <NotebookForm mode="write" recordId={id} onPreview={vi.fn()} />
    </Provider>
  );
  const view = render(node("first"));
  await screen.findByDisplayValue("first 원본");
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), {
    target: { value: "저장하지 않은 초안" },
  });
  fireEvent.change(screen.getByLabelText("위치"), { target: { value: "초안 장소" } });
  view.rerender(node("second"));
  await screen.findByDisplayValue("second 원본");
  expect(screen.queryByDisplayValue("저장하지 않은 초안")).toBeNull();
  view.rerender(node("first"));
  await screen.findByDisplayValue("저장하지 않은 초안");
  expect((screen.getByLabelText("위치") as HTMLInputElement).value).toBe("초안 장소");
  const restored = store.get(notebookDraftsAtom)[JSON.stringify(["session-a", "first"])];
  expect(restored.location).toEqual({
    address: "초안 장소",
    latitude: 33.380012,
    longitude: 126.550034,
  });
  session.mockReturnValue("session-b");
  view.rerender(node("first"));
  await screen.findByDisplayValue("first 원본");
  expect(screen.queryByDisplayValue("저장하지 않은 초안")).toBeNull();
  view.unmount();
});

it("keeps preview drafts until their exact commit and discards an explicitly cancelled draft", async () => {
  vi.spyOn(window.localStorage, "getItem").mockReturnValue("draft-session");
  vi.spyOn(api, "notebookList").mockResolvedValue({
    entries: [
      {
        record_id: "record",
        experience_date: "2026-11-07",
        activity_text: "원본",
        companion_aliases: [],
      },
    ],
  } as never);
  vi.spyOn(api, "notebookPrepare").mockResolvedValue({ preview_id: "first-preview" } as never);
  const store = createStore();
  const key = JSON.stringify(["draft-session", "record"]);
  const open = () =>
    render(
      <Provider store={store}>
        <NotebookForm mode="write" recordId="record" onPreview={vi.fn()} />
      </Provider>
    );
  let view = open();
  await screen.findByDisplayValue("원본");
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "미리보기 초안" } });
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "수정 내용 확인" }) as HTMLButtonElement).disabled
    ).toBe(false)
  );
  fireEvent.click(screen.getByRole("button", { name: "수정 내용 확인" }));
  await waitFor(() => expect(store.get(notebookDraftsAtom)[key].previewId).toBe("first-preview"));
  view.unmount();
  view = open();
  await screen.findByDisplayValue("미리보기 초안");
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "그 뒤 새 초안" } });
  store.set(clearCommittedNotebookDraftAtom, "first-preview");
  expect(store.get(notebookDraftsAtom)[key].text).toBe("그 뒤 새 초안");
  fireEvent.click(screen.getByRole("button", { name: "수정 내용 확인" }));
  await waitFor(() => expect(store.get(notebookDraftsAtom)[key].previewId).toBe("first-preview"));
  store.set(clearCommittedNotebookDraftAtom, "first-preview");
  expect(store.get(notebookDraftsAtom)[key]).toBeUndefined();
  view.unmount();
  view = open();
  await screen.findByDisplayValue("원본");
  fireEvent.change(screen.getByLabelText(RECORD_LABEL), { target: { value: "취소할 초안" } });
  fireEvent.click(screen.getByRole("button", { name: "작성 취소" }));
  expect(store.get(notebookDraftsAtom)[key]).toBeUndefined();
  view.unmount();
  open();
  await screen.findByDisplayValue("원본");
});
