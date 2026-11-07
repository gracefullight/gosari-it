import { ArrowsClockwiseIcon, CaretDownIcon } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { type PriceCardData, PriceCardList } from "@/components/price-card-list";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type PriceChannel, type PriceFilters, priceQueryOptions } from "@/lib/price.queries";

const CHANNELS: { value: PriceChannel; label: string }[] = [
  { value: "retail", label: "소매 판매가" },
  { value: "survey", label: "지역 조사가" },
  { value: "wholesale", label: "도매 거래" },
];
interface Option {
  value: string;
  label: string;
}
interface MarketOptions {
  markets: Option[];
  forms: Option[];
  grades: Option[];
  packages: Option[];
  weights?: Option[];
}
const DEFAULT_OPTIONS: MarketOptions = {
  markets: [{ value: "110001", label: "서울가락" }],
  forms: [
    { value: "생고사리", label: "생고사리" },
    { value: "건고사리", label: "건고사리" },
  ],
  grades: [],
  packages: [],
};
function todayInJeju() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
function initialFilters(): PriceFilters {
  const today = todayInJeju();
  return {
    settlement_date: today,
    settlement_date_end: today,
    market_ids: ["110001"],
    fresh_or_dried: "",
    grade: "",
    package_code: "",
    package_weight_unit: "",
    origin_filter: "",
  };
}
const selectClass =
  "min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base text-foreground focus-visible:outline-2 focus-visible:outline-ring";

export function PriceLookupPage({ initialChannel = "retail" }: { initialChannel?: PriceChannel }) {
  const [channel, setChannel] = useState<PriceChannel>(initialChannel);
  const [filters, setFilters] = useState(initialFilters);
  const [applied, setApplied] = useState(initialFilters);
  const [options, setOptions] = useState<MarketOptions>(DEFAULT_OPTIONS);
  const [filtersOpen, setFiltersOpen] = useState(true);
  const query = useQuery(priceQueryOptions(channel, applied));
  const result = query.data?.result;
  const samples = result?.sample_cards as PriceCardData[] | undefined;
  const links = result?.links as PriceCardData[] | undefined;
  const cards = (result?.price_cards as PriceCardData[] | undefined) ?? samples ?? links;
  const receivedOptions = result?.options as MarketOptions | undefined;
  if (receivedOptions && receivedOptions !== options) setOptions(receivedOptions);
  const failed = result?.failed_scope as
    | { settlement_date: string; market_code: string; remaining_scope?: unknown }[]
    | undefined;
  const unavailable = result?.reason === "AT_KEY_MISSING" || result?.reason === "LIVE_DISABLED";
  const update = (name: keyof PriceFilters, value: string | string[]) =>
    setFilters((old) => ({ ...old, [name]: value }));
  const dateInvalid = filters.settlement_date_end < filters.settlement_date;
  const appliedSummary = [
    applied.settlement_date === applied.settlement_date_end
      ? applied.settlement_date
      : `${applied.settlement_date}~${applied.settlement_date_end}`,
    applied.market_ids.length === 1
      ? options.markets.find((m) => m.value === applied.market_ids[0])?.label
      : `${applied.market_ids.length}개 시장`,
    applied.fresh_or_dried,
    options.grades.find((item) => item.value === applied.grade)?.label,
    options.packages.find((item) => item.value === applied.package_code)?.label,
    applied.package_weight_unit,
    applied.origin_filter,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <section aria-label="가격 조사" className="min-w-0">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <fieldset aria-label="가격 종류" className="flex flex-wrap gap-1 rounded-xl bg-muted p-1">
          {CHANNELS.map((item) => (
            <Button
              key={item.value}
              variant={channel === item.value ? "default" : "ghost"}
              size="sm"
              aria-pressed={channel === item.value}
              onClick={() => {
                setChannel(item.value);
                if (item.value === "wholesale") setFiltersOpen(true);
              }}
            >
              {item.label}
            </Button>
          ))}
        </fieldset>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <ArrowsClockwiseIcon
            aria-hidden="true"
            className={query.isFetching ? "animate-spin motion-reduce:animate-none" : ""}
          />
          새로고침
        </Button>
      </div>
      {channel === "wholesale" ? (
        <>
          {!filtersOpen ? (
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <p className="min-w-0 flex-1 basis-48 text-base text-muted-foreground">
                {appliedSummary}
              </p>
              <Button variant="outline" onClick={() => setFiltersOpen(true)}>
                조회 조건 변경
              </Button>
            </div>
          ) : null}
          <form
            hidden={!filtersOpen}
            className="mb-6 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!dateInvalid && filters.market_ids.length) {
                setApplied({ ...filters });
                setFiltersOpen(false);
              }
            }}
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <label htmlFor="price-date-start" className="text-base">
                  시작일
                </label>
                <DatePickerField
                  id="price-date-start"
                  aria-label="가격 시작일"
                  value={filters.settlement_date}
                  onChange={(value) => update("settlement_date", value)}
                  max={todayInJeju()}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="price-date-end" className="text-base">
                  종료일
                </label>
                <DatePickerField
                  id="price-date-end"
                  aria-label="가격 종료일"
                  value={filters.settlement_date_end}
                  onChange={(value) => update("settlement_date_end", value)}
                  min={filters.settlement_date}
                  max={todayInJeju()}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="price-market" className="text-base">
                  시장
                </label>
                <select
                  id="price-market"
                  className={selectClass}
                  value={filters.market_ids[0] ?? ""}
                  onChange={(event) => update("market_ids", [event.target.value])}
                >
                  {options.markets.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="price-form" className="text-base">
                  고사리 종류
                </label>
                <select
                  id="price-form"
                  className={selectClass}
                  value={filters.fresh_or_dried}
                  onChange={(event) => update("fresh_or_dried", event.target.value)}
                >
                  <option value="">전체</option>
                  {options.forms.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <details className="group">
              <summary className="inline-flex min-h-11 cursor-pointer items-center gap-2 text-base">
                세부 조건
                <CaretDownIcon aria-hidden="true" />
              </summary>
              <div className="grid grid-cols-1 gap-3 pt-3 md:grid-cols-2">
                <div className="space-y-1.5">
                  <label htmlFor="price-grade">등급</label>
                  <select
                    id="price-grade"
                    className={selectClass}
                    value={filters.grade}
                    onChange={(event) => update("grade", event.target.value)}
                  >
                    <option value="">전체 등급</option>
                    {options.grades.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="price-package">포장</label>
                  <select
                    id="price-package"
                    className={selectClass}
                    value={filters.package_code}
                    onChange={(event) => update("package_code", event.target.value)}
                  >
                    <option value="">전체 포장</option>
                    {options.packages.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="price-weight">단량</label>
                  <select
                    id="price-weight"
                    className={selectClass}
                    value={filters.package_weight_unit}
                    onChange={(event) => update("package_weight_unit", event.target.value)}
                  >
                    <option value="">전체 단량</option>
                    {filters.package_weight_unit &&
                    !options.weights?.some((item) => item.value === filters.package_weight_unit) ? (
                      <option value={filters.package_weight_unit}>
                        {filters.package_weight_unit}
                      </option>
                    ) : null}
                    {(options.weights ?? []).map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="price-origin">산지명</label>
                  <Input
                    id="price-origin"
                    placeholder="예: 제주"
                    value={filters.origin_filter}
                    onChange={(event) => update("origin_filter", event.target.value)}
                  />
                </div>
              </div>
              <fieldset className="mt-4">
                <legend className="text-base">시장 함께 보기</legend>
                <div className="mt-2 grid max-h-56 grid-cols-1 gap-x-4 overflow-y-auto md:grid-cols-2">
                  {options.markets.map((item) => (
                    <label key={item.value} className="flex min-h-11 items-center gap-2 text-base">
                      <input
                        type="checkbox"
                        className="size-5 accent-primary"
                        checked={filters.market_ids.includes(item.value)}
                        onChange={(event) =>
                          update(
                            "market_ids",
                            event.target.checked
                              ? [...filters.market_ids, item.value]
                              : filters.market_ids.filter((id) => id !== item.value)
                          )
                        }
                      />
                      {item.label}
                    </label>
                  ))}
                </div>
              </fieldset>
            </details>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                disabled={query.isFetching || dateInvalid || !filters.market_ids.length}
              >
                가격 조회
              </Button>
              {filters.market_ids.length > 1 ? (
                <span className="text-base text-muted-foreground">
                  {filters.market_ids.length}개 시장
                </span>
              ) : null}
              {dateInvalid ? (
                <p role="alert" className="text-base text-destructive">
                  종료일을 확인해 주세요.
                </p>
              ) : null}
            </div>
          </form>
        </>
      ) : null}
      {query.isPending ? (
        <div role="status" className="space-y-4 py-8 text-base text-muted-foreground">
          <p>가격 불러오는 중…</p>
          <div className="h-16 animate-pulse rounded-lg bg-muted motion-reduce:animate-none" />
          <div className="h-16 animate-pulse rounded-lg bg-muted motion-reduce:animate-none" />
        </div>
      ) : null}
      {query.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {query.error.message || "가격을 불러오지 못했습니다."}
          </AlertDescription>
        </Alert>
      ) : null}
      {unavailable ? (
        <p className="py-8 text-base text-muted-foreground">
          도매 가격 연결이 준비되지 않았습니다.
        </p>
      ) : null}
      {failed?.length ? (
        <Alert>
          <AlertDescription>
            <span>일부 날짜·시장 조회에 실패했습니다.</span>
            <details className="mt-2">
              <summary className="min-h-11 cursor-pointer">실패한 조회 {failed.length}건</summary>
              <ul>
                {failed.map((scope) => (
                  <li key={`${scope.settlement_date}-${scope.market_code}`}>
                    {scope.settlement_date} ·{" "}
                    {options.markets.find((m) => m.value === scope.market_code)?.label ??
                      scope.market_code}
                    {scope.remaining_scope ? " · 이후 조회 중단" : ""}
                  </li>
                ))}
              </ul>
            </details>
          </AlertDescription>
        </Alert>
      ) : null}
      {cards?.length ? <PriceCardList cards={cards} /> : null}
      {query.isSuccess && !unavailable && !cards?.length && !failed?.length ? (
        <p className="py-12 text-center text-base text-muted-foreground">
          {channel === "wholesale"
            ? "선택한 날짜·시장에서 조건에 맞는 거래가 없습니다."
            : "조회된 가격이 없습니다."}
        </p>
      ) : null}
    </section>
  );
}
