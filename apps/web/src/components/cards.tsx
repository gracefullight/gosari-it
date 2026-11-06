import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Alert,
  Badge,
  Link,
  Table,
} from "@gracefullight/krds-tw";
import { useAtomValue } from "jotai";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ResultEnvelope } from "../lib/types";
import { capabilitiesAtom } from "../stores/app";

interface RainYear {
  positive_days: number;
  valid_days: number;
  ratio: string | null;
  full_period?: { positive_days: number; valid_days: number };
}

interface RainResult {
  common_month_days: string[];
  common_day_count: number;
  per_year: Record<string, RainYear>;
}

function ComparisonTable({ rain }: { rain: RainResult }) {
  const years = Object.keys(rain.per_year).sort();
  return (
    <div className="overflow-x-auto">
      <Table>
        <thead>
          <tr>
            <th scope="col">연도</th>
            <th scope="col">양수 강수일 (공통기간)</th>
            <th scope="col">유효일 (분모)</th>
            <th scope="col">전체기간 양수/유효</th>
          </tr>
        </thead>
        <tbody>
          {years.map((year) => {
            const row = rain.per_year[year];
            return (
              <tr key={year}>
                <th scope="row">{year}</th>
                <td>{row.positive_days}</td>
                <td>{row.valid_days}</td>
                <td>
                  {row.full_period
                    ? `${row.full_period.positive_days} / ${row.full_period.valid_days}`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      <p className="mt-2 text-sm text-gray-600">
        공통 월일 {rain.common_day_count}일
        {rain.common_month_days.length > 0 &&
          ` (${rain.common_month_days[0]} ~ ${rain.common_month_days[rain.common_month_days.length - 1]})`}
        {" · "}분모가 다른 전체기간 수치와 직접 비교하지 않습니다.
      </p>
    </div>
  );
}

interface PriceCardData {
  channel: string;
  product?: string;
  origin_label_raw?: string;
  form?: string;
  product_option?: string;
  net_weight_value?: number;
  price_value?: number;
  shipping_value?: number;
  coupon_price?: number;
  coupon_condition?: string;
  price_as_of?: string;
  source_url?: string;
  title?: string;
  description?: string;
}

function PriceCards({ cards }: { cards: PriceCardData[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {cards.map((card) => (
        <div
          key={`${card.source_url}-${card.product_option ?? card.title ?? card.channel}`}
          className="rounded-lg border border-gray-200 bg-white p-4"
        >
          <div className="mb-1 text-sm font-semibold text-green-800">
            {card.channel === "retail"
              ? "상품 표시가"
              : card.channel === "survey"
                ? "지역 조사가"
                : "도매"}
          </div>
          <div className="mb-2 text-base font-bold">{card.product ?? card.title}</div>
          {Boolean(card.origin_label_raw) && (
            <div className="text-sm text-gray-600">원산지 표시: {card.origin_label_raw}</div>
          )}
          {Boolean(card.product_option) && (
            <div className="text-sm text-gray-600">옵션: {card.product_option}</div>
          )}
          {card.price_value != null && (
            <div className="mt-1 text-lg font-bold">
              {card.price_value.toLocaleString()}원
              {card.net_weight_value ? ` / ${card.net_weight_value}g` : ""}
            </div>
          )}
          {card.shipping_value != null && (
            <div className="text-sm text-gray-600">
              배송비: {card.shipping_value.toLocaleString()}원
            </div>
          )}
          {card.coupon_price != null && (
            <div className="text-sm text-gray-600">
              조건부 쿠폰가: {card.coupon_price.toLocaleString()}원 ({card.coupon_condition})
            </div>
          )}
          {Boolean(card.description) && (
            <div className="mt-1 text-sm text-gray-600">{card.description}</div>
          )}
          {Boolean(card.price_as_of) && (
            <div className="mt-1 text-xs text-gray-500">확인시점: {card.price_as_of}</div>
          )}
          {Boolean(card.source_url) && (
            <Link
              href={card.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-sm"
            >
              공식 원문 보기
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}

function StationMap({
  stations,
}: {
  stations: { station_name: string; station_code?: string | null; location?: string }[];
}) {
  const caps = useAtomValue(capabilitiesAtom);
  const mapRef = useRef<HTMLDivElement>(null);
  const tilesEnabled = caps?.map.tiles ?? false;

  useEffect(() => {
    if (!tilesEnabled || !mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors (ODbL)",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [126.55, 33.38],
      zoom: 9,
    });
    return () => map.remove();
  }, [tilesEnabled]);

  if (!tilesEnabled) {
    return (
      <div>
        <Alert severity="info">
          지도 타일이 비활성화되어 관측소 목록으로 표시합니다. 외부 타일 요청은 설정에서 허용할 수
          있습니다.
        </Alert>
        <ul className="mt-2 max-h-64 list-inside list-disc overflow-y-auto text-sm text-gray-700">
          {stations.map((s) => (
            <li key={`${s.station_code}-${s.station_name}`}>
              {s.station_name} {s.location ? `— ${s.location}` : ""}
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return <div ref={mapRef} className="map-container" role="img" aria-label="관측소 지도" />;
}

function EvidenceSection({ ids }: { ids: string[] }) {
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  if (ids.length === 0) return null;
  return (
    <Accordion>
      <AccordionItem value="evidence">
        <AccordionTrigger>근거 보기 (출처·시점·범위)</AccordionTrigger>
        <AccordionContent>
          <div className="text-sm">
            {evidence ? (
              <pre className="overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(evidence, null, 2)}
              </pre>
            ) : (
              <button
                type="button"
                className="text-green-700 underline"
                onClick={() => {
                  void api
                    .evidence(ids[0])
                    .then(setEvidence)
                    .catch(() => setEvidence({ error: "근거 조회 실패" }));
                }}
              >
                근거 불러오기
              </button>
            )}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

export function ResultCard({ envelope }: { envelope: ResultEnvelope }) {
  const result = envelope.result;
  const rain = result.daily_rainfall as RainResult | undefined;
  const currentStations = result.stations as
    | {
        station_name: string;
        station_code: string;
        temperature_c: string | null;
        day_rain_mm: string | null;
        observation_time: string;
      }[]
    | undefined;
  const priceCards = (result.sample_cards ?? result.links) as PriceCardData[] | undefined;
  const summaryRows = result.summary_rows as Record<string, string>[] | undefined;
  const stationList = result.stations as
    | { station_name: string; station_code?: string; location?: string }[]
    | undefined;
  const isStationSearch = stationList && !currentStations?.[0]?.observation_time;

  return (
    <div className="max-w-full rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {Boolean(envelope.data_status) && <Badge>{envelope.data_status}</Badge>}
        {Boolean(envelope.source_mode) && <Badge>{envelope.source_mode}</Badge>}
        {Boolean(envelope.verified_on) && (
          <span className="text-xs text-gray-500">검증일 {envelope.verified_on}</span>
        )}
        {envelope.cache_resolution !== "bypass" && <Badge>{envelope.cache_resolution}</Badge>}
      </div>
      {typeof result.explanation === "string" && (
        <p className="mb-3 text-base text-gray-800">{result.explanation}</p>
      )}
      {rain ? <ComparisonTable rain={rain} /> : null}
      {currentStations && currentStations.length > 0 && currentStations[0].observation_time && (
        <div className="overflow-x-auto">
          <p className="mb-2 text-sm text-gray-600">{String(result.notice ?? "")}</p>
          <Table>
            <thead>
              <tr>
                <th scope="col">지점</th>
                <th scope="col">기온(℃)</th>
                <th scope="col">일강수(mm)</th>
              </tr>
            </thead>
            <tbody>
              {currentStations.slice(0, 10).map((s) => (
                <tr key={s.station_code}>
                  <th scope="row">{s.station_name}</th>
                  <td>{s.temperature_c ?? "—"}</td>
                  <td>{s.day_rain_mm ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="mt-1 text-xs text-gray-500">
            전체 {currentStations.length}지점 중 10지점 표시
          </p>
        </div>
      )}
      {isStationSearch && stationList ? <StationMap stations={stationList} /> : null}
      {priceCards ? <PriceCards cards={priceCards} /> : null}
      {summaryRows ? (
        <div className="overflow-x-auto">
          <p className="mb-2 text-sm text-gray-600">{String(result.notice ?? "")}</p>
          <Table>
            <thead>
              <tr>
                <th scope="col">정산일</th>
                <th scope="col">시장</th>
                <th scope="col">고사리 행수</th>
                <th scope="col">제주 산지명</th>
              </tr>
            </thead>
            <tbody>
              {summaryRows.slice(0, 12).map((row) => (
                <tr key={`${row.settlement_date}-${row.market_code}`}>
                  <td>{row.settlement_date}</td>
                  <th scope="row">{row.market_name}</th>
                  <td>{row.total_bracken_rows}</td>
                  <td>{row.origin_name_contains_jeju}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      ) : null}
      {typeof result.reason === "string" && !rain && !priceCards && (
        <Alert severity="warning">{String(result.notice ?? result.reason)}</Alert>
      )}
      {envelope.warnings.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-sm text-gray-600">
          {envelope.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      {envelope.errors.length > 0 && (
        <div className="mt-2">
          {envelope.errors.map((error) => (
            <Alert key={error.code} severity="danger">
              {error.message}
            </Alert>
          ))}
        </div>
      )}
      <div className="mt-3">
        <EvidenceSection ids={envelope.evidence_ids} />
      </div>
    </div>
  );
}
