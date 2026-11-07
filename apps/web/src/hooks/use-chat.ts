import { useAtom, useSetAtom } from "jotai";
import { useCallback } from "react";
import { ApiError, api } from "@/lib/gosari.api";
import type { ChatMessage, Feature } from "@/stores/chat.atoms";
import {
  activeFeatureAtom,
  analysisJobsAtom,
  featureErrorsAtom,
  featureResultsAtom,
  lastCommitNoticeAtom,
  messagesAtom,
  onboardingDoneAtom,
  pendingRequestsAtom,
} from "@/stores/chat.atoms";

let counter = 0;
function nextId(): string {
  counter += 1;
  return `msg-${Date.now()}-${counter}`;
}

export function useChat() {
  const [messages, setMessages] = useAtom(messagesAtom);
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

  const runSpec = useCallback(
    async (spec: Record<string, unknown>, safeText: string, targetFeature?: Feature | null) => {
      const pageFeature = targetFeature !== undefined ? targetFeature : activeFeature;
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
      try {
        const prepared = await api.prepare({ text: trimmed });
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
        push({
          role: "assistant",
          kind: "error",
          error: err instanceof ApiError ? err.message : "요청을 처리할 수 없습니다.",
        });
      } finally {
        updatePendingRequests(null, -1);
      }
    },
    [push, runSpec, setActiveFeature, updatePendingRequests, setLastCommitNotice, setOnboardingDone]
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

  return { messages, send, confirmSpec, runSpec, openFeature, push };
}
