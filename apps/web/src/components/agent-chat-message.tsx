import { ArrowSquareOutIcon, CaretDownIcon, RobotIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { AgentResultDetailDialog } from "@/components/agent-result-detail-dialog";
import { AgentGeneratedUI } from "@/components/agent-ui-renderer";
import { AssistantMarkdown } from "@/components/assistant-markdown";
import { ChatThinkingIndicator } from "@/components/chat-thinking-indicator";
import { PersonalSearchResult } from "@/components/personal-search-result";
import { ResultCard } from "@/components/result-card";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/use-chat";
import type { AgentUIAction } from "@/lib/agent-ui.catalog";
import { conditionPreparation, notebookPreparation } from "@/lib/agent-ui-actions";
import { formatDisplayDate } from "@/lib/date-format";
import type { AgentToolCall } from "@/lib/gosari.types";
import { getStreetViewLinks, hasModalResult } from "@/lib/street-view";
import type { ChatMessage } from "@/stores/chat.atoms";

const CHANNEL_LABELS: Record<string, string> = {
  wholesale: "도매",
  survey: "조사가",
  retail: "판매가",
};
const MARKET_LABELS: Record<string, string> = { "110001": "서울가락", "210001": "부산엄궁" };
const TOOL_STATUS = { running: "진행 중", completed: "완료", failed: "실패" };
const INTERNAL_ERROR_CODE = /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/;

function readableError(error: string): string {
  return INTERNAL_ERROR_CODE.test(error)
    ? "답변을 마무리하지 못했습니다. 다시 요청해 주세요."
    : error;
}

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
  const { resumeStream, push, confirmSpec } = useChat();
  const [detailOpen, setDetailOpen] = useState(false);
  const stream = message.stream;
  if (!stream) return null;
  const results = stream.tools.filter((tool) => hasModalResult(tool.result));
  const streetViewLinks = getStreetViewLinks([
    message.envelope,
    ...stream.tools.map((tool) => tool.result),
    ...Object.values(message.ui_results ?? {}),
  ]);
  const uiResults = Object.fromEntries(
    Object.entries(message.ui_results ?? {}).filter(([, value]) => hasModalResult(value))
  );
  const hasText = Boolean(message.text?.trim());
  const showThinking =
    stream.status === "streaming" && !hasText && !message.error && !stream.tools.length;
  const cancelRequested =
    stream.status === "streaming" && stream.stage_message === "취소를 요청했습니다.";
  const showBubble =
    hasText ||
    Boolean(message.error) ||
    showThinking ||
    cancelRequested ||
    stream.status === "cancelled";
  const currentTool =
    stream.tools.filter((tool) => tool.status === "running").at(-1) ?? stream.tools.at(-1);
  const fallback = results.length ? (
    results.map((tool) => <ResultCard key={tool.id} envelope={tool.result!} />)
  ) : hasModalResult(message.envelope) ? (
    <ResultCard envelope={message.envelope} />
  ) : null;
  const personalSearch =
    message.personal_search && message.personal_search.count > 0
      ? message.personal_search
      : undefined;
  async function handleAction(action: AgentUIAction) {
    const envelope = message.ui_results?.[action.resultRef];
    if (!envelope) return;
    if (action.id !== "show_weather_map" && action.id !== "show_price_table") setDetailOpen(false);
    const openConditions = () =>
      push({
        role: "assistant",
        kind: "clarify",
        prepare: conditionPreparation(envelope, action.values),
      });
    const namedActionHandlers = {
      adjust_conditions: openConditions,
      compare_dates: openConditions,
      compare_packages: () => {
        const prepare = conditionPreparation(envelope, action.values);
        if (
          prepare.spec &&
          typeof action.values?.package_weight_unit === "string" &&
          action.values.package_weight_unit
        )
          return confirmSpec(prepare.spec, action.label ?? "다른 중량 가격 조회", null);
        openConditions();
      },
      save_to_notebook: () =>
        push({ role: "assistant", kind: "personal-form", prepare: notebookPreparation(envelope) }),
      show_weather_map: () => {},
      show_price_table: () => {},
    };
    await namedActionHandlers[action.id]?.();
  }
  return (
    <article
      aria-label="AI 답변"
      className="w-full min-w-0 max-w-5xl self-start space-y-4 text-base"
    >
      {currentTool ? (
        <details aria-label="도구 실행 내역" className="group/trace min-w-0 text-base">
          <summary className="flex min-h-11 w-fit max-w-full cursor-pointer list-none items-center gap-2 py-2 text-muted-foreground [&::-webkit-details-marker]:hidden">
            <RobotIcon aria-hidden="true" className="size-5 shrink-0" />
            <span className="min-w-0 break-words">
              {currentTool.label} · {TOOL_STATUS[currentTool.status]}
              <span className="ml-2">{stream.tools.length}건</span>
            </span>
            <CaretDownIcon
              aria-hidden="true"
              className="size-4 shrink-0 group-open/trace:rotate-180"
            />
          </summary>
          <ol className="ml-2 space-y-3 border-l border-border py-2 pl-5">
            {stream.tools.map((tool) => {
              const conditions = publicConditions(tool);
              return (
                <li key={tool.id} className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="break-words font-medium">{tool.label}</span>
                    <span
                      className={
                        tool.status === "failed" ? "text-destructive" : "text-muted-foreground"
                      }
                    >
                      {TOOL_STATUS[tool.status]}
                    </span>
                  </div>
                  {tool.summary ? (
                    <p className="whitespace-pre-wrap break-words text-muted-foreground">
                      {tool.summary}
                    </p>
                  ) : null}
                  {conditions.length || tool.error ? (
                    <details className="group/condition">
                      <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-2 text-muted-foreground [&::-webkit-details-marker]:hidden">
                        조건{tool.error ? " 및 오류" : ""} 보기
                        <CaretDownIcon
                          aria-hidden="true"
                          className="size-4 group-open/condition:rotate-180"
                        />
                      </summary>
                      <div className="space-y-2 pb-2">
                        {conditions.length ? (
                          <dl className="grid gap-2">
                            {conditions.map(([label, value]) => (
                              <div key={label} className="flex flex-wrap gap-x-3 gap-y-1">
                                <dt className="text-muted-foreground">{label}</dt>
                                <dd className="break-words">{value}</dd>
                              </div>
                            ))}
                          </dl>
                        ) : null}
                        {tool.error ? (
                          <p className="break-words text-destructive">{tool.error}</p>
                        ) : null}
                      </div>
                    </details>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </details>
      ) : null}
      {showBubble ? (
        <section
          aria-label="AI 응답 본문"
          className="w-fit max-w-[92%] space-y-3 rounded-2xl border border-border bg-card px-4 py-3 shadow-sm sm:max-w-[85%]"
        >
          {hasText ? <AssistantMarkdown text={message.text!} /> : null}
          {message.error ? (
            <p role="alert" className="text-base text-destructive">
              {readableError(message.error)}
            </p>
          ) : null}
          {showThinking ? <ChatThinkingIndicator /> : null}
          {cancelRequested ? (
            <p className="text-base text-muted-foreground">취소를 요청했습니다.</p>
          ) : null}
          {stream.status === "cancelled" ? (
            <p className="text-base text-muted-foreground">답변을 중지했습니다.</p>
          ) : null}
        </section>
      ) : null}
      {streetViewLinks.length ? (
        <div className="flex flex-wrap gap-2">
          {streetViewLinks.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`${link.locationName} Google 스트리트뷰 (새 창)`}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-base font-medium text-primary hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
            >
              {link.locationName} Google 스트리트뷰
              <ArrowSquareOutIcon aria-hidden="true" className="size-5 shrink-0" />
            </a>
          ))}
        </div>
      ) : null}
      {(message.ui_spec && Object.keys(uiResults).length) || fallback || personalSearch ? (
        <AgentResultDetailDialog open={detailOpen} onOpenChange={setDetailOpen}>
          {message.ui_spec && Object.keys(uiResults).length ? (
            <AgentGeneratedUI
              spec={message.ui_spec}
              results={uiResults}
              onAction={handleAction}
              fallback={fallback}
            />
          ) : (
            fallback
          )}
          {personalSearch ? (
            <PersonalSearchResult
              query={personalSearch.query}
              kind={personalSearch.kind}
              onNavigate={() => setDetailOpen(false)}
            />
          ) : null}
        </AgentResultDetailDialog>
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
        </div>
      ) : null}
    </article>
  );
}
