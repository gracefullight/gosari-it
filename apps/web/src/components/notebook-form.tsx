import { MapPinIcon, PencilSimpleIcon, PlusIcon } from "@phosphor-icons/react";
import { useAtomValue } from "jotai";
import { useCallback, useEffect, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { DateSelectionCalendar } from "@/components/date-selection-calendar";
import { LocationPickerDialog, type SelectedLocation } from "@/components/location-picker-dialog";
import { PublicEvidenceLinks, PublicEvidenceSelector } from "@/components/public-evidence-links";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDisplayDate } from "@/lib/date-format";
import { ApiError, api } from "@/lib/gosari.api";
import type { NotebookEntry, Preview } from "@/lib/gosari.types";
import { revisionCounterAtom } from "@/stores/chat.atoms";

interface NotebookFormProps {
  onPreview: (preview: Preview) => void;
  mode?: "list" | "write";
  recordId?: string;
  initialDate?: string;
  initialEvidenceIds?: string[];
  onNavigate?: (path: string) => void;
}

export function NotebookForm({
  onPreview,
  mode,
  recordId,
  initialDate,
  initialEvidenceIds,
  onNavigate,
}: NotebookFormProps) {
  const revision = useAtomValue(revisionCounterAtom);
  const [localMode, setLocalMode] = useState<"list" | "write">("list");
  const activeMode = mode ?? localMode;
  const [editingId, setEditingId] = useState<string | undefined>(recordId);
  const [view, setView] = useState<"list" | "calendar">("list");
  const [calendarDate, setCalendarDate] = useState(() => new Date().toLocaleDateString("en-CA"));
  const [entries, setEntries] = useState<NotebookEntry[]>([]);
  const [date, setDate] = useState(initialDate ?? "");
  const [text, setText] = useState("");
  const [aliases, setAliases] = useState("");
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState("봉지");
  const [location, setLocation] = useState<SelectedLocation | null>(null);
  const [locationOpen, setLocationOpen] = useState(false);
  const [evidenceIds, setEvidenceIds] = useState<string[]>(() => [
    ...new Set(initialEvidenceIds ?? []),
  ]);
  const [privateRegionId, setPrivateRegionId] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [aliasFilter, setAliasFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = (nextMode: "list" | "write", id?: string, selectedDate?: string) => {
    setLocalMode(nextMode);
    setEditingId(id);
    onNavigate?.(
      nextMode === "list"
        ? "/notebook"
        : id
          ? `/notebook/${encodeURIComponent(id)}/edit`
          : selectedDate
            ? `/notebook/new?date=${encodeURIComponent(selectedDate)}`
            : "/notebook/new"
    );
  };
  const loadEntries = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.notebookRecall({
        start: start || undefined,
        end: end || undefined,
        alias: aliasFilter || undefined,
      });
      setEntries(result.entries);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "기록을 불러오지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }, [start, end, aliasFilter]);
  useEffect(() => {
    void revision;
    void loadEntries();
  }, [loadEntries, revision]);
  const populate = useCallback((entry: NotebookEntry) => {
    setEditingId(entry.record_id);
    setEvidenceIds(entry.public_evidence_ids ?? []);
    setPrivateRegionId(entry.private_region_id ?? null);
    setDate(entry.experience_date);
    setText(entry.activity_text);
    setAliases(entry.companion_aliases.join(", "));
    setAmount(entry.amount_value ?? "");
    setUnit(entry.amount_unit ?? "봉지");
    setLocation(
      entry.location_address || entry.latitude != null
        ? {
            address: entry.location_address ?? "",
            latitude: entry.latitude ?? null,
            longitude: entry.longitude ?? null,
          }
        : null
    );
  }, []);
  useEffect(() => {
    if (!recordId) return;
    let active = true;
    api
      .notebookList()
      .then((result) => {
        const entry = result.entries.find((item) => item.record_id === recordId);
        if (!active) return;
        if (entry) populate(entry);
        else setError("기록을 찾을 수 없습니다.");
      })
      .catch(() => {
        if (active) setError("기록을 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [recordId, populate]);
  function startNew() {
    setDate("");
    setText("");
    setAliases("");
    setAmount("");
    setUnit("봉지");
    setLocation(null);
    setEvidenceIds([]);
    setPrivateRegionId(null);
    setError(null);
    navigate("write");
  }
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        experience_date: date,
        activity_text: text,
        companion_aliases: aliases
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        amount_value: amount ? Number(amount) : null,
        amount_unit: amount ? unit : null,
        location_address: location?.address || null,
        latitude: location?.latitude ?? null,
        longitude: location?.longitude ?? null,
        public_evidence_ids: evidenceIds,
        private_region_id: privateRegionId,
      };
      onPreview(await api.notebookPrepare(payload, editingId ? "update" : "create", editingId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "미리보기를 만들지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }
  async function requestDelete(id: string) {
    setBusy(true);
    setError(null);
    try {
      onPreview(await api.notebookPrepare({}, "delete", id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "삭제할 기록을 확인하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">
          {activeMode === "list"
            ? `내 기록 ${entries.length}`
            : editingId
              ? "기록 수정"
              : "새 기록"}
        </h2>
        {activeMode === "list" ? (
          <Button onClick={startNew}>
            <PlusIcon />
            기록 쓰기
          </Button>
        ) : (
          <Button variant="outline" onClick={() => navigate("list")}>
            목록으로
          </Button>
        )}
      </div>
      {activeMode === "list" ? (
        <fieldset className="flex gap-2" aria-label="수첩 보기 방식">
          <Button
            variant={view === "list" ? "default" : "outline"}
            size="sm"
            onClick={() => setView("list")}
          >
            목록
          </Button>
          <Button
            variant={view === "calendar" ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setStart("");
              setEnd("");
              setView("calendar");
            }}
          >
            달력
          </Button>
        </fieldset>
      ) : null}
      {error ? (
        <p role="alert" className="text-base text-destructive">
          {error}
        </p>
      ) : null}
      {activeMode === "write" ? (
        <div className="grid gap-5 rounded-2xl border border-border bg-card p-5 sm:p-7">
          <div className="grid gap-2">
            <Label htmlFor="notebook-date" required>
              채취 날짜
            </Label>
            <DatePickerField
              id="notebook-date"
              required
              aria-label="채취 날짜"
              value={date}
              onChange={setDate}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="notebook-location">위치</Label>
            <div className="flex gap-2">
              <Input
                id="notebook-location"
                value={
                  location?.address ||
                  (location?.latitude != null
                    ? `${location.latitude.toFixed(5)}, ${location.longitude?.toFixed(5)}`
                    : "")
                }
                placeholder="지도에서 위치 선택"
                readOnly
              />
              <Button variant="outline" onClick={() => setLocationOpen(true)}>
                <MapPinIcon />
                지도 선택
              </Button>
            </div>
            {location ? (
              <Button className="w-fit" variant="ghost" size="sm" onClick={() => setLocation(null)}>
                위치 지우기
              </Button>
            ) : null}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="notebook-text" required>
              기록
            </Label>
            <Textarea
              id="notebook-text"
              aria-required="true"
              rows={6}
              className="field-sizing-fixed min-h-40"
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="오늘 채취한 고사리와 기억할 일을 남겨 보세요."
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="notebook-aliases">동행</Label>
            <Input
              id="notebook-aliases"
              value={aliases}
              onChange={(e) => setAliases(e.target.value)}
              placeholder="예: 어머니, 이웃"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="notebook-amount">수량</Label>
              <Input
                id="notebook-amount"
                type="number"
                min="0"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="notebook-unit">단위</Label>
              <Input id="notebook-unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
            </div>
          </div>
          <PublicEvidenceSelector value={evidenceIds} onChange={setEvidenceIds} />
          <PublicEvidenceLinks ids={evidenceIds} />
          <Button
            onClick={() => void submit()}
            disabled={busy || !date || !text.trim() || Boolean(recordId && !editingId)}
          >
            {editingId ? "수정 내용 확인" : "저장할 내용 확인"}
          </Button>
        </div>
      ) : (
        <>
          {view === "list" ? (
            <div className="grid grid-cols-1 gap-3 rounded-xl bg-muted/60 p-4 md:grid-cols-[minmax(0,12rem)_minmax(0,12rem)_minmax(0,1fr)]">
              <div className="grid gap-1">
                <Label htmlFor="filter-start">시작 날짜</Label>
                <DatePickerField
                  id="filter-start"
                  aria-label="시작 날짜"
                  value={start}
                  onChange={setStart}
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="filter-end">종료 날짜</Label>
                <DatePickerField
                  id="filter-end"
                  aria-label="종료 날짜"
                  value={end}
                  onChange={setEnd}
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="filter-alias">동행 검색</Label>
                <Input
                  id="filter-alias"
                  value={aliasFilter}
                  onChange={(e) => setAliasFilter(e.target.value)}
                />
              </div>
            </div>
          ) : null}
          {view === "list" && (start || end || aliasFilter) && entries.length > 0 ? (
            <Button
              className="w-fit"
              size="sm"
              variant="ghost"
              onClick={() => {
                setStart("");
                setEnd("");
                setAliasFilter("");
              }}
            >
              검색 조건 지우기
            </Button>
          ) : null}
          {view === "calendar" ? (
            <DateSelectionCalendar
              value={calendarDate}
              onSelect={(selected) => {
                setCalendarDate(selected);
                setDate(selected);
                setText("");
                setAliases("");
                setAmount("");
                setLocation(null);
                setEvidenceIds([]);
                setPrivateRegionId(null);
                navigate("write", undefined, selected);
              }}
              events={entries.map((entry) => ({
                id: entry.record_id,
                title: entry.activity_text,
                start: entry.experience_date,
                allDay: true,
              }))}
              onEventSelect={(id) => {
                const entry = entries.find((item) => item.record_id === id);
                if (entry) {
                  populate(entry);
                  navigate("write", id);
                }
              }}
            />
          ) : null}
          {busy ? (
            <p role="status" className="text-base text-muted-foreground">
              기록 불러오는 중…
            </p>
          ) : null}
          {view === "list" && !busy && entries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border px-5 py-14 text-center">
              <PencilSimpleIcon className="mx-auto mb-3 size-8 text-muted-foreground" />
              <p className="text-muted-foreground">
                {start || end || aliasFilter
                  ? "검색 조건에 맞는 기록이 없습니다."
                  : "아직 기록이 없습니다."}
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-3">
                {start || end || aliasFilter ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setStart("");
                      setEnd("");
                      setAliasFilter("");
                    }}
                  >
                    검색 조건 지우기
                  </Button>
                ) : null}
                <Button variant="outline" onClick={startNew}>
                  첫 기록 쓰기
                </Button>
              </div>
            </div>
          ) : null}
          {view === "list" ? (
            <ul className="divide-y divide-border">
              {entries.map((entry) => (
                <li key={entry.record_id} className="py-5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <time className="text-base font-semibold text-primary">
                      {formatDisplayDate(entry.experience_date)}
                    </time>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          populate(entry);
                          navigate("write", entry.record_id);
                        }}
                      >
                        수정
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void requestDelete(entry.record_id)}
                      >
                        삭제
                      </Button>
                    </div>
                  </div>
                  <p className="whitespace-pre-wrap text-base">{entry.activity_text}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        onNavigate
                          ? onNavigate(`/share?record=${encodeURIComponent(entry.record_id)}`)
                          : window.location.assign(
                              `/share?record=${encodeURIComponent(entry.record_id)}`
                            )
                      }
                    >
                      나눔 연결
                    </Button>
                    <PublicEvidenceLinks ids={entry.public_evidence_ids ?? []} />
                  </div>
                  {entry.location_address || entry.latitude != null ? (
                    <button
                      type="button"
                      className="mt-2 flex items-center gap-1 text-base text-primary"
                      onClick={() => {
                        setLocation({
                          address: entry.location_address ?? "",
                          latitude: entry.latitude ?? null,
                          longitude: entry.longitude ?? null,
                        });
                        setLocationOpen(true);
                      }}
                    >
                      <MapPinIcon />
                      {entry.location_address || "기록한 위치 보기"}
                    </button>
                  ) : null}
                  <p className="mt-2 text-base text-muted-foreground">
                    {[
                      entry.companion_aliases.join(", "),
                      entry.amount_value != null
                        ? `${entry.amount_value}${entry.amount_unit ?? ""}`
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
      {locationOpen ? (
        <LocationPickerDialog
          value={location}
          onClose={() => setLocationOpen(false)}
          onSelect={(next) => {
            setLocation(next);
            setLocationOpen(false);
          }}
        />
      ) : null}
    </section>
  );
}
