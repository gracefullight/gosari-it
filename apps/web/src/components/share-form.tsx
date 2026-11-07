import { PlusIcon, UserCircleIcon, UsersThreeIcon } from "@phosphor-icons/react";
import { useAtomValue } from "jotai";
import { useCallback, useEffect, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { PublicEvidenceLinks } from "@/components/public-evidence-links";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDisplayDate } from "@/lib/date-format";
import { ApiError, api } from "@/lib/gosari.api";
import type {
  NotebookEntry,
  PersonalContact,
  Preview,
  ShareDraft,
  ShareItem,
} from "@/lib/gosari.types";
import { appPathAtom, revisionCounterAtom } from "@/stores/chat.atoms";

interface ShareFormProps {
  onPreview: (preview: Preview) => void;
}
const RELATIONSHIPS: PersonalContact["relationship"][] = [
  "가족",
  "친척",
  "친구",
  "이웃",
  "동료",
  "기타",
];
const LEGACY_ID = "previous-sharing";
interface SharingActivity {
  key: string;
  item: ShareItem;
  recordedAt: string;
  draft: ShareDraft;
  index: number;
}

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function contactForItem(item: ShareItem, contacts: PersonalContact[]): PersonalContact | undefined {
  if (item.contact_id) return contacts.find((contact) => contact.contact_id === item.contact_id);
  const matches = contacts.filter((contact) => contact.name === item.recipient_alias);
  return matches.length === 1 ? matches[0] : undefined;
}

export function ShareForm({ onPreview }: ShareFormProps) {
  const revision = useAtomValue(revisionCounterAtom);
  const path = useAtomValue(appPathAtom);
  const requestedContact = new URLSearchParams(path.split("?")[1] ?? "").get("contact");
  const [contacts, setContacts] = useState<PersonalContact[]>([]);
  const [drafts, setDrafts] = useState<ShareDraft[]>([]);
  const [notebooks, setNotebooks] = useState<NotebookEntry[]>([]);
  const requestedRecord = new URLSearchParams(path.split("?")[1] ?? "").get("record");
  const [sourceRecord, setSourceRecord] = useState(requestedRecord ?? "");
  const [editingActivity, setEditingActivity] = useState<SharingActivity | null>(null);
  const [selectedId, setSelectedId] = useState<{ path: string; id: string } | null>(null);
  const [query, setQuery] = useState("");
  const [relationship, setRelationship] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contactDialog, setContactDialog] = useState<"create" | "update" | null>(null);
  const [contactName, setContactName] = useState("");
  const [contactRelationship, setContactRelationship] =
    useState<PersonalContact["relationship"]>("가족");
  const [contactNotes, setContactNotes] = useState("");
  const [recordOpen, setRecordOpen] = useState(false);
  const [recordDate, setRecordDate] = useState(today);
  const [amount, setAmount] = useState("1");
  const [unit, setUnit] = useState("봉지");
  const [status, setStatus] = useState<"planned" | "delivered">("delivered");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [contactResult, draftResult] = await Promise.allSettled([
      api.contactsList(),
      api.shareList(),
    ]);
    // Notebook lookup is optional; existing sharing history remains available on failure.
    void api
      .notebookList()
      .then((result) => setNotebooks(result.entries))
      .catch(() => {});
    if (contactResult.status === "fulfilled") setContacts(contactResult.value.contacts);
    if (draftResult.status === "fulfilled") setDrafts(draftResult.value.drafts);
    if (contactResult.status === "rejected" || draftResult.status === "rejected")
      setError("나눔 정보를 불러오지 못했습니다.");
    setLoading(false);
  }, []);
  useEffect(() => {
    void revision;
    void load();
  }, [load, revision]);

  const activities: SharingActivity[] = drafts.flatMap((draft) =>
    draft.items.map((item, index) => ({
      key: `${draft.share_draft_id}-${index}`,
      item,
      recordedAt: draft.prepared_at,
      draft,
      index,
    }))
  );
  const previous = activities.filter(({ item }) => !contactForItem(item, contacts));
  const visibleContacts = contacts.filter(
    (contact) =>
      (!relationship || contact.relationship === relationship) &&
      (!query.trim() ||
        `${contact.name} ${contact.notes}`
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase()))
  );
  const preferredId = selectedId?.path === path ? selectedId.id : requestedContact;
  const selection =
    preferredId &&
    (contacts.some((contact) => contact.contact_id === preferredId) || preferredId === LEGACY_ID)
      ? preferredId
      : (visibleContacts[0]?.contact_id ?? (previous.length > 0 ? LEGACY_ID : null));
  const selectedContact = contacts.find((contact) => contact.contact_id === selection);
  const timeline = (
    selection === LEGACY_ID
      ? previous
      : activities.filter(
          ({ item }) =>
            contactForItem(item, contacts)?.contact_id === selectedContact?.contact_id &&
            selectedContact != null
        )
  ).sort((a, b) =>
    (b.item.occurred_on ?? b.recordedAt).localeCompare(a.item.occurred_on ?? a.recordedAt)
  );
  const delivered = timeline.filter(({ item }) => item.status === "delivered");
  const totals = delivered.reduce<Record<string, number>>((sum, { item }) => {
    const value = Number(item.amount_value);
    if (Number.isFinite(value)) sum[item.amount_unit] = (sum[item.amount_unit] ?? 0) + value;
    return sum;
  }, {});

  function selectContact(id: string) {
    setSelectedId({ path, id });
    setRecordOpen(false);
    setEditingActivity(null);
    setError(null);
  }
  function openContact(mode: "create" | "update") {
    setContactDialog(mode);
    setError(null);
    setContactName(mode === "update" ? (selectedContact?.name ?? "") : "");
    setContactRelationship(mode === "update" ? (selectedContact?.relationship ?? "가족") : "가족");
    setContactNotes(mode === "update" ? (selectedContact?.notes ?? "") : "");
  }
  async function saveContact() {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.contactsPrepare(
        { name: contactName.trim(), relationship: contactRelationship, notes: contactNotes.trim() },
        contactDialog === "update" ? "update" : "create",
        contactDialog === "update" ? selectedContact?.contact_id : undefined
      );
      setContactDialog(null);
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "지인 정보를 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  async function deleteContact() {
    if (!selectedContact) return;
    setBusy(true);
    setError(null);
    try {
      onPreview(await api.contactsPrepare({}, "delete", selectedContact.contact_id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "지인 정보를 확인하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  function editActivity(activity: SharingActivity, delivered = false) {
    setEditingActivity(activity);
    setRecordDate(delivered ? today() : (activity.item.occurred_on ?? ""));
    setAmount(String(activity.item.amount_value));
    setUnit(activity.item.amount_unit);
    setStatus(delivered ? "delivered" : (activity.item.status ?? "planned"));
    setSourceRecord(activity.draft.source_record_ids[0] ?? "");
    setRecordOpen(true);
    setError(null);
  }
  async function deleteActivity(activity: SharingActivity) {
    setBusy(true);
    setError(null);
    try {
      const remaining = activity.draft.items.filter((_, index) => index !== activity.index);
      onPreview(
        await api.sharePrepare(
          remaining.length
            ? {
                items: remaining,
                message_enabled: false,
                expected_revision: activity.draft.revision,
              }
            : { expected_revision: activity.draft.revision },
          remaining.length ? "update" : "delete",
          activity.draft.share_draft_id
        )
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "나눔 기록을 삭제하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  async function saveActivity() {
    if (!selectedContact && !editingActivity) return;
    setBusy(true);
    setError(null);
    try {
      const item: ShareItem = {
        ...editingActivity?.item,
        ...(selectedContact
          ? { contact_id: selectedContact.contact_id, recipient_alias: selectedContact.name }
          : {}),
        recipient_alias: selectedContact?.name ?? editingActivity?.item.recipient_alias ?? "",
        amount_value: Number(amount),
        amount_unit: unit.trim(),
        occurred_on: recordDate || null,
        status,
      };
      const sourceIds = editingActivity
        ? [
            ...new Set([
              ...editingActivity.draft.source_record_ids.slice(1),
              ...(sourceRecord ? [sourceRecord] : []),
            ]),
          ]
        : sourceRecord
          ? [sourceRecord]
          : [];
      const evidenceIds = [
        ...new Set([
          ...(editingActivity?.draft.public_evidence_ids ?? []),
          ...notebooks
            .filter((entry) => sourceIds.includes(entry.record_id))
            .flatMap((entry) => entry.public_evidence_ids ?? []),
        ]),
      ];
      const payload = {
        items: editingActivity
          ? editingActivity.draft.items.map((old, index) =>
              index === editingActivity.index ? item : old
            )
          : [item],
        message_enabled: false,
        ...(editingActivity ? { expected_revision: editingActivity.draft.revision } : {}),
        ...(sourceIds.length || editingActivity ? { source_record_ids: sourceIds } : {}),
        ...(evidenceIds.length ? { public_evidence_ids: evidenceIds } : {}),
      };
      const preview = editingActivity
        ? await api.sharePrepare(payload, "update", editingActivity.draft.share_draft_id)
        : await api.sharePrepare(payload);
      setRecordOpen(false);
      setEditingActivity(null);
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "나눔 기록을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div className="flex items-baseline gap-2">
          <h2 className="text-xl font-semibold">지인</h2>
          <span className="text-base tabular-nums text-muted-foreground">{contacts.length}명</span>
        </div>
        <Button onClick={() => openContact("create")}>
          <PlusIcon />
          지인 추가
        </Button>
      </header>
      {error && !contactDialog ? (
        <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
          <p role="alert" className="text-base text-destructive">
            {error}
          </p>
          <Button variant="ghost" size="sm" onClick={() => void load()}>
            다시 불러오기
          </Button>
        </div>
      ) : null}
      <div className="grid min-h-[34rem] lg:grid-cols-[18rem_minmax(0,1fr)]">
        <aside className="border-b border-border lg:border-r lg:border-b-0" aria-label="지인 목록">
          <div className="space-y-3 p-4">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="이름·메모 검색"
              aria-label="지인 검색"
            />
            <select
              className="h-10 w-full rounded-lg border border-input bg-background px-3 text-base"
              value={relationship}
              onChange={(event) => setRelationship(event.target.value)}
              aria-label="관계 필터"
            >
              <option value="">모든 관계</option>
              {RELATIONSHIPS.map((relation) => (
                <option key={relation} value={relation}>
                  {relation}
                </option>
              ))}
            </select>
          </div>
          {loading ? (
            <p role="status" className="px-5 py-4 text-base text-muted-foreground">
              지인 불러오는 중…
            </p>
          ) : null}
          {!loading && visibleContacts.length === 0 ? (
            <p className="px-5 py-6 text-base text-muted-foreground">
              {query || relationship ? "조건에 맞는 지인이 없습니다." : "등록한 지인이 없습니다."}
            </p>
          ) : null}
          <ul className="max-h-64 overflow-y-auto px-2 pb-2 lg:max-h-[38rem]">
            {visibleContacts.map((contact) => {
              const count = activities.filter(
                ({ item }) => contactForItem(item, contacts)?.contact_id === contact.contact_id
              ).length;
              return (
                <li key={contact.contact_id}>
                  <button
                    type="button"
                    aria-pressed={selection === contact.contact_id}
                    onClick={() => selectContact(contact.contact_id)}
                    className={`flex min-h-14 w-full items-center gap-3 rounded-lg px-3 py-3 text-left focus-visible:outline-2 focus-visible:outline-ring ${selection === contact.contact_id ? "bg-accent text-accent-foreground" : "hover:bg-muted"}`}
                  >
                    <UserCircleIcon className="size-7 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate font-medium">{contact.name}</span>
                    <span className="text-base text-muted-foreground">{contact.relationship}</span>
                    <span className="text-base tabular-nums text-muted-foreground">{count}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          {previous.length > 0 ? (
            <button
              type="button"
              aria-pressed={selection === LEGACY_ID}
              onClick={() => selectContact(LEGACY_ID)}
              className={`flex min-h-12 w-full items-center justify-between border-t border-border px-5 text-base ${selection === LEGACY_ID ? "bg-accent" : "hover:bg-muted"}`}
            >
              <span>이전 나눔</span>
              <span className="tabular-nums text-muted-foreground">{previous.length}</span>
            </button>
          ) : null}
        </aside>
        <div className="min-w-0 px-5 py-6 sm:px-7">
          {!selectedContact && selection !== LEGACY_ID ? (
            <div className="flex h-full min-h-72 flex-col items-center justify-center gap-3 text-center">
              <UsersThreeIcon className="size-10 text-muted-foreground" />
              <p className="font-medium">
                {contacts.length ? "지인을 선택하세요." : "지인을 추가해 주세요."}
              </p>
              <Button variant="outline" onClick={() => openContact("create")}>
                지인 추가
              </Button>
            </div>
          ) : (
            <>
              <div className="mb-6 border-b border-border pb-6">
                <p className="mb-3 text-base text-muted-foreground">
                  {selectedContact
                    ? `나 → ${selectedContact.relationship} → ${selectedContact.name}`
                    : "나 → 이전 나눔"}
                </p>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-3xl font-semibold tracking-tight">
                      {selectedContact?.name ?? "이전 나눔"}
                    </h3>
                    {selectedContact ? (
                      <p className="mt-2 text-base text-muted-foreground">
                        {selectedContact.relationship}
                      </p>
                    ) : null}
                  </div>
                  {selectedContact ? (
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => openContact("update")}>
                        지인 수정
                      </Button>
                      <Button
                        onClick={() => {
                          setEditingActivity(null);
                          setSourceRecord(requestedRecord ?? "");
                          setRecordDate(today());
                          setAmount("1");
                          setUnit("봉지");
                          setStatus("delivered");
                          setRecordOpen((open) => !open);
                        }}
                      >
                        <PlusIcon />
                        나눔 기록
                      </Button>
                    </div>
                  ) : null}
                </div>
                {selectedContact?.notes ? (
                  <p className="mt-4 whitespace-pre-wrap text-base leading-relaxed text-muted-foreground">
                    {selectedContact.notes}
                  </p>
                ) : null}
                <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2 text-base">
                  <span className="text-muted-foreground">
                    전달 완료{" "}
                    <strong className="ml-2 font-semibold tabular-nums text-foreground">
                      {delivered.length}회
                    </strong>
                  </span>
                  {Object.entries(totals).map(([key, total]) => (
                    <span key={key} className="font-medium tabular-nums">
                      {total.toLocaleString()}
                      {key}
                    </span>
                  ))}
                </div>
              </div>
              {recordOpen && (selectedContact || editingActivity) ? (
                <div className="mb-7 rounded-xl bg-muted/60 p-4">
                  <h4 className="mb-4 font-semibold">
                    {selectedContact?.name ?? editingActivity?.item.recipient_alias} 나눔{" "}
                    {editingActivity ? "수정" : "기록"}
                  </h4>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="share-occurred-on">날짜</Label>
                      <DatePickerField
                        id="share-occurred-on"
                        required={status === "delivered"}
                        aria-label="나눔 날짜"
                        value={recordDate}
                        onChange={setRecordDate}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="share-status">상태</Label>
                      <select
                        id="share-status"
                        value={status}
                        onChange={(event) =>
                          setStatus(event.target.value as "planned" | "delivered")
                        }
                        className="h-10 rounded-lg border border-input bg-background px-3 text-base"
                      >
                        <option value="delivered">전달 완료</option>
                        <option value="planned">전달 예정</option>
                      </select>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="share-amount">분량</Label>
                      <Input
                        id="share-amount"
                        type="number"
                        min="0"
                        step="any"
                        value={amount}
                        onChange={(event) => setAmount(event.target.value)}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="share-unit">단위</Label>
                      <Input
                        id="share-unit"
                        value={unit}
                        onChange={(event) => setUnit(event.target.value)}
                        placeholder="봉지, g, kg"
                      />
                    </div>
                  </div>
                  {notebooks.length ? (
                    <div className="mt-4 grid gap-2">
                      <Label htmlFor="share-source-record">연결할 수첩 기록</Label>
                      <select
                        id="share-source-record"
                        value={sourceRecord}
                        onChange={(event) => setSourceRecord(event.target.value)}
                        className="min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base"
                      >
                        <option value="">연결 안 함</option>
                        {notebooks.map((entry) => (
                          <option key={entry.record_id} value={entry.record_id}>
                            {formatDisplayDate(entry.experience_date)} ·{" "}
                            {entry.activity_text.slice(0, 50)}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : null}
                  <div className="mt-4 flex justify-end gap-2">
                    <Button variant="ghost" onClick={() => setRecordOpen(false)}>
                      취소
                    </Button>
                    <Button
                      onClick={() => void saveActivity()}
                      disabled={
                        busy ||
                        !unit.trim() ||
                        !Number.isFinite(Number(amount)) ||
                        Number(amount) <= 0 ||
                        (status === "delivered" && !recordDate)
                      }
                    >
                      기록 확인
                    </Button>
                  </div>
                </div>
              ) : null}
              <h4 className="mb-5 text-base font-semibold">
                나눔 이력{" "}
                <span className="ml-1 text-base font-normal tabular-nums text-muted-foreground">
                  {timeline.length}
                </span>
              </h4>
              {timeline.length === 0 ? (
                <p className="py-8 text-base text-muted-foreground">아직 나눔 기록이 없습니다.</p>
              ) : (
                <ol className="space-y-0">
                  {timeline.map((activity) => {
                    const { key, item, recordedAt, draft } = activity;
                    return (
                      <li
                        key={key}
                        className="relative ml-1 border-l border-border pb-6 pl-6 last:pb-1"
                      >
                        <span
                          className={`absolute top-1 -left-1.5 size-3 rounded-full border-2 border-card ${item.status === "delivered" ? "bg-primary" : "bg-muted-foreground"}`}
                        />
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="font-medium tabular-nums">
                            {item.recipient_alias}{" "}
                            <span className="ml-2">
                              {Number(item.amount_value).toLocaleString()}
                              {item.amount_unit}
                            </span>
                          </p>
                          <span className="text-base text-muted-foreground">
                            {item.status === "delivered" ? "전달 완료" : "전달 예정"}
                          </span>
                        </div>
                        <p className="mt-1 text-base tabular-nums text-muted-foreground">
                          {item.occurred_on || item.planned_delivery
                            ? formatDisplayDate(item.occurred_on ?? item.planned_delivery)
                            : `등록 ${formatDisplayDate(recordedAt)}`}
                        </p>
                        {draft.source_record_ids.length ? (
                          <div className="mt-2 flex flex-wrap gap-2">
                            {draft.source_record_ids.map((id) => {
                              const entry = notebooks.find((record) => record.record_id === id);
                              return entry ? (
                                <a
                                  key={id}
                                  href={`/notebook/${encodeURIComponent(id)}/edit`}
                                  className="inline-flex min-h-11 items-center text-base text-primary underline underline-offset-4"
                                >
                                  수첩 · {formatDisplayDate(entry.experience_date)}
                                </a>
                              ) : (
                                <span key={id} className="text-base text-muted-foreground">
                                  연결된 이전 수첩 기록
                                </span>
                              );
                            })}
                          </div>
                        ) : null}
                        <PublicEvidenceLinks ids={draft.public_evidence_ids} />
                        <div className="mt-2 flex flex-wrap gap-2">
                          {item.status !== "delivered" ? (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={busy}
                              onClick={() => editActivity(activity, true)}
                            >
                              전달 완료로 변경
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => editActivity(activity)}
                          >
                            기록 수정
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => void deleteActivity(activity)}
                          >
                            기록 삭제
                          </Button>
                        </div>
                        {item.optional_role_note ? (
                          <p className="mt-2 text-base text-muted-foreground">
                            {item.optional_role_note}
                          </p>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
              )}
              {selectedContact ? (
                <div className="mt-10 border-t border-border pt-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground"
                    disabled={busy}
                    onClick={() => void deleteContact()}
                  >
                    지인 삭제
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </div>
      {contactDialog ? (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setContactDialog(null);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{contactDialog === "create" ? "지인 추가" : "지인 수정"}</DialogTitle>
              <DialogDescription>이름과 나와의 관계를 기록하세요.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="contact-name">이름</Label>
                <Input
                  id="contact-name"
                  autoFocus
                  maxLength={100}
                  value={contactName}
                  onChange={(event) => setContactName(event.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="contact-relationship">관계</Label>
                <select
                  id="contact-relationship"
                  value={contactRelationship}
                  onChange={(event) =>
                    setContactRelationship(event.target.value as PersonalContact["relationship"])
                  }
                  className="h-10 rounded-lg border border-input bg-background px-3 text-base"
                >
                  {RELATIONSHIPS.map((relation) => (
                    <option key={relation} value={relation}>
                      {relation}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="contact-notes">메모</Label>
                <Textarea
                  id="contact-notes"
                  rows={3}
                  maxLength={2000}
                  value={contactNotes}
                  onChange={(event) => setContactNotes(event.target.value)}
                  placeholder="기억할 내용을 적어 주세요."
                />
              </div>
              {error ? (
                <p role="alert" className="text-base text-destructive">
                  {error}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setContactDialog(null)}>
                취소
              </Button>
              <Button disabled={busy || !contactName.trim()} onClick={() => void saveContact()}>
                내용 확인
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
