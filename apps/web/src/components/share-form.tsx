import { FileTextIcon, PlusIcon, UserCircleIcon, UsersThreeIcon } from "@phosphor-icons/react";
import { useAtomValue } from "jotai";
import { useCallback, useEffect, useState } from "react";
import { ShareActivityItem, type SharingActivity } from "@/components/share-activity-item";
import {
  RELATIONSHIPS,
  ShareContactDialog,
  type ShareContactValues,
} from "@/components/share-contact-dialog";
import { ShareRecordForm } from "@/components/share-record-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/gosari.api";
import type {
  NotebookEntry,
  PersonalContact,
  Preview,
  ShareDraft,
  ShareItem,
} from "@/lib/gosari.types";
import { appPathAtom, capabilitiesAtom, revisionCounterAtom } from "@/stores/chat.atoms";

interface ShareFormProps {
  onPreview: (preview: Preview) => void;
}
const LEGACY_ID = "previous-sharing";

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
  const capabilities = useAtomValue(capabilitiesAtom);
  const shareFileAllowed = capabilities?.files?.share_file === true;
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
  }
  async function saveContact(values: ShareContactValues) {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.contactsPrepare(
        { name: values.name.trim(), relationship: values.relationship, notes: values.notes.trim() },
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
  async function prepareShareFile() {
    if (!selectedContact || timeline.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      onPreview(
        await api.shareFilePrepare({
          share_draft_ids: [...new Set(timeline.map((activity) => activity.draft.share_draft_id))],
          contact_id: selectedContact.contact_id,
        })
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "공유 파일을 준비하지 못했습니다.");
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
              className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-base"
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
                        variant="outline"
                        disabled={busy || !shareFileAllowed || timeline.length === 0}
                        aria-describedby={shareFileAllowed ? undefined : "share-file-policy-note"}
                        onClick={() => void prepareShareFile()}
                      >
                        <FileTextIcon />
                        공유 파일
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
                {selectedContact && !shareFileAllowed ? (
                  <p id="share-file-policy-note" className="mt-3 text-base text-muted-foreground">
                    공유 파일 만들기는 이 센터 설정에서 꺼져 있습니다.
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
                <ShareRecordForm
                  recipientName={
                    selectedContact?.name ?? editingActivity?.item.recipient_alias ?? ""
                  }
                  editing={editingActivity != null}
                  values={{ date: recordDate, status, amount, unit, sourceRecord }}
                  onChange={(values) => {
                    setRecordDate(values.date);
                    setStatus(values.status);
                    setAmount(values.amount);
                    setUnit(values.unit);
                    setSourceRecord(values.sourceRecord);
                  }}
                  notebooks={notebooks}
                  busy={busy}
                  onCancel={() => setRecordOpen(false)}
                  onSave={() => void saveActivity()}
                />
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
                  {timeline.map((activity) => (
                    <ShareActivityItem
                      key={activity.key}
                      activity={activity}
                      notebooks={notebooks}
                      busy={busy}
                      onEdit={editActivity}
                      onDelete={deleteActivity}
                    />
                  ))}
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
        <ShareContactDialog
          mode={contactDialog}
          contact={selectedContact ?? null}
          error={error}
          busy={busy}
          onCancel={() => setContactDialog(null)}
          onSave={(values) => void saveContact(values)}
        />
      ) : null}
    </section>
  );
}
