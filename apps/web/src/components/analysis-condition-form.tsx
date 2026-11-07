import { useState } from "react";
import { InlineOutingConditionForm } from "@/components/inline-outing-condition-form";
import { InlinePriceConditionForm } from "@/components/inline-price-condition-form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useChat } from "@/hooks/use-chat";
import type { PrepareResponse } from "@/lib/gosari.types";

const YEAR_PATTERN = /^\d{4}$/;

export function AnalysisConditionForm({ prepare }: { prepare: PrepareResponse }) {
  const { confirmSpec } = useChat();
  const original = prepare.spec;
  const selection = (
    original?.station_selections as { source_id?: string; station_name?: string }[] | undefined
  )?.[0];
  const [station, setStation] = useState(selection?.station_name ?? "");
  const [years, setYears] = useState(
    Array.isArray(original?.years) ? original.years.join(",") : ""
  );
  const [periodStart, setPeriodStart] = useState(String(original?.month_day_start ?? "04-01"));
  const [periodEnd, setPeriodEnd] = useState(String(original?.month_day_end ?? "05-31"));
  const questions = prepare.form?.questions;
  const history =
    original?.operation === "history_compare" ||
    prepare.feature === "history_compare" ||
    prepare.form?.feature_hint === "history_compare";
  const price =
    prepare.form?.kind === "price_conditions" ||
    prepare.feature === "price" ||
    prepare.form?.feature_hint === "price" ||
    original?.operation === "market_query" ||
    original?.operation === "retail_lookup" ||
    original?.operation === "survey_link" ||
    prepare.form?.feature_hint === "market_query" ||
    prepare.form?.feature_hint === "retail_lookup" ||
    prepare.form?.feature_hint === "survey_link";

  function submit() {
    const yearList = years
      .split(",")
      .map((y) => Number.parseInt(y.trim(), 10))
      .filter((y) => !Number.isNaN(y));
    confirmSpec(
      {
        ...original,
        operation: "history_compare",
        source_ids: original?.source_ids ?? ["jeju_579"],
        station_selections: [
          { ...selection, source_id: selection?.source_id ?? "jeju_579", station_name: station },
        ],
        years: yearList,
        month_day_start: periodStart,
        month_day_end: periodEnd,
        elements: original?.elements ?? ["daily_rainfall"],
        comparison_scope: original?.comparison_scope ?? "common_valid_month_days",
        aggregation: original?.aggregation ?? "count_positive_days",
        unit: original?.unit ?? "day",
        timezone: original?.timezone ?? "Asia/Seoul",
      },
      `${station} ${yearList.join("·")}년 ${periodStart}~${periodEnd} 비교`
    );
  }

  return (
    <div className="max-w-[85%] rounded-2xl border border-border bg-card p-4 shadow-sm">
      <p className="mb-3 text-base font-semibold">분석 조건을 확인해 주세요</p>
      {questions ? (
        <ul className="mb-3 list-inside list-disc text-base text-muted-foreground">
          {questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      ) : null}
      {history ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="condition-station">지역</Label>
            <Input
              id="condition-station"
              value={station}
              onChange={(e) => setStation(e.target.value)}
            />
          </div>
          <div className="grid gap-3 min-[480px]:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="condition-period-start">시작 월일</Label>
              <Input
                id="condition-period-start"
                value={periodStart}
                placeholder="04-01"
                onChange={(event) => setPeriodStart(event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="condition-period-end">종료 월일</Label>
              <Input
                id="condition-period-end"
                value={periodEnd}
                placeholder="05-31"
                onChange={(event) => setPeriodEnd(event.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="condition-years">비교 연도 (쉼표 구분)</Label>
            <Input id="condition-years" value={years} onChange={(e) => setYears(e.target.value)} />
          </div>
          <Button
            onClick={submit}
            disabled={
              !station.trim() ||
              years.split(",").filter((y) => YEAR_PATTERN.test(y.trim())).length < 2
            }
          >
            이 조건으로 비교
          </Button>
        </div>
      ) : price ? (
        <InlinePriceConditionForm
          prepare={prepare}
          onConfirm={(spec, label) => confirmSpec(spec, label, null)}
        />
      ) : original ? (
        <div className="flex flex-col gap-3">
          <p className="text-base text-muted-foreground">
            {original.operation === "outing_compare"
              ? "선택한 날짜·지역·시간의 날씨를 비교합니다."
              : original.operation === "market_query"
                ? "선택한 조건의 도매 가격을 조회합니다."
                : "확인한 조건으로 자료를 조회합니다."}
          </p>
          <Button onClick={() => confirmSpec(original, "이 조건으로 조회")}>
            이 조건으로 조회
          </Button>
        </div>
      ) : (
        <InlineOutingConditionForm
          prepare={prepare}
          onConfirm={(spec, label) => confirmSpec(spec, label, null)}
        />
      )}
    </div>
  );
}
