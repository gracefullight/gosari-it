import { CircleNotchIcon } from "@phosphor-icons/react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef, useState } from "react";
import characterUrl from "@/assets/character-256.png";
import { AnalysisConditionForm } from "@/components/analysis-condition-form";
import { AnalysisJobStatus } from "@/components/analysis-job-status";
import { ApprovalConfirmDialog } from "@/components/approval-confirm-dialog";
import { ChatComposer } from "@/components/chat-composer";
import { NotebookForm } from "@/components/notebook-form";
import { PersonalSearchResult } from "@/components/personal-search-result";
import { PriceLookupPage } from "@/components/price-lookup-page";
import { RegionForm } from "@/components/region-form";
import { ResultCard } from "@/components/result-card";
import { ShareForm } from "@/components/share-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { WeatherMapPage } from "@/components/weather-map-page";
import { useChat } from "@/hooks/use-chat";
import { resolveAppRoute } from "@/lib/app-routes";
import type { Preview } from "@/lib/gosari.types";
import {
  activeFeatureAtom,
  appPathAtom,
  busyAtom,
  type ChatMessage,
  lastCommitNoticeAtom,
  messagesAtom,
  navigateToPathAtom,
  revisionCounterAtom,
} from "@/stores/chat.atoms";

function MessageView({
  message,
  onPreview,
}: {
  message: ChatMessage;
  onPreview: (preview: Preview) => void;
}) {
  if (message.role === "user")
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-3 text-base text-primary-foreground">
          {message.text}
        </div>
      </div>
    );
  if (message.kind === "error")
    return (
      <Alert variant="destructive">
        <AlertDescription>{message.error}</AlertDescription>
      </Alert>
    );
  if (message.kind === "result" && message.envelope)
    return <ResultCard envelope={message.envelope} />;
  if (message.kind === "clarify" && message.prepare)
    return <AnalysisConditionForm prepare={message.prepare} />;
  if (message.kind === "personal-form" && message.prepare) {
    const feature = message.prepare.feature;
    if (feature === "personal_search" && message.prepare.form?.query)
      return <PersonalSearchResult query={message.prepare.form.query} />;
    if (feature === "notebook") return <NotebookForm mode="write" onPreview={onPreview} />;
    if (feature === "share") return <ShareForm onPreview={onPreview} />;
    if (feature === "region_compare")
      return <RegionForm onPreview={onPreview} hideStationCompare />;
    if (feature === "market_query" || feature === "retail_lookup") return <PriceLookupPage />;
    if (feature === "outing") return <WeatherMapPage mode="outing" onPreview={onPreview} />;
    return <AnalysisConditionForm prepare={message.prepare} />;
  }
  return (
    <div className="max-w-[85%] rounded-2xl border border-border bg-card px-4 py-3 text-base">
      {message.text}
    </div>
  );
}

const PAGE_TITLES = {
  나들이: "나들이",
  "지역 탐색": "지역 탐색",
  "내 수첩": "내 수첩",
  나눔: "나눔",
  "가격 조사": "가격 조사",
};

export function ChatShell() {
  const activeFeature = useAtomValue(activeFeatureAtom);
  const path = useAtomValue(appPathAtom);
  const route = resolveAppRoute(path);
  const navigate = useSetAtom(navigateToPathAtom);
  const busy = useAtomValue(busyAtom);
  const [lastCommitNotice, setLastCommitNotice] = useAtom(lastCommitNoticeAtom);
  const setRevision = useSetAtom(revisionCounterAtom);
  const { messages, send, openFeature } = useChat();
  const setMessages = useSetAtom(messagesAtom);
  const [pendingPreview, setPendingPreview] = useState<Preview | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!activeFeature && (messages.length > 0 || busy))
      bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeFeature, messages.length, busy]);
  const isEmptyHome = !activeFeature && messages.length === 0 && route.found;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div
          data-tour="page-content"
          className={`mx-auto flex w-full flex-col gap-5 px-4 py-6 sm:px-7 max-w-7xl ${isEmptyHome ? "flex-1 justify-center" : ""}`}
        >
          <AnalysisJobStatus />
          {!route.found ? (
            <div className="py-20 text-center">
              <h1 className="text-2xl font-bold">페이지를 찾을 수 없습니다</h1>
              <Button className="mt-6" onClick={() => navigate("/")}>
                홈으로
              </Button>
            </div>
          ) : activeFeature ? (
            <>
              <header className="flex items-center justify-between gap-3">
                <h1 className="text-2xl font-bold tracking-tight">{PAGE_TITLES[activeFeature]}</h1>
              </header>
              {lastCommitNotice ? (
                <Alert className="border-primary/30 bg-secondary">
                  <AlertDescription>{lastCommitNotice}</AlertDescription>
                </Alert>
              ) : null}
              {activeFeature === "나들이" ? (
                <WeatherMapPage mode="outing" onPreview={setPendingPreview} />
              ) : null}
              {activeFeature === "지역 탐색" ? (
                <WeatherMapPage mode="regions" onPreview={setPendingPreview} />
              ) : null}
              {activeFeature === "내 수첩" ? (
                <NotebookForm
                  key={path}
                  mode={route.notebookMode}
                  recordId={route.recordId}
                  initialDate={
                    new URLSearchParams(path.split("?")[1] ?? "").get("date") ?? undefined
                  }
                  initialEvidenceIds={new URLSearchParams(path.split("?")[1] ?? "").getAll(
                    "evidence"
                  )}
                  onNavigate={navigate}
                  onPreview={setPendingPreview}
                />
              ) : null}
              {activeFeature === "나눔" ? <ShareForm onPreview={setPendingPreview} /> : null}
              {activeFeature === "가격 조사" ? <PriceLookupPage /> : null}
            </>
          ) : (
            <>
              {isEmptyHome ? (
                <div className="flex flex-col items-center gap-5 py-8 text-center">
                  <img src={characterUrl} alt="" width={132} height={132} className="size-32" />
                  <h1 className="text-4xl font-bold tracking-tight text-primary sm:text-5xl">
                    고사리잇
                  </h1>
                  <p className="text-base text-muted-foreground">
                    제주 날씨 · 채취 기록 · 나눔 · 가격
                  </p>
                  <div className="mt-2 flex flex-wrap justify-center gap-2">
                    <Button variant="outline" onClick={() => openFeature("나들이")}>
                      제주 날씨 지도
                    </Button>
                    <Button variant="outline" onClick={() => openFeature("지역 탐색")}>
                      지역 탐색
                    </Button>
                    <Button variant="outline" onClick={() => navigate("/notebook/new")}>
                      기록 쓰기
                    </Button>
                    <Button variant="outline" onClick={() => openFeature("가격 조사")}>
                      고사리 가격
                    </Button>
                  </div>
                </div>
              ) : null}
              {messages.map((message) => (
                <MessageView key={message.id} message={message} onPreview={setPendingPreview} />
              ))}
              {busy && messages.length > 0 ? (
                <div
                  className="flex items-center gap-2 text-base text-muted-foreground"
                  role="status"
                >
                  <CircleNotchIcon
                    className="size-4 animate-spin motion-reduce:animate-none"
                    aria-hidden="true"
                  />
                  답변 준비 중…
                </div>
              ) : null}
              <div ref={bottom} />
            </>
          )}
        </div>
      </div>
      {!activeFeature && route.found ? (
        <div className="flex h-[var(--app-footer-height)] min-h-[var(--app-footer-height)] shrink-0 items-center border-t border-border bg-background px-4 py-3">
          <div className="mx-auto w-full max-w-4xl">
            <ChatComposer onSend={send} disabled={busy} autoFocus />
          </div>
        </div>
      ) : null}
      {pendingPreview ? (
        <ApprovalConfirmDialog
          preview={pendingPreview}
          onClose={() => setPendingPreview(null)}
          onCommitted={(text) => {
            setPendingPreview(null);
            setRevision((value) => value + 1);
            if (activeFeature) {
              setLastCommitNotice(text);
              if (activeFeature === "내 수첩") navigate("/notebook");
            } else
              setMessages((previous) => [
                ...previous,
                { id: `committed-${Date.now()}`, role: "assistant", kind: "text", text },
              ]);
          }}
        />
      ) : null}
    </div>
  );
}
