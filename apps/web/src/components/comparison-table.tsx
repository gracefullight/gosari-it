import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export interface RainYear {
  positive_days: number;
  valid_days: number;
  ratio: string | null;
  full_period?: { positive_days: number; valid_days: number };
  value_states?: Record<string, number>;
}

export interface RainResult {
  common_month_days?: string[];
  common_dates?: string[];
  common_day_count?: number;
  per_year?: Record<string, RainYear>;
  per_station?: Record<string, RainYear>;
}

export interface TempYear {
  average: string | null;
  valid_days: number;
  full_period?: { average: string | null; valid_days: number };
  value_states?: Record<string, number>;
}

export interface TempResult {
  common_month_days?: string[];
  common_dates?: string[];
  common_day_count?: number;
  per_year?: Record<string, TempYear>;
  per_station?: Record<string, TempYear>;
}

function formatStateSummary(states?: Record<string, number>): string {
  if (!states) return "";
  const parts: string[] = [];
  if (states.valid != null) parts.push(`양수 ${states.valid}일`);
  if (states.valid_zero != null) parts.push(`숫자0 ${states.valid_zero}일`);
  if (states.unresolved_blank != null) parts.push(`공란 미확정 ${states.unresolved_blank}일`);
  if (states.missing != null) parts.push(`결측 ${states.missing}일`);
  if (states.error != null) parts.push(`오류 ${states.error}일`);
  return parts.length > 0 ? parts.join(" · ") : "";
}

export function ComparisonTable({ rain, temp }: { rain: RainResult; temp?: TempResult }) {
  if (rain.per_year) {
    const years = Object.keys(rain.per_year).sort();
    const commonDays = rain.common_month_days ?? [];
    const commonCount = rain.common_day_count ?? commonDays.length;
    return (
      <div className="flex flex-col gap-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {years.map((year) => {
            const row = rain.per_year?.[year];
            const tempRow = temp?.per_year?.[year];
            if (!row) return null;
            return (
              <div key={`kpi-${year}`} className="rounded-xl bg-accent/60 px-4 py-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-base font-semibold text-accent-foreground">
                    {year}년 봄 (공통 유효 {commonCount}일 기준)
                  </span>
                  {tempRow?.average != null ? (
                    <span className="text-base font-medium tabular-nums text-muted-foreground">
                      평균 {Number(tempRow.average).toFixed(1)}℃
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums text-primary">
                    강수 {row.positive_days}일
                  </span>
                  <span className="text-base tabular-nums text-muted-foreground">
                    / 유효 {row.valid_days}일
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>연도</TableHead>
                <TableHead className="text-right">양수 강수 (공통기간, 일)</TableHead>
                <TableHead className="text-right">공통 유효일 (일)</TableHead>
                <TableHead className="text-right">전체기간 양수/유효 (일)</TableHead>
                {temp?.per_year ? <TableHead className="text-right">평균기온 (℃)</TableHead> : null}
                <TableHead>강수 자료 품질 구성</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {years.map((year) => {
                const row = rain.per_year?.[year];
                const tempRow = temp?.per_year?.[year];
                if (!row) return null;
                return (
                  <TableRow key={year}>
                    <TableCell className="font-medium tabular-nums">{year}</TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {row.positive_days}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.valid_days}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.full_period
                        ? `${row.full_period.positive_days} / ${row.full_period.valid_days}`
                        : ""}
                    </TableCell>
                    {temp?.per_year ? (
                      <TableCell className="text-right tabular-nums">
                        {tempRow?.average != null
                          ? `${Number(tempRow.average).toFixed(1)} (${tempRow.valid_days}일)`
                          : ""}
                      </TableCell>
                    ) : null}
                    <TableCell className="text-base text-muted-foreground">
                      {formatStateSummary(row.value_states)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="mt-2 text-base text-muted-foreground">
            공통 월일 {commonCount}일
            {commonDays.length > 0
              ? ` (${commonDays[0]} ~ ${commonDays[commonDays.length - 1]})`
              : ""}
            {" · "}분모가 다른 전체기간 수치와 직접 비교하지 않습니다. 공란(unresolved_blank)은
            0으로 치환하지 않고 분리합니다.
          </p>
        </div>
      </div>
    );
  }

  if (rain.per_station) {
    const stations = Object.keys(rain.per_station);
    const commonDates = rain.common_dates ?? [];
    const commonCount = rain.common_day_count ?? commonDates.length;
    return (
      <div className="flex flex-col gap-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {stations.map((station) => {
            const row = rain.per_station?.[station];
            const tempRow = temp?.per_station?.[station];
            if (!row) return null;
            const fullTemp = tempRow?.full_period ?? tempRow;
            return (
              <div key={`kpi-${station}`} className="rounded-xl bg-accent/60 px-4 py-3">
                <div className="flex items-baseline justify-between">
                  <span className="text-base font-bold text-accent-foreground">{station}</span>
                  {fullTemp?.average != null ? (
                    <span className="text-base font-medium tabular-nums text-muted-foreground">
                      평균 {Number(fullTemp.average).toFixed(1)}℃
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums text-primary">
                    {row.full_period
                      ? `강수 ${row.full_period.positive_days}일`
                      : `공통 ${row.positive_days}일`}
                  </span>
                  <span className="text-base tabular-nums text-muted-foreground">
                    {row.full_period
                      ? `/ 전체 유효 ${row.full_period.valid_days}일`
                      : `/ 공통 유효 ${row.valid_days}일`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>관측소 지점</TableHead>
                <TableHead className="text-right">공통일자 양수 (일)</TableHead>
                <TableHead className="text-right">공통 유효일 (일)</TableHead>
                <TableHead className="text-right">지점 전체기간 양수/유효 (일)</TableHead>
                {temp?.per_station ? (
                  <TableHead className="text-right">지점 평균기온 (℃)</TableHead>
                ) : null}
                <TableHead>강수 자료 품질 구성</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {stations.map((station) => {
                const row = rain.per_station?.[station];
                const tempRow = temp?.per_station?.[station];
                if (!row) return null;
                const fullTemp = tempRow?.full_period ?? tempRow;
                return (
                  <TableRow key={station}>
                    <TableCell className="font-medium">{station}</TableCell>
                    <TableCell className="text-right font-semibold tabular-nums">
                      {row.positive_days}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{row.valid_days}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.full_period
                        ? `${row.full_period.positive_days} / ${row.full_period.valid_days}`
                        : ""}
                    </TableCell>
                    {temp?.per_station ? (
                      <TableCell className="text-right tabular-nums">
                        {fullTemp?.average != null
                          ? `${Number(fullTemp.average).toFixed(1)} (${fullTemp.valid_days}일)`
                          : ""}
                      </TableCell>
                    ) : null}
                    <TableCell className="text-base text-muted-foreground">
                      {formatStateSummary(row.value_states)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <p className="mt-2 text-base text-muted-foreground">
            동일 달력 날짜 교집합 {commonCount}일
            {commonDates.length > 0
              ? ` (${commonDates[0]} ~ ${commonDates[commonDates.length - 1]})`
              : ""}
            {" · "}서로 다른 연도의 표본인 경우 공통 달력 날짜는 0일이며 지점별 전체기간 및 자료
            품질(숫자 0·공란 미확정)을 각각 표시합니다.
          </p>
        </div>
      </div>
    );
  }

  return null;
}
