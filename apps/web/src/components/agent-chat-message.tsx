import { CaretDownIcon } from "@phosphor-icons/react";
import { ResultCard } from "@/components/result-card";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import { formatDisplayDate } from "@/lib/date-format";
import type { AgentToolCall } from "@/lib/gosari.types";
import type { ChatMessage } from "@/stores/chat.atoms";

const CHANNEL_LABELS: Record<string, string> = {
  wholesale: "도매",
  survey: "조사가",
  retail: "판매가",
};
const MARKET_LABELS: Record<string, string> = { "110001": "서울가락", "210001": "부산엄궁" };
const TOOL_STATUS = { running: "진행 중", completed: "완료", failed: "실패" };

function publicConditions(tool: AgentToolCall): [string, string][] {
  const value = tool.conditions ?? {};
  const entries: [string, unknown][] = [
    ["가격 종류", CHANNEL_LABELS[String(value.price_channel)]],
    ["고사리 종류", value.fresh_or_dried],
    ["시작일", value.settlement_date],
    ["종료일", value.settlement_date_end],
    ["원산지 표시", value.origin_filter],
    ["포장 무게", value.package_weight_unit],
    ["상품 옵션", value.product_option],
    ["조사지역", value.survey_region],
  ];
  if (Array.isArray(value.market_ids))
    entries.push([
      "시장",
      value.market_ids.map((id) => MARKET_LABELS[String(id)] ?? "선택한 시장").join(" · "),
    ]);
  if (Array.isArray(value.station_selections))
    entries.push([
      "지역",
      value.station_selections
        .flatMap((item) =>
          item &&
          typeof item === "object" &&
          "station_name" in item &&
          typeof item.station_name === "string"
            ? [item.station_name]
            : []
        )
        .join(" · "),
    ]);
  if (Array.isArray(value.years))
    entries.push(["연도", value.years.filter((year) => typeof year === "number").join(" · ")]);
  if (typeof value.month_day_start === "string" && typeof value.month_day_end === "string")
    entries.push(["기간", `${value.month_day_start}~${value.month_day_end}`]);
  if (Array.isArray(value.candidates))
    entries.push([
      "후보",
      value.candidates
        .flatMap((candidate) => {
          if (!candidate || typeof candidate !== "object") return [];
          const row = candidate as Record<string, unknown>;
          return [
            [
              row.station_name,
              formatDisplayDate(String(row.target_date ?? row.date ?? "")),
              row.target_time_window ?? row.time_slot,
            ]
              .filter((part) => typeof part === "string" && part)
              .join(" · "),
          ];
        })
        .filter(Boolean)
        .join(" / "),
    ]);
  return entries.flatMap(([label, text]) =>
    typeof text === "string" && text ? [[label, text] as [string, string]] : []
  );
}

export function AgentChatMessage({ message }: { message: ChatMessage }) {
  const { cancelStream, resumeStream } = useChat();
  const stream = message.stream;
  if (!stream) return null;
  const results = stream.tools.filter((tool) => tool.result);
  return (
    <article aria-label="AI 답변" className="min-w-0 space-y-4 text-base">
      {message.text ? (
        <p className="whitespace-pre-wrap break-words leading-relaxed">{message.text}</p>
      ) : null}
      {stream.tools.length ? (
        <section className="space-y-2" aria-label="도구 실행 내역">
          {stream.tools.map((tool) => (
            <details key={tool.id} className="group rounded-xl border border-border bg-card">
              <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 px-3 py-2 text-base [&::-webkit-details-marker]:hidden">
                <span className="min-w-0 flex-1 break-words font-medium">{tool.label}</span>
                <span
                  className={
                    tool.status === "failed" ? "text-destructive" : "text-muted-foreground"
                  }
                >
                  {TOOL_STATUS[tool.status]}
                </span>
                <CaretDownIcon
                  aria-hidden="true"
                  className="size-4 shrink-0 group-open:rotate-180"
                />
              </summary>
              <div className="space-y-3 border-t border-border px-3 py-3">
                {publicConditions(tool).length ? (
                  <dl className="grid gap-2">
                    {publicConditions(tool).map(([label, value]) => (
                      <div key={label} className="flex flex-wrap gap-x-3 gap-y-1">
                        <dt className="text-muted-foreground">{label}</dt>
                        <dd className="break-words">{value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
                {tool.summary ? (
                  <p className="whitespace-pre-wrap break-words">{tool.summary}</p>
                ) : null}
                {tool.error ? <p className="text-destructive">{tool.error}</p> : null}
              </div>
            </details>
          ))}
        </section>
      ) : null}
      {results.length ? (
        results.map((tool) => <ResultCard key={tool.id} envelope={tool.result!} />)
      ) : message.envelope ? (
        <ResultCard envelope={message.envelope} />
      ) : null}
      {message.error ? (
        <p role="alert" className="text-base text-destructive">
          {message.error}
        </p>
      ) : null}
      {stream.status === "streaming" ? (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="text-base text-muted-foreground">
            {stream.stage_message ?? "답변을 받고 있습니다."}
          </p>
          {stream.job_id ? (
            <Button
              variant="ghost"
              className="min-h-11 text-base"
              onClick={() => void cancelStream(message.id)}
            >
              답변 중지
            </Button>
          ) : null}
        </div>
      ) : null}
      {stream.status === "disconnected" ? (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            className="min-h-11 text-base"
            onClick={() => resumeStream(message.id)}
          >
            이어서 받기
          </Button>
          <Button
            variant="ghost"
            className="min-h-11 text-base"
            onClick={() => void cancelStream(message.id)}
          >
            답변 중지
          </Button>
        </div>
      ) : null}
      {stream.status === "cancelled" ? (
        <p className="text-base text-muted-foreground">답변을 중지했습니다.</p>
      ) : null}
    </article>
  );
}
