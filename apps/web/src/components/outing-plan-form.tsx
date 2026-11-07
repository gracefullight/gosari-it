import { PlusIcon, XIcon } from "@phosphor-icons/react";
import { useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { ResultCard } from "@/components/result-card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cancelAnalysisJob } from "@/lib/analysis-jobs";
import { formatDisplayDate } from "@/lib/date-format";
import { ApiError, api } from "@/lib/gosari.api";
import type { ResultEnvelope } from "@/lib/gosari.types";
import { featureResultsAtom } from "@/stores/chat.atoms";

export const OUTING_LOCATIONS = [
  ["jeju", "제주시"],
  ["aewol", "애월"],
  ["hallim", "한림"],
  ["hangyeong", "한경"],
  ["daejeong", "대정"],
  ["andeok", "안덕"],
  ["seogwipo", "서귀포시"],
  ["namwon", "남원"],
  ["pyoseon", "표선"],
  ["seongsan", "성산"],
  ["gujwa", "구좌"],
  ["jocheon", "조천"],
] as const;
const CRITERIA = [
  ["low_rain", "비 적음"],
  ["mild_temperature", "기온 온화"],
  ["low_wind", "바람 약함"],
] as const;
type Criterion = (typeof CRITERIA)[number][0];
interface Candidate {
  key: number;
  location_id: string;
  date: string;
  time_slot: string;
}
interface ComparisonConditions {
  candidates: Omit<Candidate, "key">[];
  preferred_elements: Criterion[];
}
interface AppliedComparisonConditions extends ComparisonConditions {
  candidateKeys: number[];
}
const SELECT_CLASS =
  "min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base";

export function OutingPlanForm({ initialDate }: { initialDate: string }) {
  const setResults = useSetAtom(featureResultsAtom);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const maxDateValue = new Date(`${today}T12:00:00Z`);
  maxDateValue.setUTCDate(maxDateValue.getUTCDate() + 15);
  const maxDate = maxDateValue.toISOString().slice(0, 10);
  const [candidates, setCandidates] = useState<Candidate[]>([
    { key: 1, location_id: "jeju", date: initialDate, time_slot: "09:00" },
    { key: 2, location_id: "seogwipo", date: initialDate, time_slot: "12:00" },
  ]);
  const [nextKey, setNextKey] = useState(3);
  const [criteria, setCriteria] = useState<Criterion[]>([
    "low_rain",
    "mild_temperature",
    "low_wind",
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResultEnvelope | null>(null);
  const [appliedConditions, setAppliedConditions] = useState<AppliedComparisonConditions | null>(
    null
  );
  const currentConditions: ComparisonConditions = {
    candidates: candidates.map(({ location_id, date, time_slot }) => ({
      location_id,
      date,
      time_slot,
    })),
    preferred_elements: criteria,
  };
  const conditionsChanged =
    appliedConditions != null &&
    JSON.stringify(currentConditions) !==
      JSON.stringify({
        candidates: appliedConditions.candidates,
        preferred_elements: appliedConditions.preferred_elements,
      });
  function update(key: number, patch: Partial<Candidate>) {
    setCandidates((current) =>
      current.map((candidate) => (candidate.key === key ? { ...candidate, ...patch } : candidate))
    );
  }
  function prioritize(index: number, value: Criterion) {
    setCriteria((current) => {
      const next = [...current];
      const previousIndex = current.indexOf(value);
      next[previousIndex] = current[index];
      next[index] = value;
      return next;
    });
  }
  async function compare() {
    setBusy(true);
    setError(null);
    setResult(null);
    setJobId(null);
    setProgress("후보 날씨 불러오는 중…");
    const controller = new AbortController();
    request.current = controller;
    const submittedConditions = currentConditions;
    try {
      const job = await api.runAnalysis(
        {
          operation: "outing_compare",
          source_ids: ["open_meteo"],
          ...submittedConditions,
        },
        undefined,
        {
          signal: controller.signal,
          onProgress: (job) => {
            setJobId(job.job_id);
            setProgress(job.stage === "queued" ? "비교 기다리는 중…" : "후보 날씨 비교 중…");
          },
        }
      );
      if (controller.signal.aborted) return;
      if (!job.result) throw new Error(job.error || "후보를 비교하지 못했습니다.");
      setResult(job.result);
      setAppliedConditions({
        ...submittedConditions,
        candidateKeys: candidates.map((candidate) => candidate.key),
      });
      setResults((previous) => ({ ...previous, 나들이: job.result as ResultEnvelope }));
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "후보를 비교하지 못했습니다."
      );
    } finally {
      if (request.current === controller) {
        setBusy(false);
        request.current = null;
      }
    }
  }
  async function cancel() {
    if (!jobId) return;
    try {
      await cancelAnalysisJob(jobId);
      request.current?.abort();
      setProgress("비교를 취소했습니다.");
    } catch {
      setError("비교를 취소하지 못했습니다.");
    }
  }
  const unique =
    new Set(
      candidates.map(
        (candidate) => `${candidate.location_id}/${candidate.date}/${candidate.time_slot}`
      )
    ).size === candidates.length;
  return (
    <section
      className="mt-4 grid gap-5 border-t border-border pt-6"
      aria-labelledby="outing-plan-title"
    >
      <div>
        <h2
          id="outing-plan-title"
          tabIndex={-1}
          className="scroll-mt-6 text-2xl font-semibold focus-visible:outline-2 focus-visible:outline-ring"
        >
          나들이 후보 비교
        </h2>
        <p className="mt-2 text-base text-muted-foreground">어디로, 언제 갈지 골라 보세요.</p>
      </div>
      <div className="grid gap-4">
        {candidates.map((candidate, index) => (
          <fieldset
            key={candidate.key}
            disabled={busy}
            className="grid min-w-0 grid-cols-1 gap-3 rounded-xl border border-border bg-card p-4 min-[1024px]:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,.8fr)_2.75rem]"
          >
            <legend className="px-1 text-base font-semibold">후보 {index + 1}</legend>
            <div className="grid min-w-0 gap-2">
              <Label htmlFor={`outing-location-${candidate.key}`}>지역</Label>
              <select
                id={`outing-location-${candidate.key}`}
                className={SELECT_CLASS}
                value={candidate.location_id}
                onChange={(event) => update(candidate.key, { location_id: event.target.value })}
              >
                {OUTING_LOCATIONS.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid min-w-0 gap-2">
              <Label htmlFor={`outing-date-${candidate.key}`}>날짜</Label>
              <DatePickerField
                id={`outing-date-${candidate.key}`}
                aria-label={`후보 ${index + 1} 날짜`}
                required
                min="1940-01-01"
                max={maxDate}
                value={candidate.date}
                onChange={(date) => update(candidate.key, { date })}
              />
            </div>
            <div className="grid min-w-0 gap-2">
              <Label htmlFor={`outing-time-${candidate.key}`}>시각</Label>
              <select
                id={`outing-time-${candidate.key}`}
                className={SELECT_CLASS}
                value={candidate.time_slot}
                onChange={(event) => update(candidate.key, { time_slot: event.target.value })}
              >
                {Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`).map(
                  (time) => (
                    <option key={time} value={time}>
                      {time}
                    </option>
                  )
                )}
              </select>
            </div>
            <Button
              className="min-h-11 self-end"
              variant="ghost"
              size="icon"
              aria-label={`후보 ${index + 1} 삭제`}
              disabled={candidates.length <= 2 || busy}
              onClick={() =>
                setCandidates((current) => current.filter((item) => item.key !== candidate.key))
              }
            >
              <XIcon />
            </Button>
          </fieldset>
        ))}
      </div>
      <Button
        variant="outline"
        className="w-fit"
        disabled={candidates.length >= 4 || busy}
        onClick={() => {
          setCandidates((current) => [
            ...current,
            { key: nextKey, location_id: "jocheon", date: initialDate, time_slot: "15:00" },
          ]);
          setNextKey((key) => key + 1);
        }}
      >
        <PlusIcon />
        후보 추가
      </Button>
      <fieldset className="grid gap-3" disabled={busy}>
        <legend className="mb-3 text-base font-semibold">우선순위</legend>
        <div className="grid gap-3 min-[768px]:grid-cols-3">
          {criteria.map((criterion, index) => (
            <div
              key={index === 0 ? "first" : index === 1 ? "second" : "third"}
              className="grid gap-2"
            >
              <Label htmlFor={`outing-priority-${index}`}>{index + 1}순위</Label>
              <select
                id={`outing-priority-${index}`}
                className={SELECT_CLASS}
                value={criterion}
                onChange={(event) => prioritize(index, event.target.value as Criterion)}
              >
                {CRITERIA.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </fieldset>
      {!unique ? (
        <p role="status" className="text-base text-muted-foreground">
          같은 지역·날짜·시각이 겹칩니다.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-base text-destructive">
          {error}
        </p>
      ) : null}
      {progress ? (
        <p role="status" className="text-base text-muted-foreground">
          {busy ? progress : progress === "비교를 취소했습니다." ? progress : ""}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          className="min-h-11 w-fit"
          onClick={() => void compare()}
          disabled={busy || !unique || candidates.some((candidate) => !candidate.date)}
        >
          {busy ? "비교 중…" : "후보 비교"}
        </Button>
        {busy ? (
          <Button
            variant="outline"
            className="min-h-11"
            disabled={!jobId}
            onClick={() => void cancel()}
          >
            비교 취소
          </Button>
        ) : null}
      </div>
      {result && appliedConditions ? (
        <section className="grid gap-3" aria-label="나들이 비교 결과">
          <h3 className="text-xl font-semibold">후보별 결과</h3>
          {conditionsChanged ? (
            <p
              role="status"
              className="rounded-xl bg-accent px-4 py-3 text-base text-accent-foreground"
            >
              조건이 바뀌었습니다. 후보 비교를 누르면 새 조건으로 갱신합니다.
            </p>
          ) : null}
          <section
            className="grid gap-2 text-base text-muted-foreground"
            aria-label="결과에 적용한 조건"
          >
            <p className="font-medium text-foreground">이 결과에 적용한 조건</p>
            <ul className="grid gap-1">
              {appliedConditions.candidates.map((candidate, index) => (
                <li key={appliedConditions.candidateKeys[index]}>
                  후보 {index + 1} ·{" "}
                  {OUTING_LOCATIONS.find(([id]) => id === candidate.location_id)?.[1] ??
                    candidate.location_id}
                  {" · "}
                  {formatDisplayDate(candidate.date)} · {candidate.time_slot}
                </li>
              ))}
            </ul>
            <p>
              우선순위:{" "}
              {appliedConditions.preferred_elements
                .map((criterion) => CRITERIA.find(([id]) => id === criterion)?.[1])
                .join(" → ")}
            </p>
          </section>
          <ResultCard key={result.request_id} envelope={result} />
        </section>
      ) : null}
    </section>
  );
}
