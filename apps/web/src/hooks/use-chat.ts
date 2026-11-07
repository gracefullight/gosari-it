import { useQueryClient } from "@tanstack/react-query";
import { useAtom, useSetAtom, useStore } from "jotai";
import { useCallback } from "react";
import { applyAgentEvent, emptyAgentState } from "@/lib/agent-chat";
import { AgentStreamDisconnectedError } from "@/lib/agent-stream";
import { type AnalysisStreamOptions, cancelAnalysisJob } from "@/lib/analysis-jobs";
import { ApiError, api } from "@/lib/gosari.api";
import type { JobResult } from "@/lib/gosari.types";
import type { ChatMessage, Feature } from "@/stores/chat.atoms";
import {
  activeFeatureAtom,
  analysisJobsAtom,
  conversationIdAtom,
  featureErrorsAtom,
  featureResultsAtom,
  lastCommitNoticeAtom,
  messagesAtom,
  onboardingDoneAtom,
  pendingRequestsAtom,
} from "@/stores/chat.atoms";

let counter = 0;
const streams = new Map<string, { controller: AbortController; jobId?: string }>();
function nextId(): string {
  counter += 1;
  return `msg-${Date.now()}-${counter}`;
}

export function useChat() {
  const store = useStore();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useAtom(messagesAtom);
  const [conversationId, setConversationId] = useAtom(conversationIdAtom);
  const [activeFeature, setActiveFeature] = useAtom(activeFeatureAtom);
  const setFeatureResults = useSetAtom(featureResultsAtom);
  const setFeatureErrors = useSetAtom(featureErrorsAtom);
  const setLastCommitNotice = useSetAtom(lastCommitNoticeAtom);
  const setPendingRequests = useSetAtom(pendingRequestsAtom);
  const setOnboardingDone = useSetAtom(onboardingDoneAtom);
  const setAnalysisJobs = useSetAtom(analysisJobsAtom);

  const updatePendingRequests = useCallback(
    (feature: Feature | null, delta: number) => {
      const key = feature ?? "chat";
      setPendingRequests((prev) => ({ ...prev, [key]: Math.max(0, (prev[key] ?? 0) + delta) }));
    },
    [setPendingRequests]
  );

  const push = useCallback(
    (message: Omit<ChatMessage, "id">) => {
      setMessages((prev) => [...prev, { ...message, id: nextId() }]);
    },
    [setMessages]
  );

  const runChat = useCallback(
    async (
      work: (options: AnalysisStreamOptions) => Promise<JobResult>,
      existingId?: string,
      lastEventId?: string
    ) => {
      const id = existingId ?? nextId();
      const handle = { controller: new AbortController(), jobId: undefined as string | undefined };
      streams.set(id, handle);
      if (!existingId)
        setMessages((prev) => [
          ...prev,
          { id, role: "assistant", kind: "agent", text: "", stream: emptyAgentState() },
        ]);
      else
        setMessages((prev) =>
          prev.map((message) =>
            message.id === id
              ? {
                  ...message,
                  error: undefined,
                  stream: { ...message.stream!, status: "streaming" },
                }
              : message
          )
        );
      updatePendingRequests(null, 1);
      try {
        const job = await work({
          signal: handle.controller.signal,
          conversationId: conversationId ?? undefined,
          queryClient,
          lastEventId,
          onProgress: (progress) => {
            handle.jobId = progress.job_id;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === id
                  ? {
                      ...message,
                      stream: { ...(message.stream ?? emptyAgentState()), job_id: progress.job_id },
                    }
                  : message
              )
            );
          },
          onEvent: (event) => {
            handle.jobId = event.job_id;
            setMessages((prev) =>
              prev.map((message) => (message.id === id ? applyAgentEvent(message, event) : message))
            );
          },
        });
        setMessages((prev) =>
          prev.map((message) =>
            message.id === id
              ? {
                  ...message,
                  envelope: job.result ?? message.envelope,
                  error: job.error ?? message.error,
                  stream: {
                    ...(message.stream ?? emptyAgentState()),
                    job_id: job.job_id,
                    status:
                      job.stage === "cancelled"
                        ? "cancelled"
                        : job.stage === "failed"
                          ? "failed"
                          : "completed",
                  },
                }
              : message
          )
        );
      } catch (error) {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === id
              ? {
                  ...message,
                  error: handle.controller.signal.aborted
                    ? undefined
                    : error instanceof AgentStreamDisconnectedError
                      ? error.message
                      : error instanceof ApiError
                        ? error.message
                        : "답변을 받지 못했습니다. 다시 시도해 주세요.",
                  stream: {
                    ...(message.stream ?? emptyAgentState()),
                    status: handle.controller.signal.aborted
                      ? "cancelled"
                      : error instanceof AgentStreamDisconnectedError
                        ? "disconnected"
                        : "failed",
                  },
                }
              : message
          )
        );
      } finally {
        if (streams.get(id) === handle) streams.delete(id);
        updatePendingRequests(null, -1);
      }
    },
    [queryClient, conversationId, setMessages, updatePendingRequests]
  );

  const runSpec = useCallback(
    async (spec: Record<string, unknown>, safeText: string, targetFeature?: Feature | null) => {
      const pageFeature = targetFeature !== undefined ? targetFeature : activeFeature;
      if (!pageFeature) {
        await runChat((options) => api.runAnalysis(spec, safeText, options));
        return;
      }
      updatePendingRequests(pageFeature, 1);
      if (pageFeature) {
        setFeatureErrors((prev) => ({ ...prev, [pageFeature]: null }));
      }
      let jobId: string | undefined;
      try {
        const job = await api.runAnalysis(spec, safeText, {
          onProgress: (progress) => {
            jobId = progress.job_id;
            const event = progress.events.at(-1) as { safe_message?: string } | undefined;
            setAnalysisJobs((prev) => ({
              ...prev,
              [progress.job_id]: {
                feature: pageFeature,
                message: event?.safe_message ?? "자료 확인 중…",
              },
            }));
          },
        });
        if (job.stage === "cancelled") {
          if (!pageFeature) push({ role: "assistant", kind: "text", text: "조회를 취소했습니다." });
          return;
        }
        if (pageFeature) {
          if (job.result) {
            setFeatureResults((prev) => ({ ...prev, [pageFeature]: job.result! }));
          } else {
            setFeatureErrors((prev) => ({
              ...prev,
              [pageFeature]: job.error ?? "작업 실패",
            }));
          }
        } else if (job.result) {
          push({ role: "assistant", kind: "result", envelope: job.result });
        } else {
          push({ role: "assistant", kind: "error", error: job.error ?? "작업 실패" });
        }
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : "분석 요청에 실패했습니다.";
        if (pageFeature) {
          setFeatureErrors((prev) => ({ ...prev, [pageFeature]: msg }));
        } else {
          push({ role: "assistant", kind: "error", error: msg });
        }
      } finally {
        if (jobId)
          setAnalysisJobs((prev) => {
            const next = { ...prev };
            delete next[jobId!];
            return next;
          });
        updatePendingRequests(pageFeature, -1);
      }
    },
    [
      activeFeature,
      push,
      updatePendingRequests,
      setFeatureErrors,
      setFeatureResults,
      setAnalysisJobs,
      runChat,
    ]
  );

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setOnboardingDone(true);
      setActiveFeature(null);
      setLastCommitNotice(null);
      push({ role: "user", kind: "text", text: trimmed });
      updatePendingRequests(null, 1);
      const requestId = nextId();
      const controller = new AbortController();
      streams.set(requestId, { controller });
      try {
        const conversation = conversationId ?? crypto.randomUUID();
        if (!conversationId) setConversationId(conversation);
        const response = await api.chat(
          { text: trimmed, conversation_id: conversation },
          controller.signal
        );
        if (controller.signal.aborted) {
          if (response.kind === "job") void cancelAnalysisJob(response.job_id).catch(() => {});
          return;
        }
        if (response.kind === "job") {
          await runChat((options) => api.streamJob(response, options));
          return;
        }
        const prepared = response.preparation;
        if (prepared.classification === "personal") {
          push({ role: "assistant", kind: "personal-form", prepare: prepared });
        } else if (prepared.spec && !prepared.needs_confirmation) {
          await runSpec(prepared.spec, trimmed, null);
          return;
        } else if (prepared.spec) {
          push({ role: "assistant", kind: "clarify", prepare: prepared });
        } else {
          push({ role: "assistant", kind: "clarify", prepare: prepared });
        }
      } catch (err) {
        if (!controller.signal.aborted)
          push({
            role: "assistant",
            kind: "error",
            error: err instanceof ApiError ? err.message : "요청을 처리할 수 없습니다.",
          });
      } finally {
        streams.delete(requestId);
        updatePendingRequests(null, -1);
      }
    },
    [
      push,
      runSpec,
      runChat,
      conversationId,
      setConversationId,
      setActiveFeature,
      updatePendingRequests,
      setLastCommitNotice,
      setOnboardingDone,
    ]
  );

  const confirmSpec = useCallback(
    (spec: Record<string, unknown>, label: string, targetFeature?: Feature | null) => {
      const pageFeature = targetFeature !== undefined ? targetFeature : activeFeature;
      if (!pageFeature) {
        push({ role: "user", kind: "text", text: label });
      }
      void runSpec(spec, label, pageFeature);
    },
    [activeFeature, push, runSpec]
  );

  const openFeature = useCallback(
    (feature: Feature | null) => {
      setOnboardingDone(true);
      setLastCommitNotice(null);
      setActiveFeature(feature);
      if (feature === null) {
        window.requestAnimationFrame(() => {
          document.getElementById("gosari-composer")?.focus({ preventScroll: true });
        });
      }
    },
    [setActiveFeature, setLastCommitNotice, setOnboardingDone]
  );

  const resumeStream = useCallback(
    (messageId: string) => {
      const message = store.get(messagesAtom).find((item) => item.id === messageId);
      if (!message?.stream?.job_id || streams.has(messageId)) return;
      void runChat(
        async (options) => api.streamJob(await api.getJob(message.stream!.job_id!), options),
        messageId,
        message.stream.last_event_id
      );
    },
    [store, runChat]
  );

  const cancelStream = useCallback(
    async (messageId: string) => {
      const message = messages.find((item) => item.id === messageId);
      const jobId = message?.stream?.job_id;
      if (!jobId) return;
      try {
        await cancelAnalysisJob(jobId);
        setMessages((prev) =>
          prev.map((item) =>
            item.id === messageId
              ? {
                  ...item,
                  error: undefined,
                  stream: {
                    ...item.stream!,
                    stage_message: "취소를 요청했습니다.",
                  },
                }
              : item
          )
        );
        if (!streams.has(messageId)) resumeStream(messageId);
      } catch {
        setMessages((prev) =>
          prev.map((item) =>
            item.id === messageId
              ? { ...item, error: "취소를 요청하지 못했습니다. 다시 시도해 주세요." }
              : item
          )
        );
      }
    },
    [messages, setMessages, resumeStream]
  );

  const resetConversation = useCallback(() => {
    for (const handle of streams.values()) {
      handle.controller.abort();
      if (handle.jobId) void cancelAnalysisJob(handle.jobId).catch(() => {});
    }
    streams.clear();
    void queryClient.cancelQueries({ queryKey: ["analysis", "stream"] });
    setMessages([]);
    setConversationId(null);
    setLastCommitNotice(null);
    setActiveFeature(null);
    window.requestAnimationFrame(() =>
      document.getElementById("gosari-composer")?.focus({ preventScroll: true })
    );
  }, [queryClient, setMessages, setConversationId, setLastCommitNotice, setActiveFeature]);

  return {
    messages,
    send,
    confirmSpec,
    runSpec,
    openFeature,
    push,
    cancelStream,
    resumeStream,
    resetConversation,
  };
}
