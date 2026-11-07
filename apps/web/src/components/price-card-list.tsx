import { ArrowSquareOutIcon, CaretDownIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatDisplayDate } from "@/lib/date-format";

export interface PriceCardData {
  channel: string;
  row_id?: string;
  price_basis?: string;
  original_quantity?: string;
  original_unit?: string;
  corporation?: string;
  minimum_price?: string;
  maximum_price?: string;
  total_quantity?: string;
  total_price?: string;
  product?: string;
  origin_label_raw?: string;
  survey_region?: string;
  survey_grade?: string;
  survey_stage?: string;
  form?: string;
  product_option?: string;
  net_weight_value?: number;
  price_value?: number;
  price_per_kg_value?: number;
  conversion_formula?: string;
  shipping_value?: number;
  coupon_price?: number;
  coupon_condition?: string;
  price_as_of?: string;
  source_url?: string;
  title?: string;
  description?: string;
}

interface PriceCardListProps {
  cards: PriceCardData[];
  links?: PriceCardData[];
}

const PRICE_COLUMNS =
  "xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_7rem_minmax(10rem,auto)_2.75rem_2.75rem]";

const HTTP_URL = /^https?:\/\//i;
function safeExternalUrl(value?: string): string | undefined {
  if (!value || !HTTP_URL.test(value)) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function packageLabel(card: PriceCardData): string {
  if (card.net_weight_value)
    return card.net_weight_value === 1000 ? "kg" : `${card.net_weight_value}g`;
  return card.original_quantity && card.original_unit
    ? `${card.original_quantity} ${card.original_unit}`
    : "";
}

function priceLabel(card: PriceCardData, perKg: boolean): string {
  if (perKg)
    return card.price_per_kg_value == null
      ? "환산가 없음"
      : `${card.price_per_kg_value.toLocaleString()}원 / kg`;
  if (card.price_value == null) return card.channel === "wholesale" ? "가격 미확인" : "";
  const unit = packageLabel(card);
  return `${card.price_value.toLocaleString()}원${unit ? ` / ${unit}` : ""}`;
}

export function PriceCardList({ cards }: PriceCardListProps) {
  const [displayMode, setDisplayMode] = useState<"pack" | "kg">("pack");
  const canCompare = cards.some(
    (card) => card.price_per_kg_value != null && card.net_weight_value !== 1000
  );
  const showPerKg = canCompare && displayMode === "kg";
  return (
    <div className="min-w-0">
      {canCompare ? (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="text-base text-muted-foreground">가격 기준</span>
          <fieldset aria-label="가격 표시 기준" className="flex gap-1 rounded-xl bg-muted p-1">
            <Button
              size="sm"
              className="min-h-11 text-base"
              variant={!showPerKg ? "default" : "ghost"}
              aria-pressed={!showPerKg}
              onClick={() => setDisplayMode("pack")}
            >
              상품 가격
            </Button>
            <Button
              size="sm"
              className="min-h-11 text-base"
              variant={showPerKg ? "default" : "ghost"}
              aria-pressed={showPerKg}
              onClick={() => setDisplayMode("kg")}
            >
              1kg 환산
            </Button>
          </fieldset>
        </div>
      ) : null}
      <div
        aria-hidden="true"
        className={`hidden items-center gap-x-3 px-1 pb-2 text-base text-muted-foreground xl:grid ${PRICE_COLUMNS}`}
      >
        <span>상품</span>
        <span>규격</span>
        <span>기준일</span>
        <span className="text-right">가격</span>
        <span />
        <span />
      </div>
      <ul className="divide-y divide-border border-y border-border">
        {cards.map((card) => {
          const sourceUrl = safeExternalUrl(card.source_url);
          const specification = [card.form, card.product_option ?? packageLabel(card)]
            .filter(Boolean)
            .join(" · ");
          return (
            <li
              key={
                card.row_id ??
                `${card.source_url}-${card.product_option ?? card.survey_stage ?? card.title ?? card.channel}`
              }
              className="py-3"
            >
              <details className="group text-base text-muted-foreground">
                <summary
                  className={`grid min-h-11 cursor-pointer list-none grid-cols-[minmax(0,1fr)_2.75rem_2.75rem] items-center gap-x-3 gap-y-1 rounded-sm px-1 focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden ${PRICE_COLUMNS}`}
                >
                  <span
                    className="col-span-3 min-w-0 truncate font-medium text-foreground xl:col-span-1"
                    title={card.product ?? card.title}
                  >
                    {card.product ?? card.title}
                  </span>
                  <span className="col-span-3 flex min-w-0 items-center justify-between gap-3 xl:contents">
                    <span className="min-w-0 truncate" title={specification}>
                      {specification}
                    </span>
                    <time className="shrink-0 tabular-nums" dateTime={card.price_as_of}>
                      {formatDisplayDate(card.price_as_of)}
                    </time>
                  </span>
                  <span className="min-w-0 text-right text-lg font-bold tabular-nums tracking-tight text-foreground xl:text-xl">
                    {card.channel === "wholesale" ? (
                      <span className="sr-only">정산 평균가 </span>
                    ) : null}
                    {priceLabel(card, showPerKg)}
                  </span>
                  {sourceUrl ? (
                    <a
                      href={sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`${card.product ?? card.title ?? "상품"} 외부 링크`}
                      title="외부 링크 열기"
                      className="inline-flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <ArrowSquareOutIcon className="size-5" aria-hidden="true" />
                    </a>
                  ) : (
                    <span aria-hidden="true" />
                  )}
                  <span className="inline-flex size-11 items-center justify-center rounded-lg group-hover:bg-muted">
                    <span className="sr-only">세부정보</span>
                    <CaretDownIcon
                      className="size-5 transition-transform group-open:rotate-180"
                      aria-hidden="true"
                    />
                  </span>
                </summary>
                <dl className="mt-2 grid gap-x-6 gap-y-2 border-l-2 border-border pl-3 sm:grid-cols-2">
                  {card.channel === "wholesale" ? (
                    <div>
                      <dt className="inline">가격 기준 </dt>
                      <dd className="inline text-foreground">정산 평균가</dd>
                    </div>
                  ) : null}
                  {card.corporation ? (
                    <div>
                      <dt className="inline">법인 </dt>
                      <dd className="inline text-foreground">{card.corporation}</dd>
                    </div>
                  ) : null}
                  {card.minimum_price != null && card.maximum_price != null ? (
                    <div>
                      <dt className="inline">최저·최고 </dt>
                      <dd className="inline text-foreground">
                        {Number(card.minimum_price).toLocaleString()}~
                        {Number(card.maximum_price).toLocaleString()}원
                      </dd>
                    </div>
                  ) : null}
                  {card.total_quantity ? (
                    <div>
                      <dt className="inline">거래량 </dt>
                      <dd className="inline text-foreground">
                        {Number(card.total_quantity).toLocaleString()} {card.original_unit}
                      </dd>
                    </div>
                  ) : null}
                  {card.origin_label_raw ? (
                    <div>
                      <dt className="inline">원산지 표시 </dt>
                      <dd className="inline text-foreground">{card.origin_label_raw}</dd>
                    </div>
                  ) : null}
                  {card.survey_region ? (
                    <div>
                      <dt className="inline">조사지역 </dt>
                      <dd className="inline text-foreground">
                        {card.survey_region} · {card.survey_grade ?? ""} · {card.survey_stage ?? ""}
                      </dd>
                    </div>
                  ) : null}
                  {card.price_per_kg_value != null && card.net_weight_value !== 1000 ? (
                    <div>
                      <dt className="inline">1kg 환산 </dt>
                      <dd className="inline text-foreground">
                        {card.price_per_kg_value.toLocaleString()}원/kg
                      </dd>
                    </div>
                  ) : null}
                  {card.shipping_value != null ? (
                    <div>
                      <dt className="inline">배송비 </dt>
                      <dd className="inline text-foreground">
                        {card.shipping_value.toLocaleString()}원 (별도)
                      </dd>
                    </div>
                  ) : null}
                  {card.coupon_price != null ? (
                    <div>
                      <dt className="inline">쿠폰가 </dt>
                      <dd className="inline text-foreground">
                        {card.coupon_price.toLocaleString()}원{" "}
                        {card.coupon_condition ? `(${card.coupon_condition})` : ""}
                      </dd>
                    </div>
                  ) : null}
                  {card.price_as_of ? (
                    <div>
                      <dt className="inline">확인시점: </dt>
                      <dd className="inline text-foreground">
                        {formatDisplayDate(card.price_as_of)}
                      </dd>
                    </div>
                  ) : null}
                  {card.conversion_formula ? (
                    <div className="sm:col-span-2">
                      <dt className="inline">환산식 </dt>
                      <dd className="inline text-foreground">{card.conversion_formula}</dd>
                    </div>
                  ) : null}
                </dl>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
