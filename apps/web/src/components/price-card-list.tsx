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
      <ul className="divide-y divide-border border-y border-border">
        {cards.map((card) => {
          const sourceUrl = safeExternalUrl(card.source_url);
          return (
            <li
              key={
                card.row_id ??
                `${card.source_url}-${card.product_option ?? card.survey_stage ?? card.title ?? card.channel}`
              }
              className="py-5 sm:py-6"
            >
              <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
                <div className="min-w-0 flex-1 basis-44">
                  <p className="text-base font-medium text-foreground sm:text-base">
                    {card.product ?? card.title}
                  </p>
                  <p className="mt-1 text-base text-muted-foreground">
                    {[card.form, card.product_option, formatDisplayDate(card.price_as_of)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  {card.channel === "wholesale" ? (
                    <p className="mb-1 text-base text-muted-foreground">정산 평균가</p>
                  ) : null}
                  {showPerKg ? (
                    <p className="text-xl font-bold tabular-nums tracking-tight text-foreground sm:text-2xl">
                      {card.price_per_kg_value == null
                        ? "환산가 없음"
                        : `${card.price_per_kg_value.toLocaleString()}원 / kg`}
                    </p>
                  ) : card.price_value != null ? (
                    <p className="text-xl font-bold tabular-nums tracking-tight text-foreground sm:text-2xl">
                      {card.price_value.toLocaleString()}원
                      {card.net_weight_value
                        ? card.net_weight_value === 1000
                          ? " / kg"
                          : ` / ${card.net_weight_value}g`
                        : card.original_quantity && card.original_unit
                          ? ` / ${card.original_quantity} ${card.original_unit}`
                          : ""}
                    </p>
                  ) : card.channel === "wholesale" ? (
                    <p className="text-base text-muted-foreground">가격 미확인</p>
                  ) : null}
                  {sourceUrl ? (
                    <a
                      href={sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`${card.product ?? card.title ?? "상품"} 외부 링크`}
                      title="상품 페이지 열기"
                      className="mt-1 inline-flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-primary focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      <ArrowSquareOutIcon className="size-5" aria-hidden="true" />
                    </a>
                  ) : null}
                </div>
              </div>
              <details className="group mt-2 text-base text-muted-foreground">
                <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-sm focus-visible:outline-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
                  세부정보{" "}
                  <CaretDownIcon
                    className="transition-transform group-open:rotate-180"
                    aria-hidden="true"
                  />
                </summary>
                <dl className="mt-2 grid gap-x-6 gap-y-2 border-l-2 border-border pl-3 sm:grid-cols-2">
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
