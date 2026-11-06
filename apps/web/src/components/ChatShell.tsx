import { Alert, Button, LinearProgress } from "@gracefullight/krds-tw";
import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";
import characterUrl from "../assets/character-256.png";
import { useChat } from "../hooks/useChat";
import type { Preview } from "../lib/types";
import type { ChatMessage } from "../stores/app";
import { busyAtom, chatStateAtom, messagesAtom, onboardingDoneAtom } from "../stores/app";
import { Composer } from "./Composer";
import { ConfirmDialog } from "./ConfirmDialog";
import { ResultCard } from "./cards";
import { ConditionForm, NotebookForm, RegionForm, ShareForm } from "./forms";

const QUICK_SPECS: { label: string; spec: Record<string, unknown> }[] = [
  {
    label: "선흘 2023·2024년 봄 강수 비교",
    spec: {
      operation: "history_compare",
      source_ids: ["jeju_579"],
      station_selections: [{ source_id: "jeju_579", station_name: "선흘" }],
      years: [2023, 2024],
      month_day_start: "04-01",
      month_day_end: "05-31",
      elements: ["daily_rainfall"],
      comparison_scope: "common_valid_month_days",
      aggregation: "count_positive_days",
      unit: "day",
      timezone: "Asia/Seoul",
    },
  },
  {
    label: "당일 관측 표본 보기",
    spec: { operation: "current_observation", source_ids: ["kma_aws"] },
  },
  {
    label: "상품 표시가 조사",
    spec: { operation: "retail_lookup", source_ids: ["retail_sample"], price_channel: "retail" },
  },
  {
    label: "도매 정산 표본 보기",
    spec: { operation: "market_query", source_ids: ["at_settlement"], price_channel: "wholesale" },
  },
];

function MessageView({
  message,
  onPreview,
}: {
  message: ChatMessage;
  onPreview: (p: Preview) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-green-700 px-4 py-3 text-base text-white">
          {message.text}
        </div>
      </div>
    );
  }
  if (message.kind === "error") {
    return <Alert severity="danger">{message.error}</Alert>;
  }
  if (message.kind === "result" && message.envelope) {
    return <ResultCard envelope={message.envelope} />;
  }
  if (message.kind === "clarify" && message.prepare) {
    return <ConditionForm prepare={message.prepare} />;
  }
  if (message.kind === "personal-form" && message.prepare) {
    const feature = message.prepare.feature;
    if (feature === "notebook") return <NotebookForm onPreview={onPreview} />;
    if (feature === "share") return <ShareForm onPreview={onPreview} />;
    if (feature === "region_compare") return <RegionForm onPreview={onPreview} />;
    if (feature === "market_query" || feature === "retail_lookup") {
      return <PriceQuickActions />;
    }
    if (feature === "outing") {
      return <OutingQuickActions />;
    }
    return <ConditionForm prepare={message.prepare} />;
  }
  return (
    <div className="max-w-[85%] rounded-2xl bg-white px-4 py-3 text-base shadow-sm">
      {message.text}
    </div>
  );
}

function PriceQuickActions() {
  const { confirmSpec } = useChat();
  return (
    <div className="flex flex-wrap gap-2">
      {QUICK_SPECS.filter((q) =>
        ["retail_lookup", "market_query"].includes(q.spec.operation as string)
      ).map((q) => (
        <Button key={q.label} variant="secondary" onClick={() => confirmSpec(q.spec, q.label)}>
          {q.label}
        </Button>
      ))}
      <Button
        variant="secondary"
        onClick={() =>
          confirmSpec(
            { operation: "survey_link", source_ids: ["forestinfo"], price_channel: "survey" },
            "지역 조사가 링크"
          )
        }
      >
        지역 조사가 링크
      </Button>
    </div>
  );
}

function OutingQuickActions() {
  const { confirmSpec } = useChat();
  return (
    <div className="flex flex-wrap gap-2">
      {QUICK_SPECS.slice(0, 2).map((q) => (
        <Button key={q.label} variant="secondary" onClick={() => confirmSpec(q.spec, q.label)}>
          {q.label}
        </Button>
      ))}
    </div>
  );
}

export function ChatShell() {
  const chatState = useAtomValue(chatStateAtom);
  const busy = useAtomValue(busyAtom);
  const onboardingDone = useAtomValue(onboardingDoneAtom);
  const setOnboardingDone = useSetAtom(onboardingDoneAtom);
  const { messages, send, confirmSpec } = useChat();
  const setMessages = useSetAtom(messagesAtom);
  const [pendingPreview, setPendingPreview] = useState<Preview | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const showWelcome = !onboardingDone;
  const showEmpty = onboardingDone && messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6">
          {showWelcome && (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <img src={characterUrl} alt="" width={140} height={140} className="h-36 w-36" />
              <h1 className="text-2xl font-bold text-green-900">고사리잇에 오신 것을 환영합니다</h1>
              <p className="max-w-lg text-base text-gray-700">
                고사리철 날씨 비교, 경험 기록, 나눔 준비, 가격 확인을 돕습니다. 한 문장으로 질문하면
                필요한 조건은 대화 중에 확인합니다. 개인 기록은 현재 세션에서만 유지됩니다.
              </p>
              <div className="w-full max-w-2xl">
                <Composer onSend={send} autoFocus />
              </div>
              <Button variant="text" onClick={() => setOnboardingDone(true)}>
                건너뛰기
              </Button>
            </div>
          )}
          {Boolean(showEmpty) && (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <img src={characterUrl} alt="" width={128} height={128} className="h-32 w-32" />
              <h2 className="text-xl font-bold text-green-900">안녕하세요! 무엇을 도와드릴까요?</h2>
              <p className="text-base text-gray-600">
                지난 봄 관측 비교, 후보 날짜 날씨, 나눔 목록, 가격 조사를 물어보세요.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {QUICK_SPECS.map((q) => (
                  <Button
                    key={q.label}
                    variant="secondary"
                    size="small"
                    onClick={() => confirmSpec(q.spec, q.label)}
                  >
                    {q.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {messages.map((message) => (
            <MessageView key={message.id} message={message} onPreview={setPendingPreview} />
          ))}
          {busy && (
            <div className="flex flex-col gap-2" role="status" aria-label="작업 진행 중">
              <LinearProgress />
              <span className="text-sm text-gray-500">조회·계산 중입니다…</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
      {(showEmpty || messages.length > 0) && (
        <div className="border-t border-gray-200 bg-white px-4 py-3">
          <div className="mx-auto max-w-4xl">
            <Composer onSend={send} disabled={busy} />
          </div>
        </div>
      )}
      {pendingPreview ? (
        <ConfirmDialog
          preview={pendingPreview}
          onClose={() => setPendingPreview(null)}
          onCommitted={(text) => {
            setPendingPreview(null);
            setMessages((prev) => [
              ...prev,
              { id: `committed-${Date.now()}`, role: "assistant", kind: "text", text },
            ]);
          }}
        />
      ) : null}
      {chatState === "session.ended" && null}
    </div>
  );
}
