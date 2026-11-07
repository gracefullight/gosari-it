import { useId, useState } from "react";
import { DatePickerField } from "@/components/date-picker-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDisplayDate } from "@/lib/date-format";
import type { PrepareResponse } from "@/lib/gosari.types";
import type { PriceChannel } from "@/lib/price.queries";

const CHANNELS: { value: PriceChannel; label: string; operation: string; source: string }[] = [
  { value: "wholesale", label: "도매", operation: "market_query", source: "at_settlement" },
  { value: "survey", label: "조사가", operation: "survey_link", source: "forestinfo" },
  { value: "retail", label: "판매가", operation: "retail_lookup", source: "retail_sample" },
];
const DEFAULT_MARKETS = [
  { value: "110001", label: "서울가락" },
  { value: "210001", label: "부산엄궁" },
];
const SELECT_CLASS =
  "min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-ring";

export function InlinePriceConditionForm({
  prepare,
  onConfirm,
}: {
  prepare: PrepareResponse;
  onConfirm: (spec: Record<string, unknown>, label: string) => void;
}) {
  const id = useId();
  const seed = { ...prepare.form?.initial_values, ...prepare.spec };
  const initialChannel = CHANNELS.find(
    (item) => seed.price_channel === item.value || seed.operation === item.operation
  )?.value;
  const [channel, setChannel] = useState<PriceChannel | undefined>(initialChannel);
  const [form, setForm] = useState(String(seed.fresh_or_dried ?? ""));
  const [start, setStart] = useState(String(seed.settlement_date ?? formatDisplayDate(new Date())));
  const [end, setEnd] = useState(String(seed.settlement_date_end ?? seed.settlement_date ?? start));
  const [markets, setMarkets] = useState<string[]>(
    Array.isArray(seed.market_ids) && seed.market_ids.length
      ? seed.market_ids.map(String)
      : ["110001"]
  );
  const [weight, setWeight] = useState(String(seed.package_weight_unit ?? ""));
  const [origin, setOrigin] = useState(String(seed.origin_filter ?? ""));
  const marketOptions = prepare.form?.market_options ?? DEFAULT_MARKETS;
  const selected = CHANNELS.find((item) => item.value === channel);
  const invalidDates = channel === "wholesale" && (!start || !end || end < start);
  const fieldId = (field: string) => `${id}-${field}`;

  function submit() {
    if (!selected || invalidDates) return;
    const spec: Record<string, unknown> = {
      ...seed,
      operation: selected.operation,
      source_ids:
        seed.operation === selected.operation && Array.isArray(seed.source_ids)
          ? seed.source_ids
          : [selected.source],
      price_channel: selected.value,
    };
    spec.fresh_or_dried = form || undefined;
    spec.origin_filter = origin || undefined;
    spec.package_weight_unit = weight || undefined;
    if (weight !== String(seed.package_weight_unit ?? "")) {
      spec.product_option = undefined;
      spec.product_id = undefined;
    }
    if (channel === "wholesale") {
      Object.assign(spec, {
        settlement_date: start,
        settlement_date_end: end,
        market_ids: markets,
      });
    } else {
      for (const field of [
        "settlement_date",
        "settlement_date_end",
        "market_ids",
        "grade",
        "package_code",
      ])
        delete spec[field];
    }
    const label = [selected.label, form, origin, channel === "wholesale" ? `${start}~${end}` : ""]
      .filter(Boolean)
      .join(" · ");
    onConfirm(spec, `${label} 가격 조회`);
  }

  return (
    <form
      aria-label="채팅 가격 조건"
      className="flex min-w-0 flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-2 text-base font-medium">어떤 가격을 볼까요?</legend>
        {CHANNELS.map((item) => (
          <Button
            key={item.value}
            type="button"
            variant={channel === item.value ? "default" : "outline"}
            aria-pressed={channel === item.value}
            className="min-h-11 text-base"
            onClick={() => setChannel(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </fieldset>
      {selected ? (
        <>
          <div className="grid gap-1.5">
            <Label className="text-base" htmlFor={fieldId("form")}>
              고사리 종류
            </Label>
            <select
              id={fieldId("form")}
              className={SELECT_CLASS}
              value={form}
              onChange={(event) => setForm(event.target.value)}
            >
              <option value="">생·건 전체</option>
              <option value="생고사리">생고사리</option>
              <option value="건고사리">건고사리</option>
            </select>
          </div>
          {channel === "retail" ? (
            <div className="grid gap-1.5">
              <Label className="text-base" htmlFor={fieldId("retail-weight")}>
                포장 무게
              </Label>
              <Input
                id={fieldId("retail-weight")}
                value={weight}
                placeholder="예: 200 g"
                onChange={(event) => setWeight(event.target.value)}
              />
            </div>
          ) : null}
          {channel === "wholesale" ? (
            <>
              <div className="grid gap-3 min-[480px]:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label className="text-base" required htmlFor={fieldId("start")}>
                    시작일
                  </Label>
                  <DatePickerField
                    id={fieldId("start")}
                    aria-label="가격 시작일"
                    value={start}
                    onChange={setStart}
                    max={formatDisplayDate(new Date())}
                    required
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label className="text-base" required htmlFor={fieldId("end")}>
                    종료일
                  </Label>
                  <DatePickerField
                    id={fieldId("end")}
                    aria-label="가격 종료일"
                    value={end}
                    onChange={setEnd}
                    min={start}
                    max={formatDisplayDate(new Date())}
                    required
                  />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label className="text-base" htmlFor={fieldId("market")}>
                  시장
                </Label>
                <select
                  id={fieldId("market")}
                  className={SELECT_CLASS}
                  value={markets.length > 1 ? "selected" : markets[0]}
                  onChange={(event) => setMarkets([event.target.value])}
                >
                  {markets.length > 1 ? (
                    <option value="selected">선택한 {markets.length}개 시장</option>
                  ) : null}
                  {marketOptions.map((market) => (
                    <option key={market.value} value={market.value}>
                      {market.label}
                    </option>
                  ))}
                  {markets.length === 1 &&
                  !marketOptions.some((market) => market.value === markets[0]) ? (
                    <option value={markets[0]}>선택한 시장</option>
                  ) : null}
                </select>
              </div>
              <details>
                <summary className="flex min-h-11 cursor-pointer items-center text-base text-muted-foreground">
                  세부 조건
                </summary>
                <div className="mt-2 grid gap-3">
                  <div className="grid gap-1.5">
                    <Label className="text-base" htmlFor={fieldId("weight")}>
                      포장 무게
                    </Label>
                    <Input
                      id={fieldId("weight")}
                      value={weight}
                      placeholder="예: 4 kg"
                      onChange={(event) => setWeight(event.target.value)}
                    />
                  </div>
                  <div className="grid gap-1.5">
                    <Label className="text-base" htmlFor={fieldId("origin")}>
                      원산지 표시
                    </Label>
                    <select
                      id={fieldId("origin")}
                      className={SELECT_CLASS}
                      value={origin}
                      onChange={(event) => setOrigin(event.target.value)}
                    >
                      <option value="">전체</option>
                      <option value="제주">제주</option>
                      <option value="국내산">국내산</option>
                      <option value="수입산">수입산</option>
                    </select>
                  </div>
                </div>
              </details>
            </>
          ) : null}
          {invalidDates ? (
            <p role="alert" className="text-base text-destructive">
              조회할 시작일과 종료일을 확인해 주세요.
            </p>
          ) : null}
          <Button type="submit" className="min-h-11 text-base" disabled={invalidDates}>
            가격 조회
          </Button>
        </>
      ) : null}
    </form>
  );
}
