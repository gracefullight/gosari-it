import { useId, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { OUTING_LOCATIONS } from "@/components/outing-plan-form";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { formatDisplayDate } from "@/lib/date-format";
import type { PrepareResponse } from "@/lib/gosari.types";

interface Candidate {
  key: number;
  location: string;
  date: string;
  time: string;
}
const SELECT_CLASS =
  "min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-ring";
const TIMES = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`);

export function InlineOutingConditionForm({
  prepare,
  onConfirm,
}: {
  prepare: PrepareResponse;
  onConfirm: (spec: Record<string, unknown>, label: string) => void;
}) {
  const id = useId();
  const maxDay = new Date(`${formatDisplayDate(new Date())}T12:00:00Z`);
  maxDay.setUTCDate(maxDay.getUTCDate() + 15);
  const maxDate = maxDay.toISOString().slice(0, 10);
  const seed = { ...prepare.form?.initial_values, ...prepare.spec };
  const rawCandidates =
    Array.isArray(seed.candidates) && seed.candidates.length ? seed.candidates : [seed];
  const [candidates, setCandidates] = useState<Candidate[]>(() =>
    rawCandidates.map((raw, index) => {
      const row = raw as Record<string, unknown>;
      const place = String(row.location_id ?? row.station_name ?? "");
      return {
        key: index + 1,
        location:
          OUTING_LOCATIONS.find(
            ([location, label]) =>
              location === place ||
              label === place ||
              (location === "seogwipo" && place === "서귀포")
          )?.[0] ?? "",
        date: String(row.date ?? row.target_date ?? seed.date ?? ""),
        time: String(row.time_slot ?? row.target_time_window ?? ""),
      };
    })
  );
  const [nextKey, setNextKey] = useState(candidates.length + 1);
  function update(key: number, patch: Partial<Candidate>) {
    setCandidates((current) =>
      current.map((candidate) => (candidate.key === key ? { ...candidate, ...patch } : candidate))
    );
  }
  const valid =
    candidates.every((candidate) => candidate.location && candidate.date && candidate.time) &&
    new Set(
      candidates.map((candidate) => `${candidate.location}/${candidate.date}/${candidate.time}`)
    ).size === candidates.length;
  return (
    <form
      aria-label="채팅 나들이 조건"
      className="grid min-w-0 gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onConfirm(
          {
            operation: "outing_compare",
            source_ids: ["kma_vilage", "open_meteo"],
            candidates: candidates.map(({ location, date, time }) => ({
              location_id: location,
              date,
              time_slot: time,
            })),
            preferred_elements: seed.preferred_elements ?? [
              "low_rain",
              "mild_temperature",
              "low_wind",
            ],
          },
          `${candidates
            .map(
              (candidate) =>
                `${OUTING_LOCATIONS.find(([location]) => location === candidate.location)?.[1]} ${candidate.date} ${candidate.time}`
            )
            .join(" · ")} 날씨 조회`
        );
      }}
    >
      {candidates.map((candidate, index) => (
        <fieldset
          key={candidate.key}
          className="grid min-w-0 gap-3 rounded-xl border border-border p-3"
        >
          <legend className="px-1 text-base font-medium">지역 {index + 1}</legend>
          <div className="grid gap-1.5">
            <Label className="text-base" required htmlFor={`${id}-${candidate.key}-location`}>
              지역
            </Label>
            <select
              required
              id={`${id}-${candidate.key}-location`}
              className={SELECT_CLASS}
              value={candidate.location}
              onChange={(event) => update(candidate.key, { location: event.target.value })}
            >
              <option value="">지역 선택</option>
              {OUTING_LOCATIONS.map(([location, label]) => (
                <option key={location} value={location}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 min-[480px]:grid-cols-2">
            <div className="grid min-w-0 gap-1.5">
              <Label className="text-base" required htmlFor={`${id}-${candidate.key}-date`}>
                날짜
              </Label>
              <DatePickerField
                required
                id={`${id}-${candidate.key}-date`}
                aria-label={`지역 ${index + 1} 날짜`}
                value={candidate.date}
                min="1940-01-01"
                max={maxDate}
                onChange={(date) => update(candidate.key, { date })}
              />
            </div>
            <div className="grid min-w-0 gap-1.5">
              <Label className="text-base" required htmlFor={`${id}-${candidate.key}-time`}>
                시각
              </Label>
              <select
                required
                id={`${id}-${candidate.key}-time`}
                className={SELECT_CLASS}
                value={candidate.time}
                onChange={(event) => update(candidate.key, { time: event.target.value })}
              >
                <option value="">시각 선택</option>
                {TIMES.map((time) => (
                  <option key={time} value={time}>
                    {time}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {candidates.length > 1 ? (
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 text-base"
              onClick={() =>
                setCandidates((current) => current.filter((row) => row.key !== candidate.key))
              }
            >
              지역 {index + 1} 삭제
            </Button>
          ) : null}
        </fieldset>
      ))}
      <Button
        type="button"
        variant="outline"
        className="min-h-11 text-base"
        disabled={candidates.length >= 12}
        onClick={() => {
          setCandidates((current) => [
            ...current,
            { key: nextKey, location: "", date: current[0].date, time: "" },
          ]);
          setNextKey((key) => key + 1);
        }}
      >
        지역 추가
      </Button>
      <Button type="submit" className="min-h-11 text-base" disabled={!valid}>
        이 조건으로 날씨 조회
      </Button>
    </form>
  );
}
