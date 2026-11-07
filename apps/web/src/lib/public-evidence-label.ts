import { formatDisplayDate } from "@/lib/date-format";
import type { ResultEnvelope } from "@/lib/gosari.types";

const PLACE_NAMES: Record<string, string> = {
  jeju: "제주시",
  aewol: "애월",
  hallim: "한림",
  hangyeong: "한경",
  daejeong: "대정",
  andeok: "안덕",
  seogwipo: "서귀포시",
  namwon: "남원",
  pyoseon: "표선",
  seongsan: "성산",
  gujwa: "구좌",
  jocheon: "조천",
};
const MARKET_NAMES: Record<string, string> = { "110001": "서울가락", "210001": "부산엄궁" };
const DATE_PREFIX = /^\d{4}-\d{2}-\d{2}/;
function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(object) : [];
}
function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
function distinct(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

/** A human label from public place/date/result fields; never prints identifiers or raw specs. */
export function publicEvidenceLabel(value: ResultEnvelope | Record<string, unknown>): string {
  const raw = value as unknown as Record<string, unknown>;
  const scope = object(raw.requested_scope ?? raw.public_query_spec);
  const result = object(raw.result ?? raw.result_values);
  const period = object(raw.observed_period);
  const operation = text(scope.operation);
  const candidates = rows(result.candidates ?? result.outing_candidates ?? scope.candidates);
  const stations = rows(scope.station_selections);
  const places = distinct([
    ...candidates.map(
      (row) => text(row.station_name ?? row.label) || PLACE_NAMES[text(row.location_id)] || ""
    ),
    ...stations.map((row) => text(row.station_name)),
    text(scope.station_name),
    text(result.location_name),
  ]);
  const place =
    places.slice(0, 3).join("·") + (places.length > 3 ? ` 외 ${places.length - 3}곳` : "");
  const cards = rows(result.sample_cards ?? result.price_cards ?? result.prices);
  const price =
    ["market_query", "retail_lookup", "survey_link"].includes(operation) ||
    cards.length > 0 ||
    result.channel;
  let title: string;
  if (price) {
    const channel =
      operation === "market_query" || result.channel === "wholesale"
        ? "도매 가격"
        : operation === "survey_link" || result.channel === "survey"
          ? "조사 가격"
          : "판매 가격";
    const markets = Array.isArray(scope.market_ids)
      ? scope.market_ids
          .map((id) => MARKET_NAMES[String(id)] ?? "")
          .filter(Boolean)
          .join("·")
      : "";
    const product =
      text(scope.fresh_or_dried) || text(cards[0]?.product ?? cards[0]?.title ?? cards[0]?.form);
    const option = text(scope.package_weight_unit);
    title = [markets, product, option, channel].filter(Boolean).join(" ");
  } else {
    const kind =
      operation === "station_search"
        ? "관측 지점"
        : operation === "current_observation" || result.station_count != null || result.stations
          ? "현재 날씨"
          : operation === "history_compare" ||
              operation === "region_compare" ||
              result.daily_rainfall ||
              result.average_temperature
            ? "과거 날씨 비교"
            : operation === "outing_compare" || candidates.length
              ? "나들이 날씨"
              : operation === "forecast_compare" || result.locations
                ? "날씨 예보"
                : "참고 자료";
    title = [place, kind].filter(Boolean).join(" ");
  }
  const dates = distinct(
    [
      text(scope.settlement_date),
      text(scope.settlement_date_end),
      text(scope.date),
      text(result.date),
      ...candidates.map((row) => text(row.target_date ?? row.date)),
    ]
      .filter((date) => DATE_PREFIX.test(date))
      .map((date) => formatDisplayDate(date.slice(0, 10)))
  );
  if (!dates.length) {
    const date = text(period.start ?? period.date ?? raw.verified_on);
    if (DATE_PREFIX.test(date)) dates.push(formatDisplayDate(date.slice(0, 10)));
  }
  const times = distinct(candidates.map((row) => text(row.target_time_window ?? row.time_slot)));
  const when = [dates.join("~"), times.join("·")].filter(Boolean).join(" ");
  return [title, when].filter(Boolean).join(" · ");
}
