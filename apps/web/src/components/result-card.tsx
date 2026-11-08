import { useState } from "react";
import { ComparisonTable, type RainResult, type TempResult } from "@/components/comparison-table";
import { LandOwnershipResults } from "@/components/land-ownership-results";
import { OutingCandidateCarousel } from "@/components/outing-candidate-carousel";
import { type PriceCardData, PriceCardList } from "@/components/price-card-list";
import { StationMap } from "@/components/station-map";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDisplayDate, formatDisplayDateTime } from "@/lib/date-format";
import type { ResultEnvelope } from "@/lib/gosari.types";

const DATA_STATUS_LABELS: Record<string, string> = {
  partial: "부분 자료",
  no_data: "자료 없음",
  conflict: "충돌 확인 필요",
  needs_confirmation: "확인 필요",
};

interface CurrentStation {
  station_name: string;
  station_code: string;
  temperature_c: string | null;
  day_rain_mm: string | null;
  rain_1h_mm?: string | number | null;
  observation_time: string;
}

interface OutingCandidate {
  candidate_id: string;
  label?: string;
  station_name: string;
  date?: string;
  time_slot?: string;
  target_date?: string;
  target_time_window?: string;
  current_observation?: {
    observation_time_kst: string;
    temperature_c: string | null;
    day_rain_mm: string | null;
    location?: string;
    altitude_m?: string | null;
  } | null;
  forecast?: {
    published_at: string | null;
    target_at: string;
    status: string;
    note: string;
  };
  forecast_status?: {
    published_at: string | null;
    target_at: string;
    status: string;
    note: string;
  };
  rank?: number | null;
  weather?: {
    temperature_c: number | null;
    precipitation_probability: number | null;
    wind_speed_kmh: number | null;
    condition: string;
    kind: string;
    source: string;
    source_url?: string;
    target_at: string;
    published_at?: string | null;
    precipitation_text?: string | null;
    recent_context?: {
      days: number;
      total_rain_mm: number | null;
      average_temperature_c: number | null;
    }[];
  } | null;
  reasons?: string[];
  comparison_reasons?: string[];
}

export function OutingComparisonView({
  candidates,
  failed,
  checklist,
  rankedIds,
}: {
  candidates: OutingCandidate[];
  rankedIds?: string[];
  failed?: {
    label?: string;
    candidate_id?: string;
    station_name?: string;
    message?: string;
    reason?: string;
  }[];
  checklist?: { item?: string; category?: string }[] | string[];
}) {
  const [items, setItems] = useState<{ id: string; text: string; checked: boolean }[]>(() =>
    (checklist ?? []).map((entry, index) => ({
      id: `initial-${index}`,
      text:
        typeof entry === "string"
          ? entry
          : `${entry.item ?? ""}${entry.category ? ` (${entry.category})` : ""}`,
      checked: false,
    }))
  );
  const [newItem, setNewItem] = useState("");
  const [editingItem, setEditingItem] = useState<string | null>(null);

  function toggleItem(idx: number) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, checked: !it.checked } : it)));
  }

  function addItem() {
    const trimmed = newItem.trim();
    if (!trimmed) return;
    setItems((prev) => [...prev, { id: crypto.randomUUID(), text: trimmed, checked: false }]);
    setNewItem("");
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  return (
    <div className="flex flex-col gap-4">
      <OutingCandidateCarousel
        items={[...candidates]
          .sort((a, b) => {
            const left = rankedIds?.indexOf(a.candidate_id) ?? -1;
            const right = rankedIds?.indexOf(b.candidate_id) ?? -1;
            return (left >= 0 ? left : (a.rank ?? 99)) - (right >= 0 ? right : (b.rank ?? 99));
          })
          .map((cand) => {
            const fc = cand.forecast ?? cand.forecast_status;
            const reasons = cand.reasons ?? cand.comparison_reasons ?? [];
            return {
              id: cand.candidate_id,
              rank: cand.rank,
              content: (
                <div className="flex flex-col gap-2.5 rounded-xl bg-muted/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-base font-bold text-accent-foreground">
                      {cand.rank ? (
                        <span className="mr-2 text-primary">{cand.rank}순위</span>
                      ) : null}
                      {cand.label ?? cand.station_name}
                    </span>
                    <span className="rounded-md bg-accent px-2.5 py-1 text-base font-semibold tabular-nums text-accent-foreground">
                      {formatDisplayDate(cand.date ?? cand.target_date)} ·{" "}
                      {cand.time_slot ?? cand.target_time_window}
                    </span>
                  </div>
                  {cand.weather ? (
                    <div className="grid gap-3 py-2">
                      <p className="text-base text-muted-foreground">
                        {cand.weather.kind === "historical" ? "과거 날씨" : "예보"} ·{" "}
                        {(
                          {
                            clear: "맑음",
                            cloudy: "흐림",
                            partly_cloudy: "구름 조금",
                            rain: "비",
                            snow: "눈",
                            unknown: "자료 없음",
                          } as Record<string, string>
                        )[cand.weather.condition] ?? "자료 없음"}
                      </p>
                      <dl className="grid grid-cols-3 gap-2 text-base">
                        <div>
                          <dt className="text-muted-foreground">기온</dt>
                          <dd className="mt-1 text-lg font-semibold tabular-nums">
                            {cand.weather.temperature_c == null
                              ? "—"
                              : `${cand.weather.temperature_c}℃`}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">강수확률</dt>
                          <dd className="mt-1 text-lg font-semibold tabular-nums">
                            {cand.weather.precipitation_probability == null
                              ? "—"
                              : `${cand.weather.precipitation_probability}%`}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">바람</dt>
                          <dd className="mt-1 text-lg font-semibold tabular-nums">
                            {cand.weather.wind_speed_kmh == null
                              ? "—"
                              : `${cand.weather.wind_speed_kmh}km/h`}
                          </dd>
                        </div>
                      </dl>
                      <p className="text-base text-muted-foreground">
                        출처 {cand.weather.source}
                        {cand.weather.kind === "forecast" ? (
                          <>
                            {" · 발표 "}
                            {cand.weather.published_at
                              ? formatDisplayDateTime(cand.weather.published_at)
                              : "미제공"}
                          </>
                        ) : null}
                        {" · 대상 "}
                        {formatDisplayDateTime(cand.weather.target_at)}
                      </p>
                    </div>
                  ) : null}
                  {cand.current_observation ? (
                    <div className="rounded-lg bg-card p-3 text-base text-foreground">
                      <div className="font-semibold">
                        관측시각:{" "}
                        {formatDisplayDateTime(cand.current_observation.observation_time_kst)}
                      </div>
                      <div className="mt-0.5 tabular-nums">
                        기온 {cand.current_observation.temperature_c ?? ""}℃ · 일강수{" "}
                        {cand.current_observation.day_rain_mm ?? ""}mm
                      </div>
                      {cand.current_observation.location ? (
                        <div className="text-muted-foreground">
                          {cand.current_observation.location}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {fc && !cand.weather ? (
                    <div className="rounded-lg bg-amber-50/90 p-3 text-base text-amber-900">
                      <div className="font-semibold">
                        예보 대상시각: {formatDisplayDateTime(fc.target_at)} (발표시각:{" "}
                        {fc.published_at ? formatDisplayDateTime(fc.published_at) : "미확인"})
                      </div>
                      <div>{fc.note}</div>
                    </div>
                  ) : null}
                  {reasons.length > 0 || cand.weather?.recent_context?.length ? (
                    <details className="text-base">
                      <summary className="min-h-11 cursor-pointer py-3 text-primary">
                        비교 근거
                      </summary>
                      <ul className="grid gap-2 text-base text-muted-foreground">
                        {reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                        {!reasons.some((reason) => reason.includes("최근"))
                          ? cand.weather?.recent_context?.map((period) => (
                              <li key={period.days}>
                                최근 {period.days}일 · 비{" "}
                                {period.total_rain_mm == null ? "—" : `${period.total_rain_mm}mm`} ·
                                평균{" "}
                                {period.average_temperature_c == null
                                  ? "—"
                                  : `${period.average_temperature_c}℃`}
                              </li>
                            ))
                          : null}
                      </ul>
                    </details>
                  ) : null}
                </div>
              ),
            };
          })}
      />
      {failed && failed.length > 0 ? (
        <Alert>
          <AlertDescription>
            일부 후보 조회 실패:{" "}
            {failed
              .map(
                (f) =>
                  `${f.label ?? f.station_name ?? f.candidate_id ?? "후보"}(${f.message ?? f.reason ?? "조회 불가"})`
              )
              .join(", ")}
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="border-t border-border pt-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-base font-bold text-foreground">나들이 준비 목록</span>
        </div>
        <ul className="mb-3 flex flex-col divide-y divide-border/60">
          {items.map((item, idx) => (
            <li
              key={item.id}
              className="flex min-h-11 items-center justify-between gap-2 py-1.5 text-base"
            >
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <input
                  id={`outing-check-${item.id}`}
                  aria-label={item.text || "준비물"}
                  type="checkbox"
                  checked={item.checked}
                  onChange={() => toggleItem(idx)}
                  className="size-5 shrink-0 accent-[var(--primary)]"
                />
                {editingItem === item.id ? (
                  <Input
                    autoFocus
                    aria-label="준비물 이름"
                    className="min-w-0 flex-1"
                    value={item.text}
                    onChange={(event) =>
                      setItems((previous) =>
                        previous.map((old) =>
                          old.id === item.id ? { ...old, text: event.target.value } : old
                        )
                      )
                    }
                  />
                ) : (
                  <label
                    htmlFor={`outing-check-${item.id}`}
                    className={`flex min-h-11 flex-1 cursor-pointer items-center ${item.checked ? "text-muted-foreground line-through" : "text-foreground"}`}
                  >
                    {item.text}
                  </label>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 text-base"
                onClick={() => setEditingItem(editingItem === item.id ? null : item.id)}
              >
                {editingItem === item.id ? "완료" : "수정"}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="min-h-11 text-base"
                onClick={() => removeItem(idx)}
                aria-label={`${item.text} 삭제`}
              >
                삭제
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Input
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            placeholder="준비물 항목 추가 (예: 여벌 양말)"
            className="min-w-0 flex-1"
            aria-label="추가할 준비물"
          />
          <Button onClick={addItem}>추가</Button>
        </div>
      </div>
    </div>
  );
}

export function ResultCard({ envelope }: { envelope: ResultEnvelope }) {
  const result = envelope.result;
  if ("land_ownership" in result) return <LandOwnershipResults envelope={envelope} />;
  const rain = result.daily_rainfall as RainResult | undefined;
  const temp = result.average_temperature as TempResult | undefined;
  const outingCandidates = (result.candidates ?? result.outing_candidates) as
    | OutingCandidate[]
    | undefined;
  const failedCandidates = result.failed_candidates as
    | {
        label?: string;
        candidate_id?: string;
        station_name?: string;
        message?: string;
        reason?: string;
      }[]
    | undefined;
  const checklist = result.preparation_checklist as
    | { item?: string; category?: string }[]
    | string[]
    | undefined;
  const currentStations = result.stations as CurrentStation[] | undefined;
  const sampleCards = result.sample_cards as PriceCardData[] | undefined;
  const linkCards = result.links as PriceCardData[] | undefined;
  const priceCards = sampleCards ?? linkCards;
  const extraLinks = sampleCards ? linkCards : undefined;
  const summaryRows = result.summary_rows as Record<string, string>[] | undefined;
  const stationList = result.stations as
    | { station_name: string; station_code?: string; location?: string }[]
    | undefined;
  const isStationSearch = Boolean(stationList && !currentStations?.[0]?.observation_time);

  return (
    <div className="max-w-full rounded-2xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {envelope.data_status && DATA_STATUS_LABELS[envelope.data_status] ? (
          <Badge>{DATA_STATUS_LABELS[envelope.data_status]}</Badge>
        ) : null}
        {envelope.source_mode === "replay" ? <Badge variant="secondary">표본 자료</Badge> : null}
        {envelope.verified_on ? (
          <span className="text-base text-muted-foreground">
            확인일 {formatDisplayDate(envelope.verified_on)}
          </span>
        ) : null}
      </div>
      {typeof result.explanation === "string" && !outingCandidates ? (
        <p className="mb-3 text-base text-foreground">{result.explanation}</p>
      ) : null}
      {rain ? <ComparisonTable rain={rain} temp={temp} /> : null}
      {outingCandidates ? (
        <OutingComparisonView
          candidates={outingCandidates}
          failed={failedCandidates}
          checklist={checklist}
          rankedIds={result.ranked_candidate_ids as string[] | undefined}
        />
      ) : null}
      {currentStations && currentStations.length > 0 && currentStations[0].observation_time ? (
        <div className="overflow-x-auto">
          <p className="mb-3 text-base text-muted-foreground">
            {typeof result.source === "string" ? `${result.source} · ` : ""}
            {formatDisplayDateTime(currentStations[0].observation_time)}
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>지역</TableHead>
                <TableHead className="text-right">기온 (℃)</TableHead>
                <TableHead className="text-right">
                  {typeof result.rain_period_label === "string"
                    ? result.rain_period_label
                    : "일강수 (mm)"}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {currentStations.map((s) => (
                <TableRow key={s.station_code}>
                  <TableCell className="font-medium">{s.station_name}</TableCell>
                  <TableCell className="text-right tabular-nums">{s.temperature_c ?? ""}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {s.rain_1h_mm ?? s.day_rain_mm ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {isStationSearch && stationList ? <StationMap stations={stationList} /> : null}
      {priceCards ? <PriceCardList cards={priceCards} links={extraLinks} /> : null}
      {summaryRows ? (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>정산일</TableHead>
                <TableHead>시장</TableHead>
                <TableHead className="text-right">고사리 행수 (건)</TableHead>
                <TableHead className="text-right">제주 산지명 (건)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summaryRows.slice(0, 12).map((row) => (
                <TableRow key={`${row.settlement_date}-${row.market_code}`}>
                  <TableCell className="tabular-nums">
                    {formatDisplayDate(row.settlement_date)}
                  </TableCell>
                  <TableCell className="font-medium">{row.market_name}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.total_bracken_rows}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {row.origin_name_contains_jeju}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {typeof result.reason === "string" && !rain && !priceCards && !outingCandidates ? (
        <Alert>
          <AlertDescription>조회할 자료가 없습니다.</AlertDescription>
        </Alert>
      ) : null}
      {envelope.warnings.length > 0 ? (
        <ul className="mt-3 list-inside list-disc text-base text-muted-foreground">
          {envelope.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      {envelope.errors.length > 0 ? (
        <div className="mt-2 flex flex-col gap-2">
          {envelope.errors.map((error) => (
            <Alert key={error.code} variant="destructive">
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ))}
        </div>
      ) : null}
    </div>
  );
}
