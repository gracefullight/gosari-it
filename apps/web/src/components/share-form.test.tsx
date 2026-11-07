import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ShareForm } from "@/components/share-form";
import { api } from "@/lib/gosari.api";
import type { PersonalContact, ShareDraft } from "@/lib/gosari.types";
import { appPathAtom } from "@/stores/chat.atoms";

const PREVIOUS_SHARING = /이전 나눔/;
const MOTHER_NAME = /어머니/;
const FRIEND_NAME = /민수/;

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
const contacts: PersonalContact[] = [
  {
    contact_id: "mother",
    revision: 1,
    name: "어머니",
    relationship: "가족",
    notes: "생고사리를 좋아함",
    created_at: "2026-04-01",
    updated_at: "2026-04-01",
  },
  {
    contact_id: "friend",
    revision: 1,
    name: "민수",
    relationship: "친구",
    notes: "주말에 만남",
    created_at: "2026-04-01",
    updated_at: "2026-04-01",
  },
];
const drafts: ShareDraft[] = [
  {
    share_draft_id: "draft",
    revision: 1,
    message_enabled: true,
    editable_message: "이전 문자 초안",
    source_record_ids: [],
    public_evidence_ids: [],
    prepared_at: "2026-04-12",
    items: [
      {
        contact_id: "mother",
        recipient_alias: "어머니",
        amount_value: "2",
        amount_unit: "봉지",
        occurred_on: "2026-04-12",
        status: "delivered",
      },
      {
        contact_id: "mother",
        recipient_alias: "어머니",
        amount_value: "300",
        amount_unit: "g",
        occurred_on: "2026-04-13",
        status: "delivered",
      },
      {
        recipient_alias: "예전 지인",
        amount_value: "1",
        amount_unit: "봉지",
        planned_delivery: "지난 봄",
      },
    ],
  },
];
beforeEach(() => {
  vi.spyOn(api, "contactsList").mockResolvedValue({ contacts });
  vi.spyOn(api, "shareList").mockResolvedValue({ drafts });
  vi.spyOn(api, "notebookList").mockResolvedValue({ entries: [] });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});
function mount() {
  const onPreview = vi.fn();
  render(
    <Provider>
      <ShareForm onPreview={onPreview} />
    </Provider>
  );
  return onPreview;
}

it("groups sharing history under people and keeps quantities in their original units", async () => {
  mount();
  await screen.findByRole("heading", { name: "어머니" });
  expect(screen.getByText("나 → 가족 → 어머니")).toBeTruthy();
  expect(screen.getByText("생고사리를 좋아함")).toBeTruthy();
  expect(screen.getAllByText("2봉지").length).toBeGreaterThan(0);
  expect(screen.getAllByText("300g").length).toBeGreaterThan(0);
  expect(screen.queryByText("이전 문자 초안")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: PREVIOUS_SHARING }));
  expect(screen.getByText("예전 지인")).toBeTruthy();
});

it("filters contacts by name and relationship", async () => {
  mount();
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.change(screen.getByRole("combobox", { name: "관계 필터" }), {
    target: { value: "친구" },
  });
  expect(screen.queryByRole("button", { name: MOTHER_NAME })).toBeNull();
  expect(screen.getByRole("button", { name: FRIEND_NAME })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("지인 검색"), { target: { value: "없는이름" } });
  expect(screen.getByText("조건에 맞는 지인이 없습니다.")).toBeTruthy();
});

it("submits a contact-linked dated sharing record with message generation disabled", async () => {
  const prepare = vi
    .spyOn(api, "sharePrepare")
    .mockResolvedValue({ preview_id: "preview" } as Awaited<ReturnType<typeof api.sharePrepare>>);
  const onPreview = mount();
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.click(screen.getByRole("button", { name: "나눔 기록" }));
  fireEvent.change(screen.getByLabelText("날짜"), { target: { value: "2026-04-15" } });
  fireEvent.change(screen.getByLabelText("분량"), { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "기록 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith({
      items: [
        {
          contact_id: "mother",
          recipient_alias: "어머니",
          amount_value: 3,
          amount_unit: "봉지",
          occurred_on: "2026-04-15",
          status: "delivered",
        },
      ],
      message_enabled: false,
    })
  );
  expect(onPreview).toHaveBeenCalled();
});

it("creates a person with a relationship and notes through the approval preview", async () => {
  const prepare = vi
    .spyOn(api, "contactsPrepare")
    .mockResolvedValue({ preview_id: "contact-preview" } as Awaited<
      ReturnType<typeof api.contactsPrepare>
    >);
  mount();
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.click(screen.getByRole("button", { name: "지인 추가" }));
  fireEvent.change(screen.getByLabelText("이름"), { target: { value: "이모" } });
  fireEvent.change(screen.getByLabelText("관계", { exact: true }), { target: { value: "친척" } });
  fireEvent.change(screen.getByLabelText("메모"), { target: { value: "다음 주 방문" } });
  fireEvent.click(screen.getByRole("button", { name: "내용 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      { name: "이모", relationship: "친척", notes: "다음 주 방문" },
      "create",
      undefined
    )
  );
});

it("selects the contact referenced by a sharing link", async () => {
  window.history.replaceState({}, "", "/share?contact=friend");
  const store = createStore();
  store.set(appPathAtom, "/share?contact=friend");
  render(
    <Provider store={store}>
      <ShareForm onPreview={vi.fn()} />
    </Provider>
  );
  await screen.findByRole("heading", { name: "민수" });
  expect(screen.getByText("나 → 친구 → 민수")).toBeTruthy();
});

it("edits one legacy multi-item record without replacing the remaining recipients", async () => {
  const prepare = vi
    .spyOn(api, "sharePrepare")
    .mockResolvedValue({ preview_id: "edit" } as Awaited<ReturnType<typeof api.sharePrepare>>);
  mount();
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.click(screen.getAllByRole("button", { name: "기록 수정" })[0]);
  fireEvent.change(screen.getByLabelText("분량"), { target: { value: "400" } });
  fireEvent.click(screen.getByRole("button", { name: "기록 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        items: [
          drafts[0].items[0],
          expect.objectContaining({ amount_value: 400 }),
          drafts[0].items[2],
        ],
        message_enabled: false,
      }),
      "update",
      "draft"
    )
  );
});

it("removes only the chosen item from a shared legacy draft", async () => {
  const prepare = vi
    .spyOn(api, "sharePrepare")
    .mockResolvedValue({ preview_id: "delete" } as Awaited<ReturnType<typeof api.sharePrepare>>);
  mount();
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.click(screen.getAllByRole("button", { name: "기록 삭제" })[0]);
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      {
        items: [drafts[0].items[0], drafts[0].items[2]],
        message_enabled: false,
        expected_revision: 1,
      },
      "update",
      "draft"
    )
  );
});

it("changes a planned activity to delivered after choosing the delivery date", async () => {
  vi.mocked(api.shareList).mockResolvedValue({
    drafts: [
      { ...drafts[0], items: [{ ...drafts[0].items[0], status: "planned", occurred_on: null }] },
    ],
  });
  const prepare = vi
    .spyOn(api, "sharePrepare")
    .mockResolvedValue({ preview_id: "deliver" } as Awaited<ReturnType<typeof api.sharePrepare>>);
  mount();
  await screen.findByRole("button", { name: "전달 완료로 변경" });
  fireEvent.click(screen.getByRole("button", { name: "전달 완료로 변경" }));
  fireEvent.change(screen.getByLabelText("날짜"), { target: { value: "2026-04-20" } });
  fireEvent.click(screen.getByRole("button", { name: "기록 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        items: [expect.objectContaining({ status: "delivered", occurred_on: "2026-04-20" })],
      }),
      "update",
      "draft"
    )
  );
});

it("inherits the source notebook and its public evidence on a linked new activity", async () => {
  window.history.replaceState({}, "", "/share?record=notebook-1");
  const store = createStore();
  store.set(appPathAtom, "/share?record=notebook-1");
  vi.mocked(api.notebookList).mockResolvedValue({
    entries: [
      {
        record_id: "notebook-1",
        experience_date: "2026-04-12",
        activity_text: "봄 채취",
        public_evidence_ids: ["weather-1"],
      } as never,
    ],
  });
  const prepare = vi
    .spyOn(api, "sharePrepare")
    .mockResolvedValue({ preview_id: "linked" } as Awaited<ReturnType<typeof api.sharePrepare>>);
  render(
    <Provider store={store}>
      <ShareForm onPreview={vi.fn()} />
    </Provider>
  );
  await screen.findByRole("heading", { name: "어머니" });
  fireEvent.click(screen.getByRole("button", { name: "나눔 기록" }));
  await screen.findByRole("option", { name: "2026-04-12 · 봄 채취" });
  fireEvent.click(screen.getByRole("button", { name: "기록 확인" }));
  await waitFor(() =>
    expect(prepare).toHaveBeenCalledWith(
      expect.objectContaining({
        source_record_ids: ["notebook-1"],
        public_evidence_ids: ["weather-1"],
      })
    )
  );
});
