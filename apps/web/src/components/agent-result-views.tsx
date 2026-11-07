import { useState } from "react";
import {
  JejuWeatherMap,
  WEATHER_LABELS,
  type WeatherLocation,
} from "@/components/jeju-weather-map";
import { type PriceCardData, PriceCardList } from "@/components/price-card-list";
import { OutingComparisonView } from "@/components/result-card";
import { StationMap } from "@/components/station-map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

const YEAR_PATTERN = /^\d{4}$/;

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (row): row is Record<string, unknown> =>
          Boolean(row) && typeof row === "object" && !Array.isArray(row)
      )
    : [];
}
function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function numeric(value: unknown): number | null {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
function amount(value: unknown, unit: string): string {
  const number = numeric(value);
  return number == null ? "—" : `${number.toLocaleString("ko-KR")}${unit}`;
}

function forecastValue(row: Record<string, unknown>): [string, string] {
  const category = String(row.category ?? row.element ?? "");
  const definitions: Record<string, [string, string]> = {
    TMP: ["기온", "℃"],
    T1H: ["기온", "℃"],
    TMN: ["최저기온", "℃"],
    TMX: ["최고기온", "℃"],
    POP: ["강수확률", "%"],
    PCP: ["시간당 강수량", "mm"],
    RN1: ["시간당 강수량", "mm"],
    WSD: ["풍속", "m/s"],
    REH: ["습도", "%"],
    SNO: ["적설량", "cm"],
    VEC: ["풍향", "°"],
    WAV: ["파고", "m"],
  };
  const value = row.value;
  if (value == null || value === "") return [definitions[category]?.[0] ?? "예보", "—"];
  if (category === "SKY")
    return [
      "하늘 상태",
      ({ "1": "맑음", "3": "구름 많음", "4": "흐림" } as Record<string, string>)[String(value)] ??
        "미확인",
    ];
  if (category === "PTY")
    return [
      "강수 형태",
      (
        {
          "0": "강수 없음",
          "1": "비",
          "2": "비 또는 눈",
          "3": "눈",
          "4": "소나기",
          "5": "빗방울",
          "6": "빗방울 또는 눈날림",
          "7": "눈날림",
        } as Record<string, string>
      )[String(value)] ?? "미확인",
    ];
  const [label, unit] = definitions[category] ?? [
    "예보",
    typeof row.unit === "string" ? row.unit : "",
  ];
  return [label, numeric(value) == null ? String(value) : amount(value, unit)];
}

export function AgentResultStatus({ envelope }: { envelope: ResultEnvelope }) {
  const partial = envelope.data_status === "partial";
  return (
    <>
      {partial || envelope.source_mode === "replay" ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {partial ? <Badge variant="secondary">일부 자료</Badge> : null}
          {envelope.source_mode === "replay" ? <Badge variant="secondary">표본 자료</Badge> : null}
        </div>
      ) : null}
      {envelope.data_status === "no_data" || envelope.data_status === "unavailable" ? (
        <p className="text-base text-muted-foreground">조회한 조건의 자료가 없습니다.</p>
      ) : null}
      {envelope.errors.length ? (
        <p role="alert" className="mb-3 text-base text-destructive">
          {envelope.errors.map((error) => error.message).join(" ")}
        </p>
      ) : null}
    </>
  );
}

export function AgentPriceResults({
  envelope,
  table = false,
  onList,
}: {
  envelope: ResultEnvelope;
  table?: boolean;
  onList?: () => void;
}) {
  const result = envelope.result;
  const cards = records(
    result.price_cards ?? result.sample_cards ?? result.links
  ) as unknown as PriceCardData[];
  const channel = String(
    result.channel ?? cards[0]?.channel ?? envelope.requested_scope.price_channel ?? ""
  );
  const title =
    ({ wholesale: "도매 가격", survey: "조사가", retail: "판매가" } as Record<string, string>)[
      channel
    ] ?? "가격";
  return (
    <section aria-label={title} className="min-w-0">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">{title}</h3>
        {cards.length ? (
          <span className="text-base text-muted-foreground">{cards.length}건</span>
        ) : null}
      </div>
      <AgentResultStatus envelope={envelope} />
      {table ? (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>상품·규격</TableHead>
                  <TableHead className="text-right">가격</TableHead>
                  <TableHead>기준일</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cards.map((card, index) => (
                  <TableRow key={card.row_id ?? `${card.product}-${index}`}>
                    <TableCell>
                      <p className="font-medium">{card.product ?? card.title ?? card.form}</p>
                      <p className="mt-1 text-base text-muted-foreground">
                        {[
                          card.product_option,
                          card.net_weight_value
                            ? `${card.net_weight_value}g`
                            : card.original_quantity && card.original_unit
                              ? `${card.original_quantity}${card.original_unit}`
                              : "",
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {amount(card.price_value, "원")}
                    </TableCell>
                    <TableCell className="whitespace-nowrap tabular-nums">
                      {formatDisplayDate(card.price_as_of)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <Button className="mt-3 min-h-11 text-base" variant="ghost" onClick={onList}>
            상품별로 보기
          </Button>
        </>
      ) : cards.length ? (
        <PriceCardList cards={cards} />
      ) : envelope.data_status === "complete" ? (
        <p className="text-base text-muted-foreground">표시할 가격이 없습니다.</p>
      ) : null}
    </section>
  );
}

export function AgentWeatherComparison({ envelope }: { envelope: ResultEnvelope }) {
  const result = envelope.result;
  const rain = record(result.daily_rainfall);
  const temperature = record(result.average_temperature);
  const rainRows = record(rain.per_year ?? rain.per_station);
  const temperatureRows = record(temperature.per_year ?? temperature.per_station);
  const comparisons = [...new Set([...Object.keys(rainRows), ...Object.keys(temperatureRows)])];
  const stations = records(result.stations);
  const forecast = records(result.forecast);
  const onlyForecast = !comparisons.length && !stations.length;
  return (
    <section className="min-w-0" aria-label="날씨 비교">
      <h3 className="mb-4 text-lg font-semibold">날씨 비교</h3>
      <AgentResultStatus envelope={envelope} />
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>지역·날짜</TableHead>
              <TableHead className="text-right">
                {onlyForecast ? "기상 요소" : comparisons.length ? "평균기온" : "기온"}
              </TableHead>
              <TableHead className="text-right">
                {onlyForecast ? "예보" : comparisons.length ? "비 온 날 / 관측일" : "비"}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {comparisons.length
              ? comparisons.map((name) => {
                  const row = record(rainRows[name]);
                  const temp = record(temperatureRows[name]);
                  const nameLabel = YEAR_PATTERN.test(name) ? `${name}년` : name;
                  return (
                    <TableRow key={name}>
                      <TableCell className="font-medium">{nameLabel}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {amount(temp.average, "℃")}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.positive_days == null && row.valid_days == null
                          ? "—"
                          : `${amount(row.positive_days, "일")} / ${amount(row.valid_days, "일")}`}
                      </TableCell>
                    </TableRow>
                  );
                })
              : stations.length
                ? stations.map((row, index) => (
                    <TableRow key={String(row.station_code ?? index)}>
                      <TableCell>
                        <p className="font-medium">{String(row.station_name ?? "")}</p>
                        <p className="text-base text-muted-foreground">
                          {formatDisplayDateTime(String(row.observation_time ?? ""))}
                        </p>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {amount(row.temperature_c, "℃")}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {amount(row.rain_1h_mm ?? row.day_rain_mm, "mm")}
                      </TableCell>
                    </TableRow>
                  ))
                : forecast.map((row, index) => {
                    const [label, value] = forecastValue(row);
                    return (
                      <TableRow key={String(row.target_at ?? index)}>
                        <TableCell>{formatDisplayDateTime(String(row.target_at ?? ""))}</TableCell>
                        <TableCell className="text-right">{label}</TableCell>
                        <TableCell className="text-right tabular-nums">{value}</TableCell>
                      </TableRow>
                    );
                  })}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

export function AgentOutingResults({ envelope }: { envelope: ResultEnvelope }) {
  const result = envelope.result;
  type OutingProps = Parameters<typeof OutingComparisonView>[0];
  return (
    <section className="min-w-0" aria-label="나들이 비교 결과">
      <h3 className="mb-4 text-lg font-semibold">나들이 비교</h3>
      <AgentResultStatus envelope={envelope} />
      <OutingComparisonView
        candidates={
          (result.candidates ?? result.outing_candidates ?? []) as OutingProps["candidates"]
        }
        rankedIds={result.ranked_candidate_ids as OutingProps["rankedIds"]}
        failed={result.failed_candidates as OutingProps["failed"]}
        checklist={result.preparation_checklist as OutingProps["checklist"]}
      />
    </section>
  );
}

const PUBLIC_POINTS: Record<string, [number, number]> = {
  jeju: [33.4996, 126.5312],
  aewol: [33.462, 126.329],
  hallim: [33.41, 126.267],
  hangyeong: [33.35, 126.184],
  daejeong: [33.226, 126.252],
  andeok: [33.257, 126.351],
  seogwipo: [33.2541, 126.5601],
  namwon: [33.279, 126.72],
  pyoseon: [33.326, 126.831],
  seongsan: [33.442, 126.91],
  gujwa: [33.522, 126.852],
  jocheon: [33.534, 126.634],
};
export function AgentWeatherMap({ envelope }: { envelope: ResultEnvelope }) {
  const [selected, setSelected] = useState<WeatherLocation | null>(null);
  const result = envelope.result;
  const candidates = records(envelope.requested_scope.candidates);
  const rows = records(
    result.locations ?? result.candidates ?? result.outing_candidates ?? result.stations
  );
  const locations: WeatherLocation[] = rows.flatMap((row, index) => {
    const weather = record(row.weather);
    const candidate = candidates.find((candidate) => candidate.candidate_id === row.candidate_id);
    const id = String(row.location_id ?? row.id ?? candidate?.location_id ?? "");
    const point = PUBLIC_POINTS[id];
    const latitude = numeric(row.latitude ?? candidate?.latitude ?? point?.[0]);
    const longitude = numeric(row.longitude ?? candidate?.longitude ?? point?.[1]);
    if (latitude == null || longitude == null) return [];
    const condition = String(weather.condition ?? row.condition ?? "unknown");
    return [
      {
        id: String(row.candidate_id ?? id ?? index),
        name: String(row.station_name ?? row.name ?? candidate?.station_name ?? "제주"),
        latitude,
        longitude,
        temperature_c: numeric(weather.temperature_c ?? row.temperature_c),
        precipitation_probability: numeric(
          weather.precipitation_probability ?? row.precipitation_probability
        ),
        condition: (condition in WEATHER_LABELS
          ? condition
          : "unknown") as WeatherLocation["condition"],
        forecast_at:
          String(weather.target_at ?? row.forecast_at ?? row.observation_time ?? "") || null,
      },
    ];
  });
  return (
    <section aria-label="제주 날씨 지도" className="min-w-0">
      <h3 className="mb-4 text-lg font-semibold">제주 날씨</h3>
      <AgentResultStatus envelope={envelope} />
      <JejuWeatherMap locations={locations} onSelect={setSelected} />
      {selected ? (
        <div className="mt-3 rounded-xl bg-muted p-4 text-base">
          <p className="font-semibold">{selected.name}</p>
          <p className="mt-1">
            {WEATHER_LABELS[selected.condition]} · {amount(selected.temperature_c, "℃")} · 강수확률{" "}
            {amount(selected.precipitation_probability, "%")}
          </p>
          <p className="mt-1 text-muted-foreground">
            {formatDisplayDateTime(selected.forecast_at)}
          </p>
        </div>
      ) : null}
      {!locations.length ? (
        <div className="mt-4">
          <AgentWeatherComparison envelope={envelope} />
        </div>
      ) : null}
    </section>
  );
}

export function AgentStationResults({ envelope }: { envelope: ResultEnvelope }) {
  const stations = records(envelope.result.stations).map((row) => ({
    station_name: String(row.station_name ?? ""),
    station_code: row.station_code == null ? undefined : String(row.station_code),
    location: typeof row.location === "string" ? row.location : undefined,
  }));
  return (
    <section aria-label="관측소 검색" className="min-w-0">
      <AgentResultStatus envelope={envelope} />
      <StationMap stations={stations} />
    </section>
  );
}
